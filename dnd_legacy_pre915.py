import os
import sys
import re
import json
import time
import base64
import importlib
import random
import select
import subprocess
from datetime import datetime

ADVENTURES_FILE = "avventure_dnd.json"
MODULI_DIR = "moduli_pdf"
CHARACTERS_FILE = "personaggi_dnd.json"
LEGACY_SAVE = "salvataggio_dnd.json"
LEGACY_DIARY = "diario_avventura.txt"
MODELLO = "gemini-3.8-flash"

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

CLASSI_BASE = {
    "1": {
        "classe": "Guerriero", "dado_vita": 8, "ca_base": 3,
        "forza": 15, "intelligenza": 9, "saggezza": 10, "destrezza": 13, "costituzione": 14, "carisma": 11,
        "allineamento": "Legale",
        "equip": ["Spada Lunga (1d8+1)", "Pugnale (1d4+1)", "Arco Corto (1d6)", "20 Frecce", "Corazza di Maglia", "Scudo", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre", "Corda 15m", "Pertica 3m"],
        "mo": 15
    },
    "2": {
        "classe": "Elfo", "dado_vita": 6, "ca_base": 4,
        "forza": 13, "intelligenza": 14, "saggezza": 10, "destrezza": 14, "costituzione": 12, "carisma": 12,
        "allineamento": "Neutrale",
        "equip": ["Spada Lunga (1d8+1)", "Arco Corto (1d6)", "20 Frecce", "Corazza di Maglia", "Libro Incantesimi (Sonno, Lettura Magico)", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre", "Pertica 3m"],
        "mo": 20
    },
    "3": {
        "classe": "Nano", "dado_vita": 8, "ca_base": 3,
        "forza": 14, "intelligenza": 9, "saggezza": 11, "destrezza": 11, "costituzione": 16, "carisma": 9,
        "allineamento": "Legale",
        "equip": ["Ascia da Battaglia (1d8+1)", "Martello da Guerra (1d6+1)", "Corazza di Maglia", "Scudo", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre", "Corda 15m", "Pertica 3m"],
        "mo": 25
    },
    "4": {
        "classe": "Ladro", "dado_vita": 4, "ca_base": 6,
        "forza": 11, "intelligenza": 12, "saggezza": 10, "destrezza": 16, "costituzione": 12, "carisma": 13,
        "allineamento": "Neutrale",
        "equip": ["Spada Corta (1d6)", "2 Pugnali (1d4)", "Fionda (1d4) + 20 Pietre", "Armatura di Cuoio", "Attrezzi da Scasso", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Corda 15m"],
        "mo": 30
    },
    "5": {
        "classe": "Chierico", "dado_vita": 6, "ca_base": 3,
        "forza": 13, "intelligenza": 10, "saggezza": 15, "destrezza": 10, "costituzione": 13, "carisma": 13,
        "allineamento": "Legale",
        "equip": ["Mazza Ferrata (1d6+1)", "Fionda (1d4)", "Corazza di Maglia", "Scudo", "Simbolo Sacro d'Argento", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre"],
        "mo": 20
    },
    "6": {
        "classe": "Mago", "dado_vita": 4, "ca_base": 9,
        "forza": 9, "intelligenza": 16, "saggezza": 12, "destrezza": 13, "costituzione": 11, "carisma": 11,
        "allineamento": "Neutrale",
        "equip": ["Pugnale (1d4)", "Bastone Ferrato (1d4)", "Libro Incantesimi (Sonno, Dardo Incantato, Luce)", "Veste da Viaggio", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre"],
        "mo": 35
    },
    "7": {
        "classe": "Halfling", "dado_vita": 6, "ca_base": 6,
        "forza": 11, "intelligenza": 11, "saggezza": 11, "destrezza": 15, "costituzione": 14, "carisma": 12,
        "allineamento": "Legale",
        "equip": ["Spada Corta (1d6)", "Fionda (1d4) + 20 Pietre", "Armatura di Cuoio", "Scudo", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre", "Corda 15m"],
        "mo": 20
    },
    "8": {
        "classe": "Druido", "dado_vita": 6, "ca_base": 7,
        "forza": 10, "intelligenza": 12, "saggezza": 15, "destrezza": 12, "costituzione": 13, "carisma": 12,
        "allineamento": "Neutrale",
        "equip": ["Randello Ferrato (1d4+1)", "Fionda (1d4) + 20 Pietre", "Armatura di Cuoio", "Simbolo Sacro di Vischio", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre"],
        "mo": 20
    },
    "9": {
        "classe": "Paladino", "dado_vita": 8, "ca_base": 3,
        "forza": 15, "intelligenza": 10, "saggezza": 13, "destrezza": 11, "costituzione": 14, "carisma": 15,
        "allineamento": "Legale",
        "equip": ["Spada Lunga (1d8+1)", "Lancia (1d6)", "Corazza di Maglia", "Scudo", "Simbolo Sacro d'Argento", "Zaino", "6 Torce", "Acciarino", "7 Razioni", "Otre", "Corda 15m"],
        "mo": 25
    }
}

DADO_VITA = {
    "Guerriero": 8, "Paladino": 8, "Nano": 8,
    "Elfo": 6, "Chierico": 6, "Druido": 6, "Halfling": 6,
    "Mago": 4, "Ladro": 4
}

PF_FISSI_POST_9 = {
    "Guerriero": 2, "Paladino": 2, "Nano": 3,
    "Elfo": 2, "Halfling": 2, "Ladro": 2,
    "Chierico": 1, "Druido": 1, "Mago": 1
}

TITOLI_CLASSI = {
    "Guerriero": {
        1: "Veterano", 2: "Guerriero", 3: "Spadaccino", 4: "Eroe", 5: "Campione Spadaccino",
        6: "Campione", 7: "Supereroe", 8: "Condottiero", 9: "Signore (Lord)"
    },
    "Paladino": {
        1: "Scudiero Sacro", 2: "Cavaliere Giurato", 3: "Lama di Giustizia", 4: "Campione della Fede",
        5: "Custode Sacro", 6: "Crociato della Luce", 7: "Paladino Difensore", 8: "Cavaliere Alto", 9: "Paladino Signore"
    },
    "Chierico": {
        1: "Accolito", 2: "Adepto", 3: "Sacerdote", 4: "Vicario", 5: "Curato",
        6: "Vescovo", 7: "Lama Santa", 8: "Lama Alta", 9: "Patriarca"
    },
    "Druido": {
        1: "Novizio della Selva", 2: "Iniziato dei Boschi", 3: "Custode delle Radici", 4: "Vegliafronde",
        5: "Fratello degli Alberi", 6: "Mastro dei Boschi", 7: "Guardiano della Terra", 8: "Saggio Silvano", 9: "Druido"
    },
    "Mago": {
        1: "Medium", 2: "Veggente", 3: "Illusionista", 4: "Incantatore Minore", 5: "Negromante",
        6: "Stregone", 7: "Mago", 8: "Grande Mago", 9: "Arcimago"
    },
    "Ladro": {
        1: "Apprendista", 2: "Tagliaborse", 3: "Scassinatore", 4: "Furtivo", 5: "Malandrino",
        6: "Ladro Scelto", 7: "Predatore", 8: "Mastro Scassinatore", 9: "Mastro Ladro"
    },
    "Nano": {
        1: "Recluta dei Clan", 2: "Guerriero delle Rocce", 3: "Spaccapietre", 4: "Mastro di Maglio",
        5: "Guardiano delle Profondità", 6: "Veterano dei Baratri", 7: "Campione di Ferro", 8: "Capoclan", 9: "Signore dei Nani"
    },
    "Elfo": {
        1: "Sentinella dei Boschi", 2: "Guerriero Arcano", 3: "Cacciatore Elfico", 4: "Maestro delle Fronde",
        5: "Custode dei Segreti", 6: "Spada Mistica", 7: "Vigile delle Stelle", 8: "Campione delle Selve", 9: "Signore Elfico", 10: "Nobile delle Stirpi"
    },
    "Halfling": {
        1: "Esploratore delle Colline", 2: "Tiratore Scelto", 3: "Guida Campestre", 4: "Guardiano delle Contee",
        5: "Sentinella delle Terre Basse", 6: "Mastro delle Tane", 7: "Campione del Focolare", 8: "Sceriffo Halfling"
    }
}

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
{GIALLO}           Edizione Mentzer / BECMI (Base, Expert, Companion, Master, Immortals) - Terminale AI DM{RESET}
"""

HELP_TESTO = f"""{CIANO}{GRASSETTO}=== GUIDA AI COMANDI - D&D BECMI ==={RESET}

{GIALLO}Personaggio, Emporio e Diario:{RESET}
  {VERDE}/scheda{RESET} (o /inventario)  Mostra caratteristiche, TS, livello ed equipaggiamento.
  {VERDE}/livello{RESET}                 Mostra la progressione PE, soglie di livello e avanza di livello.
  {VERDE}/emporio{RESET} (o /negozio)    Acquista armi, armature, torce, pozioni e gregari con le tue MO.
  {VERDE}/aggiorna{RESET}                Aggiorna manualmente livello, PF max, CA, MO o aggiungi oggetti.
  {VERDE}/nota <testo>{RESET}            Salva un appunto nel diario di questa avventura (/nota per leggere).

{GIALLO}Dadi e Strumenti di Esplorazione:{RESET}
  {VERDE}/d20{RESET} (o /d8+1, /2d6)     Tira dadi reali dal tuo PC e invia il risultato al Dungeon Master.
  {VERDE}/autodadi{RESET}                Attiva/disattiva la batteria completa di dadi reali ad ogni turno.
  {VERDE}/mappa{RESET}                   Genera una mappa ASCII delle stanze e dei corridoi esplorati.
  {VERDE}/suoni{RESET}                   Attiva/disattiva gli effetti sonori retro del terminale.

{GIALLO}Gestione Avventure e Uscita:{RESET}
  {VERDE}/storico{RESET}                 Mostra gli ultimi 3 turni dell'avventura corrente.
  {VERDE}/riassunto{RESET}               Comprime la memoria per mantenere veloce l'IA nelle partite lunghe.
  {VERDE}/stop{RESET} (o /interrompi, /menu, /avventure)  Interrompe l'avventura corrente, salva e torna al menu principale.
  {VERDE}/chiudi{RESET} (o /esci)        Salva tutti i progressi ed esce completamente dal programma.
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
    ripetizioni = {"critico": 3, "danno": 2, "tesoro": 1, "levelup": 4}.get(tipo, 1)
    for _ in range(ripetizioni):
        sys.stdout.write("\a")
        sys.stdout.flush()
        time.sleep(0.12)


def calcola_soglia_pe(classe, livello):
    """Restituisce i PE necessari per raggiungere il livello indicato (1-36).
    Se livello >= 37, restituisce la soglia per l'Ascensione al Rango Immortale."""
    if livello <= 1:
        return 0
    cls = classe.capitalize()
    if cls in ["Guerriero", "Paladino"]:
        t = [0, 0, 2000, 4000, 8000, 16000, 32000, 64000, 120000, 240000]
        if livello <= 9:
            return t[livello]
        return 240000 + (livello - 9) * 120000
    elif cls in ["Chierico", "Druido"]:
        t = [0, 0, 1500, 3000, 6000, 12000, 25000, 50000, 100000, 200000]
        if livello <= 9:
            return t[livello]
        return 200000 + (livello - 9) * 100000
    elif cls == "Mago":
        t = [0, 0, 2500, 5000, 10000, 20000, 40000, 80000, 150000, 300000]
        if livello <= 9:
            return t[livello]
        return 300000 + (livello - 9) * 150000
    elif cls == "Ladro":
        t = [0, 0, 1200, 2400, 4800, 9600, 20000, 40000, 80000, 160000]
        if livello <= 9:
            return t[livello]
        return 160000 + (livello - 9) * 120000
    elif cls == "Nano":
        t = [0, 0, 2200, 4400, 8800, 17000, 35000, 70000, 140000, 270000, 400000, 530000, 660000]
        if livello <= 12:
            return t[livello]
        return 660000 + (livello - 12) * 200000
    elif cls == "Elfo":
        t = [0, 0, 4000, 8000, 16000, 32000, 64000, 120000, 250000, 400000, 600000]
        if livello <= 10:
            return t[livello]
        return 600000 + (livello - 10) * 200000
    elif cls == "Halfling":
        t = [0, 0, 2000, 4000, 8000, 16000, 32000, 64000, 120000]
        if livello <= 8:
            return t[livello]
        return 120000 + (livello - 8) * 120000
    # Fallback standard guerriero
    if livello <= 9:
        return [0, 0, 2000, 4000, 8000, 16000, 32000, 64000, 120000, 240000][livello]
    return 240000 + (livello - 9) * 120000


def calcola_thac0(classe, livello, immortale=False, livello_immortale=1):
    """Calcola il THAC0 (tiro necessario per colpire CA 0 su 1d20) secondo le tabelle BECMI."""
    if immortale:
        return max(-20, 2 - livello_immortale)
    liv = max(1, min(36, livello))
    cls = classe.capitalize()
    if cls in ["Guerriero", "Paladino", "Nano", "Elfo", "Halfling"]:
        if liv <= 3: return 19
        if liv <= 6: return 17
        if liv <= 9: return 15
        if liv <= 12: return 13
        if liv <= 15: return 11
        if liv <= 18: return 10
        if liv <= 21: return 9
        if liv <= 24: return 8
        if liv <= 27: return 7
        if liv <= 30: return 6
        if liv <= 33: return 5
        return 4
    elif cls in ["Chierico", "Druido"]:
        if liv <= 4: return 19
        if liv <= 8: return 17
        if liv <= 12: return 15
        if liv <= 16: return 13
        if liv <= 20: return 12
        if liv <= 24: return 10
        if liv <= 28: return 8
        if liv <= 32: return 7
        return 6
    elif cls == "Ladro":
        if liv <= 4: return 19
        if liv <= 8: return 17
        if liv <= 12: return 15
        if liv <= 16: return 13
        if liv <= 20: return 12
        if liv <= 24: return 11
        if liv <= 28: return 9
        if liv <= 32: return 8
        return 7
    elif cls == "Mago":
        if liv <= 5: return 19
        if liv <= 10: return 17
        if liv <= 15: return 16
        if liv <= 20: return 14
        if liv <= 25: return 13
        if liv <= 30: return 11
        if liv <= 35: return 10
        return 9
    return 19


def calcola_tiro_colpire(thac0, ca, bonus):
    """Calcola il tiro minimo richiesto sul d20 (2-20) considerando THAC0, CA bersaglio e bonus."""
    serve = thac0 - ca - bonus
    return max(2, min(20, serve))


def formatta_attacco_stringa(eroe):
    """Genera la stringa completa dell'attacco con THAC0 e soglie per le CA chiave."""
    immortale = eroe.get("immortale", False)
    liv_imm = eroe.get("livello_immortale", 1)
    thac0 = calcola_thac0(eroe["classe"], eroe["livello"], immortale, liv_imm)
    mod_for = mod_caratteristica(eroe["forza"])
    mod_des = mod_caratteristica(eroe["destrezza"])

    cas = [9, 7, 5, 3, 0, -2]
    tiri_mischia = " | ".join(f"CA {ca}: {calcola_tiro_colpire(thac0, ca, mod_for)}+" for ca in cas)

    if mod_for == mod_des:
        return f"THAC0 {thac0} -> {tiri_mischia}"
    else:
        tiri_distanza = " | ".join(f"CA {ca}: {calcola_tiro_colpire(thac0, ca, mod_des)}+" for ca in [9, 5, 0])
        return f"THAC0 {thac0} | Mischia (FOR {mod_for:+d}): {tiri_mischia} | Distanza (DES {mod_des:+d}): {tiri_distanza}"


def calcola_tiri_salvezza(classe, livello, immortale=False):
    """Restituisce dict con i 5 tiri salvezza ufficiali BECMI per la classe e livello specificati."""
    if immortale:
        return {"morte": 2, "bacchette": 2, "paralisi": 2, "soffio": 2, "incantesimi": 2}
    liv = max(1, min(36, livello))
    cls = classe.capitalize()
    if cls in ["Guerriero", "Paladino"]:
        if liv <= 3:   return {"morte": 12, "bacchette": 13, "paralisi": 14, "soffio": 15, "incantesimi": 16}
        if liv <= 6:   return {"morte": 10, "bacchette": 11, "paralisi": 12, "soffio": 13, "incantesimi": 14}
        if liv <= 9:   return {"morte": 8,  "bacchette": 9,  "paralisi": 10, "soffio": 10, "incantesimi": 12}
        if liv <= 12:  return {"morte": 6,  "bacchette": 7,  "paralisi": 8,  "soffio": 8,  "incantesimi": 10}
        if liv <= 15:  return {"morte": 4,  "bacchette": 5,  "paralisi": 6,  "soffio": 5,  "incantesimi": 8}
        if liv <= 18:  return {"morte": 4,  "bacchette": 4,  "paralisi": 5,  "soffio": 4,  "incantesimi": 6}
        if liv <= 21:  return {"morte": 4,  "bacchette": 4,  "paralisi": 4,  "soffio": 3,  "incantesimi": 5}
        if liv <= 24:  return {"morte": 3,  "bacchette": 3,  "paralisi": 4,  "soffio": 3,  "incantesimi": 4}
        if liv <= 27:  return {"morte": 2,  "bacchette": 2,  "paralisi": 3,  "soffio": 2,  "incantesimi": 3}
        return {"morte": 2, "bacchette": 2, "paralisi": 2, "soffio": 2, "incantesimi": 2}
    elif cls in ["Chierico", "Druido"]:
        if liv <= 4:   return {"morte": 11, "bacchette": 12, "paralisi": 14, "soffio": 16, "incantesimi": 15}
        if liv <= 8:   return {"morte": 9,  "bacchette": 10, "paralisi": 12, "soffio": 14, "incantesimi": 12}
        if liv <= 12:  return {"morte": 7,  "bacchette": 8,  "paralisi": 10, "soffio": 12, "incantesimi": 9}
        if liv <= 16:  return {"morte": 5,  "bacchette": 6,  "paralisi": 8,  "soffio": 10, "incantesimi": 7}
        if liv <= 20:  return {"morte": 4,  "bacchette": 5,  "paralisi": 7,  "soffio": 8,  "incantesimi": 6}
        if liv <= 24:  return {"morte": 3,  "bacchette": 4,  "paralisi": 6,  "soffio": 6,  "incantesimi": 5}
        if liv <= 28:  return {"morte": 2,  "bacchette": 3,  "paralisi": 5,  "soffio": 4,  "incantesimi": 4}
        if liv <= 32:  return {"morte": 2,  "bacchette": 2,  "paralisi": 4,  "soffio": 3,  "incantesimi": 3}
        return {"morte": 2, "bacchette": 2, "paralisi": 3, "soffio": 2, "incantesimi": 2}
    elif cls == "Mago":
        if liv <= 5:   return {"morte": 13, "bacchette": 14, "paralisi": 13, "soffio": 16, "incantesimi": 15}
        if liv <= 10:  return {"morte": 11, "bacchette": 12, "paralisi": 11, "soffio": 14, "incantesimi": 12}
        if liv <= 15:  return {"morte": 9,  "bacchette": 10, "paralisi": 9,  "soffio": 12, "incantesimi": 9}
        if liv <= 20:  return {"morte": 7,  "bacchette": 8,  "paralisi": 7,  "soffio": 10, "incantesimi": 7}
        if liv <= 25:  return {"morte": 5,  "bacchette": 6,  "paralisi": 5,  "soffio": 8,  "incantesimi": 5}
        if liv <= 30:  return {"morte": 4,  "bacchette": 5,  "paralisi": 4,  "soffio": 6,  "incantesimi": 4}
        if liv <= 35:  return {"morte": 3,  "bacchette": 4,  "paralisi": 3,  "soffio": 4,  "incantesimi": 3}
        return {"morte": 2, "bacchette": 3, "paralisi": 2, "soffio": 3, "incantesimi": 2}
    elif cls == "Ladro":
        if liv <= 4:   return {"morte": 13, "bacchette": 14, "paralisi": 13, "soffio": 16, "incantesimi": 15}
        if liv <= 8:   return {"morte": 12, "bacchette": 13, "paralisi": 11, "soffio": 14, "incantesimi": 13}
        if liv <= 12:  return {"morte": 10, "bacchette": 11, "paralisi": 9,  "soffio": 12, "incantesimi": 10}
        if liv <= 16:  return {"morte": 8,  "bacchette": 9,  "paralisi": 7,  "soffio": 10, "incantesimi": 8}
        if liv <= 20:  return {"morte": 6,  "bacchette": 7,  "paralisi": 5,  "soffio": 8,  "incantesimi": 6}
        if liv <= 24:  return {"morte": 4,  "bacchette": 5,  "paralisi": 4,  "soffio": 6,  "incantesimi": 4}
        if liv <= 28:  return {"morte": 3,  "bacchette": 4,  "paralisi": 3,  "soffio": 4,  "incantesimi": 3}
        if liv <= 32:  return {"morte": 2,  "bacchette": 3,  "paralisi": 2,  "soffio": 3,  "incantesimi": 2}
        return {"morte": 2, "bacchette": 2, "paralisi": 2, "soffio": 2, "incantesimi": 2}
    elif cls in ["Nano", "Halfling"]:
        if liv <= 3:   return {"morte": 8,  "bacchette": 9,  "paralisi": 10, "soffio": 13, "incantesimi": 12}
        if liv <= 6:   return {"morte": 6,  "bacchette": 7,  "paralisi": 8,  "soffio": 10, "incantesimi": 10}
        if liv <= 9:   return {"morte": 4,  "bacchette": 5,  "paralisi": 6,  "soffio": 7,  "incantesimi": 8}
        if liv <= 12:  return {"morte": 2,  "bacchette": 3,  "paralisi": 4,  "soffio": 4,  "incantesimi": 6}
        return {"morte": 2, "bacchette": 2, "paralisi": 2, "soffio": 2, "incantesimi": 2}
    elif cls == "Elfo":
        if liv <= 3:   return {"morte": 12, "bacchette": 13, "paralisi": 13, "soffio": 15, "incantesimi": 15}
        if liv <= 6:   return {"morte": 10, "bacchette": 11, "paralisi": 11, "soffio": 13, "incantesimi": 12}
        if liv <= 9:   return {"morte": 8,  "bacchette": 9,  "paralisi": 9,  "soffio": 10, "incantesimi": 10}
        if liv <= 12:  return {"morte": 6,  "bacchette": 7,  "paralisi": 8,  "soffio": 8,  "incantesimi": 8}
        return {"morte": 4, "bacchette": 5, "paralisi": 6, "soffio": 6, "incantesimi": 6}
    return {"morte": 12, "bacchette": 13, "paralisi": 14, "soffio": 15, "incantesimi": 16}


def formatta_tiri_salvezza(ts_dict):
    """Formatta i 5 TS in una stringa leggibile e standardizzata."""
    return (
        f"Morte/Veleno {ts_dict['morte']} | "
        f"Bacchette {ts_dict['bacchette']} | "
        f"Paralisi {ts_dict['paralisi']} | "
        f"Soffio {ts_dict['soffio']} | "
        f"Incantesimi {ts_dict['incantesimi']}"
    )


def calcola_slot_incantesimi(classe, livello):
    """Restituisce lista con numero di slot per cerchio: [slot_1, slot_2, ...] secondo regole BECMI."""
    liv = max(1, min(36, livello))
    cls = classe.capitalize()
    if cls == "Mago":
        t = {
            1: [1], 2: [2], 3: [2, 1], 4: [2, 2], 5: [2, 2, 1],
            6: [3, 2, 2], 7: [3, 2, 2, 1], 8: [3, 3, 2, 2], 9: [3, 3, 3, 2, 1],
            10: [3, 3, 3, 3, 2], 11: [4, 3, 3, 3, 2, 1], 12: [4, 4, 3, 3, 3, 2],
            13: [4, 4, 4, 3, 3, 2, 1], 14: [4, 4, 4, 4, 3, 3, 2], 15: [4, 4, 4, 4, 4, 3, 2, 1],
            16: [5, 4, 4, 4, 4, 3, 3, 2], 17: [5, 5, 4, 4, 4, 4, 3, 2, 1], 18: [5, 5, 5, 4, 4, 4, 3, 3, 2],
            19: [5, 5, 5, 5, 4, 4, 4, 3, 2, 1], 20: [5, 5, 5, 5, 5, 4, 4, 3, 3, 2],
            21: [5, 5, 5, 5, 5, 4, 4, 4, 3, 2], 22: [5, 5, 5, 5, 5, 5, 4, 4, 3, 3],
            23: [5, 5, 5, 5, 5, 5, 5, 4, 4, 3], 24: [6, 5, 5, 5, 5, 5, 5, 4, 4, 3],
            25: [6, 6, 5, 5, 5, 5, 5, 5, 4, 4], 26: [6, 6, 6, 5, 5, 5, 5, 5, 5, 4],
            27: [6, 6, 6, 6, 5, 5, 5, 5, 5, 5], 28: [6, 6, 6, 6, 6, 5, 5, 5, 5, 5],
            29: [7, 6, 6, 6, 6, 6, 5, 5, 5, 5], 30: [7, 7, 6, 6, 6, 6, 6, 5, 5, 5],
            31: [7, 7, 7, 6, 6, 6, 6, 6, 5, 5], 32: [7, 7, 7, 7, 6, 6, 6, 6, 6, 5],
            33: [7, 7, 7, 7, 7, 6, 6, 6, 6, 6], 34: [8, 7, 7, 7, 7, 7, 6, 6, 6, 6],
            35: [8, 8, 7, 7, 7, 7, 7, 6, 6, 6], 36: [9, 8, 7, 7, 6, 6, 5, 5, 5]
        }
        return t.get(liv, [1])
    elif cls in ["Chierico", "Druido"]:
        t = {
            1: [], 2: [1], 3: [2], 4: [2, 1], 5: [2, 2],
            6: [2, 2, 1, 1], 7: [2, 2, 2, 1, 1], 8: [3, 3, 2, 2, 1], 9: [3, 3, 3, 2, 2],
            10: [4, 4, 3, 3, 2], 11: [4, 4, 4, 3, 3, 1], 12: [4, 4, 4, 4, 4, 1],
            13: [5, 5, 4, 4, 4, 2], 14: [5, 5, 5, 4, 4, 3], 15: [6, 5, 5, 5, 4, 4],
            16: [6, 6, 5, 5, 5, 4, 1], 17: [6, 6, 6, 5, 5, 5, 2], 18: [6, 6, 6, 6, 5, 5, 3],
            19: [7, 6, 6, 6, 6, 5, 4], 20: [7, 7, 6, 6, 6, 6, 5], 21: [7, 7, 7, 6, 6, 6, 5],
            22: [7, 7, 7, 7, 6, 6, 5], 23: [7, 7, 7, 7, 7, 6, 5], 24: [8, 7, 7, 7, 7, 6, 5],
            25: [8, 8, 7, 7, 7, 6, 5], 26: [8, 8, 8, 7, 7, 6, 6], 27: [8, 8, 8, 8, 7, 6, 6],
            28: [8, 8, 8, 8, 8, 6, 6], 29: [8, 8, 8, 8, 8, 7, 6], 30: [9, 8, 8, 8, 8, 7, 6],
            31: [9, 9, 8, 8, 8, 7, 6], 32: [9, 9, 9, 8, 8, 7, 6], 33: [9, 9, 9, 9, 8, 7, 6],
            34: [9, 9, 9, 9, 9, 7, 6], 35: [9, 9, 9, 9, 9, 8, 6], 36: [9, 9, 9, 9, 9, 8, 7]
        }
        return t.get(liv, [])
    elif cls == "Elfo":
        t = {
            1: [1], 2: [2], 3: [2, 1], 4: [2, 2], 5: [2, 2, 1],
            6: [3, 2, 2], 7: [3, 2, 2, 1], 8: [3, 3, 2, 2], 9: [3, 3, 3, 2, 1],
            10: [3, 3, 3, 3, 2]
        }
        if liv in t: return t[liv]
        return [4, 4, 4, 3, 3] if liv < 20 else [5, 4, 4, 4, 3]
    elif cls == "Paladino":
        if liv < 9: return []
        t = {
            9: [1], 10: [2], 11: [2, 1], 12: [2, 2], 13: [2, 2, 1],
            14: [3, 2, 1], 15: [3, 2, 2], 16: [3, 3, 2]
        }
        return t.get(liv, [3, 3, 3])
    return []


def formatta_slot_incantesimi(slot_list):
    if not slot_list:
        return "Nessuno"
    return ", ".join(f"{idx+1}° cerchio: {n}" for idx, n in enumerate(slot_list) if n > 0)


def calcola_abilita_ladro(livello):
    """Restituisce le percentuali ufficiali BECMI per le abilità del Ladro."""
    liv = max(1, min(36, livello))
    if liv <= 14:
        ol = 15 + (liv - 1) * 5
        frt = 10 + (liv - 1) * 5
        cs = min(99, 87 + (liv - 1))
        ms = 20 + (liv - 1) * 5
        hs = 10 + (liv - 1) * 5
        pp = 20 + (liv - 1) * 5
        if liv <= 2: hn = "1-2 su 1d6"
        elif liv <= 6: hn = "1-3 su 1d6"
        elif liv <= 13: hn = "1-4 su 1d6"
        else: hn = "1-5 su 1d6"
    else:
        ol = 80 + (liv - 14) * 4
        frt = 75 + (liv - 14) * 4
        cs = min(110, 99 + (liv - 14) // 5)
        ms = 85 + (liv - 14) * 3
        hs = 75 + (liv - 14) * 3
        pp = 85 + (liv - 14) * 4
        hn = f"{min(100, 80 + (liv - 14) * 2)}% (o 1-5 su 1d6)"
    return {
        "scassinare": ol,
        "trappole": frt,
        "scalare": cs,
        "silenzioso": ms,
        "ombre": hs,
        "borseggiare": pp,
        "ascoltare": hn
    }


def formatta_abilita_ladro(ab):
    return (
        f"Scassinare {ab['scassinare']}% | "
        f"Trappole {ab['trappole']}% | "
        f"Scalare {ab['scalare']}% | "
        f"Silenzioso {ab['silenzioso']}% | "
        f"Ombre {ab['ombre']}% | "
        f"Borseggio {ab['borseggiare']}% | "
        f"Ascoltare {ab['ascoltare']}"
    )


def ottieni_titolo_livello(eroe):
    """Restituisce il titolo di classe secondo le tabelle Mentzer / BECMI."""
    if eroe.get("immortale"):
        rango = eroe.get("rango_immortale", "Temporale")
        liv_imm = eroe.get("livello_immortale", 1)
        return f"{rango} (Liv.{liv_imm} Immortale)"
    cls = eroe.get("classe", "Guerriero")
    liv = eroe.get("livello", 1)
    titoli = TITOLI_CLASSI.get(cls, {})
    if liv in titoli:
        return titoli[liv]
    if liv >= 26:
        return f"Leggenda dei Reami (Liv.{liv})"
    elif liv >= 15:
        return f"Grande Feudatario (Liv.{liv})"
    elif liv >= 9:
        titolo_9 = titoli.get(9, "Signore")
        return f"{titolo_9} di {liv}° Livello"
    return f"{cls} di {liv}° Livello"


def determina_fascia_gioco(eroe):
    """Determina la fascia di regole BECMI attiva per il personaggio."""
    if eroe.get("immortale") or eroe.get("livello", 1) > 36:
        rango = eroe.get("rango_immortale", "Temporale")
        liv_imm = eroe.get("livello_immortale", 1)
        sfera = eroe.get("sfera", "Materia")
        return (
            "immortals",
            f"Set Immortals (Scatola Oro) - {rango} (Liv.{liv_imm})",
            f"Fascia Immortale: Il personaggio ha trasceso la mortalità. Appartiene alla Sfera di {sfera} e gestisce Punti Potere, conflitti cosmici tra le 5 Sfere, culti e trame che sconvolgono interi Piani e dimensioni."
        )
    liv = eroe.get("livello", 1)
    if liv >= 26:
        return (
            "master",
            "Set Master (Scatola Nera, Livelli 26-36)",
            "Fascia Master: Eroi leggendari al vertice della mortalità. Avventure extra-planari, manufatti leggendari, mostri epici e ricerca dell'Immortalità."
        )
    elif liv >= 15:
        return (
            "companion",
            "Set Companion (Scatola Celeste, Livelli 15-25)",
            "Fascia Companion: Baroni, Duchi e Grandi Feudatari. Gestione di domini e roccaforti, guerre tra nazioni (War Machine), intrighi dinastici e tornei."
        )
    elif liv >= 4:
        return (
            "expert",
            "Set Expert (Scatola Blu, Livelli 4-14)",
            "Fascia Expert: Esplorazione delle Terre Selvagge (Wilderness), viaggi su mappa a esagoni, sopravvivenza all'aperto, castelli e preparazione alla roccaforte (9° liv)."
        )
    else:
        return (
            "basic",
            "Set Base (Scatola Rossa, Livelli 1-3)",
            "Fascia Base: Dungeon crawling claustrofobico, cripte oscure, trappole ingegnose, torce da 6 turni, porte bloccate e sopravvivenza tattica."
        )


def stampa_banner_levelup(eroe, avanzamenti):
    titolo = ottieni_titolo_livello(eroe)
    _, nome_fascia, _ = determina_fascia_gioco(eroe)
    print(f"\n{GIALLO}{GRASSETTO}" + "=" * 80)
    print(" ⭐⭐⭐  LEVEL UP! IL TUO EROE E' SALITO DI LIVELLO!  ⭐⭐⭐ ")
    print(f" Regole Ufficiali D&D BECMI — {nome_fascia}")
    print("=" * 80 + f"{RESET}")
    print(f"  {CIANO}Eroe:{RESET} {GRASSETTO}{eroe['nome']}{RESET} | {VERDE}{eroe['classe']} Livello {eroe['livello']}{RESET} (Titolo: '{GIALLO}{titolo}{RESET}')")
    print(f"  {CIANO}Punti Ferita:{RESET} {VERDE}{GRASSETTO}{eroe['pf_attuali']}/{eroe['pf_max']} PF{RESET} | {CIANO}CA:{RESET} {eroe['ca']} | {CIANO}PE attuali:{RESET} {eroe['pe']:,}")
    for av in avanzamenti:
        print(f"  {VERDE}✔ {av}{RESET}")
    print(f"  {GIALLO}Tiri Salvezza:{RESET} {eroe['ts']}")
    print(f"  {GIALLO}Attacco:{RESET} {eroe['attacco']}")
    slot = calcola_slot_incantesimi(eroe["classe"], eroe["livello"])
    if slot:
        print(f"  {MAGENTA}Slot Incantesimi:{RESET} {formatta_slot_incantesimi(slot)}")
    if eroe["classe"] == "Ladro":
        print(f"  {MAGENTA}Abilità da Ladro:{RESET} {formatta_abilita_ladro(calcola_abilita_ladro(eroe['livello']))}")
    print(f"{GIALLO}{GRASSETTO}" + "=" * 80 + f"{RESET}\n")


def verifica_e_avanza_livello(eroe, silenzioso=False):
    """Verifica se l'eroe ha PE sufficienti per salire di livello (anche ripetutamente).
    Tira i PF (Dado Vita fino al 9° o fissi dal 10°), aggiorna TS, THAC0 e supporta l'Immortalità."""
    avanzamenti = []
    while True:
        if eroe.get("immortale"):
            liv_imm = eroe.get("livello_immortale", 1)
            if liv_imm >= 36:
                break
            soglia = 1000000 + liv_imm * 500000
            if eroe.get("pe", 0) < soglia:
                break
            nuovo_liv = liv_imm + 1
            eroe["livello_immortale"] = nuovo_liv
            if nuovo_liv <= 6:
                eroe["rango_immortale"] = "Temporale"
            elif nuovo_liv <= 12:
                eroe["rango_immortale"] = "Celestiale"
            elif nuovo_liv <= 18:
                eroe["rango_immortale"] = "Empireo"
            elif nuovo_liv <= 24:
                eroe["rango_immortale"] = "Eterno"
            else:
                eroe["rango_immortale"] = "Gerarca"
            pp_gain = 500 if nuovo_liv <= 18 else 1000
            eroe["pp_max"] = eroe.get("pp_max", 1000) + pp_gain
            eroe["pp_attuali"] = eroe.get("pp_attuali", 1000) + pp_gain
            eroe["ts"] = formatta_tiri_salvezza(calcola_tiri_salvezza(eroe["classe"], 36, immortale=True))
            eroe["attacco"] = formatta_attacco_stringa(eroe)
            avanzamenti.append(f"Ascensione Divina: {eroe['rango_immortale']} Livello {nuovo_liv} (+{pp_gain} Punti Potere!)")
            continue

        liv = eroe.get("livello", 1)
        if liv >= 36:
            soglia_ascensione = calcola_soglia_pe(eroe["classe"], 37)
            if eroe.get("pe", 0) >= soglia_ascensione:
                eroe["immortale"] = True
                eroe["rango_immortale"] = "Temporale"
                eroe["livello_immortale"] = 1
                eroe["sfera"] = eroe.get("sfera", "Materia")
                eroe["pp_max"] = 1000
                eroe["pp_attuali"] = 1000
                eroe["ts"] = formatta_tiri_salvezza(calcola_tiri_salvezza(eroe["classe"], 36, immortale=True))
                eroe["attacco"] = formatta_attacco_stringa(eroe)
                avanzamenti.append("ASCENSIONE AL RANGO IMMORTALE! L'eroe trascende il mondo mortale e accede alla Scatola Oro (1.000 Punti Potere)!")
            break

        soglia = calcola_soglia_pe(eroe["classe"], liv + 1)
        if eroe.get("pe", 0) < soglia:
            break

        nuovo_liv = liv + 1
        eroe["livello"] = nuovo_liv

        if nuovo_liv <= 9:
            dv = DADO_VITA.get(eroe["classe"], 8)
            tiro_dv = random.randint(1, dv)
            mod_cos = mod_caratteristica(eroe["costituzione"])
            pf_gain = max(1, tiro_dv + mod_cos)
            dettaglio_pf = f"1d{dv} ({tiro_dv}) {mod_cos:+d} (Costituzione) = +{pf_gain} PF"
        else:
            pf_gain = PF_FISSI_POST_9.get(eroe["classe"], 2)
            dettaglio_pf = f"+{pf_gain} PF fissi (regola BECMI dal 10° livello, nessun bonus COS)"

        eroe["pf_max"] += pf_gain
        eroe["pf_attuali"] += pf_gain

        eroe["ts"] = formatta_tiri_salvezza(calcola_tiri_salvezza(eroe["classe"], nuovo_liv))
        eroe["attacco"] = formatta_attacco_stringa(eroe)

        titolo = ottieni_titolo_livello(eroe)
        avanzamenti.append(f"Livello {nuovo_liv} - Titolo: '{titolo}' | {dettaglio_pf}")

    if avanzamenti and not silenzioso:
        suona("levelup")
    return avanzamenti


def gestisci_comando_livello(eroe, avventura, avventure, personaggi):
    """Mostra all'utente la scheda di avanzamento livello, barra PE, anteprima e permette il level up."""
    os.system("clear" if os.name == "posix" else "cls")
    cls = eroe["classe"]
    liv = eroe["livello"]
    titolo = ottieni_titolo_livello(eroe)
    codice_fascia, nome_fascia, desc_fascia = determina_fascia_gioco(eroe)

    print(f"{CIANO}{GRASSETTO}=== PROGRESSIONE LIVELLO BECMI: {eroe['nome'].upper()} ==={RESET}")
    print(f"Classe: {VERDE}{cls}{RESET} | Livello attuale: {VERDE}{liv}{RESET} (Titolo: '{GIALLO}{titolo}{RESET}')")
    print(f"Fascia Regolamento: {GIALLO}{nome_fascia}{RESET}")
    print(f"{DIM}{desc_fascia}{RESET}\n")

    if eroe.get("immortale"):
        rango_imm = eroe.get("rango_immortale", "Temporale")
        liv_imm = eroe.get("livello_immortale", 1)
        pp_att = eroe.get("pp_attuali", 1000)
        pp_max = eroe.get("pp_max", 1000)
        sfera = eroe.get("sfera", "Materia")
        print(f"{MAGENTA}{GRASSETTO}STATUS DIVINO: RANGO IMMORTALE ({rango_imm} Liv.{liv_imm}){RESET}")
        print(f"Sfera di appartenenza: {GIALLO}{sfera}{RESET} | Punti Potere (PP): {VERDE}{pp_att}/{pp_max}{RESET}")
        print(f"I tuoi Tiri Salvezza sono divini (2+) e il tuo THAC0 scende nelle profondità cosmiche ({calcola_thac0(cls, 36, True, liv_imm)}).\n")
    else:
        pe_cur_liv = calcola_soglia_pe(cls, liv)
        pe_next_liv = calcola_soglia_pe(cls, liv + 1)
        pe_att = eroe.get("pe", 0)
        delta = max(1, pe_next_liv - pe_cur_liv)
        guadagnati = max(0, pe_att - pe_cur_liv)
        perc = min(100.0, (guadagnati / delta) * 100.0)
        bar_len = 28
        filled = int(bar_len * (perc / 100.0))
        bar = "█" * filled + "░" * (bar_len - filled)

        print(f"{GIALLO}Punti Esperienza:{RESET} {pe_att:,} PE")
        print(f"Soglia Livello {liv+1}: {pe_next_liv:,} PE (Mancano {max(0, pe_next_liv - pe_att):,} PE)")
        print(f"Avanzamento: [{VERDE}{bar}{RESET}] {perc:.1f}%\n")

        print(f"{CIANO}{GRASSETTO}Statistiche di Livello Attuali:{RESET}")
        dv = DADO_VITA.get(cls, 8)
        dv_str = f"1d{dv}" if liv <= 9 else f"+{PF_FISSI_POST_9.get(cls, 2)} PF fissi"
        print(f"  - Dado Vita: {dv_str} | PF: {eroe['pf_attuali']}/{eroe['pf_max']} | CA: {eroe['ca']}")
        print(f"  - Attacco: {eroe['attacco']}")
        print(f"  - Tiri Salvezza: {eroe['ts']}")
        slot = calcola_slot_incantesimi(cls, liv)
        if slot:
            print(f"  - Slot Incantesimi: {formatta_slot_incantesimi(slot)}")
        if cls == "Ladro":
            print(f"  - Abilità da Ladro: {formatta_abilita_ladro(calcola_abilita_ladro(liv))}")

        print(f"\n{GIALLO}{GRASSETTO}Cosa si sblocca al Livello {liv+1}:{RESET}")
        if liv < 36:
            prossimo_titolo = TITOLI_CLASSI.get(cls, {}).get(liv + 1, f"{cls} di {liv+1}° Liv.")
            print(f"  - Nuovo Titolo: '{prossimo_titolo}'")
            if liv + 1 <= 9:
                mod_cos = mod_caratteristica(eroe['costituzione'])
                print(f"  - Incremento PF: +1d{dv} ({mod_cos:+d} Costituzione, min +1)")
            else:
                pf_f = PF_FISSI_POST_9.get(cls, 2)
                print(f"  - Incremento PF: +{pf_f} PF fissi (regola BECMI senza bonus Costituzione)")
            th_att = calcola_thac0(cls, liv)
            th_nxt = calcola_thac0(cls, liv + 1)
            if th_nxt < th_att:
                print(f"  - {VERDE}Miglioramento THAC0:{RESET} passa da {th_att} a {th_nxt}!")
            ts_att = calcola_tiri_salvezza(cls, liv)
            ts_nxt = calcola_tiri_salvezza(cls, liv + 1)
            migliorie_ts = [k for k in ts_att if ts_nxt[k] < ts_att[k]]
            if migliorie_ts:
                print(f"  - {VERDE}Miglioramento Tiri Salvezza:{RESET} {', '.join(migliorie_ts)}")
            slot_nxt = calcola_slot_incantesimi(cls, liv + 1)
            if len(slot_nxt) > len(slot) or sum(slot_nxt) > sum(slot):
                print(f"  - {MAGENTA}Nuovi Slot Incantesimi:{RESET} {formatta_slot_incantesimi(slot_nxt)}")
            if liv == 3:
                print(f"  - {GIALLO}PASSAGGIO ALLA FASCIA EXPERT!{RESET} Avventure nelle Terre Selvagge e viaggi all'aperto.")
            elif liv == 8:
                print(f"  - {GIALLO}NAME LEVEL (9° LIVELLO)!{RESET} Possibilità di costruire la propria Roccaforte e governare un Dominio.")
            elif liv == 14:
                print(f"  - {GIALLO}PASSAGGIO ALLA FASCIA COMPANION!{RESET} Feudalesimo, battaglie campali War Machine e politica tra nazioni.")
            elif liv == 25:
                print(f"  - {GIALLO}PASSAGGIO ALLA FASCIA MASTER!{RESET} Viaggi planari epici e ricerca dell'Immortalità.")
        else:
            print(f"  - {GIALLO}ASCENSIONE ALL'IMMORTALITÀ!{RESET} Trascendi i 36 livelli mortali ed entra nel Rango Immortale (Scatola Oro)!")

    soglia_prox = calcola_soglia_pe(cls, liv + 1)
    if eroe.get("pe", 0) >= soglia_prox and (liv < 36 or not eroe.get("immortale")):
        print(f"\n{VERDE}{GRASSETTO}" + "*" * 76)
        print("  ⭐ HAI RAGGIUNTO I PE NECESSARI PER IL PASSAGGIO DI LIVELLO! ⭐".center(76))
        print("*" * 76 + f"{RESET}")
        conferma = input(f"\n{VERDE}Vuoi salire di livello adesso? [S/n] > {RESET}").strip().lower()
        if conferma in ["", "s", "si", "y", "yes"]:
            avanzamenti = verifica_e_avanza_livello(eroe, silenzioso=False)
            stampa_banner_levelup(eroe, avanzamenti)
            salva_json(CHARACTERS_FILE, personaggi)
            salva_json(ADVENTURES_FILE, avventure)
            if avanzamenti:
                nota_lvl = f"[AVANZAMENTO REGOLAMENTO: L'eroe è salito di livello tramite /livello! {'; '.join(avanzamenti)}. Nuovi PF: {eroe['pf_attuali']}/{eroe['pf_max']}]."
                avventura["storia"].append({"role": "user", "parts": [{"text": nota_lvl}]})
                avventura["storia"].append({"role": "model", "parts": [{"text": f"Congratulazioni per il passaggio di livello! Le tue statistiche sono aggiornate.\n\nCosa fai?"}]})
                salva_json(ADVENTURES_FILE, avventure)
            input(f"\n{DIM}Premi INVIO per tornare all'avventura...{RESET}")
            return
    else:
        input(f"\n{DIM}Premi INVIO per tornare all'avventura...{RESET}")


def genera_batteria_dadi():
    """Genera tiri reali per giocatore e DM in modo che ogni prova abbia un risultato visibile."""
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

    riga_visibile = (
        f"[TIRI REALI -> Attacco/Prova 1d20: {d20_pg} | TS 1d20: {d20_ts} | "
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


def estrai_testo_pdf(percorso_pdf):
    """Estrae il testo dal PDF usando pdftotext (poppler-utils) o pypdf se disponibile."""
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
        pypdf = importlib.import_module("pypdf")
        reader = pypdf.PdfReader(percorso_pdf)
        pagine = [p.extract_text() or "" for p in reader.pages]
        testo = "\n".join(pagine).strip()
        if testo:
            return testo
    except Exception:
        pass
    return ""


def prepara_contenuto_modulo(percorso_pdf):
    """Restituisce (testo_estratto, pdf_base64) per il modulo PDF scelto."""
    testo = estrai_testo_pdf(percorso_pdf)
    if len(testo) >= 400:
        # Limite prudenziale per mantenere veloci tutti i turni
        return testo[:180000], None
    # Se il PDF e' scansionato (solo immagini) e sotto i 18 MB, usiamo inlineData base64
    if os.path.getsize(percorso_pdf) <= 18 * 1024 * 1024:
        with open(percorso_pdf, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return "", b64
    return testo, None


def elenca_moduli_pdf():
    os.makedirs(MODULI_DIR, exist_ok=True)
    files = sorted([
        f for f in os.listdir(MODULI_DIR)
        if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(MODULI_DIR, f))
    ])
    return files


def normalizza_avventura(chiave, item):
    if not isinstance(item, dict):
        item = {}
    adv_id = item.get("id") or str(chiave)
    eroe = item.get("eroe") or item.get("personaggio") or item.get("character") or "Valen di Corvobianco"
    titolo = item.get("titolo") or item.get("title") or "Avventura Salvata"
    data = item.get("data") or item.get("date") or datetime.now().strftime("%d/%m/%Y %H:%M")
    storia = item.get("storia") if isinstance(item.get("storia"), list) else []
    note = item.get("note") if isinstance(item.get("note"), str) else ""
    modulo_pdf = item.get("modulo_pdf", "")
    modulo_testo = item.get("modulo_testo", "")
    item["id"] = adv_id
    item["eroe"] = eroe
    item["titolo"] = titolo
    item["data"] = data
    item["storia"] = storia
    item["note"] = note
    item["modulo_pdf"] = modulo_pdf
    item["modulo_testo"] = modulo_testo
    return adv_id, item


def normalizza_personaggio(chiave, item):
    if not isinstance(item, dict):
        item = {}
    nome = item.get("nome") or item.get("name") or str(chiave)
    classe_raw = item.get("classe", "Guerriero")

    # Riconoscimento classe su CLASSI_BASE o fallback su Guerriero
    base_match = None
    for k, v in CLASSI_BASE.items():
        if v["classe"].lower() == str(classe_raw).lower():
            base_match = v
            break
    if not base_match:
        base_match = CLASSI_BASE["1"]

    classe = base_match["classe"]
    item["nome"] = nome
    item["classe"] = classe
    item.setdefault("livello", 1)
    item.setdefault("allineamento", base_match.get("allineamento", "Legale"))

    for k_car in ["forza", "intelligenza", "saggezza", "destrezza", "costituzione", "carisma"]:
        if k_car not in item:
            sotto_k = k_car[:3].upper()
            if isinstance(item.get("caratteristiche"), dict) and sotto_k in item["caratteristiche"]:
                item[k_car] = item["caratteristiche"][sotto_k]
            else:
                item[k_car] = base_match[k_car]

    item.setdefault("mo", base_match.get("mo", 15))
    item.setdefault("pe", 0)

    dv = DADO_VITA.get(classe, 8)
    pf_base = max(1, dv + mod_caratteristica(item["costituzione"]))
    item.setdefault("pf_max", pf_base)
    item.setdefault("pf_attuali", item["pf_max"])
    item.setdefault("ca", base_match["ca_base"] - mod_caratteristica(item["destrezza"]))

    immortale = item.get("immortale", False)
    item["ts"] = formatta_tiri_salvezza(calcola_tiri_salvezza(classe, item["livello"], immortale))
    item["attacco"] = formatta_attacco_stringa(item)

    if not isinstance(item.get("equip"), list):
        item["equip"] = list(base_match["equip"])

    return nome, item


def carica_json(percorso, default, tipo_dati=None):
    if os.path.exists(percorso):
        try:
            with open(percorso, "r", encoding="utf-8") as f:
                dati = json.load(f)
            if isinstance(default, dict):
                convertito = {}
                iterabile = dati.items() if isinstance(dati, dict) else [(f"item_{i}", x) for i, x in enumerate(dati, 1)] if isinstance(dati, list) else []
                for k, v in iterabile:
                    if tipo_dati == "avventure":
                        nk, nv = normalizza_avventura(k, v)
                        convertito[nk] = nv
                    elif tipo_dati == "personaggi":
                        nk, nv = normalizza_personaggio(k, v)
                        convertito[nk] = nv
                    else:
                        convertito[k] = v
                return convertito
            return dati
        except Exception:
            return default
    return default


def salva_json(percorso, dati):
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)


def migra_vecchi_salvataggi():
    os.makedirs(MODULI_DIR, exist_ok=True)
    avventure = carica_json(ADVENTURES_FILE, {}, tipo_dati="avventure")
    personaggi = carica_json(CHARACTERS_FILE, {}, tipo_dati="personaggi")

    if not personaggi:
        _, eroe_default = normalizza_personaggio("Valen di Corvobianco", {})
        personaggi["Valen di Corvobianco"] = eroe_default

    for adv in avventure.values():
        nome_eroe = adv.get("eroe", "Valen di Corvobianco")
        if nome_eroe not in personaggi:
            _, nuovo_p = normalizza_personaggio(nome_eroe, {})
            personaggi[nome_eroe] = nuovo_p

    if os.path.exists(LEGACY_SAVE) and not avventure:
        vecchia_storia = carica_json(LEGACY_SAVE, [])
        if vecchia_storia:
            note = ""
            if os.path.exists(LEGACY_DIARY):
                with open(LEGACY_DIARY, "r", encoding="utf-8") as f:
                    note = f.read()
            avventure["adv_1"] = {
                "id": "adv_1",
                "titolo": "La Cripta Dimenticata",
                "eroe": "Valen di Corvobianco",
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "storia": vecchia_storia,
                "note": note
            }

    salva_json(CHARACTERS_FILE, personaggi)
    if avventure:
        salva_json(ADVENTURES_FILE, avventure)
    return avventure, personaggi


def costruisci_system_prompt(eroe, avventura=None):
    equip_str = ", ".join(eroe["equip"])
    blocco_modulo = ""
    if avventura:
        mod_nome = avventura.get("modulo_pdf", "")
        mod_testo = avventura.get("modulo_testo", "")
        if mod_nome or mod_testo:
            blocco_modulo = (
                f"\nMODULO UFFICIALE CARICATO ({mod_nome}): "
                "DEVI condurre l'avventura seguendo fedelmente stanze numerate, trappole, mostri, tesori, PNG e trama del modulo seguente. "
                "ANTI-SPOILER ASSOLUTO: NON rivelare mai al giocatore il contenuto di stanze non ancora esplorate, porte segrete non trovate o trappole non scoperte!\n"
            )
            if mod_testo:
                blocco_modulo += f"--- TESTO DEL MODULO ---\n{mod_testo}\n--- FINE MODULO ---\n"

    codice_fascia, nome_fascia, desc_fascia = determina_fascia_gioco(eroe)
    titolo_eroe = ottieni_titolo_livello(eroe)
    soglia_prossimo = calcola_soglia_pe(eroe["classe"], eroe["livello"] + 1)

    extra_classe = ""
    slot = calcola_slot_incantesimi(eroe["classe"], eroe["livello"])
    if slot:
        extra_classe += f" Slot Incantesimi disponibili: {formatta_slot_incantesimi(slot)}."
    if eroe["classe"] == "Ladro":
        abilita_ladro = formatta_abilita_ladro(calcola_abilita_ladro(eroe["livello"]))
        extra_classe += f" Abilità da Ladro: {abilita_ladro}."
    if eroe.get("immortale"):
        rango_imm = eroe.get("rango_immortale", "Temporale")
        liv_imm = eroe.get("livello_immortale", 1)
        pp_att = eroe.get("pp_attuali", 1000)
        pp_max = eroe.get("pp_max", 1000)
        sfera = eroe.get("sfera", "Materia")
        extra_classe += f" Rango Immortale: {rango_imm} (Livello {liv_imm}), Sfera Cosmica: {sfera}, Punti Potere (PP): {pp_att}/{pp_max}."

    if codice_fascia == "immortals":
        istruzioni_fascia = (
            "FASCIA ATTIVA: SET IMMORTALS (Scatola Oro / Immortal Rules - Rango Immortale).\n"
            "Conduci la campagna a livello cosmico e metafisico: il personaggio ha superato i 36 livelli mortali ed è un Immortale. "
            "Gestisci: 1) Conflitti e trame divine tra le 5 Sfere di Potere (Materia, Energia, Tempo, Pensiero ed Entropia). "
            "2) Viaggi dimensionali (Piano Astrale, Etereo, Piani Elementali, Dimensione degli Incubi). "
            "3) Seguaci, sacerdoti e culti mortali che venerano l'Immortale sul Piano Materiale. "
            "4) Spesa di Punti Potere (PP) per alterare la materia, resistere a colpi divini o compiere prodigi. "
            "5) Creature cosmiche, avatar di altri Immortali e minacce all'equilibrio del Multiverso.\n"
        )
    elif codice_fascia == "master":
        istruzioni_fascia = (
            "FASCIA ATTIVA: SET MASTER (Scatola Nera, Livelli 26-36 - Eroi Leggendari).\n"
            "Conduci avventure epiche per eroi al vertice del mondo conosciuto. "
            "Gestisci: 1) Spedizioni nei Piani di Esistenza e varchi dimensionali. "
            "2) Recupero di Artefatti e Manufatti leggendari. "
            "3) Avversari mitologici: draghi vetusti, behemoth, titani e arcidemoni. "
            "4) Il Cammino dell'Immortalità: prepara l'eroe alle supreme prove delle Sfere "
            "(Sentiero della Dinastia, del Modello, dell'Infinito o del Campione) necessarie per trascendere al Rango Immortale.\n"
        )
    elif codice_fascia == "companion":
        istruzioni_fascia = (
            "FASCIA ATTIVA: SET COMPANION (Scatola Celeste, Livelli 15-25 - Feudalesimo e Grandi Battaglie).\n"
            "Conduci una campagna basata su nobiltà, roccaforti, governi e scontri tra eserciti. "
            "Gestisci: 1) Gestione del Dominio e delle Baronie (tassazione, prosperità dei sudditi, guarnigioni, fortificazioni). "
            "2) Grandi battaglie campali e assedi con le regole War Machine (calcola Valore di Battaglia BFR e morale). "
            "3) Intrighi politici e diplomatici tra corti reali, trattati e alleanze. "
            "4) Minacce e guerre che incombono su intere nazioni o sul continente.\n"
        )
    elif codice_fascia == "expert":
        istruzioni_fascia = (
            "FASCIA ATTIVA: SET EXPERT (Scatola Blu, Livelli 4-14 - Terre Selvagge / Wilderness).\n"
            "Conduci una campagna all'aperto nelle Terre Selvagge (Wilderness). "
            "Gestisci: 1) Viaggi su mappa a esagoni (6 miglia/esagono), marcia a piedi e a cavallo. "
            "2) Condizioni atmosferiche (tempeste, gelo, paludi), terreno accidentato e rischio smarrimento (1 su 1d6). "
            "3) Accampamenti notturni e turni di guardia con incontri casuali all'aperto (1 su 1d6). "
            "4) Risorse di caccia, razioni e rifornimenti per la spedizione. "
            "5) Al raggiungimento del 9° livello (Name Level), guida l'eroe verso la costruzione della propria Roccaforte e il titolo nobiliare.\n"
        )
    else:
        istruzioni_fascia = (
            "FASCIA ATTIVA: SET BASE (Scatola Rossa, Livelli 1-3 - Dungeon Crawling Classico).\n"
            "Conduci una classica avventura dungeon crawling claustrofobica e tesa. "
            "Gestisci: 1) Turni da 10 minuti di esplorazione sotterranea (le torce durano 6 turni = 1 ora). "
            "2) Ricerca di trappole con pertica, porte chiuse o bloccate (forzare con 1d6 vs Forza). "
            "3) Ascoltare rumori alle porte (1-2 su 1d6). "
            "4) Controllo incontri casuali ogni 2 turni nei dungeon (1 su 1d6). "
            "5) Reazione iniziale dei mostri su 2d6 e controllo del Morale (2d6) al primo caduto o a metà vita.\n"
        )

    return (
        f"Agisci come un Dungeon Master esperto di Dungeons & Dragons Edizione BECMI / Mentzer in lingua italiana. "
        f"Attualmente stai conducendo la campagna nella fascia: {nome_fascia}.\n"
        f"{istruzioni_fascia}"
        f"SCHEDA PERSONAGGIO: Nome {eroe['nome']}, {eroe['classe']} Livello {eroe['livello']} (Titolo: '{titolo_eroe}'), "
        f"Fascia: {nome_fascia}, Allineamento: {eroe['allineamento']}. "
        f"Forza {eroe['forza']} ({mod_caratteristica(eroe['forza']):+d}), "
        f"Intelligenza {eroe['intelligenza']} ({mod_caratteristica(eroe['intelligenza']):+d}), "
        f"Saggezza {eroe['saggezza']} ({mod_caratteristica(eroe['saggezza']):+d}), "
        f"Destrezza {eroe['destrezza']} ({mod_caratteristica(eroe['destrezza']):+d}), "
        f"Costituzione {eroe['costituzione']} ({mod_caratteristica(eroe['costituzione']):+d}), "
        f"Carisma {eroe['carisma']} ({mod_caratteristica(eroe['carisma']):+d}). "
        f"PF: {eroe['pf_attuali']}/{eroe['pf_max']}, CA: {eroe['ca']}. "
        f"Tiri per colpire: {eroe['attacco']}. Tiri Salvezza: {eroe['ts']}."
        f"{extra_classe} "
        f"Equipaggiamento attuale: {equip_str}. Monete d'Oro: {eroe['mo']}. "
        f"Punti Esperienza (PE): {eroe['pe']} (Soglia prossimo livello: {soglia_prossimo:,} PE).\n"
        "REGOLE OBBLIGATORIE E ASSOLUTE SUI TIRI DI DADO (NON DEROGABILI): "
        "1. REGOLA D'ORO DEI DADI: OGNI SINGOLA situazione, azione incerta, esplorazione, prova o pericolo DEVE mostrare esplicitamente "
        "il lancio dei dadi e il calcolo completo nel testo usando il formato [Tipo Prova: Dado -> risultato +/- mod = Totale vs Soglia -> Esito]. "
        "Esempi obbligatori: "
        "- Attacco: [Attacco: 1d20 -> 14 + 1 (For) = 15 vs CA 6 (serve 14+) -> Colpito!] [Danni: 1d8 -> 6 + 1 = 7 PF] "
        "- Ricerca trappole/porte segrete: [Cercare trappole/porte segrete: 1d6 -> 1 (serve 1) -> Trovato!] "
        "- Ascoltare dietro una porta: [Ascoltare: 1d6 -> 2 (serve 1-2) -> Senti passi!] "
        "- Sfondare/aprire porta bloccata: [Aprire porta: 1d6 -> 2 vs Forza (serve 1-3) -> Aperta!] "
        "- Incontro casuale: [Controllo incontri casuali: 1d6 -> 5 (incontro su 1) -> Nessun incontro] "
        "- Reazione PNG/mostri: [Reazione: 2d6 -> 8 + 0 (Car) = 8 -> Indecisi/Cauti] "
        "- Morale mostri: [Morale: 2d6 -> 9 vs Morale 7 -> I goblin fuggono!] "
        "- Tiro Salvezza: [TS vs Veleno: 1d20 -> 13 vs 12 -> Superato!] "
        "- Abilita da Ladro / scalare / muoversi silenziosamente / nascondersi: [Muoversi silenziosamente: d% -> 24% vs 30% -> Riuscito!] "
        "2. Se il messaggio del giocatore include [TIRI REALI -> ...], DEVI obbligatoriamente usare quei valori reali per le prove del turno, "
        "riportandoli comunque in chiaro tra parentesi quadre [...] nella tua narrazione! "
        "3. NON narrare MAI un combattimento, una ricerca, l'apertura di una porta, un'interazione con un PNG o un pericolo senza mostrare almeno un riquadro [Tiro: ...] nel testo. "
        "4. A 0 PF il personaggio muore (o se Immortale consuma PP). Assegna sempre PE al termine di scontri e tesori recuperati (1 MO recuperata = 1 PE). "
        "5. Chiudi SEMPRE ogni messaggio con una riga vuota, poi questo riquadro aggiornato e la domanda:\n"
        f"[PF: attuali/{eroe['pf_max']} | CA: {eroe['ca']} | Torce: n | Razioni: n | Frecce: n | MO: n | PE: attuali]\nCosa fai?"
        + blocco_modulo
    )


def aggiorna_eroe_da_riquadro(eroe, testo_dm):
    m = re.search(r"\[PF:\s*(-?\d+)/(\d+)\s*\|\s*CA:\s*(-?\d+).*?\|\s*MO:\s*(\d+)\s*\|\s*PE:\s*(\d+)\]", testo_dm)
    avanzamenti = []
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
        avanzamenti = verifica_e_avanza_livello(eroe, silenzioso=False)
    if "20 ->" in testo_dm or "20 naturale" in testo_dm.lower() or "critico" in testo_dm.lower():
        suona("critico")
    return avanzamenti


def mostra_scheda(eroe):
    titolo = ottieni_titolo_livello(eroe)
    _, nome_fascia, _ = determina_fascia_gioco(eroe)
    print(f"{CIANO}{GRASSETTO}=== SCHEDA PERSONAGGIO: {eroe['nome'].upper()} ==={RESET}")
    print(f"Classe: {eroe['classe']} | Livello: {eroe['livello']} ({GIALLO}{titolo}{RESET}) | Allineamento: {eroe['allineamento']}")
    print(f"Fascia Regolamento: {GIALLO}{nome_fascia}{RESET}")
    if eroe.get("immortale"):
        rango = eroe.get("rango_immortale", "Temporale")
        liv_imm = eroe.get("livello_immortale", 1)
        pp_att = eroe.get("pp_attuali", 1000)
        pp_max = eroe.get("pp_max", 1000)
        sfera = eroe.get("sfera", "Materia")
        print(f"Rango Immortale: {MAGENTA}{rango} (Liv.{liv_imm}){RESET} | Sfera Cosmica: {sfera} | Punti Potere (PP): {VERDE}{pp_att}/{pp_max}{RESET}")
    else:
        soglia_prox = calcola_soglia_pe(eroe["classe"], eroe["livello"] + 1)
        print(f"Punti Esperienza (PE): {VERDE}{eroe['pe']:,}{RESET} / {soglia_prox:,} PE (Mancano {max(0, soglia_prox - eroe['pe']):,} PE al Liv.{eroe['livello']+1})")
    print(f"Forza: {eroe['forza']} ({mod_caratteristica(eroe['forza']):+d}) | Intelligenza: {eroe['intelligenza']} ({mod_caratteristica(eroe['intelligenza']):+d}) | Saggezza: {eroe['saggezza']} ({mod_caratteristica(eroe['saggezza']):+d})")
    print(f"Destrezza: {eroe['destrezza']} ({mod_caratteristica(eroe['destrezza']):+d}) | Costituzione: {eroe['costituzione']} ({mod_caratteristica(eroe['costituzione']):+d}) | Carisma: {eroe['carisma']} ({mod_caratteristica(eroe['carisma']):+d})")
    print(f"Punti Ferita: {eroe['pf_attuali']}/{eroe['pf_max']} | Classe Armatura (CA): {eroe['ca']} | Monete d'Oro: {eroe['mo']}")
    print(f"\n{GIALLO}Tiri per Colpire:{RESET} {eroe['attacco']}")
    print(f"{GIALLO}Tiri Salvezza:{RESET} {eroe['ts']}")
    slot = calcola_slot_incantesimi(eroe["classe"], eroe["livello"])
    if slot:
        print(f"{MAGENTA}Slot Incantesimi:{RESET} {formatta_slot_incantesimi(slot)}")
    if eroe["classe"] == "Ladro":
        print(f"{MAGENTA}Abilità da Ladro:{RESET} {formatta_abilita_ladro(calcola_abilita_ladro(eroe['livello']))}")
    print(f"\n{GIALLO}Equipaggiamento e Tesori:{RESET}")
    for item in eroe["equip"]:
        print(f"  - {item}")


def pulisci_schermo(avventura, eroe):
    os.system("clear" if os.name == "posix" else "cls")
    turno = len(avventura["storia"]) // 2
    stato_dadi = f"{VERDE}ON{RESET}" if AUTODADI_ATTIVI else f"{DIM}OFF{RESET}"
    titolo_liv = ottieni_titolo_livello(eroe)
    _, nome_fascia, _ = determina_fascia_gioco(eroe)
    print(f"{ROSSO}{GRASSETTO}=== D&D BECMI ==={RESET} {GIALLO}{avventura['titolo']}{RESET} {DIM}| Eroe: {eroe['nome']} (Liv.{eroe['livello']} '{titolo_liv}') | {nome_fascia} | Turno {turno}{RESET}")
    print(f"{CIANO}Comandi:{RESET} /help | /scheda | /livello | /emporio | /mappa | /d20 | /autodadi ({stato_dadi}) | /stop (menu) | /chiudi")
    print(f"{DIM}" + "-" * 86 + f"{RESET}\n")


def chiama_gemini(storia, api_key, system_prompt, pdf_path=None):
    url_completo = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELLO}:generateContent"

    contents_invio = json.loads(json.dumps(storia))
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
        "contents": contents_invio
    }

    comando_curl = [
        "curl", "-s", "--max-time", "25", "-X", "POST",
        url_completo,
        "-H", "Content-Type: application/json",
        "-H", "x-goog-api-key: " + api_key.strip(),
        "-d", json.dumps(payload)
    ]

    processo = subprocess.run(comando_curl, capture_output=True, text=True)
    risposta_grezza = processo.stdout.strip()

    if not risposta_grezza:
        raise Exception("Timeout o risposta vuota dal server.")

    risultato = json.loads(risposta_grezza)
    if "error" in risultato:
        raise Exception(risultato["error"].get("message", str(risultato["error"])))

    cand = risultato["candidates"][0]
    part = cand["content"]["parts"][0]
    return part["text"]


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
        if riga_pulita.startswith("[PF:"):
            print(f"\n{CIANO}{GRASSETTO}{riga}{RESET}")
        elif riga_pulita == "Cosa fai?":
            print(f"{GIALLO}{GRASSETTO}{riga}{RESET}")
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
                        time.sleep(0.07)
                    elif carattere in ",;:":
                        time.sleep(0.03)
                    else:
                        time.sleep(0.012)
                if dentro_quadra:
                    sys.stdout.write(RESET)
                print()


def crea_personaggio(personaggi):
    os.system("clear" if os.name == "posix" else "cls")
    print(f"{CIANO}{GRASSETTO}=== CREAZIONE NUOVO PERSONAGGIO (D&D BECMI) ==={RESET}\n")
    for k, v in CLASSI_BASE.items():
        print(f"  {VERDE}{GRASSETTO}[{k}]{RESET} {v['classe']:<10} (DV 1d{v['dado_vita']}, CA base {v['ca_base']}, Forza {v['forza']}, Des {v['destrezza']})")

    scelta = input(f"\n{VERDE}Scegli la classe (1-9) > {RESET}").strip()
    if scelta not in CLASSI_BASE:
        scelta = "1"
    base = CLASSI_BASE[scelta]

    nome = input(f"{VERDE}Inserisci il nome del tuo {base['classe']} > {RESET}").strip()
    if not nome:
        nome = f"{base['classe']} Senza Nome"

    default_allin = base.get("allineamento", "Legale")
    allineamento = input(f"{VERDE}Allineamento [L]egale, [N]eutrale, [C]aotico (Invio = {default_allin}) > {RESET}").strip().lower()
    allineamento = {"n": "Neutrale", "c": "Caotico", "l": "Legale"}.get(allineamento, default_allin)

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

    nuovo_eroe = {
        "nome": nome, "classe": base["classe"], "livello": 1, "allineamento": allineamento,
        "forza": forza, "intelligenza": intelligenza, "saggezza": saggezza,
        "destrezza": destrezza, "costituzione": costituzione, "carisma": carisma,
        "pf_attuali": pf_max, "pf_max": pf_max, "ca": ca,
        "equip": list(base["equip"]), "mo": mo, "pe": 0
    }
    nuovo_eroe["ts"] = formatta_tiri_salvezza(calcola_tiri_salvezza(nuovo_eroe["classe"], 1))
    nuovo_eroe["attacco"] = formatta_attacco_stringa(nuovo_eroe)

    personaggi[nome] = nuovo_eroe
    salva_json(CHARACTERS_FILE, personaggi)
    return nuovo_eroe


def crea_nuova_avventura(avventure, personaggi):
    os.system("clear" if os.name == "posix" else "cls")
    print(f"{CIANO}{GRASSETTO}=== NUOVA AVVENTURA ==={RESET}\n")
    print(f"{GIALLO}1. Scegli l'eroe protagonista:{RESET}")
    nomi = list(personaggi.keys())
    for idx, n in enumerate(nomi, 1):
        p = personaggi[n]
        print(f"  {VERDE}[{idx}]{RESET} {p['nome']} ({p['classe']} Liv.{p['livello']} | PF {p['pf_attuali']}/{p['pf_max']} | {p['mo']} MO | {p['pe']} PE)")
    print(f"  {CIANO}[C]{RESET} Crea un nuovo personaggio ora")

    scelta_eroe = input(f"\n{VERDE}Seleziona eroe > {RESET}").strip().lower()
    if scelta_eroe == "c" or not nomi:
        eroe = crea_personaggio(personaggi)
    else:
        try:
            eroe = personaggi[nomi[int(scelta_eroe) - 1]]
        except Exception:
            eroe = personaggi[nomi[0]]

    print(f"\n{GIALLO}2. Scegli lo scenario dell'avventura:{RESET}")
    for k, (tit, _) in SCENARI_AVVENTURA.items():
        print(f"  {VERDE}[{k}]{RESET} {tit}")
    print(f"  {MAGENTA}{GRASSETTO}[M]{RESET} Carica un modulo PDF dalla cartella '{MODULI_DIR}/'")
    print(f"  {CIANO}[P]{RESET} Scenario personalizzato")

    modulo_pdf = ""
    modulo_testo = ""
    titolo, prompt = SCENARI_AVVENTURA["1"]
    scelta_scen = input(f"\n{VERDE}Seleziona scenario > {RESET}").strip().lower()
    if scelta_scen == "m":
        moduli = elenca_moduli_pdf()
        if not moduli:
            print(f"\n{GIALLO}Nessun file .pdf trovato nella cartella '{MODULI_DIR}/'.{RESET}")
            percorso_manuale = input(f"{VERDE}Incolla il percorso completo del file PDF (o INVIO per scenario base) > {RESET}").strip().strip('"').strip("'")
            if percorso_manuale and os.path.isfile(percorso_manuale):
                percorso_scelto = percorso_manuale
            else:
                titolo, prompt = SCENARI_AVVENTURA["1"]
                percorso_scelto = ""
        else:
            print(f"\n{CIANO}Moduli PDF disponibili in '{MODULI_DIR}/':{RESET}")
            for idx, m_file in enumerate(moduli, 1):
                print(f"  {VERDE}[{idx}]{RESET} {m_file}")
            sel_m = input(f"\n{VERDE}Scegli il numero del PDF > {RESET}").strip()
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
            titolo = input(f"{VERDE}Titolo avventura (Invio = '{titolo_default}') > {RESET}").strip() or titolo_default
            prompt = (
                f"Inizia l'avventura ufficiale '{titolo}' basata sul modulo PDF allegato. "
                "Presenta l'introduzione per i giocatori (o la prima area/stanza iniziale) senza anticipare spoiler, "
                "rispettando mostri, incontri e descrizioni del modulo."
            )
    elif scelta_scen in SCENARI_AVVENTURA:
        titolo, prompt = SCENARI_AVVENTURA[scelta_scen]
    else:
        titolo = input(f"{VERDE}Titolo della nuova avventura > {RESET}").strip() or "Spedizione nelle Terre Selvagge"
        prompt = input(f"{VERDE}Descrivi dove inizia l'avventura > {RESET}").strip() or "Inizia l'avventura davanti all'ingresso di un'antica rovina."

    if AUTODADI_ATTIVI:
        batteria = genera_batteria_dadi()
        prompt = f"{prompt}\n{batteria['testo']}"

    adv_id = f"adv_{int(time.time())}"
    nuova_adv = {
        "id": adv_id,
        "titolo": titolo,
        "eroe": eroe["nome"],
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "storia": [{"role": "user", "parts": [{"text": prompt}]}],
        "note": "",
        "modulo_pdf": modulo_pdf,
        "modulo_testo": modulo_testo
    }
    avventure[adv_id] = nuova_adv
    salva_json(ADVENTURES_FILE, avventure)
    return nuova_adv


def menu_principale(avventure, personaggi):
    while True:
        os.system("clear" if os.name == "posix" else "cls")
        print(LOGO_INTRO)
        print(f"{DIM}" + "=" * 86 + f"{RESET}\n")

        lista_adv = list(avventure.values())
        if lista_adv:
            print(f"{GIALLO}{GRASSETTO}Avventure in corso (digita il numero per riprendere):{RESET}")
            for idx, adv in enumerate(lista_adv, 1):
                turni = len(adv.get("storia", [])) // 2
                titolo = adv.get("titolo", "Avventura Salvata")
                eroe_nome = adv.get("eroe", "Valen di Corvobianco")
                data_adv = adv.get("data", "")
                print(f"  {VERDE}{GRASSETTO}[{idx}]{RESET} {titolo} — {CIANO}{eroe_nome}{RESET} {DIM}({turni} turni | {data_adv}){RESET}")
            print()

        print(f"  {VERDE}{GRASSETTO}[N]{RESET} Inizia una Nuova Avventura (scegli eroe esistente o creane uno nuovo)")
        print(f"  {CIANO}{GRASSETTO}[C]{RESET} Crea solo un Nuovo Personaggio")
        print(f"  {GIALLO}{GRASSETTO}[E]{RESET} Elimina un'avventura salvata")
        print(f"  {ROSSO}{GRASSETTO}[Q]{RESET} Chiudi ed esci dal programma\n")

        scelta = input(f"{VERDE}{GRASSETTO}Scelta > {RESET}").strip().lower()
        if scelta == "q":
            return None
        elif scelta == "n":
            return crea_nuova_avventura(avventure, personaggi)
        elif scelta == "c":
            eroe = crea_personaggio(personaggi)
            print(f"\n{VERDE}Personaggio {eroe['nome']} creato e salvato!{RESET}")
            time.sleep(1.2)
        elif scelta == "e" and lista_adv:
            num = input(f"{ROSSO}Numero dell'avventura da eliminare > {RESET}").strip()
            try:
                adv_da_rimuovere = lista_adv[int(num) - 1]
                del avventure[adv_da_rimuovere["id"]]
                salva_json(ADVENTURES_FILE, avventure)
                print(f"{GIALLO}Avventura eliminata.{RESET}")
                time.sleep(1)
            except Exception:
                pass
        else:
            try:
                idx = int(scelta) - 1
                if 0 <= idx < len(lista_adv):
                    return lista_adv[idx]
            except ValueError:
                pass


def apri_emporio(eroe, avventura):
    os.system("clear" if os.name == "posix" else "cls")
    print(f"{GIALLO}{GRASSETTO}=== EMPORIO DELLE TERRE DI CONFINE ==={RESET}")
    print(f"Eroe: {CIANO}{eroe['nome']}{RESET} | Borsello attuale: {VERDE}{GRASSETTO}{eroe['mo']} MO{RESET}\n")
    for codice, nome_item, costo, _, _ in EMPORIO_ITEMS:
        print(f"  {VERDE}[{codice:>2}]{RESET} {nome_item:<42} {GIALLO}{costo:>3} MO{RESET}")
    print(f"\n  {DIM}[0] Torna all'avventura{RESET}")

    acquisti_fatti = []
    while True:
        scelta = input(f"\n{VERDE}Numero articolo da acquistare (0 per uscire) > {RESET}").strip()
        if scelta == "0" or not scelta:
            break
        trovato = next((item for item in EMPORIO_ITEMS if item[0] == scelta), None)
        if not trovato:
            print("Articolo non valido.")
            continue
        _, nome_item, costo, tipo, label_equip = trovato
        if eroe["mo"] < costo:
            print(f"{ROSSO}Monete d'oro insufficienti! Hai solo {eroe['mo']} MO.{RESET}")
            continue
        eroe["mo"] -= costo
        eroe["equip"].append(label_equip)
        if tipo == "scudo":
            eroe["ca"] -= 1
        elif tipo == "armatura_3":
            eroe["ca"] = 3 - mod_caratteristica(eroe["destrezza"])
        acquisti_fatti.append(label_equip)
        suona("tesoro")
        print(f"{VERDE}Acquistato: {label_equip}! Rimangono {eroe['mo']} MO.{RESET}")

    if acquisti_fatti:
        nota_acquisto = f"Ho visitato l'emporio e acquistato: {', '.join(acquisti_fatti)}. Ora ho {eroe['mo']} MO e CA {eroe['ca']}."
        avventura["storia"].append({"role": "user", "parts": [{"text": nota_acquisto}]})
        avventura["storia"].append({"role": "model", "parts": [{"text": f"Ho annotato i tuoi nuovi acquisti nell'inventario ({', '.join(acquisti_fatti)}). Borsello aggiornato a {eroe['mo']} MO.\n\nCosa fai?"}]})


def aggiorna_manuale_eroe(eroe):
    os.system("clear" if os.name == "posix" else "cls")
    mostra_scheda(eroe)
    print(f"\n{GIALLO}=== AGGIORNAMENTO RAPIDO SCHEDA ==={RESET}")
    print("Premi INVIO per lasciare invariato un campo.")
    liv = input(f"Livello attuale ({eroe['livello']}): ").strip()
    if liv.isdigit():
        eroe["livello"] = int(liv)
        eroe["ts"] = formatta_tiri_salvezza(calcola_tiri_salvezza(eroe["classe"], eroe["livello"], eroe.get("immortale", False)))
        eroe["attacco"] = formatta_attacco_stringa(eroe)
    pe_in = input(f"Punti Esperienza ({eroe['pe']}): ").strip()
    if pe_in.isdigit():
        eroe["pe"] = int(pe_in)
        verifica_e_avanza_livello(eroe, silenzioso=False)
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
    print(f"\n{VERDE}Scheda aggiornata e salvata!{RESET}")
    time.sleep(1)


def genera_mappa_ascii(avventura, api_key, eroe):
    print(f"{CIANO}Disegno della mappa delle aree esplorate in corso...{RESET}")
    # Manteniamo gli ultimi 14 messaggi per evitare payload troppo grandi o timeout, estraendo solo il testo
    storia_recente = []
    for msg in avventura.get("storia", [])[-14:]:
        ruolo = "GIOCATORE" if msg.get("role") == "user" else "DUNGEON MASTER"
        testo = msg.get("parts", [{}])[0].get("text", "")
        # Rimuoviamo la riga tecnica dei tiri reali per non confondere il cartografo
        righe_pulite = [r for r in testo.split("\n") if "TIRI REALI ->" not in r]
        storia_recente.append(f"{ruolo}: " + "\n".join(righe_pulite))

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
        "  @     posizione attuale dell'eroe (" + eroe["nome"] + ")\n"
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
    # Rimuove eventuali backtick markdown se il modello li inserisce comunque
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


def comprimi_memoria(avventura, api_key, system_prompt):
    print(f"{GIALLO}Compressione della memoria in corso...{RESET}")
    richiesta = list(avventura["storia"])
    richiesta.append({
        "role": "user",
        "parts": [{"text": "Fai un riassunto completo ma sintetico di tutto cio che e accaduto finora nell'avventura: stanze esplorate, nemici sconfitti, alleati, ferite, inventario, MO e PE."}]
    })
    riassunto = chiama_gemini(richiesta, api_key, system_prompt)
    avventura["storia"] = [
        {"role": "user", "parts": [{"text": "Riassunto dell'avventura finora: " + riassunto}]},
        {"role": "model", "parts": [{"text": "Ho memorizzato tutto il progresso. Riprendiamo da dove eravamo rimasti.\n\nCosa fai?"}]}
    ]
    print(f"{VERDE}Memoria compressa con successo!{RESET}\n")
    print(riassunto)


def mostra_ultimo_turno_con_dadi(avventura):
    storia = avventura.get("storia", [])
    if not storia:
        return
    if len(storia) >= 2 and storia[-2]["role"] == "user":
        testo_u = storia[-2]["parts"][0]["text"]
        righe_dadi = [r for r in testo_u.split("\n") if "TIRI REALI" in r or "Dado locale" in r]
        if righe_dadi:
            print(f"{GIALLO}{GRASSETTO}{righe_dadi[-1]}{RESET}\n")
    ultimo = storia[-1]
    formatta_risposta(ultimo["parts"][0]["text"], animato=False)


def esegui_sessione(avventura, avventure, personaggi, api_key):
    global SUONI_ATTIVI, AUTODADI_ATTIVI
    nome_eroe = avventura.get("eroe", "Valen di Corvobianco")
    if nome_eroe not in personaggi:
        _, nuovo_p = normalizza_personaggio(nome_eroe, {})
        personaggi[nome_eroe] = nuovo_p
    eroe = personaggi[nome_eroe]
    pulisci_schermo(avventura, eroe)

    if len(avventura["storia"]) <= 1:
        if not avventura["storia"]:
            prompt_init = SCENARI_AVVENTURA["1"][1]
            if AUTODADI_ATTIVI:
                prompt_init = f"{prompt_init}\n{genera_batteria_dadi()['testo']}"
            avventura["storia"] = [{"role": "user", "parts": [{"text": prompt_init}]}]
        print(f"{DIM}Generazione della scena iniziale e lancio dei dadi...{RESET}")
        try:
            pdf_attivo = avventura.get('modulo_pdf') if not avventura.get('modulo_testo') else None
            testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroe, avventura), pdf_path=pdf_attivo)
            avventura["storia"].append({"role": "model", "parts": [{"text": testo_dm}]})
            avventura["data"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            avanzamenti = aggiorna_eroe_da_riquadro(eroe, testo_dm)
            salva_json(ADVENTURES_FILE, avventure)
            salva_json(CHARACTERS_FILE, personaggi)
            pulisci_schermo(avventura, eroe)
            if avanzamenti:
                stampa_banner_levelup(eroe, avanzamenti)
            mostra_ultimo_turno_con_dadi(avventura)
        except Exception as e:
            print(f"{ROSSO}Errore:{RESET}\n", e)
            input("\nPremi INVIO per tornare al menu...")
            return "menu"
    else:
        mostra_ultimo_turno_con_dadi(avventura)

    while True:
        try:
            azione = input(f"\n{VERDE}{GRASSETTO}> {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            salva_json(ADVENTURES_FILE, avventure)
            salva_json(CHARACTERS_FILE, personaggi)
            return "chiudi"

        if not azione:
            continue

        cmd = azione.lower()
        if cmd in ["/chiudi", "/esci", "/quit", "/exit"]:
            avventura["data"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            salva_json(ADVENTURES_FILE, avventure)
            salva_json(CHARACTERS_FILE, personaggi)
            print(f"\n{VERDE}Avventura e personaggio salvati. Chiusura del programma in corso...{RESET}")
            return "chiudi"

        if cmd in ["/stop", "/interrompi", "/avventure", "/menu", "/cambia"]:
            avventura["data"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            salva_json(ADVENTURES_FILE, avventure)
            salva_json(CHARACTERS_FILE, personaggi)
            print(f"\n{GIALLO}Avventura interrotta e salvata. Ritorno al menu principale...{RESET}")
            time.sleep(0.6)
            return "menu"

        if cmd in ["/help", "/aiuto", "/?"]:
            pulisci_schermo(avventura, eroe)
            print(HELP_TESTO)
            print(f"{DIM}--- Situazione attuale ---{RESET}\n")
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd in ["/scheda", "/inventario"]:
            pulisci_schermo(avventura, eroe)
            mostra_scheda(eroe)
            print(f"\n{DIM}--- Situazione attuale ---{RESET}\n")
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd == "/livello":
            gestisci_comando_livello(eroe, avventura, avventure, personaggi)
            pulisci_schermo(avventura, eroe)
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd in ["/emporio", "/negozio"]:
            apri_emporio(eroe, avventura)
            salva_json(ADVENTURES_FILE, avventure)
            salva_json(CHARACTERS_FILE, personaggi)
            pulisci_schermo(avventura, eroe)
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd == "/aggiorna":
            aggiorna_manuale_eroe(eroe)
            salva_json(CHARACTERS_FILE, personaggi)
            pulisci_schermo(avventura, eroe)
            mostra_ultimo_turno_con_dadi(avventura)
            continue
            mostra_ultimo_turno_con_dadi(avventura)
            continue

        if cmd == "/autodadi":
            AUTODADI_ATTIVI = not AUTODADI_ATTIVI
            stato = "ATTIVATI (tiri reali completi ad ogni turno)" if AUTODADI_ATTIVI else "DISATTIVATI (tira solo il DM o /d20)"
            print(f"{GIALLO}Autodadi {stato}.{RESET}")
            continue

        if cmd == "/mappa":
            try:
                mappa = genera_mappa_ascii(avventura, api_key, eroe)
                pulisci_schermo(avventura, eroe)
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
            pulisci_schermo(avventura, eroe)
            print(f"{GIALLO}=== ULTIMI 3 TURNI ==={RESET}\n")
            for msg in avventura["storia"][-6:]:
                ruolo = f"{VERDE}TU:{RESET}" if msg["role"] == "user" else f"{CIANO}DM:{RESET}"
                print(f"{ruolo} {msg['parts'][0]['text']}\n")
            continue

        if cmd.startswith("/nota"):
            testo_nota = azione[5:].strip()
            if testo_nota:
                avventura["note"] = avventura.get("note", "") + f"- {testo_nota}\n"
                salva_json(ADVENTURES_FILE, avventure)
                print(f"{GIALLO}Appunto salvato nel diario di questa avventura.{RESET}")
            elif avventura.get("note"):
                print(f"\n{GIALLO}=== DIARIO: {avventura['titolo'].upper()} ==={RESET}\n{avventura['note']}")
            else:
                print("Nessun appunto salvato. Usa: /nota <testo da ricordare>")
            continue

        if cmd == "/riassunto":
            try:
                comprimi_memoria(avventura, api_key, costruisci_system_prompt(eroe, avventura))
                salva_json(ADVENTURES_FILE, avventure)
            except Exception as e:
                print(f"{ROSSO}Errore durante il riassunto:{RESET}", e)
            continue

        testo_mostrato = azione
        testo_inviato = azione

        if cmd.startswith("/") and re.match(r"^/\d*d\d+", cmd):
            tiro = tira_dado(azione)
            if tiro:
                testo_mostrato = tiro
                testo_inviato = f"Ho tirato fisicamente il dado: {tiro}. Usa questo risultato e mostra il calcolo tra parentesi quadre."
            else:
                print("Formato dado non valido. Esempi: /d20, /d8+1, /2d6")
                continue
        elif AUTODADI_ATTIVI:
            batteria = genera_batteria_dadi()
            if batteria["d20"] == 20:
                suona("critico")
            elif batteria["d20"] == 1:
                suona("danno")
            testo_mostrato = f"{azione}\n{GIALLO}{GRASSETTO}{batteria['testo']}{RESET}"
            testo_inviato = f"{azione}\n{batteria['testo']}"

        avventura["storia"].append({"role": "user", "parts": [{"text": testo_inviato}]})
        print(f"\n{GIALLO}{GRASSETTO}{testo_mostrato}{RESET}")
        print(f"{DIM}Il Dungeon Master sta risolvendo i tiri e valutando la scena...{RESET}")
        try:
            pdf_attivo = avventura.get('modulo_pdf') if not avventura.get('modulo_testo') else None
            testo_dm = chiama_gemini(avventura["storia"], api_key, costruisci_system_prompt(eroe, avventura), pdf_path=pdf_attivo)
            avventura["storia"].append({"role": "model", "parts": [{"text": testo_dm}]})
            avventura["data"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            avanzamenti = aggiorna_eroe_da_riquadro(eroe, testo_dm)
            salva_json(ADVENTURES_FILE, avventure)
            salva_json(CHARACTERS_FILE, personaggi)
            pulisci_schermo(avventura, eroe)
            if avanzamenti:
                stampa_banner_levelup(eroe, avanzamenti)
            print(f"{DIM}> {testo_mostrato}{RESET}\n")
            formatta_risposta(testo_dm, animato=True)
        except Exception as e:
            print(f"{ROSSO}Errore:{RESET}\n", e)
            avventura["storia"].pop()


def main():
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    else:
        api_key = os.environ.get("GEMINI_API_KEY", "")

    if not api_key:
        print("Uso: python3 dnd.py LA_TUA_CHIAVE_API")
        return

    avventure, personaggi = migra_vecchi_salvataggi()

    while True:
        avventura_scelta = menu_principale(avventure, personaggi)
        if not avventura_scelta:
            print(f"\n{GIALLO}Arrivederci, avventuriero! Tutti i progressi sono stati salvati.{RESET}")
            break
        esito = esegui_sessione(avventura_scelta, avventure, personaggi, api_key)
        if esito == "chiudi":
            break


if __name__ == "__main__":
    main()
