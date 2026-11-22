# Contesto Progetto: D&D BECMI Terminale AI (`dnd-v9_1_5.py`)

## Architettura attuale (`dnd-v9_1_5.py` v9.1.5)
- **Linguaggio & Ambiente:** Python 3 su Linux (Debian / MX Linux), interfaccia CLI colorata ANSI con standard library pura (`sqlite3`, `wave`, `struct`, `math`, `shutil`, `re`, `json`, `zlib`).
- **Backend AI:** Google Gemini via `curl` con timeout esteso (75s/90s), finestra contestuale intelligente (per prevenire ritardi e timeout su storie lunghe), modello primario `gemini-3.6-flash` e catena di fallback automatica (`gemini-3.5-flash`, `gemini-flash-lite-latest`, `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-3-flash-preview`, `gemini-3.8-flash`, `gemini-3.7-flash`).
- **Persistenza:** SQLite database relazionale ad alte prestazioni (`dnd_becmi.db`) con migrazione trasparente dai file legacy JSON (`avventure_dnd.json`, `personaggi_dnd.json`). Nuove colonne per stato dungeon (`stato_dungeon_json`) e memoria incantesimi (`incantesimi_json`).
- **Multiplayer LAN:** Supporto Party multi-giocatore e architettura Server TCP Host / Client per partite in rete locale (porta default 5555).
- **Sistema Audio Retro-Fantasy (`suoni/`):**
  - Motore audio asincrono non bloccante via `paplay`, `pw-play`, `aplay` (ALSA/PulseAudio/PipeWire) o beep di riserva.
  - Sintetizzatore chiptune 8-bit in Python puro (`wave`, `math`, `struct`) che genera automaticamente i file `.wav` mancanti.
  - Effetti sonori supportati: `dado.wav`, `critico.wav` (20 naturale), `fallimento.wav` (1 naturale), `danno.wav`, `tesoro.wav`, `levelup.wav`, `intro.wav`, `magia.wav`.
  - Comando `/suoni` (toggle) e `/suoni test` per provare tutti i suoni a video.
- **Indicatore Attivo del Modello AI:**
  - Badge e stato del modello visibili nella barra comandi, intestazione del turno e menu principale (`[M] Seleziona Modello`).
  - Animazione spinner durante l'attesa del DM con modello in evidenza (`🎲 Dungeon Master [AI: gemini-3.8-flash] sta valutando la scena...`).
- **Logo Intro Ufficiale Rinnovato:**
  - Drago Rosso alato maestoso in ASCII art con corna dorate, occhi smeraldo luminescenti, zanne e fiamme animate.
  - Tipografia stilizzata bicolore ad alta visibilità (*DND* in oro, *SCATOLA ROSSA* in rosso cremisi) perfettamente allineata per terminali 80-100 colonne.
  - Sottotitolo rievocativo dell'Edizione Frank Mentzer (1983) con badge delle funzionalità attive.

## Sistemi BECMI Implementati (v9.1.5)
1. **Sistema Magia, Grimorio & Slot (`/magia`, `/lancia`, `/memorizza`):**
   - Compendio ufficiale BECMI dei cerchi 1-3 sia per incantesimi Arcani (Mago, Elfo) sia Divini (Chierico, Druido, Paladino) con 36 incantesimi registrati.
   - Calcolo dinamico degli slot per livello di classe secondo le tabelle della Scatola Rossa / Blu.
   - Tracciamento slot usati e memorizzazione personalizzata.
   - Comando `/lancia <nome incantesimo>` con effetto sonoro dedicato `magia.wav` e deduzione automatica degli slot.
