import getpass
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import uuid
import webbrowser
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import db_backend
import dnd_fork as game
import web_auth


ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
IS_RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))
DB_LOCATION = os.environ.get("DB_LOCATION", "local").strip()
DATABASE_IS_REMOTE = DB_LOCATION.casefold() != "local"
if DATABASE_IS_REMOTE and not db_backend.is_remote(DB_LOCATION):
    raise ValueError("DB_LOCATION deve essere 'local' oppure una connection string PostgreSQL (postgres:// o postgresql://).")
DATA_DIR_ENV = os.environ.get("DND_DATA_DIR", "").strip()
if IS_RENDER and not DATABASE_IS_REMOTE and not DATA_DIR_ENV:
    raise RuntimeError("DND_DATA_DIR non configurata. Su Render impostala sul mount path del disco persistente (/var/data).")
DATA_DIR = os.path.abspath(DATA_DIR_ENV or ROOT)
os.makedirs(DATA_DIR, exist_ok=True)


def migrate_persistent_data(filename, sqlite_database=False):
    source_path = os.path.join(ROOT, filename)
    target_path = os.path.join(DATA_DIR, filename)
    if os.path.abspath(source_path) == os.path.abspath(target_path) or os.path.exists(target_path) or not os.path.isfile(source_path):
        return
    if sqlite_database:
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix=".migration-", suffix=".db", dir=DATA_DIR, delete=False) as temporary_file:
                temporary_path = temporary_file.name
            source = sqlite3.connect(source_path)
            target = sqlite3.connect(temporary_path)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            os.replace(temporary_path, target_path)
        except Exception:
            if temporary_path and os.path.exists(temporary_path):
                os.remove(temporary_path)
            raise
    else:
        shutil.copy2(source_path, target_path)


DB_FILENAME = os.path.basename(game.DB_FILE)
KEY_FILENAME = os.path.basename(game.KEY_FILE)
migrate_persistent_data("utenti_web.json")
migrate_persistent_data(KEY_FILENAME)
if DATABASE_IS_REMOTE:
    game.DB_FILE = DB_LOCATION
    game.KEY_FILE = os.path.join(DATA_DIR, KEY_FILENAME)
else:
    migrate_persistent_data(DB_FILENAME, sqlite_database=True)
    game.DB_FILE = os.path.join(DATA_DIR, DB_FILENAME)
    game.KEY_FILE = os.path.join(DATA_DIR, KEY_FILENAME)
