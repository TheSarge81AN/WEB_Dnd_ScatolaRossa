# Contesto progetto: D&D Scatola Rossa

## Scopo

Applicazione Python da terminale che usa Google Gemini come Dungeon Master per campagne basate sulle regole storiche D&D BECMI. Il repository contiene un gioco CLI completo, persistenza locale SQLite, mappe e schede in PDF generati nativamente, effetti sonori, moduli PDF di avventura e partita LAN TCP.

La priorita operativa per modifiche future e mantenere la coerenza con il codice reale, distinguendo chiaramente il punto d'ingresso principale dalle copie storiche.

## Stato reale del repository

- Entry point principale documentato: `dnd-fork.py`.
- Alias locale identico: `dnd_fork.py` (stesso contenuto di `dnd-fork.py`).
- Versione monolitica precedente equivalente: `dnd.py` e `dnd-v9_1_5.py` (stesso contenuto).
- `dnd-fork.py` e la variante piu recente: aggiunge gestione chiave Gemini da file locale, variabile d'ambiente, argomento CLI e menu `[K]`.
- `dnd-v9_1_5.py`, `dnd.py`, `dnd-v9_1_4.py`, `dnd-v9_1_3.py`, `dnd-v9_1.py`, `dnd-v9_0.py` e `dnd_legacy_pre915.py` sono snapshot storici, non moduli da importare.
- `db_manager.py` e un modulo SQLite autonomo/demo separato dal motore persistente interno a `dnd-fork.py`. Non viene importato dagli entry point verificati.
- `requirements.txt` dichiara l'SDK ufficiale `google-genai`; il resto del motore usa la standard library Python.
- Tutti i file Python principali compilano con `python -m compileall`.
- Non sono presenti database SQLite nel repository allo stato iniziale: sono dati generati/runtime e ignorati da Git.

## Avvio

```bash
python dnd-fork.py
python dnd-fork.py LA_CHIAVE_GEMINI
python dnd-fork.py --join IP_HOST
```

## Interfaccia web

Il file `dnd_web.py` espone l'interfaccia su `http://127.0.0.1:8765` in locale e si adatta a `PORT`/`0.0.0.0` su Render.

```bash
python dnd_web.py
python dnd_web.py LA_CHIAVE_GEMINI
```

La pagina usa API HTTP JSON e riusa funzioni di `dnd-fork.py` per personaggi, avventure, Gemini, comandi e PDF. `DB_LOCATION=local` usa SQLite; una connection string `postgres://`/`postgresql://` usa PostgreSQL tramite `db_backend.py` e `psycopg`, compatibile con Neon. `web_auth.py` gestisce account, hash password, cookie di sessione, proprietà personaggi e appartenenza alle avventure. Funzionalita web:

- login con cookie HttpOnly, logout e provisioning account riservato all'amministratore;
- gestione account JSON locale oppure tabella PostgreSQL `web_users` remota, con hash/salt scrypt, reimpostazione password e revoca degli account;
- pagina amministrativa per chiave Gemini, gestione account e pulizia di tutte le avventure (comprese quelle iniziali o senza proprietario);
- personaggi associati all'account che li crea, eliminabili dall'interfaccia; l'eliminazione li rimuove dai party delle avventure ma è bloccata se il personaggio è l'ultimo membro di un'avventura;
- i personaggi morti sono persistiti e mostrati nel Cimitero degli Eroi con il titolo dell'avventura in cui sono caduti; non sono ammessi ad azioni di gioco, nuove avventure o join; risultati dei comandi slash esposti nel drawer condiviso con l'inventario;
- elenco delle avventure condivise e join con un personaggio proprio;
- azioni e risposte Gemini salvate nel database configurato e visualizzate dagli altri partecipanti tramite polling ogni 2,5 secondi;
- azioni concorrenti serializzate per singola avventura per preservare l'ordine del transcript;
- eliminazione consentita solo al creatore dell'avventura;
- selezione modulo PDF, inventario, comandi slash, cronaca e riepilogo party.