2. **Tempo del Dungeon, Illuminazione, Torce & Buio Totale (`/torcia`, `/ambiente`):**
   - Calcolo tempo a turni esplorativi di 10 minuti (con indicatore orario Hh MMm in testata).
   - **Illuminazione Ambientale Intelligente:** Riconosce automaticamente luoghi illuminati (taverne, locande, botteghe, città, villaggi, piazze, all'aperto di giorno con luce solare) sia dalla narrazione del DM che dalle azioni del giocatore. In questi ambienti le torce personali vanno in pausa, non consumano turni e non vengono mai consumate inutilmente dagli zaini.
   - **Gestione Naturale delle Torce:** Riconosce comandi in linguaggio naturale per spegnere e riporre le torce nello zaino (es. *"spegni la torcia"*, *"spengo la torcia e mi siedo"*, *"mettiamo via le torce"*) o per riaccenderle (*"accendi la torcia"*, *"estraggo una torcia"*).
   - **Nessuna Auto-accensione Indesiderata:** Se una torcia viene spenta volontariamente o se ci si trova in un luogo illuminato, il sistema non brucia mai torce di riserva dall'inventario.
   - **Comando `/torcia [on|off|auto]` & `/ambiente [tipo]`:** Menu completo per accendere, spegnere/riporre, gestire le scorte, attivare/disattivare l'auto-sostituzione a fine durata, o forzare/ispezionare l'ambiente di gioco (taverna, città, dungeon, auto).
   - Countdown di 6 turni per torcia (60 min) attivo esclusivamente nei dungeon bui con avviso di tremolio al 1° turno.
   - Condizione di Buio Totale automatica all'esaurimento con penalità BECMI (-4 al TxC, -4 alla CA) iniettata nel prompt del DM.
   - **Incontri Erranti Bilanciati (`/incontri`):** Frequenza regolabile con comando `/incontri [raro|normale|frequente|off]`. Il nuovo default ("Raro / Bilanciato") esegue il controllo ogni 4 turni (40 min) tirando 1 su 1d8 (~12.5%) con cooldown obbligatorio di almeno 4 turni per evitare incontri a raffica. Disattivato in locande, città e alla luce del sole. Niente mostri casuali durante il riposo in locanda.
3. **Riposo & Guarigione Naturale (`/riposo`):**
   - Riposo breve (10 min) per riorganizzare il party.
   - Riposo lungo (8 ore) che consuma una razione di cibo dallo zaino, ripristina 1d3 PF secondo le regole BECMI e rigenera al 100% tutti gli slot incantesimi.
   - Tiro automatico per mostri erranti notturni con risveglio immediato se l'accampamento viene interrotto.
4. **Tabelle Reazione & Morale Mostri (2d6 BECMI):**
   - Batteria dadi arricchita con tiro 2d6 Reazione (2 = Attacco immediato/feroce, 3-5 = Ostile, 6-8 = Incerto, 9-11 = Neutrale/Cauto, 12 = Amichevole/Aperto al dialogo).
   - Tiro 2d6 Morale dei mostri a disposizione del DM per verificare se i nemici fuggono o si arrendono.
5. **Esportazione Cronaca dell'Avventura (`/esporta`):**
   - Esporta la storia completa, le schede dei personaggi, le note del diario e le statistiche dell'avventura in un documento Markdown formattato salvato nella cartella `cronache/`.
6. **Mappa Tattica A4 PDF per la Campagna (`/mappa pdf`, `/mappapdf`, `/esporta mappa`):**
   - Generatore PDF 1.4 vettoriale nativo in Python puro standard library con FlateDecode compression (zero librerie terze).
   - Formato A4 perfetto per stampa o visualizzazione su tablet/schermo al tavolo da gioco (ISO 210 x 297 mm).
   - **Pagina 1 (Mappa Tattica)**:
     - Doppia cornice decorativa Scatola Rossa (cremisi e oro).
     - Intestazione con titolo avventura, party, livello, turno, tempo trascorso e stato torce.
     - Griglia blueprint a quadretti 10 piedi / 3 metri (stile TSR classico).
     - Rendering vettoriale: muri spessi in pietra con giunzioni, pavimentazione stanze, corridoi lastricati, porte in legno, porte segrete ('S'), porte aperte ('/'), token Party ('P' rosso), pericoli/trappole ('!'), tesori ('$'), badge numerati stanze.
     - Rosa dei venti (indicatore Nord) e barra di scala.
     - Legenda numerata con titoli e descrizioni delle stanze.
     - Segni convenzionali e appunti di spedizione.
   - **Pagina 2 (Dossier Ambientale & Registro di Esplorazione)**:
     - Griglia cartografica ASCII originale in riquadro terminale retro.
     - Scheda Roster Compagnia con PF, CA, attacchi, MO e slot incantesimi.
     - Dossier descrittivo approfondito degli ambienti visitati.
     - Righe tratteggiate per annotazioni a penna fisiche durante le sessioni di campagna.
   - Salvataggio automatico nella cartella dedicata `mappe/`.
7. **Schede Personaggio Ufficiali in PDF A4 (`/scheda pdf`, `/schedapdf`, `/esporta scheda`, Menu `[P]`):**
   - Esportazione vettoriale A4 ad alta definizione salvata nella cartella dedicata `schede/` con grafica e colori originali TSR Scatola Rossa (rosso cremisi e oro).
   - 6 caratteristiche base (FOR, INT, SAG, DES, COS, CAR) con punteggio, modificatori BECMI (-3..+3) e note esplicative.
   - Riquadri di combattimento ad alto impatto visivo: Punti Ferita (PF attuali e max con dado vita), Classe Armatura (CA con armatura/scudo equipaggiati), Attacco & THAC0 con bonus TxC corpo a corpo e a distanza.
   - Box dedicato per i 5 Tiri Salvezza BECMI (Raggio Morte/Veleno, Bacchette Magiche, Paralisi/Pietrificazione, Soffio di Drago, Bastoni/Incantesimi) calcolati dinamicamente per classe e livello.
   - Privilegi e abilità speciali di classe formattati su righe multiple.
   - Borsello (MO ed equivalenze monetarie BECMI), velocità di movimento (esplorazione 60', combattimento 20', corsa 60') e regole di riposo/guarigione.
   - Layout adattivo intelligente: per gli incantatori (Mago, Elfo, Chierico, Druido, Paladino) visualizza il grimorio con gli slot giornalieri per cerchio e gli incantesimi preparati; per i combattenti/non-incantatori riserva l'intero riquadro all'equipaggiamento esteso e armi.
   - Riquadro inferiore con righe per annotazioni a penna durante le sessioni al tavolo.
   - Accessibile durante il gioco con `/scheda pdf`, `/esporta scheda`, dal menu principale con l'opzione `[P]` (stampa singolo PG o party completo), e offerto automaticamente subito dopo la creazione di un eroe.
8. **Manuale dei Comandi & Guida di Gioco PDF A4 con Auto-Sincronizzazione (`manuale_comandi_dnd.pdf`, `/help pdf`, Menu `[G]`):**
   - Guida completa e compatta su 2 pagine A4 suddivisa in 7 sezioni tematiche:
     1. Azioni del Party & Comandi Base
     2. Tempo del Dungeon, Illuminazione, Torce & Buio Totale
     3. Sistema Magia, Grimorio, Slot & Lancio Incantesimi
     4. Combattimento, Tiri Dado Reali & Reazioni/Morale BECMI
     5. Gestione Eroi, Livello & Schede Personaggio PDF A4
     6. Cartografia del Dungeon & Mappe A4 PDF
     7. Audio Retro, Modello AI, Multiplayer LAN & Comandi di Sistema
   - **Meccanismo di Auto-Sincronizzazione Intelligente:** calcola l'impronta crittografica MD5 dei comandi e della guida (`.manuale_hash`). Ad ogni avvio del programma in `main()`, verifica l'hash: se i comandi o il testo di help subiscono modifiche o se il file manca, il documento PDF viene immediatamente rigenerato senza rallentamenti.
   - Può essere rigenerato o consultato in qualsiasi momento con il comando `/help pdf` (o `/comandi pdf`) in sessione o premendo `[G]` dal menu principale.
9. **Modalità di Gioco Interattiva con Chiamata Dadi DM (Menu `[I]`, `/modalita`):**
   - Scelta tra due modalità di esperienza al tavolo:
     - **Modalità Interattiva (Predefinita & Consigliata):** Il Dungeon Master AI descrive la scena fino al punto culminante e, di fronte a un'azione incerta (attacco, TS, prova abilità/scasso/trappole), **non tira mai i dadi per i giocatori né auto-risolve l'esito**. Emette invece una chiamata esplicita: `[CHIAMATA DADO: NomePG - Tira <formula> per <scopo> (vs Soglia/CA <valore>)]` e si ferma in attesa del tiro reale del giocatore.
     - **Modalità Classica / Continua:** Il DM AI e il motore tirano direttamente i dadi (inclusi autodadi) e narrano subito esito e conseguenze in modo continuo.
   - **Riconoscimento Automatico Tiri Reali:** Il giocatore può comunicare il proprio tiro lanciando dadi fisici al tavolo e digitando semplicemente il numero ottenuto (es. `16`, `ho fatto 15`, `tiro 14`), oppure digitando `/d20`, `/d8+1`, ecc. Il sistema wrappa il tiro in `[TIRO REALE: ...]` e il DM calcola la formula `[NomePG - Prova: Dado +/- mod = Totale vs Soglia -> Esito]`. In caso di colpo a segno, il DM procede chiedendo separatamente il tiro per i danni.
   - **UI & Indicatore Visivo:** Banner retro dorato e rosso in evidenza quando il DM è in attesa di un dado (`🎲 IL DM ATTENDE IL TUO TIRO: ...`), con prompt personalizzato `[NomePG - TIRO DADO] > ` e badge dedicato in testata (`🎲 Interattiva` / `🎲 Classica`).
   - **Controllo e Persistenza:** Menu dedicato `[I]` nel menu principale, scelta guidata alla creazione di nuove avventure, comando in-game `/modalita [interattiva|classica]`, e salvataggio permanente in SQLite (`stato_dungeon_json`).
10. **Gestione Inventario & Zaino Dedicata (`/inventario`, `/zaino`, `/equip`):**
   - Schermata di consultazione rapida che suddivide automaticamente gli oggetti in:
     - ⚔️ **Armi & Munizioni** (con danni e proprietà)
     - 🛡️ **Armatura & Protezione** (con CA risultante)
     - 🎒 **Zaino & Attrezzatura da Avventura** (torce, razioni, corde, attrezzi)
     - 💰 **Borsello & Tesori** (monete d'oro individuali e totali di compagnia)
   - Supporto per visualizzazione singolo personaggio (`/inventario <nome>`) o riepilogo collettivo dell'intero gruppo (`/inventario party` o `/inventario tutti`).
   - Inserito nella barra rapida dei comandi in testata e nella guida comandi `/help`.