HOST = os.environ.get("HOST", "0.0.0.0" if IS_RENDER else "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
WEB_USERNAME = os.environ.get("WEB_USERNAME", "")
WEB_PASSWORD = os.environ.get("DnD_USER_PASSWORD", "")
USERS_FILE = os.path.join(DATA_DIR, "utenti_web.json")
DB = game.DnDDatabase(game.DB_FILE)
AUTH_STORE = web_auth.WebAuthStore(game.DB_FILE, USERS_FILE, WEB_USERNAME, WEB_PASSWORD)
LOCK = threading.Lock()
ADVENTURE_LOCKS_LOCK = threading.Lock()
ADVENTURE_LOCKS = {}
RAZZE_PERSONAGGIO = ("Umano", "Elfo", "Nano", "Halfling")
CLASSI_RAZZA_BECMI = {"2", "3", "7"}
game.migra_json_in_sqlite(DB)


def api_key_active():
    key = getattr(game, "API_KEY_ATTIVA", "")
    if key:
        return key
    return game.carica_api_key_salvata() or os.environ.get("GEMINI_API_KEY", "").strip()


def api_key_status():
    saved_key = game.carica_api_key_salvata()
    environment_key = os.environ.get("GEMINI_API_KEY", "").strip()
    active_key = api_key_active()
    if active_key and active_key == saved_key:
        source = "file"
    elif active_key and active_key == environment_key:
        source = "variabile d'ambiente"
    elif active_key:
        source = "argomento o pannello admin"
    else:
        source = "non configurata"
    masked = f"{active_key[:4]}…{active_key[-4:]}" if len(active_key) > 8 else "****" if active_key else ""
    return {"configured": bool(active_key), "source": source, "masked": masked}


def json_response(handler, status, data, headers=None):
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Cache-Control", "no-store")
    for name, value in (headers or {}).items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(payload)


def adventure_lock_for(adventure_id):
    with ADVENTURE_LOCKS_LOCK:
        return ADVENTURE_LOCKS.setdefault(adventure_id, threading.Lock())


def body_json(handler):
    size = int(handler.headers.get("Content-Length", "0"))
    if not size:
        return {}
    return json.loads(handler.rfile.read(size).decode("utf-8"))


def safe_adventures():
    return DB.carica_tutte_avventure()


def safe_characters():
    return DB.carica_tutti_personaggi()


def character_view(character):
    return {
        "nome": character["nome"],
        "classe": character["classe"],
        "razza": character.get("razza", "Umano"),
        "livello": character["livello"],
        "allineamento": character["allineamento"],
        "deceduto": bool(character.get("deceduto", False) or character["pf_attuali"] <= 0),
        "avventura_morte": character.get("avventura_morte", ""),
        "pf_attuali": character["pf_attuali"],
        "pf_max": character["pf_max"],
        "ca": character["ca"],
        "mo": character["mo"],
        "pe": character["pe"],
    }


def adventure_view(adventure):
    party = adventure.get("party") or [adventure.get("eroe", "Valen di Corvobianco")]
    storia = adventure.get("storia", [])
    return {
        "id": adventure["id"],
        "titolo": adventure["titolo"],
        "party": party,
        "data": adventure.get("data", ""),
        "modulo_pdf": adventure.get("modulo_pdf", ""),
        "modalita": adventure.get("stato_dungeon", {}).get("modalita_gioco", game.MODALITA_GIOCO),
        "storia": [
            {
                "role": message["role"],
                "text": "".join(part.get("text", "") for part in message.get("parts", []))
            }
            for message in storia[-200:]
            if message.get("parts")
        ],
    }


def get_party(adventure, characters):
    party_names = adventure.get("party") or [adventure.get("eroe", "Valen di Corvobianco")]
    party = []
    for name in party_names:
        hero = characters.get(name)
        if not hero:
            _, hero = game.normalizza_personaggio_json(name, {})
            DB.salva_personaggio(hero)
            characters = DB.carica_tutti_personaggi()
            hero = characters[name]
        party.append(hero)
    return party


def capture_console(callback):
    output = io.StringIO()
    with redirect_stdout(output):
        result = callback()
    text = output.getvalue().strip()
    return text, result


def execute_slash(adventure, party, action):
    stripped = action.strip()
    lower = stripped.lower()
    eroi = party

    if lower in ("/help", "/aiuto", "/comandi", "/help pdf", "/comandi pdf"):
        if lower in ("/help pdf", "/comandi pdf"):
            text, _ = capture_console(lambda: game.aggiorna_manuale_comandi_pdf(forza=True, silenzioso=False))
        else:
            text = game.HELP_TESTO
        return True, text

    if lower.startswith(("/inventario", "/zaino", "/equip")):
        command = lower.split(maxsplit=1)[0]
        name = stripped[len(command):].strip()
        if name and name.lower() not in ("party", "tutti"):
            selected = next((e for e in eroi if e["nome"].lower() == name.lower()), None)
            text, _ = capture_console(lambda: game.mostra_inventario(selected) if selected else print("Personaggio non trovato."))
        else:
            text, _ = capture_console(lambda: game.mostra_inventario_party(eroi))
        return True, text

    if lower in ("", "/magia", "/incantesimi", "/grimorio", "/spells"):
        text, _ = capture_console(lambda: game.mostra_grimorio_e_incantesimi(eroi[0]))
        return True, text

    if lower.startswith("/lancia"):
        text, _ = capture_console(lambda: game.gestisci_comando_lancia(DB, eroi, adventure, stripped))
        return True, text

    if lower.startswith("/memorizza"):
        text, _ = capture_console(lambda: game.memorizza_incantesimo_eroe(DB, eroi[0]))
        return True, text

    if lower.startswith("/torcia"):
        subcmd = stripped[len("/torcia"):].strip()
        text, _ = capture_console(lambda: game.gestisci_comando_torcia(DB, eroi, adventure, subcmd))
        return True, text

    if lower.startswith("/ambiente"):
        subcmd = stripped[len("/ambiente"):].strip()
        text, _ = capture_console(lambda: game.gestisci_comando_ambiente(DB, adventure, subcmd))
        return True, text

    if lower.startswith("/incontri"):
        subcmd = stripped[len("/incontri"):].strip()
        text, _ = capture_console(lambda: game.gestisci_comando_incontri(DB, adventure, subcmd))
        return True, text

    if lower.startswith("/modalita"):
        subcmd = stripped[len("/modalita"):].strip()
        text, _ = capture_console(lambda: game.gestisci_comando_modalita(DB, adventure, subcmd))
        return True, text

    if lower.startswith("/riposo"):
        text, _ = capture_console(lambda: game.gestisci_comando_riposo(DB, eroi, adventure))
        return True, text

    if lower in ("/scheda pdf", "/schedapdf"):
        text, _ = capture_console(lambda: print(game.esporta_scheda_pdf_a4(eroi[0])))
        return True, text

    if lower.startswith("/mappa pdf") or lower.startswith("/mappapdf") or lower == "/esporta mappa":
        text, _ = capture_console(lambda: print(game.esporta_mappa_pdf_a4(adventure, eroi)))
        return True, text

    if lower.startswith("/esporta"):
        subcommand = lower[len("/esporta"):].strip()
        if subcommand in ("mappa", "mappapdf"):
            text, _ = capture_console(lambda: print(game.esporta_mappa_pdf_a4(adventure, eroi)))
        elif subcommand in ("scheda", "schede", "schedapdf"):
            text, _ = capture_console(lambda: [print(game.esporta_scheda_pdf_a4(hero)) for hero in eroi])
        else:
            text, _ = capture_console(lambda: print(game.esporta_cronaca_avventura(DB, adventure, eroi)))
        return True, text

    if lower in ("/suoni", "/suoni test", "/suoni prova", "/audio", "/audio test", "/audio prova"):
        command = lower.split(maxsplit=1)[0]
        sub = lower[len(command):].strip()
        if sub in ("test", "prova"):
            text, _ = capture_console(game.testa_effetti_sonori)
        else:
            game.SUONI_ATTIVI = not game.SUONI_ATTIVI
            text = "Effetti sonori attivi." if game.SUONI_ATTIVI else "Effetti sonori disattivati."
        return True, text

    return False, ""


def perform_action(adventure_id, action, user):
    with adventure_lock_for(adventure_id):
        with LOCK:
            adventure = safe_adventures().get(adventure_id)
            if not adventure:
                return 404, {"error": "Avventura non trovata."}
            characters = safe_characters()
            party = get_party(adventure, characters)
        if not AUTH_STORE.is_member(user["id"], adventure_id):
            return 403, {"error": "Unisciti all'avventura prima di inviare azioni."}
        party_names = adventure.get("party") or [adventure.get("eroe", "Valen di Corvobianco")]
        character_name = AUTH_STORE.member_character(user["id"], adventure_id)
        owned_names = {name.casefold() for name in AUTH_STORE.character_names(user["id"])}
        party_names_normalized = {name.casefold() for name in party_names}
        if not character_name or character_name.casefold() not in owned_names or character_name.casefold() not in party_names_normalized:
            character_name = next((name for name in party_names if name.casefold() in owned_names), None)
            if not character_name:
                return 409, {"error": "Non è possibile identificare il tuo personaggio in questa avventura. Contatta il proprietario della sessione."}
            AUTH_STORE.set_member_character(user["id"], adventure_id, character_name)

        selected_character = characters.get(character_name)
        if selected_character is None:
            return 403, {"error": "Questo personaggio è nel cimitero e non può più giocare."}
        if selected_character.get("deceduto") or selected_character["pf_attuali"] <= 0:
            return 403, {"error": "Questo personaggio è nel cimitero e non può più giocare."}

        with LOCK:
            slash, slash_output = execute_slash(adventure, party, action)
        if slash:
            clean_output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", slash_output)
            return 200, {"ok": True, "output": clean_output, "slash": True, "adventure": adventure_view(adventure)}

        key = api_key_active()
        if not key:
            return 400, {"error": "Chiave Gemini non configurata."}

        st_d = adventure.setdefault("stato_dungeon", {})
        for warning in game.aggiorna_tempo_e_torce(adventure, party):
            action += "\n" + warning
        turn = (len(adventure["storia"]) // 2) + 1
        encounter = game.verifica_incontro_errante(adventure, turn)
        if encounter:
            action += "\n" + encounter
        if st_d.get("modalita_gioco") == "classica":
            action += "\n" + "\n".join(game.genera_batteria_dadi(hero["nome"])["testo"] for hero in party)
        if adventure.get("buio_totale"):
            action += "\n[STATO AMBIENTALE: BUIO TOTALE.]"

        action = f"[{character_name}] {action}"
        adventure["storia"].append({"role": "user", "parts": [{"text": action}]})
        with LOCK:
            DB.aggiungi_messaggio(adventure_id, "user", action)
            DB.salva_metadati_avventura(adventure)

        pdf_path = adventure.get("modulo_pdf") if adventure.get("modulo_pdf") and not adventure.get("modulo_testo") else None
        response = game.chiama_gemini(
            adventure["storia"], key,
            game.costruisci_system_prompt(party, adventure),
            pdf_path=pdf_path,
            desc_attesa="sta valutando la scena",
        )
        adventure["storia"].append({"role": "model", "parts": [{"text": response}]})
        previously_alive = {
            hero["nome"]: not hero.get("deceduto", False) and hero["pf_attuali"] > 0
            for hero in party
        }
        game.aggiorna_party_da_riquadro(party, response)
        for hero in party:
            if previously_alive[hero["nome"]] and (hero.get("deceduto") or hero["pf_attuali"] <= 0):
                hero["avventura_morte"] = adventure["titolo"]
        with LOCK:
            for hero in party:
                DB.salva_personaggio(hero)
            DB.aggiungi_messaggio(adventure_id, "model", response)
            DB.salva_metadati_avventura(adventure)
        return 200, {"ok": True, "adventure": adventure_view(adventure)}


class WebHandler(BaseHTTPRequestHandler):
    server_version = "DndScatolaRossa/1.0"

    def session_token(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get("dnd_session")
        return morsel.value if morsel else ""

    def session_cookie(self, token=""):
        max_age = web_auth.SESSION_TTL_SECONDS if token else 0
        secure = "; Secure" if IS_RENDER else ""
        return f"dnd_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}"

    def require_auth(self):
        try:
            user = AUTH_STORE.get_user(self.session_token())
        except (OSError, ValueError) as exc:
            json_response(self, 500, {"error": str(exc)})
            return None
        if user:
            return user
        json_response(self, 401, {"error": "Accedi per continuare."})
        return None

    def require_admin(self):
        user = self.require_auth()
        if user is None:
            return False
        if user.get("is_admin"):
            return True
        json_response(self, 403, {"error": "Accesso riservato all'amministratore."})
        return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            json_response(self, 200, {"status": "ok"})
            return
        static_files = {
            "/app.webmanifest": ("app.webmanifest", "application/manifest+json"),
            "/service-worker.js": ("service-worker.js", "application/javascript; charset=utf-8"),
            "/imgs/app-icon-192.png": (os.path.join("imgs", "app-icon-192.png"), "image/png"),
            "/imgs/app-icon-512.png": (os.path.join("imgs", "app-icon-512.png"), "image/png"),
            "/imgs/apple-touch-icon.png": (os.path.join("imgs", "apple-touch-icon.png"), "image/png"),
            "/imgs/favicon-32.png": (os.path.join("imgs", "favicon-32.png"), "image/png"),
            "/imgs/app-icon.svg": (os.path.join("imgs", "app-icon.svg"), "image/svg+xml"),
            "/imgs/DnD.webp": (os.path.join("imgs", "DnD.webp"), "image/webp"),
        }
        if path in static_files:
            relative_path, content_type = static_files[path]
            try:
                with open(os.path.join(ROOT, relative_path), "rb") as asset_file:
                    payload = asset_file.read()
            except OSError as exc:
                json_response(self, 500, {"error": f"Impossibile leggere l'asset {path}: {exc}"})
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            cache_control = "no-cache" if path in ("/service-worker.js", "/app.webmanifest") else "public, max-age=3600"
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)
            return
        if path == "/" or path == "/index.html":
            self.send_response(200)
            payload = PAGE.encode("utf-8")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path == "/api/session":
            try:
                user = AUTH_STORE.get_user(self.session_token())
            except (OSError, ValueError) as exc:
                json_response(self, 500, {"error": str(exc)})
                return
            json_response(self, 200, {"authenticated": bool(user), "user": user})
            return
        if path == "/api/admin":
            if not self.require_admin():
                return
            try:
                json_response(self, 200, {"users": AUTH_STORE.list_users(), "api_key": api_key_status()})
            except (OSError, ValueError) as exc:
                json_response(self, 500, {"error": str(exc)})
            return
        user = self.require_auth()
        if user is None:
            return
        if path == "/api/state":
            with LOCK:
                adventures = safe_adventures()
                characters = safe_characters()
            owned_names = AUTH_STORE.character_names(user["id"])
            key = api_key_active()
            adventure_data = []
            for adventure in adventures.values():
                view = adventure_view(adventure)
                view["joined"] = AUTH_STORE.is_member(user["id"], adventure["id"])
                view["can_delete"] = AUTH_STORE.is_adventure_owner(user["id"], adventure["id"])
                view["members"] = AUTH_STORE.member_names(adventure["id"])
                adventure_data.append(view)
            cemetery = []
            for character in characters.values():
                if not (character.get("deceduto") or character["pf_attuali"] <= 0):
                    continue
                view = character_view(character)
                if not view["avventura_morte"]:
                    party_adventures = [
                        adventure["titolo"] for adventure in adventures.values()
                        if any(name.casefold() == character["nome"].casefold() for name in (adventure.get("party") or [adventure.get("eroe", "")]))
                    ]
                    view["avventura_morte"] = party_adventures[-1] if party_adventures else "Avventura non registrata"
                cemetery.append(view)
            json_response(self, 200, {
                "user": user,
                "adventures": adventure_data,
                "characters": [character_view(v) for v in characters.values()],
                "owned_characters": [character_view(characters[name]) for name in owned_names if name in characters],
                "my_characters": [character_view(characters[name]) for name in owned_names if name in characters and not characters[name].get("deceduto") and characters[name]["pf_attuali"] > 0],
                "cemetery": cemetery,
                "classes": [
                    {"key": k, "nome": v["classe"], "livello_max": v["max_liv"]}
                    for k, v in game.CLASSI_BASE.items() if k not in CLASSI_RAZZA_BECMI
                ],
                "races": RAZZE_PERSONAGGIO,
                "modules": game.elenca_moduli_pdf(),
                "key_set": bool(key),
                "db": "PostgreSQL remoto" if DATABASE_IS_REMOTE else game.DB_FILE,
            })
            return
        json_response(self, 404, {"error": "Endpoint non trovato"})

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            data = body_json(self)

            if path == "/api/login":
                user = AUTH_STORE.authenticate(data.get("username"), data.get("password"))
                if not user:
                    json_response(self, 401, {"error": "Nome utente o password non validi."})
                    return
                token = AUTH_STORE.create_session(user["id"])
                json_response(self, 200, {"ok": True, "user": user}, {"Set-Cookie": self.session_cookie(token)})
                return

            if path == "/api/logout":
                AUTH_STORE.delete_session(self.session_token())
                json_response(self, 200, {"ok": True}, {"Set-Cookie": self.session_cookie()})
                return

            if path.startswith("/api/admin/"):
                if not self.require_admin():
                    return
                if path == "/api/admin/users":
                    operation = str(data.get("operation", ""))
                    username = str(data.get("username", "")).strip()
                    if operation == "create":
                        AUTH_STORE.add_user(username, data.get("password"))
                    elif operation == "update":
                        AUTH_STORE.update_password(username, data.get("password"))
                    elif operation == "delete":
                        AUTH_STORE.delete_user(username)
                    else:
                        json_response(self, 400, {"error": "Operazione utenti non valida."})
                        return
                    json_response(self, 200, {"ok": True, "users": AUTH_STORE.list_users()})
                    return
                if path == "/api/admin/cleanup-adventures":
                    adventure_ids = list(safe_adventures())
                    for adventure_id in adventure_ids:
                        with adventure_lock_for(adventure_id):
                            with LOCK:
                                DB.elimina_avventura(adventure_id)
                                AUTH_STORE.remove_adventure(adventure_id)
                    json_response(self, 200, {"ok": True, "deleted": len(adventure_ids)})
                    return
                if path == "/api/admin/api-key":
                    api_key = str(data.get("api_key", "")).strip()
                    if len(api_key) > 2048:
                        json_response(self, 400, {"error": "La chiave API supera la lunghezza consentita."})
                        return
                    if api_key:
                        if not game.salva_api_key(api_key):
                            json_response(self, 500, {"error": "Impossibile salvare la chiave API sul server."})
                            return
                        game.API_KEY_ATTIVA = api_key
                    else:
                        if os.path.exists(game.KEY_FILE) and not game.elimina_api_key_salvata():
                            json_response(self, 500, {"error": "Impossibile rimuovere la chiave API salvata."})
                            return
                        game.API_KEY_ATTIVA = os.environ.get("GEMINI_API_KEY", "").strip()
                    json_response(self, 200, {"ok": True, "api_key": api_key_status()})
                    return
                json_response(self, 404, {"error": "Endpoint amministrazione non trovato."})
                return

            user = self.require_auth()
            if user is None:
                return

            if path == "/api/diary":
                adventure_id = str(data.get("adventure_id", "")).strip()
                operation = str(data.get("operation", ""))
                if not adventure_id:
                    json_response(self, 400, {"error": "Avventura non valida."})
                    return
                if not AUTH_STORE.is_member(user["id"], adventure_id):
                    json_response(self, 403, {"error": "Unisciti all'avventura per gestire il diario."})
                    return
                with adventure_lock_for(adventure_id):
                    with LOCK:
                        if operation == "add":
                            note = str(data.get("text", "")).strip()
                            if not note:
                                json_response(self, 400, {"error": "Scrivi il testo dell'annotazione."})
                                return
                            if len(note) > 2000:
                                json_response(self, 400, {"error": "L'annotazione non può superare 2000 caratteri."})
                                return
                            DB.aggiungi_nota(avventura_id=adventure_id, testo_nota=note)
                        elif operation == "delete":
                            raw_note_id = data.get("note_id")
                            if raw_note_id is None:
                                json_response(self, 400, {"error": "Annotazione non valida."})
                                return
                            try:
                                note_id = int(raw_note_id)
                            except (TypeError, ValueError):
                                json_response(self, 400, {"error": "Annotazione non valida."})
                                return
                            if note_id <= 0:
                                json_response(self, 400, {"error": "Annotazione non valida."})
                                return
                            if not DB.elimina_nota(adventure_id, note_id):
                                json_response(self, 404, {"error": "Annotazione non trovata."})
                                return
                        elif operation != "list":
                            json_response(self, 400, {"error": "Operazione diario non valida."})
                            return
                        notes = DB.carica_note_diario(adventure_id)
                json_response(self, 200, {"ok": True, "notes": notes})
                return

            if path == "/api/character/delete":
                requested_name = str(data.get("character", "")).strip()
                if not requested_name or not AUTH_STORE.owns_character(user["id"], requested_name):
                    json_response(self, 403, {"error": "Puoi eliminare solo un tuo personaggio."})
                    return
                with LOCK:
                    characters = safe_characters()
                    character_name = next((name for name in characters if name.casefold() == requested_name.casefold()), None)
                    adventures = safe_adventures()
                    affected_ids = [
                        adventure_id for adventure_id, adventure in adventures.items()
                        if any(name.casefold() == requested_name.casefold() for name in (adventure.get("party") or [adventure.get("eroe", "")]))
                    ]
                if not character_name:
                    json_response(self, 404, {"error": "Personaggio non trovato."})
                    return
                with ExitStack() as locks:
                    for adventure_id in sorted(affected_ids):
                        locks.enter_context(adventure_lock_for(adventure_id))
                    with LOCK:
                        adventures = safe_adventures()
                        current_ids = [
                            adventure_id for adventure_id, adventure in adventures.items()
                            if any(name.casefold() == character_name.casefold() for name in (adventure.get("party") or [adventure.get("eroe", "")]))
                        ]
                        if any(adventure_id not in affected_ids for adventure_id in current_ids):
                            json_response(self, 409, {"error": "Il personaggio è stato assegnato a una nuova avventura. Riprova."})
                            return
                        updated_parties = {}
                        for adventure_id in current_ids:
                            adventure = adventures[adventure_id]
                            party_names = adventure.get("party") or [adventure.get("eroe", "")]
                            remaining = [name for name in party_names if name.casefold() != character_name.casefold()]
                            if not remaining:
                                json_response(self, 409, {"error": "Non puoi eliminare l'ultimo personaggio di un'avventura. Elimina prima l'avventura."})
                                return
                            updated_parties[adventure_id] = remaining
                        owned_names = {name.casefold() for name in AUTH_STORE.character_names(user["id"])}
                        owned_names.discard(character_name.casefold())
                        for adventure_id, party_names in updated_parties.items():
                            adventure = adventures[adventure_id]
                            adventure["party"] = party_names
                            adventure["eroe"] = party_names[0]
                            DB.salva_metadati_avventura(adventure)
                            if AUTH_STORE.is_member(user["id"], adventure_id):
                                replacement = next((
                                    name for name in party_names
                                    if name.casefold() in owned_names
                                    and name in characters
                                    and not characters[name].get("deceduto")
                                    and characters[name]["pf_attuali"] > 0
                                ), None)
                                if replacement:
                                    AUTH_STORE.set_member_character(user["id"], adventure_id, replacement)
                                else:
                                    AUTH_STORE.remove_member(user["id"], adventure_id)
                        DB.elimina_personaggio(character_name)
                        AUTH_STORE.release_character(user["id"], character_name)
                json_response(self, 200, {"ok": True, "character": character_name})
                return

            if path == "/api/character":
                name = str(data.get("nome", "")).strip()
                class_key = str(data.get("classe", "1"))
                race = str(data.get("razza", "Umano"))
                alignment = str(data.get("allineamento", "Legale"))
                level = int(data.get("livello", 1))
                if class_key not in game.CLASSI_BASE or class_key in CLASSI_RAZZA_BECMI:
                    json_response(self, 400, {"error": "Seleziona una classe valida."})
                    return
                if race not in RAZZE_PERSONAGGIO:
                    json_response(self, 400, {"error": "Seleziona una razza valida."})
                    return
                base = game.CLASSI_BASE[class_key]
                if not name:
                    name = f"{base['classe']} {len(safe_characters()) + 1}"
                if len(name) > 60:
                    json_response(self, 400, {"error": "Il nome del personaggio non può superare 60 caratteri."})
                    return
                level = max(1, min(level, base["max_liv"]))
                pf_max = max(1, base["dado_vita"] + game.mod_caratteristica(base["costituzione"]))
                hero = {
                    "nome": name,
                    "classe": base["classe"],
                    "razza": race,
                    "livello": level,
                    "allineamento": alignment,
                    "immortale": False,
                    "deceduto": False,
                    "forza": base["forza"],
                    "intelligenza": base["intelligenza"],
                    "saggezza": base["saggezza"],
                    "destrezza": base["destrezza"],
                    "costituzione": base["costituzione"],
                    "carisma": base["carisma"],
                    "pf_attuali": pf_max,
                    "pf_max": pf_max,
                    "ca": base["ca_base"] - game.mod_caratteristica(base["destrezza"]),
                    "equip": list(base["equip"]),
                    "mo": base["mo"],
                    "pe": base["xp"][level - 1],
                }
                game.sincronizza_statistiche_becmi(hero)
                with LOCK:
                    if name in safe_characters():
                        json_response(self, 409, {"error": "Esiste già un personaggio con questo nome."})
                        return
                    DB.salva_personaggio(hero)
                    AUTH_STORE.claim_character(user["id"], name)
                json_response(self, 200, {"ok": True, "character": character_view(hero)})
                return

            if path == "/api/join":
                adventure_id = str(data.get("adventure_id", ""))
                character_name = str(data.get("character", "")).strip()
                with adventure_lock_for(adventure_id):
                    with LOCK:
                        adventure = safe_adventures().get(adventure_id)
                        characters = safe_characters()
                    if not adventure:
                        json_response(self, 404, {"error": "Avventura non trovata."})
                        return
                    if AUTH_STORE.is_member(user["id"], adventure_id):
                        json_response(self, 409, {"error": "Sei già parte di questa avventura."})
                        return
                    if not AUTH_STORE.owns_character(user["id"], character_name):
                        json_response(self, 403, {"error": "Puoi unirti solo con un tuo personaggio."})
                        return
                    character = next((name for name in characters if name.lower() == character_name.lower()), None)
                    if not character:
                        json_response(self, 404, {"error": "Personaggio non trovato."})
                        return
                    if characters[character].get("deceduto") or characters[character]["pf_attuali"] <= 0:
                        json_response(self, 403, {"error": "Questo personaggio è nel cimitero e non può unirsi a una sessione."})
                        return
                    if any(name.lower() == character.lower() for name in adventure.get("party", [])):
                        json_response(self, 409, {"error": "Questo personaggio è già nel party."})
                        return
                    adventure.setdefault("party", []).append(character)
                    adventure["eroe"] = adventure["party"][0]
                    with LOCK:
                        DB.salva_metadati_avventura(adventure)
                    AUTH_STORE.add_member(user["id"], adventure_id)
                    AUTH_STORE.set_member_character(user["id"], adventure_id, character)
                json_response(self, 200, {"ok": True, "adventure": adventure_view(adventure)})
                return

            if path == "/api/adventure":
                title = str(data.get("titolo", "")).strip()
                party_names = data.get("party") or []
                party_names = [str(name).strip() for name in party_names if str(name).strip()]
                if not party_names:
                    json_response(self, 400, {"error": "Seleziona almeno un personaggio."})
                    return
                with LOCK:
                    characters = safe_characters()
                owned_names = AUTH_STORE.character_names(user["id"])
                if any(name not in characters or name not in owned_names for name in party_names):
                    json_response(self, 403, {"error": "Puoi avviare un'avventura solo con i tuoi personaggi."})
                    return
                if any(characters[name].get("deceduto") or characters[name]["pf_attuali"] <= 0 for name in party_names):
                    json_response(self, 403, {"error": "Un personaggio nel cimitero non può partecipare a una nuova avventura."})
                    return

                key = api_key_active()
                if not key:
                    json_response(self, 400, {"error": "Chiave Gemini non configurata."})
                    return

                module_name = str(data.get("modulo", "")).strip()
                module_pdf = ""
                module_text = ""
                if module_name:
                    module_path = os.path.join(game.MODULI_DIR, os.path.basename(module_name))
                    if os.path.isfile(module_path):
                        module_pdf = os.path.basename(module_path)
                        module_text, b64 = game.prepara_contenuto_modulo(module_path)
                        if not module_text and b64:
                            module_pdf = os.path.abspath(module_path)

                if title:
                    adventure_title = title
                elif module_name:
                    adventure_title = os.path.splitext(os.path.basename(module_name))[0].replace("_", " ").replace("-", " ")
                else:
                    adventure_title = game.SCENARI_AVVENTURA["1"][0]

                scenario_prompt = game.SCENARI_AVVENTURA["1"][1]
                adventure_id = "adv_" + uuid.uuid4().hex[:12]
                adventure = {
                    "id": adventure_id,
                    "titolo": adventure_title,
                    "eroe": party_names[0],
                    "party": party_names,
                    "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "storia": [],
                    "note": "",
                    "modulo_pdf": module_pdf,
                    "modulo_testo": module_text,
                    "stato_dungeon": {
                        "modalita_gioco": data.get("modalita", "interattiva"),
                        "torcia_turni": 6,
                        "torcia_attiva": True,
                        "frequenza_incontri": "raro",
                    },
                }
                prompt = f"Gruppo di avventurieri: {', '.join(party_names)}. {scenario_prompt}"
                mode = adventure["stato_dungeon"]["modalita_gioco"]
                if mode == "classica":
                    prompt += "\n" + "\n".join(game.genera_batteria_dadi(name)["testo"] for name in party_names)
                adventure["storia"] = [{"role": "user", "parts": [{"text": prompt}]}]
                with LOCK:
                    party = get_party(adventure, characters)
                pdf_path = module_pdf if module_pdf and not module_text and os.path.isfile(module_pdf) else None
                response = game.chiama_gemini(
                    adventure["storia"], key,
                    game.costruisci_system_prompt(party, adventure),
                    pdf_path=pdf_path,
                    desc_attesa="sta generando la scena iniziale",
                )
                adventure["storia"].append({"role": "model", "parts": [{"text": response}]})
                with LOCK:
                    DB.salva_metadati_avventura(adventure)
                    DB.aggiungi_messaggio(adventure_id, "user", prompt)
                    DB.aggiungi_messaggio(adventure_id, "model", response)
                    AUTH_STORE.add_member(user["id"], adventure_id)
                    AUTH_STORE.set_member_character(user["id"], adventure_id, party_names[0])
                    AUTH_STORE.add_adventure_owner(user["id"], adventure_id)
                json_response(self, 200, {"ok": True, "adventure": adventure_view(adventure)})
                return

            if path == "/api/action":
                adventure_id = str(data.get("adventure_id", ""))
                action = str(data.get("action", "")).strip()
                if not action:
                    json_response(self, 400, {"error": "Inserisci un'azione."})
                    return
                if len(action) > 4000:
                    json_response(self, 400, {"error": "L'azione non può superare 4000 caratteri."})
                    return
                status, result = perform_action(adventure_id, action, user)
                json_response(self, status, result)
                return

            if path == "/api/delete":
                adventure_id = str(data.get("adventure_id", ""))
                with adventure_lock_for(adventure_id):
                    if not AUTH_STORE.is_adventure_owner(user["id"], adventure_id):
                        json_response(self, 403, {"error": "Solo chi ha creato l'avventura può eliminarla."})
                        return
                    with LOCK:
                        DB.elimina_avventura(adventure_id)
                        AUTH_STORE.remove_adventure(adventure_id)
                json_response(self, 200, {"ok": True})
                return

            json_response(self, 404, {"error": "Endpoint non trovato"})
        except (ValueError, TypeError) as exc:
            json_response(self, 400, {"error": str(exc)})
        except Exception as exc:
            json_response(self, 500, {"error": str(exc)})

    def log_message(self, format, *args):
        _ = format, args


PAGE = r"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#9c1c20">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="D&amp;D Scatola Rossa">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="icon" type="image/png" sizes="32x32" href="/imgs/favicon-32.png">
  <link rel="icon" type="image/svg+xml" href="/imgs/app-icon.svg">
  <link rel="apple-touch-icon" sizes="180x180" href="/imgs/apple-touch-icon.png">
  <link rel="manifest" href="/app.webmanifest">
  <title>D&D - Scatola Rossa</title>
  <style>
    :root {
      color-scheme:light;
      --red:#9c1c20; --gold:#d5ad55; --ink:#191512; --paper:#efe6cf; --panel:#fffaf0; --green:#4a6944;
      --app-bg:#17130f; --header-start:#321313; --header-text:#fff; --status:#f4dda0;
      --line:#baaa88; --panel-border:#b7a778; --panel-heading-border:#d5cba8;
      --button-bg:#a83336; --button-border:#7c2626; --button-text:#fff;
      --secondary-bg:#eee3c5; --secondary-text:#351818; --input-bg:#fffdf7;
      --active-bg:#eadba9; --chat-bg:#faf6e9; --user-message-bg:#f0ead8; --model-message-bg:#fff;
      --composer-bg:#e9dfc2; --muted:#756d5a; --label:#5d5138; --subtle-border:#bbaa82;
      --card-shadow:0 8px 24px #0002; --focus-ring:#9c1c2055;
    }
    body[data-palette="forest"] {
      --red:#24664f; --gold:#c3a568; --ink:#19251f; --paper:#e5eee7; --panel:#fbfdfb; --green:#397354;
      --app-bg:#101a15; --header-start:#142b22; --status:#e4efcf; --line:#a9bcae; --panel-border:#b7c8ba;
      --panel-heading-border:#d5e0d6; --button-bg:#31785c; --button-border:#225b43; --secondary-bg:#e1eadc;
      --secondary-text:#193b2d; --input-bg:#fbfdfb; --active-bg:#d4e5cf; --chat-bg:#f2f7f1;
      --user-message-bg:#e4eee2; --composer-bg:#e3ebe1; --label:#455b4c; --subtle-border:#b1c6b5;
      --focus-ring:#24664f55;
    }
    body[data-palette="arcane"] {
      --red:#68469b; --gold:#c4a4e0; --ink:#211b2b; --paper:#eee8f5; --panel:#fcfaff; --green:#55755c;
      --app-bg:#181322; --header-start:#2c1e42; --status:#eee0ff; --line:#c2b5d2; --panel-border:#c9bad9;
      --panel-heading-border:#e1d7ec; --button-bg:#7653a7; --button-border:#56377f; --secondary-bg:#e9dff2;
      --secondary-text:#35264a; --input-bg:#fdfbff; --active-bg:#e5d8f2; --chat-bg:#f8f5fb;
      --user-message-bg:#eee8f4; --composer-bg:#e9e1ef; --label:#5b5068; --subtle-border:#cdbde0;
      --focus-ring:#68469b55;
    }
    body[data-palette="midnight"] {
      color-scheme:dark;
      --red:#75b5d5; --gold:#d0ad72; --ink:#e7edf3; --paper:#202a35; --panel:#283542; --green:#8ebd91;
      --app-bg:#111820; --header-start:#151e29; --status:#e4cf9f; --line:#455563; --panel-border:#485b6c;
      --panel-heading-border:#40505f; --button-bg:#386b88; --button-border:#294f66; --button-text:#fff;
      --secondary-bg:#33414d; --secondary-text:#e7edf3; --input-bg:#18222c; --active-bg:#344957;
      --chat-bg:#18222c; --user-message-bg:#273541; --model-message-bg:#222e39; --composer-bg:#202c37;
      --muted:#b0bdc9; --label:#c0ccd6; --subtle-border:#455563; --focus-ring:#75b5d555;
    }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--app-bg); color:var(--ink); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; transition:background-color .2s ease,color .2s ease; }
    #gameView { display:flex; flex-direction:column; width:100%; height:100vh; height:100dvh; min-height:0; overflow:hidden; }
    #gameView[hidden], #loginView[hidden], #adminView[hidden], #cemeteryView[hidden] { display:none; }
    .login-view { min-height:100vh; display:grid; place-items:center; padding:20px; background:radial-gradient(ellipse at top,var(--red),var(--app-bg) 70%); }
    .login-card { width:min(440px,100%); padding:32px; background:var(--paper); border:1px solid var(--gold); border-radius:18px; box-shadow:0 24px 64px #0005; }
    .login-card h1 { margin:0 0 8px; color:var(--red); text-align:center; letter-spacing:-.04em; }
    .login-card p { color:var(--label); line-height:1.55; }
    .login-card .login-actions { display:flex; gap:8px; margin-top:16px; }
    .login-card .login-actions button { flex:1; }
    #loginMessage { min-height:20px; color:var(--red); }
    header { min-height:64px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:8px 20px;
      background:linear-gradient(110deg,var(--header-start),var(--red)); color:var(--header-text); border-bottom:1px solid var(--gold); box-shadow:0 4px 16px #0002; }
    header h1 { margin:0; font-size:20px; letter-spacing:-.03em; }
    header .status { font-size:13px; color:var(--status); }
    .header-actions { display:flex; align-items:center; gap:12px; }
    .palette-control { display:flex; align-items:center; gap:8px; }
    .palette-control label { margin:0; color:var(--status); font-size:12px; white-space:nowrap; }
    .palette-control select { width:auto; min-width:138px; padding:7px 28px 7px 10px; border:1px solid #ffffff55; border-radius:9px; background:var(--paper); color:var(--ink); font-size:13px; }
    .login-palette-control { justify-content:center; margin-top:22px; }
    .login-palette-control label { color:var(--label); font-size:13px; }
    .login-palette-control select { border-color:var(--panel-border); }
    #busyIndicator[hidden] { display:none; }
    .busy-indicator { display:inline-flex; align-items:center; font-size:21px; line-height:1; }
    .busy-indicator[aria-hidden="false"] { animation: hourglass-turn 1.2s ease-in-out infinite; }
    @keyframes hourglass-turn { 50% { transform:rotate(180deg); } }
    #databaseSavingIndicator[hidden] { display:none; }
    .database-saving-indicator { position:fixed; z-index:40; left:18px; bottom:18px; display:grid; place-items:center; width:44px; height:44px; padding:8px; color:var(--red); background:var(--paper); border:2px solid var(--gold); border-radius:14px; box-shadow:var(--card-shadow); }
    .database-saving-indicator[aria-hidden="false"] { animation: database-saving-pulse 1s ease-in-out infinite alternate; }
    .database-saving-indicator svg { width:24px; height:24px; }
    @keyframes database-saving-pulse { to { transform:scale(1.12); } }
    @media (prefers-reduced-motion: reduce) { .busy-indicator[aria-hidden="false"], .database-saving-indicator[aria-hidden="false"] { animation:none; } }
    main { flex:1; min-height:0; height:auto; display:grid; grid-template-columns:292px minmax(0, 1fr); }
    aside, section { min-height:0; }
    aside { background:var(--paper); border-right:1px solid var(--line); overflow:auto; padding:16px; }
    #sidebarToggle { display:none; }
    #sidebarBackdrop { display:none; }
    .panel { background:var(--panel); border:1px solid var(--panel-border); border-radius:14px; padding:14px; margin-bottom:14px; box-shadow:var(--card-shadow); }
    .panel h2 { margin:0 0 12px; color:var(--red); font-size:15px; border-bottom:1px solid var(--panel-heading-border); padding-bottom:8px; letter-spacing:.01em; }
    button, select, input, textarea { font:inherit; }
    button { border:1px solid var(--button-border); background:var(--button-bg); color:var(--button-text); border-radius:9px; padding:9px 13px; cursor:pointer; font-weight:600; transition:transform .15s ease,filter .15s ease,box-shadow .15s ease; }
    button:hover:not(:disabled) { filter:brightness(1.06); transform:translateY(-1px); box-shadow:0 4px 12px #0002; }
    button.secondary { background:var(--secondary-bg); color:var(--secondary-text); border-color:var(--panel-border); }
    button.danger { background:#65201f; }
    button:disabled { opacity:.55; cursor:not-allowed; }
    input, select, textarea { width:100%; border:1px solid var(--line); background:var(--input-bg); color:var(--ink); padding:10px 11px; border-radius:9px; }
    input:focus, select:focus, textarea:focus, button:focus-visible { outline:3px solid var(--focus-ring); outline-offset:2px; }
    label { display:block; font-size:12px; margin:8px 0 4px; color:var(--label); font-weight:600; }
    .adv { width:100%; text-align:left; margin:4px 0; background:var(--input-bg); color:var(--ink); border-color:var(--subtle-border); }
    .adv.active { background:var(--active-bg); border-color:var(--red); }
    .adv-wrap { display:flex; gap:6px; margin:5px 0; }
    .adv-wrap .adv { margin:0; flex:1; }
    .adv-delete { width:38px; padding:5px; background:var(--button-bg); }
    .chat { background:var(--chat-bg); display:flex; flex-direction:column; }
    #messages { flex:1; overflow:auto; padding:24px clamp(14px,3vw,36px); scroll-behavior:smooth; }
    .message { max-width:900px; margin:0 auto 14px; white-space:pre-wrap; line-height:1.58; }
    .message.user { border:1px solid var(--subtle-border); border-left:4px solid var(--green); padding:12px 15px; background:var(--user-message-bg); border-radius:4px 13px 13px 13px; }
    .message.model { border:1px solid var(--panel-heading-border); border-left:4px solid var(--red); padding:12px 15px; background:var(--model-message-bg); border-radius:4px 13px 13px 13px; box-shadow:0 3px 12px #0000000a; }
    .message-dice-link { display:inline-grid; vertical-align:middle; place-items:center; width:36px; height:36px; margin-left:8px; padding:4px; background:var(--button-bg); border:1px solid var(--button-border); border-radius:10px; color:var(--button-text); }
    .message-dice-link svg { width:23px; height:23px; }
    .story-pagination { display:flex; align-items:center; justify-content:center; gap:12px; padding:8px 14px 12px; color:var(--muted); font-size:13px; }
    .story-pagination[hidden] { display:none; }
    .story-pagination button { min-width:90px; }
    .composer { border-top:1px solid var(--line); background:var(--composer-bg); padding:14px 18px; }
    .composer-row { display:flex; gap:10px; }
    .composer-row textarea { flex:1; min-width:0; }
    .composer textarea { resize:vertical; min-height:50px; max-height:180px; }
    .composer button { min-width:92px; }
    #commandsBtn { min-width:84px; }
    #output { min-height:30px; padding:8px 12px 0; color:var(--red); font-size:13px; }
    .hero { border-bottom:1px dashed var(--line); padding:9px 0; }
    .hero strong { color:var(--red); }
    .party-hero-head { display:flex; align-items:center; justify-content:space-between; gap:6px; }
    .inventory-button { position:relative; z-index:32; display:grid; place-items:center; width:32px; height:30px; padding:3px; background:var(--red); border-color:#6f1115; }
    .inventory-button svg { display:block; width:21px; height:21px; }
    .party-title { color:var(--red); font-weight:bold; margin-bottom:6px; }
    .command-help-list { list-style:none; margin:0; padding:0; }
    .command-help-list li { display:block; padding:8px 0; border-bottom:1px dashed #d5cba8; font-size:12px; }
    .command-shortcut { display:block; margin-bottom:4px; padding:5px 8px; font-family:monospace; font-size:12px; }
    #inventoryBackdrop { position:fixed; z-index:29; inset:0; background:#0008; opacity:0; pointer-events:none; transition:opacity .22s ease; }
    #inventoryPanel { position:fixed; z-index:30; left:50%; bottom:0; width:min(720px,calc(100vw - 24px)); max-height:min(65vh,600px); overflow:auto; padding:18px; background:var(--paper); border:1px solid var(--panel-border); border-bottom:0; border-radius:18px 18px 0 0; box-shadow:0 -8px 28px #0005; transform:translate(-50%,calc(100% + 24px)); transition:transform .24s ease; }
    body.inventory-open #inventoryBackdrop { opacity:1; pointer-events:auto; }
    body.inventory-open #inventoryPanel { transform:translate(-50%,0); }
    .inventory-panel-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }
    .inventory-panel-heading h2 { margin:0; color:var(--red); font-size:18px; }
    #inventoryClose { width:36px; padding:4px; font-size:20px; line-height:1; }
    #inventoryContent { white-space:pre-wrap; line-height:1.55; }
    .muted { color:var(--muted); font-size:12px; }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
    #adminView main.admin-main { height:auto; min-height:calc(100vh - 64px); display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); align-content:start; gap:16px; padding:20px; }
    #cemeteryView main.cemetery-main { flex:none; height:calc(100vh - 64px); height:calc(100dvh - 64px); display:block; overflow:auto; padding:clamp(16px,4vw,36px); }
    .cemetery-heading { max-width:1100px; margin:0 auto 18px; }
    .cemetery-heading h2 { margin:0 0 6px; color:var(--red); }
    .cemetery-grid { max-width:1100px; margin:0 auto; display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:14px; }
    .cemetery-card { background:var(--panel); border:1px solid var(--panel-border); border-left:4px solid var(--muted); border-radius:14px; padding:16px; box-shadow:var(--card-shadow); }
    .cemetery-card h3 { margin:0 0 8px; color:var(--red); }
    .cemetery-empty { max-width:1100px; margin:auto; padding:24px; text-align:center; color:var(--muted); background:var(--panel); border:1px dashed var(--panel-border); border-radius:14px; }
    .admin-user-row { display:flex; align-items:center; gap:8px; border-bottom:1px dashed var(--panel-heading-border); padding:8px 0; }
    .admin-user-row strong { min-width:120px; }
    .admin-user-row input { min-width:100px; }
    .admin-key-status { margin-top:10px; color:var(--label); }
    dialog { color:var(--ink); background:var(--paper); border:1px solid var(--panel-border); border-radius:16px; box-shadow:0 24px 64px #0005; }
    dialog::backdrop { background:#11182099; backdrop-filter:blur(3px); }
    dialog h2 { color:var(--red); }
    .diary-dialog { width:min(620px,calc(100vw - 24px)); max-height:min(85vh,760px); max-height:min(85dvh,760px); padding:20px; overflow:auto; }
    .diary-dialog h2 { margin:0; }
    .diary-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }
    .diary-note-list { list-style:none; margin:12px 0 0; padding:0; }
    .diary-note { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; padding:12px 0; border-top:1px solid var(--panel-heading-border); }
    .diary-note-content { flex:1; min-width:0; overflow-wrap:anywhere; white-space:pre-wrap; }
    .diary-note-time { display:block; margin-bottom:5px; color:var(--muted); font-size:12px; }
    .diary-note-delete { flex:0 0 auto; }
    .chat { min-width:0; }
    @media (max-width:900px) {
      main { grid-template-columns:240px minmax(0, 1fr); }
      .header-actions { gap:8px; }
    }
    @media (max-width:700px) {
      header { justify-content:space-between; gap:8px; padding:8px 12px; }
      header h1 { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:16px; }
      header .status, .palette-control label { display:none; }
      .header-actions { flex:0 0 auto; gap:6px; }
      .header-actions button { min-width:0; padding:7px 9px; }
      .palette-control select { min-width:0; max-width:84px; padding:7px 20px 7px 7px; font-size:12px; }
      #sidebarToggle { display:inline-flex; align-items:center; justify-content:center; min-width:40px; }
      main { display:flex; flex-direction:column; height:auto; }
      #adminView main.admin-main { display:block; height:auto; }
      #cemeteryView main.cemetery-main { height:calc(100vh - 64px); height:calc(100dvh - 64px); }
      #sidebar {
        position:fixed; z-index:20; top:64px; bottom:0; left:0;
        width:min(86vw, 320px); border-right:1px solid var(--line);
        box-shadow:8px 0 24px #0005; transform:translateX(-105%);
        transition:transform .22s ease;
      }
      body.sidebar-open #sidebar { transform:translateX(0); }
      #sidebarBackdrop {
        position:fixed; z-index:19; inset:64px 0 0;
        background:#0008;
      }
      body.sidebar-open #sidebarBackdrop { display:block; }
      .chat { flex:1; height:auto; min-height:0; }
      #messages { padding:14px 12px; }
      .composer { padding:10px; }
      .composer-row { gap:6px; }
      .composer button { min-width:72px; padding:8px; }
      #commandsBtn { min-width:68px; }
      #inventoryPanel { max-height:min(70dvh,600px); padding:16px 14px max(16px,env(safe-area-inset-bottom)); }
    }
  </style>
</head>
<body>
<section id="loginView" class="login-view">
  <form id="loginForm" class="login-card">
    <h1>D&amp;D - Scatola Rossa</h1>
    <p>Accedi con le credenziali fornite dall'amministratore per continuare l'avventura o unirti a una sessione.</p>
    <label for="loginUsername">Nome utente</label>
    <input id="loginUsername" name="username" autocomplete="username" minlength="3" maxlength="32" required>
    <label for="loginPassword">Password</label>
    <input id="loginPassword" name="password" type="password" autocomplete="current-password" required>
    <p id="loginMessage" role="alert"></p>
    <div class="login-actions"><button id="loginSubmit" type="submit">Accedi</button></div>
    <div class="palette-control login-palette-control"><label for="loginPalette">Aspetto</label><select class="palette-select" id="loginPalette" aria-label="Scegli la palette colori"><option value="red">Scatola Rossa</option><option value="forest">Foresta</option><option value="arcane">Arcano</option><option value="midnight">Notte</option></select></div>
  </form>
</section>
<div id="gameView" hidden>
<header>
  <button id="sidebarToggle" type="button" aria-label="Apri il menu" aria-expanded="false">☰</button>
  <h1>D&amp;D - Scatola Rossa</h1>
  <div class="header-actions"><span id="busyIndicator" class="busy-indicator" role="status" aria-label="Elaborazione in corso" aria-hidden="true" title="Elaborazione in corso" hidden>⌛</span><div class="status" id="status">Caricamento...</div><span id="currentUser" class="status"></span><div class="palette-control"><label for="gamePalette">Palette</label><select class="palette-select" id="gamePalette" aria-label="Scegli la palette colori"><option value="red">Scatola Rossa</option><option value="forest">Foresta</option><option value="arcane">Arcano</option><option value="midnight">Notte</option></select></div><button id="adminBtn" class="secondary" type="button" hidden>Amministrazione</button><button id="logoutBtn" class="secondary" type="button">Esci</button></div>
</header>
<div id="sidebarBackdrop"></div>
<div id="inventoryBackdrop"></div>
<main>
  <aside id="sidebar">
    <div class="panel">
      <h2>Partita</h2>
      <div id="partyAdventureTitle" class="party-title">Nessuna avventura selezionata</div>
      <button id="diaryBtn" class="secondary" type="button" style="width:100%;margin:0 0 8px" disabled>Gestisci diario</button>
      <div id="party"></div>
    </div>
    <div class="panel">
      <h2>Avventure</h2>
      <div id="adventureList"></div>
      <button class="secondary" style="width:100%;margin-top:8px" id="newBtn">Nuova avventura</button>
    </div>
    <div class="panel">
      <h2>Personaggi</h2>
      <div id="characterList"></div>
      <button class="secondary" style="width:100%;margin-top:8px" id="newCharBtn">Nuovo personaggio</button>
    </div>
    <button id="cemeteryBtn" class="secondary" type="button" style="width:100%">Cimitero degli Eroi</button>
  </aside>
  <section class="chat">
    <div id="messages"></div>
    <nav id="storyPagination" class="story-pagination" aria-label="Pagine della cronaca" hidden>
      <button id="storyPrevious" class="secondary" type="button" aria-label="Pagina precedente">‹ Precedente</button>
      <span id="storyPageStatus" aria-live="polite"></span>
      <button id="storyNext" class="secondary" type="button" aria-label="Pagina successiva">Successiva ›</button>
    </nav>
    <div id="output"></div>
    <div class="composer">
      <div class="composer-row">
        <textarea id="action" placeholder="Descrivi l'azione oppure usa un comando, ad esempio /inventario"></textarea>
        <button id="commandsBtn" class="secondary" type="button" aria-label="Mostra i comandi disponibili">Comandi</button>
        <button id="sendBtn">Invia</button>
      </div>
    </div>
  </section>
</main>

<section id="inventoryPanel" role="dialog" aria-modal="true" aria-labelledby="inventoryTitle" aria-hidden="true">
  <div class="inventory-panel-heading">
    <h2 id="inventoryTitle">Risultato</h2>
    <button id="inventoryClose" type="button" aria-label="Chiudi pannello">×</button>
  </div>
  <div id="inventoryContent"></div>
</section>

<dialog id="characterDialog">
  <form method="dialog" style="min-width:min(420px,90vw)">
    <h2>Nuovo personaggio</h2>
    <label>Nome</label><input id="charName" required>
    <label>Classe</label><select id="charClass"></select>
    <label>Razza</label><select id="charRace"></select>
    <label>Allineamento</label><select id="charAlignment"><option>Legale</option><option>Neutrale</option><option>Caotico</option></select>
    <label>Livello</label><input id="charLevel" type="number" min="1" value="1">
    <div style="display:flex;gap:8px;margin-top:14px">
      <button value="cancel" class="secondary">Annulla</button>
      <button value="ok" id="createChar">Crea</button>
    </div>
  </form>
</dialog>

<dialog id="adventureDialog">
  <form method="dialog" style="min-width:min(520px,90vw)">
    <h2>Nuova avventura</h2>
    <label>Titolo</label><input id="advTitle" placeholder="Opzionale">
    <label>Personaggi</label><select id="advParty" multiple size="5"></select>
    <label>Modulo PDF</label><select id="advModule"><option value="">Scenario predefinito</option></select>
    <label>Modalita</label><select id="advMode"><option value="interattiva">Interattiva - dadi reali</option><option value="classica">Classica - autodadi</option></select>
    <div style="display:flex;gap:8px;margin-top:14px">
      <button value="cancel" class="secondary">Annulla</button>
      <button value="ok" id="createAdv">Inizia</button>
    </div>
  </form>
</dialog>

<dialog id="joinDialog">
  <form method="dialog" style="min-width:min(420px,90vw)">
    <h2>Unisciti alla sessione</h2>
    <p id="joinAdventureTitle"></p>
    <label for="joinCharacter">Personaggio da portare</label>
    <select id="joinCharacter" required></select>
    <div style="display:flex;gap:8px;margin-top:14px">
      <button value="cancel" class="secondary">Annulla</button>
      <button value="ok" id="joinSubmit">Unisciti</button>
    </div>
  </form>
</dialog>
</div>

<dialog id="diaryDialog" class="diary-dialog" aria-labelledby="diaryTitle">
  <div class="diary-heading">
    <h2 id="diaryTitle">Diario dell'avventura</h2>
    <button id="diaryClose" class="secondary" type="button" aria-label="Chiudi diario">×</button>
  </div>
  <p id="diaryAdventureTitle" class="muted"></p>
  <label for="diaryNoteInput">Nuova annotazione</label>
  <textarea id="diaryNoteInput" rows="3" maxlength="2000" placeholder="Scrivi un appunto per il gruppo..."></textarea>
  <button id="diarySave" type="button" style="margin-top:8px">Salva annotazione</button>
  <p id="diaryMessage" class="admin-key-status" role="status" aria-live="polite"></p>
  <ul id="diaryNotes" class="diary-note-list"></ul>
</dialog>

<section id="adminView" hidden>
  <header>
    <h1>Amministrazione</h1>
    <div style="display:flex;align-items:center;gap:12px"><span id="adminCurrentUser" class="status"></span><button id="adminBack" class="secondary" type="button">Torna al gioco</button><button id="adminLogoutBtn" class="secondary" type="button">Esci</button></div>
  </header>
  <main class="admin-main">
    <section class="panel">
      <h2>Account giocatori</h2>
      <p class="muted">Gli account sono conservati in modo protetto; le password non sono mai salvate in chiaro.</p>
      <form id="adminUserForm">
        <label for="newUsername">Nome utente</label><input id="newUsername" minlength="3" maxlength="32" required>
        <label for="newUserPassword">Password (almeno 10 caratteri)</label><input id="newUserPassword" type="password" minlength="10" required>
        <button type="submit" style="margin-top:10px">Crea utente</button>
      </form>
      <div id="adminUsers" style="margin-top:14px"></div>
      <p id="adminUserMessage" class="admin-key-status" role="status"></p>
    </section>
    <section class="panel">
      <h2>Manutenzione avventure</h2>
      <p class="muted">Elimina tutte le avventure dal database, comprese quelle iniziali o prive di proprietario.</p>
      <button id="cleanupAdventuresBtn" class="danger" type="button">Pulisci tutte le avventure</button>
      <p id="cleanupAdventuresMessage" class="admin-key-status" role="status"></p>
    </section>
    <section class="panel">
      <h2>Chiave API Gemini</h2>
      <p class="muted">La chiave salvata qui ha priorità su <code>GEMINI_API_KEY</code> e viene scritta nel file locale protetto.</p>
      <label for="adminApiKey">Nuova chiave API</label>
      <input id="adminApiKey" type="password" autocomplete="new-password" placeholder="Incolla la chiave per sostituirla">
      <div style="display:flex;gap:8px;margin-top:12px"><button id="saveApiKey" type="button">Salva chiave</button><button id="clearApiKey" class="secondary" type="button">Rimuovi chiave salvata</button></div>
      <p id="adminApiKeyStatus" class="admin-key-status" role="status"></p>
      <p id="adminApiKeyMessage" class="admin-key-status" role="alert"></p>
    </section>
  </main>
</section>
<section id="cemeteryView" hidden>
  <header>
    <h1>Cimitero degli Eroi</h1>
    <div class="header-actions"><div class="palette-control"><label for="cemeteryPalette">Palette</label><select class="palette-select" id="cemeteryPalette" aria-label="Scegli la palette colori"><option value="red">Scatola Rossa</option><option value="forest">Foresta</option><option value="arcane">Arcano</option><option value="midnight">Notte</option></select></div><button id="cemeteryBack" class="secondary" type="button">Torna all'avventura</button><button id="cemeteryLogoutBtn" class="secondary" type="button">Esci</button></div>
  </header>
  <main class="cemetery-main">
    <div class="cemetery-heading"><h2>Caduti in avventura</h2><p class="muted">I personaggi nel cimitero non possono essere scelti per nuove sessioni.</p></div>
    <div id="cemeteryList" class="cemetery-grid"></div>
  </main>
</section>
<span id="databaseSavingIndicator" class="database-saving-indicator" role="status" aria-label="Caricamento o salvataggio dei dati sul database in corso" aria-live="polite" aria-hidden="true" title="Caricamento o salvataggio dei dati sul database in corso" hidden><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><ellipse cx="12" cy="5" rx="8" ry="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" fill="none" stroke="currentColor" stroke-width="1.8"/></svg></span>

<script>
let state = null;
let activeId = null;
let activeDiaryAdventureId = null;
let processingOperations = 0;
let databaseActivityOperations = 0;
const PALETTE_NAMES = new Set(['red', 'forest', 'arcane', 'midnight']);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch(error => {
      console.warn('Registrazione service worker non riuscita.', error);
    });
  });
}

function applyPalette(palette, persist = true) {
  const selected = PALETTE_NAMES.has(palette) ? palette : 'red';
  document.body.dataset.palette = selected;
  document.querySelectorAll('.palette-select').forEach(select => { select.value = selected; });
  const themeColors = {red:'#9c1c20', forest:'#24664f', arcane:'#68469b', midnight:'#111820'};
  document.querySelector('meta[name="theme-color"]').content = themeColors[selected];
  if (persist) {
    try {
      localStorage.setItem('dnd_web_palette', selected);
    } catch (error) {
      console.warn('Impossibile salvare la palette in questo browser.', error);
      document.getElementById('output').textContent = 'Palette applicata, ma non salvata nel browser.';
    }
  }
}

try {
  applyPalette(localStorage.getItem('dnd_web_palette') || 'red', false);
} catch (error) {
  console.warn('Impossibile leggere la palette salvata nel browser.', error);
  applyPalette('red', false);
}
document.querySelectorAll('.palette-select').forEach(select => {
  select.addEventListener('change', () => applyPalette(select.value));
});

function setProcessing(active) {
  processingOperations = Math.max(0, processingOperations + (active ? 1 : -1));
  const indicator = document.getElementById('busyIndicator');
  indicator.hidden = processingOperations === 0;
  indicator.setAttribute('aria-hidden', String(indicator.hidden));
}

function setDatabaseActivity(active) {
  databaseActivityOperations = Math.max(0, databaseActivityOperations + (active ? 1 : -1));
  const indicator = document.getElementById('databaseSavingIndicator');
  indicator.hidden = databaseActivityOperations === 0;
  indicator.setAttribute('aria-hidden', String(indicator.hidden));
}

const WEB_COMMANDS = [
  {label:'/help', value:'/help', description:'Mostra la guida rapida.'},
  {label:'/aiuto', value:'/aiuto', description:'Alias di /help.'},
  {label:'/help pdf', value:'/help pdf', description:'Genera il manuale comandi PDF.'},
  {label:'/comandi pdf', value:'/comandi pdf', description:'Alias per generare il manuale comandi PDF.'},
  {label:'/inventario [nome|party]', value:'/inventario ', description:'Mostra l’inventario di un personaggio o del party.'},
  {label:'/zaino [nome|party]', value:'/zaino ', description:'Alias di /inventario.'},
  {label:'/magia', value:'/magia', spellCommand:true, description:'Mostra grimorio e slot.'},
  {label:'/incantesimi', value:'/incantesimi', spellCommand:true, description:'Mostra grimorio e slot (comando per Chierici).'},
  {label:'/grimorio', value:'/grimorio', description:'Alias per visualizzare grimorio e slot.'},
  {label:'/torcia [on|off|auto]', value:'/torcia ', description:'Gestisce torce; completa con on, off o auto.'},
  {label:'/ambiente [tipo]', value:'/ambiente ', description:'Imposta taverna, citta, dungeon o auto.'},
  {label:'/incontri [frequenza]', value:'/incontri ', description:'Usa raro, normale, frequente oppure off.'},
  {label:'/modalita [tipo]', value:'/modalita ', description:'Usa interattiva o classica.'},
  {label:'/scheda pdf', value:'/scheda pdf', description:'Esporta la scheda del primo eroe del party.'},
  {label:'/mappa pdf', value:'/mappa pdf', description:'Esporta la mappa tattica PDF.'},
  {label:'/esporta', value:'/esporta', description:'Esporta la cronaca della campagna.'},
  {label:'/esporta mappa', value:'/esporta mappa', description:'Esporta la mappa tattica PDF.'},
  {label:'/esporta scheda', value:'/esporta scheda', description:'Esporta le schede PDF del party.'},
  {label:'/suoni [test|prova]', value:'/suoni ', description:'Attiva/disattiva gli effetti o prova i suoni.'},
  {label:'/audio [test|prova]', value:'/audio ', description:'Alias di /suoni.'}
];

function closeSidebar() {
  document.body.classList.remove('sidebar-open');
  document.getElementById('sidebarToggle').setAttribute('aria-expanded', 'false');
}

let activeInventoryName = null;

function openDrawer(title, content) {
  closeSidebar();
  activeInventoryName = null;
  document.getElementById('inventoryTitle').textContent = title;
  document.getElementById('inventoryContent').replaceChildren(document.createTextNode(content));
  document.body.classList.add('inventory-open');
  document.getElementById('inventoryPanel').setAttribute('aria-hidden', 'false');
}

function openCommandsDrawer() {
  closeSidebar();
  const content = document.getElementById('inventoryContent');
  content.replaceChildren();
  const adventure = state?.adventures.find(item => item.id === activeId);
  const firstCharacterName = adventure?.party?.[0];
  const firstCharacter = state?.characters.find(character => character.nome === firstCharacterName);
  const isCleric = firstCharacter?.classe?.toLowerCase() === 'chierico';
  const spellCommand = isCleric ? '/incantesimi' : '/magia';
  const list = document.createElement('ul');
  list.className = 'command-help-list';
  WEB_COMMANDS.forEach(command => {
    if (command.spellCommand && command.value !== spellCommand) return;
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'command-shortcut';
    button.textContent = command.label;
    button.title = 'Inserisci ' + command.label;
    button.onclick = () => {
      const input = document.getElementById('action');
      input.value = command.value;
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      closeInventory();
    };
    const description = document.createElement('span');
    description.textContent = command.description;
    item.append(button, description);
    list.appendChild(item);
  });
  content.appendChild(list);
  document.getElementById('inventoryTitle').textContent = 'Comandi disponibili';
  document.body.classList.add('inventory-open');
  document.getElementById('inventoryPanel').setAttribute('aria-hidden', 'false');
}

function closeInventory() {
  document.body.classList.remove('inventory-open');
  document.getElementById('inventoryPanel').setAttribute('aria-hidden', 'true');
  activeInventoryName = null;
}

document.getElementById('sidebarToggle').onclick = () => {
  const open = document.body.classList.toggle('sidebar-open');
  document.getElementById('sidebarToggle').setAttribute('aria-expanded', String(open));
};
document.getElementById('sidebarBackdrop').onclick = closeSidebar;
document.getElementById('inventoryBackdrop').onclick = closeInventory;
document.getElementById('inventoryClose').onclick = closeInventory;
document.getElementById('diaryBtn').onclick = openDiary;
document.getElementById('diaryClose').onclick = () => document.getElementById('diaryDialog').close();
document.getElementById('diaryDialog').addEventListener('close', () => { activeDiaryAdventureId = null; });
document.getElementById('diarySave').onclick = saveDiaryNote;
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    closeSidebar();
    closeInventory();
  }
});

