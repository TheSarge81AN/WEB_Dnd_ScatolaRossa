import os
import sys
import re
import json
import time
import socket
import base64
import random
import select
import sqlite3
import subprocess
from datetime import datetime

DB_FILE = "dnd_becmi.db"
ADVENTURES_FILE = "avventure_dnd.json"
MODULI_DIR = "moduli_pdf"
CHARACTERS_FILE = "personaggi_dnd.json"
LEGACY_SAVE = "salvataggio_dnd.json"
LEGACY_DIARY = "diario_avventura.txt"
MODELLI_FALLBACK = [
    "gemini-3.8-flash",
    "gemini-3.8-flash-high",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest"
]
MODELLO = MODELLI_FALLBACK[0]
DEFAULT_LAN_PORT = 5555

VERDE = "\033[92m"
GIALLO = "\033[93m"
CIANO = "\033[96m"
ROSSO = "\033[91m"
MAGENTA = "\033[95m"
GRASSETTO = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

SUONI_ATTIVI = True
AUTODADI_ATTIVI = True

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
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self._crea_schema()

    def _crea_schema(self):
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS personaggi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    classe TEXT NOT NULL,
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
            cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(avventure)").fetchall()]
            if "party_json" not in cols:
                self.conn.execute("ALTER TABLE avventure ADD COLUMN party_json TEXT DEFAULT '[]'")

    def salva_personaggio(self, eroe: dict):
        sincronizza_statistiche_becmi(eroe)
        with self.conn:
            cur = self.conn.execute("SELECT id FROM personaggi WHERE nome = ?", (eroe["nome"],))
            row = cur.fetchone()
            if row:
                pg_id = row["id"]
                self.conn.execute("""
                    UPDATE personaggi SET
                        classe = ?, livello = ?, allineamento = ?, immortale = ?,
                        forza = ?, intelligenza = ?, saggezza = ?, destrezza = ?,
                        costituzione = ?, carisma = ?, pf_attuali = ?, pf_max = ?,
                        ca = ?, mo = ?, pe = ?, ts = ?, attacco = ?,
                        abilita_classe = ?, fascia_becmi = ?
                    WHERE id = ?
                """, (
                    eroe["classe"], int(eroe["livello"]), eroe["allineamento"], int(bool(eroe.get("immortale", False))),
                    int(eroe["forza"]), int(eroe["intelligenza"]), int(eroe["saggezza"]), int(eroe["destrezza"]),
                    int(eroe["costituzione"]), int(eroe["carisma"]), int(eroe["pf_attuali"]), int(eroe["pf_max"]),
                    int(eroe["ca"]), int(eroe["mo"]), int(eroe["pe"]),
                    eroe.get("ts", ""), eroe.get("attacco", ""), eroe.get("abilita_classe", ""), eroe.get("fascia_becmi", ""),
                    pg_id
                ))
            else:
                cur = self.conn.execute("""
                    INSERT INTO personaggi (
                        nome, classe, livello, allineamento, immortale,
                        forza, intelligenza, saggezza, destrezza, costituzione, carisma,
                        pf_attuali, pf_max, ca, mo, pe, ts, attacco, abilita_classe, fascia_becmi
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    eroe["nome"], eroe["classe"], int(eroe["livello"]), eroe["allineamento"], int(bool(eroe.get("immortale", False))),
                    int(eroe["forza"]), int(eroe["intelligenza"]), int(eroe["saggezza"]), int(eroe["destrezza"]),
                    int(eroe["costituzione"]), int(eroe["carisma"]), int(eroe["pf_attuali"]), int(eroe["pf_max"]),
                    int(eroe["ca"]), int(eroe["mo"]), int(eroe["pe"]),
                    eroe.get("ts", ""), eroe.get("attacco", ""), eroe.get("abilita_classe", ""), eroe.get("fascia_becmi", "")
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
            sincronizza_statistiche_becmi(pg)
            personaggi[pg["nome"]] = pg
        return personaggi

    def salva_metadati_avventura(self, adv: dict):
        party_list = adv.get("party") or [adv.get("eroe", "Valen di Corvobianco")]
        party_str = json.dumps(party_list, ensure_ascii=False)
        eroe_principale = party_list[0]
        with self.conn:
            self.conn.execute("""
                INSERT INTO avventure (id, titolo, eroe_nome, party_json, data_aggiornamento, modulo_pdf, modulo_testo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    titolo = excluded.titolo,
                    eroe_nome = excluded.eroe_nome,
                    party_json = excluded.party_json,
                    data_aggiornamento = excluded.data_aggiornamento,
                    modulo_pdf = excluded.modulo_pdf,
                    modulo_testo = excluded.modulo_testo
            """, (
                adv["id"], adv["titolo"], eroe_principale, party_str,
                adv.get("data", datetime.now().strftime("%d/%m/%Y %H:%M")),
                adv.get("modulo_pdf", ""), adv.get("modulo_testo", "")
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
        cur = self.conn.execute("SELECT * FROM avventure ORDER BY rowid ASC")
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

            avventure[adv_id] = {
                "id": adv_id,
                "titolo": r["titolo"],
                "eroe": party[0],
                "party": party,
                "data": r["data_aggiornamento"],
                "storia": storia,
                "note": self.get_note_formattate(adv_id),
                "modulo_pdf": r["modulo_pdf"] or "",
                "modulo_testo": r["modulo_testo"] or ""
            }
        return avventure

    def statistiche_db(self) -> dict:
        pg_cnt = self.conn.execute("SELECT COUNT(*) FROM personaggi").fetchone()[0]
        adv_cnt = self.conn.execute("SELECT COUNT(*) FROM avventure").fetchone()[0]
        msg_cnt = self.conn.execute("SELECT COUNT(*) FROM messaggi_storia").fetchone()[0]
        note_cnt = self.conn.execute("SELECT COUNT(*) FROM diario_note").fetchone()[0]
        inv_cnt = self.conn.execute("SELECT COUNT(*) FROM inventario").fetchone()[0]
        size_kb = round(os.path.getsize(self.db_path) / 1024, 1) if os.path.exists(self.db_path) else 0
        return {
            "file": self.db_path,
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


def calcola_slot_o_abilita(classe, livello, immortale=False):
    if immortale:
        for l_min, l_max, rango, pp in RANGHI_IMMORTALI:
            if l_min <= livello <= l_max:
                return f"Rango Immortale: {rango} (Liv. Immortale {livello}) | Punti Potere (PP): {pp + (livello - l_min) * 25}"
        return f"Rango Immortale: Gerarca (Liv. {livello}) | PP: 1000+"

    c = classe.lower()
    if c in ["mago", "elfo"]:
        max_cerchio = 5 if c == "elfo" else 9
        slots = []
        for cerchio in range(1, max_cerchio + 1):
            liv_sblocco = (cerchio - 1) * 2 + 1
            if livello >= liv_sblocco:
                n = min(6, 1 + (livello - liv_sblocco) // 2)
                slots.append(f"{cerchio}°:{n}")
        return ("Slot Incantesimi Arcani: " + " | ".join(slots)) if slots else "Nessuno slot"

    if c in ["chierico", "druido"]:
        if livello == 1 and c == "chierico":
            return "Slot Incantesimi Divini: Nessuno al 1° liv. (sblocca 1° cerchio al 2° liv.)"
        slots = []
        for cerchio in range(1, 8):
            liv_sblocco = 2 if (cerchio == 1 and c == "chierico") else (1 if cerchio == 1 else cerchio * 2)
            if livello >= liv_sblocco:
                n = min(6, 1 + (livello - liv_sblocco) // 2)
                slots.append(f"{cerchio}°:{n}")
        return ("Slot Incantesimi Divini: " + " | ".join(slots)) if slots else "Nessuno slot"

    if c == "paladino":
        if livello < 9:
            return "Poteri Paladino: Imposizione mani, Individuazione male, Immunita malattie (Incantesimi dal 9° liv.)"
        slots = [f"{cerchio}°:{min(3, 1 + (livello - (7 + cerchio * 2)) // 3)}" for cerchio in range(1, 5) if livello >= 7 + cerchio * 2]
        return "Poteri Paladino + Slot Chierico: " + " | ".join(slots)

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
        suona("critico")
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
                                     /           /
                                    /' .,,,,  ./
                                   /';'     ,/
                                  / /   ,,//,`'`
                                 ( ,, '_,  ,,,' ``
                                 |    /@  ,,, ;" `
                                /    .   ,''/' `,``
                               /   .     ./, `,, ` ;
                            ,./  .   ,-,',` ,,/''\\,'
                           |   /; ./,,'`,,'' |   |
                           |     /   ','    /    |
                            \\___/'   '     |     |
                              `,,'  |      /     `\\
                                   /      |        ~\\
                                  '       (
                                 :
                                ; .         \\--
                              :   \\         ;

  ____  _   _ ____     ____  ____    _  _____ ___  _        _      ____   ___  ____ ____     _    
 |  _ \\| \\ | |  _ \\   / ___|/ ___|  / \\|_   _/ _ \\| |      / \\    |  _ \\ / _ \\/ ___/ ___|   / \\   
 | | | |  \\| | | | |  \\___ \\| |     / _ \\ | || | | | |     / _ \\   | |_) | | | \\___ \\___ \\  / _ \\  
 | |_| | |\\  | |_| |   ___) | |___ / ___ \\| || |_| | |___ / ___ \\  |  _ <| |_| |___) |__) |/ ___ \\ 
 |____/|_| \\_|____/   |____/ \\____/_/   \\_\\_| \\___/|_____/_/   \\_\\ |_| \\_\\\\___/|____/____//_/   \\_\\
{RESET}
{GIALLO}   Edizione Mentzer / BECMI Set Base (1983) - Terminale AI DM [v9.1 SQLite | Party & LAN]{RESET}
"""

HELP_TESTO = f"""{CIANO}{GRASSETTO}=== GUIDA AI COMANDI - D&D SCATOLA ROSSA (v9.1 SQLite / Party / LAN) ==={RESET}

{GIALLO}Azioni di Gruppo e Turni Multi-Giocatore:{RESET}
  {VERDE}/gruppo <azione>{RESET}         Invia un'azione collettiva per tutto il party in un colpo solo.
  {VERDE}/salta{RESET}                   Salta l'azione individuale di un personaggio (resta in guardia).
  {VERDE}/party{RESET}                   Mostra lo stato sintetico di tutti i membri del gruppo.

{GIALLO}Personaggio, Emporio e Diario:{RESET}
  {VERDE}/scheda{RESET} (o /inventario)  Mostra caratteristiche, TS, livello ed equipaggiamento (scegli PG se in gruppo).
  {VERDE}/emporio{RESET} (o /negozio)    Acquista armi, armature, torce, pozioni e gregari con le MO.
  {VERDE}/livello{RESET} (o /levelup)    Verifica passaggio di livello BECMI, soglia PE o Ascensione Immortale.
  {VERDE}/aggiorna{RESET}                Aggiorna manualmente livello, PF max, CA, MO o aggiungi oggetti.
  {VERDE}/nota <testo>{RESET}            Salva un appunto nel diario SQLite (/nota per leggere).

{GIALLO}Dadi e Strumenti di Esplorazione:{RESET}
  {VERDE}/d20{RESET} (o /d8+1, /2d6)     Tira dadi reali dal tuo PC e invia il risultato al Dungeon Master.
  {VERDE}/autodadi{RESET}                Attiva/disattiva la batteria completa di dadi reali ad ogni turno.
  {VERDE}/mappa{RESET}                   Genera una mappa ASCII delle stanze e dei corridoi esplorati.
  {VERDE}/suoni{RESET}                   Attiva/disattiva gli effetti sonori retro del terminale.

{GIALLO}Database SQLite, Navigazione e Uscita:{RESET}
  {VERDE}/sql{RESET} (o /db)             Mostra stato e statistiche del database SQLite ({DB_FILE}).
  {VERDE}/storico{RESET}                 Mostra gli ultimi 3 turni dell'avventura corrente.
  {VERDE}/riassunto{RESET}               Comprime la memoria per mantenere veloce l'IA nelle partite lunghe.
  {VERDE}/stop{RESET} (o /menu, /0)      Salva l'avventura e torna al Menu Principale.
  {VERDE}/chiudi{RESET} (o /esci)        Chiude il database ed esce completamente dal programma.
  {VERDE}/help{RESET} (o /aiuto)         Mostra questa schermata.
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


def suona(tipo):
    if not SUONI_ATTIVI:
        return
    ripetizioni = {"critico": 3, "danno": 2, "tesoro": 1}.get(tipo, 1)
    for _ in range(ripetizioni):
        sys.stdout.write("\a")
        sys.stdout.flush()
        time.sleep(0.12)


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

    pref = f"TIRI REALI {nome_pg}" if nome_pg else "TIRI REALI"
    riga_visibile = (
        f"[{pref} -> Attacco/Prova 1d20: {d20_pg} | TS 1d20: {d20_ts} | "
        f"Esplorazione/Cerca 1d6: {d6_espl} | Incontro 1d6: {d6_inc} | "
        f"Reazione/Morale 2d6: {tot_2d6} ({d6_a}+{d6_b}) | "
        f"Danni 1d8: {d8}, 1d6: {d6_a}, 1d4: {d4} | DM 1d20: {d20_dm} | d%: {d100}]"
    )
    return {
        "d20": d20_pg,
        "d20_ts": d20_ts,
        "d20_dm": d20_dm,
        "1d6": d6_espl,
        "1d6_inc": d6_inc,
        "2d6": tot_2d6,
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
        schede_txt.append(
            f"- EROE: {eroe['nome']} ({titolo_livello}, {eroe['allineamento']}) | "
            f"FOR {eroe['forza']} ({mod_caratteristica(eroe['forza']):+d}), "
            f"INT {eroe['intelligenza']} ({mod_caratteristica(eroe['intelligenza']):+d}), "
            f"SAG {eroe['saggezza']} ({mod_caratteristica(eroe['saggezza']):+d}), "
            f"DES {eroe['destrezza']} ({mod_caratteristica(eroe['destrezza']):+d}), "
            f"COS {eroe['costituzione']} ({mod_caratteristica(eroe['costituzione']):+d}), "
            f"CAR {eroe['carisma']} ({mod_caratteristica(eroe['carisma']):+d}) | "
            f"PF: {eroe['pf_attuali']}/{eroe['pf_max']}, CA: {eroe['ca']} | "
            f"{eroe['attacco']} | TS: {eroe['ts']} | {eroe['abilita_classe']} | "
            f"Equip: {equip_str} | MO: {eroe['mo']} | PE: {eroe['pe']}"
        )
        riquadri_esempio.append(
            f"[{eroe['nome']} | PF: attuali/{eroe['pf_max']} | CA: {eroe['ca']} | Torce: n | Razioni: n | Frecce: n | MO: n | PE: attuali]"
        )

    blocco_party = "\n".join(schede_txt)
    blocco_riquadri = "\n".join(riquadri_esempio)

    return (
        "Agisci come un Dungeon Master esperto di Dungeons & Dragons Edizione Mentzer / BECMI completa "
        "(Basic, Expert, Companion, Master, Immortal - Livelli 1-36 e Ranghi Immortali) in lingua italiana. "
        f"FASCIA DI REGOLAMENTO ATTIVA: {fascia_attiva}. "
        f"GRUPPO DI AVVENTURIERI ({len(eroi_party)} personaggi):\n{blocco_party}\n"
        "REGOLE OBBLIGATORIE E ASSOLUTE SUI TIRI DI DADO E SUL PARTY (NON DEROGABILI): "
        "1. REGOLA D'ORO DEI DADI: OGNI SINGOLA situazione, azione incerta, esplorazione, prova o pericolo DEVE mostrare esplicitamente "
        "il lancio dei dadi e il calcolo completo nel testo usando il formato [NomePG - Tipo Prova: Dado -> risultato +/- mod = Totale vs Soglia -> Esito]. "
        "2. Se il messaggio dei giocatori include [TIRI REALI ... -> ...], DEVI obbligatoriamente usare quei valori reali per le prove di ciascun personaggio, "
        "riportandoli comunque in chiaro tra parentesi quadre [...] nella tua narrazione! "
        "3. Risolvi le azioni di tutti i membri del party nel round (sia che agiscano individualmente sia come azione di gruppo). "
        "4. A 0 PF un personaggio muore. Procedi a Turni da 10 minuti nei dungeon (torce durano 6 turni). 1 MO recuperata = 1 PE (diviso equamente o assegnato a chi raccoglie). "
        "5. Chiudi SEMPRE ogni messaggio con una riga vuota, poi TUTTI i riquadri aggiornati del party (una riga per ogni personaggio) e infine la domanda:\n"
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
    badge_rete = f" | {MAGENTA}{ruolo_rete}{RESET}" if ruolo_rete else ""
    print(f"{ROSSO}{GRASSETTO}=== D&D BECMI [SQLite] ==={RESET} {GIALLO}{avventura['titolo']}{RESET} {DIM}| Turno {turno} | AI: {MODELLO}{RESET}{badge_rete}")
    print(f"{CIANO}Party:{RESET} {nomi_str}")
    print(f"{CIANO}Comandi:{RESET} /gruppo | /party | /scheda | /emporio | /mappa | /d20 | /sql | /autodadi ({stato_dadi}) | /stop (menu) | /chiudi")
    print(f"{DIM}" + "-" * 96 + f"{RESET}\n")


def chiama_gemini(storia, api_key, system_prompt, pdf_path=None):
    contents_invio = []
    for msg in storia:
        parts = msg.get("parts", [])
        if parts and parts[0].get("text", "").strip():
            contents_invio.append({"role": msg["role"], "parts": [{"text": parts[0]["text"]}]})

    if pdf_path and os.path.exists(pdf_path) and contents_invio:
        if os.path.getsize(pdf_path) <= 18 * 1024 * 1024:
            with open(pdf_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            contents_invio[0]["parts"].insert(0, {
                "inlineData": {
                    "mimeType": "application/pdf",
                    "data": b64
                }
            })

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents_invio,
        "generationConfig": {
            "maxOutputTokens": 4096,
            "temperature": 0.85
        }
    }
    payload_str = json.dumps(payload)

    ultimo_errore = "Nessun modello disponibile."
    for idx, mod in enumerate(MODELLI_FALLBACK):
        url_completo = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent"
        for tentativo in range(2):
            comando_curl = [
                "curl", "-s", "--max-time", "35", "-X", "POST",
                url_completo,
                "-H", "Content-Type: application/json",
                "-H", "x-goog-api-key: " + api_key.strip(),
                "-d", payload_str
            ]

            processo = subprocess.run(comando_curl, capture_output=True, text=True)
            risposta_grezza = processo.stdout.strip()

            if not risposta_grezza:
                ultimo_errore = f"Timeout o risposta vuota dal server ({mod})."
                time.sleep(1.2)
                continue

            try:
                risultato = json.loads(risposta_grezza)
            except Exception:
                ultimo_errore = f"Risposta non valida dal server ({mod})."
                break

            if "error" in risultato:
                err_msg = risultato["error"].get("message", str(risultato["error"]))
                err_code = risultato["error"].get("code", 0)
                ultimo_errore = err_msg
                # Se il modello è sovraccarico (503 / high demand) o rate-limited (429), riprova breve e poi passa al fallback
                if err_code in (429, 503) or "high demand" in err_msg.lower() or "overloaded" in err_msg.lower() or "quota" in err_msg.lower():
                    if tentativo == 0:
                        time.sleep(1.5)
                        continue
                    if idx < len(MODELLI_FALLBACK) - 1:
                        print(f"{DIM}Modello {mod} congestionato, passo automaticamente a {MODELLI_FALLBACK[idx + 1]}...{RESET}")
                    break
                else:
                    # Se un modello fallback non esiste più (404), passa al successivo
                    if err_code == 404 or "not found" in err_msg.lower():
                        break
                    raise Exception(err_msg)

            global MODELLO
            if mod != MODELLO:
                MODELLO = mod
                print(f"{CIANO}[Modello AI attivo: {MODELLO}]{RESET}")
            cand = risultato["candidates"][0]
            finish_reason = cand.get("finishReason", "")
            parts = cand.get("content", {}).get("parts", [])
            testo_completo = "".join(p.get("text", "") for p in parts if "text" in p)
            if finish_reason == "MAX_TOKENS":
                testo_completo += "\n\n[Nota: risposta troncata per limite token del modello]"
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
        if riga_pulita.startswith("[") and "PF:" in riga_pulita:
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

    if AUTODADI_ATTIVI:
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
        "modulo_testo": modulo_testo
    }
    db.salva_metadati_avventura(nuova_adv)
    db.aggiungi_messaggio(adv_id, "user", prompt)
    avventure[adv_id] = nuova_adv
    return nuova_adv


def menu_principale(db: DnDDatabase, avventure: dict, personaggi: dict):
    while True:
        os.system("clear" if os.name == "posix" else "cls")
        print(LOGO_INTRO)
        stats = db.statistiche_db()
        ip_lan = ottieni_ip_locale()
        print(f"{DIM}SQLite: {stats['file']} ({stats['size_kb']} KB | {stats['personaggi']} Eroi | {stats['avventure']} Avventure) | Modello: {MODELLO} | IP LAN: {ip_lan}{RESET}")
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
                print(f"  {VERDE}{GRASSETTO}[{idx}]{RESET} {titolo} — {CIANO}{party_str}{RESET} {DIM}({turni} turni | {data_adv}){RESET}")
            print()

        print(f"  {VERDE}{GRASSETTO}[N]{RESET} Nuova Avventura (1-6 giocatori locali / Party Multi-Eroe)")
        print(f"  {CIANO}{GRASSETTO}[C]{RESET} Crea solo un Nuovo Personaggio")
        print(f"  {MAGENTA}{GRASSETTO}[H]{RESET} Ospita Partita in LAN (Server TCP su {ip_lan}:{DEFAULT_LAN_PORT})")
        print(f"  {MAGENTA}{GRASSETTO}[J]{RESET} Unisciti a Partita in LAN (Client TCP verso Host)")
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
                time.sleep(1.1)
        elif scelta == "h":
            return None, "host_lan"
        elif scelta == "j":
            return None, "join_lan"
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
            suona("critico")
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
        suona("critico")
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
    risposta = chiama_gemini(richiesta, api_key, system_cartografo)
    risposta = re.sub(r"^```[a-zA-Z]*\n?", "", risposta.strip())
    risposta = re.sub(r"\n?```$", "", risposta.strip())
    return risposta


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
            suona("danno")
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
    riassunto = chiama_gemini(richiesta, api_key, system_prompt)
    nuova_storia = [
        {"role": "user", "parts": [{"text": "Riassunto dell'avventura finora: " + riassunto}]},
        {"role": "model", "parts": [{"text": "Ho memorizzato tutto il progresso del gruppo. Riprendiamo da dove eravamo rimasti.\n\nCosa fate?"}]}
    ]
    avventura["storia"] = nuova_storia
    db.sostituisci_storia_compressa(avventura["id"], nuova_storia)
    print(f"{VERDE}Memoria compressa e aggiornata nel database!{RESET}\n")
    print(riassunto)


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
                suona("danno")
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
                suona("danno")
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
    print(f"{GIALLO}Fai collegare gli altri giocatori con: python3 dnd-v9_1.py --join {ip_lan}{RESET}")
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
        testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroi_party, avventura))
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

            avventura["storia"].append({"role": "user", "parts": [{"text": testo_inviato}]})
            db.aggiungi_messaggio(avventura["id"], "user", testo_inviato)

            print(f"{DIM}Il Dungeon Master ({MODELLO}) sta risolvendo il round LAN...{RESET}")
            testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroi_party, avventura))
            avventura["storia"].append({"role": "model", "parts": [{"text": testo_dm}]})
            db.aggiungi_messaggio(avventura["id"], "model", testo_dm)
            aggiorna_party_da_riquadro(eroi_party, testo_dm)
            for e in eroi_party:
                db.salva_personaggio(e)
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
    global SUONI_ATTIVI, AUTODADI_ATTIVI
    party_nomi = avventura.get("party") or [avventura.get("eroe", "Valen di Corvobianco")]
    eroi_party = []
    for nome_e in party_nomi:
        if nome_e not in personaggi:
            _, nuovo_p = normalizza_personaggio_json(nome_e, {})
            db.salva_personaggio(nuovo_p)
            personaggi.update(db.carica_tutti_personaggi())
        eroi_party.append(personaggi[nome_e])

    pulisci_schermo(avventura, eroi_party)

    if len(avventura["storia"]) <= 1:
        if not avventura["storia"]:
            prompt_init = f"Gruppo di avventurieri: {', '.join(party_nomi)}. {SCENARI_AVVENTURA['1'][1]}"
            if AUTODADI_ATTIVI:
                prompt_init += "\n" + "\n".join(genera_batteria_dadi(n)["testo"] for n in party_nomi)
            avventura["storia"] = [{"role": "user", "parts": [{"text": prompt_init}]}]
            db.aggiungi_messaggio(avventura["id"], "user", prompt_init)
        print(f"{DIM}Generazione della scena iniziale ({MODELLO}) e lancio dei dadi...{RESET}")
        try:
            pdf_attivo = avventura.get('modulo_pdf') if not avventura.get('modulo_testo') else None
            testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroi_party, avventura), pdf_path=pdf_attivo)
            avventura["storia"].append({"role": "model", "parts": [{"text": testo_dm}]})
            avventura["data"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            db.aggiungi_messaggio(avventura["id"], "model", testo_dm)
            aggiorna_party_da_riquadro(eroi_party, testo_dm)
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

        if cmd in ["/help", "/aiuto", "/?"]:
            pulisci_schermo(avventura, eroi_party)
            print(HELP_TESTO)
            print(f"{DIM}--- Situazione attuale ---{RESET}\n")
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

        if cmd in ["/scheda", "/inventario"]:
            eroe_sel = scegli_membro_party(eroi_party, "visualizzare la scheda")
            if eroe_sel:
                pulisci_schermo(avventura, eroi_party)
                mostra_scheda(eroe_sel)
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

        if cmd == "/mappa":
            try:
                mappa = genera_mappa_ascii(avventura, api_key, eroi_party)
                pulisci_schermo(avventura, eroi_party)
                print(f"{CIANO}{GRASSETTO}=== MAPPA DELL'ESPLORAZIONE ==={RESET}\n\n{mappa}")
                print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
                mostra_ultimo_turno_con_dadi(avventura)
            except Exception as e:
                print(f"{ROSSO}Impossibile generare la mappa:{RESET}", e)
            continue

        if cmd == "/suoni":
            SUONI_ATTIVI = not SUONI_ATTIVI
            print(f"{GIALLO}Effetti sonori {'ATTIVATI' if SUONI_ATTIVI else 'DISATTIVATI'}.{RESET}")
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

        if cmd.startswith("/") and re.match(r"^/\d*d\d+", cmd):
            tiro = tira_dado(azione)
            if tiro:
                azione_effettiva = f"Ho tirato fisicamente il dado: {tiro}. Usa questo risultato e mostra il calcolo tra parentesi quadre."
                testo_mostrato, testo_inviato = raccogli_azioni_party_locale(eroi_party, azione_effettiva)
            else:
                print("Formato dado non valido. Esempi: /d20, /d8+1, /2d6")
                continue
        else:
            testo_mostrato, testo_inviato = raccogli_azioni_party_locale(eroi_party, azione)

        avventura["storia"].append({"role": "user", "parts": [{"text": testo_inviato}]})
        db.aggiungi_messaggio(avventura["id"], "user", testo_inviato)

        print(f"\n{testo_mostrato}")
        print(f"{DIM}Il Dungeon Master ({MODELLO}) sta risolvendo i tiri e valutando la scena...{RESET}")
        try:
            pdf_attivo = avventura.get('modulo_pdf') if not avventura.get('modulo_testo') else None
            testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroi_party, avventura), pdf_path=pdf_attivo)
            avventura["storia"].append({"role": "model", "parts": [{"text": testo_dm}]})
            avventura["data"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            db.aggiungi_messaggio(avventura["id"], "model", testo_dm)
            aggiorna_party_da_riquadro(eroi_party, testo_dm)
            for e in eroi_party:
                db.salva_personaggio(e)
            pulisci_schermo(avventura, eroi_party)
            print(f"{DIM}{testo_mostrato}{RESET}\n")
            formatta_risposta(testo_dm, animato=True)
        except Exception as e:
            print(f"{ROSSO}Errore:{RESET}\n", e)
            avventura["storia"].pop()
            db.rimuovi_ultimo_messaggio(avventura["id"])


def main():
    if "--join" in sys.argv:
        idx = sys.argv.index("--join")
        ip_target = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ""
        avvia_client_lan(ip_target)
        return

    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        api_key = sys.argv[1]
    else:
        api_key = os.environ.get("GEMINI_API_KEY", "")

    db = DnDDatabase(DB_FILE)
    try:
        avventure, personaggi = migra_json_in_sqlite(db)

        while True:
            avventura_scelta, modo = menu_principale(db, avventure, personaggi)
            if modo == "exit":
                print(f"\n{GIALLO}Arrivederci, avventuriero! Tutti i progressi sono salvati in {DB_FILE}.{RESET}")
                break
            elif modo == "host_lan":
                if not api_key:
                    print(f"{ROSSO}Per ospitare una partita LAN serve la chiave API Gemini!{RESET}")
                    time.sleep(1.5)
                    continue
                avvia_host_lan(db, avventure, personaggi, api_key)
                avventure = db.carica_tutte_avventure()
                personaggi = db.carica_tutti_personaggi()
            elif modo == "join_lan":
                avvia_client_lan()
            elif avventura_scelta:
                if not api_key:
                    print(f"{ROSSO}Chiave API Gemini mancante! Avvia con: python3 dnd-v9_1.py LA_TUA_CHIAVE_API{RESET}")
                    break
                esito = esegui_sessione(db, avventura_scelta, personaggi, api_key)
                if esito == "chiudi":
                    break
    finally:
        db.chiudi()


if __name__ == "__main__":
    main()
