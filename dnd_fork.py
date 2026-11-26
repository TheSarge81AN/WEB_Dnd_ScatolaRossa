import os
import sys
import re
import json
import time
import socket
import base64
import random
import select
import subprocess
import threading
import math
import struct
import shutil
import wave
import zlib
import hashlib
from datetime import datetime

import db_backend
from google import genai
from google.genai import errors, types

DB_FILE = "dnd_becmi.db"
ADVENTURES_FILE = "avventure_dnd.json"
MODULI_DIR = "moduli_pdf"
CHARACTERS_FILE = "personaggi_dnd.json"
LEGACY_SAVE = "salvataggio_dnd.json"
LEGACY_DIARY = "diario_avventura.txt"
SUONI_DIR = "suoni"
MAPPE_DIR = "mappe"
SCHEDE_DIR = "schede"
MANUALE_FILE = "manuale_comandi_dnd.pdf"
MANUALE_HASH_FILE = ".manuale_hash"
MODELLI_FALLBACK = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.8-flash"
]
MODELLO = MODELLI_FALLBACK[0]
DEFAULT_LAN_PORT = 5555
CHIAVE_API_PREDEFINITA = ""
KEY_FILE = ".gemini_api_key"
API_KEY_ATTIVA = ""

VERDE = "\033[92m"
GIALLO = "\033[93m"
CIANO = "\033[96m"
ROSSO = "\033[91m"
MAGENTA = "\033[95m"
GRASSETTO = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

SUONI_ATTIVI = True
MODALITA_GIOCO_PREDEFINITA = "interattiva"
MODALITA_GIOCO = MODALITA_GIOCO_PREDEFINITA
AUTODADI_ATTIVI = (MODALITA_GIOCO == "classica")


def carica_api_key_salvata() -> str:
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                k = f.read().strip()
                if k:
                    return k
        except Exception:
            pass
    return ""