document.getElementById('commandsBtn').onclick = openCommandsDrawer;

async function api(url, data, trackDatabaseActivity = Boolean(data)) {
  if (trackDatabaseActivity) setDatabaseActivity(true);
  try {
    const res = await fetch(url, data ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {});
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Errore');
    return json;
  } finally {
    if (trackDatabaseActivity) setDatabaseActivity(false);
  }
}

let refreshing = false;
let renderedAdventureId = null;
let renderedStorySnapshot = '';
let renderedStoryPageCount = 0;
let storyPageIndex = 0;
const STORY_PAGE_LINE_LIMIT = 60;

function showLogin(message = '') {
  document.getElementById('gameView').hidden = true;
  document.getElementById('adminView').hidden = true;
  document.getElementById('cemeteryView').hidden = true;
  document.getElementById('loginView').hidden = false;
  document.getElementById('loginMessage').textContent = message;
  activeId = null;
  state = null;
  renderedAdventureId = null;
  renderedStorySnapshot = '';
  renderedStoryPageCount = 0;
  storyPageIndex = 0;
}

async function showGame(user) {
  document.getElementById('loginView').hidden = true;
  document.getElementById('adminView').hidden = true;
  document.getElementById('cemeteryView').hidden = true;
  document.getElementById('gameView').hidden = false;
  document.getElementById('currentUser').textContent = user.username;
  document.getElementById('adminBtn').hidden = !user.is_admin;
  await refresh();
}

