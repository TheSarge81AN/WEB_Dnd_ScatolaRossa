import sqlite3
from pathlib import Path
from typing import Optional

class DnDDatabase:
    def __init__(self, db_path: str = "campagna_scatola_rossa.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        # Permette di accedere alle colonne per nome (es. riga["nome"]) invece che solo per indice
        self.conn.row_factory = sqlite3.Row
        # Abilita il controllo sull'integrità delle chiavi esterne
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._inizializza_tabelle()

    def _inizializza_tabelle(self):
        """Crea le tabelle se non esistono ancora."""
        with self.conn:
            # 1. Schede Personaggio (regole Scatola Rossa: 6 caratteristiche, CA discendente, PF, XP)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS personaggi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    classe TEXT NOT NULL,
                    livello INTEGER DEFAULT 1,
                    forza INTEGER NOT NULL,
                    intelligenza INTEGER NOT NULL,
                    saggezza INTEGER NOT NULL,
                    destrezza INTEGER NOT NULL,
                    costituzione INTEGER NOT NULL,
                    carisma INTEGER NOT NULL,
                    pf_attuali INTEGER NOT NULL,
                    pf_massimi INTEGER NOT NULL,
                    classe_armatura INTEGER DEFAULT 9,
                    monete_oro INTEGER DEFAULT 0,
                    punti_esperienza INTEGER DEFAULT 0,
                    stanza_corrente TEXT DEFAULT 'Ingresso'
                );
            """)

            # 2. Inventario collegato al personaggio (se elimini il PG, sparisce anche il suo zaino)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS inventario (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    personaggio_id INTEGER NOT NULL,
                    oggetto TEXT NOT NULL,
                    quantita INTEGER DEFAULT 1,
                    equipaggiato INTEGER DEFAULT 0, -- 0 = nello zaino, 1 = equipaggiato
                    note TEXT,
                    FOREIGN KEY (personaggio_id) REFERENCES personaggi(id) ON DELETE CASCADE
                );
            """)

            # 3. Bestiario / Compendio Mostri
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS mostri (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    dadi_vita TEXT NOT NULL,       -- es. "1", "1+1", "3*"
                    classe_armatura INTEGER NOT NULL,
                    movimento TEXT,                -- es. "36m (12m)"
                    attacchi TEXT,                 -- es. "1 arma o 1 morso"
                    danni TEXT,                    -- es. "1d6"
                    tiro_salvezza TEXT,            -- es. "G1"
                    morale INTEGER DEFAULT 7,
                    allineamento TEXT DEFAULT 'Caotico',
                    xp INTEGER DEFAULT 10
                );
            """)

            # 4. Log eventi / Diario di campagna
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS log_avventura (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    personaggio_id INTEGER,
                    tipo_evento TEXT,              -- es. "COMBATTIMENTO", "TIRO_DADO", "ESPLORAZIONE"
                    descrizione TEXT NOT NULL,
                    FOREIGN KEY (personaggio_id) REFERENCES personaggi(id) ON DELETE SET NULL
                );
            """)

    # --- METODI PERSONAGGI ---
    def crea_personaggio(self, dati: dict) -> int:
        sql = """
            INSERT INTO personaggi (
                nome, classe, livello, forza, intelligenza, saggezza,
                destrezza, costituzione, carisma, pf_attuali, pf_massimi,
                classe_armatura, monete_oro
            ) VALUES (
                :nome, :classe, :livello, :forza, :intelligenza, :saggezza,
                :destrezza, :costituzione, :carisma, :pf_attuali, :pf_massimi,
                :classe_armatura, :monete_oro
            )
        """
        with self.conn:
            cur = self.conn.execute(sql, dati)
            return cur.lastrowid

    def get_personaggio(self, nome: str) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM personaggi WHERE nome = ?", (nome,))
        riga = cur.fetchone()
        return dict(riga) if riga else None

    def aggiorna_pf(self, personaggio_id: int, nuovi_pf: int):
        with self.conn:
            self.conn.execute(
                "UPDATE personaggi SET pf_attuali = ? WHERE id = ?",
                (max(0, nuovi_pf), personaggio_id)
            )

    # --- METODI INVENTARIO ---
    def aggiungi_oggetto(self, personaggio_id: int, oggetto: str, quantita: int = 1, equipaggiato: bool = False, note: str = ""):
        # Se l'oggetto esiste già nello zaino (non equipaggiato), aumenta la quantità
        cur = self.conn.execute(
            "SELECT id, quantita FROM inventario WHERE personaggio_id = ? AND oggetto = ? AND equipaggiato = ?",
            (personaggio_id, oggetto, int(equipaggiato))
        )
        esistente = cur.fetchone()
        with self.conn:
            if esistente:
                self.conn.execute(
                    "UPDATE inventario SET quantita = ? WHERE id = ?",
                    (esistente["quantita"] + quantita, esistente["id"])
                )
            else:
                self.conn.execute(
                    "INSERT INTO inventario (personaggio_id, oggetto, quantita, equipaggiato, note) VALUES (?, ?, ?, ?, ?)",
                    (personaggio_id, oggetto, quantita, int(equipaggiato), note)
                )

    def get_inventario(self, personaggio_id: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT oggetto, quantita, equipaggiato, note FROM inventario WHERE personaggio_id = ? ORDER BY equipaggiato DESC, oggetto ASC",
            (personaggio_id,)
        )
        return [dict(r) for r in cur.fetchall()]

    # --- METODI BESTIARIO ---
    def aggiungi_mostro(self, dati: dict):
        sql = """
            INSERT OR IGNORE INTO mostri (
                nome, dadi_vita, classe_armatura, movimento, attacchi,
                danni, tiro_salvezza, morale, allineamento, xp
            ) VALUES (
                :nome, :dadi_vita, :classe_armatura, :movimento, :attacchi,
                :danni, :tiro_salvezza, :morale, :allineamento, :xp
            )
        """
        with self.conn:
            self.conn.execute(sql, dati)

    def cerca_mostri_per_ca(self, ca_massima: int) -> list[dict]:
        """Esempio di query filtrata: trova mostri con CA uguale o migliore (più bassa) di quella indicata."""
        cur = self.conn.execute("SELECT * FROM mostri WHERE classe_armatura <= ? ORDER BY classe_armatura ASC", (ca_massima,))
        return [dict(r) for r in cur.fetchall()]

    # --- METODI LOG ---
    def registra_evento(self, descrizione: str, tipo_evento: str = "GENERICO", personaggio_id: Optional[int] = None):
        with self.conn:
            self.conn.execute(
                "INSERT INTO log_avventura (personaggio_id, tipo_evento, descrizione) VALUES (?, ?, ?)",
                (personaggio_id, tipo_evento, descrizione)
            )

    def get_ultimi_eventi(self, limite: int = 10) -> list[dict]:
        cur = self.conn.execute("SELECT timestamp, tipo_evento, descrizione FROM log_avventura ORDER BY id DESC LIMIT ?", (limite,))
        return [dict(r) for r in cur.fetchall()]

    def chiudi(self):
        self.conn.close()