def salva_api_key(chiave: str) -> bool:
    try:
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(chiave.strip())
        try:
            os.chmod(KEY_FILE, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False


def elimina_api_key_salvata() -> bool:
    try:
        if os.path.exists(KEY_FILE):
            os.remove(KEY_FILE)
            return True
    except Exception:
        pass
    return False


def maschera_chiave(chiave: str) -> str:
    if not chiave:
        return f"{ROSSO}NON IMPOSTATA{RESET}"
    ch = chiave.strip()
    if len(ch) <= 8:
        return f"{GIALLO}****{RESET}"
    return f"{VERDE}{ch[:4]}...{ch[-4:]}{RESET}"


def richiedi_api_key_interattiva(forza_richiesta=False) -> str:
    if not forza_richiesta:
        chiave = os.environ.get("GEMINI_API_KEY", "").strip()
        if not chiave:
            chiave = carica_api_key_salvata()
        if chiave:
            return chiave

    os.system("clear" if os.name == "posix" else "cls")
    print(LOGO_INTRO)
    print(f"{CIANO}{GRASSETTO}================================================================================================{RESET}")
    print(f"{GIALLO}{GRASSETTO}🔑 AUTENTICAZIONE GOOGLE GEMINI AI - D&D BECMI FORK{RESET}")
    print(f"{CIANO}{GRASSETTO}================================================================================================{RESET}\n")
    print("Questo fork richiede l'inserimento di una chiave API Google Gemini per animare il Dungeon Master AI.")
    print(f"Puoi ottenerne una gratuitamente in pochi secondi su: {VERDE}https://aistudio.google.com/app/apikey{RESET}\n")

    chiave_esistente = carica_api_key_salvata() or os.environ.get("GEMINI_API_KEY", "").strip()
    if chiave_esistente:
        print(f"Chiave attualmente memorizzata: {maschera_chiave(chiave_esistente)}")
        print(f"{DIM}(Premi Invio per confermare la chiave memorizzata, oppure inseriscine una nuova){RESET}\n")

    while True:
        try:
            inp = input(f"{VERDE}{GRASSETTO}Inserisci la tua Gemini API Key (o 'q' per uscire) > {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return ""

        if inp.lower() in ["q", "exit", "quit", "0"]:
            return ""

        if not inp and chiave_esistente:
            return chiave_esistente

        if inp:
            if len(inp) < 15:
                print(f"{ROSSO}⚠️ La chiave inserita sembra troppo corta o non valida. Riprova o premi 'q' per uscire.{RESET}")
                continue

            salva = input(f"\n{CIANO}Vuoi salvare la chiave in locale ({KEY_FILE}) per i prossimi avvii? (s/n) [s] > {RESET}").strip().lower()
            if salva not in ["n", "no"]:
                if salva_api_key(inp):
                    print(f"{VERDE}✓ Chiave salvata in {KEY_FILE} con permessi protetti (0600).{RESET}")
                else:
                    print(f"{GIALLO}Impossibile scrivere il file {KEY_FILE}. La chiave sarà attiva per questa sessione.{RESET}")
            else:
                print(f"{GIALLO}La chiave sarà memorizzata solo per questa sessione in RAM.{RESET}")
            time.sleep(1)
            return inp

# ==============================================================================
# MOTORE PROGRESSIONE COMPLETA BECMI (BASIC, EXPERT, COMPANION, MASTER, IMMORTAL)
# ==============================================================================

BECMI_CLASSES = {
    "1": {
        "classe": "Guerriero", "dado_vita": 8, "pf_dopo_9": 2, "ca_base": 3, "max_liv": 36,
        "forza": 15, "intelligenza": 9, "saggezza": 10, "destrezza": 13, "costituzione": 14, "carisma": 11,
        "equip": ["Spada Lunga (1d8+1)", "Pugnale (1d4+1)", "Arco Corto (1d6)", "20 Frecce", "Corazza di Maglia", "Scudo", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre", "Corda 15m", "Pertica 3m"],
        "mo": 15,
        "xp": [0, 2000, 4000, 8000, 16000, 32000, 64000, 120000, 240000, 360000, 480000, 600000, 720000, 840000, 960000, 1080000, 1200000, 1320000, 1440000, 1560000, 1680000, 1800000, 1920000, 2040000, 2160000, 2280000, 2400000, 2520000, 2640000, 2760000, 2880000, 3000000, 3120000, 3240000, 3360000, 3480000]
    },
    "2": {
        "classe": "Elfo", "dado_vita": 6, "pf_dopo_9": 2, "ca_base": 4, "max_liv": 10,
        "forza": 13, "intelligenza": 14, "saggezza": 10, "destrezza": 14, "costituzione": 12, "carisma": 12,
        "equip": ["Spada Lunga (1d8+1)", "Arco Corto (1d6)", "20 Frecce", "Corazza di Maglia", "Libro Incantesimi (Sonno, Lettura Magico)", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre", "Pertica 3m"],
        "mo": 20,
        "xp": [0, 4000, 8000, 16000, 32000, 64000, 120000, 250000, 400000, 600000]
    },
    "3": {
        "classe": "Nano", "dado_vita": 8, "pf_dopo_9": 3, "ca_base": 3, "max_liv": 12,
        "forza": 14, "intelligenza": 9, "saggezza": 11, "destrezza": 11, "costituzione": 16, "carisma": 9,
        "equip": ["Ascia da Battaglia (1d8+1)", "Martello da Guerra (1d6+1)", "Corazza di Maglia", "Scudo", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre", "Corda 15m", "Pertica 3m"],
        "mo": 25,
        "xp": [0, 2200, 4400, 8800, 17000, 35000, 70000, 140000, 270000, 400000, 530000, 660000]
    },
    "4": {
        "classe": "Ladro", "dado_vita": 4, "pf_dopo_9": 2, "ca_base": 6, "max_liv": 36,
        "forza": 11, "intelligenza": 12, "saggezza": 10, "destrezza": 16, "costituzione": 12, "carisma": 13,
        "equip": ["Spada Corta (1d6)", "2 Pugnali (1d4)", "Fionda (1d4) + 20 Pietre", "Armatura di Cuoio", "Attrezzi da Scasso", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Corda 15m"],
        "mo": 30,
        "xp": [0, 1200, 2400, 4800, 9600, 20000, 40000, 80000, 160000, 280000, 400000, 520000, 640000, 760000, 880000, 1000000, 1120000, 1240000, 1360000, 1480000, 1600000, 1720000, 1840000, 1960000, 2080000, 2200000, 2320000, 2440000, 2560000, 2680000, 2800000, 2920000, 3040000, 3160000, 3280000, 3400000]
    },
    "5": {
        "classe": "Chierico", "dado_vita": 6, "pf_dopo_9": 1, "ca_base": 3, "max_liv": 36,
        "forza": 13, "intelligenza": 10, "saggezza": 15, "destrezza": 10, "costituzione": 13, "carisma": 13,
        "equip": ["Mazza Ferrata (1d6+1)", "Fionda (1d4)", "Corazza di Maglia", "Scudo", "Simbolo Sacro d'Argento", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre"],
        "mo": 20,
        "xp": [0, 1500, 3000, 6000, 12000, 25000, 50000, 100000, 200000, 300000, 400000, 500000, 600000, 700000, 800000, 900000, 1000000, 1100000, 1200000, 1300000, 1400000, 1500000, 1600000, 1700000, 1800000, 1900000, 2000000, 2100000, 2200000, 2300000, 2400000, 2500000, 2600000, 2700000, 2800000, 2900000]
    },
    "6": {
        "classe": "Mago", "dado_vita": 4, "pf_dopo_9": 1, "ca_base": 9, "max_liv": 36,
        "forza": 9, "intelligenza": 16, "saggezza": 12, "destrezza": 13, "costituzione": 11, "carisma": 11,
        "equip": ["Pugnale (1d4)", "Bastone Ferrato (1d4)", "Libro Incantesimi (Sonno, Dardo Incantato, Luce)", "Veste da Viaggio", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre"],
        "mo": 35,
        "xp": [0, 2500, 5000, 10000, 20000, 40000, 80000, 150000, 300000, 450000, 600000, 750000, 900000, 1050000, 1200000, 1350000, 1500000, 1650000, 1800000, 1950000, 2100000, 2250000, 2400000, 2550000, 2700000, 2850000, 3000000, 3150000, 3300000, 3450000, 3600000, 3750000, 3900000, 4050000, 4200000, 4350000]
    },
    "7": {
        "classe": "Halfling", "dado_vita": 6, "pf_dopo_9": 0, "ca_base": 5, "max_liv": 8,
        "forza": 11, "intelligenza": 11, "saggezza": 12, "destrezza": 16, "costituzione": 14, "carisma": 13,
        "equip": ["Spada Corta (1d6)", "Fionda (1d4) + 20 Pietre", "Corazza di Maglia", "Scudo", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre"],
        "mo": 25,
        "xp": [0, 2000, 4000, 8000, 16000, 32000, 64000, 120000]
    },
    "8": {
        "classe": "Paladino", "dado_vita": 8, "pf_dopo_9": 2, "ca_base": 2, "max_liv": 36,
        "forza": 16, "intelligenza": 10, "saggezza": 14, "destrezza": 12, "costituzione": 15, "carisma": 17,
        "equip": ["Spada Lunga (1d8+2)", "Lancia da Cavaliere (1d10+2)", "Corazza di Piastre", "Scudo", "Simbolo Sacro", "Destriero da Guerra", "Zaino", "6 Torce", "7 Razioni"],
        "mo": 40,
        "xp": [0, 2000, 4000, 8000, 16000, 32000, 64000, 120000, 240000, 360000, 480000, 600000, 720000, 840000, 960000, 1080000, 1200000, 1320000, 1440000, 1560000, 1680000, 1800000, 1920000, 2040000, 2160000, 2280000, 2400000, 2520000, 2640000, 2760000, 2880000, 3000000, 3120000, 3240000, 3360000, 3480000]
    },
    "9": {
        "classe": "Druido", "dado_vita": 6, "pf_dopo_9": 1, "ca_base": 6, "max_liv": 36,
        "forza": 11, "intelligenza": 12, "saggezza": 16, "destrezza": 13, "costituzione": 13, "carisma": 15,
        "equip": ["Falcetto (1d4)", "Bastone Ferrato (1d4)", "Fionda (1d4)", "Armatura di Cuoio", "Vischio Sacro", "Zaino", "6 Torce", "7 Razioni", "Otre"],
        "mo": 25,
        "xp": [0, 1500, 3000, 6000, 12000, 25000, 50000, 100000, 200000, 300000, 400000, 500000, 600000, 700000, 800000, 900000, 1000000, 1100000, 1200000, 1300000, 1400000, 1500000, 1600000, 1700000, 1800000, 1900000, 2000000, 2100000, 2200000, 2300000, 2400000, 2500000, 2600000, 2700000, 2800000, 2900000]
    }
}

RANGHI_IMMORTALI = [
    (1, 6, "Iniziato", 100),
    (7, 12, "Temporale", 200),
    (13, 18, "Celeste", 350),
    (19, 24, "Empireo", 500),
    (25, 30, "Eterno", 750),
    (31, 36, "Gerarca", 1000)
]


# ==============================================================================
# MOTORE PERSISTENZA SQLITE (v9.1 MULTI-PARTY & LAN)
# ==============================================================================

class DnDDatabase:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self.conn = db_backend.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self._crea_schema()

    def _crea_schema(self):
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS personaggi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    classe TEXT NOT NULL,
                    razza TEXT NOT NULL DEFAULT 'Umano',
                    livello INTEGER NOT NULL DEFAULT 1,
                    allineamento TEXT NOT NULL DEFAULT 'Legale',
                    immortale INTEGER NOT NULL DEFAULT 0,
                    forza INTEGER NOT NULL,
                    intelligenza INTEGER NOT NULL,
                    saggezza INTEGER NOT NULL,
                    destrezza INTEGER NOT NULL,
                    costituzione INTEGER NOT NULL,
                    carisma INTEGER NOT NULL,
                    pf_attuali INTEGER NOT NULL,
                    pf_max INTEGER NOT NULL,
                    ca INTEGER NOT NULL,
                    mo INTEGER NOT NULL DEFAULT 15,
                    pe INTEGER NOT NULL DEFAULT 0,
                    ts TEXT DEFAULT '',
                    attacco TEXT DEFAULT '',
                    abilita_classe TEXT DEFAULT '',
                    fascia_becmi TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS inventario (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    personaggio_id INTEGER NOT NULL,
                    oggetto TEXT NOT NULL,
                    FOREIGN KEY (personaggio_id) REFERENCES personaggi(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS avventure (
                    id TEXT PRIMARY KEY,
                    titolo TEXT NOT NULL,
                    eroe_nome TEXT NOT NULL,
                    party_json TEXT DEFAULT '[]',
                    data_aggiornamento TEXT NOT NULL,
                    modulo_pdf TEXT DEFAULT '',
                    modulo_testo TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS messaggi_storia (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    avventura_id TEXT NOT NULL,
                    ruolo TEXT NOT NULL,
                    testo TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (avventura_id) REFERENCES avventure(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS diario_note (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    avventura_id TEXT NOT NULL,
                    testo TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (avventura_id) REFERENCES avventure(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_msg_avventura ON messaggi_storia(avventura_id, id);
                CREATE INDEX IF NOT EXISTS idx_inv_pg ON inventario(personaggio_id);
                CREATE INDEX IF NOT EXISTS idx_note_avv ON diario_note(avventura_id, id);
            """)
            cols = self.conn.table_columns("avventure")
            if "party_json" not in cols:
                self.conn.execute("ALTER TABLE avventure ADD COLUMN party_json TEXT DEFAULT '[]'")
            if "stato_dungeon_json" not in cols:
                self.conn.execute("ALTER TABLE avventure ADD COLUMN stato_dungeon_json TEXT DEFAULT '{}'")
            cols_pg = self.conn.table_columns("personaggi")
            if "razza" not in cols_pg:
                self.conn.execute("ALTER TABLE personaggi ADD COLUMN razza TEXT NOT NULL DEFAULT 'Umano'")
            if "incantesimi_json" not in cols_pg:
                self.conn.execute("ALTER TABLE personaggi ADD COLUMN incantesimi_json TEXT DEFAULT '{}'")

    def salva_personaggio(self, eroe: dict):
        sincronizza_statistiche_becmi(eroe)
        inc_json = json.dumps({
            "memorizzati": eroe.get("incantesimi_memorizzati", []),
            "usati": eroe.get("slot_usati", {})
        }, ensure_ascii=False)
        with self.conn:
            cur = self.conn.execute("SELECT id FROM personaggi WHERE nome = ?", (eroe["nome"],))
            row = cur.fetchone()
            if row:
                pg_id = row["id"]
                self.conn.execute("""
                    UPDATE personaggi SET
                        classe = ?, razza = ?, livello = ?, allineamento = ?, immortale = ?,
                        forza = ?, intelligenza = ?, saggezza = ?, destrezza = ?,
                        costituzione = ?, carisma = ?, pf_attuali = ?, pf_max = ?,
                        ca = ?, mo = ?, pe = ?, ts = ?, attacco = ?,
                        abilita_classe = ?, fascia_becmi = ?, incantesimi_json = ?
                    WHERE id = ?
                """, (
                    eroe["classe"], eroe.get("razza", "Umano"), int(eroe["livello"]), eroe["allineamento"], int(bool(eroe.get("immortale", False))),
                    int(eroe["forza"]), int(eroe["intelligenza"]), int(eroe["saggezza"]), int(eroe["destrezza"]),
                    int(eroe["costituzione"]), int(eroe["carisma"]), int(eroe["pf_attuali"]), int(eroe["pf_max"]),
                    int(eroe["ca"]), int(eroe["mo"]), int(eroe["pe"]),
                    eroe.get("ts", ""), eroe.get("attacco", ""), eroe.get("abilita_classe", ""), eroe.get("fascia_becmi", ""),
                    inc_json, pg_id
                ))
            else:
                cur = self.conn.execute("""
                    INSERT INTO personaggi (
                        nome, classe, razza, livello, allineamento, immortale,
                        forza, intelligenza, saggezza, destrezza, costituzione, carisma,
                        pf_attuali, pf_max, ca, mo, pe, ts, attacco, abilita_classe, fascia_becmi, incantesimi_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    eroe["nome"], eroe["classe"], eroe.get("razza", "Umano"), int(eroe["livello"]), eroe["allineamento"], int(bool(eroe.get("immortale", False))),
                    int(eroe["forza"]), int(eroe["intelligenza"]), int(eroe["saggezza"]), int(eroe["destrezza"]),
                    int(eroe["costituzione"]), int(eroe["carisma"]), int(eroe["pf_attuali"]), int(eroe["pf_max"]),
                    int(eroe["ca"]), int(eroe["mo"]), int(eroe["pe"]),
                    eroe.get("ts", ""), eroe.get("attacco", ""), eroe.get("abilita_classe", ""), eroe.get("fascia_becmi", ""),
                    inc_json
                ))
                pg_id = cur.lastrowid

            self.conn.execute("DELETE FROM inventario WHERE personaggio_id = ?", (pg_id,))
            equip_list = eroe.get("equip", [])
            if equip_list:
                self.conn.executemany(
                    "INSERT INTO inventario (personaggio_id, oggetto) VALUES (?, ?)",
                    [(pg_id, str(item)) for item in equip_list]
                )

    def carica_tutti_personaggi(self) -> dict:
        personaggi = {}
        cur = self.conn.execute("SELECT * FROM personaggi ORDER BY id ASC")
        for r in cur.fetchall():
            pg = dict(r)
            pg["immortale"] = bool(pg["immortale"])
            inv_cur = self.conn.execute("SELECT oggetto FROM inventario WHERE personaggio_id = ? ORDER BY id ASC", (pg["id"],))
            pg["equip"] = [ir["oggetto"] for ir in inv_cur.fetchall()]
            try:
                inc_data = json.loads(pg.get("incantesimi_json") or "{}")
            except Exception:
                inc_data = {}
            pg["incantesimi_memorizzati"] = inc_data.get("memorizzati", [])
            pg["slot_usati"] = inc_data.get("usati", {})
            sincronizza_statistiche_becmi(pg)
            personaggi[pg["nome"]] = pg
        return personaggi

    def salva_metadati_avventura(self, adv: dict):
        party_list = adv.get("party") or [adv.get("eroe", "Valen di Corvobianco")]
        party_str = json.dumps(party_list, ensure_ascii=False)
        eroe_principale = party_list[0]
        st_dungeon = adv.get("stato_dungeon") or {
            "torcia_turni": adv.get("torcia_turni_rimasti", 6),
            "torcia_attiva": adv.get("torcia_attiva", True)
        }
        st_dungeon_str = json.dumps(st_dungeon, ensure_ascii=False)
        with self.conn:
            self.conn.execute("""
                INSERT INTO avventure (id, titolo, eroe_nome, party_json, data_aggiornamento, modulo_pdf, modulo_testo, stato_dungeon_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    titolo = excluded.titolo,
                    eroe_nome = excluded.eroe_nome,
                    party_json = excluded.party_json,
                    data_aggiornamento = excluded.data_aggiornamento,
                    modulo_pdf = excluded.modulo_pdf,
                    modulo_testo = excluded.modulo_testo,
                    stato_dungeon_json = excluded.stato_dungeon_json
            """, (
                adv["id"], adv["titolo"], eroe_principale, party_str,
                adv.get("data", datetime.now().strftime("%d/%m/%Y %H:%M")),
                adv.get("modulo_pdf", ""), adv.get("modulo_testo", ""),
                st_dungeon_str
            ))

    def aggiungi_messaggio(self, avventura_id: str, ruolo: str, testo: str):
        if not testo or not testo.strip():
            return
        with self.conn:
            self.conn.execute(
                "INSERT INTO messaggi_storia (avventura_id, ruolo, testo) VALUES (?, ?, ?)",
                (avventura_id, ruolo, testo)
            )
            self.conn.execute(
                "UPDATE avventure SET data_aggiornamento = ? WHERE id = ?",
                (datetime.now().strftime("%d/%m/%Y %H:%M"), avventura_id)
            )

    def rimuovi_ultimo_messaggio(self, avventura_id: str):
        with self.conn:
            self.conn.execute("""
                DELETE FROM messaggi_storia
                WHERE id = (SELECT MAX(id) FROM messaggi_storia WHERE avventura_id = ?)
            """, (avventura_id,))

    def sostituisci_storia_compressa(self, avventura_id: str, nuova_storia: list):
        with self.conn:
            self.conn.execute("DELETE FROM messaggi_storia WHERE avventura_id = ?", (avventura_id,))
            for msg in nuova_storia:
                ruolo = msg.get("role", "user")
                parts = msg.get("parts", [])
                testo = parts[0].get("text", "") if parts else ""
                if testo.strip():
                    self.conn.execute(
                        "INSERT INTO messaggi_storia (avventura_id, ruolo, testo) VALUES (?, ?, ?)",
                        (avventura_id, ruolo, testo)
                    )

    def aggiungi_nota(self, avventura_id: str, testo_nota: str):
        with self.conn:
            self.conn.execute(
                "INSERT INTO diario_note (avventura_id, testo) VALUES (?, ?)",
                (avventura_id, testo_nota.strip())
            )

    def get_note_formattate(self, avventura_id: str) -> str:
        cur = self.conn.execute(
            "SELECT testo, timestamp FROM diario_note WHERE avventura_id = ? ORDER BY id ASC",
            (avventura_id,)
        )
        righe = [f"- [{r['timestamp']}] {r['testo']}" for r in cur.fetchall()]
        return "\n".join(righe) + ("\n" if righe else "")

    def elimina_avventura(self, avventura_id: str):
        with self.conn:
            self.conn.execute("DELETE FROM avventure WHERE id = ?", (avventura_id,))

    def carica_tutte_avventure(self) -> dict:
        avventure = {}
        cur = self.conn.execute("SELECT * FROM avventure ORDER BY id ASC")
        for r in cur.fetchall():
            adv_id = r["id"]
            msg_cur = self.conn.execute(
                "SELECT ruolo, testo FROM messaggi_storia WHERE avventura_id = ? ORDER BY id ASC",
                (adv_id,)
            )
            storia = []
            for mr in msg_cur.fetchall():
                if mr["testo"].strip():
                    storia.append({"role": mr["ruolo"], "parts": [{"text": mr["testo"]}]})

            try:
                party = json.loads(r["party_json"] or "[]")
            except Exception:
                party = []
            if not party:
                party = [r["eroe_nome"]]

            try:
                st_dungeon = json.loads(r["stato_dungeon_json"] or "{}")
            except Exception:
                st_dungeon = {}

            avventure[adv_id] = {
                "id": adv_id,
                "titolo": r["titolo"],
                "eroe": party[0],
                "party": party,
                "data": r["data_aggiornamento"],
                "storia": storia,
                "note": self.get_note_formattate(adv_id),
                "modulo_pdf": r["modulo_pdf"] or "",
                "modulo_testo": r["modulo_testo"] or "",
                "stato_dungeon": st_dungeon,
                "torcia_turni_rimasti": st_dungeon.get("torcia_turni", 6),
                "torcia_attiva": st_dungeon.get("torcia_attiva", True)
            }
        return avventure

    def statistiche_db(self) -> dict:
        pg_cnt = self.conn.execute("SELECT COUNT(*) FROM personaggi").fetchone()[0]
        adv_cnt = self.conn.execute("SELECT COUNT(*) FROM avventure").fetchone()[0]
        msg_cnt = self.conn.execute("SELECT COUNT(*) FROM messaggi_storia").fetchone()[0]
        note_cnt = self.conn.execute("SELECT COUNT(*) FROM diario_note").fetchone()[0]
        inv_cnt = self.conn.execute("SELECT COUNT(*) FROM inventario").fetchone()[0]
        size_kb = round(os.path.getsize(self.db_path) / 1024, 1) if not db_backend.is_remote(self.db_path) and os.path.exists(self.db_path) else None
        return {
            "file": "PostgreSQL remoto" if db_backend.is_remote(self.db_path) else self.db_path,
            "size_kb": size_kb,
            "personaggi": pg_cnt,
            "inventario": inv_cnt,
            "avventure": adv_cnt,
            "messaggi": msg_cnt,
            "note": note_cnt
        }

    def chiudi(self):
        self.conn.close()


# ==============================================================================
# FUNZIONI REGOLE BECMI
# ==============================================================================

def trova_dati_classe(nome_classe):
    for dati in BECMI_CLASSES.values():
        if dati["classe"].lower() == nome_classe.lower():
            return dati
    return BECMI_CLASSES["1"]


def calcola_thac0_e_attacco(classe, livello, immortale=False):
    if immortale:
        thac0 = max(2, 10 - (livello // 4))
    else:
        c = classe.lower()
        if c in ["guerriero", "paladino", "nano", "elfo", "halfling"]:
            step = (livello - 1) // 3
            thac0 = max(2, 19 - step * 2)
        elif c in ["chierico", "druido", "ladro"]:
            step = (livello - 1) // 4
            thac0 = max(4, 19 - step * 2)
        else:
            step = (livello - 1) // 5
            thac0 = max(7, 19 - step * 2)

    s_ca9 = max(2, thac0 - 9)
    s_ca5 = max(2, thac0 - 5)
    s_ca2 = max(2, thac0 - 2)
    s_ca0 = max(2, thac0)
    s_cam5 = max(2, thac0 + 5)
    return thac0, f"THAC0 {thac0} (CA 9: {s_ca9}+ | CA 5: {s_ca5}+ | CA 2: {s_ca2}+ | CA 0: {s_ca0}+ | CA -5: {s_cam5}+)"


def calcola_tiri_salvezza(classe, livello, immortale=False):
    if immortale:
        base = max(2, 7 - (livello // 6))
        return f"Morte/Veleno {base} | Bacchette {base+1} | Paralisi {base+1} | Soffio {base+2} | Incantesimi {base+2}"

    c = classe.lower()
    if c in ["nano", "halfling"]:
        fascia = min(3, (livello - 1) // 3)
        tab = [
            "Morte/Veleno 8 | Bacchette 9 | Paralisi 10 | Soffio 13 | Incantesimi 12",
            "Morte/Veleno 6 | Bacchette 7 | Paralisi 8 | Soffio 10 | Incantesimi 10",
            "Morte/Veleno 4 | Bacchette 5 | Paralisi 6 | Soffio 7 | Incantesimi 8",
            "Morte/Veleno 2 | Bacchette 3 | Paralisi 4 | Soffio 4 | Incantesimi 6"
        ]
        return tab[fascia]
    if c == "elfo":
        fascia = min(3, (livello - 1) // 3)
        tab = [
            "Morte/Veleno 12 | Bacchette 13 | Paralisi 13 | Soffio 15 | Incantesimi 15",
            "Morte/Veleno 10 | Bacchette 11 | Paralisi 11 | Soffio 13 | Incantesimi 12",
            "Morte/Veleno 8 | Bacchette 9 | Paralisi 9 | Soffio 10 | Incantesimi 10",
            "Morte/Veleno 6 | Bacchette 7 | Paralisi 7 | Soffio 8 | Incantesimi 8"
        ]
        return tab[fascia]
    if c in ["guerriero", "paladino"]:
        fascia = min(8, (livello - 1) // 3)
        tab = [
            "Morte/Veleno 12 | Bacchette 13 | Paralisi 14 | Soffio 15 | Incantesimi 16",
            "Morte/Veleno 10 | Bacchette 11 | Paralisi 12 | Soffio 13 | Incantesimi 14",
            "Morte/Veleno 8 | Bacchette 9 | Paralisi 10 | Soffio 10 | Incantesimi 12",
            "Morte/Veleno 6 | Bacchette 7 | Paralisi 8 | Soffio 8 | Incantesimi 10",
            "Morte/Veleno 5 | Bacchette 6 | Paralisi 7 | Soffio 7 | Incantesimi 9",
            "Morte/Veleno 4 | Bacchette 5 | Paralisi 6 | Soffio 6 | Incantesimi 8",
            "Morte/Veleno 3 | Bacchette 4 | Paralisi 5 | Soffio 5 | Incantesimi 7",
            "Morte/Veleno 2 | Bacchette 3 | Paralisi 4 | Soffio 4 | Incantesimi 6",
            "Morte/Veleno 2 | Bacchette 2 | Paralisi 3 | Soffio 3 | Incantesimi 5"
        ]
        return tab[fascia]
    if c in ["chierico", "druido"]:
        fascia = min(7, (livello - 1) // 4)
        tab = [
            "Morte/Veleno 11 | Bacchette 12 | Paralisi 14 | Soffio 16 | Incantesimi 15",
            "Morte/Veleno 9 | Bacchette 10 | Paralisi 12 | Soffio 14 | Incantesimi 12",
            "Morte/Veleno 7 | Bacchette 8 | Paralisi 10 | Soffio 12 | Incantesimi 10",
            "Morte/Veleno 6 | Bacchette 7 | Paralisi 9 | Soffio 10 | Incantesimi 9",
            "Morte/Veleno 5 | Bacchette 6 | Paralisi 8 | Soffio 9 | Incantesimi 8",
            "Morte/Veleno 4 | Bacchette 5 | Paralisi 7 | Soffio 8 | Incantesimi 7",
            "Morte/Veleno 3 | Bacchette 4 | Paralisi 6 | Soffio 7 | Incantesimi 6",
            "Morte/Veleno 2 | Bacchette 3 | Paralisi 5 | Soffio 6 | Incantesimi 5"
        ]
        return tab[fascia]
    if c == "ladro":
        fascia = min(7, (livello - 1) // 4)
        tab = [
            "Morte/Veleno 13 | Bacchette 14 | Paralisi 13 | Soffio 16 | Incantesimi 15",
            "Morte/Veleno 12 | Bacchette 13 | Paralisi 11 | Soffio 14 | Incantesimi 13",
            "Morte/Veleno 10 | Bacchette 11 | Paralisi 9 | Soffio 12 | Incantesimi 11",
            "Morte/Veleno 8 | Bacchette 9 | Paralisi 7 | Soffio 10 | Incantesimi 9",
            "Morte/Veleno 7 | Bacchette 8 | Paralisi 6 | Soffio 9 | Incantesimi 8",
            "Morte/Veleno 6 | Bacchette 7 | Paralisi 5 | Soffio 8 | Incantesimi 7",
            "Morte/Veleno 5 | Bacchette 6 | Paralisi 4 | Soffio 7 | Incantesimi 6",
            "Morte/Veleno 4 | Bacchette 5 | Paralisi 3 | Soffio 6 | Incantesimi 5"
        ]
        return tab[fascia]
    fascia = min(6, (livello - 1) // 5)
    tab = [
        "Morte/Veleno 13 | Bacchette 14 | Paralisi 13 | Soffio 16 | Incantesimi 15",
        "Morte/Veleno 11 | Bacchette 12 | Paralisi 11 | Soffio 14 | Incantesimi 12",
        "Morte/Veleno 9 | Bacchette 10 | Paralisi 9 | Soffio 12 | Incantesimi 10",
        "Morte/Veleno 7 | Bacchette 8 | Paralisi 7 | Soffio 10 | Incantesimi 8",
        "Morte/Veleno 6 | Bacchette 7 | Paralisi 6 | Soffio 8 | Incantesimi 7",
        "Morte/Veleno 5 | Bacchette 6 | Paralisi 5 | Soffio 7 | Incantesimi 6",
        "Morte/Veleno 4 | Bacchette 5 | Paralisi 4 | Soffio 6 | Incantesimi 5"
    ]
    return tab[fascia]


INCANTESIMI_DATABASE = {
    # Arcani 1° Cerchio (Mago / Elfo)
    "Dardo Incantato": {"cerchio": 1, "tipo": "arcano", "desc": "Colpisce infallibilmente infliggendo 1d6+1 PF di danno da forza pura."},
    "Sonno": {"cerchio": 1, "tipo": "arcano", "desc": "Addormenta magicamente 2d8 Dadi Vita di creature (max 4+1 DV ciascuna)."},
    "Scudo": {"cerchio": 1, "tipo": "arcano", "desc": "Imposta CA 2 contro proiettili, CA 4 in mischia e deflette i Dardi Incantati."},
    "Luce": {"cerchio": 1, "tipo": "arcano", "desc": "Illumina una sfera di 9m per 12 turni oppure acceca un nemico al volto."},
    "Individuazione del Magico": {"cerchio": 1, "tipo": "arcano", "desc": "Rivela aure magiche su oggetti o persone entro 18m per 2 turni."},
    "Charme": {"cerchio": 1, "tipo": "arcano", "desc": "Rende un umanoide obbediente e leale (TS contro Incantesimi)."},
    "Trattenere Portale": {"cerchio": 1, "tipo": "arcano", "desc": "Sigilla magicamente una porta chiusa per 2d6 turni."},
    "Lettura dei Linguaggi": {"cerchio": 1, "tipo": "arcano", "desc": "Permette di decifrare mappe, codici e lingue sconosciute per 2 turni."},

    # Arcani 2° Cerchio
    "Invisibilita": {"cerchio": 2, "tipo": "arcano", "desc": "Rende invisibile il bersaglio finche non attacca o lancia un incantesimo."},
    "Ragnatela": {"cerchio": 2, "tipo": "arcano", "desc": "Crea una barriera appiccicosa di ragnatele che intrappola i nemici."},
    "Immagine Speculare": {"cerchio": 2, "tipo": "arcano", "desc": "Crea 1d4 duplicati illusori del mago che sviano gli attacchi."},
    "Scassinare": {"cerchio": 2, "tipo": "arcano", "desc": "Spalanca serrature bloccate, forzieri sbarrati o sigillati magicamente."},
    "Levitazione": {"cerchio": 2, "tipo": "arcano", "desc": "Consente di levitare verticalmente fino a 6m al turno per 6 turni."},
    "Forza Fantasma": {"cerchio": 2, "tipo": "arcano", "desc": "Crea un'illusione realistica completa di forme, suoni e calore."},

    # Arcani 3° Cerchio
    "Palla di Fuoco": {"cerchio": 3, "tipo": "arcano", "desc": "Detonazione sferica di fuoco (1d6 PF per livello dell'incantatore, raggio 6m)."},
    "Fulmine": {"cerchio": 3, "tipo": "arcano", "desc": "Scarica elettrica rettilinea (1d6 PF per livello, linea di 18m)."},
    "Volare": {"cerchio": 3, "tipo": "arcano", "desc": "Concede il volo libero a 36m a turno per 1d6 turni + 1 turno per livello."},
    "Dissolvi Magie": {"cerchio": 3, "tipo": "arcano", "desc": "Neutralizza e dissolve incantesimi ed effetti magici attivi."},
    "Velocita": {"cerchio": 3, "tipo": "arcano", "desc": "Raddoppia attacchi e velocita di movimento per fino a 24 alleati."},
    "Respirare Sott'Acqua": {"cerchio": 3, "tipo": "arcano", "desc": "Permette a una creatura di respirare sott'acqua per 24 ore."},

    # Divini 1° Cerchio (Chierico / Druido / Paladino)
    "Cura Ferite Leggere": {"cerchio": 1, "tipo": "divino", "desc": "Ristabilisce 1d6+1 Punti Ferita a una creatura toccata (o ferisce non-morti)."},
    "Individuazione del Male": {"cerchio": 1, "tipo": "divino", "desc": "Rivela intenzioni malvagie e creature impure entro 36m per 6 turni."},
    "Purificare Cibo e Acqua": {"cerchio": 1, "tipo": "divino", "desc": "Rende commestibili e puri cibo avariato e acqua avvelenata per 12 persone."},
    "Rimuovi Paura": {"cerchio": 1, "tipo": "divino", "desc": "Dissipa il panico e dona +4 ai TS contro paura per 2 turni."},
    "Resistere al Freddo": {"cerchio": 1, "tipo": "divino", "desc": "Protegge da temperature polari e dona +2 ai TS contro gelo per 6 turni."},
    "Luce Divina": {"cerchio": 1, "tipo": "divino", "desc": "Sfera di luce sacra (raggio 9m) per 12 turni o acceca temporaneamente."},

    # Divini 2° Cerchio
    "Benedizione": {"cerchio": 2, "tipo": "divino", "desc": "Dona +1 al tiro per colpire e ai TS a tutto il gruppo per 6 turni."},
    "Trattieni Persone": {"cerchio": 2, "tipo": "divino", "desc": "Paralizza fino a 1d4 umanoidi per 9 turni (TS contro Incantesimi per negare)."},
    "Silenzio": {"cerchio": 2, "tipo": "divino", "desc": "Genera silenzio totale in un raggio di 4,5m, bloccando magie con componente verbale."},
    "Trova Trappole": {"cerchio": 2, "tipo": "divino", "desc": "Rivela trappole meccaniche o magiche entro 9m per 2 turni."},
    "Resistere al Fuoco": {"cerchio": 2, "tipo": "divino", "desc": "Protegge dal calore estremo e dona +2 ai TS contro fiamme per 6 turni."},
    "Serpente di Corda": {"cerchio": 2, "tipo": "divino", "desc": "Anima una corda che si innalza verso l'alto permettendo una rapida scalata."},

    # Divini 3° Cerchio
    "Cura Malattie": {"cerchio": 3, "tipo": "divino", "desc": "Guarisce istantaneamente qualsiasi malattia, infezione o parassita."},
    "Rimuovi Maledizione": {"cerchio": 3, "tipo": "divino", "desc": "Spezza maledizioni, sortilegi o anatemi gravanti su creature od oggetti."},
    "Luce Continua": {"cerchio": 3, "tipo": "divino", "desc": "Crea una fonte di luce perenne che dissipa ogni oscurita naturale o magica."},
    "Crescita Animale": {"cerchio": 3, "tipo": "divino", "desc": "Raddoppia taglia, PF e danni inflitti da un animale per 12 turni."}
}


def slot_incantesimi_per_cerchio(classe: str, livello: int, immortale: bool = False) -> dict:
    if immortale:
        return {}
    c = classe.lower()
    res = {}
    if c in ["mago", "elfo"]:
        max_cerchio = 5 if c == "elfo" else 9
        for cerchio in range(1, max_cerchio + 1):
            liv_sblocco = (cerchio - 1) * 2 + 1
            if livello >= liv_sblocco:
                res[cerchio] = min(6, 1 + (livello - liv_sblocco) // 2)
    elif c in ["chierico", "druido"]:
        for cerchio in range(1, 8):
            liv_sblocco = 2 if (cerchio == 1 and c == "chierico") else (1 if cerchio == 1 else cerchio * 2)
            if livello >= liv_sblocco:
                res[cerchio] = min(6, 1 + (livello - liv_sblocco) // 2)
    elif c == "paladino" and livello >= 9:
        for cerchio in range(1, 5):
            if livello >= 7 + cerchio * 2:
                res[cerchio] = min(3, 1 + (livello - (7 + cerchio * 2)) // 3)
    return res


def calcola_slot_o_abilita(classe, livello, immortale=False):
    if immortale:
        for l_min, l_max, rango, pp in RANGHI_IMMORTALI:
            if l_min <= livello <= l_max:
                return f"Rango Immortale: {rango} (Liv. Immortale {livello}) | Punti Potere (PP): {pp + (livello - l_min) * 25}"
        return f"Rango Immortale: Gerarca (Liv. {livello}) | PP: 1000+"

    c = classe.lower()
    if c in ["mago", "elfo", "chierico", "druido", "paladino"]:
        slots = slot_incantesimi_per_cerchio(classe, livello, immortale)
        if slots:
            tipo_label = "Arcani" if c in ["mago", "elfo"] else "Divini"
            s_str = " | ".join(f"{k}°:{v}" for k, v in sorted(slots.items()))
            return f"Slot Incantesimi {tipo_label}: {s_str}"
        if c == "chierico" and livello == 1:
            return "Slot Incantesimi Divini: Nessuno al 1° liv. (sblocca 1° cerchio al 2° liv.)"
        if c == "paladino" and livello < 9:
            return "Poteri Paladino: Imposizione mani, Individuazione male, Immunita malattie (Incantesimi dal 9° liv.)"
        return "Nessuno slot"

    if c == "ladro":
        scasso = min(99, 15 + (livello - 1) * 4)
        trappole = min(99, 10 + (livello - 1) * 4)
        borseggio = min(99, 20 + (livello - 1) * 4)
        silenzio = min(99, 20 + (livello - 1) * 4)
        nascondersi = min(99, 10 + (livello - 1) * 4)
        scalare = min(99, 87 + (livello - 1) // 2)
        ascoltare = min(95, 30 + (livello - 1) * 3)
        return (f"Abilita Ladro: Scassinare {scasso}% | Trappole {trappole}% | Borseggio {borseggio}% | "
                f"Muoversi Silenz. {silenzio}% | Nascondersi {nascondersi}% | Scalare {scalare}% | Ascoltare {ascoltare}%")

    if livello >= 9 and c in ["guerriero", "nano", "halfling"]:
        return "Privilegio Dominio/Roccaforte attivo (Companion): puo fondare una roccaforte e attrarre seguaci."
    return "Maestria nelle armi e combattimento corpo a corpo"


def fascia_regole_becmi(livello, immortale=False):
    if immortale:
        return "IMMORTAL (Scatola Oro - Piani Esterni, Sfere del Potere, Entita Cosmiche)"
    if livello <= 3:
        return "BASIC (Scatola Rossa - Dungeon sotterranei e Terre di Confine)"
    if livello <= 14:
        return "EXPERT (Scatola Blu - Esplorazione Terre Selvagge, Viaggi, Mostri Epici)"
    if livello <= 25:
        return "COMPANION (Scatola Verde - Domini, Roccaforti, Battaglie Campali, Piani Elementali)"
    return "MASTER (Scatola Nera - Artefatti, Maestria Gran Maestro, Quest per l'Immortalita)"


def prossima_soglia_pe(classe, livello, immortale=False):
    if immortale:
        return livello * 100000
    dati = trova_dati_classe(classe)
    xp_tab = dati["xp"]
    if livello >= len(xp_tab):
        return None
    return xp_tab[livello]


def sincronizza_statistiche_becmi(eroe):
    immortale = bool(eroe.get("immortale", False))
    livello = int(eroe.get("livello", 1))
    classe = eroe.get("classe", "Guerriero")
    thac0, att_str = calcola_thac0_e_attacco(classe, livello, immortale)
    eroe["thac0"] = thac0
    eroe["attacco"] = att_str
    eroe["ts"] = calcola_tiri_salvezza(classe, livello, immortale)
    eroe["abilita_classe"] = calcola_slot_o_abilita(classe, livello, immortale)
    eroe["fascia_becmi"] = fascia_regole_becmi(livello, immortale)
    eroe.setdefault("incantesimi_memorizzati", [])
    eroe.setdefault("slot_usati", {})
    if not eroe["incantesimi_memorizzati"]:
        c = classe.lower()
        if c == "mago":
            eroe["incantesimi_memorizzati"] = ["Dardo Incantato"]
        elif c == "elfo":
            eroe["incantesimi_memorizzati"] = ["Sonno"]
        elif c == "chierico" and livello >= 2:
            eroe["incantesimi_memorizzati"] = ["Cura Ferite Leggere"]
        elif c == "druido":
            eroe["incantesimi_memorizzati"] = ["Purificare Cibo e Acqua"]


def verifica_passaggio_livello(eroe):
    if eroe.get("immortale", False):
        return []
    dati = trova_dati_classe(eroe["classe"])
    xp_tab = dati["xp"]
    max_liv = dati["max_liv"]
    dv = dati["dado_vita"]
    pf_dopo_9 = dati["pf_dopo_9"]
    mod_cos = mod_caratteristica(eroe["costituzione"])

    avanzamenti = []
    while eroe["livello"] < max_liv:
        soglia = xp_tab[eroe["livello"]]
        if eroe["pe"] >= soglia:
            eroe["livello"] += 1
            nuovo_liv = eroe["livello"]
            if nuovo_liv <= 9:
                tiro = random.randint(1, dv)
                guadagno = max(1, tiro + mod_cos)
                dettaglio = f"1d{dv} ({tiro}) {mod_cos:+d} COS = +{guadagno} PF"
            else:
                guadagno = pf_dopo_9
                dettaglio = f"fisso post-9° liv. = +{guadagno} PF"
            eroe["pf_max"] += guadagno
            eroe["pf_attuali"] += guadagno
            avanzamenti.append((nuovo_liv, guadagno, dettaglio))
        else:
            break

    if avanzamenti:
        sincronizza_statistiche_becmi(eroe)
        suona("levelup")
        print(f"\n{VERDE}{GRASSETTO}*** PASSAGGIO DI LIVELLO BECMI! ***{RESET}")
        for liv, guad, dett in avanzamenti:
            print(f"{GIALLO}  -> {eroe['nome']} sale al Livello {liv} ({fascia_regole_becmi(liv)})! [{dett}]{RESET}")
        print(f"{CIANO}  -> Nuovi PF Max: {eroe['pf_max']} | {eroe['attacco']}{RESET}\n")
    return avanzamenti


CLASSI_BASE = BECMI_CLASSES

SCENARI_AVVENTURA = {
    "1": ("La Cripta Dimenticata", "Inizia l'avventura davanti all'ingresso semidistrutto di un'antica cripta nelle Terre di Confine al crepuscolo."),
    "2": ("La Rocca sulle Terre di Confine", "Inizia l'avventura nel cortile affollato della Rocca sulle Terre di Confine, pronto a esplorare le Caverne del Caos."),
    "3": ("Le Rovine del Castello Caldwell", "Inizia l'avventura davanti al cancello arrugginito di un maniero infestato appena acquistato da un mercante locale."),
    "4": ("L'Isola del Terrore", "Inizia l'avventura sulla spiaggia nebbiosa di un'isola inesplorata piena di rovine ciclopiche e creature preistoriche.")
}

EMPORIO_ITEMS = [
    ("1", "Torcia (set da 6)", 1, "equip", "6 Torce"),
    ("2", "Razioni di Ferro (7 giorni)", 15, "equip", "7 Razioni di Ferro"),
    ("3", "Pertica di legno (3 metri)", 1, "equip", "Pertica di legno (3m)"),
    ("4", "Corda (15 metri)", 1, "equip", "Corda (15m)"),
    ("5", "Acqua Santa (fiala)", 25, "equip", "Fiala di Acqua Santa"),
    ("6", "Olio per lanterna (fiala)", 2, "equip", "Fiala d'olio"),
    ("7", "Pozione di Guarigione (1d6+1 PF)", 50, "equip", "Pozione di Guarigione"),
    ("8", "Scudo (migliora CA di 1)", 10, "scudo", "Scudo"),
    ("9", "Corazza di Piastre (CA base 3)", 60, "armatura_3", "Corazza di Piastre"),
    ("10", "Spada Lunga (1d8 danni)", 10, "equip", "Spada Lunga (1d8)"),
    ("11", "Arco Corto + 20 Frecce", 30, "equip", "Arco Corto + 20 Frecce"),
    ("12", "Ingaggia Portatore di Torce (1 missione)", 5, "equip", "Gregario: Portatore di Torce"),
    ("13", "Ingaggia Uomo d'Arme (1 missione)", 15, "equip", "Gregario: Uomo d'Arme")
]

LOGO_INTRO = f"""{ROSSO}{GRASSETTO}
                 __====-_                                     _-====__
           _--^^^#####//      \\\\        {GIALLO}/\\       /\\{ROSSO}        //      \\\\#####^^^--_
        _-^##########// (    ) \\\\      {GIALLO}/  \\_____/  \\{ROSSO}      // (    ) \\\\##########^-_
       -############//  | \\/ |  \\\\    {GIALLO}|  {VERDE}<@>{GIALLO}   {VERDE}<@>{GIALLO}  |{ROSSO}    //  | \\/ |  \\\\############-
     _/############//    \\__/    \\\\  {GIALLO}/|      ^      |\\{ROSSO}  //    \\__/    \\\\############\\_
    /#############((              ))_{GIALLO} |   \\=====/   | {ROSSO}_((              ))#############\\
   -###############\\\\            //  {GIALLO}\\|    \\vvv/    |/  {ROSSO}\\\\            //###############-
  -#################\\\\          //    {GIALLO}\\      V      /    {ROSSO}\\\\          //#################-
   -###################\\\\      //      {GIALLO}\\__       __/      {ROSSO}\\\\      //###################-
     --##################\\\\  //           {GIALLO}\\     /           {ROSSO}\\\\  //##################--
        ---############## \\/               {GIALLO}\\___/             {ROSSO}\\/ ##############---
{GIALLO}                                    . - ~ ( 🔥 ) ~ - .
                                   (  ( ~~~~~~~~~~ )  )
{RESET}
  {GIALLO}{GRASSETTO} ___  _  _ ___   {ROSSO}   ___  ___   _ _____ ___  _        _     ___   ___  ___ ___   _   
  {GIALLO}|   \\| \\| |   \\  {ROSSO}  / __|/ __| /_\\_   _/ _ \\| |      /_\\   | _ \\ / _ \\/ __/ __| /_\\  
  {GIALLO}| |) | .` | |) | {ROSSO}  \\__ \\ (__ / _ \\| || (_) | |__   / _ \\  |   /| (_) \\__ \\__ \\/ _ \\ 
  {GIALLO}|___/|_|\\_|___/  {ROSSO}  |___/\\___/_/ \\_\\_| \\___/|____| /_/ \\_\\ |_|_\\ \\___/|___/___/_/ \\_\\
{RESET}
{GIALLO}{GRASSETTO}        ⚔️   E D I Z I O N E   F R A N K   M E N T Z E R   ( 1 9 8 3 )   ⚔️{RESET}
{CIANO}         Terminale AI Dungeon Master con Regole BECMI • SQLite • Audio & Mappe A4{RESET}
"""

HELP_TESTO = f"""{CIANO}{GRASSETTO}=== GUIDA AI COMANDI - D&D SCATOLA ROSSA (v9.1 SQLite / Party / LAN) ==={RESET}

{GIALLO}Azioni di Gruppo e Turni Multi-Giocatore:{RESET}
  {VERDE}/gruppo <azione>{RESET}         Invia un'azione collettiva per tutto il party in un colpo solo.
  {VERDE}/salta{RESET}                   Salta l'azione individuale di un personaggio (resta in guardia).
  {VERDE}/party{RESET}                   Mostra lo stato sintetico di tutti i membri del gruppo.

{GIALLO}Personaggio, Emporio e Diario:{RESET}
  {VERDE}/scheda{RESET} (o /scheda pdf)   Mostra la scheda o stampa la Scheda Ufficiale in PDF A4 ({SCHEDE_DIR}/).
  {VERDE}/inventario{RESET} (o /zaino)   Visualizza inventario, armi, armature, zaino e borsello monete.
  {VERDE}/emporio{RESET} (o /negozio)    Acquista armi, armature, torce, pozioni e gregari con le MO.
  {VERDE}/livello{RESET} (o /levelup)    Verifica passaggio di livello BECMI, soglia PE o Ascensione Immortale.
  {VERDE}/aggiorna{RESET}                Aggiorna manualmente livello, PF max, CA, MO o aggiungi oggetti.
  {VERDE}/nota <testo>{RESET}            Salva un appunto nel diario SQLite (/nota per leggere).

{GIALLO}Magia, Sopravvivenza e Riposo:{RESET}
  {VERDE}/magia{RESET} (o /incantesimi)  Mostra slot incantesimi e grimorio (Mago, Elfo, Chierico, Druido).
  {VERDE}/lancia <nome>{RESET} (o /cast) Lancia un incantesimo memorizzato consumando lo slot del cerchio.
  {VERDE}/riposo{RESET} (o /accampamento)Riposo breve (10m) o lungo (8h per recuperare 1d3 PF e tutti gli slot).
  {VERDE}/torcia{RESET} [on|off|auto]    Accende, spegne/riponi nello zaino o gestisce scorte (anche: "spegni torcia").
  {VERDE}/ambiente{RESET} [tipo]         Mostra o imposta l'ambiente (taverna, citta, dungeon, auto).
  {VERDE}/incontri{RESET} [raro|norm|off]Regola la frequenza incontri erranti dungeon (default: rari con cooldown).
  {VERDE}/modalita{RESET} [interattiva|classica] Alterna tra modalità 'interattiva' (chiamata dadi DM) e 'classica' (auto).

{GIALLO}Dadi e Strumenti di Esplorazione:{RESET}
  {VERDE}/d20{RESET} (o /d8+1, /2d6)     Tira dadi reali dal tuo PC e invia il risultato al Dungeon Master.
  {VERDE}/autodadi{RESET}                Attiva/disattiva la batteria completa di dadi reali ad ogni turno.
  {VERDE}/mappa{RESET} (o /mappa pdf)    Mostra mappa ASCII ed esporta PDF A4 con mappa tattica per la campagna.
  {VERDE}/suoni{RESET} (o /suoni test)   Attiva/disattiva gli effetti sonori o esegue il test audio retro.

{GIALLO}Database, Navigazione e Uscita:{RESET}
  {VERDE}/esporta{RESET} (o /esporta pdf) Esporta cronaca Markdown, mappa tattica o scheda in PDF A4.
  {VERDE}/modello{RESET} (o /ai)         Mostra o imposta il modello Gemini attivo e la catena di fallback.
  {VERDE}/sql{RESET} (o /db)             Mostra stato e statistiche del database ({"PostgreSQL remoto" if db_backend.is_remote(DB_FILE) else DB_FILE}).
  {VERDE}/storico{RESET}                 Mostra gli ultimi 3 turni dell'avventura corrente.
  {VERDE}/riassunto{RESET}               Comprime la memoria per mantenere veloce l'IA nelle partite lunghe.
  {VERDE}/stop{RESET} (o /menu, /0)      Salva l'avventura e torna al Menu Principale.
  {VERDE}/chiudi{RESET} (o /esci)        Chiude il database ed esce completamente dal programma.
  {VERDE}/help{RESET} (o /help pdf)      Mostra la guida comandi (o rigenera il Manuale PDF A4 aggiornato).
"""


def mod_caratteristica(val):
    if val <= 3:
        return -3
    if val <= 5:
        return -2
    if val <= 8:
        return -1
    if val <= 12:
        return 0
    if val <= 15:
        return 1
    if val <= 17:
        return 2
    return 3


def sintetizza_suoni_mancanti():
    os.makedirs(SUONI_DIR, exist_ok=True)
    sample_rate = 22050

    def _scrivi_wav(percorso, campioni):
        try:
            with wave.open(percorso, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(b''.join(struct.pack('<h', max(-32767, min(32767, int(s)))) for s in campioni))
        except Exception:
            pass

    # 1. Dado (rotolio percussivo dadi)
    f_dado = os.path.join(SUONI_DIR, "dado.wav")
    if not os.path.exists(f_dado):
        samples_dado = []
        for colpo in range(5):
            dur = 0.035
            n = int(sample_rate * dur)
            freq = 600 + random.randint(-150, 200)
            for i in range(n):
                t = i / sample_rate
                env = math.exp(-i / (n * 0.3))
                noise = (random.random() * 2 - 1) * 0.7
                sine = math.sin(2 * math.pi * freq * t) * 0.3
                samples_dado.append((noise + sine) * env * 22000)
            samples_dado.extend([0] * int(sample_rate * (0.02 + colpo * 0.015)))
        _scrivi_wav(f_dado, samples_dado)

    # 2. Critico (arpeggio trionfale C5 -> E5 -> G5 -> C6)
    f_critico = os.path.join(SUONI_DIR, "critico.wav")
    if not os.path.exists(f_critico):
        note = [523.25, 659.25, 783.99, 1046.50]
        samples = []
        for idx, f in enumerate(note):
            dur = 0.08 if idx < 3 else 0.22
            n = int(sample_rate * dur)
            for i in range(n):
                t = i / sample_rate
                env = (1.0 - i / n) ** 1.2
                onda = 0.5 if math.sin(2 * math.pi * f * t) > 0 else -0.5
                onda += 0.25 * math.sin(4 * math.pi * f * t)
                samples.append(onda * env * 24000)
        _scrivi_wav(f_critico, samples)

    # 3. Fallimento (jingle dissonante discendente Eb4 -> D4 -> Db4 -> C4)
    f_fall = os.path.join(SUONI_DIR, "fallimento.wav")
    if not os.path.exists(f_fall):
        note = [311.13, 293.66, 277.18, 261.63]
        samples = []
        for idx, f in enumerate(note):
            dur = 0.10 if idx < 3 else 0.28
            n = int(sample_rate * dur)
            for i in range(n):
                t = i / sample_rate
                env = (1.0 - i / n)
                onda = 0.5 if math.sin(2 * math.pi * f * t) > 0 else -0.5
                samples.append(onda * env * 22000)
        _scrivi_wav(f_fall, samples)

    # 4. Danno (impatto / sferzata sorda con rumore)
    f_danno = os.path.join(SUONI_DIR, "danno.wav")
    if not os.path.exists(f_danno):
        samples = []
        n = int(sample_rate * 0.22)
        for i in range(n):
            t = i / sample_rate
            env = math.exp(-i / (n * 0.25))
            f = max(60, 280 - i * 0.25)
            onda = 0.4 if math.sin(2 * math.pi * f * t) > 0 else -0.4
            noise = (random.random() * 2 - 1) * 0.6
            samples.append((onda + noise) * env * 26000)
        _scrivi_wav(f_danno, samples)

    # 5. Tesoro (doppio squillo monete d'oro B5 -> E6)
    f_tesoro = os.path.join(SUONI_DIR, "tesoro.wav")
    if not os.path.exists(f_tesoro):
        note = [987.77, 1318.51]
        samples = []
        for f in note:
            dur = 0.16
            n = int(sample_rate * dur)
            for i in range(n):
                t = i / sample_rate
                env = math.exp(-i / (n * 0.35))
                onda = math.sin(2 * math.pi * f * t) + 0.3 * math.sin(4 * math.pi * f * t)
                samples.append(onda * env * 22000)
            samples.extend([0] * int(sample_rate * 0.03))
        _scrivi_wav(f_tesoro, samples)

    # 6. Level Up (fanfara trionfale BECMI)
    f_lvl = os.path.join(SUONI_DIR, "levelup.wav")
    if not os.path.exists(f_lvl):
        note = [523.25, 659.25, 783.99, 1046.50, 1318.51]
        samples = []
        for idx, f in enumerate(note):
            dur = 0.09 if idx < 4 else 0.35
            n = int(sample_rate * dur)
            for i in range(n):
                t = i / sample_rate
                env = (1.0 - i / n) ** 0.8
                onda = 0.5 if math.sin(2 * math.pi * f * t) > 0 else -0.5
                onda += 0.25 * math.sin(3 * math.pi * f * t)
                samples.append(onda * env * 25000)
        _scrivi_wav(f_lvl, samples)

    # 7. Intro (accordo arpeggiato fantasy)
    f_intro = os.path.join(SUONI_DIR, "intro.wav")
    if not os.path.exists(f_intro):
        note = [220.00, 329.63, 440.00, 554.37, 659.25]
        samples = []
        for idx, f in enumerate(note):
            dur = 0.12 if idx < 4 else 0.40
            n = int(sample_rate * dur)
            for i in range(n):
                t = i / sample_rate
                env = math.exp(-i / (n * 0.4))
                onda = math.sin(2 * math.pi * f * t) + 0.25 * math.sin(4 * math.pi * f * t)
                samples.append(onda * env * 20000)
        _scrivi_wav(f_intro, samples)

    # 8. Magia (arpeggio scintillante ascendente)
    f_magia = os.path.join(SUONI_DIR, "magia.wav")
    if not os.path.exists(f_magia):
        notes = [440.0, 554.37, 659.25, 880.0, 1108.73, 1318.51]
        samples = []
        for idx, f in enumerate(notes):
            dur = 0.06 if idx < len(notes)-1 else 0.25
            n = int(sample_rate * dur)
            for i in range(n):
                t = i / sample_rate
                env = math.exp(-i / (n * 0.45))
                onda = math.sin(2 * math.pi * f * t) + 0.35 * math.sin(4 * math.pi * f * t) + 0.15 * math.sin(6 * math.pi * f * t)
                samples.append(onda * env * 22000)
        _scrivi_wav(f_magia, samples)


def riproduci_file_audio(percorso):
    if not os.path.exists(percorso):
        return False
    players = [
        ["paplay"],
        ["pw-play"],
        ["aplay", "-q"],
        ["play", "-q"],
        ["mpg123", "-q"]
    ]
    for p in players:
        if shutil.which(p[0]):
            try:
                subprocess.Popen(p + [percorso], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                continue
    return False


def suona(tipo):
    if not SUONI_ATTIVI:
        return

    def _esegui():
        file_audio = os.path.join(SUONI_DIR, f"{tipo}.wav")
        if os.path.exists(file_audio):
            if riproduci_file_audio(file_audio):
                return
        ripetizioni = {"critico": 3, "levelup": 3, "magia": 2, "danno": 2, "fallimento": 2, "tesoro": 1}.get(tipo, 1)
        for _ in range(ripetizioni):
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(0.12)

    threading.Thread(target=_esegui, daemon=True).start()


def testa_effetti_sonori():
    sintetizza_suoni_mancanti()
    print(f"\n{CIANO}{GRASSETTO}=== TEST EFFETTI SONORI (Cartella: {SUONI_DIR}/) ==={RESET}")
    lista = [
        ("dado", "🎲 Rotolio Dadi"),
        ("critico", "🌟 20 Naturale / Colpo Critico"),
        ("fallimento", "💀 1 Naturale / Fallimento Critico"),
        ("danno", "⚔️ Danno / Ferita Subita"),
        ("tesoro", "💰 Monete / Bottino Emporio"),
        ("levelup", "🏆 Passaggio di Livello BECMI"),
        ("intro", "🏰 Introduzione Scena / Avventura"),
        ("magia", "🔮 Incantesimo / Magia Lanciata")
    ]
    for tipo, desc in lista:
        print(f"  -> Riproduco: {GIALLO}{desc}{RESET} ({tipo}.wav)...")
        suona(tipo)
        time.sleep(0.65)
    print(f"\n{VERDE}Test completato! Puoi sostituire i file .wav in '{SUONI_DIR}/' con i tuoi suoni preferiti.{RESET}\n")


def valuta_reazione_mostro(tot2d6: int) -> str:
    if tot2d6 <= 2:
        return "2 (Attacco Immediato/Feroce)"
    elif tot2d6 <= 5:
        return f"{tot2d6} (Ostile e Minaccioso)"
    elif tot2d6 <= 8:
        return f"{tot2d6} (Incerto/Esitante)"
    elif tot2d6 <= 11:
        return f"{tot2d6} (Neutrale/Cauto - Possibile Dialogo)"
    else:
        return "12 (Amichevole/Aperto a Negoziazione)"


def genera_batteria_dadi(nome_pg=""):
    d20_pg = random.randint(1, 20)
    d20_ts = random.randint(1, 20)
    d20_dm = random.randint(1, 20)
    d6_espl = random.randint(1, 6)
    d6_inc = random.randint(1, 6)
    d6_a = random.randint(1, 6)
    d6_b = random.randint(1, 6)
    d8 = random.randint(1, 8)
    d4 = random.randint(1, 4)
    d100 = random.randint(1, 100)
    tot_2d6 = d6_a + d6_b
    d6_m1 = random.randint(1, 6)
    d6_m2 = random.randint(1, 6)
    morale_2d6 = d6_m1 + d6_m2

    reaz_str = valuta_reazione_mostro(tot_2d6)
    pref = f"TIRI REALI {nome_pg}" if nome_pg else "TIRI REALI"
    riga_visibile = (
        f"[{pref} -> Attacco/Prova 1d20: {d20_pg} | TS 1d20: {d20_ts} | "
        f"Esplorazione 1d6: {d6_espl} | Incontro 1d6: {d6_inc} | "
        f"Reazione Mostri 2d6: {tot_2d6} ({reaz_str}) | Morale Mostri 2d6: {morale_2d6} | "
        f"Danni 1d8: {d8}, 1d6: {d6_a}, 1d4: {d4} | DM 1d20: {d20_dm} | d%: {d100}]"
    )
    return {
        "d20": d20_pg,
        "d20_ts": d20_ts,
        "d20_dm": d20_dm,
        "1d6": d6_espl,
        "1d6_inc": d6_inc,
        "2d6": tot_2d6,
        "morale": morale_2d6,
        "1d8": d8,
        "1d4": d4,
        "d100": d100,
        "testo": riga_visibile
    }


def ottieni_ip_locale():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def estrai_testo_pdf(percorso_pdf):
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", percorso_pdf, "-"],
            capture_output=True, text=True, timeout=30
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(percorso_pdf)
        pagine = [p.extract_text() or "" for p in reader.pages]
        testo = "\n".join(pagine).strip()
        if testo:
            return testo
    except Exception:
        pass
    return ""


def prepara_contenuto_modulo(percorso_pdf):
    testo = estrai_testo_pdf(percorso_pdf)
    if len(testo) >= 400:
        return testo[:180000], None
    if os.path.getsize(percorso_pdf) <= 18 * 1024 * 1024:
        with open(percorso_pdf, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return "", b64
    return testo, None


def elenca_moduli_pdf():
    os.makedirs(MODULI_DIR, exist_ok=True)
    return sorted([
        f for f in os.listdir(MODULI_DIR)
        if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(MODULI_DIR, f))
    ])


def normalizza_personaggio_json(chiave, item):
    if not isinstance(item, dict):
        item = {}
    base = CLASSI_BASE["1"]
    nome = item.get("nome") or item.get("name") or str(chiave)
    car = item.get("caratteristiche") if isinstance(item.get("caratteristiche"), dict) else {}
    item["nome"] = nome
    item.setdefault("classe", base["classe"])
    item.setdefault("razza", "Umano")
    item.setdefault("livello", 1)
    item.setdefault("allineamento", "Legale")
    item.setdefault("forza", car.get("FOR", base["forza"]))
    item.setdefault("intelligenza", car.get("INT", base["intelligenza"]))
    item.setdefault("saggezza", car.get("SAG", base["saggezza"]))
    item.setdefault("destrezza", car.get("DES", base["destrezza"]))
    item.setdefault("costituzione", car.get("COS", base["costituzione"]))
    item.setdefault("carisma", car.get("CAR", base["carisma"]))
    item.setdefault("pf_attuali", 8)
    item.setdefault("pf_max", 8)
    item.setdefault("ca", 3)
    if not isinstance(item.get("equip"), list):
        item["equip"] = list(base["equip"])
    item.setdefault("mo", 15)
    item.setdefault("pe", 0)
    item.setdefault("immortale", False)
    sincronizza_statistiche_becmi(item)
    return nome, item


def carica_json_grezzo(percorso, default):
    if os.path.exists(percorso):
        try:
            with open(percorso, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def migra_json_in_sqlite(db: DnDDatabase):
    os.makedirs(MODULI_DIR, exist_ok=True)
    personaggi = db.carica_tutti_personaggi()
    avventure = db.carica_tutte_avventure()

    if personaggi or avventure:
        return avventure, personaggi

    print(f"{CIANO}Inizializzazione database SQLite ({DB_FILE}) e migrazione salvataggi esistenti...{RESET}")
    raw_pg = carica_json_grezzo(CHARACTERS_FILE, {})
    if isinstance(raw_pg, dict) and raw_pg:
        for k, v in raw_pg.items():
            _, pg_norm = normalizza_personaggio_json(k, v)
            db.salva_personaggio(pg_norm)
    else:
        _, eroe_default = normalizza_personaggio_json("Valen di Corvobianco", {})
        db.salva_personaggio(eroe_default)

    personaggi = db.carica_tutti_personaggi()

    raw_adv = carica_json_grezzo(ADVENTURES_FILE, {})
    if isinstance(raw_adv, dict) and raw_adv:
        for k, item in raw_adv.items():
            if not isinstance(item, dict):
                continue
            adv_id = item.get("id") or str(k)
            eroe_nome = item.get("eroe") or item.get("eroe_nome") or "Valen di Corvobianco"
            if eroe_nome not in personaggi:
                _, nuovo_p = normalizza_personaggio_json(eroe_nome, {})
                db.salva_personaggio(nuovo_p)
                personaggi = db.carica_tutti_personaggi()

            adv_record = {
                "id": adv_id,
                "titolo": item.get("titolo") or "Avventura Migrata",
                "eroe": eroe_nome,
                "party": [eroe_nome],
                "data": item.get("data") or item.get("ultimo_accesso") or datetime.now().strftime("%d/%m/%Y %H:%M"),
                "modulo_pdf": item.get("modulo_pdf", ""),
                "modulo_testo": item.get("modulo_testo", "")
            }
            db.salva_metadati_avventura(adv_record)

            for msg in item.get("storia", []):
                if isinstance(msg, dict):
                    ruolo = msg.get("role", "user")
                    parts = msg.get("parts", [])
                    testo = parts[0].get("text", "") if parts and isinstance(parts[0], dict) else ""
                    if testo.strip():
                        db.aggiungi_messaggio(adv_id, ruolo, testo)

            note_vecchie = item.get("note", "")
            if isinstance(note_vecchie, str) and note_vecchie.strip():
                for riga in note_vecchie.strip().splitlines():
                    db.aggiungi_nota(adv_id, riga.lstrip("- "))

    elif os.path.exists(LEGACY_SAVE):
        vecchia_storia = carica_json_grezzo(LEGACY_SAVE, [])
        if vecchia_storia:
            adv_record = {
                "id": "adv_legacy_1",
                "titolo": "La Cripta Dimenticata",
                "eroe": "Valen di Corvobianco",
                "party": ["Valen di Corvobianco"],
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "modulo_pdf": "",
                "modulo_testo": ""
            }
            db.salva_metadati_avventura(adv_record)
            for msg in vecchia_storia:
                if isinstance(msg, dict) and msg.get("parts"):
                    testo = msg["parts"][0].get("text", "")
                    if testo.strip():
                        db.aggiungi_messaggio("adv_legacy_1", msg.get("role", "user"), testo)
            if os.path.exists(LEGACY_DIARY):
                with open(LEGACY_DIARY, "r", encoding="utf-8") as f:
                    for riga in f.read().splitlines():
                        if riga.strip():
                            db.aggiungi_nota("adv_legacy_1", riga.lstrip("- "))

    time.sleep(0.5)
    return db.carica_tutte_avventure(), db.carica_tutti_personaggi()


def _conteggia_scorta(equip: list, pattern: str) -> int:
    totale = 0
    for item in equip:
        if not re.search(pattern, item, re.IGNORECASE):
            continue
        quantita = re.search(rf"(\d+)\s+{pattern}\b", item, re.IGNORECASE)
        totale += int(quantita.group(1)) if quantita else 1
    return totale


def costruisci_system_prompt(eroi_party: list, avventura=None):
    blocco_modulo = ""
    if avventura:
        mod_nome = avventura.get("modulo_pdf", "")
        mod_testo = avventura.get("modulo_testo", "")
        if mod_nome or mod_testo:
            blocco_modulo = (
                f"\nMODULO UFFICIALE CARICATO ({mod_nome}): "
                "DEVI condurre l'avventura seguendo fedelmente stanze numerate, trappole, mostri, tesori, PNG e trama del modulo seguente. "
                "ANTI-SPOILER ASSOLUTO: NON rivelare mai ai giocatori il contenuto di stanze non ancora esplorate, porte segrete non trovate o trappole non scoperte!\n"
            )
            if mod_testo:
                blocco_modulo += f"--- TESTO DEL MODULO ---\n{mod_testo}\n--- FINE MODULO ---\n"

    schede_txt = []
    riquadri_esempio = []
    livello_max = 1
    fascia_attiva = "BASIC (Scatola Rossa)"

    for eroe in eroi_party:
        sincronizza_statistiche_becmi(eroe)
        if eroe["livello"] >= livello_max:
            livello_max = eroe["livello"]
            fascia_attiva = eroe["fascia_becmi"]
        equip_str = ", ".join(eroe["equip"])
        titolo_livello = (
            f"Immortale Livello {eroe['livello']}"
            if eroe.get("immortale")
            else f"{eroe['classe']} Livello {eroe['livello']}"
        )
        prep_spells = eroe.get("incantesimi_memorizzati", [])
        spells_str = f" | Incantesimi preparati oggi: {', '.join(prep_spells)}" if prep_spells else ""
        torce = _conteggia_scorta(eroe["equip"], r"torc(?:ia|e)")
        razioni = _conteggia_scorta(eroe["equip"], r"razion(?:e|i)")
        frecce = _conteggia_scorta(eroe["equip"], r"frecce")
        schede_txt.append(
            f"- EROE: {eroe['nome']} ({titolo_livello}, {eroe['allineamento']}) | "
            f"FOR {eroe['forza']} ({mod_caratteristica(eroe['forza']):+d}), "
            f"INT {eroe['intelligenza']} ({mod_caratteristica(eroe['intelligenza']):+d}), "
            f"SAG {eroe['saggezza']} ({mod_caratteristica(eroe['saggezza']):+d}), "
            f"DES {eroe['destrezza']} ({mod_caratteristica(eroe['destrezza']):+d}), "
            f"COS {eroe['costituzione']} ({mod_caratteristica(eroe['costituzione']):+d}), "
            f"CAR {eroe['carisma']} ({mod_caratteristica(eroe['carisma']):+d}) | "
            f"PF: {eroe['pf_attuali']}/{eroe['pf_max']}, CA: {eroe['ca']} | "
            f"{eroe['attacco']} | TS: {eroe['ts']} | {eroe['abilita_classe']}{spells_str} | "
            f"Equip: {equip_str} | MO: {eroe['mo']} | PE: {eroe['pe']}"
        )
        riquadri_esempio.append(
            f"[{eroe['nome']} | PF: attuali/{eroe['pf_max']} | CA: {eroe['ca']} | Torce: {torce} | Razioni: {razioni} | Frecce: {frecce} | MO: n | PE: attuali]"
        )

    blocco_party = "\n".join(schede_txt)
    blocco_riquadri = "\n".join(riquadri_esempio)

    modalita = "interattiva"
    if avventura and isinstance(avventura, dict):
        st_d = avventura.get("stato_dungeon") or {}
        modalita = st_d.get("modalita_gioco", MODALITA_GIOCO)
    else:
        modalita = MODALITA_GIOCO

    if modalita == "interattiva":
        blocco_regole_dadi = (
            "REGOLE OBBLIGATORIE SUI TIRI DI DADO (MODALITÀ INTERATTIVA - NON DEROGABILE): "
            "1. REGOLA DELLA CHIAMATA DEI DADI (INTERACTIVE MODE): Quando un eroe compie un'azione incerta che richiede una prova "
            "(attacco contro un bersaglio, tiro salvezza, prova di caratteristica, cercare trappole o porte segrete, scassinare, ascoltare, percepire, ecc.), "
            "TU COME DUNGEON MASTER NON DEVI MAI TIRARE IL DADO PER LUI NÉ RISOLVERE L'AZIONE AL POSTO SUO! "
            "Descrivi la situazione fino al momento culminante, fermati e CHIEDI ESPLICITAMENTE al giocatore di tirare il dado usando la formula: "
            "[CHIAMATA DADO: NomePG - Tira <formula> per <scopo> (vs Soglia/CA <valore>)]. "
            "Esempi: "
            "[CHIAMATA DADO: Valen - Tira 1d20 per Colpire con Spada Lunga (vs CA 6)] "
            "[CHIAMATA DADO: Morgana - Tira 1d20 per Tiro Salvezza contro Veleno (vs Soglia 14)] "
            "[CHIAMATA DADO: Robin - Tira 1d100 per Trovare/Disattivare Trappole (vs 20%)] "
            "[CHIAMATA DADO: Darok - Tira 1d6 per Ascoltare Dietro la Porta (vs 1-2 su 1d6)]. "
            "Dopo la chiamata fermati e attendi il tiro del giocatore! "
            "2. RISOLUZIONE DEI TIRI DEI GIOCATORI: Quando il giocatore comunica il suo tiro reale "
            "(es. [TIRO REALE: 16], o /d20 -> 16, o 'ho fatto 16'), PRENDI QUEL VALORE REALE, applica i modificatori e mostra il calcolo: "
            "[NomePG - Tipo Prova: Dado +/- mod = Totale vs Soglia -> Esito], e narra le conseguenze! "
            "Se l'attacco è andato a segno (Colpito!), NON tirare i danni al posto suo: chiedi subito il tiro per i danni: "
            "[CHIAMATA DADO: NomePG - Tira <dado danni> per i Danni] e attendi la risposta! "
            "3. TIRI DEI MOSTRI E PNG: I mostri e i pericoli ambientali vengono tirati direttamente da te (DM) sempre indicando la formula: "
            "[Goblin #1 - Attacco: 1d20 -> 13 + 0 = 13 vs CA 3 -> Mancato!]. "
            "4. Se e solo se il giocatore ti chiede esplicitamente 'tira tu DM' o include già nel suo messaggio un tiro reale per quell'azione, "
            "puoi risolvere direttamente l'azione riportando il calcolo tra parentesi quadre. "
        )
    else:
        blocco_regole_dadi = (
            "REGOLE OBBLIGATORIE SUI TIRI DI DADO (MODALITÀ CLASSICA / FAST): "
            "1. REGOLA D'ORO DEI DADI: OGNI SINGOLA situazione, azione incerta, esplorazione, prova o pericolo DEVE mostrare esplicitamente "
            "il lancio dei dadi e il calcolo completo nel testo usando il formato [NomePG - Tipo Prova: Dado -> risultato +/- mod = Totale vs Soglia -> Esito]. "
            "2. Se il messaggio dei giocatori include [TIRI REALI ... -> ...], DEVI obbligatoriamente usare quei valori reali per le prove di ciascun personaggio, "
            "riportandoli comunque in chiaro tra parentesi quadre [...] nella tua narrazione! "
        )

    return (
        "Agisci come un Dungeon Master esperto di Dungeons & Dragons Edizione Mentzer / BECMI completa "
        "(Basic, Expert, Companion, Master, Immortal - Livelli 1-36 e Ranghi Immortali) in lingua italiana. "
        f"FASCIA DI REGOLAMENTO ATTIVA: {fascia_attiva}. "
        f"GRUPPO DI AVVENTURIERI ({len(eroi_party)} personaggi):\n{blocco_party}\n"
        "SCORTE INVENTARIO: i conteggi Torce, Razioni e Frecce nei riquadri sono i valori aggiornati e autorevoli. "
        "Riportali senza ricalcolarli o sottrarli di nuovo in base all'azione di questo turno: il codice gestisce i consumi. "
        "La torcia attiva e il suo timer sono separati dalle torce di scorta nello zaino; non inventare consumi o quantità.\n"
        f"{blocco_regole_dadi}"
        "3. Risolvi le azioni di tutti i membri del party nel round (sia che agiscano individualmente sia come azione di gruppo). "
        "4. A 0 PF un personaggio muore. Procedi a Turni da 10 minuti ESCLUSIVAMENTE nei dungeon e sotterranei bui (dove le torce durano 6 turni). In taverne, locande, città, botteghe o all'aperto di giorno c'è luce naturale o delle lanterne: le torce NON servono, NON si consumano e NON devono essere accese! 1 MO recuperata = 1 PE. Se il gruppo finisce al buio senza torce in un dungeon buio, applica penalita di -4 al tiro per colpire e alla CA. "
        "5. Quando compaiono mostri o creature, rispetta il tiro [Reazione Mostri 2d6]: con esito incerto, neutrale o amichevole NON attaccano a testa bassa ma valutano il gruppo, parlano o accettano tributi/cibo. Con perdite gravi, valuta il [Morale Mostri 2d6]. "
        "6. Chiudi SEMPRE ogni messaggio con una riga vuota, poi TUTTI i riquadri aggiornati del party (una riga per ogni personaggio) e infine la domanda:\n"
        f"{blocco_riquadri}\nCosa fate?"
        + blocco_modulo
    )


def aggiorna_party_da_riquadro(eroi_party: list, testo_dm: str):
    for eroe in eroi_party:
        nome_esc = re.escape(eroe["nome"])
        pat_nome = rf"\[\s*{nome_esc}\s*\|\s*PF:\s*(-?\d+)/(\d+)\s*\|\s*CA:\s*(-?\d+).*?\|\s*MO:\s*(\d+)\s*\|\s*PE:\s*(\d+)\]"
        m = re.search(pat_nome, testo_dm, re.IGNORECASE)
        if not m and len(eroi_party) == 1:
            m = re.search(r"\[PF:\s*(-?\d+)/(\d+)\s*\|\s*CA:\s*(-?\d+).*?\|\s*MO:\s*(\d+)\s*\|\s*PE:\s*(\d+)\]", testo_dm)
        if m:
            vecchi_pf = eroe["pf_attuali"]
            vecchie_mo = eroe["mo"]
            eroe["pf_attuali"] = int(m.group(1))
            eroe["pf_max"] = int(m.group(2))
            eroe["ca"] = int(m.group(3))
            eroe["mo"] = int(m.group(4))
            eroe["pe"] = int(m.group(5))
            if eroe["pf_attuali"] < vecchi_pf:
                suona("danno")
            elif eroe["mo"] > vecchie_mo:
                suona("tesoro")
            verifica_passaggio_livello(eroe)

    if "20 ->" in testo_dm or "20 naturale" in testo_dm.lower() or "critico" in testo_dm.lower():
        suona("critico")
    elif "1 ->" in testo_dm or "1 naturale" in testo_dm.lower() or "fallimento critico" in testo_dm.lower():
        suona("fallimento")


def mostra_scheda(eroe):
    sincronizza_statistiche_becmi(eroe)
    imm = eroe.get("immortale", False)
    soglia = prossima_soglia_pe(eroe["classe"], eroe["livello"], imm)
    soglia_str = f" / {soglia} PE" if soglia else " (Livello Massimo Classe)"
    titolo_cl = f"IMMORTALE (Liv. {eroe['livello']})" if imm else f"{eroe['classe']} Livello {eroe['livello']}"
    print(f"{CIANO}{GRASSETTO}=== SCHEDA PERSONAGGIO: {eroe['nome'].upper()} ==={RESET}")
    print(f"Classe/Rango: {titolo_cl} | Allineamento: {eroe['allineamento']} | PE: {eroe['pe']}{soglia_str}")
    print(f"{MAGENTA}Regolamento attivo:{RESET} {eroe['fascia_becmi']}")
    print(f"Forza: {eroe['forza']} ({mod_caratteristica(eroe['forza']):+d}) | Intelligenza: {eroe['intelligenza']} ({mod_caratteristica(eroe['intelligenza']):+d}) | Saggezza: {eroe['saggezza']} ({mod_caratteristica(eroe['saggezza']):+d})")
    print(f"Destrezza: {eroe['destrezza']} ({mod_caratteristica(eroe['destrezza']):+d}) | Costituzione: {eroe['costituzione']} ({mod_caratteristica(eroe['costituzione']):+d}) | Carisma: {eroe['carisma']} ({mod_caratteristica(eroe['carisma']):+d})")
    print(f"Punti Ferita: {eroe['pf_attuali']}/{eroe['pf_max']} | Classe Armatura (CA): {eroe['ca']} | Monete d'Oro: {eroe['mo']}")
    print(f"\n{GIALLO}Tiri per Colpire:{RESET} {eroe['attacco']}")
    print(f"{GIALLO}Tiri Salvezza:{RESET} {eroe['ts']}")
    print(f"{GIALLO}Capacita & Incantesimi:{RESET} {eroe['abilita_classe']}")
    print(f"\n{GIALLO}Equipaggiamento e Tesori:{RESET}")
    for item in eroe["equip"]:
        print(f"  - {item}")
    prep = eroe.get("incantesimi_memorizzati", [])
    if prep:
        print(f"\n{MAGENTA}{GRASSETTO}Incantesimi Preparati per la Giornata:{RESET} {', '.join(prep)}")


def categorizza_inventario(equip: list):
    armi = []
    armature = []
    zaino = []
    parole_armi = ["spada", "pugnale", "arco", "frecc", "ascia", "martello", "dardo", "lancia", "mazza", "bastone", "alabarda", "balestra", "quadrell", "fionda"]
    parole_armature = ["corazza", "armatura", "scudo", "maglia", "piastre", "cuoio", "elmo"]
    for item in equip:
        item_lower = item.lower()
        if any(w in item_lower for w in parole_armi):
            armi.append(item)
        elif any(w in item_lower for w in parole_armature):
            armature.append(item)
        else:
            zaino.append(item)
    return armi, armature, zaino


def mostra_inventario(eroe: dict):
    sincronizza_statistiche_becmi(eroe)
    armi, armature, zaino = categorizza_inventario(eroe.get("equip", []))
    print(f"{CIANO}{GRASSETTO}=== INVENTARIO & EQUIPAGGIAMENTO: {eroe['nome'].upper()} ==={RESET}")
    print(f"{DIM}{eroe['classe']} Livello {eroe['livello']} | CA: {eroe['ca']} | {eroe['attacco']}{RESET}")
    print(f"\n{GIALLO}{GRASSETTO}💰 Borsello:{RESET} {VERDE}{GRASSETTO}{eroe.get('mo', 0)} Monete d'Oro (MO){RESET}")

    print(f"\n{ROSSO}{GRASSETTO}⚔️ Armi & Munizioni:{RESET}")
    if armi:
        for it in armi:
            print(f"  - {it}")
    else:
        print(f"  {DIM}(Nessuna arma equipaggiata){RESET}")

    print(f"\n{CIANO}{GRASSETTO}🛡️ Armatura & Protezione:{RESET}")
    if armature:
        for it in armature:
            print(f"  - {it}")
    else:
        print(f"  {DIM}(Nessuna armatura indossata, CA base 9){RESET}")

    print(f"\n{VERDE}{GRASSETTO}🎒 Zaino & Attrezzatura da Avventura:{RESET}")
    if zaino:
        for it in zaino:
            print(f"  - {it}")
    else:
        print(f"  {DIM}(Zaino vuoto){RESET}")
    print(f"{DIM}" + "-" * 65 + f"{RESET}")


def mostra_inventario_party(eroi_party: list):
    print(f"{CIANO}{GRASSETTO}=== INVENTARIO GENERALE DEL GRUPPO ({len(eroi_party)} Eroi) ==={RESET}\n")
    tot_mo = sum(e.get("mo", 0) for e in eroi_party)
    for e in eroi_party:
        sincronizza_statistiche_becmi(e)
        armi, armature, zaino = categorizza_inventario(e.get("equip", []))
        print(f"{VERDE}{GRASSETTO}{e['nome']}{RESET} ({e['classe']} Liv.{e['livello']}) — {GIALLO}{e.get('mo', 0)} MO{RESET}")
        equip_sint = []
        if armi:
            equip_sint.append(f"{ROSSO}Armi:{RESET} " + ", ".join(armi))
        if armature:
            equip_sint.append(f"{CIANO}Difesa:{RESET} " + ", ".join(armature))
        if zaino:
            equip_sint.append(f"{VERDE}Zaino:{RESET} " + ", ".join(zaino))
        for riga in equip_sint:
            print(f"  • {riga}")
        print()
    print(f"{GIALLO}{GRASSETTO}💰 Tesoro Totale della Compagnia: {tot_mo} Monete d'Oro (MO){RESET}")
    print(f"{DIM}" + "-" * 65 + f"{RESET}")


def mostra_riepilogo_party(eroi_party: list):
    print(f"{CIANO}{GRASSETTO}=== GRUPPO DI AVVENTURIERI ({len(eroi_party)} Eroi) ==={RESET}")
    for idx, e in enumerate(eroi_party, 1):
        print(f"  {VERDE}[{idx}]{RESET} {GRASSETTO}{e['nome']}{RESET} ({e['classe']} Liv.{e['livello']}) — PF: {e['pf_attuali']}/{e['pf_max']} | CA: {e['ca']} | MO: {e['mo']} | PE: {e['pe']}")


def scegli_membro_party(eroi_party: list, azione_desc: str):
    if len(eroi_party) == 1:
        return eroi_party[0]
    print(f"\n{GIALLO}Seleziona il personaggio per {azione_desc}:{RESET}")
    for idx, e in enumerate(eroi_party, 1):
        print(f"  {VERDE}[{idx}]{RESET} {e['nome']} ({e['classe']} Liv.{e['livello']} | PF {e['pf_attuali']}/{e['pf_max']} | {e['mo']} MO)")
    print(f"  {DIM}[0] Torna indietro{RESET}")
    scelta = input(f"\n{VERDE}Scelta > {RESET}").strip()
    if scelta == "0" or not scelta:
        return None
    try:
        idx = int(scelta) - 1
        if 0 <= idx < len(eroi_party):
            return eroi_party[idx]
    except ValueError:
        pass
    return None


def pulisci_schermo(avventura, eroi_party: list, ruolo_rete=""):
    os.system("clear" if os.name == "posix" else "cls")
    turno = len(avventura["storia"]) // 2
    stato_dadi = f"{VERDE}ON{RESET}" if AUTODADI_ATTIVI else f"{DIM}OFF{RESET}"
    nomi_str = ", ".join(f"{e['nome']} (Liv.{e['livello']})" for e in eroi_party)
    st_dungeon = avventura.get("stato_dungeon") or {}
    luce_amb = st_dungeon.get("luce_ambientale", False)
    amb_nome = st_dungeon.get("ambiente_nome", "Taverna / Locanda" if luce_amb else "Dungeon")
    torce_rimaste = st_dungeon.get("torcia_turni", avventura.get("torcia_turni_rimasti", 6))
    torcia_attiva = st_dungeon.get("torcia_attiva", False if luce_amb else True)
    buio = avventura.get("buio_totale", False)

    if luce_amb:
        icona = "🍻" if any(k in amb_nome.lower() for k in ["tavern", "locand", "osteria"]) else ("☀️" if any(k in amb_nome.lower() for k in ["giorno", "aperto", "citt", "borgo", "villaggio", "piazza"]) else "🏛️")
        stato_luce = f"{VERDE}{icona} Luce: {amb_nome}{RESET}"
        if torcia_attiva:
            stato_luce += f" {DIM}(🔥 Torcia: {torce_rimaste}/6 t){RESET}"
    elif not torcia_attiva or buio:
        stato_luce = f"{ROSSO}{GRASSETTO}🌑 BUIO TOTALE! (/torcia on){RESET}"
    else:
        stato_luce = f"{GIALLO}🔥 Torcia: {torce_rimaste}/6 t{RESET}"

    minuti_tot = turno * 10
    tempo_str = f"{minuti_tot // 60}h {minuti_tot % 60:02d}m"
    badge_rete = f" | {MAGENTA}{ruolo_rete}{RESET}" if ruolo_rete else ""
    mod_badge = f"{VERDE}🎲 Interattiva{RESET}" if st_dungeon.get("modalita_gioco", MODALITA_GIOCO) == "interattiva" else f"{GIALLO}🎲 Classica{RESET}"
    print(f"{ROSSO}{GRASSETTO}=== D&D BECMI [SQLite] ==={RESET} {GIALLO}{avventura['titolo']}{RESET} {DIM}| Turno {turno} ({tempo_str}){RESET} | {stato_luce} | {mod_badge} | {CIANO}DM AI: {VERDE}{GRASSETTO}{MODELLO}{RESET}{badge_rete}")
    print(f"{CIANO}Party:{RESET} {nomi_str}")
    print(f"{CIANO}Comandi:{RESET} /gruppo | /scheda | /inventario | /magia | /lancia | /modalita | /torcia | /ambiente | /incontri | /mappa | /esporta | /stop  {MAGENTA}[DM AI: {VERDE}{GRASSETTO}{MODELLO}{MAGENTA}]{RESET}")
    print(f"{DIM}" + "-" * 96 + f"{RESET}\n")


class IndicatoreAttesaDM:
    def __init__(self, messaggio="sta valutando la scena e tirando i dadi"):
        self.messaggio = messaggio
        self.stop_event = threading.Event()
        self.thread = None

    def _anima(self):
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        while not self.stop_event.is_set():
            char = spinner[idx % len(spinner)]
            testo = f"\r{GIALLO}🎲 {GRASSETTO}Dungeon Master{RESET} {MAGENTA}[AI: {VERDE}{GRASSETTO}{MODELLO}{MAGENTA}]{RESET} {CIANO}{self.messaggio}... {GIALLO}{char}{RESET} "
            sys.stdout.write(testo)
            sys.stdout.flush()
            idx += 1
            time.sleep(0.09)
        sys.stdout.write("\r" + " " * 110 + "\r")
        sys.stdout.flush()

    def __enter__(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._anima, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=0.3)


def normalizza_storia_gemini(raw_contents):
    """Garantisce la stretta alternanza user -> model -> user -> model richiesta dall'API Gemini."""
    if not raw_contents:
        return []
    puliti = []
    for m in raw_contents:
        parts = m.get("parts", [])
        if not parts or not parts[0].get("text", "").strip():
            continue
        ruolo = "user" if m.get("role") == "user" else "model"
        testo = parts[0]["text"].strip()
        if puliti and puliti[-1]["role"] == ruolo:
            puliti[-1]["parts"][0]["text"] += "\n" + testo
        else:
            puliti.append({"role": ruolo, "parts": [{"text": testo}]})

    if puliti and puliti[0]["role"] != "user":
        puliti.insert(0, {"role": "user", "parts": [{"text": "Iniziamo la sessione di D&D."}]})
    return puliti


def chiama_gemini(storia, api_key, system_prompt, pdf_path=None, desc_attesa="sta valutando la scena e tirando i dadi"):
    global MODELLO
    contents_invio = normalizza_storia_gemini(storia)

    # Finestra contestuale intelligente per mantenere le chiamate ultra-rapide (1-3s) ed evitare timeout su storie lunghe:
    if len(contents_invio) > 14:
        primo = contents_invio[0]
        idx_start = -12
        while abs(idx_start) <= len(contents_invio) and contents_invio[idx_start]["role"] != "user":
            idx_start += 1
        recenti = contents_invio[idx_start:]
        ponte_dm = {
            "role": "model",
            "parts": [{"text": "[Dungeon Master: Ricevuto lo scenario iniziale. Il gruppo ha proseguito l'esplorazione fino a questo punto. Situazione, eroi ed equipaggiamento sono sincronizzati nel prompt di sistema.]"}]
        }
        contents_invio = normalizza_storia_gemini([primo, ponte_dm] + recenti)

    pdf_part = None
    if pdf_path and os.path.exists(pdf_path) and contents_invio:
        if os.path.getsize(pdf_path) <= 18 * 1024 * 1024:
            with open(pdf_path, "rb") as f:
                pdf_part = types.Part.from_bytes(data=f.read(), mime_type="application/pdf")

    contents = []
    for index, message in enumerate(contents_invio):
        parts = []
        if index == 0 and pdf_part is not None:
            parts.append(pdf_part)
        parts.extend(
            types.Part(text=part["text"])
            for part in message["parts"]
            if "text" in part
        )
        contents.append(types.Content(role=message["role"], parts=parts))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=8192,
        temperature=0.85,
    )

    ultimo_errore = "Nessun modello disponibile."
    modelli_da_provare = [MODELLO] + [m for m in MODELLI_FALLBACK if m != MODELLO]

    with genai.Client(
        api_key=api_key.strip(),
        http_options=types.HttpOptions(timeout=22_000),
    ) as client:
        with IndicatoreAttesaDM(desc_attesa):
            for idx, mod in enumerate(modelli_da_provare):
                for tentativo in range(2):
                    try:
                        risultato = client.models.generate_content(
                            model=mod,
                            contents=contents,
                            config=config,
                        )
                    except errors.APIError as exc:
                        err_msg = exc.message or str(exc)
                        err_code = exc.code
                        ultimo_errore = f"{mod}: {err_msg}"
                        err_lower = err_msg.lower()

                        if "per day limit" in err_lower or "quota exceeded" in err_lower or "resource_exhausted" in err_lower:
                            if idx < len(modelli_da_provare) - 1:
                                prossimo = modelli_da_provare[idx + 1]
                                print(f"\n{GIALLO}⚠️ Quota esaurita su {mod}. Passaggio automatico al modello di riserva {prossimo}...{RESET}")
                                MODELLO = prossimo
                                break
                            raise Exception(f"Quota giornaliera esaurita su tutti i modelli disponibili. Dettaglio: {err_msg}") from exc

                        is_transient = err_code == 503 or any(k in err_lower for k in ["high demand", "overloaded", "spikes in demand"])
                        if is_transient and tentativo == 0:
                            time.sleep(1.5)
                            continue

                        if idx < len(modelli_da_provare) - 1:
                            MODELLO = modelli_da_provare[idx + 1]
                            break
                        raise Exception(err_msg) from exc

                    testo_completo = risultato.text or ""
                    if not testo_completo:
                        ultimo_errore = f"Risposta vuota dal modello ({mod})."
                        if tentativo == 0:
                            time.sleep(0.8)
                            continue
                        if idx < len(modelli_da_provare) - 1:
                            MODELLO = modelli_da_provare[idx + 1]
                            break
                        continue

                    candidates = risultato.candidates or []
                    finish_reason = candidates[0].finish_reason if candidates else None
                    if str(finish_reason).split(".")[-1] == "MAX_TOKENS":
                        testo_completo += "\n\n[Nota: risposta troncata per limite token del modello]"
                    if mod != MODELLO:
                        MODELLO = mod
                    return testo_completo

    raise Exception(ultimo_errore)


def tasto_premuto():
    if os.name == "posix":
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            sys.stdin.readline()
            return True
    return False


def evidenzia_dadi(riga):
    return re.sub(r"(\[[^\]]+\])", rf"{GIALLO}{GRASSETTO}\1{RESET}", riga)


def formatta_risposta(testo, animato=False):
    righe = testo.strip().split("\n")
    salta = not animato

    for riga in righe:
        riga_pulita = riga.strip()
        if "[CHIAMATA DADO:" in riga_pulita.upper():
            print(f"\n{ROSSO}{GRASSETTO}╔════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
            print(f"{ROSSO}{GRASSETTO}║ 🎲 {GIALLO}{riga_pulita}{RESET}")
            print(f"{ROSSO}{GRASSETTO}╚════════════════════════════════════════════════════════════════════════════════════════╝{RESET}")
        elif riga_pulita.startswith("[") and "PF:" in riga_pulita:
            print(f"{CIANO}{GRASSETTO}{riga}{RESET}")
        elif riga_pulita in ["Cosa fai?", "Cosa fate?"]:
            print(f"\n{GIALLO}{GRASSETTO}{riga}{RESET}")
        else:
            if salta:
                print(evidenzia_dadi(riga))
            else:
                dentro_quadra = False
                for i, carattere in enumerate(riga):
                    if tasto_premuto():
                        salta = True
                        if dentro_quadra:
                            sys.stdout.write(RESET)
                            dentro_quadra = False
                        sys.stdout.write(evidenzia_dadi(riga[i:]))
                        sys.stdout.flush()
                        break
                    if carattere == "[":
                        dentro_quadra = True
                        sys.stdout.write(f"{GIALLO}{GRASSETTO}[")
                    elif carattere == "]" and dentro_quadra:
                        dentro_quadra = False
                        sys.stdout.write(f"]{RESET}")
                    else:
                        sys.stdout.write(carattere)
                    sys.stdout.flush()
                    if carattere in ".!?":
                        time.sleep(0.06)
                    elif carattere in ",;:":
                        time.sleep(0.025)
                    else:
                        time.sleep(0.01)
                if dentro_quadra:
                    sys.stdout.write(RESET)
                print()


def crea_personaggio(db: DnDDatabase, personaggi: dict):
    os.system("clear" if os.name == "posix" else "cls")
    print(f"{CIANO}{GRASSETTO}=== CREAZIONE NUOVO PERSONAGGIO (SCALA COMPLETA BECMI) ==={RESET}\n")
    for k, v in CLASSI_BASE.items():
        print(f"  {VERDE}{GRASSETTO}[{k}]{RESET} {v['classe']:<10} (DV 1d{v['dado_vita']}, Max Liv.{v['max_liv']:<2}, CA base {v['ca_base']}, For {v['forza']}, Des {v['destrezza']})")
    print(f"\n  {DIM}[0] Torna al menu precedente{RESET}")

    scelta = input(f"\n{VERDE}Scegli la classe (1-9, oppure 0 per tornare) > {RESET}").strip()
    if scelta == "0":
        return None
    if scelta not in CLASSI_BASE:
        scelta = "1"
    base = CLASSI_BASE[scelta]

    nome = input(f"{VERDE}Inserisci il nome del tuo {base['classe']} (0 per annullare) > {RESET}").strip()
    if nome == "0":
        return None
    if not nome:
        nome = f"{base['classe']} {len(personaggi) + 1}"

    allineamento = input(f"{VERDE}Allineamento [L]egale, [N]eutrale, [C]aotico (Invio = Legale) > {RESET}").strip().lower()
    allineamento = {"n": "Neutrale", "c": "Caotico"}.get(allineamento, "Legale")

    modo = input(f"{GIALLO}Caratteristiche: [S]tandard bilanciate o [T]iro casuale 3d6? (Invio = Standard) > {RESET}").strip().lower()
    if modo == "t":
        forza = sum(random.randint(1, 6) for _ in range(3))
        intelligenza = sum(random.randint(1, 6) for _ in range(3))
        saggezza = sum(random.randint(1, 6) for _ in range(3))
        destrezza = sum(random.randint(1, 6) for _ in range(3))
        costituzione = sum(random.randint(1, 6) for _ in range(3))
        carisma = sum(random.randint(1, 6) for _ in range(3))
        tiro_pf = random.randint(1, base["dado_vita"])
        pf_max = max(1, tiro_pf + mod_caratteristica(costituzione))
        ca = base["ca_base"] - mod_caratteristica(destrezza)
        mo = sum(random.randint(1, 6) for _ in range(3)) * 10
        print(f"\n{GIALLO}Tiri 3d6 generati:{RESET} FOR {forza}, INT {intelligenza}, SAG {saggezza}, DES {destrezza}, COS {costituzione}, CAR {carisma}")
        print(f"{GIALLO}PF iniziali (1d{base['dado_vita']}+COS):{RESET} {pf_max} | {GIALLO}CA:{RESET} {ca} | {GIALLO}Oro iniziale (3d6x10):{RESET} {mo} MO")
        input(f"\n{DIM}Premi INVIO per confermare l'eroe...{RESET}")
    else:
        forza, intelligenza, saggezza = base["forza"], base["intelligenza"], base["saggezza"]
        destrezza, costituzione, carisma = base["destrezza"], base["costituzione"], base["carisma"]
        pf_max = max(1, base["dado_vita"] + mod_caratteristica(costituzione))
        ca = base["ca_base"] - mod_caratteristica(destrezza)
        mo = base["mo"]

    liv_iniz = input(f"{GIALLO}Livello di partenza (1-{base['max_liv']}, Invio = 1 Basic) > {RESET}").strip()
    livello_partenza = int(liv_iniz) if liv_iniz.isdigit() and 1 <= int(liv_iniz) <= base["max_liv"] else 1
    pe_partenza = base["xp"][livello_partenza - 1]
    if livello_partenza > 1:
        for l_extra in range(2, livello_partenza + 1):
            if l_extra <= 9:
                pf_max += max(1, random.randint(1, base["dado_vita"]) + mod_caratteristica(costituzione))
            else:
                pf_max += base["pf_dopo_9"]
        mo += livello_partenza * 150

    nuovo_eroe = {
        "nome": nome, "classe": base["classe"], "livello": livello_partenza, "allineamento": allineamento,
        "immortale": False,
        "forza": forza, "intelligenza": intelligenza, "saggezza": saggezza,
        "destrezza": destrezza, "costituzione": costituzione, "carisma": carisma,
        "pf_attuali": pf_max, "pf_max": pf_max, "ca": ca,
        "equip": list(base["equip"]), "mo": mo, "pe": pe_partenza
    }
    sincronizza_statistiche_becmi(nuovo_eroe)
    db.salva_personaggio(nuovo_eroe)
    personaggi.clear()
    personaggi.update(db.carica_tutti_personaggi())
    return personaggi[nome]


def crea_nuova_avventura(db: DnDDatabase, avventure: dict, personaggi: dict):
    os.system("clear" if os.name == "posix" else "cls")
    print(f"{CIANO}{GRASSETTO}=== NUOVA AVVENTURA (SINGOLO O PARTY MULTI-GIOCATORE) ==={RESET}")
    print(f"{DIM}Digita 0 in qualsiasi passaggio per tornare al Menu Principale.{RESET}\n")

    num_str = input(f"{GIALLO}Quanti giocatori partecipano? (1-6, Invio = 1, 0 = Menu Principale) > {RESET}").strip()
    if num_str == "0":
        return None
    num_giocatori = int(num_str) if num_str.isdigit() and 1 <= int(num_str) <= 6 else 1

    party_nomi = []
    for g_idx in range(1, num_giocatori + 1):
        while True:
            print(f"\n{GIALLO}--- Scelta Eroe per Giocatore {g_idx} di {num_giocatori} ---{RESET}")
            nomi_disp = [n for n in personaggi.keys() if n not in party_nomi]
            for idx, n in enumerate(nomi_disp, 1):
                p = personaggi[n]
                print(f"  {VERDE}[{idx}]{RESET} {p['nome']} ({p['classe']} Liv.{p['livello']} | PF {p['pf_attuali']}/{p['pf_max']} | {p['mo']} MO)")
            print(f"  {CIANO}[C]{RESET} Crea un nuovo personaggio ora")
            print(f"  {DIM}[0] Torna al Menu Principale{RESET}")

            scelta_eroe = input(f"\n{VERDE}Seleziona eroe per Giocatore {g_idx} > {RESET}").strip().lower()
            if scelta_eroe == "0":
                return None
            if scelta_eroe == "c" or not nomi_disp:
                nuovo = crea_personaggio(db, personaggi)
                if nuovo:
                    party_nomi.append(nuovo["nome"])
                    break
            else:
                try:
                    scelto = nomi_disp[int(scelta_eroe) - 1]
                    party_nomi.append(scelto)
                    break
                except Exception:
                    print(f"{ROSSO}Selezione non valida.{RESET}")

    print(f"\n{GIALLO}Scegli lo scenario dell'avventura:{RESET}")
    for k, (tit, _) in SCENARI_AVVENTURA.items():
        print(f"  {VERDE}[{k}]{RESET} {tit}")
    print(f"  {MAGENTA}{GRASSETTO}[M]{RESET} Carica un modulo PDF dalla cartella '{MODULI_DIR}/'")
    print(f"  {CIANO}[P]{RESET} Scenario personalizzato")
    print(f"  {DIM}[0] Torna al Menu Principale{RESET}")

    modulo_pdf = ""
    modulo_testo = ""
    scelta_scen = input(f"\n{VERDE}Seleziona scenario > {RESET}").strip().lower()
    if scelta_scen == "0":
        return None
    if scelta_scen == "m":
        moduli = elenca_moduli_pdf()
        if not moduli:
            print(f"\n{GIALLO}Nessun file .pdf trovato nella cartella '{MODULI_DIR}/'.{RESET}")
            percorso_manuale = input(f"{VERDE}Incolla il percorso completo del file PDF (0 = Menu Principale) > {RESET}").strip().strip('"').strip("'")
            if percorso_manuale == "0":
                return None
            if percorso_manuale and os.path.isfile(percorso_manuale):
                percorso_scelto = percorso_manuale
            else:
                titolo, prompt = SCENARI_AVVENTURA["1"]
                percorso_scelto = ""
        else:
            print(f"\n{CIANO}Moduli PDF disponibili in '{MODULI_DIR}/':{RESET}")
            for idx, m_file in enumerate(moduli, 1):
                print(f"  {VERDE}[{idx}]{RESET} {m_file}")
            print(f"  {DIM}[0] Torna al Menu Principale{RESET}")
            sel_m = input(f"\n{VERDE}Scegli il numero del PDF > {RESET}").strip()
            if sel_m == "0":
                return None
            try:
                percorso_scelto = os.path.join(MODULI_DIR, moduli[int(sel_m) - 1])
            except Exception:
                percorso_scelto = os.path.join(MODULI_DIR, moduli[0])

        if percorso_scelto:
            print(f"{DIM}Lettura e indicizzazione del modulo PDF in corso...{RESET}")
            modulo_pdf = os.path.basename(percorso_scelto)
            testo_estratto, b64_pdf = prepara_contenuto_modulo(percorso_scelto)
            if testo_estratto:
                modulo_testo = testo_estratto
                print(f"{VERDE}Testo estratto con successo ({len(modulo_testo)} caratteri).{RESET}")
            elif b64_pdf:
                modulo_pdf = os.path.abspath(percorso_scelto)
                print(f"{VERDE}PDF scansionato collegato direttamente alle API Gemini.{RESET}")
            titolo_default = os.path.splitext(os.path.basename(percorso_scelto))[0].replace("_", " ").replace("-", " ")
            titolo = input(f"{VERDE}Titolo avventura (Invio = '{titolo_default}', 0 = Menu) > {RESET}").strip()
            if titolo == "0":
                return None
            titolo = titolo or titolo_default
            prompt = (
                f"Inizia l'avventura ufficiale '{titolo}' per il gruppo composto da {', '.join(party_nomi)} basata sul modulo PDF allegato. "
                "Presenta l'introduzione per i giocatori (o la prima area/stanza iniziale) senza anticipare spoiler, "
                "rispettando mostri, incontri e descrizioni del modulo."
            )
    elif scelta_scen in SCENARI_AVVENTURA:
        titolo, base_prompt = SCENARI_AVVENTURA[scelta_scen]
        prompt = f"Gruppo di avventurieri: {', '.join(party_nomi)}. {base_prompt}"
    else:
        titolo = input(f"{VERDE}Titolo della nuova avventura (0 = Menu Principale) > {RESET}").strip()
        if titolo == "0":
            return None
        titolo = titolo or "Spedizione nelle Terre Selvagge"
        prompt = input(f"{VERDE}Descrivi dove inizia l'avventura > {RESET}").strip() or "Inizia l'avventura davanti all'ingresso di un'antica rovina."
        prompt = f"Gruppo di avventurieri: {', '.join(party_nomi)}. {prompt}"

    print(f"\n{CIANO}{GRASSETTO}Modalità di gioco per questa avventura:{RESET}")
    print(f"  {VERDE}[1] Interattiva{RESET} (Il DM AI indica quale dado tirare e attende il tuo tiro reale) [CONSIGLIATA]")
    print(f"  {GIALLO}[2] Classica{RESET} (Narrazione fluida con dadi risolti direttamente dal DM)")
    scelta_mod = input(f"{VERDE}Scegli modalità [1/2] (Invio per {MODALITA_GIOCO.capitalize()}) > {RESET}").strip()
    modalita_adv = "classica" if scelta_mod == "2" else ("interattiva" if scelta_mod == "1" else MODALITA_GIOCO)

    if AUTODADI_ATTIVI and modalita_adv == "classica":
        righe_dadi = [genera_batteria_dadi(nome)["testo"] for nome in party_nomi]
        prompt = f"{prompt}\n" + "\n".join(righe_dadi)

    adv_id = f"adv_{int(time.time())}"
    nuova_adv = {
        "id": adv_id,
        "titolo": titolo,
        "eroe": party_nomi[0],
        "party": party_nomi,
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "storia": [{"role": "user", "parts": [{"text": prompt}]}],
        "note": "",
        "modulo_pdf": modulo_pdf,
        "modulo_testo": modulo_testo,
        "stato_dungeon": {
            "modalita_gioco": modalita_adv,
            "torcia_turni": 6,
            "torcia_attiva": False,
            "luce_ambientale": True,
            "ambiente_nome": "Città / Villaggio",
            "ambiente_manuale": False,
            "auto_sostituisci": True,
            "frequenza_incontri": "raro"
        }
    }
    db.salva_metadati_avventura(nuova_adv)
    db.aggiungi_messaggio(adv_id, "user", prompt)
    avventure[adv_id] = nuova_adv
    return nuova_adv


def menu_principale(db: DnDDatabase, avventure: dict, personaggi: dict):
    global MODELLO, MODALITA_GIOCO, AUTODADI_ATTIVI, API_KEY_ATTIVA
    while True:
        os.system("clear" if os.name == "posix" else "cls")
        print(LOGO_INTRO)
        stats = db.statistiche_db()
        ip_lan = ottieni_ip_locale()
        key_str = maschera_chiave(API_KEY_ATTIVA)
        print(f"{DIM}SQLite: {stats['file']} ({stats['size_kb']} KB | {stats['personaggi']} Eroi | {stats['avventure']} Avventure) | Modello: {MODELLO} | Key: {key_str}{DIM} | IP LAN: {ip_lan}{RESET}")
        print(f"{DIM}" + "=" * 96 + f"{RESET}\n")

        lista_adv = list(avventure.values())
        if lista_adv:
            print(f"{GIALLO}{GRASSETTO}Avventure salvate (digita il numero per riprendere in locale):{RESET}")
            for idx, adv in enumerate(lista_adv, 1):
                turni = len(adv.get("storia", [])) // 2
                titolo = adv.get("titolo", "Avventura Salvata")
                party_list = adv.get("party") or [adv.get("eroe", "Valen di Corvobianco")]
                party_str = ", ".join(party_list)
                data_adv = adv.get("data", "")
                mod_adv = adv.get("stato_dungeon", {}).get("modalita_gioco", MODALITA_GIOCO)
                mod_badge = f"{VERDE}🎲 Interattiva{RESET}" if mod_adv == "interattiva" else f"{GIALLO}🎲 Classica{RESET}"
                print(f"  {VERDE}{GRASSETTO}[{idx}]{RESET} {titolo} — {CIANO}{party_str}{RESET} {DIM}({turni} turni | {mod_badge}{DIM} | {data_adv}){RESET}")
            print()

        mod_badge_menu = f"{VERDE}INTERATTIVA (Chiamata Dadi DM){RESET}" if MODALITA_GIOCO == "interattiva" else f"{GIALLO}CLASSICA (Auto/Fast){RESET}"
        print(f"  {VERDE}{GRASSETTO}[N]{RESET} Nuova Avventura (1-6 giocatori locali / Party Multi-Eroe)")
        print(f"  {CIANO}{GRASSETTO}[C]{RESET} Crea solo un Nuovo Personaggio")
        print(f"  {GIALLO}{GRASSETTO}[P]{RESET} Stampa Scheda Personaggio in PDF A4 (cartella {SCHEDE_DIR}/)")
        print(f"  {CIANO}{GRASSETTO}[G]{RESET} Manuale dei Comandi & Guida in PDF A4 ({MANUALE_FILE})")
        print(f"  {MAGENTA}{GRASSETTO}[H]{RESET} Ospita Partita in LAN (Server TCP su {ip_lan}:{DEFAULT_LAN_PORT})")
        print(f"  {MAGENTA}{GRASSETTO}[J]{RESET} Unisciti a Partita in LAN (Client TCP verso Host)")
        print(f"  {GIALLO}{GRASSETTO}[I]{RESET} Modalità di Gioco (Attiva: {mod_badge_menu})")
        print(f"  {CIANO}{GRASSETTO}[M]{RESET} Seleziona Modello AI (Attivo: {MODELLO})")
        print(f"  {GIALLO}{GRASSETTO}[K]{RESET} Gestione Chiave API Gemini (Attiva: {maschera_chiave(API_KEY_ATTIVA)})")
        print(f"  {GIALLO}{GRASSETTO}[E]{RESET} Elimina un'avventura salvata")
        print(f"  {ROSSO}{GRASSETTO}[Q]{RESET} Chiudi ed esci dal programma\n")

        scelta = input(f"{VERDE}{GRASSETTO}Scelta > {RESET}").strip().lower()
        if scelta == "q":
            return None, "exit"
        elif scelta == "n":
            adv = crea_nuova_avventura(db, avventure, personaggi)
            if adv:
                return adv, "local"
        elif scelta == "c":
            eroe = crea_personaggio(db, personaggi)
            if eroe:
                print(f"\n{VERDE}Personaggio {eroe['nome']} creato e salvato in SQLite!{RESET}")
                opz_pdf = input(f"{CIANO}Vuoi stampare subito la Scheda del Personaggio in PDF A4? (s/n) > {RESET}").strip().lower()
                if opz_pdf in ["s", "si", "y", "yes"]:
                    esporta_scheda_pdf_a4(eroe)
                    input(f"\n{DIM}Premi Invio per tornare al Menu Principale...{RESET}")
                else:
                    time.sleep(1.1)
        elif scelta == "p":
            print(f"\n{CIANO}{GRASSETTO}=== STAMPA SCHEDA PERSONAGGIO IN PDF A4 ==={RESET}")
            lista_pg = list(personaggi.values())
            if not lista_pg:
                print(f"{GIALLO}Nessun personaggio registrato nel database SQLite.{RESET}")
                time.sleep(1.2)
                continue
            for i, pg in enumerate(lista_pg, 1):
                print(f"  {VERDE}[{i}]{RESET} {pg['nome']} ({pg['classe']} Liv.{pg['livello']} - {pg['allineamento']})")
            print(f"  {GIALLO}[T]{RESET} Stampa le schede di TUTTI i personaggi ({len(lista_pg)} eroi)")
            scelta_pg = input(f"\n{VERDE}Seleziona personaggio da stampare (o 0 per annullare) > {RESET}").strip().lower()
            if scelta_pg in ["t", "tutti", "all"]:
                for pg in lista_pg:
                    esporta_scheda_pdf_a4(pg)
                input(f"\n{DIM}Premi Invio per tornare al Menu Principale...{RESET}")
            elif scelta_pg.isdigit() and 1 <= int(scelta_pg) <= len(lista_pg):
                pg_scelto = lista_pg[int(scelta_pg) - 1]
                esporta_scheda_pdf_a4(pg_scelto)
                input(f"\n{DIM}Premi Invio per tornare al Menu Principale...{RESET}")
            continue
        elif scelta == "g":
            aggiorna_manuale_comandi_pdf(forza=True, silenzioso=False)
            input(f"\n{DIM}Premi Invio per tornare al Menu Principale...{RESET}")
            continue
        elif scelta == "h":
            return None, "host_lan"
        elif scelta == "j":
            return None, "join_lan"
        elif scelta == "i":
            print(f"\n{CIANO}{GRASSETTO}=== SELEZIONE MODALITÀ DI GIOCO ==={RESET}")
            print(f"  {VERDE}[1] Interattiva (Dadi Reali & Chiamata DM){RESET} - {DIM}CONSIGLIATA{RESET}")
            print(f"      Il DM AI si ferma ad ogni azione incerta, indica quale dado tirare e aspetta il tuo tiro reale.")
            print(f"  {GIALLO}[2] Classica / Automatica{RESET}")
            print(f"      Il DM AI o il motore tirano e narrano direttamente i risultati in modo continuo e veloce.")
            mod_label = f"{VERDE}INTERATTIVA{RESET}" if MODALITA_GIOCO == "interattiva" else f"{GIALLO}CLASSICA{RESET}"
            print(f"\nModalità attualmente attiva: {mod_label}")
            scelta_m = input(f"\n{VERDE}Scegli modalità [1-2] o premi Invio per alternare: {RESET}").strip()
            if scelta_m == "1":
                MODALITA_GIOCO = "interattiva"
                AUTODADI_ATTIVI = False
            elif scelta_m == "2":
                MODALITA_GIOCO = "classica"
                AUTODADI_ATTIVI = True
            elif not scelta_m:
                MODALITA_GIOCO = "classica" if MODALITA_GIOCO == "interattiva" else "interattiva"
                AUTODADI_ATTIVI = (MODALITA_GIOCO == "classica")
            print(f"\n{VERDE}Modalità di gioco impostata su: {GRASSETTO}{MODALITA_GIOCO.upper()}{RESET}")
            time.sleep(1)
            continue
        elif scelta == "m":
            print(f"\n{CIANO}{GRASSETTO}=== SELEZIONE MODELLO GEMINI ==={RESET}")
            for i, m in enumerate(MODELLI_FALLBACK, 1):
                attivo = f" {VERDE}(ATTIVO){RESET}" if m == MODELLO else ""
                print(f"  [{i}] {m}{attivo}")
            scelta_m = input(f"\n{VERDE}Scegli modello [1-{len(MODELLI_FALLBACK)}] o premi Invio per lasciare invariato: {RESET}").strip()
            if scelta_m.isdigit() and 1 <= int(scelta_m) <= len(MODELLI_FALLBACK):
                MODELLO = MODELLI_FALLBACK[int(scelta_m) - 1]
                print(f"{VERDE}Modello AI impostato su: {GRASSETTO}{MODELLO}{RESET}")
                time.sleep(1)
            continue
        elif scelta == "k":
            print(f"\n{CIANO}{GRASSETTO}=== GESTIONE CHIAVE API GOOGLE GEMINI ==={RESET}")
            print(f"Chiave attualmente attiva: {maschera_chiave(API_KEY_ATTIVA)}")
            print(f"File memorizzazione su disco: {KEY_FILE} ({'PRESENTE' if os.path.exists(KEY_FILE) else 'NON PRESENTE'})")
            print(f"\n  {VERDE}[1]{RESET} Inserisci / Modifica Chiave API")
            print(f"  {ROSSO}[2]{RESET} Rimuovi chiave salvata da disco ({KEY_FILE})")
            print(f"  {DIM}[0]{RESET} Torna al Menu Principale")
            sk = input(f"\n{VERDE}Scelta > {RESET}").strip()
            if sk == "1":
                nuova_k = richiedi_api_key_interattiva(forza_richiesta=True)
                if nuova_k:
                    API_KEY_ATTIVA = nuova_k
                    print(f"\n{VERDE}✓ Chiave API aggiornata con successo!{RESET}")
                    time.sleep(1)
            elif sk == "2":
                if elimina_api_key_salvata():
                    print(f"\n{GIALLO}✓ File {KEY_FILE} rimosso con successo.{RESET}")
                else:
                    print(f"\n{GIALLO}Nessun file {KEY_FILE} da rimuovere.{RESET}")
                time.sleep(1)
            continue
        elif scelta == "e":
            if not lista_adv:
                print(f"{GIALLO}Nessuna avventura da eliminare.{RESET}")
                time.sleep(1)
                continue
            num = input(f"{ROSSO}Numero dell'avventura da eliminare (0 = Torna al Menu Principale) > {RESET}").strip()
            if num == "0" or not num:
                continue
            try:
                adv_da_rimuovere = lista_adv[int(num) - 1]
                db.elimina_avventura(adv_da_rimuovere["id"])
                del avventure[adv_da_rimuovere["id"]]
                print(f"{GIALLO}Avventura eliminata dal database.{RESET}")
                time.sleep(1)
            except Exception:
                pass
        else:
            try:
                idx = int(scelta) - 1
                if 0 <= idx < len(lista_adv):
                    return lista_adv[idx], "local"
            except ValueError:
                pass


def apri_emporio(db: DnDDatabase, eroi_party: list, avventura: dict):
    os.system("clear" if os.name == "posix" else "cls")
    print(f"{GIALLO}{GRASSETTO}=== EMPORIO DELLE TERRE DI CONFINE ==={RESET}")
    eroe = scegli_membro_party(eroi_party, "fare acquisti")
    if not eroe:
        return

    os.system("clear" if os.name == "posix" else "cls")
    print(f"{GIALLO}{GRASSETTO}=== EMPORIO DELLE TERRE DI CONFINE ==={RESET}")
    print(f"Acquirente: {CIANO}{eroe['nome']}{RESET} | Borsello attuale: {VERDE}{GRASSETTO}{eroe['mo']} MO{RESET}\n")
    for codice, nome_item, costo, _, _ in EMPORIO_ITEMS:
        print(f"  {VERDE}[{codice:>2}]{RESET} {nome_item:<42} {GIALLO}{costo:>3} MO{RESET}")
    print(f"\n  {DIM}[0] Torna all'avventura{RESET}")

    acquisti_fatti = []
    while True:
        scelta = input(f"\n{VERDE}Numero articolo da acquistare (0 per tornare indietro) > {RESET}").strip()
        if scelta == "0" or not scelta:
            break
        trovato = next((item for item in EMPORIO_ITEMS if item[0] == scelta), None)
        if not trovato:
            print("Articolo non valido.")
            continue
        _, nome_item, costo, tipo, label_equip = trovato
        if eroe["mo"] < costo:
            print(f"{ROSSO}Monete d'oro insufficienti! {eroe['nome']} ha solo {eroe['mo']} MO.{RESET}")
            continue
        eroe["mo"] -= costo
        eroe["equip"].append(label_equip)
        if tipo == "scudo":
            eroe["ca"] -= 1
        elif tipo == "armatura_3":
            eroe["ca"] = 3 - mod_caratteristica(eroe["destrezza"])
        acquisti_fatti.append(label_equip)
        suona("tesoro")
        print(f"{VERDE}Acquistato per {eroe['nome']}: {label_equip}! Rimangono {eroe['mo']} MO.{RESET}")

    if acquisti_fatti:
        nota_acquisto = f"{eroe['nome']} ha visitato l'emporio e acquistato: {', '.join(acquisti_fatti)}. Ora ha {eroe['mo']} MO e CA {eroe['ca']}."
        risp_dm = f"Ho annotato i nuovi acquisti di {eroe['nome']} nell'inventario ({', '.join(acquisti_fatti)}). Borsello: {eroe['mo']} MO.\n\nCosa fate?"
        avventura["storia"].append({"role": "user", "parts": [{"text": nota_acquisto}]})
        avventura["storia"].append({"role": "model", "parts": [{"text": risp_dm}]})
        db.aggiungi_messaggio(avventura["id"], "user", nota_acquisto)
        db.aggiungi_messaggio(avventura["id"], "model", risp_dm)
        db.salva_personaggio(eroe)


def aggiorna_manuale_eroe(db: DnDDatabase, eroi_party: list):
    os.system("clear" if os.name == "posix" else "cls")
    print(f"{GIALLO}{GRASSETTO}=== AGGIORNAMENTO RAPIDO SCHEDA ==={RESET}")
    eroe = scegli_membro_party(eroi_party, "aggiornare la scheda")
    if not eroe:
        return

    os.system("clear" if os.name == "posix" else "cls")
    mostra_scheda(eroe)
    print(f"\n{GIALLO}Premi INVIO per lasciare invariato un campo, oppure 0 su Livello per annullare.{RESET}")
    liv = input(f"Livello attuale ({eroe['livello']}): ").strip()
    if liv == "0":
        return
    if liv.isdigit():
        eroe["livello"] = int(liv)
    pe = input(f"Punti Esperienza PE ({eroe['pe']}): ").strip()
    if pe.isdigit():
        eroe["pe"] = int(pe)
    pfm = input(f"PF Massimi ({eroe['pf_max']}): ").strip()
    if pfm.isdigit():
        eroe["pf_max"] = int(pfm)
        eroe["pf_attuali"] = int(pfm)
    ca = input(f"Classe Armatura ({eroe['ca']}): ").strip()
    if ca.lstrip("-").isdigit():
        eroe["ca"] = int(ca)
    mo = input(f"Monete d'Oro ({eroe['mo']}): ").strip()
    if mo.isdigit():
        eroe["mo"] = int(mo)
    nuovo_ogg = input("Aggiungi oggetto/tesoro all'inventario: ").strip()
    if nuovo_ogg:
        eroe["equip"].append(nuovo_ogg)
    sincronizza_statistiche_becmi(eroe)
    verifica_passaggio_livello(eroe)
    db.salva_personaggio(eroe)
    print(f"\n{VERDE}Scheda BECMI di {eroe['nome']} aggiornata e salvata in SQLite!{RESET}")
    time.sleep(1)


def gestisci_comando_livello(db: DnDDatabase, eroi_party: list, avventura: dict):
    os.system("clear" if os.name == "posix" else "cls")
    print(f"{CIANO}{GRASSETTO}=== PROGRESSIONE BECMI & ASCENSIONE IMMORTALE ==={RESET}")
    eroe = scegli_membro_party(eroi_party, "gestire livello / Immortalita")
    if not eroe:
        return

    os.system("clear" if os.name == "posix" else "cls")
    sincronizza_statistiche_becmi(eroe)
    mostra_scheda(eroe)
    avanzamenti = verifica_passaggio_livello(eroe)
    if avanzamenti:
        msg = f"{eroe['nome']} e salito al Livello {eroe['livello']} ({eroe['fascia_becmi']})! Ora ha {eroe['pf_max']} PF max, {eroe['attacco']}."
        risp = f"Congratulazioni! Ho registrato il passaggio di {eroe['nome']} al Livello {eroe['livello']}.\n\nCosa fate?"
        avventura["storia"].append({"role": "user", "parts": [{"text": msg}]})
        avventura["storia"].append({"role": "model", "parts": [{"text": risp}]})
        db.aggiungi_messaggio(avventura["id"], "user", msg)
        db.aggiungi_messaggio(avventura["id"], "model", risp)
        db.salva_personaggio(eroe)
        input(f"\n{DIM}Premi INVIO per continuare...{RESET}")
        return

    print(f"\n{GIALLO}Opzioni avanzate:{RESET}")
    print(f"  {VERDE}[1]{RESET} Forza passaggio di livello (+1 livello con tiro Dado Vita)")
    print(f"  {MAGENTA}[2]{RESET} Ascensione al Rango Immortale (Scatola Oro - trasforma l'eroe in Immortale Liv. 1)")
    print(f"  {DIM}[0] Torna all'avventura{RESET}")
    scelta = input(f"\n{VERDE}Scelta > {RESET}").strip()
    if scelta == "0" or not scelta:
        return
    if scelta == "1":
        dati = trova_dati_classe(eroe["classe"])
        max_l = 36 if eroe.get("immortale") else dati["max_liv"]
        if eroe["livello"] < max_l:
            eroe["livello"] += 1
            if not eroe.get("immortale"):
                if eroe["livello"] <= 9:
                    guad = max(1, random.randint(1, dati["dado_vita"]) + mod_caratteristica(eroe["costituzione"]))
                else:
                    guad = dati["pf_dopo_9"]
                eroe["pf_max"] += guad
                eroe["pf_attuali"] += guad
            sincronizza_statistiche_becmi(eroe)
            db.salva_personaggio(eroe)
            suona("levelup")
            print(f"{VERDE}Livello di {eroe['nome']} aumentato a {eroe['livello']} ({eroe['fascia_becmi']})!{RESET}")
            time.sleep(1.2)
    elif scelta == "2" and not eroe.get("immortale"):
        eroe["immortale"] = True
        eroe["livello"] = 1
        eroe["pe"] = 0
        eroe["pf_max"] += 20
        eroe["pf_attuali"] = eroe["pf_max"]
        sincronizza_statistiche_becmi(eroe)
        db.salva_personaggio(eroe)
        suona("levelup")
        print(f"{MAGENTA}{GRASSETTO}ASCENSIONE COMPLETATA! {eroe['nome']} e ora un Immortale Iniziato (Liv. 1)!{RESET}")
        msg_u = f"{eroe['nome']} ha completato la Quest per l'Immortalita ed e asceso al Rango Immortale (Iniziato, Livello Immortale 1)!"
        msg_m = f"I cieli si squarciano mentre {eroe['nome']} abbandona la condizione mortale per entrare nella Sfera degli Immortali!\n\nCosa fate?"
        avventura["storia"].append({"role": "user", "parts": [{"text": msg_u}]})
        avventura["storia"].append({"role": "model", "parts": [{"text": msg_m}]})
        db.aggiungi_messaggio(avventura["id"], "user", msg_u)
        db.aggiungi_messaggio(avventura["id"], "model", msg_m)
        time.sleep(1.5)


def genera_mappa_ascii(avventura, api_key, eroi_party: list):
    print(f"{CIANO}Disegno della mappa delle aree esplorate in corso...{RESET}")
    storia_recente = []
    for msg in avventura.get("storia", [])[-14:]:
        ruolo = "GIOCATORI" if msg.get("role") == "user" else "DUNGEON MASTER"
        testo = msg.get("parts", [{}])[0].get("text", "")
        righe_pulite = [r for r in testo.split("\n") if "TIRI REALI" not in r]
        storia_recente.append(f"{ruolo}: " + "\n".join(righe_pulite))

    nomi_party = ", ".join(e["nome"] for e in eroi_party)
    cronaca = "\n---\n".join(storia_recente) if storia_recente else f"Inizio avventura: {avventura.get('titolo', 'Dungeon')}"
    if avventura.get("modulo_testo"):
        cronaca += "\n\nRIFERIMENTO STANZE DAL MODULO (disegna SOLO le stanze gia visitate nella cronaca sopra, NON quelle non ancora esplorate!):\n" + avventura["modulo_testo"][:25000]
    prompt_cartografo = (
        "Sei un cartografo di Dungeons & Dragons. Leggi la cronaca dell'esplorazione qui sotto e disegna "
        "una mappa ASCII chiara, ordinata e ben allineata di tutti gli ambienti, stanze, corridoi, porte, "
        "scale e punti di interesse scoperti finora.\n"
        "USA ESCLUSIVAMENTE QUESTI SIMBOLI ASCII:\n"
        "+----+  muri perimetrali e angoli\n"
        "|    |  pareti verticali\n"
        "  .     pavimento esplorato\n"
        "  #     corridoio o passaggio\n"
        "  D     porta chiusa / / porta aperta / S porta segreta\n"
        "  @     posizione attuale del gruppo (" + nomi_party + ")\n"
        "  !     pericolo, trappola o nemico\n"
        "  $     tesoro o oggetto importante\n\n"
        "REGOLE TASSATIVE:\n"
        "- Non usare markdown (niente ```), scrivi direttamente i caratteri della mappa.\n"
        "- Non aggiungere tiri di dado o riquadri [PF: ...].\n"
        "- Sotto la mappa scrivi una breve legenda numerata delle stanze (es. 1. Ingresso, 2. Sala delle Colonne...).\n\n"
        "CRONACA DELL'ESPLORAZIONE:\n" + cronaca
    )

    richiesta = [{"role": "user", "parts": [{"text": prompt_cartografo}]}]
    system_cartografo = "Sei un generatore di mappe ASCII per dungeon di D&D. Rispondi solo con la mappa ASCII e una breve legenda."
    risposta = chiama_gemini(richiesta, api_key, system_cartografo, desc_attesa="sta disegnando la mappa ASCII")
    risposta = re.sub(r"^```[a-zA-Z]*\n?", "", risposta.strip())
    risposta = re.sub(r"\n?```$", "", risposta.strip())
    return risposta


def sanitize_pdf_text(text: str) -> str:
    replacements = {
        "\u2022": "-", "\u2013": "-", "\u2014": "--",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "à": "a'", "á": "a'", "è": "e'", "é": "e'", "ì": "i'", "í": "i'", "ò": "o'", "ó": "o'", "ù": "u'", "ú": "u'",
        "À": "A'", "Á": "A'", "È": "E'", "É": "E'", "Ì": "I'", "Í": "I'", "Ò": "O'", "Ó": "O'", "Ù": "U'", "Ú": "U'",
        "€": "EUR", "©": "(C)", "®": "(R)"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return "".join(c if ord(c) < 128 else "" for c in text)


def wrap_text_lines(text: str, max_chars: int = 90) -> list:
    righe = []
    for par in text.splitlines():
        p_str = par.strip()
        if not p_str:
            righe.append("")
            continue
        parole = p_str.split()
        cur = []
        cur_len = 0
        for w in parole:
            spazio = 1 if cur else 0
            if cur_len + len(w) + spazio <= max_chars:
                cur.append(w)
                cur_len += len(w) + spazio
            else:
                if cur:
                    righe.append(" ".join(cur))
                cur = [w]
                cur_len = len(w)
        if cur:
            righe.append(" ".join(cur))
    return righe


class PDFCanvas:
    def __init__(self, w=595.28, h=841.89):
        self.w = w
        self.h = h
        self.stream = []

    def rect(self, x, y, w, h, fill=None, stroke=None, line_width=1.0):
        cmd = []
        if line_width:
            cmd.append(f"{line_width:.2f} w")
        if stroke:
            cmd.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
        if fill:
            cmd.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        cmd.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        if fill and stroke:
            cmd.append("B")
        elif fill:
            cmd.append("f")
        elif stroke:
            cmd.append("S")
        self.stream.append("\n".join(cmd))

    def line(self, x1, y1, x2, y2, stroke=(0, 0, 0), line_width=1.0, dash=None):
        cmd = [f"{line_width:.2f} w", f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG"]
        if dash:
            cmd.append(f"[{' '.join(str(d) for d in dash)}] 0 d")
        else:
            cmd.append("[] 0 d")
        cmd.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")
        self.stream.append("\n".join(cmd))

    def circle(self, cx, cy, r, fill=None, stroke=None, line_width=1.0):
        k = 0.5522847498 * r
        cmd = []
        if line_width:
            cmd.append(f"{line_width:.2f} w")
        if stroke:
            cmd.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
        if fill:
            cmd.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        cmd.append(f"{cx+r:.2f} {cy:.2f} m")
        cmd.append(f"{cx+r:.2f} {cy+k:.2f} {cx+k:.2f} {cy+r:.2f} {cx:.2f} {cy+r:.2f} c")
        cmd.append(f"{cx-k:.2f} {cy+r:.2f} {cx-r:.2f} {cy+k:.2f} {cx-r:.2f} {cy:.2f} c")
        cmd.append(f"{cx-r:.2f} {cy-k:.2f} {cx-k:.2f} {cy-r:.2f} {cx:.2f} {cy-r:.2f} c")
        cmd.append(f"{cx+k:.2f} {cy-r:.2f} {cx+r:.2f} {cy-k:.2f} {cx+r:.2f} {cy:.2f} c")
        if fill and stroke:
            cmd.append("B")
        elif fill:
            cmd.append("f")
        elif stroke:
            cmd.append("S")
        self.stream.append("\n".join(cmd))

    def text(self, x, y, string, font="F1", size=10, color=(0, 0, 0)):
        clean = sanitize_pdf_text(str(string))
        safe_str = clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        cmd = [
            "BT",
            f"/{font} {size:.2f} Tf",
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg",
            f"{x:.2f} {y:.2f} Td",
            f"({safe_str}) Tj",
            "ET"
        ]
        self.stream.append("\n".join(cmd))

    def get_content(self):
        return "\n".join(self.stream)


def build_pdf_document(pages_content, w=595.28, h=841.89):
    fonts = [
        ('F1', '/Helvetica'),
        ('F2', '/Helvetica-Bold'),
        ('F3', '/Courier'),
        ('F4', '/Courier-Bold'),
        ('F5', '/Times-Bold')
    ]
    objs = []
    def add(d):
        objs.append(d)
        return len(objs)

    add(b'<< /Type /Catalog /Pages 2 0 R >>')
    add(None)
    font_map = {}
    for fn, bf in fonts:
        fid = add(f'<< /Type /Font /Subtype /Type1 /BaseFont {bf} >>'.encode('latin1'))
        font_map[fn] = fid
    font_res = ' '.join(f'/{k} {v} 0 R' for k, v in font_map.items())

    page_ids = []
    for content in pages_content:
        c_comp = zlib.compress(content.encode('latin1'))
        cid = add(f'<< /Length {len(c_comp)} /Filter /FlateDecode >>\nstream\n'.encode('latin1') + c_comp + b'\nendstream')
        pid = add(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}] /Contents {cid} 0 R /Resources << /Font << {font_res} >> >> >>'.encode('latin1'))
        page_ids.append(pid)

    kids = ' '.join(f'{pid} 0 R' for pid in page_ids)
    objs[1] = f'<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>'.encode('latin1')

    out = [b'%PDF-1.4\n']
    offsets = []
    for i, o in enumerate(objs):
        offsets.append(sum(len(x) for x in out))
        out.append(f'{i+1} 0 obj\n'.encode('latin1') + o + b'\nendobj\n')

    sx = sum(len(x) for x in out)
    out.append(f'xref\n0 {len(objs)+1}\n0000000000 65535 f \n'.encode('latin1'))
    for off in offsets:
        out.append(f'{off:010d} 00000 n \n'.encode('latin1'))
    out.append(f'trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{sx}\n%%EOF\n'.encode('latin1'))
    return b''.join(out)


def separa_mappa_e_legenda(testo_cartografo: str):
    righe = testo_cartografo.splitlines()
    righe_griglia = []
    righe_legenda = []
    in_legenda = False

    for riga in righe:
        r_strip = riga.strip()
        if not in_legenda:
            if re.match(r"^(legenda|stanze|ambienti|aree|note|1[\.\:\-\)])", r_strip, re.IGNORECASE):
                in_legenda = True
                righe_legenda.append(riga)
            elif any(c in riga for c in ["+", "|", "#", "@", "$", "!"]):
                righe_griglia.append(riga)
            elif righe_griglia and not r_strip:
                righe_griglia.append(riga)
            elif righe_griglia and not in_legenda and r_strip:
                in_legenda = True
                righe_legenda.append(riga)
        else:
            righe_legenda.append(riga)

    while righe_griglia and not righe_griglia[-1].strip():
        righe_griglia.pop()
    while righe_griglia and not righe_griglia[0].strip():
        righe_griglia.pop(0)

    return righe_griglia, righe_legenda


def disegna_mappa_vettoriale(canvas, righe_ascii, map_x=35, map_y=360, map_w=525, map_h=365):
    if not righe_ascii:
        canvas.text(map_x + 130, map_y + 180, "Nessuna stanza rilevata sulla mappa.", font="F1", size=11, color=(0.5, 0.5, 0.5))
        return

    R = len(righe_ascii)
    C = max(len(l) for l in righe_ascii)
    if R == 0 or C == 0:
        return

    padded = [l.ljust(C) for l in righe_ascii]
    cell_size = min(map_w / C, map_h / R)
    cell_size = max(7.0, min(cell_size, 20.0))

    tot_w = C * cell_size
    tot_h = R * cell_size
    origin_x = map_x + (map_w - tot_w) / 2
    origin_y = map_y + (map_h - tot_h) / 2

    # Draw faint blueprint grid
    grid_col = (0.80, 0.88, 0.94)
    for c in range(C + 1):
        gx = origin_x + c * cell_size
        canvas.line(gx, origin_y, gx, origin_y + tot_h, stroke=grid_col, line_width=0.5)
    for r in range(R + 1):
        gy = origin_y + r * cell_size
        canvas.line(origin_x, gy, origin_x + tot_w, gy, stroke=grid_col, line_width=0.5)

    def get_ch(r, c):
        if 0 <= r < R and 0 <= c < C:
            return padded[r][c]
        return ' '

    # 1. Floors & Corridors
    for r in range(R):
        for c in range(C):
            ch = padded[r][c]
            bx = origin_x + c * cell_size
            by = origin_y + (R - 1 - r) * cell_size
            if ch in ['.', '@', '!', '$', '0','1','2','3','4','5','6','7','8','9']:
                canvas.rect(bx, by, cell_size, cell_size, fill=(1, 1, 1))
            elif ch == '#':
                canvas.rect(bx, by, cell_size, cell_size, fill=(0.88, 0.88, 0.90), stroke=(0.7, 0.72, 0.75), line_width=0.5)

    # 2. Walls & Doors
    wall_col = (0.15, 0.15, 0.20)
    for r in range(R):
        for c in range(C):
            ch = padded[r][c]
            bx = origin_x + c * cell_size
            by = origin_y + (R - 1 - r) * cell_size
            cx = bx + cell_size / 2
            cy = by + cell_size / 2

            if ch == '-':
                canvas.line(bx, cy, bx + cell_size, cy, stroke=wall_col, line_width=2.5)
            elif ch == '|':
                canvas.line(cx, by, cx, by + cell_size, stroke=wall_col, line_width=2.5)
            elif ch == '+':
                left_c = get_ch(r, c - 1)
                right_c = get_ch(r, c + 1)
                up_c = get_ch(r - 1, c)
                down_c = get_ch(r + 1, c)
                conns = 0
                if left_c in ['-', '+', 'D', 'S', '/']:
                    canvas.line(bx, cy, cx, cy, stroke=wall_col, line_width=2.5); conns += 1
                if right_c in ['-', '+', 'D', 'S', '/']:
                    canvas.line(cx, cy, bx + cell_size, cy, stroke=wall_col, line_width=2.5); conns += 1
                if up_c in ['|', '+', 'D', 'S', '/']:
                    canvas.line(cx, cy, cx, by + cell_size, stroke=wall_col, line_width=2.5); conns += 1
                if down_c in ['|', '+', 'D', 'S', '/']:
                    canvas.line(cx, by, cx, cy, stroke=wall_col, line_width=2.5); conns += 1
                if conns == 0:
                    canvas.line(bx + 2, cy, bx + cell_size - 2, cy, stroke=wall_col, line_width=2.5)
                    canvas.line(cx, by + 2, cx, by + cell_size - 2, stroke=wall_col, line_width=2.5)
            elif ch == 'D':
                left_c = get_ch(r, c - 1)
                right_c = get_ch(r, c + 1)
                if left_c in ['-', '+'] or right_c in ['-', '+']:
                    canvas.rect(bx + 1, cy - 3, cell_size - 2, 6, fill=(0.55, 0.27, 0.07), stroke=wall_col, line_width=1.0)
                else:
                    canvas.rect(cx - 3, by + 1, 6, cell_size - 2, fill=(0.55, 0.27, 0.07), stroke=wall_col, line_width=1.0)
            elif ch == 'S':
                canvas.circle(cx, cy, cell_size * 0.35, fill=(0.95, 0.95, 0.95), stroke=wall_col, line_width=1.0)
                canvas.text(cx - 2.5, cy - 3.0, "S", font="F2", size=cell_size * 0.6, color=wall_col)
            elif ch == '/':
                canvas.line(cx - 2, cy - 3, cx + 3, cy + 3, stroke=(0.55, 0.27, 0.07), line_width=2.0)

    # 3. Features & Tokens
    for r in range(R):
        for c in range(C):
            ch = padded[r][c]
            bx = origin_x + c * cell_size
            by = origin_y + (R - 1 - r) * cell_size
            cx = bx + cell_size / 2
            cy = by + cell_size / 2
            if ch == '@':
                canvas.circle(cx, cy, cell_size * 0.42, fill=(0.85, 0.10, 0.10), stroke=(1, 1, 1), line_width=1.5)
                canvas.text(cx - 3.2, cy - 3.0, "P", font="F2", size=cell_size * 0.65, color=(1, 1, 1))
            elif ch == '!':
                canvas.circle(cx, cy, cell_size * 0.38, fill=(0.88, 0.35, 0.05), stroke=(1, 1, 1), line_width=1.0)
                canvas.text(cx - 2.0, cy - 3.0, "!", font="F2", size=cell_size * 0.65, color=(1, 1, 1))
            elif ch == '$':
                canvas.circle(cx, cy, cell_size * 0.38, fill=(0.88, 0.68, 0.12), stroke=(0.4, 0.3, 0.0), line_width=1.0)
                canvas.text(cx - 2.5, cy - 3.0, "$", font="F2", size=cell_size * 0.65, color=(0.2, 0.15, 0.0))
            elif ch.isdigit():
                canvas.circle(cx, cy, cell_size * 0.44, fill=(0.20, 0.30, 0.48), stroke=(1, 1, 1), line_width=1.0)
                canvas.text(cx - 3.0, cy - 3.2, ch, font="F2", size=cell_size * 0.65, color=(1, 1, 1))
            elif ch == '.':
                canvas.circle(cx, cy, 1.0, fill=(0.65, 0.65, 0.65))


def estrai_dossier_stanze(righe_legenda):
    stanze = []
    corrente = None
    for r in righe_legenda:
        r_str = r.strip()
        if not r_str or re.match(r"^(legenda|stanze|ambienti|aree|note)", r_str, re.IGNORECASE):
            continue
        m = re.match(r"^(\d+)[\.\:\-\)]\s*(.*)", r_str)
        if m:
            if corrente:
                stanze.append(corrente)
            num = m.group(1)
            resto = m.group(2)
            if ":" in resto:
                tit, desc = resto.split(":", 1)
            elif "-" in resto:
                tit, desc = resto.split("-", 1)
            else:
                tit, desc = resto, ""
            corrente = {"num": num, "titolo": tit.strip(), "desc": desc.strip()}
        elif corrente:
            corrente["desc"] += (" " if corrente["desc"] else "") + r_str
    if corrente:
        stanze.append(corrente)
    return stanze


def esporta_mappa_pdf_a4(avventura: dict, eroi_party: list, testo_mappa: str = None, api_key: str = None) -> str:
    dir_mappe = MAPPE_DIR
    os.makedirs(dir_mappe, exist_ok=True)
    titolo_pulito = re.sub(r"[^\w\-_]", "_", avventura.get("titolo", "avventura")).strip("_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    nome_file = f"mappa_{titolo_pulito}_{timestamp}_A4.pdf"
    percorso_completo = os.path.join(dir_mappe, nome_file)

    if not testo_mappa:
        if api_key:
            testo_mappa = genera_mappa_ascii(avventura, api_key, eroi_party)
        else:
            testo_mappa = avventura.get("ultima_mappa_ascii", "+---+\n| 1 |\n+---+")

    avventura["ultima_mappa_ascii"] = testo_mappa

    righe_griglia, righe_legenda = separa_mappa_e_legenda(testo_mappa)
    dossier = estrai_dossier_stanze(righe_legenda)

    turni = len(avventura.get("storia", [])) // 2
    minuti = turni * 10
    tempo_str = f"{minuti // 60}h {minuti % 60:02d}m"
    st_dungeon = avventura.get("stato_dungeon", {})
    luce_amb = st_dungeon.get("luce_ambientale", False)
    amb_nome = st_dungeon.get("ambiente_nome", "Taverna" if luce_amb else "Dungeon")
    t_rimasti = st_dungeon.get("torcia_turni", avventura.get("torcia_turni_rimasti", 6))
    if luce_amb:
        luce_str = f"Luce Ambientale ({amb_nome})"
    elif not st_dungeon.get("torcia_attiva", True) or avventura.get("buio_totale"):
        luce_str = "BUIO TOTALE (-4 TxC/CA)"
    else:
        luce_str = f"Luce Torcia ({t_rimasti}/6 t)"
    party_str = ", ".join(f"{e['nome']} ({e['classe']} L.{e['livello']})" for e in eroi_party)

    # PAGE 1: Tactical Map
    p1 = PDFCanvas()
    p1.rect(20, 20, 555.28, 801.89, stroke=(0.54, 0.0, 0.0), line_width=2.5)
    p1.rect(24, 24, 547.28, 793.89, stroke=(0.85, 0.65, 0.13), line_width=1.0)

    p1.rect(25, 765, 545.28, 52, fill=(0.54, 0.0, 0.0))
    p1.text(40, 796, "DUNGEONS & DRAGONS BECMI - SCATOLA ROSSA", "F2", 13, (1, 0.85, 0.2))
    p1.text(40, 778, f"MAPPA TATTICA: {avventura.get('titolo', 'DUNGEON').upper()}", "F2", 12, (1, 1, 1))

    p1.rect(25, 742, 545.28, 23, fill=(0.95, 0.94, 0.90), stroke=(0.8, 0.8, 0.8), line_width=0.5)
    meta_txt = f"Party: {party_str}  |  Turno: {turni} ({tempo_str})  |  {luce_str}  |  Scala: 1 quadretto = 10 ft (3m)"
    p1.text(35, 750, meta_txt, "F1", 8.5, (0.2, 0.2, 0.2))

    p1.rect(35, 360, 525, 365, fill=(0.97, 0.97, 0.94), stroke=(0.54, 0.0, 0.0), line_width=1.5)
    disegna_mappa_vettoriale(p1, righe_griglia, map_x=35, map_y=360, map_w=525, map_h=365)

    p1.text(515, 705, "NORD", "F2", 8, (0.54, 0.0, 0.0))
    p1.line(528, 675, 528, 700, stroke=(0.54, 0.0, 0.0), line_width=2.0)
    p1.line(528, 700, 524, 692, stroke=(0.54, 0.0, 0.0), line_width=1.5)
    p1.line(528, 700, 532, 692, stroke=(0.54, 0.0, 0.0), line_width=1.5)

    p1.rect(35, 175, 525, 170, fill=(0.98, 0.98, 0.97), stroke=(0.85, 0.65, 0.13), line_width=1.0)
    p1.rect(35, 323, 525, 22, fill=(0.85, 0.65, 0.13))
    p1.text(45, 330, "LEGENDA STANZE & AREE ESPLORATE", "F2", 10, (0.1, 0.1, 0.1))

    cur_y = 305
    if dossier:
        for st in dossier[:5]:
            p1.circle(52, cur_y + 3, 7, fill=(0.20, 0.30, 0.48))
            p1.text(49, cur_y, st["num"], "F2", 8, (1, 1, 1))
            tit_str = st["titolo"] if st["titolo"] else f"Area {st['num']}"
            p1.text(65, cur_y + 1, tit_str, "F2", 9, (0.1, 0.1, 0.1))
            desc_righe = wrap_text_lines(st["desc"], max_chars=85)
            cur_y -= 12
            for dr in desc_righe[:2]:
                p1.text(65, cur_y + 1, dr, "F1", 8.5, (0.25, 0.25, 0.25))
                cur_y -= 11
            cur_y -= 3
            if cur_y < 185:
                break
    else:
        for lr in righe_legenda[:7]:
            p1.text(45, cur_y, lr, "F1", 8.5, (0.1, 0.1, 0.1))
            cur_y -= 13

    p1.rect(35, 45, 525, 115, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
    p1.rect(35, 140, 525, 20, fill=(0.92, 0.92, 0.92))
    p1.text(45, 146, "SEGNI CONVENZIONALI & APPUNTI DEL CARTOGRAFO", "F2", 9, (0.2, 0.2, 0.2))
    p1.text(45, 125, "[P] Posizione Party  |  [D] Porta Chiusa  |  [/] Porta Aperta  |  [S] Porta Segreta  |  [!] Pericolo  |  [$] Tesoro", "F2", 8.5, (0.3, 0.3, 0.3))
    p1.text(45, 105, "Appunti Spedizione:", "F2", 8.5, (0.54, 0, 0))
    note_txt = avventura.get("note") or "Nessuna annotazione particolare finora. Porte e passaggi segreti rilevati sulla mappa."
    note_lines = wrap_text_lines(note_txt, max_chars=92)
    ny = 92
    for nl in note_lines[:3]:
        p1.text(45, ny, nl, "F1", 8.5, (0.2, 0.2, 0.2))
        ny -= 11

    p1.text(35, 28, f"D&D Scatola Rossa BECMI - Mappa di Campagna A4 (Pagina 1 di 2) - AI DM: {MODELLO}", "F1", 7.5, (0.5, 0.5, 0.5))

    # PAGE 2: Dossier & ASCII Blueprint
    p2 = PDFCanvas()
    p2.rect(20, 20, 555.28, 801.89, stroke=(0.54, 0.0, 0.0), line_width=2.5)
    p2.rect(24, 24, 547.28, 793.89, stroke=(0.85, 0.65, 0.13), line_width=1.0)
    p2.rect(25, 765, 545.28, 52, fill=(0.54, 0.0, 0.0))
    p2.text(40, 796, "DUNGEONS & DRAGONS BECMI - SCATOLA ROSSA", "F2", 13, (1, 0.85, 0.2))
    p2.text(40, 778, "DOSSIER STANZE, GRIGLIA CARTOGRAFICA & SCHEDA ROSTER", "F2", 12, (1, 1, 1))

    p2.rect(25, 742, 545.28, 23, fill=(0.95, 0.94, 0.90), stroke=(0.8, 0.8, 0.8), line_width=0.5)
    p2.text(35, 750, "Registro Cartografico & Documento di Supporto per DM e Giocatori", "F1", 8.5, (0.2, 0.2, 0.2))

    p2.rect(35, 480, 525, 245, fill=(0.10, 0.12, 0.15), stroke=(0.85, 0.65, 0.13), line_width=1.2)
    p2.rect(35, 705, 525, 20, fill=(0.85, 0.65, 0.13))
    p2.text(45, 711, "GRIGLIA CARTOGRAFICA ASCII ORIGINALE", "F2", 9, (0.1, 0.1, 0.1))

    y_asc = 688
    for al in righe_griglia[:15]:
        p2.text(48, y_asc, al, font="F4", size=9.5, color=(0.25, 0.95, 0.45))
        y_asc -= 13

    p2.rect(35, 335, 525, 130, fill=(0.98, 0.98, 0.97), stroke=(0.54, 0.0, 0.0), line_width=1.0)
    p2.rect(35, 445, 525, 20, fill=(0.54, 0.0, 0.0))
    p2.text(45, 451, "COMPAGNIA DEGLI AVVENTURIERI (PARTY ROSTER)", "F2", 9.5, (1, 1, 1))

    py = 428
    for e in eroi_party[:4]:
        s_slots = e.get("incantesimi_memorizzati", [])
        inc_str = f" | Magia: {', '.join(s_slots)}" if s_slots else ""
        p2.text(45, py, f"{e['nome']} - {e['classe']} Livello {e['livello']} ({e.get('allineamento', 'Neutrale')})", "F2", 9, (0.15, 0.15, 0.15))
        p2.text(45, py - 11, f"PF: {e['pf_attuali']}/{e['pf_max']}  |  CA: {e['ca']}  |  MO: {e['mo']}  |  PE: {e['pe']}{inc_str}", "F1", 8.5, (0.3, 0.3, 0.3))
        p2.text(45, py - 22, f"Attacco: {e.get('attacco', 'Standard')}  |  TS: {e.get('ts', 'Standard')}", "F1", 7.5, (0.45, 0.45, 0.45))
        py -= 32

    p2.rect(35, 45, 525, 275, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
    p2.rect(35, 300, 525, 20, fill=(0.92, 0.92, 0.92))
    p2.text(45, 306, "DETTAGLIO STANZE, DIARIO DEL CARTOGRAFO & ANNOTAZIONI AL TAVOLO", "F2", 9, (0.2, 0.2, 0.2))

    dy = 282
    for st in dossier:
        p2.text(45, dy, f"STANZA {st['num']}: {st['titolo'].upper()}", "F2", 8.5, (0.54, 0, 0))
        dy -= 11
        for dl in wrap_text_lines(st["desc"], max_chars=90)[:3]:
            p2.text(45, dy, dl, "F1", 8, (0.2, 0.2, 0.2))
            dy -= 10
        dy -= 4
        if dy < 120:
            break

    p2.text(45, dy, "Note del Master / Giocatore (Annotazioni a penna durante la sessione):", "F2", 8, (0.4, 0.4, 0.4))
    dy -= 10
    while dy > 55:
        p2.line(45, dy, 545, dy, stroke=(0.82, 0.82, 0.82), line_width=0.5, dash=[2, 2])
        dy -= 14

    p2.text(35, 28, f"D&D Scatola Rossa BECMI - Mappa di Campagna A4 (Pagina 2 di 2) - AI DM: {MODELLO}", "F1", 7.5, (0.5, 0.5, 0.5))

    pdf_bytes = build_pdf_document([p1.get_content(), p2.get_content()])
    with open(percorso_completo, "wb") as f:
        f.write(pdf_bytes)

    suona("levelup")
    print(f"\n{VERDE}{GRASSETTO}🗺️ Mappa A4 PDF per la campagna generata con successo!{RESET}")
    print(f"{CIANO}Percorso file:{RESET} {os.path.abspath(percorso_completo)}")
    return os.path.abspath(percorso_completo)


def esporta_scheda_pdf_a4(eroe: dict) -> str:
    sincronizza_statistiche_becmi(eroe)
    os.makedirs(SCHEDE_DIR, exist_ok=True)
    nome_pulito = re.sub(r"[^\w\-_]", "_", eroe.get("nome", "eroe")).strip("_")
    percorso_completo = os.path.join(SCHEDE_DIR, f"scheda_{nome_pulito}_A4.pdf")

    c = PDFCanvas()
    # Doppio bordo decorativo (rosso e oro)
    c.rect(20, 20, 555.28, 801.89, stroke=(0.54, 0.0, 0.0), line_width=2.5)
    c.rect(24, 24, 547.28, 793.89, stroke=(0.85, 0.65, 0.13), line_width=1.0)

    # Banner Intestazione
    c.rect(25, 765, 545.28, 52, fill=(0.54, 0.0, 0.0))
    c.text(40, 796, "DUNGEONS & DRAGONS BECMI - SCATOLA ROSSA", "F2", 13, (1, 0.85, 0.2))
    c.text(40, 778, f"SCHEDA UFFICIALE DEL PERSONAGGIO: {eroe['nome'].upper()}", "F2", 12, (1, 1, 1))

    # Striscia Identita & Regole
    c.rect(25, 738, 545.28, 24, fill=(0.95, 0.94, 0.90), stroke=(0.8, 0.8, 0.8), line_width=0.5)
    soglia = prossima_soglia_pe(eroe["classe"], eroe["livello"])
    soglia_str = f" / {soglia} PE" if soglia else " (Max Liv.)"
    info_txt = f"Classe: {eroe['classe']} Liv.{eroe['livello']}  |  Allineamento: {eroe['allineamento']}  |  PE: {eroe['pe']}{soglia_str}  |  Regole: {eroe.get('fascia_becmi', 'BECMI')}"
    c.text(35, 746, info_txt, "F1", 8.5, (0.2, 0.2, 0.2))

    # Colonna Sinistra: 6 Caratteristiche Base
    c.rect(35, 415, 160, 315, fill=(0.98, 0.98, 0.97), stroke=(0.85, 0.65, 0.13), line_width=1.0)
    c.rect(35, 708, 160, 22, fill=(0.85, 0.65, 0.13))
    c.text(45, 715, "CARATTERISTICHE BASE", "F2", 9.5, (0.1, 0.1, 0.1))

    attrs = [
        ("FORZA", eroe.get("forza", 10), "FOR", "TxC CaC, danni e porte"),
        ("INTELLIGENZA", eroe.get("intelligenza", 10), "INT", "Lingue, bonus PE"),
        ("SAGGEZZA", eroe.get("saggezza", 10), "SAG", "TS contro incantesimi"),
        ("DESTREZZA", eroe.get("destrezza", 10), "DES", "TxC distanza, bonus CA"),
        ("COSTITUZIONE", eroe.get("costituzione", 10), "COS", "Modificatore PF per DV"),
        ("CARISMA", eroe.get("carisma", 10), "CAR", "Reazione PNG, gregari")
    ]

    ay = 675
    for nome_attr, val, abbrev, nota in attrs:
        mod = mod_caratteristica(val)
        mod_str = f"{mod:+d}"
        c.rect(42, ay - 5, 34, 28, fill=(0.92, 0.94, 0.97), stroke=(0.54, 0.0, 0.0), line_width=1.0)
        c.text(49, ay + 6, str(val), "F2", 13, (0.1, 0.1, 0.1))
        c.text(46, ay - 2, f"({mod_str})", "F2", 8.5, (0.54, 0.0, 0.0))
        c.text(82, ay + 10, nome_attr, "F2", 8.5, (0.15, 0.15, 0.15))
        c.text(82, ay - 1, nota, "F1", 7.5, (0.4, 0.4, 0.4))
        ay -= 46

    # Colonna Sinistra: Borsello & Movimento
    c.rect(35, 275, 160, 130, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
    c.rect(35, 385, 160, 20, fill=(0.92, 0.92, 0.92))
    c.text(45, 391, "BORSELLO & MOVIMENTO", "F2", 9, (0.2, 0.2, 0.2))

    c.text(45, 368, f"Monete d'Oro (MO): {eroe.get('mo', 0)}", "F2", 10, (0.75, 0.55, 0.05))
    c.text(45, 353, "Equivalenze BECMI:", "F2", 7.5, (0.4, 0.4, 0.4))
    c.text(45, 341, "1 MO = 10 MA = 100 MR", "F1", 7.5, (0.3, 0.3, 0.3))
    c.text(45, 323, "Tassi Movimento:", "F2", 8, (0.2, 0.2, 0.2))
    c.text(45, 309, "Esplorazione: 60' (20m)/t", "F1", 7.5, (0.3, 0.3, 0.3))
    c.text(45, 297, "Combattimento: 20' (6m)/r", "F1", 7.5, (0.3, 0.3, 0.3))
    c.text(45, 285, "Corsa rapida: 60' (20m)/r", "F1", 7.5, (0.3, 0.3, 0.3))

    # Colonna Sinistra: Dadi Vita & Riposo
    c.rect(35, 115, 160, 150, fill=(0.98, 0.98, 0.97), stroke=(0.7, 0.7, 0.7), line_width=0.8)
    c.rect(35, 245, 160, 20, fill=(0.92, 0.92, 0.92))
    c.text(45, 251, "DADI VITA & GUARIGIONE", "F2", 9, (0.2, 0.2, 0.2))
    dati_cl = trova_dati_classe(eroe["classe"])
    dv_cl = dati_cl.get("dado_vita", 8)
    c.text(45, 228, f"Dado Vita Classe: d{dv_cl}", "F2", 8.5, (0.2, 0.2, 0.2))
    c.text(45, 214, "Riposo Breve (10m): Ripristino", "F1", 7.5, (0.3, 0.3, 0.3))
    c.text(45, 201, "Riposo Lungo (8h): 1d3 PF nat.", "F1", 7.5, (0.3, 0.3, 0.3))
    c.text(45, 188, "Ricarica 100% slot magia.", "F1", 7.5, (0.3, 0.3, 0.3))
    c.text(45, 165, "Lingue Parlate:", "F2", 8, (0.2, 0.2, 0.2))
    c.text(45, 151, f"Comune, {eroe['allineamento']}", "F1", 7.5, (0.3, 0.3, 0.3))
    c.text(45, 133, "Capacita di Carico: 1600 cn", "F1", 7.5, (0.4, 0.4, 0.4))

    # Colonna Destra: Schede di Combattimento (PF, CA, THAC0)
    # Box PF
    c.rect(205, 630, 115, 100, fill=(0.99, 0.95, 0.95), stroke=(0.7, 0.1, 0.1), line_width=1.5)
    c.rect(205, 710, 115, 20, fill=(0.7, 0.1, 0.1))
    c.text(215, 716, "PUNTI FERITA (PF)", "F2", 8.5, (1, 1, 1))
    c.text(225, 672, f"{eroe.get('pf_attuali', 1)}", "F2", 24, (0.7, 0.1, 0.1))
    c.text(265, 668, f"/ {eroe.get('pf_max', 1)} max", "F1", 10, (0.4, 0.4, 0.4))
    mod_cos = mod_caratteristica(eroe.get('costituzione', 10))
    c.text(215, 642, f"Dado Vita: {eroe['livello']}d{dv_cl} {mod_cos:+d}", "F1", 8, (0.3, 0.3, 0.3))

    # Box CA
    c.rect(328, 630, 110, 100, fill=(0.94, 0.96, 0.99), stroke=(0.1, 0.3, 0.6), line_width=1.5)
    c.rect(328, 710, 110, 20, fill=(0.1, 0.3, 0.6))
    c.text(338, 716, "CLASSE ARMATURA", "F2", 8.5, (1, 1, 1))
    c.text(360, 672, f"{eroe.get('ca', 9)}", "F2", 28, (0.1, 0.3, 0.6))
    armatura_descr = "Senza armatura"
    for eq in eroe.get("equip", []):
        eq_l = eq.lower()
        if any(a in eq_l for a in ["piastre", "maglia", "cuoio", "scudo"]):
            armatura_descr = eq
            break
    c.text(338, 642, armatura_descr[:16], "F1", 8, (0.3, 0.3, 0.3))

    # Box Attacco / THAC0
    c.rect(446, 630, 114, 100, fill=(0.95, 0.98, 0.95), stroke=(0.1, 0.5, 0.2), line_width=1.5)
    c.rect(446, 710, 114, 20, fill=(0.1, 0.5, 0.2))
    c.text(456, 716, "ATTACCO & THAC0", "F2", 8.5, (1, 1, 1))
    thac0_val = eroe.get("thac0", 19)
    c.text(465, 674, f"THAC0 {thac0_val}", "F2", 14, (0.1, 0.5, 0.2))
    mod_for = mod_caratteristica(eroe.get('forza', 10))
    mod_des = mod_caratteristica(eroe.get('destrezza', 10))
    c.text(456, 652, f"CaC: {mod_for:+d} TxC / Danni", "F1", 8, (0.3, 0.3, 0.3))
    c.text(456, 638, f"Distanza: {mod_des:+d} TxC", "F1", 8, (0.3, 0.3, 0.3))

    # Tiri Salvezza BECMI (5 categorie)
    c.rect(205, 530, 355, 90, fill=(0.98, 0.98, 0.97), stroke=(0.54, 0.0, 0.0), line_width=1.0)
    c.rect(205, 600, 355, 20, fill=(0.54, 0.0, 0.0))
    c.text(215, 606, "TIRI SALVEZZA BECMI (TIRI DI PROTEZIONE SU 1D20)", "F2", 8.5, (1, 1, 1))

    ts_str = eroe.get("ts", "")
    m_morte = re.search(r"(?:Morte/Veleno|Raggio)\s+(\d+)", ts_str)
    m_bacch = re.search(r"Bacchette\s+(\d+)", ts_str)
    m_paral = re.search(r"Paralisi\s+(\d+)", ts_str)
    m_soffio = re.search(r"Soffio\s+(\d+)", ts_str)
    m_incant = re.search(r"Incantesimi\s+(\d+)", ts_str)

    val_morte = m_morte.group(1) if m_morte else "12"
    val_bacch = m_bacch.group(1) if m_bacch else "13"
    val_paral = m_paral.group(1) if m_paral else "14"
    val_soffio = m_soffio.group(1) if m_soffio else "15"
    val_incant = m_incant.group(1) if m_incant else "16"

    ts_categories = [
        ("RAGGIO MORTE / VELENO", val_morte),
        ("BACCHETTE MAGICHE", val_bacch),
        ("PARALISI / PIETRIFICAZ.", val_paral),
        ("SOFFIO DI DRAGO", val_soffio),
        ("BASTONI / INCANTESIMI", val_incant)
    ]
    tsx = 212
    for cat, val in ts_categories:
        c.rect(tsx, 540, 65, 52, fill=(1, 1, 1), stroke=(0.8, 0.8, 0.8), line_width=0.5)
        c.text(tsx + 22, 568, str(val), "F2", 14, (0.54, 0.0, 0.0))
        words = cat.split()
        line1 = " ".join(words[:len(words)//2 + 1])
        line2 = " ".join(words[len(words)//2 + 1:])
        c.text(tsx + 4, 552, line1[:11], "F1", 6, (0.3, 0.3, 0.3))
        c.text(tsx + 4, 544, line2[:11], "F1", 6, (0.3, 0.3, 0.3))
        tsx += 68

    # Privilegi & Abilita di Classe
    c.rect(205, 415, 355, 105, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
    c.rect(205, 500, 355, 20, fill=(0.85, 0.65, 0.13))
    c.text(215, 506, "PRIVILEGI & ABILITA DI CLASSE", "F2", 9, (0.1, 0.1, 0.1))

    ab_lines = wrap_text_lines(eroe.get("abilita_classe", ""), max_chars=62)
    aby = 482
    for abl in ab_lines[:6]:
        c.text(215, aby, abl, "F1", 8, (0.2, 0.2, 0.2))
        aby -= 12

    # Verifica se Incantatore
    slots = slot_incantesimi_per_cerchio(eroe["classe"], eroe["livello"], eroe.get("immortale", False))
    if slots:
        # Box Equipaggiamento (Superiore)
        c.rect(205, 260, 355, 145, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
        c.rect(205, 385, 355, 20, fill=(0.92, 0.92, 0.92))
        c.text(215, 391, "EQUIPAGGIAMENTO & DOTAZIONE", "F2", 9, (0.2, 0.2, 0.2))

        eq_y = 368
        for item in eroe.get("equip", []):
            c.text(215, eq_y, f"- {item}", "F1", 8, (0.15, 0.15, 0.15))
            eq_y -= 12
            if eq_y < 268:
                break

        # Box Grimorio & Incantesimi (Inferiore)
        c.rect(205, 115, 355, 135, fill=(0.98, 0.98, 0.99), stroke=(0.1, 0.3, 0.6), line_width=0.8)
        c.rect(205, 230, 355, 20, fill=(0.1, 0.3, 0.6))
        c.text(215, 236, "GRIMORIO & INCANTESIMI MEMORIZZATI", "F2", 9, (1, 1, 1))

        slots_str = " | ".join(f"{c_num}° Cerchio: {tot} slot" for c_num, tot in sorted(slots.items()))
        c.text(215, 214, f"Slot Giornalieri: {slots_str}", "F2", 8, (0.1, 0.3, 0.6))

        sp_y = 198
        prep = eroe.get("incantesimi_memorizzati", [])
        if prep:
            for inc in prep:
                info = INCANTESIMI_DATABASE.get(inc, {})
                c_num = info.get("cerchio", 1)
                desc = info.get("desc", "")
                c.text(215, sp_y, f"* {inc} ({c_num}° Cerchio)", "F2", 8, (0.1, 0.1, 0.1))
                if desc:
                    c.text(320, sp_y, f"- {desc[:42]}", "F1", 7.5, (0.4, 0.4, 0.4))
                sp_y -= 13
                if sp_y < 125:
                    break
        else:
            c.text(215, sp_y, "Nessun incantesimo attualmente memorizzato.", "F1", 8, (0.5, 0.5, 0.5))
    else:
        # Box Equipaggiamento Esteso per non-incantatori
        c.rect(205, 115, 355, 290, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
        c.rect(205, 385, 355, 20, fill=(0.92, 0.92, 0.92))
        c.text(215, 391, "EQUIPAGGIAMENTO, ARMI & DOTAZIONE DI VIAGGIO", "F2", 9, (0.2, 0.2, 0.2))

        eq_y = 368
        for item in eroe.get("equip", []):
            c.text(215, eq_y, f"- {item}", "F1", 8, (0.15, 0.15, 0.15))
            eq_y -= 12
            if eq_y < 125:
                break

    # Box Inferiore: Appunti & Note a Penna al Tavolo
    c.rect(35, 45, 525, 60, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
    c.rect(35, 88, 525, 17, fill=(0.94, 0.94, 0.94))
    c.text(45, 93, "APPUNTI DI CAMPAGNA & ANNOTAZIONI AL TAVOLO (A PENNA)", "F2", 8, (0.3, 0.3, 0.3))
    c.line(45, 70, 545, 70, stroke=(0.85, 0.85, 0.85), line_width=0.5, dash=[2, 2])
    c.line(45, 55, 545, 55, stroke=(0.85, 0.85, 0.85), line_width=0.5, dash=[2, 2])

    # Footer
    c.text(35, 28, "D&D Scatola Rossa BECMI • Scheda Ufficiale Personaggio (A4) • AI Dungeon Master", "F1", 7.5, (0.5, 0.5, 0.5))

    pdf_bytes = build_pdf_document([c.get_content()])
    with open(percorso_completo, "wb") as f:
        f.write(pdf_bytes)

    suona("tesoro")
    print(f"\n{VERDE}{GRASSETTO}📜 Scheda Personaggio A4 PDF generata con successo!{RESET}")
    print(f"{CIANO}Eroe:{RESET} {eroe['nome']} ({eroe['classe']} Liv.{eroe['livello']})")
    print(f"{CIANO}Percorso file:{RESET} {os.path.abspath(percorso_completo)}")
    return os.path.abspath(percorso_completo)


def calcola_hash_manuale_comandi() -> str:
    payload = f"{HELP_TESTO}\nv9.1.5_becmi_manual"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def aggiorna_manuale_comandi_pdf(forza: bool = False, silenzioso: bool = False) -> str:
    percorso_manuale = os.path.join(os.getcwd(), MANUALE_FILE)
    hash_corrente = calcola_hash_manuale_comandi()

    hash_salvato = None
    if os.path.exists(MANUALE_HASH_FILE):
        try:
            with open(MANUALE_HASH_FILE, "r", encoding="utf-8") as f:
                hash_salvato = f.read().strip()
        except Exception:
            hash_salvato = None

    if not forza and os.path.exists(percorso_manuale) and hash_salvato == hash_corrente:
        return percorso_manuale

    # Genera le 2 pagine del manuale
    p1 = PDFCanvas()
    p1.rect(20, 20, 555.28, 801.89, stroke=(0.54, 0.0, 0.0), line_width=2.5)
    p1.rect(24, 24, 547.28, 793.89, stroke=(0.85, 0.65, 0.13), line_width=1.0)

    # Banner Header Pagina 1
    p1.rect(25, 765, 545.28, 52, fill=(0.54, 0.0, 0.0))
    p1.text(40, 796, "DUNGEONS & DRAGONS BECMI - SCATOLA ROSSA", "F2", 13, (1, 0.85, 0.2))
    p1.text(40, 778, "MANUALE DEI COMANDI & GUIDA RAPIDA DI GIOCO (PARTE 1)", "F2", 12, (1, 1, 1))

    p1.rect(25, 742, 545.28, 23, fill=(0.95, 0.94, 0.90), stroke=(0.8, 0.8, 0.8), line_width=0.5)
    p1.text(35, 750, "Istruzioni Ufficiali BECMI  |  Terminale AI DM  |  Documento Sincronizzato con il Codice", "F1", 8.5, (0.2, 0.2, 0.2))

    # Sezione 1: Azioni del Party & Comandi Base
    p1.rect(35, 575, 525, 155, fill=(0.98, 0.98, 0.97), stroke=(0.85, 0.65, 0.13), line_width=1.0)
    p1.rect(35, 708, 525, 22, fill=(0.85, 0.65, 0.13))
    p1.text(45, 715, "1. AZIONI DI GIOCO, ESPLORAZIONE & GRUPPO", "F2", 9.5, (0.1, 0.1, 0.1))

    p1.text(45, 692, "Linguaggio Naturale: Digita qualsiasi azione in italiano (es. 'Avanzo con la spada', 'Esamino la porta').", "F2", 8.5, (0.1, 0.1, 0.1))
    p1.text(45, 680, "Il Dungeon Master AI risolvera' la scena applicando le regole BECMI, calcolando tiri e difficolta'.", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 665, "/gruppo <azione> : Invia un'azione collettiva coordinata per l'intero gruppo in un singolo turno.", "F2", 8.5, (0.54, 0, 0))
    p1.text(45, 650, "/salta           : Salta il turno del personaggio corrente, mettendolo in posizione difensiva e vigilanza.", "F2", 8.5, (0.54, 0, 0))
    p1.text(45, 635, "/party           : Mostra il riepilogo rapido di tutti i membri della compagnia (PF, CA, MO, Livello).", "F2", 8.5, (0.54, 0, 0))
    p1.text(45, 620, "/storico         : Rilegge e mostra gli ultimi turni dell'avventura per rinfrescare la memoria del party.", "F2", 8.5, (0.54, 0, 0))
    p1.text(45, 605, "/nota <testo>    : Salva un appunto nel diario SQLite di campagna (digita /nota senza testo per leggerlo).", "F2", 8.5, (0.54, 0, 0))
    p1.text(45, 590, "/riassunto       : Comprime la memoria della conversazione per mantenere il DM rapido e reattivo.", "F2", 8.5, (0.54, 0, 0))

    # Sezione 2: Tempo del Dungeon, Torce & Buio
    p1.rect(35, 395, 525, 170, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
    p1.rect(35, 543, 525, 22, fill=(0.54, 0.0, 0.0))
    p1.text(45, 550, "2. TEMPO DEL DUNGEON, ILLUMINAZIONE, TORCE & BUIO TOTALE", "F2", 9.5, (1, 1, 1))

    p1.text(45, 527, "Turno Esplorativo (10 Minuti): Nei dungeon 1 turno = 10 min. In taverne, citta o di giorno la luce e naturale.", "F2", 8.5, (0.1, 0.1, 0.1))
    p1.text(45, 513, "Durata Torcia (6 Turni): Conta solo nei dungeon bui! A zero viene rinnovata solo se non e stata spenta.", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 499, "Spegni Torcia: Scrivi 'spegni torcia' o '/torcia off' per riporla nello zaino e fermare il consumo.", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 485, "Condizione Buio Totale: Nel buio sotterraneo senza torce si applica -4 al TxC, -4 alla CA e cecita.", "F2", 8.5, (0.7, 0.1, 0.1))
    p1.text(45, 471, "Incontri Erranti (/incontri): Bilanciati (1 su 1d8 ogni 4 turni, cooldown) o disattivabili (/incontri off).", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 457, "/torcia [on|off|auto] : Accende, spegne/riponi nello zaino o gestisce scorte e auto-ricambio a fine durata.", "F2", 8.5, (0.54, 0, 0))
    p1.text(45, 443, "/ambiente [taverna|dungeon|auto]: Controlla o imposta l'ambiente di luce naturale o buio sotterraneo.", "F2", 8.5, (0.54, 0, 0))
    p1.text(45, 429, "/riposo          : Riposo Breve (10m) o Lungo (8h con recupero 1d3 PF e ricarica slot incantesimi).", "F2", 8.5, (0.54, 0, 0))

    # Sezione 3: Magia, Grimorio & Lancio
    p1.rect(35, 120, 525, 265, fill=(0.98, 0.98, 0.97), stroke=(0.85, 0.65, 0.13), line_width=1.0)
    p1.rect(35, 363, 525, 22, fill=(0.85, 0.65, 0.13))
    p1.text(45, 370, "3. SISTEMA MAGIA, GRIMORIO, SLOT & LANCIO INCANTESIMI", "F2", 9.5, (0.1, 0.1, 0.1))

    p1.text(45, 347, "Classi Incantatrici: Maghi, Elfi (Magia Arcana) e Chierici, Druidi, Paladini (Magia Divina).", "F2", 8.5, (0.1, 0.1, 0.1))
    p1.text(45, 333, "Compendio BECMI Ufficiale: 36 incantesimi registrati per i Cerchi 1, 2 e 3 con descrizioni originali.", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 319, "/magia (o /incantesimi) : Apre il grimorio, mostra gli slot disponibili per cerchio e gli incantesimi memorizzati.", "F2", 8.5, (0.54, 0, 0))
    p1.text(45, 305, "/magia memorizza        : Seleziona e prepara nuovi incantesimi dagli slot liberi della giornata.", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 291, "/lancia <nome> (o /cast): Lancia un incantesimo preparato (es. '/lancia dardo incantato' o '/lancia cura').", "F2", 8.5, (0.54, 0, 0))
    p1.text(45, 277, "   - Verifica automatica dello slot disponibile del cerchio corrispondente.", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 263, "   - Consumo istantaneo dello slot nel database SQLite senza perdita di sincronizzazione.", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 249, "   - Invio dell'effetto descrittivo completo direttamente al prompt del Dungeon Master AI.", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 235, "   - Effetto sonoro retro dedicato 'magia' a onde pulsate sincronizzato.", "F1", 8, (0.3, 0.3, 0.3))
    p1.text(45, 219, "Regola BECMI Concentrazione: Se l'incantatore subisce danni prima del suo turno, perde l'incantesimo.", "F2", 8, (0.7, 0.1, 0.1))
    p1.text(45, 205, "Recupero Slot: Tutti gli incantesimi vengono completamente ripristinati solo dopo un Riposo Lungo (/riposo 8h).", "F1", 8, (0.3, 0.3, 0.3))

    p1.text(35, 45, "D&D Scatola Rossa BECMI • Manuale Comandi & Guida di Gioco (Pagina 1 di 2) • AI DM", "F1", 7.5, (0.5, 0.5, 0.5))

    # Pagina 2
    p2 = PDFCanvas()
    p2.rect(20, 20, 555.28, 801.89, stroke=(0.54, 0.0, 0.0), line_width=2.5)
    p2.rect(24, 24, 547.28, 793.89, stroke=(0.85, 0.65, 0.13), line_width=1.0)

    # Banner Header Pagina 2
    p2.rect(25, 765, 545.28, 52, fill=(0.54, 0.0, 0.0))
    p2.text(40, 796, "DUNGEONS & DRAGONS BECMI - SCATOLA ROSSA", "F2", 13, (1, 0.85, 0.2))
    p2.text(40, 778, "MANUALE DEI COMANDI & GUIDA RAPIDA DI GIOCO (PARTE 2)", "F2", 12, (1, 1, 1))

    p2.rect(25, 742, 545.28, 23, fill=(0.95, 0.94, 0.90), stroke=(0.8, 0.8, 0.8), line_width=0.5)
    p2.text(35, 750, "Tiri Dado Reali  |  Schede PDF A4  |  Mappe Tattiche  |  Multiplayer LAN", "F1", 8.5, (0.2, 0.2, 0.2))

    # Sezione 4: Dadi, Combattimento & Reazione
    p2.rect(35, 580, 525, 150, fill=(0.98, 0.98, 0.97), stroke=(0.85, 0.65, 0.13), line_width=1.0)
    p2.rect(35, 708, 525, 22, fill=(0.85, 0.65, 0.13))
    p2.text(45, 715, "4. COMBATTIMENTO, TIRI DADO REALI & REAZIONI/MORALE BECMI", "F2", 9.5, (0.1, 0.1, 0.1))

    p2.text(45, 692, "Tiri d'Attacco & THAC0: Per colpire un bersaglio si tira 1d20: Risultato Necessario = THAC0 - CA del Nemico.", "F2", 8.5, (0.1, 0.1, 0.1))
    p2.text(45, 678, "Tiri Salvezza (1d20): Raggio/Veleno, Bacchette, Paralisi/Pietrificazione, Soffio di Drago, Bastoni/Incantesimi.", "F1", 8, (0.3, 0.3, 0.3))
    p2.text(45, 664, "Reazione Mostri (2d6 BECMI): 2-5 Ostile, 6-8 Incerto/Trattabile, 9-11 Amichevole, 12 Alleato entusiasta.", "F1", 8, (0.3, 0.3, 0.3))
    p2.text(45, 650, "Morale Mostri (2d6): Tirato alla prima morte o a meta' PF: se fallito la creatura fugge o si arrende.", "F1", 8, (0.3, 0.3, 0.3))
    p2.text(45, 636, "/modalita [interattiva|classica]: Passa tra 'Interattiva' (chiamata dadi DM e attesa tiro) e 'Classica' (auto).", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 622, "/d20, /d8+1, /2d6, /d100 : Tira dadi fisici con il PC, oppure digita direttamente il numero fatto dal vivo.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 608, "/autodadi               : Attiva/disattiva il lancio automatico di dadi ad ogni turno (disattivo in Interattiva).", "F1", 8, (0.3, 0.3, 0.3))
    p2.text(45, 594, "   - Suoni retro dedicati per 20 naturale (critico trionfale) e 1 naturale (fallimento critico cupo).", "F1", 8, (0.3, 0.3, 0.3))

    # Sezione 5: Gestione Eroi & Schede PDF
    p2.rect(35, 435, 525, 135, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
    p2.rect(35, 548, 525, 22, fill=(0.54, 0.0, 0.0))
    p2.text(45, 555, "5. GESTIONE EROI, LIVELLO & SCHEDE PERSONAGGIO PDF A4", "F2", 9.5, (1, 1, 1))

    p2.text(45, 533, "/scheda                 : Visualizza la scheda con Caratteristiche, PF, CA, THAC0, Tiri Salvezza e Privilegi.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 519, "/inventario (o /zaino)  : Mostra l'inventario categorizzato (Armi, Armature, Zaino, Borsello MO, singolo o party).", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 505, "/scheda pdf (o /schedapdf): Genera e stampa la Scheda Personaggio Ufficiale in formato PDF A4 (cartella schede/).", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 491, "/livello (o /levelup)   : Verifica i PE e gestisce il passaggio di livello automatico (PF, tiro dadi vita e nuovi privilegi).", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 477, "/emporio (o /negozio)   : Accede al mercato della Scatola Rossa: compra armi, armature, torce, pozioni e gregari con le MO.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 463, "/aggiorna               : Modifica manuale avanzata delle statistiche, aggiunta rapida monete o equipaggiamento speciale.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 449, "/esporta                : Esporta la cronaca completa dell'avventura in un file Markdown formattato (cartella cronache/).", "F2", 8.5, (0.54, 0, 0))

    # Sezione 6: Mappe Vettoriali A4 & Cartografia
    p2.rect(35, 290, 525, 135, fill=(0.98, 0.98, 0.97), stroke=(0.54, 0.0, 0.0), line_width=1.0)
    p2.rect(35, 403, 525, 22, fill=(0.54, 0.0, 0.0))
    p2.text(45, 410, "6. CARTOGRAFIA DEL DUNGEON & MAPPE A4 PDF", "F2", 9.5, (1, 1, 1))

    p2.text(45, 387, "/mappa                  : Disegna nel terminale la mappa ASCII aggiornata delle stanze e corridoi esplorati dal party.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 373, "/mappa pdf (o /mappapdf): Esporta la Mappa Tattica A4 PDF su 2 pagine per la campagna (salvata nella cartella mappe/).", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 359, "   - Pagina 1: Mappa vettoriale con quadretti da 10 piedi (stile TSR), pareti in pietra, porte, token Party, legenda e note.", "F1", 8, (0.3, 0.3, 0.3))
    p2.text(45, 345, "   - Pagina 2: Dossier stanze dettagliato, griglia ASCII terminale retro e spazio per annotazioni a penna al tavolo.", "F1", 8, (0.3, 0.3, 0.3))
    p2.text(45, 331, "Simboli della Mappa:", "F2", 8, (0.2, 0.2, 0.2))
    p2.text(45, 319, "   - [P] / @ : Posizione attuale Compagnia   |   [D] : Porta in legno chiusa   |   [/] : Porta aperta", "F1", 7.5, (0.3, 0.3, 0.3))
    p2.text(45, 307, "   - [S] : Porta segreta o passaggio celato  |   [!] : Pericolo o trappola     |   [$] : Scrigno o tesoro", "F1", 7.5, (0.3, 0.3, 0.3))

    # Sezione 7: Audio, Modello AI, Multiplayer LAN & Uscita
    p2.rect(35, 65, 525, 215, fill=(1, 1, 1), stroke=(0.7, 0.7, 0.7), line_width=0.8)
    p2.rect(35, 258, 525, 22, fill=(0.85, 0.65, 0.13))
    p2.text(45, 265, "7. AUDIO RETRO, MODELLO AI, MULTIPLAYER LAN & COMANDI DI SISTEMA", "F2", 9.5, (0.1, 0.1, 0.1))

    p2.text(45, 242, "/suoni                  : Attiva o disattiva gli effetti sonori retro chiptune 8-bit sintetizzati in Python puro.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 228, "/suoni test             : Riproduce tutti gli 8 effetti sonori (dado, critico, fallimento, danno, tesoro, levelup, intro, magia).", "F1", 8, (0.3, 0.3, 0.3))
    p2.text(45, 214, "/modello (o /ai)        : Visualizza il modello Gemini attivo e la catena di fallback automatica (default: gemini-3.8-flash).", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 200, "/sql (o /db)            : Mostra le statistiche e lo stato del database relazionale SQLite dnd_becmi.db.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 186, "/help (o /aiuto)        : Mostra la guida sintetica direttamente nel terminale di gioco.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 172, "/help pdf (o /comandi pdf): Rigenera e apre questo Manuale dei Comandi in formato PDF A4 aggiornato.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 158, "/stop (o /menu, /0)     : Salva automaticamente la sessione nel database SQLite e torna al Menu Principale.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 144, "/chiudi (o /esci)       : Salva tutti i progressi, chiude la connessione al database ed esce dal programma.", "F2", 8.5, (0.54, 0, 0))
    p2.text(45, 128, "Modalita' LAN Multiplayer:", "F2", 8, (0.2, 0.2, 0.2))
    p2.text(45, 116, "   - Menu [H]: Avvia il Server TCP Host sulla porta 5555 consentendo ad altri giocatori sulla rete locale di unirsi.", "F1", 7.5, (0.3, 0.3, 0.3))
    p2.text(45, 104, "   - Menu [J] (o flag --join <IP>): Si collega come Client TCP all'Host per una campagna multi-giocatore a turni sincronizzati.", "F1", 7.5, (0.3, 0.3, 0.3))
    p2.text(45, 84, "Nota di Sincronizzazione: Questo documento PDF si rigenera automaticamente ad ogni avvio in caso di modifiche ai comandi.", "F1", 7, (0.5, 0.5, 0.5))

    p2.text(35, 40, "D&D Scatola Rossa BECMI • Manuale Comandi & Guida di Gioco (Pagina 2 di 2) • AI DM", "F1", 7.5, (0.5, 0.5, 0.5))

    pdf_bytes = build_pdf_document([p1.get_content(), p2.get_content()])
    with open(percorso_manuale, "wb") as f:
        f.write(pdf_bytes)

    try:
        with open(MANUALE_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(hash_corrente)
    except Exception:
        pass

    if not silenzioso:
        suona("levelup")
        print(f"\n{VERDE}{GRASSETTO}📖 Manuale dei Comandi PDF A4 generato e sincronizzato con successo!{RESET}")
        print(f"{CIANO}Percorso file:{RESET} {os.path.abspath(percorso_manuale)}")
    return os.path.abspath(percorso_manuale)


def tira_dado(comando):
    expr = re.sub(r"^/d?", "", comando.strip().lower())
    if not expr:
        return None
    try:
        bonus = 0
        if "+" in expr:
            expr, bonus_str = expr.split("+", 1)
            bonus = int(bonus_str)
        elif "-" in expr:
            expr, bonus_str = expr.split("-", 1)
            bonus = -int(bonus_str)

        if "d" in expr:
            num_str, facce_str = expr.split("d", 1)
            num = int(num_str) if num_str else 1
            facce = int(facce_str)
        else:
            num = 1
            facce = int(expr)

        if num < 1 or facce < 2:
            return None

        tiri = [random.randint(1, facce) for _ in range(num)]
        totale = sum(tiri) + bonus
        if facce == 20 and 20 in tiri:
            suona("critico")
        elif facce == 20 and 1 in tiri:
            suona("fallimento")
        else:
            suona("dado")
        dettaglio = f"{tiri}" + (f" {bonus:+d}" if bonus != 0 else "")
        return f"[Dado locale {num}d{facce}{bonus:+d}: {totale} | dettagli: {dettaglio}]" if bonus else f"[Dado locale {num}d{facce}: {totale} | dettagli: {tiri}]"
    except Exception:
        return None


def comprimi_memoria(db: DnDDatabase, avventura: dict, api_key: str, system_prompt: str):
    print(f"{GIALLO}Compressione della memoria SQLite in corso...{RESET}")
    richiesta = list(avventura["storia"])
    richiesta.append({
        "role": "user",
        "parts": [{"text": "Fai un riassunto completo ma sintetico di tutto cio che e accaduto finora nell'avventura per tutto il party: stanze esplorate, nemici sconfitti, alleati, ferite, inventario, MO e PE."}]
    })
    riassunto = chiama_gemini(richiesta, api_key, system_prompt, desc_attesa="sta riassumendo la cronaca dell'avventura")
    nuova_storia = [
        {"role": "user", "parts": [{"text": "Riassunto dell'avventura finora: " + riassunto}]},
        {"role": "model", "parts": [{"text": "Ho memorizzato tutto il progresso del gruppo. Riprendiamo da dove eravamo rimasti.\n\nCosa fate?"}]}
    ]
    avventura["storia"] = nuova_storia
    db.sostituisci_storia_compressa(avventura["id"], nuova_storia)
    print(f"{VERDE}Memoria compressa e aggiornata nel database!{RESET}\n")
    print(riassunto)


def mostra_grimorio_e_incantesimi(eroe: dict):
    slots = slot_incantesimi_per_cerchio(eroe["classe"], eroe["livello"], eroe.get("immortale", False))
    if not slots:
        print(f"\n{GIALLO}{eroe['nome']} ({eroe['classe']}) non e un incantatore o non ha ancora slot incantesimi.{RESET}")
        return

    tipo_inc = "arcano" if eroe["classe"].lower() in ["mago", "elfo"] else "divino"
    tipo_label = "Grimorio Arcano" if tipo_inc == "arcano" else "Preghiere Sacre"
    print(f"\n{CIANO}{GRASSETTO}=== {tipo_label.upper()} - {eroe['nome'].upper()} ({eroe['classe']} Liv.{eroe['livello']}) ==={RESET}")
    print(f"{GIALLO}Slot Incantesimi Giornalieri:{RESET}")
    usati = eroe.get("slot_usati", {})
    for cerchio, tot in sorted(slots.items()):
        usati_cerchio = usati.get(str(cerchio), 0)
        rimasti = max(0, tot - usati_cerchio)
        colore_slot = VERDE if rimasti > 0 else ROSSO
        print(f"  {cerchio}° Cerchio: {colore_slot}{rimasti}/{tot} disponibili{RESET} (usati oggi: {usati_cerchio})")

    prep = eroe.get("incantesimi_memorizzati", [])
    print(f"\n{GIALLO}Incantesimi Attualmente Preparati per la Giornata:{RESET}")
    if prep:
        for idx, inc in enumerate(prep, 1):
            info = INCANTESIMI_DATABASE.get(inc, {})
            c = info.get("cerchio", 1)
            desc = info.get("desc", "")
            print(f"  {VERDE}[{idx}]{RESET} {GRASSETTO}{inc}{RESET} ({c}° Cerchio) — {DIM}{desc}{RESET}")
    else:
        print(f"  {DIM}Nessun incantesimo preparato. Usa '/magia memorizza' per preparare i tuoi incantesimi.{RESET}")


def memorizza_incantesimo_eroe(db, eroe: dict):
    slots = slot_incantesimi_per_cerchio(eroe["classe"], eroe["livello"], eroe.get("immortale", False))
    if not slots:
        print(f"{GIALLO}{eroe['nome']} non possiede slot incantesimi da memorizzare.{RESET}")
        return

    tipo_inc = "arcano" if eroe["classe"].lower() in ["mago", "elfo"] else "divino"
    max_c = max(slots.keys())
    inc_disponibili = [
        nome for nome, dati in INCANTESIMI_DATABASE.items()
        if dati["tipo"] == tipo_inc and dati["cerchio"] <= max_c
    ]

    print(f"\n{CIANO}{GRASSETTO}=== MEMORIZZAZIONE INCANTESIMI: {eroe['nome']} ==={RESET}")
    for idx, nome in enumerate(inc_disponibili, 1):
        d = INCANTESIMI_DATABASE[nome]
        print(f"  {VERDE}[{idx:2d}]{RESET} {GRASSETTO}{nome:22s}{RESET} ({d['cerchio']}° Cerchio) — {DIM}{d['desc']}{RESET}")

    scelta = input(f"\n{VERDE}Seleziona numero incantesimo da memorizzare (o 0 per annullare) > {RESET}").strip()
    if scelta.isdigit() and 1 <= int(scelta) <= len(inc_disponibili):
        scelto = inc_disponibili[int(scelta) - 1]
        cerchio = INCANTESIMI_DATABASE[scelto]["cerchio"]
        tot_slot = slots.get(cerchio, 0)
        gia_prep = [x for x in eroe.get("incantesimi_memorizzati", []) if INCANTESIMI_DATABASE.get(x, {}).get("cerchio") == cerchio]
        if len(gia_prep) >= tot_slot:
            print(f"\n{ROSSO}Hai gia memorizzato il numero massimo di incantesimi per il {cerchio}° Cerchio ({tot_slot}/{tot_slot})!{RESET}")
        else:
            eroe.setdefault("incantesimi_memorizzati", []).append(scelto)
            db.salva_personaggio(eroe)
            suona("magia")
            print(f"\n{VERDE}Incantesimo '{scelto}' memorizzato con successo per {eroe['nome']}!{RESET}")
        time.sleep(1.2)


def gestisci_comando_lancia(db, eroi_party, avventura, azione):
    parti = azione.split(maxsplit=1)
    nome_input = parti[1].strip().lower() if len(parti) > 1 else ""

    incantatori = [e for e in eroi_party if slot_incantesimi_per_cerchio(e["classe"], e["livello"], e.get("immortale", False))]
    if not incantatori:
        print(f"\n{GIALLO}Nessun membro del gruppo e in grado di lanciare incantesimi.{RESET}")
        return None

    eroe = scegli_membro_party(incantatori, "lanciare l'incantesimo") if len(incantatori) > 1 else incantatori[0]
    if not eroe:
        return None

    prep = eroe.get("incantesimi_memorizzati", [])
    if not prep:
        print(f"\n{GIALLO}{eroe['nome']} non ha incantesimi preparati! Usa prima '/magia' per memorizzarli.{RESET}")
        return None

    inc_scelto = None
    if nome_input:
        for p in prep:
            if nome_input in p.lower():
                inc_scelto = p
                break

    if not inc_scelto:
        print(f"\n{CIANO}{GRASSETTO}Incantesimi preparati da {eroe['nome']}:{RESET}")
        for idx, inc in enumerate(prep, 1):
            d = INCANTESIMI_DATABASE.get(inc, {})
            print(f"  {VERDE}[{idx}]{RESET} {GRASSETTO}{inc}{RESET} ({d.get('cerchio', 1)}° Cerchio) — {DIM}{d.get('desc', '')}{RESET}")
        scelta = input(f"\n{VERDE}Quale incantesimo vuoi lanciare? [1-{len(prep)}] > {RESET}").strip()
        if scelta.isdigit() and 1 <= int(scelta) <= len(prep):
            inc_scelto = prep[int(scelta) - 1]

    if not inc_scelto:
        return None

    cerchio = INCANTESIMI_DATABASE.get(inc_scelto, {}).get("cerchio", 1)
    tot_slots = slot_incantesimi_per_cerchio(eroe["classe"], eroe["livello"], eroe.get("immortale", False)).get(cerchio, 0)
    usati = eroe.setdefault("slot_usati", {}).get(str(cerchio), 0)

    if usati >= tot_slots:
        print(f"\n{ROSSO}Tutti gli slot del {cerchio}° Cerchio sono stati consumati per oggi! E necessario un riposo completo per recuperarli.{RESET}")
        return None

    eroe["slot_usati"][str(cerchio)] = usati + 1
    eroe["incantesimi_memorizzati"].remove(inc_scelto)
    db.salva_personaggio(eroe)
    suona("magia")

    bersaglio = input(f"{CIANO}Bersaglio o direzione dell'incantesimo (es. 'sul capo dei goblin' o premi Invio): {RESET}").strip()
    bers_txt = f" verso {bersaglio}" if bersaglio else ""
    desc_effetto = INCANTESIMI_DATABASE.get(inc_scelto, {}).get("desc", "")
    azione_finale = (
        f"{eroe['nome']} lancia con formula verbale e gesti arcani l'incantesimo '{inc_scelto}' ({cerchio}° Cerchio){bers_txt}! "
        f"[Effetto da regolamento BECMI: {desc_effetto}]"
    )
    return azione_finale


def rileva_intento_torcia(testo: str):
    t = testo.lower().strip()
    if t.startswith("/torcia") or t.startswith("/luce"):
        parts = t.split()
        if len(parts) > 1:
            sub = parts[1]
            if sub in ["off", "spegni", "spenta", "via", "no", "0", "stop"]:
                return "off"
            if sub in ["on", "accendi", "accesa", "si", "1", "start"]:
                return "on"
            if sub in ["auto", "toggle"]:
                return "toggle_auto"

    spegni_pat = r"\b(spegn[a-z]*|mett[a-z]*\s+via|ripon[a-z]*|custodisci|conserva|smorza)\b.*?\b(torc[a-z]*|luc[a-z]*|fiaccol[a-z]*)\b|\b(spegni|spegnere|spengo|spegniamo|spegnete)\b"
    accendi_pat = r"\b(accend[a-z]*|estra[a-z]*|tira\s+fuori|prendi)\b.*?\b(torc[a-z]*|fiaccol[a-z]*)\b|\b(accendi|accendere|accendo|accendiamo|accendete)\b"

    if re.search(spegni_pat, t):
        return "off"
    if re.search(accendi_pat, t):
        return "on"
    return None


def rileva_ambiente_e_luce(testo_dm: str, azione: str = "", st_attuale: dict = None):
    st = st_attuale or {}
    blocco_manuale = st.get("ambiente_manuale", False)
    if blocco_manuale:
        return st.get("luce_ambientale", False), st.get("ambiente_nome", "Dungeon"), True

    testo_tot = f"{azione} {testo_dm}".lower()

    # 1. Controllo tag esplicito DM [Ambiente: ...]
    m_tag = re.search(r"\[\s*ambiente:\s*([^\]]+)\]", testo_dm, re.IGNORECASE)
    if m_tag:
        val = m_tag.group(1).strip().lower()
        if any(k in val for k in ["taverna", "locanda", "citt", "villaggio", "borgo", "giorno", "aperto", "luce", "sole", "bottega", "osteria"]):
            return True, m_tag.group(1).strip(), False
        if any(k in val for k in ["dungeon", "cripta", "buio", "sotterrane", "caverna", "grotta", "notte", "catacomb", "rovine buie"]):
            return False, m_tag.group(1).strip(), False

    # 2. Transizioni esplicite verso luoghi illuminati
    transizioni_luce = [
        r"\b(entrat[eio]|entri|entriamo|tornat[eio]|torniamo|arrivat[eio]|siete|vi\s+trovate)\s+.*?\b(locanda|taverna|villaggio|citt[aà]|borgo|casa|tempio|bottega|osteria|piazza|mercato)\b",
        r"\b(uscit[eio]|uscite|usciamo|tornate|salite)\s+.*?\b(all[\'\s]aperto|fuori|alla\s+luce|in\s+superficie|dal\s+dungeon|dalla\s+cripta)\b"
    ]
    for p in transizioni_luce:
        if re.search(p, testo_tot):
            if any(k in testo_tot for k in ["locanda", "taverna", "osteria"]):
                return True, "Taverna / Locanda", False
            if any(k in testo_tot for k in ["citt", "villaggio", "borgo", "piazza", "mercato"]):
                return True, "Città / Villaggio", False
            return True, "All'aperto (Giorno)", False

    # 3. Transizioni esplicite verso luoghi bui / dungeon
    transizioni_buio = [
        r"\b(entrat[eio]|scendet[eio]|inoltrat[eio]|addentrat[eio]|scendiamo|entriamo)\s+.*?\b(cripta|dungeon|sotterrane[oi]|cavern[ae]|grott[ae]|cunicol[oi]|tomba|catacomb[ae]|rovine)\b",
        r"\b(calat[eio]|varcat[eio])\s+.*?\b(botola|portale\s+oscuro|ingresso\s+della\s+cripta|soglia\s+buia)\b"
    ]
    for p in transizioni_buio:
        if re.search(p, testo_tot):
            return False, "Dungeon / Sotterraneo", False

    # 4. Rilevamento contestuale basato su parole chiave
    parole_luce = ["locanda", "taverna", "locandiere", "oste", "boccale", "birra", "idromele", "tavolo", "focolare", "camino", "sole", "mezzogiorno", "piazza", "villaggio", "città", "citta", "mercato", "bottega", "strada", "aperto", "luce naturale"]
    parole_buio = ["cripta", "dungeon", "sotterraneo", "tomba", "sarcofago", "muffa", "tenebre", "stalattiti", "buio pesto", "cunicolo", "catacomba", "caverna", "grotta", "mura umide", "antro oscuro"]

    score_luce = sum(1 for w in parole_luce if w in testo_tot)
    score_buio = sum(1 for w in parole_buio if w in testo_tot)

    if score_luce > score_buio and score_luce >= 2:
        if any(k in testo_tot for k in ["locanda", "taverna", "oste", "boccale", "focolare"]):
            return True, "Taverna / Locanda", False
        if any(k in testo_tot for k in ["piazza", "villaggio", "città", "citta", "mercato", "bottega"]):
            return True, "Città / Villaggio", False
        return True, "All'aperto (Giorno)", False
    elif score_buio > score_luce and score_buio >= 2:
        return False, "Dungeon / Sotterraneo", False

    luce_prec = st.get("luce_ambientale", False)
    amb_prec = st.get("ambiente_nome", "Dungeon / Sotterraneo" if not luce_prec else "Luogo Illuminato")
    return luce_prec, amb_prec, False


def aggiorna_tempo_e_torce(avventura: dict, eroi_party: list):
    st_dungeon = avventura.setdefault("stato_dungeon", {})
    luce_ambientale = st_dungeon.get("luce_ambientale", False)
    torcia_on = st_dungeon.get("torcia_attiva", False if luce_ambientale else True)
    turni_torcia = st_dungeon.get("torcia_turni", 6)
    auto_sostituisci = st_dungeon.get("auto_sostituisci", True)

    avvisi = []

    # Se siamo in presenza di luce ambientale (taverna, locanda, citta, aperto di giorno)
    if luce_ambientale:
        avventura["buio_totale"] = False
        st_dungeon["torcia_turni"] = turni_torcia
        avventura["torcia_turni_rimasti"] = turni_torcia
        avventura["torcia_attiva"] = torcia_on
        return avvisi

    # Se siamo in un dungeon buio
    if not torcia_on:
        avventura["buio_totale"] = True
        avvisi.append(f"{ROSSO}{GRASSETTO}⚠️ Il gruppo si trova nel BUIO TOTALE! (/torcia on o scrivi 'accendi la torcia' per fare luce).{RESET}")
    else:
        avventura["buio_totale"] = False
        turni_torcia -= 1
        if turni_torcia <= 0:
            if auto_sostituisci:
                trovata = False
                for e in eroi_party:
                    for idx, item in enumerate(e.get("equip", [])):
                        if "torc" in item.lower():
                            trovata = True
                            m = re.search(r"(\d+)\s+Torce?", item, re.IGNORECASE)
                            if m:
                                cnt = int(m.group(1)) - 1
                                if cnt > 0:
                                    e["equip"][idx] = f"{cnt} Torce"
                                else:
                                    e["equip"].pop(idx)
                            else:
                                e["equip"].pop(idx)
                            turni_torcia = 6
                            st_dungeon["torcia_attiva"] = True
                            avvisi.append(f"{GIALLO}🔥 La torcia si e consumata. {e['nome']} ne accende una nuova dallo zaino!{RESET}")
                            break
                    if trovata:
                        break
                if not trovata:
                    turni_torcia = 0
                    st_dungeon["torcia_attiva"] = False
                    avventura["buio_totale"] = True
                    avvisi.append(f"{ROSSO}{GRASSETTO}⚠️ LE TORCE SONO ESAURITE! Il gruppo piomba nel BUIO TOTALE (-4 a colpire, CA peggiorata di 4)!{RESET}")
            else:
                turni_torcia = 0
                st_dungeon["torcia_attiva"] = False
                avventura["buio_totale"] = True
                avvisi.append(f"{GIALLO}⚠️ La torcia si e spenta. Usa '/torcia on' o scrivi 'accendi una torcia' per estrarne un'altra dallo zaino.{RESET}")
        elif turni_torcia == 1:
            avvisi.append(f"{GIALLO}🔥 La torcia sta tremolando e sta per spegnersi (1 turno rimasto)!{RESET}")

    st_dungeon["torcia_turni"] = turni_torcia
    avventura["torcia_turni_rimasti"] = turni_torcia
    avventura["torcia_attiva"] = st_dungeon.get("torcia_attiva", False)
    return avvisi


def gestisci_comando_torcia(db, eroi_party: list, avventura: dict, subcmd: str = ""):
    st_d = avventura.setdefault("stato_dungeon", {})
    t_rimasti = st_d.get("torcia_turni", avventura.get("torcia_turni_rimasti", 6))
    torcia_attiva = st_d.get("torcia_attiva", False if st_d.get("luce_ambientale") else True)
    luce_amb = st_d.get("luce_ambientale", False)
    amb_nome = st_d.get("ambiente_nome", "Taverna" if luce_amb else "Dungeon")
    auto_sost = st_d.get("auto_sostituisci", True)

    sub = subcmd.strip().lower()
    if sub in ["off", "spegni", "spenta", "via", "no", "0", "stop"]:
        st_d["torcia_attiva"] = False
        avventura["torcia_attiva"] = False
        db.salva_metadati_avventura(avventura)
        print(f"\n{VERDE}🕯️ Torcia spenta e riposta nello zaino. (Turni conservati: {t_rimasti}/6 t).{RESET}")
        if luce_amb:
            print(f"{CIANO}Ambiente attuale: {amb_nome} (Luce naturale presente, nessuna penalità).{RESET}")
        else:
            print(f"{GIALLO}⚠️ Sei in un dungeon/luogo buio: senza torcia sei nel BUIO TOTALE (-4 TxC/CA).{RESET}")
        return

    if sub in ["on", "accendi", "accesa", "si", "1", "start"]:
        if t_rimasti > 0:
            st_d["torcia_attiva"] = True
            avventura["torcia_attiva"] = True
            avventura["buio_totale"] = False
            db.salva_metadati_avventura(avventura)
            print(f"\n{VERDE}🔥 Torcia riaccesa! ({t_rimasti}/6 turni rimanenti).{RESET}")
        else:
            trovata = False
            for e in eroi_party:
                for idx, item in enumerate(e.get("equip", [])):
                    if "torc" in item.lower():
                        trovata = True
                        m = re.search(r"(\d+)\s+Torce?", item, re.IGNORECASE)
                        if m:
                            cnt = int(m.group(1)) - 1
                            if cnt > 0:
                                e["equip"][idx] = f"{cnt} Torce"
                            else:
                                e["equip"].pop(idx)
                        else:
                            e["equip"].pop(idx)
                        db.salva_personaggio(e)
                        break
                if trovata:
                    break
            st_d["torcia_turni"] = 6
            st_d["torcia_attiva"] = True
            avventura["torcia_turni_rimasti"] = 6
            avventura["buio_totale"] = False
            db.salva_metadati_avventura(avventura)
            if trovata:
                print(f"\n{VERDE}🔥 Nuova torcia estratta dallo zaino e accesa! (6/6 turni garantiti).{RESET}")
            else:
                print(f"\n{GIALLO}🔥 Torcia accesa (nessuna scorta consumata). (6/6 turni).{RESET}")
        return

    if sub in ["auto", "toggle"]:
        st_d["auto_sostituisci"] = not auto_sost
        db.salva_metadati_avventura(avventura)
        stato_s = f"{VERDE}ATTIVA{RESET}" if st_d["auto_sostituisci"] else f"{ROSSO}DISATTIVATA{RESET}"
        print(f"\n{CIANO}Sostituzione automatica torce all'esaurimento: {stato_s}{RESET}")
        return

    print(f"\n{GIALLO}{GRASSETTO}=== GESTIONE TORCE E ILLUMINAZIONE ==={RESET}")
    print(f"Ambiente attuale: {VERDE if luce_amb else GIALLO}{amb_nome}{RESET} {'(Luce naturale)' if luce_amb else '(Oscurità dungeon)'}")
    stato_torcia_str = f"{VERDE}ACCESA ({t_rimasti}/6 turni){RESET}" if torcia_attiva else f"{DIM}SPENTA/RIPOSTA NELLO ZAINO ({t_rimasti}/6 turni conservati){RESET}"
    print(f"Stato torcia: {stato_torcia_str}")
    torce_tot = sum(
        int(m.group(1)) if (m := re.search(r"(\d+)\s+Torce?", item, re.IGNORECASE)) else 1
        for e in eroi_party for item in e.get("equip", []) if "torc" in item.lower()
    )
    print(f"Scorte totali torce nel party: {CIANO}{torce_tot} torce negli zaini{RESET}")
    print(f"Auto-accensione a esaurimento: {VERDE + 'ATTIVA' if auto_sost else ROSSO + 'DISATTIVATA'}{RESET}")
    print("-" * 55)
    print(f"  {VERDE}[1]{RESET} Accendi torcia (estrai nuova o riaccendi)")
    print(f"  {VERDE}[2]{RESET} Spegni e riponi torcia nello zaino")
    print(f"  {VERDE}[3]{RESET} Attiva/Disattiva auto-accensione a esaurimento")
    print(f"  {DIM}[0] Torna al gioco{RESET}")
    scelta = input(f"\n{VERDE}Scegli opzione > {RESET}").strip()
    if scelta == "1":
        gestisci_comando_torcia(db, eroi_party, avventura, "on")
    elif scelta == "2":
        gestisci_comando_torcia(db, eroi_party, avventura, "off")
    elif scelta == "3":
        gestisci_comando_torcia(db, eroi_party, avventura, "auto")


def gestisci_comando_ambiente(db, avventura: dict, subcmd: str = ""):
    st_d = avventura.setdefault("stato_dungeon", {})
    luce_amb = st_d.get("luce_ambientale", False)
    amb_nome = st_d.get("ambiente_nome", "Taverna / Locanda" if luce_amb else "Dungeon / Sotterraneo")
    manuale = st_d.get("ambiente_manuale", False)

    sub = subcmd.strip().lower()
    if sub in ["taverna", "locanda", "osteria", "luce", "citta", "città", "villaggio", "giorno", "sole"]:
        st_d["luce_ambientale"] = True
        nome_scelto = "Taverna / Locanda" if sub in ["taverna", "locanda", "osteria"] else ("Città / Villaggio" if sub in ["citta", "città", "villaggio"] else "All'aperto (Giorno)")
        st_d["ambiente_nome"] = nome_scelto
        st_d["ambiente_manuale"] = True
        avventura["buio_totale"] = False
        db.salva_metadati_avventura(avventura)
        print(f"\n{VERDE}🍻 Ambiente impostato su: {nome_scelto} (Luce presente, torce in pausa).{RESET}")
        return

    if sub in ["dungeon", "sotterraneo", "cripta", "caverna", "buio", "notte"]:
        st_d["luce_ambientale"] = False
        st_d["ambiente_nome"] = "Dungeon / Sotterraneo"
        st_d["ambiente_manuale"] = True
        db.salva_metadati_avventura(avventura)
        print(f"\n{GIALLO}🌑 Ambiente impostato su: Dungeon / Sotterraneo (Oscurità attiva, servono torce).{RESET}")
        return

    if sub in ["auto", "ripristina", "reset"]:
        st_d["ambiente_manuale"] = False
        db.salva_metadati_avventura(avventura)
        print(f"\n{CIANO}🔄 Rilevamento automatico dell'ambiente ripristinato (gestito dalla narrazione DM).{RESET}")
        return

    print(f"\n{GIALLO}{GRASSETTO}=== GESTIONE AMBIENTE ED ILLUMINAZIONE ==={RESET}")
    modalita = f"{GIALLO}MANUALE{RESET}" if manuale else f"{VERDE}AUTOMATICA (IA DM){RESET}"
    print(f"Ambiente attuale: {VERDE if luce_amb else GIALLO}{amb_nome}{RESET} (Modalità: {modalita})")
    print(f"Luce ambientale: {VERDE + 'PRESENTE (torce spente non consumano)' if luce_amb else ROSSO + 'ASSENTE (dungeon buio, torce necessarie)'}{RESET}")
    print("-" * 55)
    print(f"  {VERDE}[1]{RESET} Imposta Taverna / Locanda (Luce presente)")
    print(f"  {VERDE}[2]{RESET} Imposta Città / Aperto di Giorno (Luce presente)")
    print(f"  {VERDE}[3]{RESET} Imposta Dungeon / Cripta / Caverna (Buio sotterraneo)")
    print(f"  {VERDE}[4]{RESET} Modalità Automatica (l'ambiente segue la narrazione del DM)")
    print(f"  {DIM}[0] Torna al gioco{RESET}")
    scelta = input(f"\n{VERDE}Scegli opzione > {RESET}").strip()
    if scelta == "1":
        gestisci_comando_ambiente(db, avventura, "taverna")
    elif scelta == "2":
        gestisci_comando_ambiente(db, avventura, "citta")
    elif scelta == "3":
        gestisci_comando_ambiente(db, avventura, "dungeon")
    elif scelta == "4":
        gestisci_comando_ambiente(db, avventura, "auto")


def verifica_incontro_errante(avventura: dict, turno_attuale: int):
    st_d = avventura.setdefault("stato_dungeon", {})
    if st_d.get("luce_ambientale", False):
        return None

    freq = st_d.get("frequenza_incontri", "raro").lower()
    if freq in ["off", "disattiva", "disattivato", "nessuno", "0", "mai"]:
        return None

    config = {
        "raro": (4, 8, 4),        # Ogni 4 turni (40 min), 1 su 1d8 (12.5%), min 4 turni cooldown
        "normale": (3, 6, 3),     # Ogni 3 turni (30 min), 1 su 1d6 (16.7%), min 3 turni cooldown
        "frequente": (2, 6, 2)    # Ogni 2 turni (20 min), 1 su 1d6 (16.7%), min 2 turni cooldown
    }
    intervallo, facce, cooldown = config.get(freq, config["raro"])

    ultimo = st_d.get("ultimo_incontro_turno", -999)
    if (turno_attuale - ultimo) < cooldown:
        return None

    if turno_attuale % intervallo != 0:
        return None

    tiro = random.randint(1, facce)
    if tiro == 1:
        st_d["ultimo_incontro_turno"] = turno_attuale
        return f"[INCONTRO ERRANTE BECMI (1 su 1d{facce}): Una pattuglia nemica o creatura errante del dungeon sopraggiunge attirata da rumori o passi!]"
    return None


def gestisci_comando_incontri(db, avventura: dict, subcmd: str = ""):
    st_d = avventura.setdefault("stato_dungeon", {})
    freq_attuale = st_d.get("frequenza_incontri", "raro").lower()

    sub = subcmd.strip().lower()
    if sub in ["off", "disattiva", "disattivato", "nessuno", "0", "mai"]:
        st_d["frequenza_incontri"] = "off"
        db.salva_metadati_avventura(avventura)
        print(f"\n{ROSSO}Incontri erranti DISATTIVATI.{RESET} Nessun mostro casuale comparira' durante l'esplorazione (affronterai solo i mostri previsti dalla storia/stanze).")
        return

    if sub in ["raro", "rari", "bilanciato", "consigliato", "1"]:
        st_d["frequenza_incontri"] = "raro"
        db.salva_metadati_avventura(avventura)
        print(f"\n{VERDE}Frequenza incontri erranti impostata su: RARA (Consigliata).{RESET} Controllo ogni 4 turni (1 su 1d8, con cooldown 4 turni).")
        return

    if sub in ["normale", "standard", "classico", "2"]:
        st_d["frequenza_incontri"] = "normale"
        db.salva_metadati_avventura(avventura)
        print(f"\n{GIALLO}Frequenza incontri erranti impostata su: NORMALE / CLASSICA.{RESET} Controllo ogni 3 turni (1 su 1d6, con cooldown 3 turni).")
        return

    if sub in ["frequente", "frequenti", "alto", "difficile", "3"]:
        st_d["frequenza_incontri"] = "frequente"
        db.salva_metadati_avventura(avventura)
        print(f"\n{MAGENTA}Frequenza incontri erranti impostata su: FREQUENTE.{RESET} Controllo ogni 2 turni (1 su 1d6, con cooldown 2 turni).")
        return

    print(f"\n{GIALLO}{GRASSETTO}=== FREQUENZA INCONTRI ERRANTI NEL DUNGEON ==={RESET}")
    print(f"Frequenza attuale: {VERDE if freq_attuale=='raro' else (ROSSO if freq_attuale=='off' else GIALLO)}{freq_attuale.upper()}{RESET}")
    print("Regola: Si applica solo nei dungeon/sotterranei bui (mai in locande, citta o alla luce del sole).")
    print("-" * 65)
    print(f"  {VERDE}[1]{RESET} Rari / Bilanciati (Consigliato: controllo ogni 4 turni con 1 su 1d8 e cooldown)")
    print(f"  {VERDE}[2]{RESET} Normali / Classici (Controllo ogni 3 turni con 1 su 1d6 e cooldown)")
    print(f"  {VERDE}[3]{RESET} Frequenti (Controllo ogni 2 turni con 1 su 1d6)")
    print(f"  {ROSSO}[4]{RESET} Disattivati (Nessun mostro casuale, solo mostri di trama)")
    print(f"  {DIM}[0] Torna al gioco{RESET}")
    scelta = input(f"\n{VERDE}Scegli opzione > {RESET}").strip()
    if scelta == "1":
        gestisci_comando_incontri(db, avventura, "raro")
    elif scelta == "2":
        gestisci_comando_incontri(db, avventura, "normale")
    elif scelta == "3":
        gestisci_comando_incontri(db, avventura, "frequente")
    elif scelta == "4":
        gestisci_comando_incontri(db, avventura, "off")


def estrai_chiamata_dado(testo: str) -> list:
    """Estrae una o più chiamate di dado dal testo del Dungeon Master."""
    if not testo:
        return []
    pattern = r"\[CHIAMATA DADO:\s*([^\]]+)\]"
    return re.findall(pattern, testo, re.IGNORECASE)


def gestisci_comando_modalita(db, avventura: dict, subcmd: str = ""):
    global MODALITA_GIOCO, AUTODADI_ATTIVI
    st_d = avventura.setdefault("stato_dungeon", {})
    sub = subcmd.strip().lower()
    if sub in ["interattiva", "interactive", "interattivo", "1"]:
        st_d["modalita_gioco"] = "interattiva"
        AUTODADI_ATTIVI = False
    elif sub in ["classica", "classic", "classico", "auto", "2"]:
        st_d["modalita_gioco"] = "classica"
        AUTODADI_ATTIVI = True
    elif not sub:
        curr = st_d.get("modalita_gioco", MODALITA_GIOCO)
        nuova = "classica" if curr == "interattiva" else "interattiva"
        st_d["modalita_gioco"] = nuova
        AUTODADI_ATTIVI = (nuova == "classica")
    else:
        print(f"\n{GIALLO}Sintassi: /modalita [interattiva|classica]{RESET}")
        return

    MODALITA_GIOCO = st_d["modalita_gioco"]
    db.salva_metadati_avventura(avventura)
    nuova_mod = st_d["modalita_gioco"]
    if nuova_mod == "interattiva":
        print(f"\n{VERDE}🎲 Modalità impostata su: {GRASSETTO}INTERATTIVA{RESET}")
        print(f"{CIANO}Il DM AI ora indicherà quali dadi tirare [CHIAMATA DADO: ...] e attenderà il tuo tiro reale!{RESET}")
        print(f"{DIM}(Autodadi disattivati automaticamente per consentire i tuoi tiri manuali){RESET}")
    else:
        print(f"\n{GIALLO}🎲 Modalità impostata su: {GRASSETTO}CLASSICA{RESET}")
        print(f"{CIANO}Il DM AI e il motore risolveranno direttamente i tiri in modo continuo e fluido.{RESET}")
        print(f"{DIM}(Autodadi attivati per la narrazione automatica continua){RESET}")


def gestisci_comando_riposo(db, eroi_party: list, avventura: dict):
    print(f"\n{CIANO}{GRASSETTO}=== GESTIONE DEL RIPOSO (Regole BECMI) ==={RESET}")
    print(f"  {VERDE}[1]{RESET} Riposo Breve (10 minuti / 1 turno) — Riorganizza lo zaino, accende nuove torce.")
    print(f"  {VERDE}[2]{RESET} Riposo Lungo / Accampamento (8 ore) — Recupero 1d3 PF per ferito, ricarica slot magia, consumo razioni.")
    print(f"  {DIM}[0] Annulla e torna al gioco{RESET}")

    scelta = input(f"\n{VERDE}Scegli tipo di riposo > {RESET}").strip()
    if scelta == "1":
        avvisi = aggiorna_tempo_e_torce(avventura, eroi_party)
        for a in avvisi:
            print(a)
        print(f"\n{VERDE}Il gruppo prende una breve pausa di 10 minuti per riprendere fiato.{RESET}")
        return "Il gruppo di avventurieri effettua un riposo breve di 10 minuti per riprendere fiato e riorganizzarsi."

    elif scelta == "2":
        report_pf = []
        for e in eroi_party:
            if e["pf_attuali"] < e["pf_max"]:
                cura = random.randint(1, 3)
                e["pf_attuali"] = min(e["pf_max"], e["pf_attuali"] + cura)
                report_pf.append(f"{e['nome']} (+{cura} PF -> {e['pf_attuali']}/{e['pf_max']})")
            e["slot_usati"] = {}
            db.salva_personaggio(e)

        consumate_raz = 0
        for e in eroi_party:
            for idx, item in enumerate(e.get("equip", [])):
                if "razion" in item.lower():
                    m = re.search(r"(\d+)\s+Razion", item, re.IGNORECASE)
                    if m:
                        cnt = int(m.group(1)) - 1
                        if cnt > 0:
                            e["equip"][idx] = f"{cnt} Razioni"
                        else:
                            e["equip"].pop(idx)
                    else:
                        e["equip"].pop(idx)
                    consumate_raz += 1
                    break

        suona("levelup")
        print(f"\n{VERDE}{GRASSETTO}*** NOTTE TRASCORSA (RIPOSO DI 8 ORE) ***{RESET}")
        if report_pf:
            print(f"{GIALLO}Guarigione naturale:{RESET} {', '.join(report_pf)}")
        else:
            print(f"{GIALLO}Tutti gli eroi erano gia al massimo dei Punti Ferita.{RESET}")
        print(f"{CIANO}Tutti gli slot incantesimi sono stati completamente ripristinati!{RESET}")
        if consumate_raz:
            print(f"{DIM}Consumate {consumate_raz} razioni di cibo per il sostentamento del party.{RESET}")

        if avventura.get("stato_dungeon", {}).get("luce_ambientale", False):
            extra_notte = "\n[Il riposo trascorre tranquillo e protetto nella sicurezza della locanda/città.]"
        else:
            tiro_notte = random.randint(1, 8)
            t_notte = "[IMBOSCATA NOTTURNA BECMI (1 su 1d8): I turni di guardia scorgono creature ostili attirate dall'accampamento!]" if tiro_notte == 1 else None
            extra_notte = f"\n{t_notte}" if t_notte else "\n[La notte trascorre senza imboscate ostili improvvise.]"

        return f"Il gruppo allestisce un accampamento ed effettua un riposo completo di 8 ore per dormire, medicare le ferite e pregare/studiare i tomi arcani.{extra_notte}"

    return None


def esporta_cronaca_avventura(db, avventura: dict, eroi_party: list):
    dir_cronache = "cronache"
    os.makedirs(dir_cronache, exist_ok=True)
    titolo_pulito = re.sub(r"[^\w\-_]", "_", avventura.get("titolo", "avventura")).strip("_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    nome_file = f"cronaca_{titolo_pulito}_{timestamp}.md"
    percorso_completo = os.path.join(dir_cronache, nome_file)

    turni = len(avventura.get("storia", [])) // 2
    tempo_min = turni * 10
    tempo_str = f"{tempo_min // 60} ore e {tempo_min % 60:02d} minuti"

    righe = []
    righe.append(f"# 📜 Cronaca dell'Avventura: {avventura.get('titolo', 'Avventura D&D')}")
    righe.append(f"\n- **Data Inizio/Aggiornamento:** {avventura.get('data', 'N/D')}")
    righe.append(f"- **Turni di Gioco:** {turni} ({tempo_str} di tempo nel dungeon)")
    righe.append(f"- **Dungeon Master AI:** {MODELLO}")
    righe.append(f"- **Regolamento Attivo:** BECMI Mentzer (Livelli 1-36 + Immortali)")

    righe.append("\n## ⚔️ Compagnia degli Avventurieri (Party)")
    for e in eroi_party:
        soglia = prossima_soglia_pe(e["classe"], e["livello"], e.get("immortale", False))
        soglia_str = f" / {soglia} PE" if soglia else " (Max)"
        imm = " (Immortale)" if e.get("immortale") else ""
        righe.append(f"\n### {e['nome']} — {e['classe']} Livello {e['livello']}{imm} ({e['allineamento']})")
        righe.append(f"- **Punti Ferita:** {e['pf_attuali']}/{e['pf_max']} | **Classe Armatura:** {e['ca']} | **Borsello:** {e['mo']} MO | **PE:** {e['pe']}{soglia_str}")
        righe.append(f"- **Caratteristiche:** FOR {e['forza']} ({mod_caratteristica(e['forza']):+d}), INT {e['intelligenza']} ({mod_caratteristica(e['intelligenza']):+d}), SAG {e['saggezza']} ({mod_caratteristica(e['saggezza']):+d}), DES {e['destrezza']} ({mod_caratteristica(e['destrezza']):+d}), COS {e['costituzione']} ({mod_caratteristica(e['costituzione']):+d}), CAR {e['carisma']} ({mod_caratteristica(e['carisma']):+d})")
        righe.append(f"- **Attacco & THAC0:** {e.get('attacco', '')}")
        righe.append(f"- **Tiri Salvezza:** {e.get('ts', '')}")
        righe.append(f"- **Equipaggiamento:** {', '.join(e.get('equip', []))}")
        prep = e.get("incantesimi_memorizzati", [])
        if prep:
            righe.append(f"- **Incantesimi Preparati:** {', '.join(prep)}")

    note = avventura.get("note") or db.get_note_formattate(avventura["id"])
    if note and note.strip():
        righe.append(f"\n## 📓 Diario e Appunti del Gruppo\n```text\n{note}\n```")

    righe.append("\n## 🗺️ Registro Cronologico dell'Esplorazione")
    storia = avventura.get("storia", [])
    t_num = 1
    for i in range(0, len(storia), 2):
        u_msg = storia[i]["parts"][0]["text"] if i < len(storia) else ""
        m_msg = storia[i+1]["parts"][0]["text"] if i+1 < len(storia) else ""
        righe.append(f"\n### --- Turno {t_num} ---")
        righe.append(f"\n**Gruppo:**\n{u_msg}")
        righe.append(f"\n**Dungeon Master ({MODELLO}):**\n{m_msg}")
        t_num += 1

    contenuto = "\n".join(righe) + "\n"
    with open(percorso_completo, "w", encoding="utf-8") as f:
        f.write(contenuto)

    suona("tesoro")
    print(f"\n{VERDE}{GRASSETTO}Cronaca esportata con successo!{RESET}")
    print(f"{CIANO}Percorso file:{RESET} {os.path.abspath(percorso_completo)}")
    return percorso_completo


def mostra_ultimo_turno_con_dadi(avventura):
    storia = avventura.get("storia", [])
    if not storia:
        return
    if len(storia) >= 2 and storia[-2]["role"] == "user":
        testo_u = storia[-2]["parts"][0]["text"]
        righe_dadi = [r for r in testo_u.split("\n") if "TIRI REALI" in r or "Dado locale" in r]
        if righe_dadi:
            print(f"{GIALLO}{GRASSETTO}" + "\n".join(righe_dadi) + f"{RESET}\n")
    ultimo = storia[-1]
    formatta_risposta(ultimo["parts"][0]["text"], animato=False)


# ==============================================================================
# RACCOLTA AZIONI PARTY & MODALITA' LAN (HOST / CLIENT)
# ==============================================================================

def raccogli_azioni_party_locale(eroi_party: list, prima_azione: str):
    if len(eroi_party) == 1:
        eroe = eroi_party[0]
        if prima_azione.lower().startswith("/gruppo "):
            prima_azione = prima_azione[8:].strip()
        if AUTODADI_ATTIVI:
            bat = genera_batteria_dadi(eroe["nome"])
            if bat["d20"] == 20:
                suona("critico")
            elif bat["d20"] == 1:
                suona("fallimento")
            else:
                suona("dado")
            mostrato = f"{eroe['nome']}: {prima_azione}\n{GIALLO}{GRASSETTO}{bat['testo']}{RESET}"
            inviato = f"{eroe['nome']}: {prima_azione}\n{bat['testo']}"
            return mostrato, inviato
        return f"{eroe['nome']}: {prima_azione}", f"{eroe['nome']}: {prima_azione}"

    if prima_azione.lower().startswith("/gruppo "):
        azione_comune = prima_azione[8:].strip()
        righe_mostrate = [f"{MAGENTA}{GRASSETTO}[AZIONE DI GRUPPO]{RESET} {azione_comune}"]
        righe_inviate = [f"AZIONE COLLETTIVA DEL GRUPPO: {azione_comune}"]
        if AUTODADI_ATTIVI:
            for e in eroi_party:
                bat = genera_batteria_dadi(e["nome"])
                if bat["d20"] == 20:
                    suona("critico")
                elif bat["d20"] == 1:
                    suona("fallimento")
                else:
                    suona("dado")
                righe_mostrate.append(f"{GIALLO}{GRASSETTO}{bat['testo']}{RESET}")
                righe_inviate.append(bat["testo"])
        return "\n".join(righe_mostrate), "\n".join(righe_inviate)

    azioni_round = [(eroi_party[0], prima_azione)]
    for e in eroi_party[1:]:
        print(f"\n{CIANO}{GRASSETTO}Turno di {e['nome']} ({e['classe']} Liv.{e['livello']} | PF {e['pf_attuali']}/{e['pf_max']}):{RESET}")
        az = input(f"{VERDE}> {RESET}").strip()
        if not az or az.lower() == "/salta":
            az = "Resta vigile e in posizione difensiva coprendo i compagni."
        elif az.lower().startswith("/gruppo "):
            az = az[8:].strip()
        elif az.startswith("/") and re.match(r"^/\d*d\d+", az.lower()):
            tiro = tira_dado(az)
            az = f"Tira il dado: {tiro}" if tiro else "Resta in guardia."
        azioni_round.append((e, az))

    righe_mostrate = []
    righe_inviate = []
    for e, az in azioni_round:
        righe_mostrate.append(f"{CIANO}{e['nome']}{RESET}: {az}")
        righe_inviate.append(f"{e['nome']}: {az}")
        if AUTODADI_ATTIVI and "Dado locale" not in az:
            bat = genera_batteria_dadi(e["nome"])
            if bat["d20"] == 20:
                suona("critico")
            elif bat["d20"] == 1:
                suona("fallimento")
            else:
                suona("dado")
            righe_mostrate.append(f"{GIALLO}{GRASSETTO}{bat['testo']}{RESET}")
            righe_inviate.append(bat["testo"])

    return "\n".join(righe_mostrate), "\n".join(righe_inviate)


def invia_pacchetto_lan(sock: socket.socket, obj: dict):
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    sock.sendall(data)


def ricevi_pacchetto_lan(f_obj):
    line = f_obj.readline()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


def avvia_host_lan(db: DnDDatabase, avventure: dict, personaggi: dict, api_key: str):
    os.system("clear" if os.name == "posix" else "cls")
    ip_lan = ottieni_ip_locale()
    print(f"{MAGENTA}{GRASSETTO}=== OSPITA PARTITA IN LAN (SERVER TCP) ==={RESET}")
    print(f"Indirizzo IP locale di questo PC: {VERDE}{GRASSETTO}{ip_lan}{RESET}")
    print(f"{DIM}Digita 0 in qualsiasi momento per tornare al Menu Principale.{RESET}\n")

    porta_str = input(f"{VERDE}Porta TCP (Invio = {DEFAULT_LAN_PORT}, 0 = Menu Principale) > {RESET}").strip()
    if porta_str == "0":
        return
    porta = int(porta_str) if porta_str.isdigit() else DEFAULT_LAN_PORT

    lista_adv = list(avventure.values())
    print(f"\n{GIALLO}Scegli l'avventura da ospitare in LAN:{RESET}")
    for idx, adv in enumerate(lista_adv, 1):
        print(f"  {VERDE}[{idx}]{RESET} {adv['titolo']} ({', '.join(adv.get('party', [adv['eroe']]))})")
    print(f"  {CIANO}[N]{RESET} Crea una nuova avventura")
    print(f"  {DIM}[0] Torna al Menu Principale{RESET}")

    scelta = input(f"\n{VERDE}Scelta > {RESET}").strip().lower()
    if scelta == "0":
        return
    if scelta == "n" or not lista_adv:
        avventura = crea_nuova_avventura(db, avventure, personaggi)
        if not avventura:
            return
    else:
        try:
            avventura = lista_adv[int(scelta) - 1]
        except Exception:
            avventura = lista_adv[0]

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("0.0.0.0", porta))
        server.listen(5)
    except Exception as e:
        print(f"{ROSSO}Impossibile aprire la porta {porta}: {e}{RESET}")
        input("\nPremi INVIO per tornare al Menu Principale...")
        return

    print(f"\n{VERDE}{GRASSETTO}Server LAN attivo su {ip_lan}:{porta}!{RESET}")
    print(f"{GIALLO}Fai collegare gli altri giocatori con: python3 {os.path.basename(sys.argv[0])} --join {ip_lan}{RESET}")
    print(f"{DIM}In attesa di 1 giocatore remoto (oppure premi Ctrl+C per annullare e tornare al menu)...{RESET}")

    try:
        conn, addr = server.accept()
    except KeyboardInterrupt:
        server.close()
        return

    f_remoto = conn.makefile("rb")
    print(f"{VERDE}Giocatore connesso da {addr[0]}!{RESET}")

    invia_pacchetto_lan(conn, {"tipo": "lista_pg", "personaggi": list(personaggi.values())})
    risp_client = ricevi_pacchetto_lan(f_remoto)
    if not risp_client:
        conn.close()
        server.close()
        return

    pg_remoto = risp_client.get("personaggio")
    if pg_remoto:
        db.salva_personaggio(pg_remoto)
        personaggi.update(db.carica_tutti_personaggi())
        if pg_remoto["nome"] not in avventura["party"]:
            avventura["party"].append(pg_remoto["nome"])
            db.salva_metadati_avventura(avventura)

    eroi_party = [personaggi[n] for n in avventura["party"] if n in personaggi]

    if len(avventura["storia"]) <= 1:
        if not avventura["storia"]:
            p_init = f"Gruppo LAN: {', '.join(avventura['party'])}. {SCENARI_AVVENTURA['1'][1]}"
            avventura["storia"] = [{"role": "user", "parts": [{"text": p_init}]}]
            db.aggiungi_messaggio(avventura["id"], "user", p_init)
        testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroi_party, avventura), desc_attesa="sta generando la scena iniziale LAN")
        avventura["storia"].append({"role": "model", "parts": [{"text": testo_dm}]})
        db.aggiungi_messaggio(avventura["id"], "model", testo_dm)
        aggiorna_party_da_riquadro(eroi_party, testo_dm)
        for e in eroi_party:
            db.salva_personaggio(e)

    try:
        while True:
            ultimo_dm = avventura["storia"][-1]["parts"][0]["text"]
            pulisci_schermo(avventura, eroi_party, ruolo_rete=f"HOST LAN {ip_lan}:{porta}")
            formatta_risposta(ultimo_dm, animato=False)
            invia_pacchetto_lan(conn, {"tipo": "stato_turno", "titolo": avventura["titolo"], "testo_dm": ultimo_dm})

            print(f"\n{CIANO}1. Inserisci l'azione locale (o /gruppo <azione>, /stop per tornare al menu):{RESET}")
            az_host = input(f"{VERDE}{GRASSETTO}> {RESET}").strip()
            if az_host.lower() in ["/stop", "/menu", "/0", "/chiudi", "/esci"]:
                invia_pacchetto_lan(conn, {"tipo": "fine_sessione"})
                break

            print(f"{DIM}In attesa dell'azione del giocatore remoto ({pg_remoto['nome']})...{RESET}")
            pkt_remoto = ricevi_pacchetto_lan(f_remoto)
            if not pkt_remoto or pkt_remoto.get("tipo") == "disconnesso":
                print(f"{GIALLO}Il giocatore remoto si e disconnesso.{RESET}")
                time.sleep(1.2)
                break

            az_client = pkt_remoto.get("azione", "Resta in guardia.")
            if az_host.lower().startswith("/gruppo "):
                testo_inviato = f"AZIONE COLLETTIVA DEL GRUPPO: {az_host[8:].strip()}"
            else:
                testo_inviato = f"{eroi_party[0]['nome']}: {az_host}\n{pg_remoto['nome']}: {az_client}"

            if AUTODADI_ATTIVI:
                dadi_txt = "\n".join(genera_batteria_dadi(e["nome"])["testo"] for e in eroi_party)
                testo_inviato = f"{testo_inviato}\n{dadi_txt}"

            avvisi_dungeon = aggiorna_tempo_e_torce(avventura, eroi_party)
            for avviso in avvisi_dungeon:
                print(f"\n{avviso}")

            turno_attuale = (len(avventura["storia"]) // 2) + 1
            evento_errante = verifica_incontro_errante(avventura, turno_attuale)
            if evento_errante:
                print(f"\n{ROSSO}{GRASSETTO}⚠️ {evento_errante}{RESET}")
                testo_inviato = f"{testo_inviato}\n{evento_errante}"

            if avventura.get("buio_totale"):
                testo_inviato = f"{testo_inviato}\n[STATO AMBIENTALE: BUIO TOTALE. Il party non ha torce/fonti di luce accese: -4 ai tiri per colpire, penalita a sorpresa e difesa peggiorata di 4 punti CA.]"

            avventura["storia"].append({"role": "user", "parts": [{"text": testo_inviato}]})
            db.aggiungi_messaggio(avventura["id"], "user", testo_inviato)

            testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroi_party, avventura), desc_attesa="sta risolvendo il round LAN")
            avventura["storia"].append({"role": "model", "parts": [{"text": testo_dm}]})
            db.aggiungi_messaggio(avventura["id"], "model", testo_dm)
            aggiorna_party_da_riquadro(eroi_party, testo_dm)
            st_d = avventura.setdefault("stato_dungeon", {})
            luce_amb, amb_nome, manuale = rileva_ambiente_e_luce(testo_dm, testo_inviato, st_d)
            st_d["luce_ambientale"] = luce_amb
            st_d["ambiente_nome"] = amb_nome
            st_d["ambiente_manuale"] = manuale
            if luce_amb:
                avventura["buio_totale"] = False
            for e in eroi_party:
                db.salva_personaggio(e)
            db.salva_metadati_avventura(avventura)
    finally:
        conn.close()
        server.close()


def avvia_client_lan(host_ip_predefinito=""):
    os.system("clear" if os.name == "posix" else "cls")
    print(f"{MAGENTA}{GRASSETTO}=== UNISCITI A PARTITA IN LAN (CLIENT TCP) ==={RESET}")
    print(f"{DIM}Digita 0 in qualsiasi momento per tornare al Menu Principale.{RESET}\n")

    host_ip = host_ip_predefinito
    if not host_ip:
        host_ip = input(f"{VERDE}Inserisci IP dell'Host LAN (es. 192.168.0.105, 0 = Menu) > {RESET}").strip()
        if host_ip == "0" or not host_ip:
            return

    porta_str = input(f"{VERDE}Porta TCP (Invio = {DEFAULT_LAN_PORT}, 0 = Menu) > {RESET}").strip()
    if porta_str == "0":
        return
    porta = int(porta_str) if porta_str.isdigit() else DEFAULT_LAN_PORT

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        print(f"{DIM}Connessione a {host_ip}:{porta} in corso...{RESET}")
        sock.connect((host_ip, porta))
        sock.settimeout(None)
    except Exception as e:
        print(f"{ROSSO}Connessione fallita verso {host_ip}:{porta} ({e}){RESET}")
        input("\nPremi INVIO per tornare al Menu Principale...")
        return

    f_srv = sock.makefile("rb")
    benvenuto = ricevi_pacchetto_lan(f_srv)
    if not benvenuto:
        sock.close()
        return

    lista_pg = benvenuto.get("personaggi", [])
    print(f"\n{VERDE}Connesso all'Host LAN! Scegli il tuo personaggio:{RESET}")
    for idx, p in enumerate(lista_pg, 1):
        print(f"  {VERDE}[{idx}]{RESET} {p['nome']} ({p['classe']} Liv.{p['livello']} | PF {p['pf_attuali']}/{p['pf_max']})")
    print(f"  {CIANO}[N]{RESET} Crea un nuovo personaggio rapido per questa sessione")
    print(f"  {DIM}[0] Disconnetti e torna al Menu Principale{RESET}")

    scelta = input(f"\n{VERDE}Scelta > {RESET}").strip().lower()
    if scelta == "0":
        sock.close()
        return
    if scelta == "n" or not lista_pg:
        nome_c = input(f"{VERDE}Nome del tuo eroe > {RESET}").strip() or "Avventuriero LAN"
        _, pg_scelto = normalizza_personaggio_json(nome_c, {"nome": nome_c})
    else:
        try:
            pg_scelto = lista_pg[int(scelta) - 1]
        except Exception:
            pg_scelto = lista_pg[0]

    invia_pacchetto_lan(sock, {"tipo": "join_pg", "personaggio": pg_scelto})

    try:
        while True:
            print(f"\n{DIM}In attesa del turno dal Dungeon Master (Host)...{RESET}")
            pkt = ricevi_pacchetto_lan(f_srv)
            if not pkt or pkt.get("tipo") == "fine_sessione":
                print(f"\n{GIALLO}L'Host ha terminato la sessione LAN.{RESET}")
                time.sleep(1.2)
                break

            os.system("clear" if os.name == "posix" else "cls")
            print(f"{MAGENTA}{GRASSETTO}=== CLIENT LAN ({host_ip}) ==={RESET} {GIALLO}{pkt.get('titolo', '')}{RESET} {DIM}| Eroe: {pg_scelto['nome']}{RESET}")
            print(f"{DIM}Digita /stop o /0 per disconnetterti e tornare al Menu Principale{RESET}\n")
            formatta_risposta(pkt.get("testo_dm", ""), animato=False)

            az = input(f"\n{VERDE}{GRASSETTO}[{pg_scelto['nome']}] > {RESET}").strip()
            if az.lower() in ["/stop", "/menu", "/0", "/chiudi", "/esci"]:
                invia_pacchetto_lan(sock, {"tipo": "disconnesso"})
                break
            invia_pacchetto_lan(sock, {"tipo": "azione", "azione": az or "Resta in guardia."})
    finally:
        sock.close()


def esegui_sessione(db: DnDDatabase, avventura: dict, personaggi: dict, api_key: str):
    global SUONI_ATTIVI, AUTODADI_ATTIVI, MODELLO, MODALITA_GIOCO
    party_nomi = avventura.get("party") or [avventura.get("eroe", "Valen di Corvobianco")]
    eroi_party = []
    for nome_e in party_nomi:
        if nome_e not in personaggi:
            _, nuovo_p = normalizza_personaggio_json(nome_e, {})
            db.salva_personaggio(nuovo_p)
            personaggi.update(db.carica_tutti_personaggi())
        eroi_party.append(personaggi[nome_e])

    st_d = avventura.setdefault("stato_dungeon", {})
    if "modalita_gioco" not in st_d:
        st_d["modalita_gioco"] = MODALITA_GIOCO
    if st_d.get("modalita_gioco") == "interattiva":
        AUTODADI_ATTIVI = False
    elif st_d.get("modalita_gioco") == "classica":
        AUTODADI_ATTIVI = True

    # Pulizia automatica: se la sessione si riapre dopo un crash o Ctrl+C con un messaggio 'user' orfano in coda
    if avventura.get("storia") and len(avventura["storia"]) > 1 and avventura["storia"][-1].get("role") == "user":
        avventura["storia"].pop()
        db.rimuovi_ultimo_messaggio(avventura["id"])

    if "luce_ambientale" not in st_d and avventura.get("storia"):
        testo_ultimo = ""
        for m in reversed(avventura["storia"]):
            if m.get("role") == "model":
                parts = m.get("parts", [])
                if parts and "text" in parts[0]:
                    testo_ultimo = parts[0]["text"]
                    break
        luce_amb, amb_nome, _ = rileva_ambiente_e_luce(testo_ultimo, "", st_d)
        st_d["luce_ambientale"] = luce_amb
        st_d["ambiente_nome"] = amb_nome
        if luce_amb:
            st_d["torcia_attiva"] = False
            avventura["buio_totale"] = False

    pulisci_schermo(avventura, eroi_party)

    if len(avventura["storia"]) <= 1:
        if not avventura["storia"]:
            prompt_init = f"Gruppo di avventurieri: {', '.join(party_nomi)}. {SCENARI_AVVENTURA['1'][1]}"
            if AUTODADI_ATTIVI:
                prompt_init += "\n" + "\n".join(genera_batteria_dadi(n)["testo"] for n in party_nomi)
            avventura["storia"] = [{"role": "user", "parts": [{"text": prompt_init}]}]
            db.aggiungi_messaggio(avventura["id"], "user", prompt_init)
            suona("intro")
        try:
            pdf_attivo = avventura.get('modulo_pdf') if not avventura.get('modulo_testo') else None
            testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroi_party, avventura), pdf_path=pdf_attivo, desc_attesa="sta generando la scena iniziale e i tiri")
            avventura["storia"].append({"role": "model", "parts": [{"text": testo_dm}]})
            avventura["data"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            db.aggiungi_messaggio(avventura["id"], "model", testo_dm)
            aggiorna_party_da_riquadro(eroi_party, testo_dm)
            st_d = avventura.setdefault("stato_dungeon", {})
            luce_amb, amb_nome, manuale = rileva_ambiente_e_luce(testo_dm, prompt_init if 'prompt_init' in locals() else '', st_d)
            st_d["luce_ambientale"] = luce_amb
            st_d["ambiente_nome"] = amb_nome
            st_d["ambiente_manuale"] = manuale
            if luce_amb:
                avventura["buio_totale"] = False
            for e in eroi_party:
                db.salva_personaggio(e)
            pulisci_schermo(avventura, eroi_party)
            mostra_ultimo_turno_con_dadi(avventura)
        except Exception as e:
            print(f"{ROSSO}Errore:{RESET}\n", e)
            input("\nPremi INVIO per tornare al menu...")
            return "menu"
    else:
        mostra_ultimo_turno_con_dadi(avventura)

    while True:
        primo_eroe = eroi_party[0]
        # Controllo se l'ultimo messaggio del DM contiene una chiamata dado
        ultimo_dm_testo = ""
        for m in reversed(avventura.get("storia", [])):
            if m.get("role") == "model":
                parts = m.get("parts", [])
                if parts and "text" in parts[0]:
                    ultimo_dm_testo = parts[0]["text"]
                    break
        chiamate_dado = estrai_chiamata_dado(ultimo_dm_testo)

        pg_chiamato = primo_eroe["nome"]
        if chiamate_dado:
            for ch in chiamate_dado:
                for e in eroi_party:
                    if e["nome"].lower() in ch.lower():
                        pg_chiamato = e["nome"]
                        break
            print(f"\n{GIALLO}╔════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
            for ch in chiamate_dado:
                print(f"{GIALLO}║ 🎲 {ROSSO}{GRASSETTO}IL DM ATTENDE IL TUO TIRO:{RESET} {CIANO}{GRASSETTO}{ch}{RESET}")
            print(f"{GIALLO}║ {DIM}Puoi lanciare un dado reale dal vivo e digitare il numero (es. 16), oppure digitare /d20{RESET}")
            print(f"{GIALLO}╚════════════════════════════════════════════════════════════════════════════════════════╝{RESET}")
            prompt_input = f"\n{VERDE}{GRASSETTO}[{pg_chiamato} - TIRO DADO] > {RESET}"
        else:
            prompt_input = f"\n{VERDE}{GRASSETTO}[{primo_eroe['nome']}] > {RESET}" if len(eroi_party) > 1 else f"\n{VERDE}{GRASSETTO}> {RESET}"
        try:
            azione = input(prompt_input).strip()
        except (KeyboardInterrupt, EOFError):
            for e in eroi_party:
                db.salva_personaggio(e)
            return "chiudi"

        if not azione:
            continue

        cmd = azione.lower()

        # Rilevamento intenti torcia in linguaggio naturale (es. "spegni la torcia", "accendi la torcia")
        intento_t = rileva_intento_torcia(azione) if not cmd.startswith("/") else None
        if intento_t == "off":
            st_d = avventura.setdefault("stato_dungeon", {})
            st_d["torcia_attiva"] = False
            avventura["torcia_attiva"] = False
            t_rim = st_d.get("torcia_turni", 6)
            db.salva_metadati_avventura(avventura)
            print(f"\n{VERDE}🕯️ Hai spento la torcia e l'hai riposta al sicuro nello zaino (turni conservati: {t_rim}/6 t).{RESET}")
            if st_d.get("luce_ambientale"):
                print(f"{CIANO}Ti trovi in un luogo illuminato ({st_d.get('ambiente_nome', 'Taverna')}): nessuna penalità di buio.{RESET}")
            else:
                print(f"{GIALLO}⚠️ Sei in un dungeon/luogo buio: senza torcia sei nel BUIO TOTALE (-4 TxC/CA). Per riaccenderla usa '/torcia on' o scrivi 'accendi la torcia'.{RESET}")
            pure_spegni = [
                "spegni la torcia", "spengo la torcia", "spegniamo le torce", "spegni torcia",
                "spegnete le torce", "mettiamo via la torcia", "metto via la torcia", "ripongo la torcia",
                "mettiamo via le torce", "spegni le torce", "spengo torcia", "spegnere la torcia"
            ]
            if cmd in pure_spegni:
                continue
        elif intento_t == "on":
            st_d = avventura.setdefault("stato_dungeon", {})
            t_rim = st_d.get("torcia_turni", 0)
            if t_rim > 0:
                st_d["torcia_attiva"] = True
                avventura["torcia_attiva"] = True
                avventura["buio_totale"] = False
                db.salva_metadati_avventura(avventura)
                print(f"\n{VERDE}🔥 Hai riacceso la torcia! ({t_rim}/6 turni rimanenti).{RESET}")
            else:
                trovata = False
                for e in eroi_party:
                    for idx, item in enumerate(e.get("equip", [])):
                        if "torc" in item.lower():
                            trovata = True
                            m = re.search(r"(\d+)\s+Torce?", item, re.IGNORECASE)
                            if m:
                                cnt = int(m.group(1)) - 1
                                if cnt > 0:
                                    e["equip"][idx] = f"{cnt} Torce"
                                else:
                                    e["equip"].pop(idx)
                            else:
                                e["equip"].pop(idx)
                            db.salva_personaggio(e)
                            break
                    if trovata:
                        break
                st_d["torcia_turni"] = 6
                st_d["torcia_attiva"] = True
                avventura["torcia_turni_rimasti"] = 6
                avventura["buio_totale"] = False
                db.salva_metadati_avventura(avventura)
                if trovata:
                    print(f"\n{VERDE}🔥 Nuova torcia estratta dallo zaino e accesa! (6/6 turni garantiti).{RESET}")
                else:
                    print(f"\n{GIALLO}🔥 Torcia accesa (nessuna scorta consumata). (6/6 turni).{RESET}")
            pure_accendi = [
                "accendi la torcia", "accendo la torcia", "accendiamo le torce", "accendi torcia",
                "accendete le torce", "accendiamo una torcia", "tira fuori una torcia", "estraggo una torcia",
                "accendi una torcia", "accendere la torcia"
            ]
            if cmd in pure_accendi:
                continue
        if cmd in ["/chiudi", "/esci", "/quit", "/exit"]:
            for e in eroi_party:
                db.salva_personaggio(e)
            print(f"\n{VERDE}Database SQLite sincronizzato. Chiusura del programma in corso...{RESET}")
            return "chiudi"

        if cmd in ["/stop", "/interrompi", "/avventure", "/menu", "/cambia", "/0", "0"]:
            for e in eroi_party:
                db.salva_personaggio(e)
            print(f"\n{GIALLO}Avventura salvata in SQLite. Ritorno al Menu Principale...{RESET}")
            time.sleep(0.5)
            return "menu"

        if cmd in ["/help", "/aiuto", "/?", "/comandi"] or cmd.startswith("/help ") or cmd.startswith("/comandi "):
            subcmd = azione.split(maxsplit=1)[1].strip().lower() if " " in azione else ""
            if subcmd in ["pdf", "a4", "manuale", "stampa"]:
                aggiorna_manuale_comandi_pdf(forza=True, silenzioso=False)
            else:
                pulisci_schermo(avventura, eroi_party)
                print(HELP_TESTO)
                opz_pdf = input(f"\n{VERDE}Vuoi aprire o rigenerare il Manuale dei Comandi in PDF A4? (s/n) > {RESET}").strip().lower()
                if opz_pdf in ["s", "si", "y", "yes"]:
                    aggiorna_manuale_comandi_pdf(forza=True, silenzioso=False)
            print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd == "/party":
            pulisci_schermo(avventura, eroi_party)
            mostra_riepilogo_party(eroi_party)
            print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd in ["/sql", "/db"]:
            st = db.statistiche_db()
            print(f"\n{CIANO}{GRASSETTO}=== STATO DATABASE SQLITE ==={RESET}")
            print(f"File: {st['file']} ({st['size_kb']} KB)")
            print(f"Eroi salvati: {st['personaggi']} | Oggetti inventario: {st['inventario']}")
            print(f"Avventure: {st['avventure']} | Messaggi cronologia: {st['messaggi']} | Note diario: {st['note']}")
            continue

        if cmd in ["/modello", "/ai", "/model"] or cmd.startswith("/modello ") or cmd.startswith("/ai "):
            parti = azione.split(maxsplit=1)
            if len(parti) > 1:
                nuovo_mod = parti[1].strip()
                if nuovo_mod in MODELLI_FALLBACK:
                    MODELLO = nuovo_mod
                    print(f"\n{VERDE}Modello AI impostato su: {GRASSETTO}{MODELLO}{RESET}")
                else:
                    print(f"\n{GIALLO}Modello '{nuovo_mod}' non valido.{RESET}")
                    print(f"Modelli disponibili: {', '.join(MODELLI_FALLBACK)}")
            else:
                print(f"\n{CIANO}{GRASSETTO}=== STATO MODELLO AI ==={RESET}")
                print(f"Modello attualmente attivo: {VERDE}{GRASSETTO}{MODELLO}{RESET}")
                print(f"Catena di fallback: {DIM}{' -> '.join(MODELLI_FALLBACK)}{RESET}")
                print(f"{DIM}Per cambiare modello usa: /modello <nome> (es. /modello gemini-3.8-flash){RESET}")
            continue

        if cmd in ["/inventario", "/zaino", "/equip", "inventario", "zaino"] or cmd.startswith("/inventario ") or cmd.startswith("/zaino ") or cmd.startswith("/equip "):
            subcmd = azione.split(maxsplit=1)[1].strip().lower() if " " in azione else ""
            pulisci_schermo(avventura, eroi_party)
            if subcmd in ["party", "gruppo", "tutti", "all"]:
                mostra_inventario_party(eroi_party)
            elif subcmd:
                trovato = None
                for e in eroi_party:
                    if subcmd in e["nome"].lower():
                        trovato = e
                        break
                if trovato:
                    mostra_inventario(trovato)
                else:
                    mostra_inventario_party(eroi_party)
            else:
                if len(eroi_party) == 1:
                    mostra_inventario(eroi_party[0])
                else:
                    print(f"{CIANO}{GRASSETTO}=== GESTIONE INVENTARIO & ZAINO ==={RESET}")
                    for idx, e in enumerate(eroi_party, 1):
                        print(f"  {VERDE}[{idx}]{RESET} {e['nome']} ({e['classe']} Liv.{e['livello']}) — {GIALLO}{e['mo']} MO{RESET}")
                    print(f"  {GIALLO}[T]{RESET} Visualizza l'inventario completo di TUTTO il gruppo")
                    scelta_inv = input(f"\n{VERDE}Seleziona personaggio (o 0 per annullare) > {RESET}").strip().lower()
                    if scelta_inv in ["t", "tutti", "all"]:
                        pulisci_schermo(avventura, eroi_party)
                        mostra_inventario_party(eroi_party)
                    elif scelta_inv.isdigit() and 1 <= int(scelta_inv) <= len(eroi_party):
                        pulisci_schermo(avventura, eroi_party)
                        mostra_inventario(eroi_party[int(scelta_inv) - 1])

            print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd in ["/scheda", "/schedapdf", "/pdfscheda"] or cmd.startswith("/scheda "):
            subcmd = azione.split(maxsplit=1)[1].strip().lower() if " " in azione else ""
            if subcmd in ["pdf", "a4", "stampa", "esporta"] or cmd in ["/schedapdf", "/pdfscheda"]:
                if len(eroi_party) == 1:
                    esporta_scheda_pdf_a4(eroi_party[0])
                else:
                    print(f"\n{CIANO}{GRASSETTO}=== STAMPA SCHEDA PERSONAGGIO IN PDF A4 ==={RESET}")
                    for idx, e in enumerate(eroi_party, 1):
                        print(f"  {VERDE}[{idx}]{RESET} {e['nome']} ({e['classe']} Liv.{e['livello']})")
                    print(f"  {GIALLO}[T]{RESET} Stampa le schede di TUTTI i membri del party ({len(eroi_party)} eroi)")
                    scelta_pg = input(f"\n{VERDE}Seleziona personaggio (o 0 per annullare) > {RESET}").strip().lower()
                    if scelta_pg in ["t", "tutti", "all"]:
                        for e in eroi_party:
                            esporta_scheda_pdf_a4(e)
                    elif scelta_pg.isdigit() and 1 <= int(scelta_pg) <= len(eroi_party):
                        esporta_scheda_pdf_a4(eroi_party[int(scelta_pg) - 1])
                print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
                mostra_ultimo_turno_con_dadi(avventura)
            else:
                eroe_sel = scegli_membro_party(eroi_party, "visualizzare la scheda")
                if eroe_sel:
                    pulisci_schermo(avventura, eroi_party)
                    mostra_scheda(eroe_sel)
                    opz_pdf = input(f"\n{VERDE}Vuoi generare il PDF in formato A4 di questa scheda? (s/n) > {RESET}").strip().lower()
                    if opz_pdf in ["s", "si", "y", "yes"]:
                        esporta_scheda_pdf_a4(eroe_sel)
                    print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
                    mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd in ["/emporio", "/negozio"]:
            apri_emporio(db, eroi_party, avventura)
            pulisci_schermo(avventura, eroi_party)
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd in ["/livello", "/levelup"]:
            gestisci_comando_livello(db, eroi_party, avventura)
            pulisci_schermo(avventura, eroi_party)
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd in ["/magia", "/incantesimi", "/grimorio", "/spells"] or cmd.startswith("/magia ") or cmd.startswith("/incantesimi "):
            parti = azione.split(maxsplit=1)
            arg = parti[1].strip().lower() if len(parti) > 1 else ""
            incantatori = [e for e in eroi_party if slot_incantesimi_per_cerchio(e["classe"], e["livello"], e.get("immortale", False))]
            if not incantatori:
                print(f"\n{GIALLO}Nessun membro del gruppo e in grado di lanciare incantesimi.{RESET}")
            else:
                eroe_sel = scegli_membro_party(incantatori, "gestire gli incantesimi") if len(incantatori) > 1 else incantatori[0]
                if eroe_sel:
                    pulisci_schermo(avventura, eroi_party)
                    mostra_grimorio_e_incantesimi(eroe_sel)
                    if arg in ["memorizza", "prepara", "cambia"] or not eroe_sel.get("incantesimi_memorizzati"):
                        memorizza_incantesimo_eroe(db, eroe_sel)
                    print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
                    mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd in ["/memorizza", "/prepara"] or cmd.startswith("/memorizza ") or cmd.startswith("/prepara "):
            incantatori = [e for e in eroi_party if slot_incantesimi_per_cerchio(e["classe"], e["livello"], e.get("immortale", False))]
            if not incantatori:
                print(f"\n{GIALLO}Nessun membro del gruppo puo memorizzare incantesimi.{RESET}")
            else:
                eroe_sel = scegli_membro_party(incantatori, "memorizzare incantesimi") if len(incantatori) > 1 else incantatori[0]
                if eroe_sel:
                    pulisci_schermo(avventura, eroi_party)
                    memorizza_incantesimo_eroe(db, eroe_sel)
                    print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
                    mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd.startswith("/lancia") or cmd.startswith("/cast"):
            azione_lancio = gestisci_comando_lancia(db, eroi_party, avventura, azione)
            if not azione_lancio:
                continue
            azione = azione_lancio

        if cmd in ["/riposo", "/accampamento", "/dormi", "/camp", "/rest"]:
            azione_riposo = gestisci_comando_riposo(db, eroi_party, avventura)
            if not azione_riposo:
                continue
            azione = azione_riposo

        if cmd.startswith("/torcia") or cmd.startswith("/luce") or cmd in ["/torcia", "/luce", "/torce"]:
            sub_arg = azione.split()[1] if len(azione.split()) > 1 else ""
            gestisci_comando_torcia(db, eroi_party, avventura, sub_arg)
            continue

        if cmd.startswith("/ambiente"):
            sub_arg = azione.split()[1] if len(azione.split()) > 1 else ""
            gestisci_comando_ambiente(db, avventura, sub_arg)
            continue

        if cmd.startswith("/incontri") or cmd.startswith("/erranti"):
            sub_arg = azione.split()[1] if len(azione.split()) > 1 else ""
            gestisci_comando_incontri(db, avventura, sub_arg)
            continue

        if cmd.startswith("/modalita") or cmd.startswith("/interactive") or cmd in ["/modalita", "/classica"]:
            sub_arg = azione.split()[1] if len(azione.split()) > 1 else ""
            if cmd == "/classica":
                sub_arg = "classica"
            elif cmd.startswith("/interactive"):
                sub_arg = "interattiva"
            gestisci_comando_modalita(db, avventura, sub_arg)
            continue

        if cmd in ["/esporta", "/export", "/salva_cronaca"] or cmd.startswith("/esporta ") or cmd.startswith("/export "):
            pulisci_schermo(avventura, eroi_party)
            subcmd = azione.split(maxsplit=1)[1].strip().lower() if " " in azione else ""
            if subcmd in ["mappa", "mappapdf"]:
                esporta_mappa_pdf_a4(avventura, eroi_party, api_key=api_key)
            elif subcmd in ["scheda", "schede", "schedapdf"]:
                for e in eroi_party:
                    esporta_scheda_pdf_a4(e)
            elif subcmd in ["manuale", "comandi", "help"]:
                aggiorna_manuale_comandi_pdf(forza=True, silenzioso=False)
            else:
                esporta_cronaca_avventura(db, avventura, eroi_party)
                opz_m = input(f"\n{VERDE}Vuoi esportare anche la Mappa A4 PDF per la campagna? (s/n) > {RESET}").strip().lower()
                if opz_m in ["s", "si", "y", "yes"]:
                    esporta_mappa_pdf_a4(avventura, eroi_party, api_key=api_key)
                opz_s = input(f"{VERDE}Vuoi esportare anche le Schede Personaggio A4 PDF del party? (s/n) > {RESET}").strip().lower()
                if opz_s in ["s", "si", "y", "yes"]:
                    for e in eroi_party:
                        esporta_scheda_pdf_a4(e)
            print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd == "/aggiorna":
            aggiorna_manuale_eroe(db, eroi_party)
            pulisci_schermo(avventura, eroi_party)
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd == "/autodadi":
            AUTODADI_ATTIVI = not AUTODADI_ATTIVI
            stato = "ATTIVATI (tiri reali completi ad ogni turno)" if AUTODADI_ATTIVI else "DISATTIVATI (tira solo il DM o /d20)"
            print(f"{GIALLO}Autodadi {stato}.{RESET}")
            continue

        if cmd in ["/mappa", "/mappapdf", "/pdfmappa"] or cmd.startswith("/mappa "):
            subcmd = azione.split(maxsplit=1)[1].strip().lower() if " " in azione else ""
            try:
                mappa = genera_mappa_ascii(avventura, api_key, eroi_party)
                avventura["ultima_mappa_ascii"] = mappa
                pulisci_schermo(avventura, eroi_party)
                print(f"{CIANO}{GRASSETTO}=== MAPPA DELL'ESPLORAZIONE ==={RESET}\n\n{mappa}")

                if subcmd in ["pdf", "a4", "stampa", "esporta"] or cmd in ["/mappapdf", "/pdfmappa"]:
                    esporta_mappa_pdf_a4(avventura, eroi_party, testo_mappa=mappa, api_key=api_key)
                else:
                    opz_pdf = input(f"\n{VERDE}Vuoi generare il PDF in formato A4 con la mappa per la campagna? (s/n) > {RESET}").strip().lower()
                    if opz_pdf in ["s", "si", "y", "yes"]:
                        esporta_mappa_pdf_a4(avventura, eroi_party, testo_mappa=mappa, api_key=api_key)

                print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
                mostra_ultimo_turno_con_dadi(avventura)
            except Exception as e:
                print(f"{ROSSO}Impossibile generare la mappa:{RESET}", e)
            continue

        if cmd in ["/suoni", "/audio"] or cmd.startswith("/suoni ") or cmd.startswith("/audio "):
            parti = azione.split(maxsplit=1)
            arg = parti[1].strip().lower() if len(parti) > 1 else ""
            if arg in ["test", "prova"]:
                testa_effetti_sonori()
            else:
                SUONI_ATTIVI = not SUONI_ATTIVI
                stato = "ATTIVATI" if SUONI_ATTIVI else "DISATTIVATI"
                print(f"{GIALLO}Effetti sonori {stato}. Digita '/suoni test' per ascoltare una prova audio.{RESET}")
            continue

        if cmd == "/storico":
            pulisci_schermo(avventura, eroi_party)
            print(f"{GIALLO}=== ULTIMI 3 TURNI ==={RESET}\n")
            for msg in avventura["storia"][-6:]:
                ruolo = f"{VERDE}GRUPPO:{RESET}" if msg["role"] == "user" else f"{CIANO}DM:{RESET}"
                print(f"{ruolo} {msg['parts'][0]['text']}\n")
            continue

        if cmd.startswith("/nota"):
            testo_nota = azione[5:].strip()
            if testo_nota:
                db.aggiungi_nota(avventura["id"], testo_nota)
                avventura["note"] = db.get_note_formattate(avventura["id"])
                print(f"{GIALLO}Appunto salvato nel diario SQLite.{RESET}")
            elif avventura.get("note"):
                print(f"\n{GIALLO}=== DIARIO: {avventura['titolo'].upper()} ==={RESET}\n{avventura['note']}")
            else:
                print("Nessun appunto salvato. Usa: /nota <testo da ricordare>")
            continue

        if cmd == "/riassunto":
            try:
                comprimi_memoria(db, avventura, api_key, costruisci_system_prompt(eroi_party, avventura))
            except Exception as e:
                print(f"{ROSSO}Errore durante il riassunto:{RESET}", e)
            continue

        # Riconoscimento rapido tiro reale digitato a mano (es. "16", "ho fatto 15", "tiro 18", "dado: 14", "16+1=17")
        match_tiro_reale = re.match(r"^(?:ho\s+fatto|tiro(?:\s*dado)?|dado|risultato)?\s*[:=]?\s*(\d{1,3}(?:\s*[+-]\s*\d+)?(?:\s*=\s*\d+)?)$", azione.strip(), re.IGNORECASE)
        if match_tiro_reale and (chiamate_dado or st_d.get("modalita_gioco") == "interattiva"):
            val_tiro = match_tiro_reale.group(1).strip()
            suona("dado")
            print(f"{VERDE}🎲 Risultato del tiro reale registrato: {GRASSETTO}{val_tiro}{RESET}")
            azione_effettiva = f"Ho effettuato il tiro reale richiesto: [TIRO REALE: {val_tiro}]. Risolvi la prova applicando le regole BECMI e narra le conseguenze."
            testo_mostrato, testo_inviato = raccogli_azioni_party_locale(eroi_party, azione_effettiva)
        elif cmd.startswith("/") and re.match(r"^/\d*d\d+", cmd):
            tiro = tira_dado(azione)
            if tiro:
                azione_effettiva = f"Ho effettuato il tiro richiesto con dadi reali: [TIRO REALE {azione.lstrip('/')}: {tiro}]. Risolvi la prova applicando le regole BECMI e narra le conseguenze."
                testo_mostrato, testo_inviato = raccogli_azioni_party_locale(eroi_party, azione_effettiva)
            else:
                print("Formato dado non valido. Esempi: /d20, /d8+1, /2d6")
                continue
        else:
            testo_mostrato, testo_inviato = raccogli_azioni_party_locale(eroi_party, azione)

        avvisi_dungeon = aggiorna_tempo_e_torce(avventura, eroi_party)
        for avviso in avvisi_dungeon:
            print(f"\n{avviso}")

        # Incontro errante BECMI: controllo dungeon bilanciato con frequenza e cooldown
        turno_attuale = (len(avventura["storia"]) // 2) + 1
        evento_errante = verifica_incontro_errante(avventura, turno_attuale)
        if evento_errante:
            print(f"\n{ROSSO}{GRASSETTO}⚠️ {evento_errante}{RESET}")
            testo_inviato = f"{testo_inviato}\n{evento_errante}"

        if avventura.get("buio_totale"):
            testo_inviato = f"{testo_inviato}\n[STATO AMBIENTALE: BUIO TOTALE. Il party non ha torce/fonti di luce accese: -4 ai tiri per colpire, penalita a sorpresa e difesa peggiorata di 4 punti CA.]"

        avventura["storia"].append({"role": "user", "parts": [{"text": testo_inviato}]})
        db.aggiungi_messaggio(avventura["id"], "user", testo_inviato)

        print(f"\n{testo_mostrato}")
        try:
            pdf_attivo = avventura.get('modulo_pdf') if not avventura.get('modulo_testo') else None
            testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroi_party, avventura), pdf_path=pdf_attivo, desc_attesa="sta valutando la scena e tirando i dadi")
            avventura["storia"].append({"role": "model", "parts": [{"text": testo_dm}]})
            avventura["data"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            db.aggiungi_messaggio(avventura["id"], "model", testo_dm)
            aggiorna_party_da_riquadro(eroi_party, testo_dm)
            st_d = avventura.setdefault("stato_dungeon", {})
            luce_amb, amb_nome, manuale = rileva_ambiente_e_luce(testo_dm, testo_inviato, st_d)
            st_d["luce_ambientale"] = luce_amb
            st_d["ambiente_nome"] = amb_nome
            st_d["ambiente_manuale"] = manuale
            if luce_amb:
                avventura["buio_totale"] = False
            for e in eroi_party:
                db.salva_personaggio(e)
            db.salva_metadati_avventura(avventura)
            pulisci_schermo(avventura, eroi_party)
            print(f"{DIM}{testo_mostrato}{RESET}\n")
            try:
                import termios
                termios.tcflush(sys.stdin, termios.TCIFLUSH)
            except Exception:
                pass
            formatta_risposta(testo_dm, animato=True)
        except (Exception, KeyboardInterrupt) as e:
            if isinstance(e, KeyboardInterrupt):
                print(f"\n{GIALLO}Azione interrotta dall'utente (Ctrl+C).{RESET}")
            else:
                print(f"{ROSSO}Errore:{RESET}\n", e)
            if avventura.get("storia") and avventura["storia"][-1].get("role") == "user":
                avventura["storia"].pop()
                db.rimuovi_ultimo_messaggio(avventura["id"])


def main():
    global API_KEY_ATTIVA
    if "--join" in sys.argv:
        idx = sys.argv.index("--join")
        ip_target = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ""
        avvia_client_lan(ip_target)
        return

    # 1. Se passata come argomento CLI (es. python3 dnd_fork.py AIzaSy...)
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        API_KEY_ATTIVA = sys.argv[1].strip()
    else:
        # 2. Richiesta o caricamento interattivo all'avvio
        API_KEY_ATTIVA = richiedi_api_key_interattiva(forza_richiesta=False)

    if not API_KEY_ATTIVA:
        print(f"\n{ROSSO}Avvio annullato: nessuna chiave API fornita.{RESET}")
        print(f"{DIM}Per ottenere una chiave gratuita visita: https://aistudio.google.com/app/apikey{RESET}")
        return

    api_key = API_KEY_ATTIVA
    db = DnDDatabase(DB_FILE)
    sintetizza_suoni_mancanti()
    aggiorna_manuale_comandi_pdf(forza=False, silenzioso=True)
    try:
        avventure, personaggi = migra_json_in_sqlite(db)

        while True:
            avventura_scelta, modo = menu_principale(db, avventure, personaggi)
            api_key = API_KEY_ATTIVA
            if modo == "exit":
                print(f"\n{GIALLO}Arrivederci, avventuriero! Tutti i progressi sono salvati in {DB_FILE}.{RESET}")
                break
            elif modo == "host_lan":
                if not api_key:
                    print(f"{ROSSO}Per ospitare una partita LAN serve la chiave API Gemini! Usa il menu [K].{RESET}")
                    time.sleep(1.5)
                    continue
                avvia_host_lan(db, avventure, personaggi, api_key)
                avventure = db.carica_tutte_avventure()
                personaggi = db.carica_tutti_personaggi()
            elif modo == "join_lan":
                avvia_client_lan()
            elif avventura_scelta:
                if not api_key:
                    print(f"{ROSSO}Chiave API Gemini mancante! Usa il menu [K] per impostarla.{RESET}")
                    time.sleep(1.5)
                    continue
                esito = esegui_sessione(db, avventura_scelta, personaggi, api_key)
                if esito == "chiudi":
                    break
    finally:
        db.chiudi()


if __name__ == "__main__":
    main()