document.getElementById('loginForm').onsubmit = async event => {
  event.preventDefault();
  const message = document.getElementById('loginMessage');
  try {
    const result = await api('/api/login', {
      username:document.getElementById('loginUsername').value,
      password:document.getElementById('loginPassword').value
    });
    document.getElementById('loginPassword').value = '';
    await showGame(result.user);
  } catch(e) { message.textContent = e.message; }
};

document.getElementById('logoutBtn').onclick = async () => {
  try {
    await api('/api/logout', {});
    activeId = null;
    showLogin();
  } catch(e) { document.getElementById('status').textContent = e.message; }
};

document.getElementById('adminBtn').onclick = openAdmin;
document.getElementById('adminLogoutBtn').onclick = () => document.getElementById('logoutBtn').click();
document.getElementById('cemeteryBtn').onclick = () => {
  closeSidebar();
  closeInventory();
  document.getElementById('gameView').hidden = true;
  document.getElementById('cemeteryView').hidden = false;
  renderCemetery();
};
document.getElementById('cemeteryBack').onclick = async () => {
  document.getElementById('cemeteryView').hidden = true;
  document.getElementById('gameView').hidden = false;
  await refresh();
};
document.getElementById('cemeteryLogoutBtn').onclick = () => document.getElementById('logoutBtn').click();
document.getElementById('adminBack').onclick = async () => {
  document.getElementById('adminView').hidden = true;
  document.getElementById('gameView').hidden = false;
  await refresh();
};

