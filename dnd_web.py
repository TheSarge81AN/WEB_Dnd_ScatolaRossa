import getpass
import html
import io
import json
import os
import re
import sys
import threading
import uuid
import webbrowser
from contextlib import redirect_stdout
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import dnd_fork as game
import web_auth


ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
IS_RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))
HOST = os.environ.get("HOST", "0.0.0.0" if IS_RENDER else "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
WEB_USERNAME = os.environ.get("WEB_USERNAME", "")
WEB_PASSWORD = os.environ.get("DnD_USER_PASSWORD", "")
USERS_FILE = os.path.join(ROOT, "utenti_web.json")
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

    if lower in ("/help", "/aiuto", "/help pdf", "/comandi pdf"):
        if lower in ("/help pdf", "/comandi pdf"):
            text, _ = capture_console(lambda: game.aggiorna_manuale_comandi_pdf(forza=True, silenzioso=False))
        else:
            text = game.HELP_TESTO
        return True, text

    if lower.startswith("/inventario"):
        name = stripped[len("/inventario"):].strip()
        if name and name.lower() not in ("party", "tutti"):
            selected = next((e for e in eroi if e["nome"].lower() == name.lower()), None)
            text, _ = capture_console(lambda: game.mostra_inventario(selected) if selected else print("Personaggio non trovato."))
        else:
            text, _ = capture_console(lambda: game.mostra_inventario_party(eroi))
        return True, text

    if lower in ("", "/magia"):
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

    if lower in ("/scheda pdf", "/schedapdf", "/esporta scheda"):
        text, _ = capture_console(lambda: print(game.esporta_scheda_pdf_a4(eroi[0])))
        return True, text

    if lower.startswith("/mappa pdf") or lower.startswith("/mappapdf") or lower == "/esporta mappa":
        text, _ = capture_console(lambda: print(game.esporta_mappa_pdf_a4(adventure, eroi)))
        return True, text

    if lower.startswith("/esporta"):
        text, _ = capture_console(lambda: print(game.esporta_cronaca_avventura(DB, adventure, eroi)))
        return True, text

    if lower in ("/suoni", "/suoni test"):
        sub = lower[len("/suoni"):].strip()
        if sub == "test":
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
            characters = safe_characters()
            if adventure:
                party = get_party(adventure, characters)
        if not adventure:
            return 404, {"error": "Avventura non trovata."}
        if not AUTH_STORE.is_member(user["id"], adventure_id):
            return 403, {"error": "Unisciti all'avventura prima di inviare azioni."}

        with LOCK:
            slash, slash_output = execute_slash(adventure, party, action)
        if slash:
            clean_output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", slash_output)
            return 200, {"ok": True, "output": clean_output, "adventure": adventure_view(adventure)}

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

        action = f"[{user['username']}] {action}"
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
        game.aggiorna_party_da_riquadro(party, response)
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
            self.current_user = AUTH_STORE.get_user(self.session_token())
        except (OSError, ValueError) as exc:
            json_response(self, 500, {"error": str(exc)})
            return False
        if self.current_user:
            return True
        json_response(self, 401, {"error": "Accedi per continuare."})
        return False

    def require_admin(self):
        if not hasattr(self, "current_user") and not self.require_auth():
            return False
        if self.current_user.get("is_admin"):
            return True
        json_response(self, 403, {"error": "Accesso riservato all'amministratore."})
        return False

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            json_response(self, 200, {"status": "ok"})
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
        if not self.require_auth():
            return
        if path == "/api/state":
            with LOCK:
                adventures = safe_adventures()
                characters = safe_characters()
            owned_names = AUTH_STORE.character_names(self.current_user["id"])
            key = api_key_active()
            adventure_data = []
            for adventure in adventures.values():
                view = adventure_view(adventure)
                view["joined"] = AUTH_STORE.is_member(self.current_user["id"], adventure["id"])
                view["can_delete"] = AUTH_STORE.is_adventure_owner(self.current_user["id"], adventure["id"])
                view["members"] = AUTH_STORE.member_names(adventure["id"])
                adventure_data.append(view)
            json_response(self, 200, {
                "user": self.current_user,
                "adventures": adventure_data,
                "characters": [character_view(v) for v in characters.values()],
                "my_characters": [character_view(characters[name]) for name in owned_names if name in characters],
                "classes": [
                    {"key": k, "nome": v["classe"], "livello_max": v["max_liv"]}
                    for k, v in game.CLASSI_BASE.items() if k not in CLASSI_RAZZA_BECMI
                ],
                "races": RAZZE_PERSONAGGIO,
                "modules": game.elenca_moduli_pdf(),
                "key_set": bool(key),
                "db": game.DB_FILE,
            })
            return
        json_response(self, 404, {"error": "Endpoint non trovato"})

    def do_POST(self):
        path = urlparse(self.path).path
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

            if not self.require_auth():
                return
            user = self.current_user

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
                    if any(name.lower() == character.lower() for name in adventure.get("party", [])):
                        json_response(self, 409, {"error": "Questo personaggio è già nel party."})
                        return
                    adventure.setdefault("party", []).append(character)
                    adventure["eroe"] = adventure["party"][0]
                    with LOCK:
                        DB.salva_metadati_avventura(adventure)
                    AUTH_STORE.add_member(user["id"], adventure_id)
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
        return


PAGE = r"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>D&D - Scatola Rossa</title>
  <style>
    :root { --red:#9c1c20; --gold:#d5ad55; --ink:#191512; --paper:#efe6cf; --panel:#fffaf0; --green:#4a6944; }
    * { box-sizing:border-box; }
    body { margin:0; background:#17130f; color:var(--ink); font-family:Georgia, "Times New Roman", serif; }
    #gameView[hidden], #loginView[hidden], #adminView[hidden] { display:none; }
    .login-view { min-height:100vh; display:grid; place-items:center; padding:20px; background:radial-gradient(ellipse at top,#492020,#17130f 70%); }

    .login-card { width:min(420px,100%); padding:28px; background:var(--paper); border:2px solid var(--gold); border-radius:6px; box-shadow:0 16px 48px #0008; }
    .login-card h1 { margin:0 0 8px; color:var(--red); text-align:center; }
    .login-card p { color:#5d5138; line-height:1.45; }
    .login-card .login-actions { display:flex; gap:8px; margin-top:16px; }
    .login-card .login-actions button { flex:1; }
    #loginMessage { min-height:20px; color:var(--red); }
    header { height:58px; display:flex; align-items:center; justify-content:space-between; padding:0 20px;
      background:linear-gradient(90deg,#321313,var(--red)); color:white; border-bottom:3px solid var(--gold); }
    header h1 { margin:0; font-size:21px; letter-spacing:.5px; }
    header .status { font-size:13px; color:#f4dda0; }
    main { height:calc(100vh - 58px); display:grid; grid-template-columns:280px minmax(0, 1fr); }
    aside, section { min-height:0; }
    aside { background:var(--paper); border-right:1px solid #baaa88; overflow:auto; padding:14px; }
    #sidebarToggle { display:none; }
    #sidebarBackdrop { display:none; }
    .panel { background:var(--panel); border:1px solid #b7a778; border-radius:4px; padding:12px; margin-bottom:12px; }
    .panel h2 { margin:0 0 10px; color:var(--red); font-size:16px; border-bottom:1px solid #d5cba8; padding-bottom:6px; }
    button, select, input, textarea { font:inherit; }
    button { border:1px solid #7c2626; background:#a83336; color:white; border-radius:3px; padding:7px 10px; cursor:pointer; }
    button.secondary { background:#eee3c5; color:#351818; border-color:#99865f; }
    button.danger { background:#65201f; }
    button:disabled { opacity:.55; cursor:not-allowed; }
    input, select, textarea { width:100%; border:1px solid #aa9a70; background:#fffdf7; padding:8px; border-radius:3px; }
    label { display:block; font-size:12px; margin:7px 0 3px; color:#5d5138; }
    .adv { width:100%; text-align:left; margin:4px 0; background:#fffdf7; color:var(--ink); border-color:#bbaa82; }
    .adv.active { background:#eadba9; border-color:#9c1c20; }
    .adv-wrap { display:flex; gap:4px; margin:4px 0; }
    .adv-wrap .adv { margin:0; flex:1; }
    .adv-delete { width:34px; padding:5px; background:#65201f; }
    .chat { background:#faf6e9; display:flex; flex-direction:column; }
    #messages { flex:1; overflow:auto; padding:20px 28px; }
    .message { max-width:900px; margin:0 auto 14px; white-space:pre-wrap; line-height:1.48; }
    .message.user { border-left:3px solid #7c8b67; padding:9px 12px; background:#f0ead8; }
    .message.model { border-left:3px solid var(--red); padding:9px 12px; background:white; }
    .composer { border-top:1px solid #b8a985; background:#e9dfc2; padding:12px 16px; }
    .composer-row { display:flex; gap:8px; }
    .composer textarea { resize:none; height:48px; }
    .composer button { width:90px; }
    #output { min-height:30px; padding:8px 12px 0; color:#74302e; font-size:13px; }
    .hero { border-bottom:1px dashed #baa978; padding:7px 0; }
    .hero strong { color:var(--red); }
    .party-hero-head { display:flex; align-items:center; justify-content:space-between; gap:6px; }
    .inventory-button { position:relative; z-index:32; display:grid; place-items:center; width:32px; height:30px; padding:3px; background:var(--red); border-color:#6f1115; }
    .inventory-button svg { display:block; width:21px; height:21px; }
    .party-title { color:var(--red); font-weight:bold; margin-bottom:6px; }
    .command-help summary { color:var(--red); font-weight:bold; cursor:pointer; }
    .command-help ul { list-style:none; margin:9px 0 0; padding:0; }
    .command-help li { display:block; padding:6px 0; border-bottom:1px dashed #d5cba8; font-size:12px; }
    .command-shortcut { display:block; margin-bottom:4px; padding:3px 5px; font-family:monospace; font-size:11px; }
    #inventoryBackdrop { position:fixed; z-index:29; inset:0; background:#0008; opacity:0; pointer-events:none; transition:opacity .22s ease; }
    #inventoryPanel { position:fixed; z-index:30; left:50%; bottom:0; width:min(720px,calc(100vw - 24px)); max-height:min(65vh,600px); overflow:auto; padding:16px; background:var(--paper); border:1px solid #b7a778; border-bottom:0; border-radius:12px 12px 0 0; box-shadow:0 -8px 28px #0005; transform:translate(-50%,calc(100% + 24px)); transition:transform .24s ease; }
    body.inventory-open #inventoryBackdrop { opacity:1; pointer-events:auto; }
    body.inventory-open #inventoryPanel { transform:translate(-50%,0); }
    body.inventory-open #sidebar { z-index:31; }
    .inventory-panel-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }
    .inventory-panel-heading h2 { margin:0; color:var(--red); font-size:18px; }
    #inventoryClose { width:34px; padding:4px; font-size:20px; line-height:1; }
    #inventoryContent { white-space:pre-wrap; line-height:1.5; }
    .muted { color:#756d5a; font-size:12px; }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
    #adminView main.admin-main { height:auto; min-height:calc(100vh - 58px); display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); align-content:start; gap:16px; padding:20px; }
    .admin-user-row { display:flex; align-items:center; gap:8px; border-bottom:1px dashed #d5cba8; padding:8px 0; }
    .admin-user-row strong { min-width:120px; }
    .admin-user-row input { min-width:100px; }
    .admin-key-status { margin-top:10px; color:#5d5138; }
    .chat { min-width:0; }
    @media (max-width:900px) {
      main { grid-template-columns:220px minmax(0, 1fr); }
    }
    @media (max-width:700px) {
      header { justify-content:flex-start; gap:10px; padding:0 12px; }
      header h1 { font-size:17px; }
      header .status { display:none; }
      #sidebarToggle { display:inline-flex; align-items:center; justify-content:center; min-width:40px; }
      main { display:block; height:calc(100vh - 58px); }
      #adminView main.admin-main { display:block; height:auto; }
      #sidebar {
        position:fixed; z-index:20; top:58px; bottom:0; left:0;
        width:min(86vw, 320px); border-right:1px solid #baaa88;
        box-shadow:8px 0 24px #0005; transform:translateX(-105%);
        transition:transform .22s ease;
      }
      body.sidebar-open #sidebar { transform:translateX(0); }
      #sidebarBackdrop {
        position:fixed; z-index:19; inset:58px 0 0;
        background:#0008;
      }
      body.sidebar-open #sidebarBackdrop { display:block; }
      .chat { height:calc(100vh - 58px); }
      #messages { padding:14px 12px; }
      .composer { padding:10px; }
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
  </form>
</section>
<div id="gameView" hidden>
<header>
  <button id="sidebarToggle" type="button" aria-label="Apri il menu" aria-expanded="false">☰</button>
  <h1>D&amp;D - Scatola Rossa</h1>
  <div style="display:flex;align-items:center;gap:12px"><div class="status" id="status">Caricamento...</div><span id="currentUser" class="status"></span><button id="adminBtn" class="secondary" type="button" hidden>Amministrazione</button><button id="logoutBtn" class="secondary" type="button">Esci</button></div>
</header>
<div id="sidebarBackdrop"></div>
<div id="inventoryBackdrop"></div>
<main>
  <aside id="sidebar">
    <div class="panel">
      <h2>Partita</h2>
      <div id="partyAdventureTitle" class="party-title">Nessuna avventura selezionata</div>
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
    <details class="panel command-help">
      <summary>Comandi disponibili</summary>
      <ul id="commandList"></ul>
    </details>
  </aside>
  <section class="chat">
    <div id="messages"></div>
    <div id="output"></div>
    <div class="composer">
      <div class="composer-row">
        <textarea id="action" placeholder="Descrivi l'azione oppure usa un comando, ad esempio /inventario"></textarea>
        <button id="sendBtn">Invia</button>
      </div>
    </div>
  </section>
</main>

<section id="inventoryPanel" role="dialog" aria-modal="true" aria-labelledby="inventoryTitle" aria-hidden="true">
  <div class="inventory-panel-heading">
    <h2 id="inventoryTitle">Inventario</h2>
    <button id="inventoryClose" type="button" aria-label="Chiudi inventario">×</button>
  </div>
  <div id="inventoryContent"></div>
</section>

<dialog id="characterDialog">
  <form method="dialog" style="min-width:min(420px,90vw)">
    <h2 style="color:#9c1c20">Nuovo personaggio</h2>
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
    <h2 style="color:#9c1c20">Nuova avventura</h2>
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
    <h2 style="color:#9c1c20">Unisciti alla sessione</h2>
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

<section id="adminView" hidden>
  <header>
    <h1>Amministrazione</h1>
    <div style="display:flex;align-items:center;gap:12px"><span id="adminCurrentUser" class="status"></span><button id="adminBack" class="secondary" type="button">Torna al gioco</button><button id="adminLogoutBtn" class="secondary" type="button">Esci</button></div>
  </header>
  <main class="admin-main">
    <section class="panel">
      <h2>Account giocatori</h2>
      <p class="muted">Gli account sono salvati in <code>utenti_web.json</code>; le password nel file sono protette con hash e salt.</p>
      <form id="adminUserForm">
        <label for="newUsername">Nome utente</label><input id="newUsername" minlength="3" maxlength="32" required>
        <label for="newUserPassword">Password (almeno 10 caratteri)</label><input id="newUserPassword" type="password" minlength="10" required>
        <button type="submit" style="margin-top:10px">Crea utente</button>
      </form>
      <div id="adminUsers" style="margin-top:14px"></div>
      <p id="adminUserMessage" class="admin-key-status" role="status"></p>
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

<script>
let state = null;
let activeId = null;

const WEB_COMMANDS = [
  {label:'/help', value:'/help', description:'Mostra la guida rapida.'},
  {label:'/help pdf', value:'/help pdf', description:'Genera il manuale comandi PDF.'},
  {label:'/inventario', value:'/inventario', description:'Mostra l’inventario del party.'},
  {label:'/magia', value:'/magia', description:'Mostra grimorio e slot.'},
  {label:'/torcia [on|off|auto]', value:'/torcia ', description:'Gestisce torce; completa con on, off o auto.'},
  {label:'/ambiente [tipo]', value:'/ambiente ', description:'Imposta taverna, citta, dungeon o auto.'},
  {label:'/incontri [frequenza]', value:'/incontri ', description:'Usa raro, normale, frequente oppure off.'},
  {label:'/modalita [tipo]', value:'/modalita ', description:'Usa interattiva o classica.'},
  {label:'/scheda pdf', value:'/scheda pdf', description:'Esporta la scheda del primo eroe del party.'},
  {label:'/mappa pdf', value:'/mappa pdf', description:'Esporta la mappa tattica PDF.'},
  {label:'/esporta', value:'/esporta', description:'Esporta la cronaca della campagna.'},
  {label:'/suoni [test]', value:'/suoni ', description:'Attiva/disattiva gli effetti o prova i suoni.'}
];

function closeSidebar() {
  document.body.classList.remove('sidebar-open');
  document.getElementById('sidebarToggle').setAttribute('aria-expanded', 'false');
}

let activeInventoryName = null;

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
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    closeSidebar();
    closeInventory();
  }
});

function renderCommandList() {
  const list = document.getElementById('commandList');
  WEB_COMMANDS.forEach(command => {
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
      closeSidebar();
    };
    const description = document.createElement('span');
    description.textContent = command.description;
    item.append(button, description);
    list.appendChild(item);
  });
}

renderCommandList();

async function api(url, data) {
  const res = await fetch(url, data ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {});
  const json = await res.json();
  if (!res.ok) throw new Error(json.error || 'Errore');
  return json;
}

let refreshing = false;
let renderedAdventureId = null;

function showLogin(message = '') {
  document.getElementById('gameView').hidden = true;
  document.getElementById('adminView').hidden = true;
  document.getElementById('loginView').hidden = false;
  document.getElementById('loginMessage').textContent = message;
  activeId = null;
  state = null;
  renderedAdventureId = null;
}

async function showGame(user) {
  document.getElementById('loginView').hidden = true;
  document.getElementById('adminView').hidden = true;
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
  try {
    const result = await api('/api/admin');
    const list = document.getElementById('adminUsers');
    list.replaceChildren();
    result.users.forEach(username => {
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
      list.append(row);
    });
    const key = result.api_key;
    document.getElementById('adminApiKeyStatus').textContent = key.configured
      ? `Configurata (${key.source}): ${key.masked}` : 'Nessuna chiave Gemini configurata.';
  } catch(e) {
    document.getElementById('adminApiKeyMessage').textContent = e.message;
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

async function refresh() {
  if (refreshing || document.getElementById('gameView').hidden) return;
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
    `<div class="hero"><strong>${escapeHtml(c.nome)}</strong><br><span class="muted">Classe: ${escapeHtml(c.classe)} | Razza: ${escapeHtml(c.razza || 'Umano')} | Liv. ${c.livello} | PF ${c.pf_attuali}/${c.pf_max}</span></div>`
  ).join('') : '<div class="muted">Crea un personaggio per partecipare.</div>';

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
  document.getElementById('advModule').innerHTML = '<option value="">Scenario predefinito</option>' +
    state.modules.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
  document.getElementById('advParty').innerHTML = state.my_characters.map(c =>
    `<option value="${escapeHtml(c.nome)}">${escapeHtml(c.nome)} - Classe: ${escapeHtml(c.classe)} | Razza: ${escapeHtml(c.razza || 'Umano')} Liv. ${c.livello}</option>`
  ).join('');
  document.getElementById('joinCharacter').innerHTML = state.my_characters.map(c =>
    `<option value="${escapeHtml(c.nome)}">${escapeHtml(c.nome)} - Classe: ${escapeHtml(c.classe)} | Razza: ${escapeHtml(c.razza || 'Umano')} Liv. ${c.livello}</option>`
  ).join('');
  if (!state.adventures.some(a => a.id === activeId && a.joined)) {
    activeId = state.adventures.find(a => a.joined)?.id || null;
  }
  renderActive();
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

function renderActive() {
  const adv = state?.adventures.find(a => a.id === activeId && a.joined);
  const messages = document.getElementById('messages');
  const party = document.getElementById('party');
  const title = document.getElementById('partyAdventureTitle');
  if (!adv) {
    title.textContent = 'Nessuna avventura selezionata';
    const placeholder = '<div class="message">Seleziona una sessione a cui partecipi o unisciti a una sessione disponibile.</div>';
    if (messages.innerHTML !== placeholder) messages.innerHTML = placeholder;
    renderedAdventureId = null;
    party.innerHTML = '';
    return;
  }
  title.textContent = `${adv.titolo} — ${adv.members.join(', ') || 'nessun partecipante'}`;
  const messageHtml = adv.storia.map(m =>
    `<div class="message ${m.role === 'model' ? 'model' : 'user'}">${escapeHtml(m.text)}</div>`
  ).join('');
  const wasAtBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 60;
  const adventureChanged = renderedAdventureId !== adv.id;
  if (adventureChanged || messages.innerHTML !== messageHtml) {
    messages.innerHTML = messageHtml;
    renderedAdventureId = adv.id;
    if (adventureChanged || wasAtBottom) {
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

async function showInventory(name) {
  if (document.body.classList.contains('inventory-open') && activeInventoryName === name) {
    closeInventory();
    return;
  }
  activeInventoryName = name;
  const panel = document.getElementById('inventoryPanel');
  const content = document.getElementById('inventoryContent');
  document.getElementById('inventoryTitle').textContent = `Inventario - ${name}`;
  content.textContent = 'Caricamento inventario...';
  document.body.classList.add('inventory-open');
  panel.setAttribute('aria-hidden', 'false');
  try {
    const result = await api('/api/action', {
      adventure_id:activeId,
      action:`/inventario ${name}`
    });
    if (activeInventoryName === name) content.textContent = result.output || 'Inventario vuoto.';
  } catch(e) {
    if (activeInventoryName === name) content.textContent = e.message;
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
  finally { send.disabled = false; }
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
  document.getElementById('output').textContent = 'Il Dungeon Master sta valutando...';
  try {
    const result = await api('/api/action',{adventure_id:activeId,action});
    actionInput.value = '';
    document.getElementById('output').textContent = result.output || '';
    await refresh();
  } catch(e) {
    document.getElementById('output').textContent = e.message;
  } finally {
    send.disabled = false;
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
