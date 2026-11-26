# 🐉 D&D Scatola Rossa (BECMI) - AI Dungeon Master per Terminale

Un gioco di ruolo testuale completo per terminale basato sulle regole storiche di **Dungeons & Dragons Edizione BECMI (Scatola Rossa, Frank Mentzer 1983)**, animato dall'intelligenza artificiale **Google Gemini** come Dungeon Master interattivo.

Il motore di gioco usa la **Standard Library**; le richieste a Gemini usano l'SDK ufficiale Google `google-genai`.

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
- **SDK ufficiale Google Gemini** (`google-genai`, installato da `requirements.txt`).
- Una **Chiave API Google Gemini** (gratuita) ottenibile su [Google AI Studio](https://aistudio.google.com/app/apikey).

### Installazione
Clona il repository e installa la dipendenza Gemini:

```bash
git clone https://github.com/nghtcp/Dnd_ScatolaRossa.git
cd Dnd_ScatolaRossa
python -m pip install -r requirements.txt
```

Se la rete richiede un proxy, impostare `HTTP_PROXY` e `HTTPS_PROXY` nell'ambiente prima di installare le dipendenze e avviare il gioco; `pip` e l'SDK Gemini useranno queste variabili.

---

## 🎮 Avvio del Gioco

### Interfaccia web

Per usare il nuovo menu web locale:

```bash
python dnd_web.py
```

Il server apre `http://127.0.0.1:8765`; accedi con l'account amministratore oppure con un account creato dall'amministratore. L'amministratore usa `WEB_USERNAME` e `DnD_USER_PASSWORD`; nel pannello Amministrazione può gestire gli account e aggiornare la chiave Gemini. Con `DB_LOCATION=local` gli account giocatore sono conservati in `utenti_web.json`; con una connection string PostgreSQL sono conservati nel DB remoto. Le password sono protette con hash e salt, mai in chiaro. In locale, se le variabili admin mancano, vengono richieste nel terminale. È possibile passare la chiave API come argomento:

```bash
python dnd_web.py LA_TUA_CHIAVE_API
```

L'interfaccia web sostituisce il menu e gli input della console per le operazioni principali:

- login e sessione persistente nel browser; gli account sono creati dall'amministratore;
- gestione amministrativa degli account (JSON locale o tabella PostgreSQL remota) e della chiave Gemini;
- creazione di personaggi associati al proprio account;
- creazione di avventure e join alle sessioni esistenti usando un proprio personaggio;
- selezione ed eliminazione delle avventure create dal proprio account;
- sidebar con riepilogo partita, richiudibile su schermi mobili;
- pulsante zaino per consultare l'inventario dei membri del party e helper dei comandi web;
- scelta dei moduli in `moduli_pdf/`;
- invio delle azioni al DM;
- consultazione del party e della cronaca.

I comandi `/...` possono essere inviati dalla casella azione della pagina. In modalità locale il file utenti viene inizializzato con `{"users": []}` e aggiornato dal pannello; in modalità PostgreSQL i dati account sono memorizzati nella tabella `web_users`. In entrambi i casi sono conservati salt e hash scrypt, mai password in chiaro. Crea o reimposta le password dal pannello amministrativo.

### Pubblicazione su Render

Il repository include `render.yaml` per creare un Web Service Render con disco persistente (piano Starter a pagamento). Puoi usarlo come Blueprint oppure impostare manualmente:

- **Build Command:** `python -m compileall -q dnd_web.py dnd_fork.py web_auth.py db_backend.py`
- **Start Command:** `python dnd_web.py`
- **Health Check Path:** `/health`
- **Environment:** `DB_LOCATION`, `WEB_USERNAME`, `DnD_USER_PASSWORD`, `GEMINI_API_KEY`
- In modalità locale: disco persistente da almeno 1 GB montato su `/var/data` e `DND_DATA_DIR=/var/data`

Il servizio usa `PORT` fornita da Render e ascolta su `0.0.0.0`. `WEB_USERNAME` identifica l'amministratore e Render genera `DnD_USER_PASSWORD`. L'amministratore crea gli account giocatore dalla pagina Amministrazione; le sessioni attive sono condivise tra account e la cronaca viene aggiornata automaticamente nel browser.

**Database e persistenza:** `DB_LOCATION` non distingue maiuscole/minuscole per il valore `local`. In questo caso viene usato SQLite `dnd_becmi.db` e su Render occorre il disco persistente montato su `/var/data` (`DND_DATA_DIR=/var/data`); account e chiave Gemini restano nei file `utenti_web.json` e `.gemini_api_key` sul disco. Se `DB_LOCATION` contiene una connection string `postgres://` o `postgresql://`, l'app usa PostgreSQL remoto per personaggi, avventure, messaggi, account, sessioni e associazioni; il file `utenti_web.json`, se presente al primo avvio e la tabella `web_users` è vuota, viene importato una volta. Per Neon copia la connection string PostgreSQL **pooled** dalla dashboard e impostala in Render come variabile segreta `DB_LOCATION` (in genere inizia con `postgresql://` e include `sslmode=require`); non inserirla nel repository. In modalità remota non è necessario un disco per i dati DB; la chiave salvata dal pannello resta invece locale, quindi usa `GEMINI_API_KEY` oppure conserva `.gemini_api_key` su un disco persistente. Le connessioni PostgreSQL sono gestite da `psycopg`. Passare da SQLite a PostgreSQL non trasferisce automaticamente personaggi, avventure o cronache già salvati nel DB SQLite: esportali/migrali prima del cambio. Il Blueprint è configurato per modalità locale con disco persistente e piano Starter; per usare Neon su Render Free, imposta `DB_LOCATION` nella dashboard, seleziona il piano Free e rimuovi dal servizio sia il disco sia la variabile `DND_DATA_DIR` (il filesystem gratuito resta effimero).

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
├── dnd-fork.py            # Entry point principale CLI
├── dnd_web.py             # Entry point del sito web multiplayer
├── db_backend.py          # Backend SQLite locale / PostgreSQL remoto
├── web_auth.py            # Autenticazione, account e appartenenze
├── utenti_web.json        # Account locali (generato dall'admin, ignorato da Git)
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