async function openAdmin() {
  document.getElementById('gameView').hidden = true;
  document.getElementById('adminView').hidden = false;
  document.getElementById('adminCurrentUser').textContent = document.getElementById('currentUser').textContent;
  await loadAdmin();
}

async function loadAdmin() {
  const list = document.getElementById('adminUsers');
  list.textContent = 'Caricamento account...';
  document.getElementById('adminApiKeyStatus').textContent = 'Caricamento stato chiave API...';
  setDatabaseActivity(true);
  try {
    const result = await api('/api/admin');
    list.replaceChildren();
    let rows = document.createDocumentFragment();
    for (const [index, username] of result.users.entries()) {
      const row = document.createElement('div');
      row.className = 'admin-user-row';
      const name = document.createElement('strong');
      name.textContent = username;
      const password = document.createElement('input');
      password.type = 'password';
      password.minLength = 10;
      password.placeholder = 'Nuova password';
      password.autocomplete = 'new-password';
      const update = document.createElement('button');
      update.type = 'button';
      update.textContent = 'Aggiorna';
      update.onclick = async () => {
        try {
          await api('/api/admin/users', {operation:'update', username, password:password.value});
          password.value = '';
          document.getElementById('adminUserMessage').textContent = `Password aggiornata per ${username}.`;
          await loadAdmin();
        } catch(e) { document.getElementById('adminUserMessage').textContent = e.message; }
      };
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'danger';
      remove.textContent = 'Elimina';
      remove.onclick = async () => {
        if (!confirm(`Eliminare l'account ${username}?`)) return;
        try {
          await api('/api/admin/users', {operation:'delete', username});
          await loadAdmin();
        } catch(e) { document.getElementById('adminUserMessage').textContent = e.message; }
      };
      row.append(name, password, update, remove);
      rows.append(row);
      if ((index + 1) % 40 === 0) {
        list.append(rows);
        rows = document.createDocumentFragment();
        await new Promise(resolve => setTimeout(resolve, 0));
      }
    }
    list.append(rows);
    const key = result.api_key;
    document.getElementById('adminApiKeyStatus').textContent = key.configured
      ? `Configurata (${key.source}): ${key.masked}` : 'Nessuna chiave Gemini configurata.';
  } catch(e) {
    list.replaceChildren();
    document.getElementById('adminApiKeyMessage').textContent = e.message;
  } finally {
    setDatabaseActivity(false);
  }
}

