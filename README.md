# 🐉 D&D Scatola Rossa (BECMI) - AI Dungeon Master per Terminale

Un gioco di ruolo testuale completo per terminale basato sulle regole storiche di **Dungeons & Dragons Edizione BECMI (Scatola Rossa, Frank Mentzer 1983)**, animato dall'intelligenza artificiale **Google Gemini** come Dungeon Master interattivo.

Il progetto è sviluppato in **Python 3 puro** utilizzando esclusivamente la **Standard Library** (nessun `pip install` o libreria esterna richiesta).

---

## ✨ Caratteristiche Principali

* **🎲 Modalità Interattiva con Chiamata Dadi Reali**: Il DM AI narra le scene e, nelle situazioni di incertezza, emette una chiamata esplicita (`[CHIAMATA DADO: NomePG - Tira 1d20...]`) e si ferma attendendo il tiro fisico dei dadi o il comando del giocatore prima di proseguire.
* **📜 Motore Regole BECMI Fedele**:
  * 7 classi storiche: Guerriero, Chierico, Mago, Ladro, Nano, Elfo, Halfling.
  * Tabella progressione fino al 36° livello (Basic, Expert, Companion, Master, Immortal).
  * Calcolo THAC0, matrice tiri per colpire, 5 Tiri Salvezza BECMI distinti per classe e livello.
  * Tiri reazione mostri 2d6 e tiri morale 2d6.
* **🕯️ Gestione Torce, Illuminazione & Buio Totale**:
  * Tempo a turni di 10 minuti (con orologio Hh MMm).
  * Riconoscimento automatico di ambienti illuminati (locande, città, luce del giorno) per non sprecare torce.
  * Countdown torce nei dungeon e penalità BECMI in caso di buio totale.
* **🧙‍♂️ Sistema Magia & Grimorio Ufficiale**:
  * 36 incantesimi per cerchi 1-3 (Arcani e Divini).
  * Slot giornalieri calcolati dinamicamente, preparazione, memorizzazione e lancio con `/lancia`.
* **🎒 Gestione Inventario & Zaino**:
  * Visualizzazione suddivisa per Armi/Munizioni, Armature/CA, Zaino/Attrezzatura e Borsello monete d'oro con `/inventario`.
* **📄 Esportazioni Vettoriali PDF A4 Native (senza librerie terze)**:
  * **Schede Personaggio Ufficiali A4 PDF** stile Scatola Rossa (`/scheda pdf`, Menu `[P]`).
  * **Mappe Tattiche A4 PDF** con griglia blueprint da 10 piedi, stanze, porte segrete, pericoli, token party e dossier descrittivo (`/mappa pdf`).
  * **Manuale Comandi PDF A4** a 2 pagine con auto-sincronizzazione crittografica delle modifiche (`manuale_comandi_dnd.pdf`, `/help pdf`).
* **🎵 Motore Audio Chiptune Retro 8-bit**:
  * Effetti sonori procedurali (dado, colpo critico, fallimento, danno, tesoro, level-up, incantesimo).
  * Riproduzione tramite `paplay`, `pw-play`, `aplay` o beep di riserva.
* **🌐 Multiplayer LAN**:
  * Supporto per party cooperativo e architettura TCP Client/Server per giocare in rete locale.
* **💾 Persistenza SQLite**:
  * Database locale `dnd_becmi.db` con salvataggi automatici a ogni turno e gestione multi-avventura.

---

## 🚀 Requisiti e Installazione

### Requisiti
- **Linux / macOS / WSL** (compatibile con qualsiasi terminale ANSI a 256 colori).
- **Python 3.10+**.
- **`curl`** installato nel sistema (utilizzato per le chiamate REST a Google Gemini API).
- Una **Chiave API Google Gemini** (gratuita) ottenibile su [Google AI Studio](https://aistudio.google.com/app/apikey).

### Installazione
Non è necessaria alcuna installazione con `pip`! Clona semplicemente il repository:

```bash
git clone https://github.com/nghtcp/Dnd_ScatolaRossa.git
cd Dnd_ScatolaRossa
```

---

## 🎮 Avvio del Gioco

Il repository include lo script principale pronto all'uso:

```bash
python3 dnd-fork.py
```

### Gestione della Chiave API Gemini
Al primo avvio, il programma ti chiederà di inserire la tua chiave API Gemini:
1. **Salvataggio locale facoltativo**: Puoi scegliere di salvarla in `.gemini_api_key` (con permessi protetti `0600`) per non doverla reinserire ai successivi avvii.
2. **Linea di comando**: Puoi passare la chiave direttamente come argomento:
   ```bash
   python3 dnd-fork.py LA_TUA_CHIAVE_API
   ```
3. **Variabile d'ambiente**: Oppure impostare la variabile:
   ```bash
   export GEMINI_API_KEY="LA_TUA_CHIAVE_API"
   python3 dnd-fork.py
   ```
4. **Gestione in-game**: Dal Menu Principale, premi `[K]` per visualizzare la chiave mascherata, cambiarla o eliminare il file salvato.

---

## ⌨️ Comandi di Gioco Rapidi

Durante la partita puoi digitare comandi naturali per il DM oppure utilizzare i comandi rapidi:

| Comando | Descrizione |
|---|---|
| `/help` / `/aiuto` | Mostra la guida comandi e le azioni disponibili |
| `/help pdf` | Genera o apre la guida comandi in PDF A4 (`manuale_comandi_dnd.pdf`) |
| `/inventario` | Mostra equipaggiamento, armi, armatura e monete d'oro |
| `/torcia [on\|off]` | Accende o ripone la torcia nello zaino |
| `/magia` | Mostra il grimorio, gli incantesimi memorizzati e gli slot |
| `/lancia <nome>` | Lancia un incantesimo consumando lo slot |
| `/riposo` | Effettua un riposo breve (10m) o lungo (8h, recupera PF e slot) |
| `/scheda pdf` | Esporta la scheda del personaggio in PDF vettoriale A4 |
| `/mappa pdf` | Esporta la mappa tattica e il dossier del dungeon in PDF A4 |
| `/modalita` | Alterna tra Modalità Interattiva (chiamata dadi) e Classica |
| `/incontri` | Regola la frequenza dei mostri erranti (raro, normale, frequente, off) |
| `/suoni` | Attiva o disattiva gli effetti sonori retro 8-bit |
| `/esporta` | Salva la cronaca completa dell'avventura in Markdown |

---

## 📁 Struttura del Repository

```text
├── dnd-fork.py            # Entry point principale con gestione sicura delle credenziali
├── db_manager.py          # Modulo per la gestione del database SQLite
├── manuale_comandi_dnd.pdf# Manuale comandi ufficiale pronto per la stampa
├── avventure_dnd.json     # Dati iniziali delle avventure predefinite
├── personaggi_dnd.json    # Dati iniziali degli eroi pregenerati
├── suoni/                 # Effetti sonori chiptune a 8-bit (.wav)
├── cronache/              # Cartella di output per le cronache esportate (.md)
├── mappe/                 # Cartella di output per le mappe A4 in PDF
├── schede/                # Cartella di output per le schede PG A4 in PDF
├── PROJECT_CONTEXT.md     # Documentazione architetturale dettagliata
└── README.md              # Questo file
```

---

## ⚖️ Licenza e Disclaimer

Questo software è un progetto non ufficiale creato per uso personale e hobbistico a tributo del classico *Dungeons & Dragons Basic Set (Scatola Rossa)* ideato da Gary Gygax e curato da Frank Mentzer (TSR, 1983). Tutti i marchi registrati appartengono ai rispettivi proprietari.