L'amministratore è identificato da `WEB_USERNAME` e `DnD_USER_PASSWORD`; su Render la password è generata dal Blueprint. Solo l'amministratore può creare, aggiornare ed eliminare account nella pagina admin. Gli account giocatore sono definiti in `utenti_web.json` con salt/hash scrypt in modalità locale, oppure nella tabella `web_users` del DB PostgreSQL remoto; mai password in chiaro. La stessa pagina aggiorna la chiave Gemini salvandola nel file protetto `.gemini_api_key`; una chiave salvata ha precedenza su `GEMINI_API_KEY`. Gli endpoint di gioco richiedono un account autenticato; `/health` resta pubblico e i cookie su Render sono marcati `Secure`.

`DB_LOCATION=local` (default, anche `LOCAL`) usa SQLite e conserva account in `utenti_web.json`; su Render richiede `DND_DATA_DIR` sul disco persistente `/var/data`. Se `DB_LOCATION` è una URI PostgreSQL (`postgres://` o `postgresql://`), personaggi, inventario, avventure, messaggi, note, account, sessioni e associazioni sono salvati in PostgreSQL (Neon supportato via `psycopg`). Un eventuale `utenti_web.json` viene importato all'avvio remoto solo se `web_users` è vuota; le operazioni account successive agiscono sul DB. Il file `.gemini_api_key` rimane locale: con un filesystem effimero usa la variabile `GEMINI_API_KEY` o un disco persistente. Il Blueprint Render predefinito usa SQLite su disco persistente da 1 GB e piano Starter; Neon consente di spostare i dati DB fuori dal filesystem, ma il piano Render Free resta effimero e può sospendere il servizio. La conversione del DB SQLite esistente a PostgreSQL non è automatica; pianificare una migrazione prima di cambiare backend.

Per il motore CLI la chiave viene risolta nell'ordine: argomento CLI, `GEMINI_API_KEY`, `.gemini_api_key`, richiesta interattiva. Per `dnd_web.py` l'argomento CLI ha precedenza; altrimenti `.gemini_api_key` salvata dal pannello admin precede `GEMINI_API_KEY`. Il file chiave usa permessi Unix `0600` dove supportato; `utenti_web.json` è ignorato da Git.

## Architettura

Il programma CLI e prevalentemente monolitico: configurazione, modelli dati, SQLite, chiamate REST, UI ANSI, audio, PDF, LAN e loop di gioco stanno nel singolo entry point. Il server web usa `db_backend.py` per selezionare SQLite locale o PostgreSQL remoto.

### Flusso principale

1. `main()` richiede/risolve la chiave API.
2. `DnDDatabase` apre `dnd_becmi.db`, abilita foreign key e WAL, crea o migra lo schema.
3. `migra_json_in_sqlite()` migra i dati legacy dal JSON alla prima esecuzione.
4. `menu_principale()` permette creazione/caricamento avventure, personaggi, LAN e utility.
5. `esegui_sessione()` gestisce turni, comandi slash, chiamate Gemini, dadi, torce, riposo, magia e salvataggi.
6. Ogni nuova avventura o personaggio viene conservato nel database; i file JSON restano sorgenti legacy/seme.

### Persistenza SQLite principale

Database: `dnd_becmi.db`

Tabelle principali definite in `DnDDatabase`:

- `personaggi`: statistiche BECMI, PF, CA, PE, allineamenti, incantesimi JSON e campi di stato.
- `inventario`: oggetti collegati al personaggio con eliminazione a cascata.
- `avventure`: titolo, eroe, party JSON, modulo PDF/testo e stato dungeon JSON.
- `messaggi_storia`: transcript ordinato della conversazione per avventura.
- `diario_note`: note di campagna.

Indici:

- `idx_msg_avventura`
- `idx_inv_pg`
- `idx_note_avv`

Migrazioni compatibili all'avvio:

- `party_json`
- `stato_dungeon_json`
- `incantesimi_json`
- `deceduto` nei personaggi; PF a zero o inferiori sono migrati come personaggi deceduti
- `avventura_morte` nei personaggi per registrare il titolo dell'avventura in cui sono caduti

Le colonne JSON sono stringhe serializzate SQLite, da trattare come payload Python dopo `json.loads()`.

### Dati legacy

- `avventure_dnd.json`: avventure pregenerate o salvate nello storico formato JSON.
- `personaggi_dnd.json`: personaggi pregenerati/storici.
- `salvataggio_dnd.json`: vecchio snapshot della storia di gioco.
- `diario_avventura.txt`: diario legacy.

Il database ha priorita una volta migrato. Evitare modifiche alla migrazione senza testare dati gia esistenti.

## Sistemi implementati

- Regole BECMI: 9 classi includendo le estensioni Druido e Paladino, livelli fino al 36°, fasce Basic/Expert/Companion/Master/Immortal, THAC0, attacchi, tiri salvezza e XP.
- Classe, slot, grimorio e memorizzazione incantesimi.
- Tempo di dungeon a turni da 10 minuti, torce, ambienti illuminati e buio totale.
- Il prompt Gemini include i conteggi correnti di torce, razioni e frecce; le scorte salvate sono autorevoli e non vanno ricalcolate dal modello.
- Riposo breve/lungo e recupero PF.
- Reazione 2d6 e morale mostri.
- Mostri erranti con frequenza configurabile e cooldown.
- Modalita interattiva con chiamata dadi reali; modalita classica con autodadi.
- Party locale e host/client LAN sulla porta `5555`.
- Audio 8-bit con sintesi `.wav` se mancanti.
- Interfaccia web HTML/CSS inclusa in `dnd_web.py` (server HTTP standard library, non Flask), con palette Scatola Rossa, Foresta, Arcano e Notte salvata in `localStorage`.
- Gemini tramite SDK ufficiale Python, con elenco di modelli fallback.
- PDF: schede personaggio, mappe tattiche/dossier e manuale comandi.
- Esportazione cronache Markdown.
- Controllo automatico hash/manuale PDF all'avvio.

## Struttura repository

```text
dnd-fork.py                 Entry point principale CLI
dnd_fork.py                 Alias esatto del punto d'ingresso CLI
dnd.py / dnd-v9_1_5.py      Copia storica della versione precedente
dnd_web.py                  Entry point dell'interfaccia web e deploy Render
db_backend.py               Adattatore SQLite locale / PostgreSQL remoto
web_auth.py                 Account JSON/DB, sessioni e partecipazione web
utenti_web.json              Account giocatori runtime locale (ignorato da Git)
db_manager.py               Database demo indipendente non usato dal gioco
avventure_dnd.json          Seed/migrazione avventure legacy
personaggi_dnd.json         Seed/migrazione personaggi legacy
salvataggio_dnd.json        Snapshot legacy
manuale_comandi_dnd.pdf     Manuale generato
moduli_pdf/                 Moduli PDF importabili
cronache/                   Cronache Markdown generate
mappe/                      Mappe A4 PDF generate
schede/                     Schede A4 PDF generate
suoni/                      Effetti WAV
PROJECT_CONTEXT.md          Questo documento
README.md                   Installazione e guida utente
.gitignore                  Credenziali, DB e output ignorati
```

## File principali da modificare

Per nuove funzionalita di gioco modificare prima `dnd-fork.py`. Aggiornare `dnd-fork.py` e `dnd_fork.py` solo se si vuole mantenere l'alias identico: al momento sono copie byte-identiche.

Non propagare modifiche agli snapshot `dnd-v9_*.py` salvo una migrazione/versioning esplicitamente richiesta.

`db_manager.py` descrive uno schema diverso da quello del gioco principale. Non presumere che metodi o tabelle siano condivisi.

## Integrazione Gemini