document.getElementById('adminUserForm').onsubmit = async event => {
  event.preventDefault();
  const message = document.getElementById('adminUserMessage');
  try {
    const result = await api('/api/admin/users', {
      operation:'create',
      username:document.getElementById('newUsername').value,
      password:document.getElementById('newUserPassword').value
    });
    document.getElementById('newUsername').value = '';
    document.getElementById('newUserPassword').value = '';
    message.textContent = 'Utente creato.';
    await loadAdmin();
  } catch(e) { message.textContent = e.message; }
};

document.getElementById('saveApiKey').onclick = async () => {
  const message = document.getElementById('adminApiKeyMessage');
  try {
    const result = await api('/api/admin/api-key', {api_key:document.getElementById('adminApiKey').value});
    document.getElementById('adminApiKey').value = '';
    message.textContent = 'Chiave API salvata.';
    const key = result.api_key;
    document.getElementById('adminApiKeyStatus').textContent = `Configurata (${key.source}): ${key.masked}`;
  } catch(e) { message.textContent = e.message; }
};

document.getElementById('cleanupAdventuresBtn').onclick = async () => {
  if (!confirm('Eliminare tutte le avventure, incluse quelle iniziali e senza proprietario? Questa operazione non si può annullare.')) return;
  const button = document.getElementById('cleanupAdventuresBtn');
  const message = document.getElementById('cleanupAdventuresMessage');
  button.disabled = true;
  try {
    const result = await api('/api/admin/cleanup-adventures', {});
    message.textContent = `Eliminate ${result.deleted} avventure.`;
    await refresh();
  } catch(e) { message.textContent = e.message; }
  finally { button.disabled = false; }
};

document.getElementById('clearApiKey').onclick = async () => {
  if (!confirm('Rimuovere la chiave API salvata sul server?')) return;
  const message = document.getElementById('adminApiKeyMessage');
  try {
    const result = await api('/api/admin/api-key', {api_key:''});
    message.textContent = 'Chiave salvata rimossa; se presente verrà usata GEMINI_API_KEY.';
    const key = result.api_key;
    document.getElementById('adminApiKeyStatus').textContent = key.configured
      ? `Configurata (${key.source}): ${key.masked}` : 'Nessuna chiave Gemini configurata.';
  } catch(e) { message.textContent = e.message; }
};

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
}

function renderCemetery() {
  const cemeteryList = document.getElementById('cemeteryList');
  if (!state?.cemetery?.length) {
    cemeteryList.className = 'cemetery-empty';
    cemeteryList.textContent = 'Il cimitero è vuoto.';
    return;
  }
  cemeteryList.className = 'cemetery-grid';
  const owned = new Set((state.owned_characters || []).map(character => character.nome.toLocaleLowerCase()));
  cemeteryList.innerHTML = state.cemetery.map(character =>
    `<article class="cemetery-card"><h3>${escapeHtml(character.nome)}</h3><div>${escapeHtml(character.classe)}${character.razza ? ` | ${escapeHtml(character.razza)}` : ''}</div><div>Livello ${character.livello} | PF ${character.pf_attuali}/${character.pf_max}</div><div>Caduto nell'avventura: ${escapeHtml(character.avventura_morte || 'Avventura non registrata')}</div><div class="muted">Personaggio non più giocabile</div>${owned.has(character.nome.toLocaleLowerCase()) ? `<button class="character-delete danger" type="button" data-character="${escapeHtml(character.nome)}" style="margin-top:10px">Elimina personaggio</button>` : ''}</article>`
  ).join('');
  cemeteryList.querySelectorAll('.character-delete').forEach(button => {
    button.onclick = () => deleteCharacter(button.dataset.character);
  });
}

async function deleteCharacter(name) {
  if (!confirm(`Eliminare definitivamente il personaggio "${name}"?`)) return;
  const cemeteryVisible = !document.getElementById('cemeteryView').hidden;
  try {
    await api('/api/character/delete', {character:name});
    await refresh(true);
    if (!cemeteryVisible) document.getElementById('output').textContent = `Personaggio ${name} eliminato.`;
  } catch(e) { alert(e.message); }
}

function requestsDiceRoll(text) {
  return /\b(?:tira(?:te)?|lancia(?:te)?|effettua(?:te)?|esegui(?:te)?|fai|fate)\b.{0,100}\b(?:dado|dadi|tiro|tiri)\b|\b(?:tira(?:te)?|lancia(?:te)?|effettua(?:te)?|esegui(?:te)?|fai|fate)\b.{0,100}(?:\d*d\d+)\b|\b(?:dado|dadi)\b.{0,60}\b(?:tira|lancia|effettua|esegui|fai|fate)\b/i.test(text);
}

function estimateStoryLines(text, container) {
  const canvas = estimateStoryLines.canvas || (estimateStoryLines.canvas = document.createElement('canvas'));
  const context = canvas.getContext('2d');
  if (!context) return Math.max(1, String(text).split(/\r?\n/).length);
  context.font = getComputedStyle(container).font;
  const messageWidth = Math.max(1, Math.min(900, container.clientWidth - 48) - 38);
  let lines = 0;
  for (const paragraph of String(text).split(/\r?\n/)) {
    if (!paragraph) { lines++; continue; }
    let line = '';
    for (const word of paragraph.split(/\s+/)) {
      const candidate = line ? `${line} ${word}` : word;
      if (line && context.measureText(candidate).width > messageWidth) {
        lines++;
        line = word;
      } else {
        line = candidate;
      }
    }
    lines++;
  }
  return Math.max(1, lines);
}

function wrapStoryText(text, container) {
  const canvas = estimateStoryLines.canvas || (estimateStoryLines.canvas = document.createElement('canvas'));
  const context = canvas.getContext('2d');
  if (!context) return String(text);
  context.font = getComputedStyle(container).font;
  const messageWidth = Math.max(1, Math.min(900, container.clientWidth - 48) - 38);
  const wrappedParagraphs = String(text).split(/\r?\n/).map(paragraph => {
    if (!paragraph) return '';
    const lines = [];
    let line = '';
    for (const word of paragraph.split(/\s+/)) {
      const candidate = line ? `${line} ${word}` : word;
      if (line && context.measureText(candidate).width > messageWidth) {
        lines.push(line);
        line = word;
      } else {
        line = candidate;
      }
      while (context.measureText(line).width > messageWidth) {
        let splitAt = line.length - 1;
        while (splitAt > 1 && context.measureText(line.slice(0, splitAt)).width > messageWidth) splitAt--;
        lines.push(line.slice(0, splitAt));
        line = line.slice(splitAt);
      }
    }
    if (line) lines.push(line);
    return lines.join('\n');
  });
  return wrappedParagraphs.join('\n');
}

function paginateStory(story, container) {
  const pages = [];
  let page = [];
  let pageLines = 0;
  for (const message of story) {
    const messageLines = estimateStoryLines(message.text, container);
    const diceRequested = message.role === 'model' && requestsDiceRoll(message.text);
    const fragments = messageLines > STORY_PAGE_LINE_LIMIT
      ? wrapStoryText(message.text, container).split('\n').reduce((chunks, line) => {
          if (!chunks.length || chunks[chunks.length - 1].length >= STORY_PAGE_LINE_LIMIT) chunks.push([]);
          chunks[chunks.length - 1].push(line);
          return chunks;
        }, []).map((lines, index, chunks) => ({
          ...message,
          text:lines.join('\n'),
          diceRequested,
          isFinalFragment:index === chunks.length - 1,
        }))
      : [{...message, diceRequested, isFinalFragment:true}];
    for (const fragment of fragments) {
      const fragmentLines = estimateStoryLines(fragment.text, container);
      if (page.length && pageLines + fragmentLines > STORY_PAGE_LINE_LIMIT) {
        pages.push(page);
        page = [];
        pageLines = 0;
      }
      page.push(fragment);
      pageLines += fragmentLines;
    }
  }
  if (page.length) pages.push(page);
  return pages.length ? pages : [[]];
}

async function refresh(force = false) {
  if (refreshing || (!force && document.getElementById('gameView').hidden)) return;
  refreshing = true;
  try {
    state = await api('/api/state');
    document.getElementById('status').textContent =
      `${state.my_characters.length} personaggi | ${state.adventures.length} sessioni | ${state.key_set ? 'Gemini configurato' : 'Chiave mancante'}`;

  const list = document.getElementById('adventureList');
  list.innerHTML = '';
  state.adventures.forEach(a => {
    const wrap = document.createElement('div');
    wrap.className = 'adv-wrap';
    const b = document.createElement('button');
    b.className = 'adv' + (a.id === activeId ? ' active' : '');
    b.textContent = a.titolo;
    b.title = a.joined ? `Partecipanti: ${a.members.join(', ') || 'nessuno'}` : 'Sessione attiva: seleziona per unirti';
    b.onclick = () => a.joined ? selectAdventure(a.id) : openJoinDialog(a);
    wrap.appendChild(b);
    if (!a.joined) {
      const join = document.createElement('button');
      join.className = 'adv-delete';
      join.textContent = '+';
      join.title = 'Unisciti alla sessione';
      join.disabled = !state.my_characters.length;
      join.onclick = () => openJoinDialog(a);
      wrap.appendChild(join);
    } else if (a.can_delete) {
      const del = document.createElement('button');
      del.className = 'adv-delete';
      del.textContent = '×';
      del.title = 'Elimina avventura';
      del.onclick = async () => {
        if (!confirm(`Eliminare "${a.titolo}"?`)) return;
        await api('/api/delete',{adventure_id:a.id});
        if (activeId === a.id) activeId = null;
        await refresh();
      };
      wrap.appendChild(del);
    }
    list.appendChild(wrap);
  });
  renderAdventureList();

  const chars = document.getElementById('characterList');
  chars.innerHTML = state.my_characters.length ? state.my_characters.map(c =>
    `<div class="hero"><div class="party-hero-head"><strong>${escapeHtml(c.nome)}</strong><button class="character-delete danger" type="button" data-character="${escapeHtml(c.nome)}" aria-label="Elimina ${escapeHtml(c.nome)}" title="Elimina personaggio">×</button></div><span class="muted">Classe: ${escapeHtml(c.classe)} | Razza: ${escapeHtml(c.razza || 'Umano')} | Liv. ${c.livello} | PF ${c.pf_attuali}/${c.pf_max}</span></div>`
  ).join('') : '<div class="muted">Crea un personaggio per partecipare.</div>';
  chars.querySelectorAll('.character-delete').forEach(button => {
    button.onclick = () => deleteCharacter(button.dataset.character);
  });

  const classSelect = document.getElementById('charClass');
  const selectedClass = classSelect.value;
  classSelect.innerHTML = state.classes.map(c =>
    `<option value="${c.key}">${escapeHtml(c.nome)} (max Liv. ${c.livello_max})</option>`
  ).join('');
  if (state.classes.some(c => c.key === selectedClass)) classSelect.value = selectedClass;
  const raceSelect = document.getElementById('charRace');
  const selectedRace = raceSelect.value;
  raceSelect.innerHTML = state.races.map(race =>
    `<option value="${escapeHtml(race)}">${escapeHtml(race)}</option>`
  ).join('');
  if (state.races.includes(selectedRace)) raceSelect.value = selectedRace;
  const moduleSelect = document.getElementById('advModule');
  const selectedModule = moduleSelect.value;
  moduleSelect.innerHTML = '<option value="">Scenario predefinito</option>' +
    state.modules.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
  if ([...moduleSelect.options].some(option => option.value === selectedModule)) moduleSelect.value = selectedModule;

  const partySelect = document.getElementById('advParty');
  const selectedParty = new Set([...partySelect.selectedOptions].map(option => option.value));
  partySelect.innerHTML = state.my_characters.map(c =>
    `<option value="${escapeHtml(c.nome)}">${escapeHtml(c.nome)} - Classe: ${escapeHtml(c.classe)} | Razza: ${escapeHtml(c.razza || 'Umano')} Liv. ${c.livello}</option>`
  ).join('');
  [...partySelect.options].forEach(option => { option.selected = selectedParty.has(option.value); });

  const joinCharacterSelect = document.getElementById('joinCharacter');
  const selectedJoinCharacter = joinCharacterSelect.value;
  joinCharacterSelect.innerHTML = state.my_characters.map(c =>
    `<option value="${escapeHtml(c.nome)}">${escapeHtml(c.nome)} - Classe: ${escapeHtml(c.classe)} | Razza: ${escapeHtml(c.razza || 'Umano')} Liv. ${c.livello}</option>`
  ).join('');
  if (state.my_characters.some(c => c.nome === selectedJoinCharacter)) joinCharacterSelect.value = selectedJoinCharacter;
  if (!state.adventures.some(a => a.id === activeId && a.joined)) {
    activeId = state.adventures.find(a => a.joined)?.id || null;
  }
  renderActive();
  renderCemetery();
  } finally {
    refreshing = false;
  }
}

function selectAdventure(id) {
  activeId = id;
  renderActive();
  renderAdventureList();
  closeSidebar();
}

let joiningAdventureId = null;
function openJoinDialog(adventure) {
  if (!state.my_characters.length) {
    alert('Crea prima un personaggio per unirti a una sessione.');
    return;
  }
  joiningAdventureId = adventure.id;
  document.getElementById('joinAdventureTitle').textContent = adventure.titolo;
  document.getElementById('joinDialog').showModal();
}

document.getElementById('joinSubmit').onclick = async event => {
  event.preventDefault();
  const button = document.getElementById('joinSubmit');
  button.disabled = true;
  try {
    await api('/api/join', {
      adventure_id:joiningAdventureId,
      character:document.getElementById('joinCharacter').value
    });
    document.getElementById('joinDialog').close();
    selectAdventure(joiningAdventureId);
    await refresh();
  } catch(e) { alert(e.message); }
  finally { button.disabled = false; }
};

function renderAdventureList() {
  document.querySelectorAll('.adv').forEach((b,i) => {
    b.classList.toggle('active', state.adventures[i]?.id === activeId);
  });
}