- Richieste inviate con `google-genai` tramite `client.models.generate_content()`.
- La chiave viene passata dal chiamante al client SDK; non viene stampata nei log.
- Sono mantenuti cronologia, istruzioni di sistema, configurazione di generazione e PDF inline.
- L'SDK usa le variabili standard `HTTP_PROXY`/`HTTPS_PROXY` se presenti nell'ambiente.
- Il prompt di sistema e costruito da `costruisci_system_prompt()`.
- La storia usa il formato Gemini `role/user|model` con blocchi `parts[].text`.
- Sono presenti normalizzazioni di fallback dei contenuti restituiti e fallback tra modelli.
- La finestra/cronologia puo essere compressa per evitare prompt troppo grandi.
- Timeout, retry API e fallback modelli sono configurati in `chiama_gemini()`.
- Le chiamate non devono mai essere effettuate con una chiave segreta in log, screenshot o output.

## Comandi e convenzioni

- Comandi utente in-game: prefisso `/` (`/help`, `/inventario`, `/torcia`, `/magia`, `/lancia`, `/riposo`, `/scheda`, `/mappa`, `/modalita`, `/incontri`, `/suoni`, `/esporta`).
- Lingua interna dei testi: italiano.
- Output terminale: codici ANSI; usare le costanti `VERDE`, `GIALLO`, `CIANO`, `ROSSO`, `MAGENTA`, `GRASSETTO`, `DIM`, `RESET`.
- I dati personaggio restano dizionari Python serializzati in SQLite/JSON.
- Stati temporali di avventura vanno preferibilmente in `stato_dungeon_json`, incantesimi in `incantesimi_json`.
- PDF generati sono vettoriali e basati su `zlib`, stream PDF e font/posizionamenti nativi del programma.

## Audio

Cartella `suoni/`. Il motore prova prima player disponibili (`paplay`, `pw-play`, `aplay`) e crea WAV sintetici quando i file mancano. Su Windows le chiamate Linux possono non essere disponibili: il fallback deve restare non bloccante e l'esperienza in terminale Windows non deve dipendere dall'audio.

## LAN

- Host: server TCP locale, porta default `5555`.
- Client: avviabile con menu o `python dnd-fork.py --join IP`.
- Il protocollo scambia dizionari Python serializzati come pacchetti JSON.
- Operazioni LAN devono preservare il database dell'host come fonte autorevole.

## Requisiti pratici

- Python 3.10 o superiore suggerito.
- `google-genai>=1.75.0,<2.0.0` installato da `requirements.txt` (compatibile con Python 3.10+).
- Terminale con supporto ANSI consigliato.
- `curl` non è richiesto per le chiamate Gemini.
- Su Windows usare Python nel terminale con percorsi in backslash ed evitare dipendenze Unix non guardate.

## Validazione attuale

Verifica minima:

```bash
python -m compileall dnd-fork.py dnd_fork.py dnd.py dnd-v9_1_5.py db_manager.py dnd_web.py web_auth.py db_backend.py
```

Non esiste uno script ufficiale di test. Per una modifica mirata, creare o usare uno snippet diretto che eserciti la funzione modificata senza avviare Gemini o una partita interattiva. I test devono coprire: migrazioni SQLite, salvataggi JSON, calcoli BECMI, parsing comandi/dadi, generazione PDF e timeout/fallback API.

## Precauzioni per agenti

- Partire da `dnd-fork.py`, non dagli snapshot storici.
- Usare `apply_patch`/patch chirurgici nel file principale.
- Mantenere compatibile SQLite e i dati JSON gia presenti.
- Non registrare o committare `.gemini_api_key`, `dnd_becmi.db`, export, PDF runtime o WAL.
- Verificare sempre sintassi prima e dopo modifiche.
- Usare l'SDK Google dichiarato in `requirements.txt` per le chiamate Gemini; evitare altre dipendenze non necessarie.
- Quando si aggiunge un comando slash, aggiornare: parser/comando in-game, `HELP_TESTO`, hash/manuale PDF e README se la feature e visibile all'utente.
- Quando si modifica la persistenza, aggiungere migrazione compatibile in `_crea_schema()` e verificare righe gia esistenti.