function renderActive(allowAutoScroll = true) {
  const adv = state?.adventures.find(a => a.id === activeId && a.joined);
  const messages = document.getElementById('messages');
  const party = document.getElementById('party');
  const title = document.getElementById('partyAdventureTitle');
  document.getElementById('diaryBtn').disabled = !adv;
  if (!adv) {
    title.textContent = 'Nessuna avventura selezionata';
    const placeholder = '<div class="message">Seleziona una sessione a cui partecipi o unisciti a una sessione disponibile.</div>';
    if (messages.innerHTML !== placeholder) messages.innerHTML = placeholder;
    renderedAdventureId = null;
    renderedStorySnapshot = '';
    renderedStoryPageCount = 0;
    storyPageIndex = 0;
    document.getElementById('storyPagination').hidden = true;
    party.innerHTML = '';
    return;
  }
  title.textContent = `${adv.titolo} — ${adv.members.join(', ') || 'nessun partecipante'}`;
  const wasAtBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 60;
  const adventureChanged = renderedAdventureId !== adv.id;
  const storySnapshot = JSON.stringify(adv.storia);
  const storyChanged = storySnapshot !== renderedStorySnapshot;
  const wasOnLatestPage = storyPageIndex >= renderedStoryPageCount - 1;
  const pages = paginateStory(adv.storia, messages);
  if (adventureChanged || (storyChanged && wasOnLatestPage)) storyPageIndex = pages.length - 1;
  storyPageIndex = Math.min(storyPageIndex, pages.length - 1);
  renderedStoryPageCount = pages.length;
  const currentPage = pages[storyPageIndex];
  const messageHtml = currentPage.map(m => {
    const isModel = m.role === 'model';
    const showDiceLink = isModel && m.isFinalFragment !== false && (m.diceRequested ?? requestsDiceRoll(m.text));
    const diceLink = showDiceLink
      ? '<a class="message-dice-link" href="https://dice-simulator.com/app/" target="_blank" rel="noopener noreferrer" title="Apri i dadi online in un popup" aria-label="Apri i dadi online in un popup"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m12 2 9 5v10l-9 5-9-5V7l9-5Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="m3.5 7.3 8.5 5 8.5-5M12 12.3V22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><circle cx="8" cy="8" r="1" fill="currentColor"/><circle cx="16" cy="8" r="1" fill="currentColor"/><circle cx="12" cy="17" r="1" fill="currentColor"/></svg></a>'
      : '';
    return `<div class="message ${isModel ? 'model' : 'user'}">${escapeHtml(m.text)}${showDiceLink ? ` ${diceLink}` : ''}</div>`;
  }).join('');
  const pagination = document.getElementById('storyPagination');
  pagination.hidden = pages.length <= 1;
  document.getElementById('storyPageStatus').textContent = pages.length > 1
    ? `Pagina ${storyPageIndex + 1} di ${pages.length}` : '';
  document.getElementById('storyPrevious').disabled = storyPageIndex === 0;
  document.getElementById('storyNext').disabled = storyPageIndex >= pages.length - 1;
  if (adventureChanged || storyChanged || messages.innerHTML !== messageHtml) {
    messages.innerHTML = messageHtml;
    renderedAdventureId = adv.id;
    renderedStorySnapshot = storySnapshot;
    renderedStoryPageCount = pages.length;
    messages.querySelectorAll('.message-dice-link').forEach(link => {
      link.addEventListener('click', event => {
        const popup = window.open(link.href, 'dndDicePopup', 'popup=yes,width=1000,height=760,resizable=yes,scrollbars=yes');
        if (popup) {
          event.preventDefault();
          popup.focus();
        }
      });
    });
    if (allowAutoScroll && (adventureChanged || storyChanged && wasOnLatestPage || wasAtBottom)) {
      requestAnimationFrame(() => { messages.scrollTop = messages.scrollHeight; });
    }
  }
  party.innerHTML = adv.party.map(name => {
    const c = state.characters.find(x => x.nome === name);
    return c ? `<div class="hero"><div class="party-hero-head"><strong>${escapeHtml(c.nome)}</strong><button class="inventory-button" type="button" title="Visualizza inventario" aria-label="Visualizza inventario di ${escapeHtml(c.nome)}" data-character="${escapeHtml(c.nome)}"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M8.5 6V5a3.5 3.5 0 0 1 7 0v1M7 7h10a3 3 0 0 1 3 3v9H4v-9a3 3 0 0 1 3-3Z" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 12h8v4H8zM7 10v8M17 10v8" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>Classe: ${escapeHtml(c.classe)} | Razza: ${escapeHtml(c.razza || 'Umano')}<br>Liv. ${c.livello}<br>PF ${c.pf_attuali}/${c.pf_max} | CA ${c.ca}</div>` : '';
  }).join('');
  party.querySelectorAll('.inventory-button').forEach(button => {
    button.onclick = () => showInventory(button.dataset.character);
  });
}

document.getElementById('storyPrevious').onclick = () => {
  if (storyPageIndex > 0) {
    storyPageIndex--;
    renderActive(false);
    document.getElementById('messages').scrollTop = 0;
  }
};
document.getElementById('storyNext').onclick = () => {
  const adventure = state?.adventures.find(item => item.id === activeId && item.joined);
  if (adventure) {
    const pages = paginateStory(adventure.storia, document.getElementById('messages'));
    if (storyPageIndex < pages.length - 1) {
      storyPageIndex++;
      renderActive(false);
      document.getElementById('messages').scrollTop = 0;
    }
  }
};

async function showInventory(name) {
  if (document.body.classList.contains('inventory-open') && activeInventoryName === name) {
    closeInventory();
    return;
  }
  activeInventoryName = name;
  openDrawer(`Inventario - ${name}`, 'Caricamento inventario...');
  try {
    const result = await api('/api/action', {
      adventure_id:activeId,
      action:`/inventario ${name}`
    });
    if (activeInventoryName === name) document.getElementById('inventoryContent').textContent = result.output || 'Inventario vuoto.';
  } catch(e) {
    if (activeInventoryName === name) document.getElementById('inventoryContent').textContent = e.message;
  }
}

async function openDiary() {
  const adventure = state?.adventures.find(item => item.id === activeId && item.joined);
  if (!adventure) return;
  closeSidebar();
  closeInventory();
  activeDiaryAdventureId = adventure.id;
  document.getElementById('diaryTitle').textContent = `Diario — ${adventure.titolo}`;
  document.getElementById('diaryAdventureTitle').textContent = 'Annotazioni condivise con il gruppo.';
  document.getElementById('diaryNoteInput').value = '';
  document.getElementById('diaryMessage').textContent = '';
  document.getElementById('diaryDialog').showModal();
  await loadDiaryNotes(adventure.id);
}

async function loadDiaryNotes(adventureId) {
  const list = document.getElementById('diaryNotes');
  list.textContent = 'Caricamento annotazioni...';
  try {
    const result = await api('/api/diary', {operation:'list', adventure_id:adventureId});
    if (activeDiaryAdventureId !== adventureId) return;
    renderDiaryNotes(result.notes, adventureId);
  } catch(e) {
    if (activeDiaryAdventureId === adventureId) {
      list.replaceChildren();
      document.getElementById('diaryMessage').textContent = e.message;
    }
  }
}

function renderDiaryNotes(notes, adventureId) {
  const list = document.getElementById('diaryNotes');
  list.replaceChildren();
  if (!notes.length) {
    const empty = document.createElement('li');
    empty.className = 'muted';
    empty.textContent = 'Nessuna annotazione salvata.';
    list.appendChild(empty);
    return;
  }
  notes.forEach(note => {
    const item = document.createElement('li');
    item.className = 'diary-note';
    const content = document.createElement('div');
    content.className = 'diary-note-content';
    const timestamp = document.createElement('time');
    timestamp.className = 'diary-note-time';
    timestamp.textContent = note.timestamp;
    const text = document.createElement('div');
    text.textContent = note.testo;
    content.append(timestamp, text);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'danger diary-note-delete';
    remove.textContent = 'Elimina';
    remove.setAttribute('aria-label', 'Elimina annotazione');
    remove.onclick = async () => {
      if (!confirm('Eliminare questa annotazione dal diario?')) return;
      remove.disabled = true;
      try {
        const result = await api('/api/diary', {
          operation:'delete',
          adventure_id:adventureId,
          note_id:note.id
        });
        if (activeDiaryAdventureId !== adventureId) return;
        renderDiaryNotes(result.notes, adventureId);
        document.getElementById('diaryMessage').textContent = 'Annotazione eliminata.';
      } catch(e) {
        document.getElementById('diaryMessage').textContent = e.message;
        remove.disabled = false;
      }
    };
    item.append(content, remove);
    list.appendChild(item);
  });
}

async function saveDiaryNote() {
  const adventureId = activeDiaryAdventureId;
  const input = document.getElementById('diaryNoteInput');
  const button = document.getElementById('diarySave');
  const message = document.getElementById('diaryMessage');
  const text = input.value.trim();
  if (!adventureId || !text) {
    message.textContent = 'Scrivi il testo dell’annotazione.';
    return;
  }
  button.disabled = true;
  message.textContent = '';
  try {
    const result = await api('/api/diary', {operation:'add', adventure_id:adventureId, text});
    if (activeDiaryAdventureId !== adventureId) return;
    input.value = '';
    renderDiaryNotes(result.notes, adventureId);
    message.textContent = 'Annotazione salvata.';
  } catch(e) {
    message.textContent = e.message;
  } finally {
    button.disabled = false;
  }
}

document.getElementById('newCharBtn').onclick = () => document.getElementById('characterDialog').showModal();
document.getElementById('createChar').onclick = async (event) => {
  event.preventDefault();
  const dialog = document.getElementById('characterDialog');
  try {
    await api('/api/character',{
      nome:document.getElementById('charName').value,
      classe:document.getElementById('charClass').value,
      razza:document.getElementById('charRace').value,
      allineamento:document.getElementById('charAlignment').value,
      livello:parseInt(document.getElementById('charLevel').value || '1')
    });
    dialog.close();
    document.getElementById('charName').value = '';
    await refresh();
  } catch(e) { alert(e.message); }
};

document.getElementById('newBtn').onclick = () => {
  if (!state.my_characters.length) { alert('Crea prima almeno un personaggio.'); return; }
  document.getElementById('adventureDialog').showModal();
};
document.getElementById('createAdv').onclick = async (event) => {
  event.preventDefault();
  const select = document.getElementById('advParty');
  const party = [...select.selectedOptions].map(o => o.value);
  if (!party.length) { alert('Seleziona almeno un personaggio.'); return; }
  const send = document.getElementById('sendBtn');
  send.disabled = true;
  setProcessing(true);
  try {
    const result = await api('/api/adventure',{
      titolo:document.getElementById('advTitle').value,
      party,
      modulo:document.getElementById('advModule').value,
      modalita:document.getElementById('advMode').value
    });
    activeId = result.adventure.id;
    document.getElementById('adventureDialog').close();
    await refresh();
  } catch(e) { alert(e.message); }
  finally { send.disabled = false; setProcessing(false); }
};

document.getElementById('sendBtn').onclick = sendAction;
document.getElementById('action').onkeydown = e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAction(); }
};
async function sendAction() {
  if (!activeId) { alert('Seleziona un\'avventura.'); return; }
  const actionInput = document.getElementById('action');
  const action = actionInput.value.trim();
  if (!action) return;
  const send = document.getElementById('sendBtn');
  send.disabled = true;
  setProcessing(true);
  document.getElementById('output').textContent = 'Il Dungeon Master sta valutando...';
  try {
    const result = await api('/api/action',{adventure_id:activeId,action});
    actionInput.value = '';
    document.getElementById('output').textContent = '';
    await refresh();
    if (result.slash === true && typeof result.output === 'string') {
      const command = action.trim().split(/\s+/, 1)[0];
      openDrawer(`Risultato ${command}`, result.output || 'Nessun contenuto da mostrare.');
    }
  } catch(e) {
    document.getElementById('output').textContent = e.message;
  } finally {
    send.disabled = false;
    setProcessing(false);
  }
}

async function initialize() {
  try {
    const session = await api('/api/session');
    if (session.authenticated) await showGame(session.user);
    else showLogin();
  } catch(e) { showLogin(e.message); }
}

initialize();
window.setInterval(async () => {
  try { await refresh(); }
  catch(e) {
    if (e.message === 'Accedi per continuare.') showLogin('La sessione è scaduta. Accedi di nuovo.');
    else document.getElementById('status').textContent = e.message;
  }
}, 2500);
</script>
</body>
</html>
"""


def main():
    global PORT, WEB_USERNAME, WEB_PASSWORD
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        game.API_KEY_ATTIVA = sys.argv[1].strip()
    else:
        game.API_KEY_ATTIVA = api_key_active()

    if bool(WEB_USERNAME) != bool(WEB_PASSWORD):
        raise RuntimeError("WEB_USERNAME e DnD_USER_PASSWORD devono essere impostate entrambe.")
    if not WEB_USERNAME:
        if IS_RENDER:
            raise RuntimeError("Configura WEB_USERNAME e DnD_USER_PASSWORD nelle variabili d'ambiente Render.")
        WEB_USERNAME = input("Nome utente amministratore: ").strip()
        WEB_PASSWORD = getpass.getpass("Password amministratore: ")
    AUTH_STORE.configure_admin(WEB_USERNAME, WEB_PASSWORD)

    server = ThreadingHTTPServer((HOST, PORT), WebHandler)
    url = f"http://{HOST}:{PORT}"
    print(f"D&D Scatola Rossa web: {url}")
    print("Premi Ctrl+C per fermare il server.")
    if not IS_RENDER:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        DB.chiudi()


if __name__ == "__main__":
    main()
