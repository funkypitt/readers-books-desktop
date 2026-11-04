#!/usr/bin/env python3
"""Reader's Books — a shelf as a plain list; books as pages of text cut at whole lines.

The desktop twin of the Android app: the same shelf, the same reader (EPUB, MOBI, FB2, TXT; the
place in each book kept), the same magazine contents, the same optional library on a drive (a
WebDAV address), the same highlights, the same credentials file. One file, PyQt5 — and
paper2epub.py next to it, which turns a paper in PDF into an EPUB.
"""
import json
import locale
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import threading
import uuid
import time
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha1, sha256
from urllib.parse import quote, unquote, urljoin, urlparse

import requests
from PyQt5 import QtCore, QtGui, QtWidgets

APP = "readers-books"
VERSION = "1.18.1"
AGENT = "Readers-Books/%s (+https://gallaz.ch/apps)" % VERSION


def _app_dirs():
    if sys.platform == "win32":
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Readers Books")
        return base, base
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/" + APP)
        return base, base
    return (os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), APP),
            os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), APP))


CONFIG_DIR, DATA_DIR = _app_dirs()
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LIBRARY_FILE = os.path.join(DATA_DIR, "library.json")
BOOKS_DIR = os.path.join(DATA_DIR, "books")
INDEX_FILE = os.path.join(DATA_DIR, "library-index.json")
KINDS_FILE = os.path.join(DATA_DIR, "library-kinds.json")     # which books of the library are newspapers or magazines
KINDS_VERSION = 2       # 2: gatherings of articles count too, and issues carry their own date
FOLLOW_FILE = os.path.join(DATA_DIR, "follow.json")
HIGHLIGHTS_DIR = os.path.join(DATA_DIR, "highlights")

# ------------------------------------------------------------------------------------------
# Six languages, the English text as the key — the same wording as the phone
# ------------------------------------------------------------------------------------------

STRINGS = {
 "fr": {
  "follow this folder": "suivre ce dossier",
  "stop following this folder": "ne plus suivre ce dossier",
  "its new books one click away, at the top of the library": "ses nouveaux livres à un clic, en haut de la bibliothèque",
  "looking for new books…": "recherche des nouveautés…",
  "fetching %d of %d…": "téléchargement %d sur %d…",
  "nothing new · %s": "rien de nouveau · %s",
  "followed folder · click to fetch what is new": "dossier suivi · cliquez pour chercher les nouveautés",
  "issues on this computer": "numéros sur cet ordinateur",
  "the whole folder on the drive": "tout le dossier sur le drive",
  "no issue of this folder is on this computer yet": "aucun numéro de ce dossier n'est encore sur cet ordinateur",
  "on this computer": "sur cet ordinateur",
  "continue reading": "reprendre la lecture",
  "set up a library": "configurer une bibliothèque",
  "your books on your drive, on all your devices": "vos livres sur votre drive, sur tous vos appareils",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Give the WebDAV address of the drive with a username and an application password (kDrive, Nextcloud, any WebDAV server). The drive is then scanned for epub, mobi, azw and fb2 files. Highlights and the page you are at are written next to each book, so the login must be allowed to write there.": "Des livres gardés sur un drive, listés par dossier ; un livre n'est téléchargé que lorsqu'on clique dessus. Donnez l'adresse WebDAV du drive avec un nom d'utilisateur et un mot de passe d'application (kDrive, Nextcloud, tout serveur WebDAV). Le drive est alors parcouru à la recherche de fichiers epub, mobi, azw et fb2. Les surlignages et la page où vous êtes sont écrits à côté de chaque livre : le compte doit pouvoir y écrire.",
  "Highlights: in any book, drag across a passage to highlight it, with a comment if you like; a click on a highlight shows its comment. In a book from the library they are kept next to the book on the drive, with the page you are at, and follow it to your other devices; in a book opened from this computer they stay on this computer, and go to the library with the book if it is added to it. The book's menu exports them. With the WebDAV address of the Reader's Notes folder given below, a note per book lists its highlights in Reader's Notes.": "Surlignages : dans n'importe quel livre, glissez sur un passage pour le surligner, avec un commentaire si vous le voulez ; un clic sur un surlignage montre son commentaire. Dans un livre de la bibliothèque, ils sont gardés à côté du livre sur le drive, avec la page où vous êtes, et le suivent sur vos autres appareils ; dans un livre ouvert depuis cet ordinateur, ils restent sur cet ordinateur, et vont à la bibliothèque avec le livre s'il y est ajouté. Le menu du livre les exporte. Avec l'adresse WebDAV du dossier de Reader's Notes donnée ci-dessous, une note par livre reprend ses surlignages dans Reader's Notes.",
  "highlight": "surligner",
  "comment": "commenter",
  "add a comment": "ajouter un commentaire",
  "edit the comment": "modifier le commentaire",
  "remove the highlight": "retirer le surlignage",
  "copy": "copier",
  "export the highlights": "exporter les surlignages",
  "highlights": "surlignages",
  "Reader's Notes folder": "dossier de Reader's Notes",
  "same as the library": "comme la bibliothèque",
  "username for the notes": "nom d'utilisateur pour les notes",
  "password for the notes": "mot de passe pour les notes",
  "yesterday": "hier",
  "this file could not be read": "ce fichier n'a pas pu être lu",
  "+ open a book": "+ ouvrir un livre",
  "library": "bibliothèque",
  "black on white": "noir sur blanc",
  "white on black": "blanc sur noir",
  "lavender": "lavande",
  "sage": "sauge",
  "nordic": "nordique",
  "terracotta": "terracotta",
  "coquette": "coquette",
  "activist": "militante",
  "sultry": "torride",
  "nature": "nature",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file: from here, or by dropping it on this window.": "rien sur l'étagère. Ouvrir un fichier epub, mobi, fb2 ou texte : d'ici, ou en le déposant sur cette fenêtre.",
  "not started": "pas commencé",
  "read": "lire",
  "contents": "sommaire",
  "chapters": "chapitres",
  "remove from the shelf": "retirer de l'étagère",
  "settings": "réglages",
  "books": "livres",
  "larger text": "texte plus grand",
  "smaller text": "texte plus petit",
  "book text": "texte des livres",
  "serif": "à empattements",
  "sans-serif": "sans empattements",
  "mono": "chasse fixe",
  "colours": "couleurs",
  "reading size — click for larger": "taille de lecture — cliquer pour agrandir",
  "automatic size": "taille automatique",
  "the size the app starts with": "la taille de départ de l'application",
  "font": "police",
  "size of the shelf and menus": "taille de l'étagère et des menus",
  "on": "oui",
  "off": "non",
  "keep the screen on while reading": "garder l'écran allumé en lisant",
  "forget the library": "oublier la bibliothèque",
  "removes the link, the login and the list of books; the shelf is kept": "retire le lien, l'identifiant et la liste des livres ; l'étagère est gardée",
  "reads epub, mobi, fb2 and txt files": "lit les fichiers epub, mobi, fb2 et txt",
  "Pierre Gallaz · developed with Claude Code": "Pierre Gallaz · développé avec Claude Code",
  "WebDAV address": "adresse WebDAV",
  "username": "nom d'utilisateur",
  "password": "mot de passe",
  "cancel": "annuler",
  "export credentials": "exporter les identifiants",
  "a file to set up another device — it holds the password": "un fichier pour configurer un autre appareil — il contient le mot de passe",
  "import credentials": "importer les identifiants",
  "Reader's credentials": "Identifiants Reader's",
  "credentials exported — the file holds the password: keep it private": "identifiants exportés — le fichier contient le mot de passe : gardez-le privé",
  "drive and login taken from another Reader's app": "drive et identifiants repris d'une autre app Reader's",
  "credentials imported": "identifiants importés",
  "not a Reader's credentials file": "ce n'est pas un fichier d'identifiants Reader's",
  "this file holds nothing for %s": "ce fichier ne contient rien pour %s",
  "the file cannot be read: %s": "le fichier est illisible : %s",
  "scanning… %d folders, %d books": "parcours en cours… %d dossiers, %d livres",
  "the drive refused the login": "le drive a refusé l'identification",
  "the drive could not be read: %s": "le drive n'a pas pu être lu : %s",
  "continue the scan": "poursuivre le parcours",
  "the scan stopped after %d folders · %d books so far": "le parcours s'est arrêté après %d dossiers · %d livres jusqu'ici",
  "%d folders could not be read": "%d dossiers n'ont pas pu être lus",
  "no e-book found on the drive (epub, mobi, azw, fb2)": "aucun livre numérique trouvé sur le drive (epub, mobi, azw, fb2)",
  "all books": "tous les livres",
  "on the drive": "sur le drive",
  "news": "actualités",
  "latest %s": "dernier : %s",
  "looking for more… %d/%d": "recherche en cours… %d/%d",
  "the newest first": "les plus récents d'abord",
  "search": "rechercher",
  "title, author or folder": "titre, auteur ou dossier",
  "no book matches": "aucun livre ne correspond",
  "search again": "rechercher encore",
  "top of the drive": "racine du drive",
  "scanned on %s": "parcouru le %s",
  "stop the scan": "arrêter le parcours",
  "scan the drive again": "parcourir le drive à nouveau",
  "sync now": "synchroniser maintenant",
  "folders of the library": "dossiers de la bibliothèque",
  "The whole drive is in the library. Choose folders to keep only those, with everything inside them: the library is then synced faster. Right-click a folder to leave it out: it is then neither shown nor synced, whatever else is chosen. The transcriptions of Reader's Podcasts stay unless left out.": "Tout le drive est dans la bibliothèque. Choisissez des dossiers pour ne garder que ceux-là, avec tout ce qu'ils contiennent : la bibliothèque se synchronise alors plus vite. Un clic droit sur un dossier l'écarte : il n'est alors ni affiché ni synchronisé, quel que soit le reste du choix. Les transcriptions de Reader's Podcasts restent, sauf si elles sont écartées.",
  "the whole drive": "tout le drive",
  "in %s": "dans %s",
  "left out": "écarté",
  "leave this folder out": "écarter ce dossier",
  "take this folder back in": "reprendre ce dossier",
  "keep only some folders?": "ne garder que certains dossiers ?",
  "%d folders hold books — choose the ones for the library, or leave the whole drive": "%d dossiers contiennent des livres — choisissez ceux de la bibliothèque, ou gardez tout le drive",
  "by name": "par nom",
  "newest first": "les plus récents d'abord",
  "oldest first": "les plus anciens d'abord",
  "by author": "par auteur",
  "last opened first": "les derniers ouverts d'abord",
  "order": "ordre",
  "group by top folder": "regrouper par dossier principal",
  "every folder": "chaque dossier",
  "with subfolders": "avec les sous-dossiers",
  "this folder only": "ce dossier seulement",
  "most books first": "les plus fournis d'abord",
  "by title": "par titre",
  "last added first": "les derniers ajoutés d'abord",
  "downloading…": "téléchargement…",
  "on the shelf": "sur l'étagère",
  "opened %s": "ouvert %s",
  "the book could not be fetched: %s": "le livre n'a pas pu être récupéré : %s",
  "add to the library": "ajouter à la bibliothèque",
  "The book is copied to the drive, into the folder you choose, and becomes a book of the library: its highlights and the page you are at are then kept next to it and follow it to your other devices. Nothing on the drive is written over.": "Le livre est copié sur le drive, dans le dossier que vous choisissez, et devient un livre de la bibliothèque : ses surlignages et la page où vous en êtes sont alors gardés à côté de lui et le suivent sur vos autres appareils. Rien n'est écrasé sur le drive.",
  "sending…": "envoi…",
  "“%s” is now in the library, in %s.": "« %s » est maintenant dans la bibliothèque, dans %s.",
  "the book could not be sent: %s": "le livre n'a pas pu être envoyé : %s",
  "last time": "la dernière fois",
  "setting up the converter…": "mise en place du convertisseur…",
  "the converter could not be set up: %s": "le convertisseur n'a pas pu être mis en place : %s",
  "the PDF “%s” is being turned into an EPUB…": "le PDF « %s » est converti en EPUB…",
  "loading the models": "chargement des modèles",
  "reading the pages": "lecture des pages",
  "making the EPUB": "fabrication de l'EPUB",
  "the PDF “%s” could not be turned into an EPUB: %s": "le PDF « %s » n'a pas pu être converti en EPUB : %s",
  "A PDF is not read as it is: it is turned into an EPUB, a book of the shelf, its figures, tables and equations as pictures; the PDF itself is left as it was. The converter is set up once: about 2 GB downloaded.": "Un PDF ne se lit pas tel quel : il est converti en EPUB, un livre de l'étagère, ses figures, tableaux et équations en images ; le PDF lui-même reste tel qu'il était. Le convertisseur se met en place une fois : environ 2 Go téléchargés.",
  "set up the converter": "mettre en place le convertisseur",
  "reading the scanned pages": "lecture des pages scannées",
  "“%s” is a scan: its pages are pictures. To get its text, install Tesseract (the tesseract-ocr package) and open the PDF again.": "« %s » est un scan : ses pages sont des images. Pour en avoir le texte, installez Tesseract (le paquet tesseract-ocr) et rouvrez le PDF.",
  "books, or a PDF to turn into an EPUB": "livres, ou un PDF à convertir en EPUB",
  "a PDF, turned into an EPUB": "un PDF, converti en EPUB",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file, or a PDF to turn into an EPUB: from here, or by dropping it on this window.": "rien sur l'étagère. Ouvrir un fichier epub, mobi, fb2 ou texte, ou un PDF à convertir en EPUB : d'ici, ou en le déposant sur cette fenêtre.",
 },
 "de": {
  "follow this folder": "diesem Ordner folgen",
  "stop following this folder": "diesem Ordner nicht mehr folgen",
  "its new books one click away, at the top of the library": "seine neuen Bücher mit einem Klick, oben in der Bibliothek",
  "looking for new books…": "suche nach neuen Büchern…",
  "fetching %d of %d…": "lade %d von %d…",
  "nothing new · %s": "nichts Neues · %s",
  "followed folder · click to fetch what is new": "gefolgter Ordner · klicken, um Neues zu holen",
  "issues on this computer": "Ausgaben auf diesem Computer",
  "the whole folder on the drive": "der ganze Ordner auf dem Drive",
  "no issue of this folder is on this computer yet": "noch keine Ausgabe dieses Ordners auf diesem Computer",
  "on this computer": "auf diesem Computer",
  "continue reading": "weiterlesen",
  "set up a library": "eine Bibliothek einrichten",
  "your books on your drive, on all your devices": "Ihre Bücher auf Ihrem Drive, auf all Ihren Geräten",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Give the WebDAV address of the drive with a username and an application password (kDrive, Nextcloud, any WebDAV server). The drive is then scanned for epub, mobi, azw and fb2 files. Highlights and the page you are at are written next to each book, so the login must be allowed to write there.": "Bücher auf einem Drive, nach Ordnern aufgelistet; ein Buch wird erst heruntergeladen, wenn Sie es anklicken. Geben Sie die WebDAV-Adresse des Drives mit Benutzername und Anwendungspasswort an (kDrive, Nextcloud, jeder WebDAV-Server). Das Drive wird dann nach epub-, mobi-, azw- und fb2-Dateien durchsucht. Markierungen und die Seite, auf der Sie sind, werden neben jedes Buch geschrieben: das Konto muss dort schreiben dürfen.",
  "Highlights: in any book, drag across a passage to highlight it, with a comment if you like; a click on a highlight shows its comment. In a book from the library they are kept next to the book on the drive, with the page you are at, and follow it to your other devices; in a book opened from this computer they stay on this computer, and go to the library with the book if it is added to it. The book's menu exports them. With the WebDAV address of the Reader's Notes folder given below, a note per book lists its highlights in Reader's Notes.": "Markierungen: Ziehen Sie in einem beliebigen Buch über eine Stelle, um sie zu markieren, auf Wunsch mit Kommentar; ein Klick auf eine Markierung zeigt ihren Kommentar. In einem Buch aus der Bibliothek liegen sie neben dem Buch auf dem Drive, mit der Seite, auf der Sie sind, und folgen ihm auf Ihre anderen Geräte; in einem Buch, das von diesem Computer geöffnet wurde, bleiben sie auf diesem Computer und gehen mit dem Buch in die Bibliothek, wenn es ihr hinzugefügt wird. Das Menü des Buchs exportiert sie. Mit der unten angegebenen WebDAV-Adresse des Ordners von Reader's Notes führt eine Notiz pro Buch seine Markierungen in Reader's Notes auf.",
  "highlight": "markieren",
  "comment": "kommentieren",
  "add a comment": "Kommentar hinzufügen",
  "edit the comment": "Kommentar ändern",
  "remove the highlight": "Markierung entfernen",
  "copy": "kopieren",
  "export the highlights": "Markierungen exportieren",
  "highlights": "Markierungen",
  "Reader's Notes folder": "Ordner von Reader's Notes",
  "same as the library": "wie die Bibliothek",
  "username for the notes": "Benutzername für die Notizen",
  "password for the notes": "Passwort für die Notizen",
  "yesterday": "gestern",
  "this file could not be read": "diese Datei konnte nicht gelesen werden",
  "+ open a book": "+ ein Buch öffnen",
  "library": "Bibliothek",
  "black on white": "Schwarz auf Weiß",
  "white on black": "Weiß auf Schwarz",
  "lavender": "Lavendel",
  "sage": "Salbei",
  "nordic": "nordisch",
  "terracotta": "Terrakotta",
  "coquette": "kokett",
  "activist": "kämpferisch",
  "sultry": "glühend",
  "nature": "Natur",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file: from here, or by dropping it on this window.": "nichts im Regal. Eine epub-, mobi-, fb2- oder Textdatei öffnen: von hier oder durch Ablegen auf diesem Fenster.",
  "not started": "nicht begonnen",
  "read": "lesen",
  "contents": "Inhalt",
  "chapters": "Kapitel",
  "remove from the shelf": "aus dem Regal nehmen",
  "settings": "Einstellungen",
  "books": "Bücher",
  "larger text": "größerer Text",
  "smaller text": "kleinerer Text",
  "book text": "Buchtext",
  "serif": "mit Serifen",
  "sans-serif": "serifenlos",
  "mono": "Festbreite",
  "colours": "Farben",
  "%d · auto": "%d · automatisch",
  "reading size — click for larger": "Lesegröße — klicken für größer",
  "automatic size": "automatische Größe",
  "the size the app starts with": "die Größe, mit der die App beginnt",
  "font": "Schrift",
  "size of the shelf and menus": "Größe von Regal und Menüs",
  "on": "an",
  "off": "aus",
  "keep the screen on while reading": "Bildschirm beim Lesen anlassen",
  "forget the library": "Bibliothek vergessen",
  "removes the link, the login and the list of books; the shelf is kept": "entfernt Link, Anmeldung und Bücherliste; das Regal bleibt",
  "reads epub, mobi, fb2 and txt files": "liest epub-, mobi-, fb2- und txt-Dateien",
  "Pierre Gallaz · developed with Claude Code": "Pierre Gallaz · entwickelt mit Claude Code",
  "WebDAV address": "WebDAV-Adresse",
  "username": "Benutzername",
  "password": "Passwort",
  "cancel": "abbrechen",
  "export credentials": "Zugangsdaten exportieren",
  "a file to set up another device — it holds the password": "eine Datei, um ein anderes Gerät einzurichten — sie enthält das Passwort",
  "import credentials": "Zugangsdaten importieren",
  "Reader's credentials": "Reader's-Zugangsdaten",
  "credentials exported — the file holds the password: keep it private": "Zugangsdaten exportiert — die Datei enthält das Passwort: halten Sie sie privat",
  "drive and login taken from another Reader's app": "Drive und Anmeldung aus einer anderen Reader's-App übernommen",
  "credentials imported": "Zugangsdaten importiert",
  "not a Reader's credentials file": "keine Reader's-Zugangsdatendatei",
  "this file holds nothing for %s": "diese Datei enthält nichts für %s",
  "the file cannot be read: %s": "die Datei ist nicht lesbar: %s",
  "scanning… %d folders, %d books": "Suche läuft… %d Ordner, %d Bücher",
  "the drive refused the login": "das Drive hat die Anmeldung abgelehnt",
  "the drive could not be read: %s": "das Drive konnte nicht gelesen werden: %s",
  "continue the scan": "Suche fortsetzen",
  "the scan stopped after %d folders · %d books so far": "die Suche ist nach %d Ordnern stehen geblieben · bisher %d Bücher",
  "%d folders could not be read": "%d Ordner konnten nicht gelesen werden",
  "no e-book found on the drive (epub, mobi, azw, fb2)": "kein E-Book auf dem Drive gefunden (epub, mobi, azw, fb2)",
  "all books": "alle Bücher",
  "on the drive": "auf dem Laufwerk",
  "news": "Nachrichten",
  "latest %s": "neueste: %s",
  "looking for more… %d/%d": "Suche läuft… %d/%d",
  "the newest first": "die neuesten zuerst",
  "search": "suchen",
  "title, author or folder": "Titel, Autor oder Ordner",
  "no book matches": "kein Buch passt dazu",
  "search again": "erneut suchen",
  "top of the drive": "Wurzel des Drives",
  "scanned on %s": "durchsucht am %s",
  "stop the scan": "Suche anhalten",
  "scan the drive again": "Drive erneut durchsuchen",
  "sync now": "jetzt synchronisieren",
  "folders of the library": "Ordner der Bibliothek",
  "The whole drive is in the library. Choose folders to keep only those, with everything inside them: the library is then synced faster. Right-click a folder to leave it out: it is then neither shown nor synced, whatever else is chosen. The transcriptions of Reader's Podcasts stay unless left out.": "Das ganze Drive ist in der Bibliothek. Wählen Sie Ordner, um nur diese zu behalten, mit allem darin: die Bibliothek wird dann schneller synchronisiert. Ein Rechtsklick auf einen Ordner schließt ihn aus: er wird dann weder angezeigt noch synchronisiert, was auch sonst gewählt ist. Die Transkriptionen von Reader's Podcasts bleiben, außer sie sind ausgeschlossen.",
  "the whole drive": "das ganze Drive",
  "in %s": "in %s",
  "left out": "ausgeschlossen",
  "leave this folder out": "diesen Ordner ausschließen",
  "take this folder back in": "diesen Ordner wieder aufnehmen",
  "keep only some folders?": "nur einige Ordner behalten?",
  "%d folders hold books — choose the ones for the library, or leave the whole drive": "%d Ordner enthalten Bücher — wählen Sie die der Bibliothek, oder behalten Sie das ganze Drive",
  "by name": "nach Name",
  "newest first": "neueste zuerst",
  "oldest first": "älteste zuerst",
  "by author": "nach Autor",
  "last opened first": "zuletzt geöffnete zuerst",
  "order": "Reihenfolge",
  "group by top folder": "nach oberstem Ordner gruppieren",
  "every folder": "jeder Ordner",
  "with subfolders": "mit Unterordnern",
  "this folder only": "nur dieser Ordner",
  "most books first": "die meisten Bücher zuerst",
  "by title": "nach Titel",
  "last added first": "zuletzt hinzugefügte zuerst",
  "downloading…": "wird heruntergeladen…",
  "on the shelf": "im Regal",
  "opened %s": "geöffnet %s",
  "the book could not be fetched: %s": "das Buch konnte nicht geholt werden: %s",
  "add to the library": "zur Bibliothek hinzufügen",
  "The book is copied to the drive, into the folder you choose, and becomes a book of the library: its highlights and the page you are at are then kept next to it and follow it to your other devices. Nothing on the drive is written over.": "Das Buch wird in den gewählten Ordner des Drives kopiert und wird ein Buch der Bibliothek: seine Markierungen und die Seite, auf der Sie sind, werden dann neben ihm abgelegt und folgen ihm auf Ihre anderen Geräte. Nichts auf dem Drive wird überschrieben.",
  "sending…": "wird gesendet…",
  "“%s” is now in the library, in %s.": "„%s“ ist jetzt in der Bibliothek, in %s.",
  "the book could not be sent: %s": "das Buch konnte nicht gesendet werden: %s",
  "last time": "letztes Mal",
  "setting up the converter…": "Konverter wird eingerichtet…",
  "the converter could not be set up: %s": "der Konverter konnte nicht eingerichtet werden: %s",
  "the PDF “%s” is being turned into an EPUB…": "das PDF „%s“ wird in EPUB umgewandelt…",
  "loading the models": "Modelle werden geladen",
  "reading the pages": "Seiten werden gelesen",
  "making the EPUB": "EPUB wird erstellt",
  "the PDF “%s” could not be turned into an EPUB: %s": "das PDF „%s“ konnte nicht in EPUB umgewandelt werden: %s",
  "A PDF is not read as it is: it is turned into an EPUB, a book of the shelf, its figures, tables and equations as pictures; the PDF itself is left as it was. The converter is set up once: about 2 GB downloaded.": "Ein PDF wird nicht so gelesen, wie es ist: es wird in ein EPUB umgewandelt, ein Buch im Regal, seine Abbildungen, Tabellen und Gleichungen als Bilder; das PDF selbst bleibt unverändert. Der Konverter wird einmal eingerichtet: etwa 2 GB werden heruntergeladen.",
  "set up the converter": "Konverter einrichten",
  "reading the scanned pages": "gescannte Seiten werden gelesen",
  "“%s” is a scan: its pages are pictures. To get its text, install Tesseract (the tesseract-ocr package) and open the PDF again.": "„%s“ ist ein Scan: seine Seiten sind Bilder. Um den Text zu erhalten, installieren Sie Tesseract (das Paket tesseract-ocr) und öffnen Sie das PDF erneut.",
  "books, or a PDF to turn into an EPUB": "Bücher, oder ein PDF zum Umwandeln in EPUB",
  "a PDF, turned into an EPUB": "ein PDF, in EPUB umgewandelt",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file, or a PDF to turn into an EPUB: from here, or by dropping it on this window.": "nichts im Regal. Eine epub-, mobi-, fb2- oder Textdatei öffnen, oder ein PDF zum Umwandeln in EPUB: von hier oder durch Ablegen auf diesem Fenster.",
 },
 "es": {
  "follow this folder": "seguir esta carpeta",
  "stop following this folder": "dejar de seguir esta carpeta",
  "its new books one click away, at the top of the library": "sus libros nuevos a un clic, arriba en la biblioteca",
  "looking for new books…": "buscando libros nuevos…",
  "fetching %d of %d…": "descargando %d de %d…",
  "nothing new · %s": "nada nuevo · %s",
  "followed folder · click to fetch what is new": "carpeta seguida · haga clic para traer lo nuevo",
  "issues on this computer": "números en este ordenador",
  "the whole folder on the drive": "toda la carpeta en el drive",
  "no issue of this folder is on this computer yet": "todavía no hay ningún número de esta carpeta en este ordenador",
  "on this computer": "en este ordenador",
  "continue reading": "seguir leyendo",
  "set up a library": "configurar una biblioteca",
  "your books on your drive, on all your devices": "tus libros en tu drive, en todos tus dispositivos",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Give the WebDAV address of the drive with a username and an application password (kDrive, Nextcloud, any WebDAV server). The drive is then scanned for epub, mobi, azw and fb2 files. Highlights and the page you are at are written next to each book, so the login must be allowed to write there.": "Libros guardados en un drive, listados por carpeta; un libro solo se descarga cuando haces clic en él. Indica la dirección WebDAV del drive con un nombre de usuario y una contraseña de aplicación (kDrive, Nextcloud, cualquier servidor WebDAV). Entonces se recorre el drive buscando archivos epub, mobi, azw y fb2. Los resaltados y la página en la que estás se escriben junto a cada libro: la cuenta debe poder escribir allí.",
  "Highlights: in any book, drag across a passage to highlight it, with a comment if you like; a click on a highlight shows its comment. In a book from the library they are kept next to the book on the drive, with the page you are at, and follow it to your other devices; in a book opened from this computer they stay on this computer, and go to the library with the book if it is added to it. The book's menu exports them. With the WebDAV address of the Reader's Notes folder given below, a note per book lists its highlights in Reader's Notes.": "Resaltados: en cualquier libro, arrastra sobre un pasaje para resaltarlo, con un comentario si quieres; un clic en un resaltado muestra su comentario. En un libro de la biblioteca se guardan junto al libro en el drive, con la página en la que estás, y lo siguen en tus otros dispositivos; en un libro abierto desde este ordenador se quedan en este ordenador, y van a la biblioteca con el libro si se añade a ella. El menú del libro los exporta. Con la dirección WebDAV de la carpeta de Reader's Notes indicada abajo, una nota por libro recoge sus resaltados en Reader's Notes.",
  "highlight": "resaltar",
  "comment": "comentar",
  "add a comment": "añadir un comentario",
  "edit the comment": "editar el comentario",
  "remove the highlight": "quitar el resaltado",
  "copy": "copiar",
  "export the highlights": "exportar los resaltados",
  "highlights": "resaltados",
  "Reader's Notes folder": "carpeta de Reader's Notes",
  "same as the library": "como la biblioteca",
  "username for the notes": "usuario para las notas",
  "password for the notes": "contraseña para las notas",
  "yesterday": "ayer",
  "this file could not be read": "no se pudo leer este archivo",
  "+ open a book": "+ abrir un libro",
  "library": "biblioteca",
  "black on white": "negro sobre blanco",
  "white on black": "blanco sobre negro",
  "lavender": "lavanda",
  "sage": "salvia",
  "nordic": "nórdico",
  "terracotta": "terracota",
  "coquette": "coqueta",
  "activist": "militante",
  "sultry": "tórrido",
  "nature": "naturaleza",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file: from here, or by dropping it on this window.": "nada en la estantería. Abre un archivo epub, mobi, fb2 o de texto: desde aquí, o soltándolo sobre esta ventana.",
  "not started": "sin empezar",
  "read": "leer",
  "contents": "sumario",
  "chapters": "capítulos",
  "remove from the shelf": "quitar de la estantería",
  "settings": "ajustes",
  "books": "libros",
  "larger text": "texto más grande",
  "smaller text": "texto más pequeño",
  "book text": "texto de los libros",
  "serif": "con serifa",
  "sans-serif": "sin serifa",
  "mono": "monoespaciada",
  "colours": "colores",
  "%d · auto": "%d · automático",
  "reading size — click for larger": "tamaño de lectura — haz clic para agrandar",
  "automatic size": "tamaño automático",
  "the size the app starts with": "el tamaño con el que empieza la aplicación",
  "font": "fuente",
  "size of the shelf and menus": "tamaño de la estantería y los menús",
  "on": "sí",
  "off": "no",
  "keep the screen on while reading": "mantener la pantalla encendida al leer",
  "forget the library": "olvidar la biblioteca",
  "removes the link, the login and the list of books; the shelf is kept": "quita el enlace, el usuario y la lista de libros; la estantería se conserva",
  "reads epub, mobi, fb2 and txt files": "lee archivos epub, mobi, fb2 y txt",
  "Pierre Gallaz · developed with Claude Code": "Pierre Gallaz · desarrollado con Claude Code",
  "WebDAV address": "dirección WebDAV",
  "username": "nombre de usuario",
  "password": "contraseña",
  "cancel": "cancelar",
  "export credentials": "exportar credenciales",
  "a file to set up another device — it holds the password": "un archivo para configurar otro dispositivo — contiene la contraseña",
  "import credentials": "importar credenciales",
  "Reader's credentials": "Credenciales Reader's",
  "credentials exported — the file holds the password: keep it private": "credenciales exportadas — el archivo contiene la contraseña: mantenlo privado",
  "drive and login taken from another Reader's app": "drive y usuario tomados de otra app Reader's",
  "credentials imported": "credenciales importadas",
  "not a Reader's credentials file": "no es un archivo de credenciales Reader's",
  "this file holds nothing for %s": "este archivo no contiene nada para %s",
  "the file cannot be read: %s": "no se puede leer el archivo: %s",
  "scanning… %d folders, %d books": "recorriendo… %d carpetas, %d libros",
  "the drive refused the login": "el drive rechazó el inicio de sesión",
  "the drive could not be read: %s": "no se pudo leer el drive: %s",
  "continue the scan": "continuar el recorrido",
  "the scan stopped after %d folders · %d books so far": "el recorrido se detuvo tras %d carpetas · %d libros hasta ahora",
  "%d folders could not be read": "%d carpetas no se pudieron leer",
  "no e-book found on the drive (epub, mobi, azw, fb2)": "no se encontró ningún libro electrónico en el drive (epub, mobi, azw, fb2)",
  "all books": "todos los libros",
  "on the drive": "en el disco",
  "news": "noticias",
  "latest %s": "último: %s",
  "looking for more… %d/%d": "buscando más… %d/%d",
  "the newest first": "los más recientes primero",
  "search": "buscar",
  "title, author or folder": "título, autor o carpeta",
  "no book matches": "ningún libro coincide",
  "search again": "buscar de nuevo",
  "top of the drive": "raíz del drive",
  "scanned on %s": "recorrido el %s",
  "stop the scan": "detener el recorrido",
  "scan the drive again": "recorrer el drive de nuevo",
  "sync now": "sincronizar ahora",
  "folders of the library": "carpetas de la biblioteca",
  "The whole drive is in the library. Choose folders to keep only those, with everything inside them: the library is then synced faster. Right-click a folder to leave it out: it is then neither shown nor synced, whatever else is chosen. The transcriptions of Reader's Podcasts stay unless left out.": "Todo el drive está en la biblioteca. Elija carpetas para quedarse solo con esas, con todo lo que contienen: la biblioteca se sincroniza entonces más rápido. Un clic derecho en una carpeta la deja fuera: entonces ni se muestra ni se sincroniza, sea cual sea el resto de la elección. Las transcripciones de Reader's Podcasts se quedan, salvo si se dejan fuera.",
  "the whole drive": "todo el drive",
  "in %s": "en %s",
  "left out": "dejada fuera",
  "leave this folder out": "dejar fuera esta carpeta",
  "take this folder back in": "volver a incluir esta carpeta",
  "keep only some folders?": "¿quedarse solo con algunas carpetas?",
  "%d folders hold books — choose the ones for the library, or leave the whole drive": "%d carpetas contienen libros — elija las de la biblioteca, o deje todo el drive",
  "by name": "por nombre",
  "newest first": "los más recientes primero",
  "oldest first": "los más antiguos primero",
  "by author": "por autor",
  "last opened first": "los últimos abiertos primero",
  "order": "orden",
  "group by top folder": "agrupar por carpeta principal",
  "every folder": "cada carpeta",
  "with subfolders": "con las subcarpetas",
  "this folder only": "solo esta carpeta",
  "most books first": "las que tienen más libros primero",
  "by title": "por título",
  "last added first": "los últimos añadidos primero",
  "downloading…": "descargando…",
  "on the shelf": "en la estantería",
  "opened %s": "abierto %s",
  "the book could not be fetched: %s": "no se pudo obtener el libro: %s",
  "add to the library": "añadir a la biblioteca",
  "The book is copied to the drive, into the folder you choose, and becomes a book of the library: its highlights and the page you are at are then kept next to it and follow it to your other devices. Nothing on the drive is written over.": "El libro se copia al drive, en la carpeta que elija, y pasa a ser un libro de la biblioteca: sus resaltados y la página en la que está se guardan entonces junto a él y le siguen a sus otros dispositivos. Nada del drive se sobrescribe.",
  "sending…": "enviando…",
  "“%s” is now in the library, in %s.": "«%s» está ahora en la biblioteca, en %s.",
  "the book could not be sent: %s": "no se pudo enviar el libro: %s",
  "last time": "la última vez",
  "setting up the converter…": "preparando el conversor…",
  "the converter could not be set up: %s": "no se pudo preparar el conversor: %s",
  "the PDF “%s” is being turned into an EPUB…": "el PDF «%s» se está convirtiendo en EPUB…",
  "loading the models": "cargando los modelos",
  "reading the pages": "leyendo las páginas",
  "making the EPUB": "haciendo el EPUB",
  "the PDF “%s” could not be turned into an EPUB: %s": "el PDF «%s» no pudo convertirse en EPUB: %s",
  "A PDF is not read as it is: it is turned into an EPUB, a book of the shelf, its figures, tables and equations as pictures; the PDF itself is left as it was. The converter is set up once: about 2 GB downloaded.": "Un PDF no se lee tal cual: se convierte en un EPUB, un libro de la estantería, con sus figuras, tablas y ecuaciones como imágenes; el PDF en sí queda como estaba. El conversor se prepara una sola vez: unos 2 GB descargados.",
  "set up the converter": "preparar el conversor",
  "reading the scanned pages": "leyendo las páginas escaneadas",
  "“%s” is a scan: its pages are pictures. To get its text, install Tesseract (the tesseract-ocr package) and open the PDF again.": "«%s» es un escaneo: sus páginas son imágenes. Para obtener su texto, instala Tesseract (el paquete tesseract-ocr) y vuelve a abrir el PDF.",
  "books, or a PDF to turn into an EPUB": "libros, o un PDF para convertir en EPUB",
  "a PDF, turned into an EPUB": "un PDF, convertido en EPUB",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file, or a PDF to turn into an EPUB: from here, or by dropping it on this window.": "nada en la estantería. Abre un archivo epub, mobi, fb2 o de texto, o un PDF para convertir en EPUB: desde aquí, o soltándolo sobre esta ventana.",
 },
 "pt": {
  "follow this folder": "seguir esta pasta",
  "stop following this folder": "deixar de seguir esta pasta",
  "its new books one click away, at the top of the library": "os seus livros novos a um clique, no topo da biblioteca",
  "looking for new books…": "procurando livros novos…",
  "fetching %d of %d…": "baixando %d de %d…",
  "nothing new · %s": "nada de novo · %s",
  "followed folder · click to fetch what is new": "pasta seguida · clique para trazer o que é novo",
  "issues on this computer": "edições neste computador",
  "the whole folder on the drive": "a pasta inteira no drive",
  "no issue of this folder is on this computer yet": "ainda não há nenhuma edição desta pasta neste computador",
  "on this computer": "neste computador",
  "continue reading": "continuar a ler",
  "set up a library": "configurar uma biblioteca",
  "your books on your drive, on all your devices": "os seus livros na sua drive, em todos os seus aparelhos",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Give the WebDAV address of the drive with a username and an application password (kDrive, Nextcloud, any WebDAV server). The drive is then scanned for epub, mobi, azw and fb2 files. Highlights and the page you are at are written next to each book, so the login must be allowed to write there.": "Livros guardados numa drive, listados por pasta; um livro só é descarregado quando clica nele. Indique o endereço WebDAV da drive com um nome de utilizador e uma palavra-passe de aplicação (kDrive, Nextcloud, qualquer servidor WebDAV). A drive é então percorrida à procura de ficheiros epub, mobi, azw e fb2. Os destaques e a página em que está são escritos ao lado de cada livro: a conta tem de poder escrever aí.",
  "Highlights: in any book, drag across a passage to highlight it, with a comment if you like; a click on a highlight shows its comment. In a book from the library they are kept next to the book on the drive, with the page you are at, and follow it to your other devices; in a book opened from this computer they stay on this computer, and go to the library with the book if it is added to it. The book's menu exports them. With the WebDAV address of the Reader's Notes folder given below, a note per book lists its highlights in Reader's Notes.": "Destaques: em qualquer livro, arraste sobre uma passagem para a destacar, com um comentário se quiser; um clique num destaque mostra o seu comentário. Num livro da biblioteca ficam ao lado do livro na drive, com a página em que está, e acompanham-no nos seus outros aparelhos; num livro aberto a partir deste computador ficam neste computador, e vão para a biblioteca com o livro se ele lhe for adicionado. O menu do livro exporta-os. Com o endereço WebDAV da pasta do Reader's Notes indicado abaixo, uma nota por livro reúne os seus destaques no Reader's Notes.",
  "highlight": "destacar",
  "comment": "comentar",
  "add a comment": "adicionar um comentário",
  "edit the comment": "editar o comentário",
  "remove the highlight": "retirar o destaque",
  "copy": "copiar",
  "export the highlights": "exportar os destaques",
  "highlights": "destaques",
  "Reader's Notes folder": "pasta do Reader's Notes",
  "same as the library": "como a biblioteca",
  "username for the notes": "utilizador para as notas",
  "password for the notes": "palavra-passe para as notas",
  "yesterday": "ontem",
  "this file could not be read": "não foi possível ler este ficheiro",
  "+ open a book": "+ abrir um livro",
  "library": "biblioteca",
  "black on white": "preto sobre branco",
  "white on black": "branco sobre preto",
  "lavender": "lavanda",
  "sage": "sálvia",
  "nordic": "nórdico",
  "terracotta": "terracota",
  "coquette": "coquete",
  "activist": "militante",
  "sultry": "tórrido",
  "nature": "natureza",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file: from here, or by dropping it on this window.": "nada na estante. Abra um ficheiro epub, mobi, fb2 ou de texto: daqui, ou largando-o sobre esta janela.",
  "not started": "por começar",
  "read": "ler",
  "contents": "sumário",
  "chapters": "capítulos",
  "remove from the shelf": "retirar da estante",
  "settings": "definições",
  "books": "livros",
  "larger text": "texto maior",
  "smaller text": "texto menor",
  "book text": "texto dos livros",
  "serif": "com serifa",
  "sans-serif": "sem serifa",
  "mono": "monoespaçada",
  "colours": "cores",
  "%d · auto": "%d · automático",
  "reading size — click for larger": "tamanho de leitura — clique para aumentar",
  "automatic size": "tamanho automático",
  "the size the app starts with": "o tamanho com que a aplicação começa",
  "font": "letra",
  "size of the shelf and menus": "tamanho da estante e dos menus",
  "on": "sim",
  "off": "não",
  "keep the screen on while reading": "manter o ecrã ligado ao ler",
  "forget the library": "esquecer a biblioteca",
  "removes the link, the login and the list of books; the shelf is kept": "remove a ligação, o utilizador e a lista de livros; a estante mantém-se",
  "reads epub, mobi, fb2 and txt files": "lê ficheiros epub, mobi, fb2 e txt",
  "Pierre Gallaz · developed with Claude Code": "Pierre Gallaz · desenvolvido com Claude Code",
  "WebDAV address": "endereço WebDAV",
  "username": "nome de utilizador",
  "password": "palavra-passe",
  "cancel": "cancelar",
  "export credentials": "exportar credenciais",
  "a file to set up another device — it holds the password": "um ficheiro para configurar outro aparelho — contém a palavra-passe",
  "import credentials": "importar credenciais",
  "Reader's credentials": "Credenciais Reader's",
  "credentials exported — the file holds the password: keep it private": "credenciais exportadas — o ficheiro contém a palavra-passe: mantenha-o privado",
  "drive and login taken from another Reader's app": "drive e utilizador retirados de outra app Reader's",
  "credentials imported": "credenciais importadas",
  "not a Reader's credentials file": "não é um ficheiro de credenciais Reader's",
  "this file holds nothing for %s": "este ficheiro não contém nada para %s",
  "the file cannot be read: %s": "não é possível ler o ficheiro: %s",
  "scanning… %d folders, %d books": "a percorrer… %d pastas, %d livros",
  "the drive refused the login": "a drive recusou o início de sessão",
  "the drive could not be read: %s": "não foi possível ler a drive: %s",
  "continue the scan": "continuar o percurso",
  "the scan stopped after %d folders · %d books so far": "o percurso parou após %d pastas · %d livros até agora",
  "%d folders could not be read": "%d pastas não puderam ser lidas",
  "no e-book found on the drive (epub, mobi, azw, fb2)": "nenhum livro eletrónico encontrado na drive (epub, mobi, azw, fb2)",
  "all books": "todos os livros",
  "on the drive": "no disco",
  "news": "notícias",
  "latest %s": "último: %s",
  "looking for more… %d/%d": "procurando mais… %d/%d",
  "the newest first": "os mais recentes primeiro",
  "search": "pesquisar",
  "title, author or folder": "título, autor ou pasta",
  "no book matches": "nenhum livro corresponde",
  "search again": "pesquisar de novo",
  "top of the drive": "raiz da drive",
  "scanned on %s": "percorrida a %s",
  "stop the scan": "parar o percurso",
  "scan the drive again": "percorrer a drive de novo",
  "sync now": "sincronizar agora",
  "folders of the library": "pastas da biblioteca",
  "The whole drive is in the library. Choose folders to keep only those, with everything inside them: the library is then synced faster. Right-click a folder to leave it out: it is then neither shown nor synced, whatever else is chosen. The transcriptions of Reader's Podcasts stay unless left out.": "Toda a drive está na biblioteca. Escolha pastas para ficar só com essas, com tudo o que contêm: a biblioteca sincroniza-se então mais depressa. Um clique direito numa pasta deixa-a de fora: deixa então de ser mostrada e sincronizada, seja qual for o resto da escolha. As transcrições do Reader's Podcasts ficam, salvo se deixadas de fora.",
  "the whole drive": "toda a drive",
  "in %s": "em %s",
  "left out": "deixada de fora",
  "leave this folder out": "deixar esta pasta de fora",
  "take this folder back in": "voltar a incluir esta pasta",
  "keep only some folders?": "ficar só com algumas pastas?",
  "%d folders hold books — choose the ones for the library, or leave the whole drive": "%d pastas contêm livros — escolha as da biblioteca, ou deixe toda a drive",
  "by name": "por nome",
  "newest first": "mais recentes primeiro",
  "oldest first": "mais antigos primeiro",
  "by author": "por autor",
  "last opened first": "os últimos abertos primeiro",
  "order": "ordem",
  "group by top folder": "agrupar por pasta principal",
  "every folder": "cada pasta",
  "with subfolders": "com as subpastas",
  "this folder only": "só esta pasta",
  "most books first": "as com mais livros primeiro",
  "by title": "por título",
  "last added first": "os últimos adicionados primeiro",
  "downloading…": "a descarregar…",
  "on the shelf": "na estante",
  "opened %s": "aberto %s",
  "the book could not be fetched: %s": "não foi possível obter o livro: %s",
  "add to the library": "adicionar à biblioteca",
  "The book is copied to the drive, into the folder you choose, and becomes a book of the library: its highlights and the page you are at are then kept next to it and follow it to your other devices. Nothing on the drive is written over.": "O livro é copiado para a drive, na pasta que escolher, e passa a ser um livro da biblioteca: os seus destaques e a página em que está ficam então guardados ao lado dele e seguem-no para os seus outros aparelhos. Nada na drive é substituído.",
  "sending…": "a enviar…",
  "“%s” is now in the library, in %s.": "«%s» está agora na biblioteca, em %s.",
  "the book could not be sent: %s": "não foi possível enviar o livro: %s",
  "last time": "da última vez",
  "setting up the converter…": "a preparar o conversor…",
  "the converter could not be set up: %s": "não foi possível preparar o conversor: %s",
  "the PDF “%s” is being turned into an EPUB…": "o PDF «%s» está a ser convertido em EPUB…",
  "loading the models": "a carregar os modelos",
  "reading the pages": "a ler as páginas",
  "making the EPUB": "a fazer o EPUB",
  "the PDF “%s” could not be turned into an EPUB: %s": "o PDF «%s» não pôde ser convertido em EPUB: %s",
  "A PDF is not read as it is: it is turned into an EPUB, a book of the shelf, its figures, tables and equations as pictures; the PDF itself is left as it was. The converter is set up once: about 2 GB downloaded.": "Um PDF não é lido tal como está: é convertido num EPUB, um livro da estante, com as figuras, tabelas e equações como imagens; o próprio PDF fica como estava. O conversor prepara-se uma só vez: cerca de 2 GB descarregados.",
  "set up the converter": "preparar o conversor",
  "reading the scanned pages": "a ler as páginas digitalizadas",
  "“%s” is a scan: its pages are pictures. To get its text, install Tesseract (the tesseract-ocr package) and open the PDF again.": "«%s» é uma digitalização: as páginas são imagens. Para obter o texto, instale o Tesseract (o pacote tesseract-ocr) e volte a abrir o PDF.",
  "books, or a PDF to turn into an EPUB": "livros, ou um PDF para converter em EPUB",
  "a PDF, turned into an EPUB": "um PDF, convertido em EPUB",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file, or a PDF to turn into an EPUB: from here, or by dropping it on this window.": "nada na estante. Abra um ficheiro epub, mobi, fb2 ou de texto, ou um PDF para converter em EPUB: daqui, ou largando-o sobre esta janela.",
 },
 "ru": {
  "follow this folder": "следить за этой папкой",
  "stop following this folder": "больше не следить за этой папкой",
  "its new books one click away, at the top of the library": "её новые книги в один щелчок, вверху библиотеки",
  "looking for new books…": "поиск новых книг…",
  "fetching %d of %d…": "загрузка %d из %d…",
  "nothing new · %s": "ничего нового · %s",
  "followed folder · click to fetch what is new": "папка под наблюдением · щёлкните, чтобы получить новое",
  "issues on this computer": "выпуски на этом компьютере",
  "the whole folder on the drive": "вся папка на диске",
  "no issue of this folder is on this computer yet": "на этом компьютере пока нет ни одного выпуска из этой папки",
  "on this computer": "на этом компьютере",
  "continue reading": "продолжить чтение",
  "set up a library": "подключить библиотеку",
  "your books on your drive, on all your devices": "ваши книги на вашем диске, на всех ваших устройствах",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Give the WebDAV address of the drive with a username and an application password (kDrive, Nextcloud, any WebDAV server). The drive is then scanned for epub, mobi, azw and fb2 files. Highlights and the page you are at are written next to each book, so the login must be allowed to write there.": "Книги на диске, перечисленные по папкам; книга загружается только когда вы щёлкаете по ней. Укажите адрес WebDAV диска с именем пользователя и паролем приложения (kDrive, Nextcloud, любой сервер WebDAV). Затем диск просматривается в поисках файлов epub, mobi, azw и fb2. Выделения и страница, на которой вы остановились, записываются рядом с каждой книгой: учётной записи должна быть разрешена запись.",
  "Highlights: in any book, drag across a passage to highlight it, with a comment if you like; a click on a highlight shows its comment. In a book from the library they are kept next to the book on the drive, with the page you are at, and follow it to your other devices; in a book opened from this computer they stay on this computer, and go to the library with the book if it is added to it. The book's menu exports them. With the WebDAV address of the Reader's Notes folder given below, a note per book lists its highlights in Reader's Notes.": "Выделения: в любой книге проведите мышью по отрывку, чтобы выделить его, при желании с комментарием; щелчок по выделению показывает комментарий. В книге из библиотеки они хранятся рядом с книгой на диске вместе со страницей, на которой вы остановились, и следуют за ней на другие ваши устройства; в книге, открытой с этого компьютера, они остаются на этом компьютере и переходят в библиотеку вместе с книгой, если её туда добавить. Меню книги их экспортирует. Если ниже указан адрес WebDAV папки Reader's Notes, заметка для каждой книги перечисляет её выделения в Reader's Notes.",
  "highlight": "выделить",
  "comment": "комментировать",
  "add a comment": "добавить комментарий",
  "edit the comment": "изменить комментарий",
  "remove the highlight": "убрать выделение",
  "copy": "копировать",
  "export the highlights": "экспортировать выделения",
  "highlights": "выделения",
  "Reader's Notes folder": "папка Reader's Notes",
  "same as the library": "как у библиотеки",
  "username for the notes": "имя пользователя для заметок",
  "password for the notes": "пароль для заметок",
  "yesterday": "вчера",
  "this file could not be read": "этот файл не удалось прочитать",
  "+ open a book": "+ открыть книгу",
  "library": "библиотека",
  "black on white": "чёрным по белому",
  "white on black": "белым по чёрному",
  "lavender": "лаванда",
  "sage": "шалфей",
  "nordic": "северный",
  "terracotta": "терракота",
  "coquette": "кокетка",
  "activist": "активистка",
  "sultry": "знойный",
  "nature": "природа",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file: from here, or by dropping it on this window.": "на полке пусто. Откройте файл epub, mobi, fb2 или текст: отсюда или перетащив его в это окно.",
  "not started": "не начата",
  "read": "читать",
  "contents": "содержание",
  "chapters": "главы",
  "remove from the shelf": "убрать с полки",
  "settings": "настройки",
  "books": "книги",
  "larger text": "крупнее текст",
  "smaller text": "мельче текст",
  "book text": "текст книг",
  "serif": "с засечками",
  "sans-serif": "без засечек",
  "mono": "моноширинный",
  "colours": "цвета",
  "%d · auto": "%d · авто",
  "reading size — click for larger": "размер чтения — щёлкните, чтобы увеличить",
  "automatic size": "автоматический размер",
  "the size the app starts with": "размер, с которого начинает приложение",
  "font": "шрифт",
  "size of the shelf and menus": "размер полки и меню",
  "on": "вкл",
  "off": "выкл",
  "keep the screen on while reading": "не гасить экран при чтении",
  "forget the library": "забыть библиотеку",
  "removes the link, the login and the list of books; the shelf is kept": "удаляет ссылку, учётные данные и список книг; полка сохраняется",
  "reads epub, mobi, fb2 and txt files": "читает файлы epub, mobi, fb2 и txt",
  "Pierre Gallaz · developed with Claude Code": "Pierre Gallaz · разработано с Claude Code",
  "WebDAV address": "адрес WebDAV",
  "username": "имя пользователя",
  "password": "пароль",
  "ok": "ок",
  "cancel": "отмена",
  "export credentials": "экспортировать учётные данные",
  "a file to set up another device — it holds the password": "файл для настройки другого устройства — в нём пароль",
  "import credentials": "импортировать учётные данные",
  "Reader's credentials": "Учётные данные Reader's",
  "credentials exported — the file holds the password: keep it private": "учётные данные экспортированы — в файле пароль: храните его в тайне",
  "drive and login taken from another Reader's app": "диск и учётные данные взяты из другого приложения Reader's",
  "credentials imported": "учётные данные импортированы",
  "not a Reader's credentials file": "это не файл учётных данных Reader's",
  "this file holds nothing for %s": "в этом файле нет ничего для %s",
  "the file cannot be read: %s": "файл не читается: %s",
  "scanning… %d folders, %d books": "просмотр… папок: %d, книг: %d",
  "the drive refused the login": "диск отклонил вход",
  "the drive could not be read: %s": "не удалось прочитать диск: %s",
  "continue the scan": "продолжить просмотр",
  "the scan stopped after %d folders · %d books so far": "просмотр остановился после %d папок · пока %d книг",
  "%d folders could not be read": "не удалось прочитать папок: %d",
  "no e-book found on the drive (epub, mobi, azw, fb2)": "на диске не найдено электронных книг (epub, mobi, azw, fb2)",
  "all books": "все книги",
  "on the drive": "на диске",
  "news": "новости",
  "latest %s": "последний: %s",
  "looking for more… %d/%d": "идёт поиск… %d/%d",
  "the newest first": "сначала новые",
  "search": "поиск",
  "title, author or folder": "название, автор или папка",
  "no book matches": "ни одна книга не подходит",
  "search again": "искать снова",
  "top of the drive": "корень диска",
  "scanned on %s": "просмотрено %s",
  "stop the scan": "остановить просмотр",
  "scan the drive again": "просмотреть диск заново",
  "sync now": "синхронизировать сейчас",
  "folders of the library": "папки библиотеки",
  "The whole drive is in the library. Choose folders to keep only those, with everything inside them: the library is then synced faster. Right-click a folder to leave it out: it is then neither shown nor synced, whatever else is chosen. The transcriptions of Reader's Podcasts stay unless left out.": "В библиотеке весь диск. Выберите папки, чтобы оставить только их со всем содержимым: тогда библиотека синхронизируется быстрее. Щёлкните папку правой кнопкой, чтобы исключить её: тогда она не показывается и не синхронизируется, что бы ни было выбрано. Транскрипции Reader's Podcasts остаются, если не исключены.",
  "the whole drive": "весь диск",
  "in %s": "в %s",
  "left out": "исключена",
  "leave this folder out": "исключить эту папку",
  "take this folder back in": "вернуть эту папку",
  "keep only some folders?": "оставить только некоторые папки?",
  "%d folders hold books — choose the ones for the library, or leave the whole drive": "в %d папках есть книги — выберите папки библиотеки или оставьте весь диск",
  "by name": "по имени",
  "newest first": "сначала новые",
  "oldest first": "сначала старые",
  "by author": "по автору",
  "last opened first": "сначала недавно открытые",
  "order": "порядок",
  "group by top folder": "группировать по верхней папке",
  "every folder": "каждая папка",
  "with subfolders": "с подпапками",
  "this folder only": "только эта папка",
  "most books first": "сначала с наибольшим числом книг",
  "by title": "по названию",
  "last added first": "сначала последние добавленные",
  "downloading…": "загрузка…",
  "on the shelf": "на полке",
  "opened %s": "открыта %s",
  "the book could not be fetched: %s": "не удалось получить книгу: %s",
  "add to the library": "добавить в библиотеку",
  "The book is copied to the drive, into the folder you choose, and becomes a book of the library: its highlights and the page you are at are then kept next to it and follow it to your other devices. Nothing on the drive is written over.": "Книга копируется на диск, в выбранную папку, и становится книгой библиотеки: её выделения и страница, на которой вы остановились, хранятся рядом с ней и следуют за ней на ваши другие устройства. Ничего на диске не перезаписывается.",
  "sending…": "отправка…",
  "“%s” is now in the library, in %s.": "«%s» теперь в библиотеке, в папке %s.",
  "the book could not be sent: %s": "не удалось отправить книгу: %s",
  "last time": "в прошлый раз",
  "setting up the converter…": "установка конвертера…",
  "the converter could not be set up: %s": "не удалось установить конвертер: %s",
  "the PDF “%s” is being turned into an EPUB…": "PDF «%s» преобразуется в EPUB…",
  "loading the models": "загрузка моделей",
  "reading the pages": "чтение страниц",
  "making the EPUB": "создание EPUB",
  "the PDF “%s” could not be turned into an EPUB: %s": "PDF «%s» не удалось преобразовать в EPUB: %s",
  "A PDF is not read as it is: it is turned into an EPUB, a book of the shelf, its figures, tables and equations as pictures; the PDF itself is left as it was. The converter is set up once: about 2 GB downloaded.": "PDF не читается как есть: он преобразуется в EPUB — книгу на полке, с рисунками, таблицами и формулами в виде картинок; сам PDF остаётся без изменений. Конвертер устанавливается один раз: около 2 ГБ загрузки.",
  "set up the converter": "установить конвертер",
  "reading the scanned pages": "распознавание отсканированных страниц",
  "“%s” is a scan: its pages are pictures. To get its text, install Tesseract (the tesseract-ocr package) and open the PDF again.": "«%s» — это скан: его страницы — картинки. Чтобы получить текст, установите Tesseract (пакет tesseract-ocr) и откройте PDF снова.",
  "books, or a PDF to turn into an EPUB": "книги или PDF для преобразования в EPUB",
  "a PDF, turned into an EPUB": "PDF, преобразуемый в EPUB",
  "nothing on the shelf. Open an epub, mobi, fb2 or plain-text file, or a PDF to turn into an EPUB: from here, or by dropping it on this window.": "на полке пусто. Откройте файл epub, mobi, fb2 или текст либо PDF для преобразования в EPUB: отсюда или перетащив его в это окно.",
 },
}

PLURALS = {
 "en": ("%d book", "%d books"), "fr": ("%d livre", "%d livres"), "de": ("%d Buch", "%d Bücher"),
 "es": ("%d libro", "%d libros"), "pt": ("%d livro", "%d livros"),
 "ru": ("%d книга", "%d книги", "%d книг"),
}
FOLDERS_LEFT_OUT = {
 "en": ("%d folder left out", "%d folders left out"), "fr": ("%d dossier écarté", "%d dossiers écartés"),
 "de": ("%d Ordner ausgeschlossen", "%d Ordner ausgeschlossen"), "es": ("%d carpeta dejada fuera", "%d carpetas dejadas fuera"),
 "pt": ("%d pasta deixada de fora", "%d pastas deixadas de fora"),
 "ru": ("%d папка исключена", "%d папки исключены", "%d папок исключено"),
}
FOLDERS = {
 "en": ("%d folder", "%d folders"), "fr": ("%d dossier", "%d dossiers"), "de": ("%d Ordner", "%d Ordner"),
 "es": ("%d carpeta", "%d carpetas"), "pt": ("%d pasta", "%d pastas"),
 "ru": ("%d папка", "%d папки", "%d папок"),
}
FOLDERS_CHOSEN = {
 "en": ("%d folder chosen", "%d folders chosen"), "fr": ("%d dossier choisi", "%d dossiers choisis"),
 "de": ("%d Ordner gewählt", "%d Ordner gewählt"), "es": ("%d carpeta elegida", "%d carpetas elegidas"),
 "pt": ("%d pasta escolhida", "%d pastas escolhidas"),
 "ru": ("%d папка выбрана", "%d папки выбраны", "%d папок выбрано"),
}

PAPERS = {
 "en": ("%d PDF waiting", "%d PDFs waiting"), "fr": ("%d PDF en attente", "%d PDF en attente"),
 "de": ("%d PDF wartet", "%d PDFs warten"), "es": ("%d PDF en espera", "%d PDF en espera"),
 "pt": ("%d PDF à espera", "%d PDF à espera"),
 "ru": ("%d PDF ждёт", "%d PDF ждут", "%d PDF ждут"),
}


def _lang():
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(name)
        if v:
            code = v.split(":")[0].split(".")[0].split("_")[0].lower()
            if code in STRINGS:
                return code
            if code == "en":
                return "en"
    try:
        code = (locale.getdefaultlocale()[0] or "en").split("_")[0].lower()
    except Exception:
        code = "en"
    return code if code in STRINGS else "en"


LANG = _lang()


def _(key, *args):
    text = STRINGS.get(LANG, {}).get(key, key)
    return text % args if args else text


NEW = {
 "en": ("%d new", "%d new"), "fr": ("%d nouveau", "%d nouveaux"), "de": ("%d neu", "%d neu"),
 "es": ("%d nuevo", "%d nuevos"), "pt": ("%d novo", "%d novos"),
 "ru": ("%d новый", "%d новых", "%d новых"),
}
ISSUES_COUNT = {
 "en": ("%d issue", "%d issues"), "fr": ("%d numéro", "%d numéros"), "de": ("%d Ausgabe", "%d Ausgaben"),
 "es": ("%d número", "%d números"), "pt": ("%d edição", "%d edições"),
 "ru": ("%d выпуск", "%d выпуска", "%d выпусков"),
}


def n_new(n):
    return _plural(NEW, n)


def n_issues(n):
    return _plural(ISSUES_COUNT, n)


def n_books(n):
    """« 1 book », « 3 books » — with the three Russian forms."""
    return _plural(PLURALS, n)


def n_folders(n):
    """« 1 folder », « 3 folders »."""
    return _plural(FOLDERS, n)


def n_folders_chosen(n):
    """« 1 folder chosen », « 3 folders chosen »."""
    return _plural(FOLDERS_CHOSEN, n)


def n_folders_left_out(n):
    """« 1 folder left out », « 3 folders left out »."""
    return _plural(FOLDERS_LEFT_OUT, n)


def n_papers(n):
    return _plural(PAPERS, n)


def _plural(table, n):
    forms = table.get(LANG) or table["en"]
    if LANG == "ru":
        if n % 10 == 1 and n % 100 != 11:
            form = forms[0]
        elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
            form = forms[1]
        else:
            form = forms[2]
    else:
        form = forms[0] if n == 1 or (LANG == "fr" and n == 0) else forms[1]
    return form % n


# ------------------------------------------------------------------------------------------
# The model: paragraphs and pictures, no styles or links. Lengths are counted the way the phone
# counts them (UTF-16 units), which is also how Qt numbers the characters of a line: a place in
# a book is (chapter, character), the same on any screen and at any text size.
# ------------------------------------------------------------------------------------------

NORMAL, HEADING, LEAD, SMALL = "NORMAL", "HEADING", "LEAD", "SMALL"


def u16(text):
    return len(text.encode("utf-16-le")) // 2


ITALIC, BOLD, SMALL_CAPS, SUPER, SUB, UNDERLINE, STRIKE, MONO, UPPER, LOWER, CAPITALIZE = 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024
FLAGS, SIZE_SHIFT = 2047, 16


class Para:
    """A paragraph: its text, as it is counted (highlights are places in it), and its kind.
    `styles` marks the words set apart: runs (start, end, flags) of the text, in characters of
    the string — ITALIC, BOLD and the others above, and a size in per cent from SIZE_SHIFT (0 =
    the paragraph's own). `look` is how the book sets the paragraph (Look). Neither changes
    anything in the text itself."""
    __slots__ = ("text", "kind", "styles", "look")

    def __init__(self, text, kind=NORMAL, styles=None, look=None):
        self.text, self.kind, self.styles, self.look = text, kind, styles or None, look

    def slice(self, start, end):
        runs = [(max(a, start) - start, min(b, end) - start, f) for a, b, f in (self.styles or ()) if min(b, end) > max(a, start)]
        return Para(self.text[start:end], self.kind, runs, self.look.slice(start, end) if self.look else None)


class TextBlock:
    def __init__(self, paragraphs):
        self.paragraphs = paragraphs
        self.length = sum(u16(p.text) + 1 for p in paragraphs)


class ImageBlock:
    """A picture inside the book file; `source` is its entry in the EPUB."""
    length = 1

    def __init__(self, source, look=None):
        self.source, self.look = source, look


class Chapter:
    def __init__(self, title, blocks):
        self.title, self.blocks = title, blocks
        self.length = sum(b.length for b in blocks)


class Article:
    def __init__(self, chapter, category, title, author, image):
        self.chapter, self.category, self.title, self.author, self.image = chapter, category, title, author, image


class Book:
    """A parsed book. `magazine` is a list of Articles when the file is a magazine issue as the
    newspapers pipeline writes them: an article per chapter, a contents page with sections."""

    def __init__(self, title, chapters, magazine=None):
        self.title, self.chapters, self.magazine = title, chapters, magazine
        self.total = sum(c.length for c in chapters)

    def chars_before(self, chapter):
        return sum(c.length for c in self.chapters[:chapter])


class Unsupported(Exception):
    pass


# ------------------------------------------------------------------------------------------
# CSS: the little of it a reader with its own font, size, margins and colours follows — the
# publisher's alignment, indents, spacing, sizes of headings and small print, quotations, lists,
# verse, small capitals, superscripts, rules, drop caps, page breaks and tables. Selectors are
# kept when simple (an element, a class, an element with classes, these in a chain of
# descendants or children); any other rule is left out. Rule for rule the phone's Css.kt and
# Styling.kt, so that a book is set alike on both.
# ------------------------------------------------------------------------------------------

AUTO, LEFT, CENTER, RIGHT, JUSTIFY = 0, 1, 2, 3, 4
DISC, CIRCLE, SQUARE, DECIMAL, LOWER_ALPHA, UPPER_ALPHA, LOWER_ROMAN, UPPER_ROMAN = 1, 2, 3, 4, 5, 6, 7, 8
NAN = float("nan")


def _isnan(x):
    return x != x


class Look:
    """How the book sets a paragraph (or a picture), from its style sheets as far as a reader
    with its own font, size, margins and colours follows them: never a character of the text.
    The fields are the phone's (Model.kt, Look); lengths in ems of the reader's size, NaN or AUTO
    when the book said nothing."""
    __slots__ = ("align", "indent", "left", "right", "above", "page_break", "rule", "size", "flags", "level",
                 "marker", "number", "drop_cap", "soft", "cells", "table", "width", "pixels",
                 "list_marker", "list_from", "list_to", "list_left")

    def __init__(self, align=AUTO, indent=NAN, left=0.0, right=0.0, above=0.0, page_break=False, rule=False, size=1.0,
                 flags=0, level=0, marker=0, number=0, drop_cap=0, soft=None, cells=None, table=0, width=NAN, pixels=0,
                 list_marker=0, list_from=0, list_to=0, list_left=0.0):
        self.align, self.indent, self.left, self.right, self.above = align, indent, left, right, above
        self.page_break, self.rule, self.size, self.flags, self.level = page_break, rule, size, flags, level
        self.marker, self.number, self.drop_cap, self.soft, self.cells = marker, number, drop_cap, soft, cells
        self.table, self.width, self.pixels = table, width, pixels
        # for every paragraph of a list item: its list's kind of marker, the numbers its items run
        # through and the margin it stands in, for a column of markers as wide as the widest
        self.list_marker, self.list_from, self.list_to, self.list_left = list_marker, list_from, list_to, list_left

    def slice(self, start, end):
        first = start == 0
        soft = [k - start for k in (self.soft or ()) if start <= k < end] or None
        cells = None
        if self.cells:
            cells = []
            for c in self.cells:
                s, e = max(c[0], start), min(c[1], end)
                if e > s:
                    cells.append((s - start, e - start) + tuple(c[2:]))
            cells = cells or None
        return Look(self.align, self.indent if first else 0.0, self.left, self.right, self.above if first else 0.0,
                    first and self.page_break, first and self.rule, self.size, self.flags, self.level,
                    self.marker if first else 0, self.number, self.drop_cap if first else 0, soft, cells, self.table,
                    self.width, self.pixels, self.list_marker, self.list_from, self.list_to, self.list_left)


class _Compound:
    __slots__ = ("tag", "classes")

    def __init__(self, tag, classes):
        self.tag, self.classes = tag, classes


class _Selector:
    """`parts` right to left; child[i]: parts[i] is a child (not only a descendant) of parts[i + 1]."""
    __slots__ = ("parts", "child", "first_letter", "specificity")

    def __init__(self, parts, child, first_letter):
        self.parts, self.child, self.first_letter = parts, child, first_letter
        self.specificity = sum(len(p.classes) * 10 + (1 if p.tag else 0) for p in parts)


class _Rule:
    __slots__ = ("selector", "decls", "order")

    def __init__(self, selector, decls, order):
        self.selector, self.decls, self.order = selector, decls, order


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_COMPOUND = re.compile(r"^([a-zA-Z][\w-]*)?((?:\.[\w-]+)*)$")
_LENGTH = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+))(em|rem|%|px|pt|ex|ch)?$")
EM_PER_PERCENT = 0.2
SIZE_WORDS = {"xx-small": 0.6, "x-small": 0.75, "small": 0.89, "medium": 1.0, "large": 1.2, "x-large": 1.5,
              "xx-large": 2.0, "xxx-large": 3.0}


def css_declarations(body):
    out = []
    for d in body.split(";"):
        colon = d.find(":")
        if colon <= 0:
            continue
        name = d[:colon].strip().lower()
        value = d[colon + 1:].strip()
        important = value.lower().endswith("!important")
        if important:
            value = value[:-10].strip()
        if name and value:
            out.append((name, value.lower(), important))
    return out


def _skip_block(css, start):
    depth, j = 0, start
    while j < len(css):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(css)


def _css_selector(text):
    t = text.strip()
    if not t:
        return None
    first_letter = False
    for p in ("::first-letter", ":first-letter"):
        if t.lower().endswith(p):
            first_letter, t = True, t[:-len(p)].rstrip()
            break
    if not t or any(c in '[]*+~:#()"\'@\\' for c in t):
        return None
    parts, child, pending = [], [], False
    for tok in [x for x in re.split(r"\s+", t.replace(">", " > ")) if x]:
        if tok == ">":
            if not parts:
                return None
            pending = True
            continue
        m = _COMPOUND.match(tok)
        if not m:
            return None
        tag = (m.group(1) or "").lower() or None
        classes = [c for c in m.group(2).split(".") if c]
        if tag is None and not classes:
            return None
        parts.append(_Compound(tag, classes))
        child.append(pending)
        pending = False
    if not parts or pending:
        return None
    rl = parts[::-1]
    flags = [child[len(rl) - 1 - k] for k in range(len(rl) - 1)]
    return _Selector(rl, flags, first_letter)


def css_parse(text, first_order=0):
    """The rules of a style sheet; `first_order` numbers them after those already read."""
    css = _CSS_COMMENT.sub(" ", text)
    rules, order, i, n = [], first_order, 0, len(css)
    while i < n:
        c = css[i]
        if c.isspace() or c in ";}":
            i += 1
            continue
        if c == "@":
            j = i
            while j < n and css[j] not in ";{":
                j += 1
            i = _skip_block(css, j) if j < n and css[j] == "{" else j + 1
            continue
        start = css.find("{", i)
        if start < 0:
            break
        close = css.find("}", start)
        end = n if close < 0 else close
        decls = css_declarations(css[start + 1:end])
        if decls:
            for sel in css[i:start].split(","):
                s = _css_selector(sel)
                if s:
                    rules.append(_Rule(s, decls, order))
                    order += 1
        i = end + 1
    return rules


def css_em(value, font_size=False):
    """A length in ems; None for what is not one. px/pt at 16 px / 12 pt the em (not for sizes)."""
    v = value.strip()
    if v == "0":
        return 0.0
    m = _LENGTH.match(v)
    if not m:
        return None
    x = float(m.group(1))
    unit = m.group(2) or ""
    if unit in ("em", "rem"):
        return x
    if unit == "%":
        return x / 100.0 if font_size else x * EM_PER_PERCENT
    if unit in ("ex", "ch"):
        return x * 0.5
    if unit == "px":
        return None if font_size else x / 16.0
    if unit == "pt":
        return None if font_size else x / 12.0
    if unit == "":
        return 0.0 if x == 0 else None
    return None


def css_sides(value):
    v = value.strip().split()
    if len(v) == 1:
        return [v[0]] * 4
    if len(v) == 2:
        return [v[0], v[1], v[0], v[1]]
    if len(v) == 3:
        return [v[0], v[1], v[2], v[1]]
    if len(v) == 4:
        return v
    return None


class Sheet:
    """Rules indexed by the element or first class of their rightmost part."""
    def __init__(self, rules):
        self.by_key, self.empty = {}, not rules
        for r in rules:
            last = r.selector.parts[0]
            self.by_key.setdefault("." + last.classes[0] if last.classes else last.tag, []).append(r)


_BREAKS = {"always", "page", "left", "right", "recto", "verso"}
_MARKERS = {"none": 0, "disc": DISC, "circle": CIRCLE, "square": SQUARE, "decimal": DECIMAL,
            "decimal-leading-zero": DECIMAL, "lower-alpha": LOWER_ALPHA, "lower-latin": LOWER_ALPHA,
            "upper-alpha": UPPER_ALPHA, "upper-latin": UPPER_ALPHA, "lower-roman": LOWER_ROMAN, "upper-roman": UPPER_ROMAN}


class Style:
    """What a style sheet makes of one element. Inherited: alignment, indent, size, weight,
    slant, small capitals, case, monospace, line breaks kept, raised or lowered, underline and
    strike, list marker. Its own: margins, page breaks, float, width, a ::first-letter rule."""
    INHERITED = ("align", "indent", "size", "size_set", "bold", "weight_set", "italic", "small_caps", "transform",
                 "mono", "pre", "valign", "underline", "strike", "list_type")

    def __init__(self):
        self.align, self.indent, self.size, self.size_set = AUTO, NAN, 1.0, False
        self.bold = self.weight_set = self.italic = self.small_caps = False
        self.transform, self.mono, self.pre, self.valign = 0, False, False, 0
        self.underline = self.strike = False
        self.list_type = -1
        self.mt = self.mb = self.ml = self.mr = self.pt = self.pb = self.pl = self.pr = 0.0
        self.break_before = self.break_after = self.float_left = self.first_letter = False
        self.width = NAN
        self.own_indent = NAN

    def inherit(self):
        s = Style()
        for k in Style.INHERITED:
            setattr(s, k, getattr(self, k))
        return s

    @property
    def flags(self):
        return ((ITALIC if self.italic else 0) | (BOLD if self.bold else 0) | (SMALL_CAPS if self.small_caps else 0)
                | (SUPER if self.valign == 1 else 0) | (SUB if self.valign == 2 else 0)
                | (UNDERLINE if self.underline else 0) | (STRIKE if self.strike else 0) | (MONO if self.mono else 0)
                | {1: UPPER, 2: LOWER, 3: CAPITALIZE}.get(self.transform, 0))

    def apply(self, name, value, parent):
        if name == "text-align":
            a = {"left": LEFT, "start": LEFT, "-webkit-left": LEFT, "center": CENTER, "-webkit-center": CENTER,
                 "middle": CENTER, "right": RIGHT, "end": RIGHT, "-webkit-right": RIGHT, "justify": JUSTIFY}.get(value)
            if a is not None:
                self.align = a
        elif name == "text-indent":
            e = css_em(value)
            if e is not None:
                self.own_indent = e
        elif name in ("margin", "padding"):
            v = css_sides(value)
            if v:
                e = [css_em(x) for x in v]
                keys = ("mt", "mr", "mb", "ml") if name == "margin" else ("pt", "pr", "pb", "pl")
                for k, x in zip(keys, e):
                    if x is not None:
                        setattr(self, k, x)
        elif name in _SIDES:
            e = css_em(value)
            if e is not None:
                setattr(self, _SIDES[name], e)
        elif name == "font-size":
            f = SIZE_WORDS.get(value)
            if f is None:
                if value == "smaller":
                    f = parent.size * 0.83
                elif value == "larger":
                    f = parent.size * 1.2
                else:
                    e = css_em(value, font_size=True)
                    if e is not None:
                        f = e if value.endswith("rem") else parent.size * e
            if f is not None and f > 0:
                self.size, self.size_set = f, True
        elif name == "font-weight":
            n = int(value) if value.isdigit() else None
            if value in ("bold", "bolder") or (n or 0) >= 600:
                self.bold, self.weight_set = True, True
            elif value in ("normal", "lighter") or (n if n is not None else 1000) < 600:
                self.bold, self.weight_set = False, True
        elif name == "font-style":
            if value in ("italic", "oblique"):
                self.italic = True
            elif value == "normal":
                self.italic = False
        elif name in ("font-variant", "font-variant-caps"):
            if "small-caps" in value:
                self.small_caps = True
            elif value in ("normal", "none"):
                self.small_caps = False
        elif name == "text-transform":
            self.transform = {"uppercase": 1, "lowercase": 2, "capitalize": 3, "none": 0}.get(value, self.transform)
        elif name == "vertical-align":
            self.valign = {"super": 1, "sub": 2, "baseline": 0}.get(value, self.valign)
        elif name in ("text-decoration", "text-decoration-line"):
            if "none" in value:
                self.underline = self.strike = False
            if "underline" in value:
                self.underline = True
            if "line-through" in value:
                self.strike = True
        elif name == "white-space":
            if value in ("pre", "pre-wrap", "pre-line", "break-spaces"):
                self.pre = True
            elif value in ("normal", "nowrap"):
                self.pre = False
        elif name in ("page-break-before", "break-before"):
            if value in _BREAKS:
                self.break_before = True
            elif value in ("auto", "avoid"):
                self.break_before = False
        elif name in ("page-break-after", "break-after"):
            if value in _BREAKS:
                self.break_after = True
            elif value in ("auto", "avoid"):
                self.break_after = False
        elif name in ("list-style-type", "list-style"):
            for w in value.split():
                if w in _MARKERS:
                    self.list_type = _MARKERS[w]
        elif name == "float":
            self.float_left = value == "left"
        elif name == "width":
            if value.endswith("%"):
                try:
                    x = float(value[:-1].strip())
                except ValueError:
                    x = 0
                if x > 0:
                    self.width = min(x, 100.0) / 100.0


_SIDES = {"margin-top": "mt", "margin-bottom": "mb", "margin-left": "ml", "margin-right": "mr",
          "padding-top": "pt", "padding-bottom": "pb", "padding-left": "pl", "padding-right": "pr"}

_VOID = {"br", "hr", "img", "col", "meta", "link", "input", "wbr", "source", "area", "base", "param", "track", "embed",
         "image", "empty-line"}
_BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "dl", "dt", "dd", "blockquote", "pre",
          "section", "article", "aside", "header", "footer", "nav", "figure", "figcaption", "table", "thead", "tbody",
          "tfoot", "tr", "td", "th", "caption", "center", "body", "html", "main", "address", "hgroup", "details",
          "summary", "form", "fieldset", "title", "subtitle", "epigraph", "poem", "stanza", "v", "cite",
          "text-author", "annotation"}
_NO_MARGIN = {"html", "body", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption"}
_PAGE = {"html", "body", "thead", "tbody", "tfoot", "tr", "td", "th", "caption"}
_MONO = {"code", "kbd", "samp", "tt", "pre"}
_CAPTION = re.compile("caption|legend")
_DROP_CAP = re.compile(r"(drop-?cap.*|dropcap.*|lettrine.*|initiale?|first-?letter|big-?initial)$")
_ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"']+))""")
_TAG_NAME = re.compile(r"^</?\s*([a-zA-Z][\w:-]*)")


class _Node:
    __slots__ = ("tag", "classes", "inline", "parent", "attrs", "counter", "ordinal", "span")

    def __init__(self, tag, classes, inline, parent, attrs):
        self.tag, self.classes, self.inline, self.parent, self.attrs = tag, classes, inline, parent, attrs
        self.counter, self.ordinal, self.span = 0, 0, 1


class Tree:
    """The elements of one page, as their tags open and close, with the style of each. Node 0
    is the page itself."""

    def __init__(self, sheet, fb2):
        self.sheet, self.fb2 = sheet, fb2
        self.nodes = [_Node("", [], None, -1, {})]
        self.styles = [Style()]
        self.alike = {}
        self.current = 0

    def tag(self, raw):
        """A tag as it was in the page (from its last « < »). Returns the name of an element
        without inside (br, hr…), which the caller places itself."""
        t = raw[raw.rfind("<"):]
        if t.startswith("<!") or t.startswith("<?"):
            return None
        m = _TAG_NAME.match(t)
        if not m:
            return None
        name = m.group(1).split(":")[-1].lower()
        if t.startswith("</"):
            self._close(name)
            return None
        if name in _VOID:
            return name
        if t.endswith("/>"):
            return None
        self._open(name, self.attributes(t))
        return None

    @staticmethod
    def attributes(t):
        body = t[1:]
        k = 0
        while k < len(body) and not body[k].isspace() and body[k] not in ">/":
            k += 1
        out = {}
        for m in _ATTR.finditer(body[k:]):
            v = m.group(2) if m.group(2) is not None else m.group(3) if m.group(3) is not None else m.group(4) or ""
            out[m.group(1).split(":")[-1].lower()] = v
        return out

    def leaf(self, name, attrs):
        self.nodes.append(self._node(name, attrs, self.current))
        self.styles.append(None)
        return len(self.nodes) - 1

    def _node(self, name, attrs, parent):
        classes = [c for c in (attrs.get("class") or "").split() if c]
        inline = css_declarations(attrs["style"].lower()) if "style" in attrs else None
        return _Node(name, classes, inline, parent, attrs)

    def _nearest(self, start, names, stop=()):
        n = start
        while n > 0:
            t = self.nodes[n].tag
            if t in names:
                return n
            if t in stop:
                return -1
            n = self.nodes[n].parent
        return -1

    def _int(self, v, default):
        try:
            return int((v or "").strip())
        except ValueError:
            return default

    def _open(self, name, attrs):
        if name in _BLOCK:
            k = self._nearest(self.current, {"p"}, _BLOCK - {"p"})
            if k > 0:
                self.current = self.nodes[k].parent
        closing = {"li": ({"li"}, {"ul", "ol"}), "td": ({"td", "th"}, {"tr", "table"}), "th": ({"td", "th"}, {"tr", "table"}),
                   "tr": ({"tr"}, {"table"}), "dt": ({"dt", "dd"}, {"dl"}), "dd": ({"dt", "dd"}, {"dl"})}.get(name)
        if closing:
            k = self._nearest(self.current, *closing)
            if k > 0:
                self.current = self.nodes[k].parent
        n = self._node(name, attrs, self.current)
        if name in ("ol", "ul"):
            n.ordinal = self._int(attrs.get("start"), 1)
            n.counter = n.ordinal - 1
        elif name == "li":
            k = self._nearest(self.current, {"ul", "ol"})
            if k > 0:
                lst = self.nodes[k]
                lst.counter = self._int(attrs.get("value"), lst.counter + 1)
                n.ordinal = lst.counter
        elif name == "tr":
            k = self._nearest(self.current, {"table"})
            if k > 0:
                n.ordinal = self.nodes[k].counter
                self.nodes[k].counter += 1
        elif name in ("td", "th"):
            k = self._nearest(self.current, {"tr"}, {"table"})
            if k > 0:
                row = self.nodes[k]
                n.ordinal = row.counter
                n.span = min(20, max(1, self._int(attrs.get("colspan"), 1)))
                row.counter += n.span
        self.nodes.append(n)
        self.styles.append(None)
        self.current = len(self.nodes) - 1

    def _close(self, name):
        n = self.current
        while n > 0 and self.nodes[n].tag != name:
            n = self.nodes[n].parent
        if n > 0:
            self.current = self.nodes[n].parent

    # ---- styles ----

    def style(self, n):
        s = self.styles[n]
        if s is not None:
            return s
        pending, p = [], n
        while p > 0 and self.styles[p] is None:
            pending.append(p)
            p = self.nodes[p].parent
        for k in reversed(pending):
            # siblings alike are styled alike: no rule here looks at anything but the ancestors
            node = self.nodes[k]
            key = (node.parent, node.tag, tuple(node.classes), tuple(node.inline or ()), node.attrs.get("align"))
            style = self.alike.get(key)
            if style is None:
                style = self.alike[key] = self._compute(k)
            self.styles[k] = style
        return self.styles[n]

    def _compute(self, n):
        node = self.nodes[n]
        parent = self.styles[node.parent]
        s = parent.inherit()
        decls = []          # (priority, order, name, value)
        for i, (name, value) in enumerate(self._ua(n)):
            decls.append((-1, i, name, value))
        if "align" in node.attrs:
            decls.append((0, -1, "text-align", node.attrs["align"].strip().lower()))
        if self.sheet and not self.sheet.empty:
            seen = set()
            for key in [node.tag] + ["." + c for c in node.classes]:
                for r in self.sheet.by_key.get(key, ()):
                    if id(r) in seen or not self._matches(r.selector, n):
                        continue
                    seen.add(id(r))
                    if r.selector.first_letter:
                        if self._big_letter(r.decls):
                            s.first_letter = True
                        continue
                    for name, value, important in r.decls:
                        decls.append((r.selector.specificity + (100000 if important else 0), r.order, name, value))
        for name, value, important in node.inline or ():
            decls.append((50000 + (100000 if important else 0), 0, name, value))
        decls.sort(key=lambda d: (d[0], d[1]))
        if node.tag in _MONO:
            s.mono = True
        for _p, _o, name, value in decls:
            s.apply(name, value, parent)
        if not _isnan(s.own_indent):
            s.indent = s.own_indent * s.size
        for k in ("mt", "mb", "ml", "mr", "pt", "pb", "pl", "pr"):
            setattr(s, k, getattr(s, k) * s.size)
        return s

    @staticmethod
    def _big_letter(decls):
        for name, value, _i in decls:
            if name == "float" and value == "left":
                return True
            if name == "font-size":
                f = SIZE_WORDS.get(value)
                if f is None:
                    f = css_em(value, font_size=True)
                if (f or 0) >= 1.5:
                    return True
        return False

    def _matches(self, sel, n):
        if not self._compound(sel.parts[0], n):
            return False
        cur = n
        for k in range(1, len(sel.parts)):
            cur = self.nodes[cur].parent
            if sel.child[k - 1]:
                if cur <= 0 or not self._compound(sel.parts[k], cur):
                    return False
            else:
                while cur > 0 and not self._compound(sel.parts[k], cur):
                    cur = self.nodes[cur].parent
                if cur <= 0:
                    return False
        return True

    def _compound(self, c, n):
        node = self.nodes[n]
        if c.tag is not None and c.tag != node.tag:
            return False
        return all(k in node.classes for k in c.classes)

    def _ua(self, n):
        """What every reader does with these elements when the book says nothing."""
        node = self.nodes[n]
        t, fb2 = node.tag, self.fb2
        out = []
        if t in ("h1", "h2", "h3", "h5", "h6"):
            out.append(("font-size", {"h1": "2em", "h2": "1.5em", "h3": "1.17em", "h5": "0.83em", "h6": "0.67em"}[t]))
            out.append(("font-weight", "bold"))
        elif t == "h4" or t in ("b", "strong"):
            out.append(("font-weight", "bold"))
        elif t in ("i", "em", "var", "dfn", "emphasis"):
            out.append(("font-style", "italic"))
        elif t in ("u", "ins"):
            out.append(("text-decoration", "underline"))
        elif t in ("s", "strike", "del", "strikethrough"):
            out.append(("text-decoration", "line-through"))
        elif t == "sup":
            out.append(("vertical-align", "super"))
        elif t == "sub":
            out.append(("vertical-align", "sub"))
        elif t == "pre":
            out.append(("white-space", "pre"))
        elif t == "small":
            out.append(("font-size", "smaller"))
        elif t == "big":
            out.append(("font-size", "larger"))
        elif t == "center":
            out.append(("text-align", "center"))
        elif t == "th":
            out += [("font-weight", "bold"), ("text-align", "center")]
        elif t == "caption":
            out.append(("text-align", "center"))
        elif t == "figcaption":
            out += [("text-align", "center"), ("font-size", "0.85em")]
        elif t == "blockquote":
            out.append(("margin", "0.5em 1.5em"))
        elif t in ("ul", "ol"):
            out.append(("padding-left", "1.5em"))
            depth, p = 0, node.parent
            while p > 0:
                if self.nodes[p].tag in ("ul", "ol"):
                    depth += 1
                p = self.nodes[p].parent
            out.append(("list-style-type", "decimal" if t == "ol" else ("disc", "circle")[depth] if depth < 2 else "square"))
        elif t == "dd":
            out.append(("margin-left", "1.5em"))
        elif t == "figure":
            out.append(("margin", "0.5em 0"))
        elif t == "cite":
            out.append(("margin", "0.5em 1.5em") if fb2 else ("font-style", "italic"))
        elif fb2 and t == "title":
            out += [("text-align", "center"), ("font-weight", "bold"), ("font-size", "1.3em")]
        elif fb2 and t == "subtitle":
            out += [("text-align", "center"), ("font-weight", "bold")]
        elif fb2 and t == "epigraph":
            out += [("margin-left", "2em"), ("font-style", "italic")]
        elif fb2 and t == "text-author":
            out.append(("text-align", "right"))
        elif fb2 and t == "poem":
            out.append(("margin-left", "2em"))
        elif fb2 and t == "stanza":
            out.append(("margin-bottom", "0.5em"))
        elif fb2 and t == "v":
            out.append(("text-indent", "0"))
        if any(_CAPTION.search(c.lower()) for c in node.classes):
            out.append(("text-align", "center"))
        return out

    # ---- shapes the reader needs ----

    def is_block(self, n):
        return n == 0 or self.nodes[n].tag in _BLOCK

    def block_of(self, n):
        while n > 0 and self.nodes[n].tag not in _BLOCK:
            n = self.nodes[n].parent
        return n

    def within(self, n, ancestor):
        while n > 0:
            if n == ancestor:
                return True
            n = self.nodes[n].parent
        return ancestor == 0

    def chain(self, n):
        out = []
        while n > 0:
            out.append(n)
            n = self.nodes[n].parent
        return out

    def cell_of(self, n):
        while n > 0:
            t = self.nodes[n].tag
            if t in ("td", "th"):
                return n
            if t == "table":
                return -1
            n = self.nodes[n].parent
        return -1

    def table_of(self, n):
        while n > 0:
            if self.nodes[n].tag == "table":
                return n
            n = self.nodes[n].parent
        return -1

    def row_of(self, n):
        while n > 0:
            t = self.nodes[n].tag
            if t == "tr":
                return n
            if t == "table":
                return -1
            n = self.nodes[n].parent
        return -1

    def is_header(self, cell):
        return self.nodes[cell].tag == "th" or self._nearest(cell, {"thead"}, {"table"}) > 0

    def is_drop_cap(self, n, block):
        node = self.nodes[n]
        if any(_DROP_CAP.match(c.lower()) for c in node.classes):
            return True
        s = self.style(n)
        return s.float_left and s.size >= self.style(block).size * 1.5


MIN_SIZE, MAX_SIZE, MAX_ABOVE, MAX_INDENT, MAX_SIDE, MAX_LEFT, MAX_RIGHT = 0.8, 1.6, 2.5, 3.0, 4.0, 8.0, 4.0


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class _Presenter:
    """Makes the Look of each paragraph and picture of a page, in their order: what each one
    opens and closes of the page's elements gives the space before it, its page break, the
    marker of a list item."""

    def __init__(self, tree, node_at, set_in, hard_at, rules_at, gaps_at):
        self.tree, self.node_at, self.set_in = tree, node_at, set_in
        self.hard_at, self.rules_at, self.gaps_at = hard_at, rules_at, gaps_at
        self.before, self.last_at, self.pending_rule = set(), -1, False

    def hard(self, at):
        return at in self.hard_at or self.tree.style(self.node_at[at]).pre

    def rule_next(self):
        self.pending_rule = True

    def _opening(self, node, at):
        tree = self.tree
        chain = set(tree.chain(node))
        opened, closed = chain - self.before, self.before - chain
        above, page_break = 0.0, False
        for n in opened:
            st = tree.style(n)
            if st.break_before:
                page_break = True
            if tree.is_block(n) and tree.nodes[n].tag not in _PAGE:
                above = max(above, st.mt + st.pt)
        for n in closed:
            st = tree.style(n)
            if st.break_after:
                page_break = True
            if tree.is_block(n) and tree.nodes[n].tag not in _PAGE:
                above = max(above, st.mb + st.pb)
        if any(self.last_at < g <= at for g in self.gaps_at):
            above = max(above, 1.0)
        rule = self.pending_rule or any(self.last_at < r <= at for r in self.rules_at)
        self.pending_rule = False
        self.before, self.last_at = chain, at
        return _clamp(above, 0.0, MAX_ABOVE), page_break, rule, opened

    def _margins(self, block):
        tree = self.tree
        left = right = 0.0
        n = block
        while n > 0:
            node = tree.nodes[n]
            if tree.is_block(n) and node.tag not in _NO_MARGIN:
                st = tree.style(n)
                left += _clamp(st.ml + st.pl, 0.0, MAX_SIDE)
                right += _clamp(st.mr + st.pr, 0.0, MAX_SIDE)
            n = node.parent
        return min(left, MAX_LEFT), min(right, MAX_RIGHT)

    def picture(self, node, at):
        if node is None:
            return None
        above, page_break, rule, _opened = self._opening(node, at)
        tree = self.tree
        st = tree.style(node)
        w = (tree.nodes[node].attrs.get("width") or "").strip() or None
        width = st.width
        if _isnan(width) and w and w.endswith("%"):
            try:
                width = _clamp(float(w[:-1]) / 100.0, 0.05, 1.0)
            except ValueError:
                pass
        pixels = 0
        if w and not w.endswith("%"):
            try:
                pixels = max(0, int(float(w[:-2] if w.endswith("px") else w)))
            except ValueError:
                pixels = 0
        align = tree.style(tree.block_of(tree.nodes[node].parent)).align
        return Look(align=align, above=above, page_break=page_break, rule=rule, width=width, pixels=pixels)

    def paragraph(self, t, kind):
        tree, node_at, set_in = self.tree, self.node_at, self.set_in
        first = t.at[0]
        node = node_at[first]
        above, page_break, rule, opened = self._opening(node, first)
        block = tree.block_of(node)
        bs = tree.style(block)
        left, right = self._margins(block)
        marker = number = level = 0
        list_marker = list_from = list_to = 0
        list_left = 0.0
        n = block
        while n > 0:
            tag = tree.nodes[n].tag
            if tag == "li" and marker == 0 and n in opened:
                marker, number = max(0, tree.style(n).list_type), tree.nodes[n].ordinal
            if tag == "li" and list_marker == 0:
                # the list this item is in: its kind of marker, its numbers, the margin it stands in
                lst = tree.nodes[n].parent
                list_marker = max(0, tree.style(n).list_type)
                if lst > 0 and tree.nodes[lst].tag in ("ul", "ol") and list_marker > 0:
                    list_from = tree.nodes[lst].ordinal
                    list_to = max(tree.nodes[lst].counter, list_from)
                    list_left = self._margins(tree.nodes[lst].parent)[0]
                else:
                    list_marker = 0
            if level == 0 and len(tag) == 2 and tag[0] == "h" and tag[1] in "123456":
                level = int(tag[1])
            n = tree.nodes[n].parent
        size = _clamp(0.8 if kind == SMALL and not bs.size_set else bs.size, MIN_SIZE, MAX_SIZE)
        block_flags = bs.flags | (BOLD if kind == LEAD and not bs.weight_set else 0)
        soft = [i for i, c in enumerate(t.chars) if c == "\n" and t.at[i] == -1] or None

        known = {}

        def flag_of(at):
            key = node_at[at] * 4 + set_in[at]
            f = known.get(key)
            if f is None:
                st = tree.style(node_at[at])
                f = (set_in[at] | st.flags) & ~block_flags
                ratio = _clamp(st.size, MIN_SIZE, MAX_SIZE) / size
                if not f & (SUPER | SUB) and (ratio < 0.97 or ratio > 1.03):
                    f |= int(ratio * 100 + 0.5) << SIZE_SHIFT
                known[key] = f
            return f
        styles = t.styles(flag_of)
        indent = bs.indent if _isnan(bs.indent) else _clamp(bs.indent, -MAX_INDENT, MAX_INDENT)
        table = tree.table_of(node)
        look = Look(align=bs.align, indent=indent, left=left, right=right, above=above, page_break=page_break,
                    rule=rule, size=size, flags=block_flags, level=level, marker=marker, number=number,
                    drop_cap=self._drop_cap(t, node, block, bs), soft=soft, cells=self._cells(t, node),
                    table=max(0, table), list_marker=list_marker, list_from=list_from, list_to=list_to,
                    list_left=list_left)
        return styles, look

    def _drop_cap(self, t, node, block, bs):
        tree = self.tree
        big, p = -1, node
        while p > 0 and p != block:
            if tree.is_drop_cap(p, block):
                big = p
            p = tree.nodes[p].parent
        if big > 0:
            k = 0
            while k < len(t.chars) and t.at[k] >= 0 and tree.within(self.node_at[t.at[k]], big):
                k += 1
            return k if 1 <= k <= 3 and k < len(t.chars) and not any(c.isspace() for c in t.chars[:k]) else 0
        if not bs.first_letter:
            return 0
        k = 0
        while k < 2 and k < len(t.chars) and not t.chars[k].isalnum() and not t.chars[k].isspace():
            k += 1
        return k + 1 if k < len(t.chars) - 1 and t.chars[k].isalnum() else 0

    def _cells(self, t, node):
        tree = self.tree
        if tree.table_of(node) <= 0:
            return None
        n = len(t.chars)
        cell_at = [tree.cell_of(self.node_at[a]) if a >= 0 else -2 for a in t.at]
        for k in range(n):
            if cell_at[k] == -2:
                cell_at[k] = cell_at[k - 1] if 0 < k < n - 1 and cell_at[k - 1] >= 0 and cell_at[k - 1] == cell_at[k + 1] else -1
        out, k = [], 0
        while k < n:
            c, e = cell_at[k], k + 1
            while e < n and cell_at[e] == c:
                e += 1
            if c > 0:
                row = tree.row_of(c)
                out.append((k, e, tree.nodes[row].ordinal if row > 0 else 0, tree.nodes[c].ordinal, tree.nodes[c].span,
                            1 if tree.is_header(c) else 0))
            k = e
        return out or None


# ------------------------------------------------------------------------------------------
# HTML → paragraphs. Regex based on purpose: tolerant of sloppy markup. Rule for rule the
# phone's HtmlText, so that a chapter has the same characters at the same places on both.
# ------------------------------------------------------------------------------------------

_DROP = re.compile(r"<(script|style|head|svg|math)\b[^>]*>.*?</\1>", re.I | re.S)
_COMMENTS = re.compile(r"<!--.*?-->", re.S)
_BR = re.compile(r"<br\b[^>]*>", re.I)
_PARA_BREAK = re.compile(
    r"</(p|div|h[1-6]|li|tr|blockquote|section|article|title|subtitle|dd|dt|pre|table|figcaption|aside|header|footer|epigraph|stanza|v)>"
    r"|<(p|div|h[1-6]|li|tr|blockquote|section|article|dd|dt|pre|table|figcaption|aside|header|footer)\b[^>]*>"
    r"|<empty-line\s*/?>|<hr\b[^>]*/?>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_HEADING = re.compile(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", re.I | re.S)
_SVG_IMAGE = re.compile(r'<image\b[^>]*?(?:xlink:)?href="([^"]+)"[^>]*>', re.I)
_IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*>', re.I)
_HEADING_OPEN = re.compile(r"<h[1-6]\b[^>]*>", re.I)
_CLASSED = re.compile(r'<(p|div)\b[^>]*class="([^"]*)"[^>]*>', re.I)
_LEAD = re.compile(r"\blead\b|\bchapo\b|\bstandfirst\b")
_SMALLPRINT = re.compile(r"\bcategory\b|\bauthor\b|\bbyline\b|caption|\bcredit\b|\bseparator\b|\bfootnote\b")
_SPACES = re.compile("[ \\t\\r   ]+")
_BLANK_LINE = re.compile(r"\n\s*\n")
_MARKS = re.compile("\u0001[HLS]")
_ENTITY = re.compile(r"&(#x[0-9a-fA-F]+|#[0-9]+|[a-zA-Z]+);")
MARK, IMG = "\u0001", "\u0002"

_NAMED = {
    "amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " ",
    "mdash": "—", "ndash": "–", "hellip": "…", "lsquo": "‘", "rsquo": "’", "ldquo": "“", "rdquo": "”",
    "laquo": "«", "raquo": "»", "shy": "", "copy": "©", "reg": "®", "deg": "°", "middot": "·",
    "eacute": "é", "egrave": "è", "ecirc": "ê", "agrave": "à", "acirc": "â", "ccedil": "ç", "ugrave": "ù",
    "ucirc": "û", "ocirc": "ô", "icirc": "î", "iuml": "ï", "euml": "ë", "auml": "ä", "ouml": "ö", "uuml": "ü",
    "szlig": "ß", "ntilde": "ñ", "oacute": "ó", "iacute": "í", "uacute": "ú", "aacute": "á", "atilde": "ã", "otilde": "õ",
    "Eacute": "É", "Agrave": "À", "Ccedil": "Ç", "times": "×", "euro": "€", "pound": "£", "sect": "§",
}


def decode_entities(s):
    def one(m):
        e = m.group(1)
        try:
            if e.startswith("#x"):
                return chr(int(e[2:], 16))
            if e.startswith("#"):
                return chr(int(e[1:]))
        except (ValueError, OverflowError):
            return m.group(0)
        return _NAMED.get(e, m.group(0))
    return _ENTITY.sub(one, s)


def strip_tags(text):
    return re.sub(r"\s+", " ", re.sub("[\u0001\u0002]", "", decode_entities(_ANY_TAG.sub("", text))))


def heading_of(text):
    m = _HEADING.search(text)
    if not m:
        return None
    t = strip_tags(m.group(1)).strip()
    return t if t and len(t) < 120 else None


_EMPHASIS = re.compile(r"<(/?)(i|em|b|strong)(\s[^>]*)?>", re.I)
ITALIC_ON, ITALIC_OFF, BOLD_ON, BOLD_OFF = "\u0003", "\u0004", "\u0005", "\u0006"
_EMPHASIS_MARKS = re.compile("[\u0003-\u0006]")


def _emphasis(m):
    if (m.group(3) or "").rstrip().endswith("/"):
        return ""                                    # <b/>: nothing to set
    italic = m.group(2).lower() in ("i", "em")
    if m.group(1):
        return ITALIC_OFF if italic else BOLD_OFF
    return ITALIC_ON if italic else BOLD_ON


class _Traced:
    """A piece of text with, for each character, its place in the text it was cut from (-1 for a
    line break put in between): the steps that make paragraphs, done so that each character keeps
    track of whether it was in italic or bold."""
    __slots__ = ("chars", "at")

    def __init__(self, chars, at):
        self.chars, self.at = chars, at

    def cut(self, start, end):
        return _Traced(self.chars[start:end], self.at[start:end])

    def lstrip(self):
        t = self.chars.lstrip()
        return self.cut(len(self.chars) - len(t), len(self.chars))

    def strip(self):
        i = len(self.chars) - len(self.chars.lstrip())
        j = len(self.chars.rstrip())
        return self.cut(i, max(i, j))

    def lines(self, hard=None):
        """Its lines stripped, the empty ones dropped, joined again by line breaks. A line break
        put in between is -1, or -2 when `hard` says the one it stands for stays a line break."""
        parts, joins, gap_hard, start = [], [], False, 0
        for i in range(len(self.chars) + 1):
            if i == len(self.chars) or self.chars[i] == "\n":
                piece = self.cut(start, i)
                if piece.chars.strip():
                    if parts:
                        joins.append(-2 if gap_hard else -1)
                    parts.append(piece.strip())
                    gap_hard = False
                if i < len(self.chars) and hard is not None and parts and self.at[i] >= 0 and hard(self.at[i]):
                    gap_hard = True
                start = i + 1
        if len(parts) == 1:
            return parts[0]
        chars, at = [], []
        for k, p in enumerate(parts):
            if k:
                chars.append("\n")
                at.append(joins[k - 1])
            chars.append(p.chars)
            at.extend(p.at)
        return _Traced("".join(chars), at)

    def without(self, pattern):
        if not pattern.search(self.chars):
            return self
        chars, at, start = [], [], 0
        for m in pattern.finditer(self.chars):
            chars.append(self.chars[start:m.start()])
            at.extend(self.at[start:m.start()])
            start = m.end()
        chars.append(self.chars[start:])
        at.extend(self.at[start:])
        return _Traced("".join(chars), at)

    def styles(self, set_in):
        """The runs, from what each character of the source was set in (`set_in(place)`)."""
        runs, i, n = [], 0, len(self.chars)
        while i < n:
            f = set_in(self.at[i]) if self.at[i] >= 0 else 0
            j = i + 1
            while j < n and (set_in(self.at[j]) if self.at[j] >= 0 else f) == f:
                j += 1
            if f:
                runs.append((i, j, f))
            i = j
        return runs

    @staticmethod
    def collapse(text):
        """Every run of these spaces made one plain space, as the text always was."""
        chars, at, start = [], [], 0
        for m in _SPACES.finditer(text):
            chars.append(text[start:m.start()])
            at.extend(range(start, m.start()))
            chars.append(" ")
            at.append(m.start())
            start = m.end()
        chars.append(text[start:])
        at.extend(range(start, len(text)))
        return _Traced("".join(chars), at)


# The book's presentation: every tag left after the steps below is followed by a mark and its
# number (two characters of the private use area), and every picture is preceded by one; the marks
# go out with italic and bold, before the text is touched, so that the text is the same character
# for character, and each character knows the element it was in.
TAG_MARK, PICTURE_MARK, PUA, PUA_SIZE = "\u0007", "\u0008", 0xE000, 6400
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.I | re.S)


def _number(k):
    return chr(PUA + k // PUA_SIZE) + chr(PUA + k % PUA_SIZE)


def page_rules(text, first_order):
    """The rules of the <style> blocks of a page."""
    out = []
    for m in _STYLE_BLOCK.finditer(text):
        out += css_parse(m.group(1).replace("<!--", " ").replace("-->", " "), first_order + len(out))
    return out


def to_blocks(text, image, rules=(), fb2=False):
    """Paragraphs with their kind, and the pictures between them. `image` maps an `src` to what
    the reader can load, or None to drop it. Kinds are marked with control characters before the
    tags are stripped. Words in italic or bold keep it as runs beside the text (Para.styles), and
    each paragraph how the book sets it (Para.look, from `rules`, the page's own style blocks and
    the style attributes): the text itself is exactly what it is without them, so a place in it
    is the same either way. `fb2` sets FictionBook's own elements (poems, epigraphs…)."""
    styled = TAG_MARK not in text and PICTURE_MARK not in text
    tree = Tree(Sheet(list(rules) + page_rules(text, len(rules))), fb2) if styled else None
    pictures = []
    s = _COMMENTS.sub("", text)
    s = _SVG_IMAGE.sub(lambda m: '<img src="%s"/>' % m.group(1), s)

    def picture(m):
        found = image(m.group(1))
        if not found:
            return " "
        if styled:
            pictures.append(m.group(0))
            return "\n\n%s%s%s%s\n\n" % (PICTURE_MARK, _number(len(pictures) - 1), IMG, found)
        return "\n\n%s%s\n\n" % (IMG, found)
    s = _IMG.sub(picture, s)
    s = _DROP.sub(" ", s)
    s = _HEADING_OPEN.sub(lambda m: m.group(0) + MARK + "H", s)

    def classed(m):
        c = m.group(2).lower()
        if _LEAD.search(c):
            return m.group(0) + MARK + "L"
        if _SMALLPRINT.search(c):
            return m.group(0) + MARK + "S"
        return m.group(0)
    s = _CLASSED.sub(classed, s)
    # a text that carries these control characters itself is left without emphasis, as it is
    marked = not _EMPHASIS_MARKS.search(s)
    if marked:
        s = _EMPHASIS.sub(_emphasis, s)
    tags = []
    if styled:
        def tag(m):
            tags.append(m.group(0))
            return m.group(0) + TAG_MARK + _number(len(tags) - 1)
        s = _ANY_TAG.sub(tag, s)
    s = _BR.sub("\n", s)
    s = _PARA_BREAK.sub("\n\n", s)
    s = _ANY_TAG.sub("", s)
    s = decode_entities(s)
    # the marks out: the text without them, what each character is set in, the element it is in
    plain, set_in, node_at, italic, bold = [], [], [], 0, 0
    hard_at, rules_at, gaps_at, picture_node = set(), [], [], {}
    special = re.compile("[\u0003-\u0008]" if marked else "[\u0007\u0008]")
    length = 0                  # characters in plain so far
    i, n = 0, len(s)
    while i < n:
        m = special.search(s, i)
        j = m.start() if m else n
        if j > i:               # a stretch of text, all set in the same
            plain.append(s[i:j])
            set_in.extend([(ITALIC if italic else 0) | (BOLD if bold else 0)] * (j - i))
            if tree is not None:
                node_at.extend([tree.current] * (j - i))
            length += j - i
        if not m:
            break
        c = s[j]
        i = j + 1
        if c in (TAG_MARK, PICTURE_MARK):
            if tree is not None and j + 2 < n:
                k = (ord(s[j + 1]) - PUA) * PUA_SIZE + (ord(s[j + 2]) - PUA)
                if c == TAG_MARK:
                    if 0 <= k < len(tags):
                        name = tree.tag(tags[k])
                        if name == "br":
                            if length and plain[-1][-1] == "\n":
                                hard_at.add(length - 1)
                        elif name == "hr":
                            rules_at.append(length)
                        elif name == "empty-line":
                            gaps_at.append(length)
                elif 0 <= k < len(pictures):
                    picture_node[length] = tree.leaf("img", tree.attributes(pictures[k]))
                i = j + 3
                continue
            # the page's own control character (no presentation then): kept as text
            plain.append(c)
            set_in.append((ITALIC if italic else 0) | (BOLD if bold else 0))
            length += 1
            continue
        if c == ITALIC_ON:
            italic += 1
        elif c == ITALIC_OFF:
            italic = max(0, italic - 1)
        elif c == BOLD_ON:
            bold += 1
        else:
            bold = max(0, bold - 1)
    whole = _Traced.collapse("".join(plain))
    look = _Presenter(tree, node_at, set_in, hard_at, rules_at, gaps_at) if tree is not None else None
    blocks, paras, start = [], [], 0
    raws = []
    for m in _BLANK_LINE.finditer(whole.chars):
        raws.append(whole.cut(start, m.start()))
        start = m.end()
    raws.append(whole.cut(start, len(whole.chars)))
    for raw in raws:
        para = raw.lines(look.hard if look else None)
        if not para.chars:
            continue
        if para.chars.startswith(IMG):
            if paras:
                blocks.append(TextBlock(paras))
                paras = []
            blocks.append(ImageBlock(para.chars[1:].split("\n")[0].strip(),
                                     look.picture(picture_node.get(para.at[0]), para.at[0]) if look else None))
            continue
        kind, t = NORMAL, para
        while len(t.chars) > 1 and t.chars[0] == MARK:
            kind = {"H": HEADING, "L": LEAD, "S": SMALL}.get(t.chars[1], kind)
            t = t.cut(2, len(t.chars)).lstrip()
        t = t.without(_MARKS)
        if t.chars in ("---", "♦"):       # the pipeline's separators
            if t.chars == "---" and look:
                look.rule_next()
            continue
        if not t.chars:
            continue
        if look is None:
            paras.append(Para(t.chars, kind, t.styles(set_in.__getitem__)))
        else:
            styles, l = look.paragraph(t, kind)
            paras.append(Para(t.chars, kind, styles, l))
    if paras:
        blocks.append(TextBlock(paras))
    return blocks


# ------------------------------------------------------------------------------------------
# The formats: EPUB (zip + OPF spine), MOBI (PalmDoc), FB2 (XML) and plain text. The aim is a
# stable text extraction, not fidelity.
# ------------------------------------------------------------------------------------------

EPUB, MOBI, FB2, TXT = "EPUB", "MOBI", "FB2", "TXT"
OPEN_FILTER = "*.epub *.mobi *.prc *.azw *.azw3 *.fb2 *.txt"


def detect(path, name_hint):
    with open(path, "rb") as fh:
        head = fh.read(68)
    if head[:2] == b"PK":
        return EPUB
    if head[60:68] == b"BOOKMOBI":
        return MOBI
    ext = name_hint.rsplit(".", 1)[-1].lower() if "." in name_hint else ""
    if ext == "fb2":
        return FB2
    start = head.decode("latin-1")
    if "<?xml" in start or "<FictionBook" in start:
        return FB2
    return {"epub": EPUB, "mobi": MOBI, "prc": MOBI, "azw": MOBI, "azw3": MOBI}.get(ext, TXT)


def _read_text(path):
    with open(path, "rb") as fh:
        data = fh.read()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", "replace")


def parse_book(path, fmt, fallback_title):
    if fmt == EPUB:
        book = _parse_epub(path, fallback_title)
    elif fmt == MOBI:
        book = _parse_mobi(path, fallback_title)
    elif fmt == FB2:
        book = _parse_fb2(_read_text(path), fallback_title)
    else:
        book = _parse_txt(_read_text(path), fallback_title)
    if not book.chapters:
        raise Unsupported("no text found")
    chapters, first_part = _split_long(book.chapters)
    magazine = None
    if book.magazine:
        magazine = [Article(first_part[a.chapter], a.category, a.title, a.author, a.image) for a in book.magazine]
    return Book(book.title, chapters, magazine)


_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)


def _attr(tag, name):
    m = re.search(r'\b%s\s*=\s*"([^"]*)"' % name, tag, re.I) or re.search(r"\b%s\s*=\s*'([^']*)'" % name, tag, re.I)
    return m.group(1) if m else None


def _resolve(directory, href):
    parts = []
    for seg in (directory + unquote(href.split("#")[0])).split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


def _norm(path):
    return path.split("#")[0].lower()


def _dir_of(path):
    return path.rsplit("/", 1)[0] + "/" if "/" in path else ""


def _parse_epub(path, fallback_title):
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise Unsupported("not an EPUB")
    with zf:
        names = set(zf.namelist())

        def read(name):
            name = name if name in names else name.lstrip("/")
            if name not in names:
                return None
            return zf.read(name).decode("utf-8", "replace")

        container = read("META-INF/container.xml")
        if container is None:
            raise Unsupported("not an EPUB")
        m = re.search(r'full-path="([^"]+)"', container)
        if not m:
            raise Unsupported("no OPF")
        opf_path = m.group(1)
        opf = read(opf_path)
        if opf is None:
            raise Unsupported("OPF missing")
        base = _dir_of(opf_path)

        items = {}
        for tag in re.findall(r"<item\b[^>]*>", opf, re.I):
            iid, href = _attr(tag, "id"), _attr(tag, "href")
            if iid and href:
                items[iid] = (href, _attr(tag, "media-type") or "")
        spine = [x for x in (_attr(t, "idref") for t in re.findall(r"<itemref\b[^>]*>", opf, re.I)) if x]
        m = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf, re.I | re.S)
        title = (decode_entities(m.group(1)).strip() if m else "") or fallback_title

        # Chapter titles from the NCX (EPUB 2) or the nav document (EPUB 3), keyed by href.
        titles = {}
        ncx = next((h for h, t in items.values() if "dtbncx" in t), None) \
            or next((h for h, t in items.values() if h.lower().endswith(".ncx")), None)
        ncx_text = read(_resolve(base, ncx)) if ncx else None
        if ncx_text:
            for np in re.findall(r"<navPoint\b.*?</navPoint>", ncx_text, re.I | re.S):
                t = re.search(r"<text>(.*?)</text>", np, re.S)
                src = re.search(r'<content\b[^>]*src="([^"]+)"', np)
                if t and src:
                    titles.setdefault(_norm(_resolve(base, src.group(1))), decode_entities(t.group(1)).strip())
        m = re.search(r'<item\b[^>]*properties="[^"]*\bnav\b[^"]*"[^>]*>', opf, re.I)
        nav_href = _attr(m.group(0), "href") if m else None
        nav = read(_resolve(base, nav_href)) if nav_href else None
        nav_dir = base + _dir_of(nav_href) if nav_href else base
        if nav:
            for href, text in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', nav, re.I | re.S):
                titles.setdefault(_norm(_resolve(nav_dir, href)), strip_tags(text).strip())

        # The publisher's style sheets, each read once; the rules a page links to, in its order.
        sheets = {}

        def style_sheets(text, chapter_dir):
            out = []
            for tag in _LINK_TAG.findall(text):
                if "stylesheet" not in (_attr(tag, "rel") or "").lower() and "css" not in (_attr(tag, "type") or "").lower():
                    continue
                href = _attr(tag, "href")
                if not href:
                    continue
                where = _resolve(chapter_dir, href)
                if where not in sheets:
                    css = read(where)
                    sheets[where] = css_parse(css) if css is not None else []
                for r in sheets[where]:
                    out.append(_Rule(r.selector, r.decls, len(out)))
            return out

        chapters, by_path, htmls = [], {}, []
        for index, idref in enumerate(spine):
            if idref not in items:
                continue
            href, kind = items[idref]
            if kind and "html" not in kind and "xml" not in kind:
                continue
            where = _resolve(base, href)
            text = read(where)
            if text is None:
                continue
            chapter_dir = _dir_of(where)

            def image(src, chapter_dir=chapter_dir):
                p = _resolve(chapter_dir, src)
                return p if p in names else None

            blocks = to_blocks(text, image, style_sheets(text, chapter_dir))
            if not blocks:
                continue
            by_path[_norm(where)] = len(chapters)
            htmls.append(text)
            chapters.append(Chapter(titles.get(_norm(where)) or heading_of(text) or str(index + 1), blocks))

        magazine = _parse_magazine(nav, nav_dir, chapters, by_path, htmls)
        if magazine:
            # Only the articles are chapters: the title page and the contents page go.
            keep = sorted({a.chapter for a in magazine})
            remap = {c: i for i, c in enumerate(keep)}
            title_of = {}
            for a in magazine:
                title_of.setdefault(a.chapter, a.title)
            articles = [Article(remap[a.chapter], a.category, a.title, a.author, a.image) for a in magazine]
            return Book(title, [Chapter(title_of.get(c) or chapters[c].title, chapters[c].blocks) for c in keep], articles)
        return Book(title, chapters)


def _parse_magazine(nav, nav_dir, chapters, by_path, htmls):
    """The nav carries a section, a title and an author per article (signature A), or else
    every article page starts with them (signature B)."""
    def classed(text, tag, cls):
        m = re.search(r'<%s\b[^>]*class="[^"]*\b%s\b[^"]*"[^>]*>(.*?)</%s>' % (tag, cls, tag), text, re.I | re.S)
        return (strip_tags(m.group(1)).strip() or None) if m else None

    def cover(chapter):
        return next((b.source for b in chapters[chapter].blocks if isinstance(b, ImageBlock)), None)

    articles = []
    if nav and "toc-cat" in nav and "toc-title" in nav:
        for li in re.findall(r"<li\b[^>]*>(.*?)</li>", nav, re.I | re.S):
            m = re.search(r'<a\b[^>]*href="([^"]+)"', li, re.I)
            chapter = by_path.get(_norm(_resolve(nav_dir, m.group(1)))) if m else None
            title = classed(li, "span", "toc-title")
            if chapter is None or not title:
                continue
            articles.append(Article(chapter, classed(li, "span", "toc-cat") or "", title,
                                    classed(li, "span", "toc-author"), cover(chapter)))
        if articles:
            return articles
    structured = 0
    for i, text in enumerate(htmls):
        category, title = classed(text, "p", "category"), heading_of(text)
        if not category or not title:
            continue
        structured += 1
        articles.append(Article(i, category, title, classed(text, "p", "author"), cover(i)))
    return articles if chapters and structured * 2 >= len(chapters) else None


def _parse_mobi(path, fallback_title):
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        count = struct.unpack_from(">H", data, 76)[0]
        if count < 2:
            raise Unsupported("empty MOBI")
        offsets = [struct.unpack_from(">I", data, 78 + 8 * i)[0] for i in range(count)] + [len(data)]
        r0 = offsets[0]
        compression, = struct.unpack_from(">H", data, r0)
        text_records, = struct.unpack_from(">H", data, r0 + 8)
        encryption, = struct.unpack_from(">H", data, r0 + 12)
        if encryption:
            raise Unsupported("DRM")
        if compression not in (1, 2):
            raise Unsupported("HUFF/CDIC compression")
        charset, extra = "utf-8", 0
        title = data[:32].decode("latin-1").rstrip("\x00").strip() or fallback_title
        if data[r0 + 16:r0 + 20] == b"MOBI":
            header_length, = struct.unpack_from(">I", data, r0 + 20)
            encoding, = struct.unpack_from(">I", data, r0 + 28)
            if encoding == 1252:
                charset = "cp1252"
            if header_length >= 0xE4:
                extra, = struct.unpack_from(">H", data, r0 + 0xF2)
            exth_flag, = struct.unpack_from(">I", data, r0 + 0x80)
            exth = r0 + 16 + header_length
            if exth_flag & 0x40 and data[exth:exth + 4] == b"EXTH":
                n, = struct.unpack_from(">I", data, exth + 8)
                p = exth + 12
                for _i in range(n):
                    kind, length = struct.unpack_from(">II", data, p)
                    if kind == 503 and length > 8:
                        title = data[p + 8:p + length].decode(charset, "replace")
                    p += length
        out = bytearray()
        for i in range(1, min(text_records, count - 1) + 1):
            start, end = offsets[i], offsets[i + 1]
            # Strip trailing entries (bits 1..15), then the multibyte trailer (bit 0).
            for bit in range(15, 0, -1):
                if extra & (1 << bit):
                    size = shift = 0
                    p = end - 1
                    while p >= start:
                        b = data[p]
                        size |= (b & 0x7F) << shift
                        shift += 7
                        if b & 0x80 or shift > 28 or p == start:
                            break
                        p -= 1
                    end -= size
            if extra & 1:
                end -= (data[end - 1] & 3) + 1
            if end <= start:
                continue
            record = data[start:end]
            out += _palmdoc(record) if compression == 2 else record
    except (struct.error, IndexError):
        raise Unsupported("damaged MOBI")
    text = out.decode(charset, "replace")
    chapters = []
    for i, section in enumerate(re.split(r"<mbp:pagebreak\s*/?>", text, flags=re.I)):
        blocks = to_blocks(section, lambda src: None)
        if blocks:
            chapters.append(Chapter(heading_of(section) or str(i + 1), blocks))
    return Book(title, chapters)


def _palmdoc(data):
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        i += 1
        if c == 0:
            out.append(0)
        elif c <= 8:
            out += data[i:i + c]
            i += c
        elif c <= 0x7F:
            out.append(c)
        elif c <= 0xBF:
            if i >= n:
                break
            v = (c << 8) | data[i]
            i += 1
            distance, length = (v >> 3) & 0x7FF, (v & 7) + 3
            start = len(out) - distance
            if start < 0:
                continue
            for k in range(length):
                out.append(out[start + k])
        else:
            out.append(32)
            out.append(c ^ 0x80)
    return bytes(out)


def _parse_fb2(xml, fallback_title):
    plain = re.sub(r"<binary\b.*?</binary>", "", xml, flags=re.I | re.S)
    m = re.search(r"<book-title>(.*?)</book-title>", plain, re.S)
    title = (decode_entities(m.group(1)).strip() if m else "") or fallback_title
    body = "\n".join(re.findall(r"<body\b.*?</body>", plain, re.I | re.S)) or plain
    chapters = []
    for i, section in enumerate(re.split(r"<section\b[^>]*>", body, flags=re.I)):
        blocks = to_blocks(section, lambda src: None, fb2=True)
        if not blocks:
            continue
        m = re.search(r"<title>(.*?)</title>", section, re.S)
        t = strip_tags(m.group(1)).strip() if m else ""
        chapters.append(Chapter(t or str(i + 1), blocks))
    return Book(title, chapters)


def _parse_txt(text, fallback_title):
    paragraphs = [p.strip() for p in _BLANK_LINE.split(text.replace("\r\n", "\n")) if p.strip()]
    if not paragraphs:
        return Book(fallback_title, [])
    return Book(fallback_title, [Chapter(fallback_title, [TextBlock([Para(p) for p in paragraphs])])])


def _split_long(chapters, limit=12000):
    """Chapters are kept under ~12k characters so that laying one out stays quick. Also returns,
    for every original chapter, the index of its first part."""
    out, first_part = [], []
    for ch in chapters:
        first_part.append(len(out))
        if ch.length <= limit:
            out.append(ch)
            continue
        state = {"n": 1, "blocks": [], "part": [], "size": 0}

        def flush_text():
            if state["part"]:
                state["blocks"].append(TextBlock(state["part"]))
                state["part"] = []

        def flush_part():
            flush_text()
            if state["blocks"]:
                out.append(Chapter(ch.title if state["n"] == 1 else "%s · %d" % (ch.title, state["n"]), state["blocks"]))
                state["n"] += 1
            state["blocks"], state["size"] = [], 0

        for block in ch.blocks:
            if isinstance(block, ImageBlock):
                flush_text()
                state["blocks"].append(block)
                state["size"] += 1
                continue
            for p in block.paragraphs:
                length = u16(p.text)
                if state["size"] + length > limit and (state["part"] or state["blocks"]):
                    flush_part()
                if length > limit:          # a single monstrous paragraph is cut hard
                    o = 0
                    while len(p.text) - o > limit:
                        cut = p.text.rfind(" ", o, o + limit + 1) - o
                        if cut < limit // 2:
                            cut = limit
                        state["part"].append(p.slice(o, o + cut))
                        o += cut
                        o += len(p.text[o:]) - len(p.text[o:].lstrip())
                        flush_part()
                    if o < len(p.text):
                        state["part"].append(p.slice(o, len(p.text)))
                        state["size"] += u16(p.text[o:])
                else:
                    state["part"].append(p)
                    state["size"] += length + 1
        flush_part()
    return out, first_part


# ------------------------------------------------------------------------------------------
# The shelf: library.json and a copy of each book, as on the phone. A book is copied in when it
# is opened, so the original can move; its place is one (chapter, character) pair.
# ------------------------------------------------------------------------------------------

def _now():
    return int(time.time() * 1000)


def _write_private(path, text):
    """Written beside and moved into place, readable by this account only where the system
    knows what that means: the configuration holds the library's password."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


class Library:
    def __init__(self):
        os.makedirs(BOOKS_DIR, exist_ok=True)
        self.lock = threading.RLock()
        self.cache = {}
        try:
            with open(LIBRARY_FILE, encoding="utf-8") as fh:
                self.books = [b for b in json.load(fh).get("books", []) if b.get("id") and b.get("fileName")]
        except Exception:
            self.books = []
        self.moved = []         # (old entry, new entry): the same book under another entry or address, for the window to finish
        self._sort()

    def _sort(self):
        """Most recently opened first."""
        self.books.sort(key=lambda b: -max(b.get("opened", 0), b.get("added", 0)))

    def _save(self):
        self._sort()
        try:
            _write_private(LIBRARY_FILE, json.dumps({"books": self.books}, ensure_ascii=False, indent=1))
        except OSError:
            pass

    def get(self, book_id):
        return next((b for b in self.books if b["id"] == book_id), None)

    def by_source(self, source):
        return next((b for b in self.books if b.get("source") == source), None)

    def path(self, entry):
        return os.path.join(BOOKS_DIR, entry["fileName"])

    def save_position(self, book_id, chapter, char_offset, progress, when=None, article=None):
        """`when` is given for a place read on another device: it keeps the date it was read.
        `article` = the chapter the article being read begins with, in a magazine: its own place
        is kept too, so that it reopens there."""
        with self.lock:
            e = self.get(book_id)
            if e:
                e.update(chapter=chapter, charOffset=char_offset, progress=progress, opened=when or _now())
                if article is not None:
                    e.setdefault("places", {})[str(article)] = [chapter, char_offset]
                self._save()

    def link(self, book_id, source, source_name):
        """A book of the shelf that was just sent to the drive: from now on a book of the library, by that address and that file name."""
        with self.lock:
            e = self.get(book_id)
            if e:
                before = dict(e)
                e.update(source=source, sourceName=source_name)
                self._save()
                self._moved(before, e)

    def _moved(self, old, new):
        """The same book goes on under another entry or address: its highlights follow it now,
        what else is to be done (the note under its old name) is left to the window."""
        if move_highlights(old, new):
            self.moved.append((dict(old), dict(new)))

    def same_as(self, new, source):
        """The copy on the shelf that a book just opened replaces, keeping its place and its
        highlights: from the same place on the drive; else the same book (`same_book`) — for a
        book of the library, only a copy that is not on the drive itself; for a file opened
        here, also one with the same title and format, which is how a new copy of a book opened
        again has always found its page. Copies that never had their fingerprint learn it here."""
        if source:
            found = self.by_source(source)
            if found:
                return found
        changed = False
        for b in self.books:
            if not b.get("fingerprint") and b["format"] == new["format"]:
                b["fingerprint"], b["bookId"] = book_fingerprint(self.path(b)), epub_id(self.path(b), b["format"])
                changed = True
        if changed:
            self._save()
        if source:
            return next((b for b in self.books if not from_library(b) and same_book(b, new)), None)
        return (next((b for b in self.books if same_book(b, new)), None)
                or next((b for b in self.books if b["title"] == new["title"] and b["format"] == new["format"]), None))

    def remove(self, book_id):
        with self.lock:
            e = self.get(book_id)
            if not e:
                return
            try:
                os.remove(self.path(e))
            except OSError:
                pass
            self.cache.pop(e["fileName"], None)
            self.books = [b for b in self.books if b["id"] != book_id]
            self._save()

    def add(self, source_path, display_name, source=None, move=False, modified=0):
        """Copy a file onto the shelf (or move it, for a download), parsing it once to make sure
        it can be read. The same book again replaces the old copy but keeps its place. Blocking."""
        tmp = os.path.join(BOOKS_DIR, "import.tmp")
        if move:
            shutil.move(source_path, tmp)
        else:
            shutil.copyfile(source_path, tmp)
        try:
            fmt = detect(tmp, display_name)
            fallback = display_name.rsplit(".", 1)[0].replace("_", " ") if "." in display_name else display_name
            book = parse_book(tmp, fmt, fallback)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        with self.lock:
            book_id = _base36(_now())
            while self.get(book_id):
                book_id = _base36(int(book_id, 36) + 1)
            file_name = "%s.%s" % (book_id, fmt.lower())
            target = os.path.join(BOOKS_DIR, file_name)
            os.replace(tmp, target)
            self.cache[file_name] = book
            fingerprint, book_uid = book_fingerprint(target), epub_id(target, fmt)
            same = self.same_as({"title": book.title, "format": fmt, "fingerprint": fingerprint, "bookId": book_uid}, source)
            entry = {"id": book_id, "fileName": file_name, "title": book.title, "format": fmt, "added": _now(),
                     "opened": same["opened"] if same else 0, "chapter": same["chapter"] if same else 0,
                     "charOffset": same["charOffset"] if same else 0, "progress": same["progress"] if same else 0,
                     "magazine": book.magazine is not None, "source": source or (same.get("source") if same else None),
                     # the file's name: the drive's for a book of the library, else as it was opened, for the day it is sent to the library
                     "sourceName": display_name if source or not (same and same.get("source")) else same.get("sourceName"),
                     "fingerprint": fingerprint, "bookId": book_uid,
                     # the drive's last change of the file: when an issue came out, as far as we know
                     "sourceModified": modified if source else (same.get("sourceModified", 0) if same else 0)}
            if same:
                try:
                    os.remove(self.path(same))
                except OSError:
                    pass
                self.cache.pop(same["fileName"], None)
                self.books = [b for b in self.books if b["id"] != same["id"]]
            self.books.append(entry)
            self._save()
            if same:
                self._moved(same, entry)
            return entry

    def book(self, entry):
        """Parse (or take from the cache) a book. Blocking."""
        found = self.cache.get(entry["fileName"])
        if found:
            return found
        book = parse_book(self.path(entry), entry["format"], entry["title"])
        with self.lock:
            self.cache[entry["fileName"]] = book
            if (book.magazine is not None) != bool(entry.get("magazine")):
                entry["magazine"] = book.magazine is not None
                self._save()
        return book


def _base36(n):
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out or "0"


# ------------------------------------------------------------------------------------------
# Papers in PDF: paper2epub.py (next to this file) turns one into an EPUB, in a Python
# environment of its own (Marker and torch, about 2 GB) set up once in the app's data folder.
# The app itself never imports them; the converter runs as a separate process.
# ------------------------------------------------------------------------------------------

CONVERTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper2epub.py")
# Only where the app runs as a Python script with the converter beside it (the .deb, the
# PKGBUILD, the source): the Windows and macOS builds are frozen, with no Python to make an
# environment with.
PAPERS_POSSIBLE = not getattr(sys, "frozen", False) and os.path.isfile(CONVERTER)
if PAPERS_POSSIBLE:
    OPEN_FILTER += " *.pdf"     # a PDF is a paper: see paper2epub.py
PAPERS_ENV = os.path.join(DATA_DIR, "paper-converter")
PAPERS_WORK = os.path.join(DATA_DIR, "papers")
# Known to work together; torch is the CPU build: the converter reads the PDF's own text, a
# graphics card would not make it faster.
CONVERTER_PACKAGES = [
    ["torch==2.14.1", "torchvision==0.29.1", "--index-url", "https://download.pytorch.org/whl/cpu"],
    ["marker-pdf==2.0.0", "pylatexenc==2.11"],
]


def is_pdf(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def converter_python():
    return os.path.join(PAPERS_ENV, "Scripts" if sys.platform == "win32" else "bin", "python.exe" if sys.platform == "win32" else "python")


def _pins():
    return " ".join(p for packages in CONVERTER_PACKAGES for p in packages if "==" in p)


def converter_ready():
    """Set up, with the packages this version of the app wants (a newer one sets it up again)."""
    try:
        with open(os.path.join(PAPERS_ENV, "ready")) as fh:
            return os.path.isfile(CONVERTER) and fh.read() == _pins()
    except OSError:
        return False


def _quiet(command, log):
    """Runs a command, its output into the log; an error carries the last line of it."""
    with open(log, "ab") as fh:
        done = subprocess.run(command, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    if done.returncode:
        try:
            with open(log, "rb") as fh:
                last = [l for l in fh.read().decode("utf-8", "replace").splitlines() if l.strip()][-1:]
        except OSError:
            last = []
        raise IOError(last[0].strip() if last else "exit %d" % done.returncode)


def set_up_converter(step):
    """Blocking. `step(n, of)` before each of the steps: the environment, torch, Marker, its
    models. A step that fails can simply be run again."""
    os.makedirs(DATA_DIR, exist_ok=True)
    log = os.path.join(DATA_DIR, "paper-converter.log")
    steps = 2 + len(CONVERTER_PACKAGES)
    step(1, steps)
    if not os.path.isfile(converter_python()):
        try:
            _quiet([sys.executable, "-m", "venv", PAPERS_ENV], log)
        except IOError as exc:
            shutil.rmtree(PAPERS_ENV, ignore_errors=True)
            raise IOError("%s (python3-venv?)" % exc)
    pip = [converter_python(), "-m", "pip", "install", "--disable-pip-version-check", "-q"]
    for i, packages in enumerate(CONVERTER_PACKAGES):
        step(2 + i, steps)
        _quiet(pip + packages, log)
    step(steps, steps)          # the models, downloaded once
    _quiet([converter_python(), "-I", "-c", "from marker.models import create_model_dict; create_model_dict()"], log)
    with open(os.path.join(PAPERS_ENV, "ready"), "w") as fh:
        fh.write(_pins())


def convert_paper(pdf_path, step, notice=None):
    """Blocking: the EPUB made of the paper, in PAPERS_WORK. `step(word, page, of)` as the
    converter goes; `notice(word)` for what it says besides ("no-ocr": a scan, no Tesseract)."""
    os.makedirs(PAPERS_WORK, exist_ok=True)
    out = os.path.join(PAPERS_WORK, "%s.epub" % _base36(_now()))
    log = os.path.join(DATA_DIR, "paper-converter.log")
    env = dict(os.environ, PYTHONUNBUFFERED="1", TQDM_DISABLE="1")
    error = None
    with open(log, "ab") as err:
        process = subprocess.Popen([converter_python(), "-I", CONVERTER, "--progress", pdf_path, out],
                                   stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL, env=env)
        for line in process.stdout:
            try:
                said = json.loads(line)
            except ValueError:
                continue
            if "step" in said:
                step(said["step"], said.get("page"), said.get("of"))
            elif "notice" in said and notice:
                notice(said["notice"])
            elif "error" in said:
                error = said["error"]
        process.wait()
    if process.returncode or not os.path.isfile(out):
        try:
            os.remove(out)
        except OSError:
            pass
        raise IOError(error or "exit %d" % process.returncode)
    return out


# ------------------------------------------------------------------------------------------
# The library on a drive: a WebDAV server or a public kDrive share link. A folder is named by an
# opaque reference, so a scan can be stopped and carried on later. Nothing is downloaded until a
# book is asked for.
# ------------------------------------------------------------------------------------------

BOOK_EXTENSIONS = ("epub", "mobi", "azw", "azw3", "fb2")     # no PDF; no TXT, a drive is full of them
TRANSCRIPTS_FOLDER = "transcriptions"       # where Reader's Podcasts puts what was said in an episode, a small book each
MAX_FOLDERS, PARALLEL, ATTEMPTS, RETRY_PAUSE = 20000, 3, 3, 2      # the pause grows: 2 s, then 8 s


class WrongLogin(IOError):
    pass


def _ext(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def skip_folder(name):
    """Hidden folders and the server's own bins are never worth walking."""
    return name.startswith(".") or name.lower() in ("trash", "lost+found")


def _check(response):
    if response.status_code in (401, 403):
        raise WrongLogin("wrong login")
    if response.status_code != 207 and not 200 <= response.status_code < 300:
        raise IOError("HTTP %d" % response.status_code)


def remote_title(book):
    return (book["name"].rsplit(".", 1)[0] if "." in book["name"] else book["name"]).replace("_", " ")


def remote_folder_name(book):
    return book["folder"].rsplit("/", 1)[-1]


def remote_author(book):
    """The author as far as the drive tells it: what precedes " - " in the file name, else the
    folder's name, where libraries file one author per folder."""
    title = remote_title(book)
    return title.split(" - ")[0].strip() if " - " in title else remote_folder_name(book)


_SEPARATORS = re.compile(r"[\s_\-–—.,;:()\[\]'’\"«»]+")


def plain_text(text):
    """Text as searched: lower case, accents and other marks taken off, every separator a space."""
    bare = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
    return _SEPARATORS.sub(" ", bare).strip()


def search_books(books, query):
    """The books whose name, author or folder carries every word of `query`, accents and case
    aside ("maigret 1950" finds "Simenon - Maigret et la vieille dame.epub" in "Books/1950s").
    An empty query finds nothing: the list is asked for, not spilled."""
    words = plain_text(query).split()
    if not words:
        return []
    found = []
    for b in books:
        text = plain_text(" ".join((remote_title(b), remote_author(b), b["folder"].replace("/", " "))))
        if all(w in text for w in words):
            found.append(b)
    return found


_PROPFIND = ('<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/>'
             '<d:getcontentlength/><d:getlastmodified/><d:creationdate/></d:prop></d:propfind>')


class WebDav:
    def __init__(self, url, username, password):
        self.base = url.strip() if url.strip().endswith("/") else url.strip() + "/"
        self.session = requests.Session()
        self.session.auth = (username.encode("utf-8"), password.encode("utf-8"))
        self.session.headers["User-Agent"] = AGENT

    def roots(self):
        return [self.base]

    def folder_ref(self, path):
        """The address of a folder named by its path below the top of the drive ("" = the top)."""
        return self.base + "".join(quote(p, safe="") + "/" for p in path.split("/") if p)

    def folder_path(self, ref):
        """The path below the top of the drive of a folder's address, decoded."""
        return "/".join(unquote(p) for p in self._relative(ref).split("/") if p)

    def list_all(self):
        """One request for the whole tree. Many servers refuse it, or quietly answer for one
        level only."""
        try:
            deep = self._propfind(self.base, "infinity", 600)
        except Exception:
            return None
        if not any(is_dir and "/" in self._relative(href) for href, is_dir, _s, _m in deep):
            return None
        return [b for b in (self._book(i) for i in deep if not i[1]) if b]

    def list(self, folder):
        items = self._propfind(folder, "1", 90)
        return ([href for href, is_dir, _s, _m in items
                 if is_dir and not skip_folder(unquote(href.rstrip("/").rsplit("/", 1)[-1]))],
                [b for b in (self._book(i) for i in items if not i[1]) if b])

    def _book(self, item):
        href, _is_dir, size, modified = item
        rel = self._relative(href)
        name = unquote(rel.rsplit("/", 1)[-1])
        if _ext(name) not in BOOK_EXTENSIONS:
            return None
        parts = [unquote(p) for p in rel.split("/")[:-1] if p]
        if any(skip_folder(p) for p in parts):
            return None
        book = {"name": name, "folder": "/".join(parts), "ref": href, "size": size, "modified": modified}
        created = getattr(self, "created", {}).get(href)
        if created:
            book["created"] = created
        return book

    def _relative(self, href):
        """The path of an address below the base, still percent-encoded."""
        base_path = urlparse(self.base).path.rstrip("/")
        path = urlparse(href).path
        return (path[len(base_path):] if path.startswith(base_path) else path).strip("/")

    def _propfind(self, url, depth, timeout):
        r = self.session.request("PROPFIND", url, data=_PROPFIND, stream=True, timeout=(30, timeout),
                                 headers={"Depth": depth, "Content-Type": "application/xml"})
        try:
            _check(r)
            r.raw.decode_content = True
            return self._parse(r.raw, url)
        finally:
            r.close()

    def _parse(self, stream, requested):
        """The multistatus answer is read as it comes: a whole drive may be tens of megabytes."""
        out = []
        href, is_dir, size, modified = None, False, 0, 0
        self.created = getattr(self, "created", {})
        created = 0
        for event, node in ET.iterparse(stream, events=("start", "end")):
            tag = node.tag.rsplit("}", 1)[-1]
            if event == "start":
                if tag == "response":
                    href, is_dir, size, modified, created = None, False, 0, 0, 0
                continue
            if tag == "href" and href is None:
                href = (node.text or "").strip()
            elif tag == "collection":
                is_dir = True
            elif tag == "getcontentlength":
                try:
                    size = int((node.text or "").strip())
                except ValueError:
                    size = 0
            elif tag == "getlastmodified":
                try:
                    modified = int(parsedate_to_datetime((node.text or "").strip()).timestamp() * 1000)
                except Exception:
                    modified = 0
            elif tag == "creationdate":
                created = iso_ms((node.text or "").strip())
            elif tag == "response":
                if href:
                    full = urljoin(requested, href)
                    if full.rstrip("/") != requested.rstrip("/"):
                        out.append((full, is_dir, size, modified))
                        if created:
                            self.created[full] = created
                node.clear()
        return out

    def download(self, book, dest, progress=None):
        with self.session.get(book["ref"], stream=True, timeout=(30, 90)) as r:
            _check(r)
            _save_stream(r, dest, progress)

    def file_ref(self, folder, name):
        """The address of a file named `name` in the folder at this path below the top of the drive."""
        return self.folder_ref(folder) + quote(name, safe="")

    def exists(self, ref):
        """Whether something is at this address."""
        r = self.session.head(ref, timeout=(30, 90))
        if r.status_code == 404:
            return False
        _check(r)
        return True

    def upload(self, ref, path):
        """Put a file on the drive at this address, in place of whatever was there. A book may be
        large and the line slow: ten minutes."""
        with open(path, "rb") as fh:
            _check(self.session.put(ref, data=fh, timeout=(30, 600)))

    def read_range(self, ref, start, length, size=0):
        """Some bytes of a file: `length` from `start`, or the last `length` when `start` is None.
        (bytes, whole size); None when the server sends the whole file instead (no ranges).
        With the file's size known, the end is asked for from where it starts: kDrive drops the
        connection on a range from the end longer than the file."""
        if start is None and size:
            start = max(0, size - length)
        if start is not None and size:
            length = min(length, max(1, size - start))
        spec = "bytes=-%d" % length if start is None else "bytes=%d-%d" % (start, start + length - 1)
        for attempt in range(3):
            try:
                with self.session.get(ref, headers={"Range": spec, "Accept-Encoding": "identity"}, stream=True, timeout=(30, 60)) as r:
                    if r.status_code == 416:
                        return b"", 0
                    _check(r)
                    if r.status_code != 206:
                        return None
                    total = r.headers.get("Content-Range", "").rsplit("/", 1)[-1]
                    return r.content, int(total) if total.isdigit() else 0
            except requests.ConnectionError:
                # the server closed a connection kept for the next request: once more on a new one
                if attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))


def _save_stream(response, dest, progress):
    total = int(response.headers.get("Content-Length") or 0)
    done = 0
    with open(dest, "wb") as fh:
        for chunk in response.iter_content(256 * 1024):
            fh.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(int(done * 100 / total))


def library_configured(cfg):
    """An address with a login: the library is a WebDAV folder the app may read and write."""
    return bool(cfg.get("url", "").strip() and cfg.get("username", "").strip() and cfg.get("password"))


def library_started(cfg):
    return bool(cfg.get("url") or cfg.get("username") or cfg.get("password"))


def remote_for(cfg):
    """None when nothing usable is set."""
    try:
        if library_configured(cfg):
            return WebDav(cfg["url"], cfg["username"].strip(), cfg["password"])
    except Exception:
        pass
    return None


def iso_ms(text):
    """An ISO 8601 date (WebDAV's creationdate) in milliseconds, 0 when unreadable."""
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        try:
            return int(parsedate_to_datetime(text).timestamp() * 1000)
        except Exception:
            return 0


# ------------------------------------------------------------------------------------------
# News: the newspapers' and magazines' issues among the library's books, told by their contents
# page as the reader tells a magazine (a section, a title per article in the nav; or articles
# that start with a section and a headline), read on the drive without fetching the book: the
# end of the EPUB (its zip directory), then its package and its nav, a few kilobytes each.
# ------------------------------------------------------------------------------------------

def _zip_directory(read, tail_size=65536):
    """The zip's entries, name → (method, compressed size, offset of its local header)."""
    got = read(None, tail_size)
    if got is None:
        return None
    tail, total = got
    at = tail.rfind(b"PK\x05\x06")
    if at < 0 or len(tail) < at + 22:
        return None
    cd_size, cd_offset = struct.unpack_from("<II", tail, at + 12)
    tail_start = (total or len(tail)) - len(tail)
    if cd_offset >= tail_start:
        cd = tail[cd_offset - tail_start:cd_offset - tail_start + cd_size]
    else:
        got = read(cd_offset, cd_size)
        if got is None:
            return None
        cd = got[0]
    entries, i = {}, 0
    while i + 46 <= len(cd) and cd[i:i + 4] == b"PK\x01\x02":
        method, = struct.unpack_from("<H", cd, i + 10)
        comp, = struct.unpack_from("<I", cd, i + 20)
        n, x, c = struct.unpack_from("<HHH", cd, i + 28)
        offset, = struct.unpack_from("<I", cd, i + 42)
        name = cd[i + 46:i + 46 + n].decode("utf-8", "replace")
        entries[name] = (method, comp, offset)
        i += 46 + n + x + c
    return entries


def _zip_member(read, entries, name, limit=400000):
    import zlib
    if name not in entries:
        name = next((n for n in entries if n.lower() == name.lower()), None)
        if name is None:
            return None
    method, comp, offset = entries[name]
    if comp > limit:
        return None
    got = read(offset, 30 + 1024 + comp)
    if got is None:
        return None
    head = got[0]
    if head[:4] != b"PK\x03\x04":
        return None
    n, x = struct.unpack_from("<HH", head, 26)
    data = head[30 + n + x:30 + n + x + comp]
    if method == 0:
        return data
    if method == 8:
        try:
            return zlib.decompressobj(-15).decompress(data)
        except zlib.error:
            return None
    return None


def epub_is_news(read):
    return epub_kind(read)[0]


_DC_DATE = re.compile(r"<dc:date[^>]*>\s*(\d{4})-(\d{2})-(\d{2})")


def epub_kind(read):
    """(news, issue date): news = True for an issue of a newspaper or a magazine, or a gathering
    of articles (a newsletter's, a channel's summaries: a contents page of titles, with or without
    their authors); False for a book; None when the drive would not say (no byte ranges, a broken
    file). The issue's date is its own (dc:date), in milliseconds, 0 when it has none.
    `read(start, length)` as WebDav.read_range."""
    entries = _zip_directory(read)
    if entries is None:
        return None, 0
    opf_name = next((n for n in entries if n.lower().endswith(".opf")), None)
    if opf_name is None:
        return None, 0
    opf = _zip_member(read, entries, opf_name)
    if opf is None:
        return None, 0
    opf = opf.decode("utf-8", "replace")
    m = _DC_DATE.search(opf)
    try:
        date = int(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).timestamp() * 1000) if m else 0
    except ValueError:
        date = 0
    base = opf_name.rsplit("/", 1)[0] + "/" if "/" in opf_name else ""
    items = {}
    nav = None
    for tag in re.findall(r"<item\b[^>]*>", opf, re.I):
        m_id = re.search(r'\bid="([^"]+)"', tag)
        m_href = re.search(r'\bhref="([^"]+)"', tag)
        if not m_href:
            continue
        href = posixpath.normpath(base + unquote(m_href.group(1).split("#")[0]))
        if m_id:
            items[m_id.group(1)] = href
        if re.search(r'properties="[^"]*\bnav\b', tag):
            nav = href
    if nav:
        text = _zip_member(read, entries, nav)
        if text is not None:
            text = text.decode("utf-8", "replace")
            # one title per article (a publisher may call its contents' own heading "toc-title")
            if re.search(r'<span\b[^>]*class="[^"]*\btoc-title\b', text):
                return True, date
    # signature B: the articles themselves start with their section and a headline
    spine = [items[i] for i in re.findall(r'<itemref\b[^>]*idref="([^"]+)"', opf) if i in items]
    if len(spine) < 3:
        return False, date
    picks = [spine[len(spine) * k // 4] for k in (1, 2, 3)]
    structured = 0
    for name in picks:
        text = _zip_member(read, entries, name)
        if text is None:
            continue
        text = text.decode("utf-8", "replace")
        if re.search(r'<p\b[^>]*class="[^"]*\bcategory\b', text, re.I) and re.search(r"<h1\b", text, re.I):
            structured += 1
    return structured >= 2, date


def news_date(book, kind=None):
    """When an issue came out: its own date (dc:date) when it says, else what the drive knows —
    the file's creation, else its last change. A file the drive made again (repaired, copied)
    keeps its issue's date."""
    return (kind or {}).get("d") or book.get("created") or book.get("modified") or 0


def source_key(cfg):
    return "dav:%s@%s" % (cfg.get("url", "").strip(), cfg.get("username", "").strip())


def from_library(entry):
    """A book fetched from the drive: the one kind that has highlights, and a place that travels."""
    return (entry.get("source") or "").startswith(("http://", "https://"))


def can_send(cfg, entry):
    """A book of the shelf may be sent to the library when there is one, it is not from it, and
    a sync of the drive would list its kind (not plain text)."""
    return library_configured(cfg) and entry.get("format") != TXT and not from_library(entry)


def send_name(entry):
    """The file name a book goes to the drive under: the one it was opened with when it was a
    book's, else its title, with the format's extension."""
    kept = entry.get("sourceName") if _ext(entry.get("sourceName") or "") in BOOK_EXTENSIONS else None
    ext = kept.rsplit(".", 1)[1] if kept else entry["format"].lower()
    stem = kept.rsplit(".", 1)[0] if kept else entry["title"]
    stem = " ".join(re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", stem).split())[:120] or "book"
    return "%s.%s" % (stem, ext)


# Which folders of the drive make the library. Empty = the whole drive. A chosen folder stands
# for everything inside it; the folder Reader's Podcasts sends its transcripts to is always in.
# A folder left out is out with everything inside it, whatever else is chosen: neither shown nor
# walked by a sync. Both lists are kept in the settings; a sync walks only the chosen folders,
# skips the ones left out, and only the remaining books are shown.

def chosen_folders(cfg):
    """The folders chosen in the settings: paths below the top of the drive, sorted."""
    return sorted(f for f in (cfg.get("library_folders") or []) if isinstance(f, str) and f)


def excluded_folders(cfg):
    """The folders left out in the settings: paths below the top of the drive, sorted."""
    return sorted(f for f in (cfg.get("library_excluded") or []) if isinstance(f, str) and f)


def folder_under(parent, folder):
    return parent == "" or folder == parent or folder.startswith(parent + "/")


def left_out(excluded, folder):
    """True when the folder, or a folder above it, was left out."""
    return any(e and folder_under(e, folder) for e in excluded)


def in_library(chosen, folder, excluded=()):
    return not left_out(excluded, folder) and (not chosen or folder_under(TRANSCRIPTS_FOLDER, folder) or any(folder_under(c, folder) for c in chosen))


def part_of(chosen, folder):
    """The chosen folder a folder is part of without being chosen itself; None otherwise."""
    for c in chosen:
        if c != folder and folder_under(c, folder):
            return c
    if chosen and folder != TRANSCRIPTS_FOLDER and folder_under(TRANSCRIPTS_FOLDER, folder):
        return TRANSCRIPTS_FOLDER
    return None


def top_folder(folder):
    """The top folder a folder is in: its first name; "" for the top of the drive itself."""
    return folder.split("/", 1)[0]


def relative_folder(base, folder):
    """A folder's path as seen from inside `base`: "" for the base itself."""
    if folder == base:
        return ""
    return folder if not base else folder[len(base) + 1:]


def grouped_folders(books, top):
    """The folders these books are in, as (path, count, latest change, folders spanned): every
    folder, or the top folders only, each standing for everything inside it (the books of the
    top of the drive stand by themselves)."""
    groups = {}
    for b in books:
        groups.setdefault(top_folder(b["folder"]) if top else b["folder"], []).append(b)
    return [(p, len(bs), max(b["modified"] for b in bs), len({b["folder"] for b in bs}) if top else 1) for p, bs in groups.items()]


def sort_folders(folders, order):
    if order == "NEWEST":
        return sorted(folders, key=lambda f: (-f[2], f[0].lower()))
    if order == "COUNT":
        return sorted(folders, key=lambda f: (-f[1], f[0].lower()))
    return sorted(folders, key=lambda f: f[0].lower())


def sort_books(books, order, opened=None):
    """The books of one list in the chosen order; `opened` = when this app last opened each, by its reference."""
    opened = opened or {}
    if order == "OLDEST":
        return sorted(books, key=lambda b: (b["modified"], b["name"].lower()))
    if order == "NAME":
        return sorted(books, key=lambda b: b["name"].lower())
    if order == "AUTHOR":     # books whose author is not known go last, by name
        return sorted(books, key=lambda b: (not remote_author(b), remote_author(b).lower(), remote_title(b).lower()))
    if order == "OPENED":
        return sorted(books, key=lambda b: (-opened.get(b["ref"], 0), b["name"].lower()))
    return sorted(books, key=lambda b: (-b["modified"], b["name"].lower()))


BOOK_ORDERS = ("NEWEST", "OLDEST", "NAME", "AUTHOR", "OPENED")
FOLDER_ORDERS = ("NAME", "NEWEST", "COUNT")
SHELF_ORDERS = ("OPENED", "TITLE", "ADDED")


def order_name(order):
    return {"NEWEST": _("newest first"), "OLDEST": _("oldest first"), "NAME": _("by name"), "AUTHOR": _("by author"),
            "OPENED": _("last opened first"), "COUNT": _("most books first"), "TITLE": _("by title"), "ADDED": _("last added first")}.get(order, "")


def library_roots(chosen):
    """Where a sync starts: the chosen folders and the transcripts', or the top of the drive."""
    return list(dict.fromkeys(chosen + [TRANSCRIPTS_FOLDER])) if chosen else [""]


def merge_folder(books, folder, subfolders, found):
    """The books after one folder was listed again: its own books are replaced by what was
    found, and the books of subfolders the drive no longer has (not in `subfolders`) are
    dropped, with everything below them. Books elsewhere stay as they were."""
    kept_sub = set(subfolders)
    kept = []
    for b in books:
        if b["folder"] == folder:
            continue
        if not folder_under(folder, b["folder"]):
            kept.append(b)
            continue
        below = b["folder"] if folder == "" else b["folder"][len(folder) + 1:]
        child = below.split("/", 1)[0] if folder == "" else folder + "/" + below.split("/", 1)[0]
        if child in kept_sub:
            kept.append(b)
    return kept + [b for b in found if b["folder"] == folder]


# ------------------------------------------------------------------------------------------
# Magazines: the issues of one magazine are told apart from those of another by the title of the
# issue (dc:title), the date taken off — « 24 heures — Edition du mardi 3 novembre 2026 » is an
# issue of « 24 heures ». The title, not the publisher: one publisher prints several papers, and
# the pipeline names its podcasts « Huberman Lab — <episode> — Édition du … ». The name is what
# comes before the first dash between spaces when what follows has a figure in it; otherwise the
# title up to its date, if it has one; otherwise the whole title. Only magazines are grouped.
# Rule for rule the phone's Magazines.
# ------------------------------------------------------------------------------------------

_DASHES = (" — ", " – ", " - ")
_MONTH = r"[^\W\d_]{3,}\.?"
_ISSUE_DATE = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|\b\d{1,2}(er|\.)?\s+" + _MONTH + r"\s+\d{4}|\b" + _MONTH + r"\s+\d{1,2}(st|nd|rd|th)?,?\s+\d{4}"
    r"|\b" + _MONTH + r"\s+\d{4}(?![-./]?\d)|\b(n[°ºo]\.?|nr\.?|no\.?|#)\s*\d+", re.I)
_TRAILING = re.compile(r"[\s,;:·|(\-–—]+$|\s+(du|de|des|del|de la|do|da|of|the|vom|von|am|le|la|el|edition|édition|edición|edição|ausgabe|issue|выпуск|от)$", re.I)
_WEEKDAY = re.compile(r"\s+(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|monday|tuesday|wednesday|thursday|friday|saturday|sunday|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)$", re.I)
_LEADING = re.compile(r"^(du|de|des|del|do|da|of|vom|von|от)\s+", re.I)


def magazine_name(title):
    """The magazine's name in the title of one of its issues."""
    t = title.strip()
    for dash in _DASHES:
        i = t.find(dash)
        if i > 0 and any(c.isdigit() for c in t[i:]):
            return t[:i].strip()
    m = _ISSUE_DATE.search(t)
    if not m or m.start() == 0:
        return t
    head = t[:m.start()]
    while True:
        nxt = _WEEKDAY.sub("", _TRAILING.sub("", head))
        if nxt == head:
            break
        head = nxt
    return head.strip() or t


def magazine_key(title):
    """What issues of the same magazine share: the name in lower case, accents and spacing aside."""
    bare = unicodedata.normalize("NFD", magazine_name(title).lower())
    return re.sub(r"\s+", " ", "".join(c for c in bare if not unicodedata.combining(c))).strip()


def magazine_issue(title):
    """The title of the issue without the magazine's name: « Edition du mercredi 4 novembre 2026 »."""
    name, t = magazine_name(title), title.strip()
    if name == t:
        return t
    rest = _LEADING.sub("", t[len(name):].lstrip(" —–-,:|·")) if t.startswith(name) else t
    return rest or t


def issue_time(entry):
    """When an issue came out, as far as this computer knows: the drive's date, else when it came here."""
    return entry.get("sourceModified") or entry.get("added", 0)


def magazine_issues(entries, key):
    """The issues of one magazine on the shelf, newest first."""
    return sorted((e for e in entries if e.get("magazine") and magazine_key(e["title"]) == key),
                  key=lambda e: (-issue_time(e), [-ord(c) for c in e["title"]]))


def magazine_groups(entries):
    """The issues of each magazine with two or more on the shelf, by key, newest first."""
    keys = {}
    for e in entries:
        if e.get("magazine"):
            keys.setdefault(magazine_key(e["title"]), []).append(e)
    return {k: magazine_issues(v, k) for k, v in keys.items() if k and len(v) >= 2}


# ------------------------------------------------------------------------------------------
# Followed folders: a folder of the drive followed for its new books (the day's paper). `seen` =
# its books that are no longer new: there when it was first followed (all but the latest day's),
# fetched since, or removed from the shelf. Nothing is fetched by itself: a click on a followed
# folder lists that folder again and fetches its new books. Rule for rule the phone's Follow.
# ------------------------------------------------------------------------------------------

def first_seen(books, folder, tz=None):
    """What counts as seen when a folder is first followed: everything in it but the books of its
    latest day, which are new at once — following a folder of daily papers gives today's."""
    inside = [b for b in books if folder_under(folder, b["folder"])]
    newest = max((b.get("modified", 0) for b in inside), default=0)
    if newest <= 0:
        return []

    def day(ms):
        return datetime.fromtimestamp(ms / 1000.0, tz).date()
    latest = day(newest)
    return sorted(b["ref"] for b in inside if b.get("modified", 0) <= 0 or day(b["modified"]) != latest)


def fresh_books(books, followed, on_shelf):
    """The new books of a followed folder (and of the folders inside it), newest first."""
    seen = set(followed.get("seen", ()))
    found = [b for b in books if folder_under(followed["folder"], b["folder"]) and b["ref"] not in seen and b["ref"] not in on_shelf]
    found.sort(key=lambda b: b["name"].lower(), reverse=True)
    found.sort(key=lambda b: -b.get("modified", 0))
    return found


def prune_seen(followed, books):
    """What is still worth remembering as seen: the books the folder holds now."""
    there = {b["ref"] for b in books if folder_under(followed["folder"], b["folder"])}
    return dict(followed, seen=[r for r in followed.get("seen", ()) if r in there])


class Following:
    """The followed folders, kept in follow.json next to the library's index."""

    def __init__(self):
        try:
            with open(FOLLOW_FILE, encoding="utf-8") as fh:
                self.folders = [f for f in json.load(fh).get("folders", []) if f.get("folder")]
        except Exception:
            self.folders = []
        self.lock = threading.RLock()

    def _save(self):
        try:
            _write_private(FOLLOW_FILE, json.dumps({"folders": self.folders}, ensure_ascii=False, indent=1))
        except OSError:
            pass

    def get(self, folder):
        return next((f for f in self.folders if f["folder"] == folder), None)

    def follow(self, folder, books):
        with self.lock:
            if folder and not self.get(folder):
                self.folders.append({"folder": folder, "seen": first_seen(books, folder), "checkedAt": 0})
                self._save()

    def unfollow(self, folder):
        with self.lock:
            self.folders = [f for f in self.folders if f["folder"] != folder]
            self._save()

    def seen(self, folder, ref):
        with self.lock:
            f = self.get(folder)
            if f and ref not in f["seen"]:
                f["seen"].append(ref)
                self._save()

    def removed(self, entry):
        """A book of the library left the shelf: it does not come back as new."""
        ref = entry.get("source")
        if not ref:
            return
        with self.lock:
            changed = False
            for f in self.folders:
                if ref not in f["seen"]:
                    f["seen"].append(ref)
                    changed = True
            if changed:
                self._save()

    def checked(self, folder, books):
        with self.lock:
            self.folders = [dict(prune_seen(f, books), checkedAt=_now()) if f["folder"] == folder else f for f in self.folders]
            self._save()

    def forget(self):
        with self.lock:
            self.folders = []
            self._save()


EMPTY_INDEX = {"scannedAt": 0, "source": "", "books": [], "complete": True, "frontier": [], "failed": [], "folders": 0}


class Walk:
    """The folders a sync has still to list, by what the last syncs found: those that held books,
    then those on the way to them, then the others; each folder once, known by its path (the
    drive's own address and the one made from a path may be written differently). The phone's
    RemoteLibrary.Walk."""

    def __init__(self, known, path_of):
        self.known = set(known)
        self.path_of = path_of
        self.on_the_way = {"/".join(f.split("/")[:i]) for f in self.known for i in range(len(f.split("/")))}
        self.ranks = ([], [], [])
        self.seen = set()

    def rank(self, path):
        return 0 if path in self.known else 1 if path in self.on_the_way else 2

    def add(self, ref):
        path = self.path_of(ref)
        if path not in self.seen:
            self.seen.add(path)
            self.ranks[self.rank(path)].append(ref)

    def retry(self, ref):
        """Back first in line (a refused login: the sync carries on from it)."""
        self.seen.add(self.path_of(ref))
        self.ranks[0].insert(0, ref)

    def next(self):
        for r in self.ranks:
            if r:
                return r.pop(0)
        return None

    def all(self):
        return [ref for r in self.ranks for ref in r]


class RemoteLibrary:
    """The drive's e-books as scanned so far, kept on disk so the library opens at once.

    A sync walks the tree (the chosen folders only, when some are chosen) and merges each folder
    as it is listed: what is known stays on the screen, new books appear, books gone from the
    drive go, and the list never empties while the drive is walked. `complete` = the whole walk
    was done; otherwise `frontier` holds the folders still to list, so a sync that was stopped
    (window closed, network gone) carries on where it was. `failed` = folders the server would
    not list after three tries."""

    def __init__(self):
        try:
            with open(INDEX_FILE, encoding="utf-8") as fh:
                self.index = dict(EMPTY_INDEX, **json.load(fh))
        except Exception:
            self.index = dict(EMPTY_INDEX)
        self.progress = None        # (folders, books, failed) while a scan runs
        self.error = None
        self.thread = None
        self.stop = threading.Event()
        self.changed = 0            # bumped at every step, for the window to notice
        self.refreshing = False
        self.relisting = threading.Lock()
        try:
            with open(KINDS_FILE, encoding="utf-8") as fh:
                self.kinds = json.load(fh)
        except Exception:
            self.kinds = {}         # book address → {"s": size, "m": modified, "news": True/False/None, "t": tries}
        self.sorting = None         # (done, of) while the books are being told apart
        self.sort_thread = None
        self.sort_lock = threading.Lock()
        self.sort_queue = []        # what is still to look at, the newest first
        self.sort_busy = set()

    @property
    def scanning(self):
        return self.thread is not None and self.thread.is_alive()

    def matches(self, cfg):
        return self.index["source"] == source_key(cfg) and self.index["scannedAt"] > 0

    def shown(self, cfg):
        """The books in the library: those of the chosen folders, or all of them."""
        chosen, excluded = chosen_folders(cfg), excluded_folders(cfg)
        return [b for b in self.index["books"] if in_library(chosen, b["folder"], excluded)]

    def folders(self, cfg):
        """The folders of the library, in the chosen order, as (path, count, latest change, folders
        spanned): every folder, or the top folders only when the library is grouped by them."""
        return sort_folders(grouped_folders(self.shown(cfg), bool(cfg.get("library_top_folders"))), cfg.get("folder_sort", "NAME"))

    def known_folders(self):
        """Every folder the drive was seen to hold books in, chosen or not, as (path, count): what the choice is made from."""
        return [(p, n) for p, n, _m, _s in sort_folders(grouped_folders(self.index["books"], False), "NAME")]

    def books(self, cfg, folder, subfolders=False):
        """The books of one folder, alone or with everything inside it; left-out folders stay out."""
        return [b for b in self.shown(cfg) if (folder_under(folder, b["folder"]) if subfolders else b["folder"] == folder)]

    def has_subfolders(self, cfg, folder):
        """True when a folder holds books in folders inside it."""
        return any(b["folder"] != folder and folder_under(folder, b["folder"]) for b in self.shown(cfg))

    def sync_quietly(self, cfg):
        """The sync after the folders of the library were chosen again: the same walk, by itself."""
        if not self.scanning and self.matches(cfg):
            self.scan(cfg, False)

    def scan(self, cfg, fresh):
        """From scratch when `fresh` (or when the account changed); else carrying on an
        unfinished walk; else the whole library again."""
        remote = remote_for(cfg)
        if self.scanning or remote is None:
            return
        fresh = fresh or not self.matches(cfg)
        if fresh:
            start = dict(EMPTY_INDEX, source=source_key(cfg), complete=False)
        elif not self.index["complete"]:
            start = dict(self.index)
        else:
            start = dict(self.index, complete=False, frontier=[], folders=0)
        from_top = fresh or self.index["complete"]
        self.error = None
        self.stop = threading.Event()
        self.progress = (start["folders"], len(start["books"]), len(start["failed"]))
        self.thread = threading.Thread(target=self._run, args=(remote, start, from_top, chosen_folders(cfg), self.stop, excluded_folders(cfg)), daemon=True)
        self.thread.start()

    def cancel(self):
        self.stop.set()
        self.progress = None
        self.changed += 1

    def refresh_folder(self, cfg, name=TRANSCRIPTS_FOLDER):
        """One folder of the drive looked at again, without walking the rest: the one Reader's
        Podcasts sends its transcripts to, so that a transcript made this morning is in the
        library when it is opened, with no scan to ask for. In the background."""
        if remote_for(cfg) is None or self.scanning or not self.matches(cfg) or not self.index["complete"] or self.refreshing or left_out(excluded_folders(cfg), name):
            return

        self.refreshing = True

        def run():
            try:
                self.relist(cfg, name)
            except Exception:
                pass                                # could not be read: what was known stays
            finally:
                self.refreshing = False

        threading.Thread(target=run, daemon=True).start()

    def relist(self, cfg, name):
        """One folder listed again with the folders inside it, and merged into the library: its
        books replaced by what the drive has now. While a sync runs, the sync brings them; for
        another account than the index's, nothing is done. Blocking; raises when the drive could
        not be read, leaving the index as it was."""
        remote = remote_for(cfg)
        if remote is None:
            raise IOError("no library")
        if self.scanning or not self.matches(cfg):
            return
        excluded = excluded_folders(cfg)
        with self.relisting:
            self.refreshing = True
            try:
                source = self.index["source"]
                top = remote.folder_ref(name)
                found, queue = [], [top]
                while queue and len(found) < 20000:
                    folder = queue.pop(0)
                    try:
                        dirs, books = remote.list(folder)
                    except IOError as exc:
                        if folder == top and "404" in str(exc):
                            break                   # no such folder (yet, or any more): nothing in it
                        raise
                    queue.extend(d for d in dirs if not (excluded and left_out(excluded, remote.folder_path(d))))     # a folder left out stays out
                    found.extend(books)
                if self.scanning or self.index["source"] != source:
                    return
                kept = [b for b in self.index["books"] if not folder_under(name, b["folder"]) or left_out(excluded, b["folder"])]
                merged = kept + found
                key = lambda b: (b["ref"], b.get("modified", 0), b.get("size", 0))
                if sorted(map(key, merged)) != sorted(map(key, self.index["books"])):
                    self._save(dict(self.index, books=merged))
            finally:
                self.refreshing = False

    def forget(self):
        self.cancel()
        self.index = dict(EMPTY_INDEX)
        self.kinds = {}
        for f in (INDEX_FILE, KINDS_FILE):
            try:
                os.remove(f)
            except OSError:
                pass

    # ---- news: which books are issues of a newspaper or a magazine ----

    def kind_of(self, book):
        k = self.kinds.get(book["ref"])
        if k and k.get("v") == KINDS_VERSION and k.get("s") == book.get("size") and k.get("m") == book.get("modified"):
            return k
        return None

    def issue_date(self, book):
        return news_date(book, self.kind_of(book))

    def news(self, cfg):
        """The library's newspapers, magazines and gatherings of articles, the newest issue first."""
        found = [b for b in self.shown(cfg) if (self.kind_of(b) or {}).get("news")]
        return sorted(found, key=lambda b: (self.issue_date(b), b.get("created") or b.get("modified") or 0), reverse=True)

    def unsorted(self, cfg):
        """The EPUBs not yet looked at (or changed since), and those the drive would not answer for, three times at most."""
        out = []
        for b in self.shown(cfg):
            if _ext(b["name"]) != "epub":
                continue
            k = self.kind_of(b)
            if k is None or (k.get("news") is None and k.get("t", 0) < ATTEMPTS):
                out.append(b)
        return out

    def sort_books(self, cfg, known=None):
        """Tells the news from the books, in the background, a few kilobytes read per book. Books
        on this computer are told by what the reader already found (`known`: address → magazine)."""
        running = self.sort_thread is not None and self.sort_thread.is_alive()
        todo = self.unsorted(cfg)
        if running:
            # books new to the library go before what the first pass has still to look at
            with self.sort_lock:
                queued = {b["ref"] for b in self.sort_queue}
                new = [b for b in todo if b["ref"] not in queued and b["ref"] not in self.sort_busy]
                if new:
                    self.sort_queue[:0] = sorted(new, key=news_date, reverse=True)
                    self.sorting = (self.sorting[0], self.sorting[1] + len(new)) if self.sorting else (0, len(new))
            return
        known = known or {}
        told = [b for b in todo if b["ref"] in known]
        for b in told:
            self.kinds[b["ref"]] = {"s": b.get("size"), "m": b.get("modified"), "news": bool(known[b["ref"]]), "v": KINDS_VERSION}
        todo = [b for b in todo if b["ref"] not in known]
        if not todo:
            if told:
                self._save_kinds()
            return
        remote = remote_for(cfg)
        if remote is None:
            return
        self.sorting = (0, len(todo))
        lock = self.sort_lock
        queue = self.sort_queue
        queue[:] = sorted(todo, key=news_date, reverse=True)       # the latest first: that is where the news is

        def worker():
            while True:
                with lock:
                    if not queue or self.stop.is_set():
                        return
                    b = queue.pop(0)
                    self.sort_busy.add(b["ref"])
                try:
                    news, date = epub_kind(lambda start, length: remote.read_range(b["ref"], start, length, b.get("size") or 0))
                except WrongLogin:
                    with lock:
                        queue.clear()
                    return
                except Exception:
                    news, date = None, 0
                with lock:
                    self.sort_busy.discard(b["ref"])
                    old = self.kinds.get(b["ref"]) or {}
                    tries = (old.get("t", 0) + 1) if news is None and old.get("m") == b.get("modified") else (1 if news is None else 0)
                    self.kinds[b["ref"]] = {"s": b.get("size"), "m": b.get("modified"), "news": news, "t": tries, "d": date, "v": KINDS_VERSION}
                    done = self.sorting[0] + 1 if self.sorting else 1
                    self.sorting = (done, len(todo))
                    if done % 25 == 0:
                        self._save_kinds()
                self.changed += 1

        def run():
            workers = [threading.Thread(target=worker, daemon=True) for _i in range(PARALLEL)]
            for w in workers:
                w.start()
            for w in workers:
                w.join()
            self.sorting = None
            self._save_kinds()
            self.changed += 1

        self.sort_thread = threading.Thread(target=run, daemon=True)
        self.sort_thread.start()

    def _save_kinds(self):
        try:
            _write_private(KINDS_FILE, json.dumps(self.kinds, ensure_ascii=False))
        except OSError:
            pass

    def send(self, cfg, folder, name, path):
        """A book of the shelf sent to the drive, into this folder of the library, under this file
        name — or the next free one, when a file of that name is there already: nothing on the
        drive is ever written over. Listed in the library at once, as the drive names it, with no
        sync to wait for. Blocking; returns the book as the drive lists it."""
        remote = remote_for(cfg)
        if remote is None:
            raise IOError("no library")
        stem, ext = (name.rsplit(".", 1) + [""])[:2] if "." in name else (name, "")
        chosen = name
        for n in range(2, 21):
            if not remote.exists(remote.file_ref(folder, chosen)):
                break
            chosen = "%s (%d)%s" % (stem, n, "." + ext if ext else "")
        ref = remote.file_ref(folder, chosen)
        remote.upload(ref, path)
        # the drive's own listing of the folder, so the book is known by the address a sync would give it
        try:
            book = next((b for b in remote.list(remote.folder_ref(folder))[1] if b["name"] == chosen), None)
        except Exception:
            book = None
        if book is None:
            book = {"name": chosen, "folder": folder, "ref": ref, "size": os.path.getsize(path), "modified": _now()}
        if self.matches(cfg) or not self.index["scannedAt"]:
            books = [b for b in self.index["books"] if b["ref"] != book["ref"] and not (b["folder"] == folder and b["name"] == chosen)]
            self._save(dict(self.index, source=source_key(cfg), books=books + [book]))
        return book

    def _save(self, index):
        self.index = index
        try:
            _write_private(INDEX_FILE, json.dumps(index, ensure_ascii=False))
        except OSError:
            pass
        self.changed += 1

    def _run(self, remote, start, from_top, chosen, stop, excluded=()):
        try:
            self._walk(remote, start, from_top, chosen, stop, excluded)
        except Exception as exc:
            if not stop.is_set():
                self.error = exc
        finally:
            if not stop.is_set():
                self.progress = None
            self.changed += 1

    def _walk(self, remote, index, from_top, chosen, stop, excluded=()):
        roots = [remote.folder_ref(p) for p in library_roots(chosen)]
        if from_top:
            # the whole tree at once, when the server allows it and the whole drive is wanted
            everything = remote.list_all() if not chosen else None
            if everything is not None:
                self._save(dict(index, books=everything, complete=True, frontier=[], failed=[],
                                folders=len({b["folder"] for b in everything}), scannedAt=_now()))
                return
            index = dict(index, frontier=roots)
        # A pool of workers over one queue, so a slow folder holds nobody else back. Folders that
        # failed last time get another chance now. Each folder listed is merged into the books
        # known so far, so the library stays whole on the screen while the drive is walked.
        # The queue goes by what the last syncs found: the folders that held books first (asked for
        # at once, without waiting for the walk to reach them), then the folders on the way to
        # them, then the rest of the drive, where new books are only looked for.
        lock = threading.Lock()
        books = list(index["books"])
        queue = Walk({b["folder"] for b in books if in_library(chosen, b["folder"], excluded)}, remote.folder_path)
        for f in index["frontier"] + index["failed"]:
            queue.add(f)
        seeded = set()
        if from_top:
            for path in sorted(queue.known):
                ref = remote.folder_ref(path)
                seeded.add(ref)
                queue.add(ref)
        in_flight, failed = set(), []
        state = {"folders": index["folders"], "fatal": None, "dirty": False}

        def snapshot(complete):
            with lock:
                state["dirty"] = False
                return dict(index, books=list(books), frontier=[] if complete else queue.all() + sorted(in_flight),
                            failed=list(failed), folders=state["folders"], scannedAt=_now(), complete=complete)

        def worker():
            while not stop.is_set():
                with lock:
                    if state["fatal"] or state["folders"] + len(in_flight) >= MAX_FOLDERS:
                        return
                    folder = queue.next()
                    if folder is not None:
                        in_flight.add(folder)
                    elif not in_flight:
                        return
                    else:
                        folder = None
                if folder is None:
                    time.sleep(0.2)
                    continue
                result, error = self._list_with_retries(remote, folder, stop)
                with lock:
                    in_flight.discard(folder)
                    if result:
                        # a folder left out is not walked; its books stay known, so it can be taken back
                        for d in result[0]:
                            if not left_out(excluded, remote.folder_path(d)):
                                queue.add(d)
                        books[:] = merge_folder(books, remote.folder_path(folder), [remote.folder_path(d) for d in result[0]], result[1])
                        state["folders"] += 1
                    elif isinstance(error, WrongLogin):
                        # Back on the list: once the login is put right, the scan carries on
                        # from this very folder instead of finding nothing left to do.
                        state["fatal"] = error
                        queue.retry(folder)
                    elif (folder in roots or folder in seeded) and "404" in str(error):
                        # A chosen folder the drive no longer has (or no transcripts folder yet) is simply empty.
                        path = remote.folder_path(folder)
                        books[:] = [b for b in books if not folder_under(path, b["folder"])]
                    else:
                        failed.append(folder)
                    state["dirty"] = True
                    self.progress = (state["folders"], len(books), len(failed))
                self.changed += 1

        workers = [threading.Thread(target=worker, daemon=True) for _i in range(PARALLEL)]
        for w in workers:
            w.start()
        # The checkpoint: every two seconds while anything changed, and once more at the end.
        last = time.time()
        while any(w.is_alive() for w in workers):
            time.sleep(0.1)
            if time.time() - last >= 2:
                last = time.time()
                if state["dirty"]:
                    self._save(snapshot(False))
        if stop.is_set():
            # Stopped by hand: what was in flight goes back on the list of what is left to do.
            self._save(snapshot(False))
            return
        if state["fatal"]:
            self._save(snapshot(False))
            raise state["fatal"]
        self._save(snapshot(True))

    def _list_with_retries(self, remote, folder, stop):
        """Servers hiccup (timeouts, 429, 5xx): three tries with a pause; a refused login stops
        everything, and a folder that is not there (404) is not asked for again."""
        attempt = 0
        while True:
            try:
                return remote.list(folder), None
            except WrongLogin as exc:
                return None, exc
            except (IOError, requests.RequestException, ET.ParseError, ValueError) as exc:
                attempt += 1
                if "404" in str(exc) or attempt >= ATTEMPTS or stop.wait(RETRY_PAUSE * attempt * attempt):
                    return None, exc


# ------------------------------------------------------------------------------------------
# Highlights and comments, for the books of the library. A highlight is a passage of one
# chapter — (chapter, first character, the one after the last), counted as the phone counts
# them — with the words themselves and, if one was written, a comment.
#
# They travel in a file that lies next to the book on the drive, "<book file>.highlights.json",
# with the place the book was left at. And a note per book lists them in Reader's Notes: a
# plain-text file written into the folder "Reader's Books" of the notes folder, which Reader's
# Notes shows read-only.
# ------------------------------------------------------------------------------------------

HIGHLIGHTS_FORMAT = "readers-highlights"
HIGHLIGHTS_SUFFIX = ".highlights.json"
BOOKS_FOLDER = "Reader's Books"
OBJECT = "\ufffc"          # the place of a picture in the text of a chapter


def chapter_text(chapter):
    """The text of a chapter as its characters are counted: every paragraph followed by a line
    break, a picture standing for one character."""
    return "".join("".join(p.text + "\n" for p in b.paragraphs) if isinstance(b, TextBlock) else OBJECT
                   for b in chapter.blocks)


class Text16:
    """A text addressed in UTF-16 units, which is how places in a book are counted."""
    def __init__(self, text):
        self.data = text.encode("utf-16-le")
        self.length = len(self.data) // 2

    def cut(self, start, end):
        return self.data[2 * max(0, start):2 * max(0, end)].decode("utf-16-le", "ignore")

    def is_word(self, i):
        c = self.cut(i, i + 1)
        return bool(c) and (c.isalnum() or c in "'’-" or 0xD800 <= ord(c[0]) <= 0xDFFF)

    def words(self, start, end):
        """The passage widened to whole words, and narrowed to what is not blank at its ends."""
        start, end = max(0, min(start, end)), min(self.length, max(start, end))
        while start > 0 and self.is_word(start - 1) and self.is_word(start):
            start -= 1
        while end < self.length and end > 0 and self.is_word(end - 1) and self.is_word(end):
            end += 1
        while start < end and not self.cut(start, start + 1).strip():
            start += 1
        while end > start and not self.cut(end - 1, end).strip():
            end -= 1
        return start, end


# ------------------------------------------------------------------------------------------
# The same book in two copies — a book opened from a file and the same book fetched from the
# library later — so that the highlights made in the one go to the other. Either rule is
# enough: the same bytes (SHA-256 of the file: the very file is on the drive); or, for EPUBs,
# the same package identifier (the dc:identifier the OPF names as its unique-identifier) AND
# the same title — the drive's copy was rewritten by a library tool, the book is still that
# one; the title too, because some tools stamp one identifier on every book they make. A title
# alone is never enough. The same rules as the phone's (BookIdentity).
# ------------------------------------------------------------------------------------------

def book_fingerprint(path):
    try:
        digest = sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return ""


def package_id(opf):
    """The identifier the package names as its own, read from the OPF's text."""
    pkg = re.search(r"<(?:\w+:)?package\b[^>]*>", opf, re.I)
    ref = pkg and re.search(r"""unique-identifier\s*=\s*["']([^"']+)["']""", pkg.group(0))
    if not ref:
        return ""
    tag = re.search(r"""<dc:identifier\b[^>]*\bid\s*=\s*["']""" + re.escape(ref.group(1)) + r"""["'][^>]*>([^<]*)</dc:identifier>""", opf, re.I)
    return tag.group(1).strip() if tag else ""


def epub_id(path, fmt):
    """The EPUB's own identifier, or "" (another format, or none given)."""
    if fmt != EPUB:
        return ""
    try:
        with zipfile.ZipFile(path) as z:
            container = z.read("META-INF/container.xml").decode("utf-8", "replace")
            found = re.search(r'full-path="([^"]+)"', container)
            return package_id(z.read(found.group(1)).decode("utf-8", "replace")) if found else ""
    except Exception:
        return ""


def same_book(a, b):
    return bool((a.get("fingerprint") and a.get("fingerprint") == b.get("fingerprint"))
                or (a.get("bookId") and a.get("bookId") == b.get("bookId") and a.get("title") == b.get("title")))


def highlight_key(entry):
    return sha1((entry.get("source") or entry["id"]).encode("utf-8")).hexdigest()


def book_file_name(entry, index_books=()):
    """The name of the book's file on the drive: kept when it was fetched, else read from its
    address, else from the list of the drive's books."""
    if entry.get("sourceName"):
        return entry["sourceName"]
    source = entry.get("source") or ""
    if source.startswith(("http://", "https://")):
        return unquote(urlparse(source).path.rstrip("/").rsplit("/", 1)[-1])
    return next((b["name"] for b in index_books if b["ref"] == source), entry["title"])


def load_highlights(entry):
    try:
        with open(os.path.join(HIGHLIGHTS_DIR, highlight_key(entry) + ".json"), encoding="utf-8") as fh:
            data = json.load(fh)
        return [h for h in data.get("highlights", []) if isinstance(h, dict) and h.get("id")], bool(data.get("dirty"))
    except Exception:
        return [], False


def save_highlights(entry, highlights, dirty, name=None):
    """The highlights kept on this computer, in the form of the file next to a book of the
    library (for a book of the shelf alone, the only copy), plus `dirty`: not yet where they go —
    the drive's file, or the note in Reader's Notes."""
    try:
        _write_private(os.path.join(HIGHLIGHTS_DIR, highlight_key(entry) + ".json"),
                       json.dumps({"format": HIGHLIGHTS_FORMAT, "version": 1, "book": name or book_file_name(entry),
                                   "highlights": highlights, "dirty": dirty}, ensure_ascii=False, indent=1))
    except OSError:
        pass


def move_highlights(old, new):
    """The same book under another entry or address: its highlights go with it, folded into what
    the new one already has by the drive's rule, marked as still to be sent. True when there
    were some."""
    a, b = highlight_key(old), highlight_key(new)
    if a == b:
        return False
    mine, _dirty = load_highlights(old)
    try:
        os.remove(os.path.join(HIGHLIGHTS_DIR, a + ".json"))
    except OSError:
        pass
    if not mine:
        return False
    save_highlights(new, merge_highlights(mine, load_highlights(new)[0]), True)
    return True


def new_highlight(chapter, start, end, text, comment=""):
    now = _now()
    return {"id": uuid.uuid4().hex[:12], "chapter": chapter, "start": start, "end": end, "text": text,
            "comment": comment, "created": now, "modified": now, "deleted": False}


def merge_highlights(ours, theirs):
    """Both lists folded into one: the same highlight (same id) is the one changed last, and one
    removed stays in the list as removed, so that it does not come back from the other side."""
    merged = {}
    for h in list(theirs) + list(ours):
        old = merged.get(h["id"])
        if old is None or (h.get("modified", 0), bool(h.get("deleted"))) > (old.get("modified", 0), bool(old.get("deleted"))):
            merged[h["id"]] = h
    return sorted(merged.values(), key=lambda h: (h.get("chapter", 0), h.get("start", 0), h["id"]))


def live_highlights(highlights):
    """What is shown: not removed, in the order of the book."""
    return sorted((h for h in highlights if not h.get("deleted")), key=lambda h: (h.get("chapter", 0), h.get("start", 0)))


def anchor_highlights(highlights, book):
    """A highlight whose words are no longer where it says (a book file replaced by another
    edition) is looked for in its chapter; found, it follows them. Returns the list to show."""
    texts = {}
    out = []
    for h in live_highlights(highlights):
        c = h.get("chapter", 0)
        if not 0 <= c < len(book.chapters):
            continue
        if c not in texts:
            texts[c] = Text16(chapter_text(book.chapters[c]))
        t, words = texts[c], h.get("text", "")
        if words and t.cut(h["start"], h["end"]) != words:
            raw = chapter_text(book.chapters[c])
            at = raw.find(words)
            if at < 0:
                continue
            start = u16(raw[:at])
            h = dict(h, start=start, end=start + u16(words))
        out.append(h)
    return out


_QUOTES = {"fr": ("«\u00a0", "\u00a0»"), "en": ("“", "”"), "de": ("„", "“")}


def note_text(book_name, highlights):
    """The note Reader's Notes shows for a book: its name, then every passage between quotation
    marks, in the order of the book, each followed by its comment when it has one."""
    name = book_name.rsplit(".", 1)[0] if "." in book_name else book_name
    opening, closing = _QUOTES.get(LANG, ("«", "»"))
    parts = [name]
    for h in live_highlights(highlights):
        parts.append(opening + " ".join(h.get("text", "").split()) + closing)
        if (h.get("comment") or "").strip():
            parts.append(h["comment"].strip())
    return "\n\n".join(parts) + "\n"


def note_file_name(book_name):
    """The same rule as Reader's Notes for the name of a note's file."""
    name = book_name.rsplit(".", 1)[0] if "." in book_name else book_name
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', " ", name)
    base = re.sub(r"[ \t\n\x0b\f\r]+", " ", base).strip().rstrip(".")
    return (base or "untitled") + ".txt"


def _dav_session(username, password):
    session = requests.Session()
    session.auth = (username.encode("utf-8"), password.encode("utf-8"))
    session.headers["User-Agent"] = AGENT
    return session


def sidecar_address(cfg, entry):
    """Where the highlights of a book and the place it was left at are kept for every device:
    in a file next to the book. None for a book that did not come from the library."""
    if not from_library(entry) or not library_configured(cfg):
        return None
    return entry["source"] + HIGHLIGHTS_SUFFIX


def position_of(entry):
    """Where a book was left and when, as it travels: None when it was never opened."""
    if not entry.get("opened"):
        return None
    return {"chapter": entry.get("chapter", 0), "charOffset": entry.get("charOffset", 0),
            "progress": entry.get("progress", 0), "modified": entry["opened"]}


def sync_sidecar(cfg, entry, highlights, name=None, position=None):
    """Ours and the drive's folded together and written back where they differ: the highlights
    one by one, and the place in the book, where the one read last wins. Returns (highlights,
    whether the drive's highlights had to be written, the place, whether that place is the
    drive's and newer than ours). Blocking."""
    address = sidecar_address(cfg, entry)
    if not address:
        return highlights, False, position, False
    session = _dav_session(cfg["username"].strip(), cfg["password"])
    r = session.get(address, timeout=(30, 60))
    theirs, there = [], None
    if r.status_code != 404:
        _check(r)
        try:
            data = r.json()
            if isinstance(data, dict) and data.get("format") == HIGHLIGHTS_FORMAT:
                theirs = [h for h in data.get("highlights", []) if isinstance(h, dict) and h.get("id")]
                if isinstance(data.get("position"), dict) and isinstance(data["position"].get("modified"), int):
                    there = data["position"]
        except ValueError:
            theirs = []
    merged = merge_highlights(highlights, theirs)
    marks = merged != merge_highlights(theirs, []) and bool(merged or r.status_code != 404)
    ours_newer = bool(position) and (there is None or position["modified"] > there["modified"])
    theirs_newer = there is not None and (not position or there["modified"] > position["modified"])
    best = position if ours_newer or there is None else there
    if not marks and not ours_newer:
        return merged, False, best, theirs_newer
    body = {"format": HIGHLIGHTS_FORMAT, "version": 1, "book": name or book_file_name(entry), "highlights": merged}
    if best:
        body["position"] = {k: best.get(k, 0) for k in ("chapter", "charOffset", "progress", "modified")}
    body = json.dumps(body, ensure_ascii=False, indent=1).encode("utf-8")
    _check(session.put(address, data=body, headers={"Content-Type": "application/json"}, timeout=(30, 60)))
    return merged, marks, best, theirs_newer


def sync_book(cfg, entry, name, position=None):
    """One book brought in step with the drive: its highlights, its note in Reader's Notes, the
    place it was left at. Returns (highlights, the drive's place when it is the newer one, else
    None), or None when nothing here was to be kept (changed meanwhile). Blocking."""
    before, dirty = load_highlights(entry)
    if not sidecar_address(cfg, entry):
        # a book of the shelf alone: its highlights stay here, only its note goes to Reader's Notes
        if note_only(cfg, entry):
            write_note(cfg, name, before)
            if load_highlights(entry)[0] != before:
                return None
            save_highlights(entry, before, False, name)
        return before, None
    merged, marks, best, theirs_newer = sync_sidecar(cfg, entry, before, name, position or position_of(entry))
    # The note is written again whenever the drive's highlights were: two devices that met there
    # at the same moment leave a note that lacks what one of them had.
    if dirty or marks or merged != before:
        write_note(cfg, name, merged)
    if load_highlights(entry)[0] != before:         # changed here meanwhile: the next turn takes it
        return None
    if dirty or merged != before:
        save_highlights(entry, merged, False, name)
    return merged, (best if theirs_newer else None)


def note_only(cfg, entry):
    """A book of the shelf alone whose highlights changed since its note was last written, with a notes folder to write it to."""
    return not from_library(entry) and notes_account(cfg) is not None and load_highlights(entry)[1]


def notes_account(cfg):
    """The folder of Reader's Notes and the login for it — the library's unless another is given.
    None when no folder is named."""
    address = cfg.get("notes_url", "").strip()
    if not address:
        return None
    username = cfg.get("notes_username", "").strip() or cfg.get("username", "").strip()
    password = cfg.get("notes_password") or cfg.get("password", "")
    if not username or not password:
        return None
    return (address if address.endswith("/") else address + "/"), username, password


def write_note(cfg, book_name, highlights):
    """The book's note in Reader's Notes: written when there is something to say, removed when
    there is nothing left. Blocking."""
    account = notes_account(cfg)
    if not account:
        return
    address, username, password = account
    session = _dav_session(username, password)
    folder = address + quote(BOOKS_FOLDER, safe="") + "/"
    target = folder + quote(note_file_name(book_name), safe="")
    if not live_highlights(highlights):
        r = session.delete(target, timeout=(30, 60))
        if r.status_code != 404:
            _check(r)
        return
    r = session.request("MKCOL", folder, timeout=(30, 60))
    if r.status_code not in (201, 405, 301):         # made, or there already
        _check(r)
    _check(session.put(target, data=note_text(book_name, highlights).encode("utf-8"),
                       headers={"Content-Type": "text/plain; charset=utf-8"}, timeout=(30, 60)))


# ------------------------------------------------------------------------------------------
# The Reader's credentials file, the same for every Reader's app: one JSON file, one section
# per app. Exporting merges our section into a file that may hold the others'. It holds the
# password.
# ------------------------------------------------------------------------------------------

CREDENTIALS_FORMAT = "readers-credentials"
CREDENTIALS_SECTION = "readers-books"
CREDENTIALS_FALLBACK = "magazine-reader"          # reaches the same kind of drive
SERVER_FALLBACKS = ("readers-scanner", "readers-notes", "readers-recorder")   # their "server", never their folder
CREDENTIAL_KEYS = ("url", "username", "password")
NOTES_KEYS = ("notes_url", "notes_username", "notes_password")


class NotCredentials(Exception):
    pass


class NothingForUs(Exception):
    pass


def export_credentials(cfg, path):
    path = os.path.expanduser(path)
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            raise NotCredentials()
        if not isinstance(data, dict) or data.get("format") != CREDENTIALS_FORMAT:
            raise NotCredentials()
    data["format"], data["version"] = CREDENTIALS_FORMAT, 1
    data[CREDENTIALS_SECTION] = {k: cfg[k] for k in CREDENTIAL_KEYS + NOTES_KEYS if cfg.get(k)}
    _write_private(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_credentials(text):
    """What a file brings for us: ({url, username, password} with None for what it does
    not say, whether it came from another app's section)."""
    try:
        root = json.loads(text)
    except Exception:
        raise NotCredentials()
    if not isinstance(root, dict) or root.get("format") != CREDENTIALS_FORMAT:
        raise NotCredentials()

    def text_of(section, key):
        v = section.get(key)
        return v if isinstance(v, str) else None

    for name, fallback in ((CREDENTIALS_SECTION, False), (CREDENTIALS_FALLBACK, True)):
        s = root.get(name)
        if isinstance(s, dict):
            account = {k: text_of(s, k) for k in CREDENTIAL_KEYS}
            if any(v is not None for v in account.values()):
                return account, fallback
    for name in SERVER_FALLBACKS:
        s = root.get(name)
        if isinstance(s, dict) and text_of(s, "server") is not None:
            return {"url": text_of(s, "server"), "username": text_of(s, "username"),
                    "password": text_of(s, "password")}, True
    raise NothingForUs()


def apply_credentials(cfg, account):
    """What the file names replaces what is set; what it leaves out stays."""
    set_library_url(cfg, account["url"] if account["url"] is not None else cfg.get("url", ""))
    cfg.update(username=(account["username"] if account["username"] is not None else cfg.get("username", "")).strip(),
               password=account["password"] if account["password"] is not None else cfg.get("password", ""))


def set_library_url(cfg, url):
    """The library's address. Another drive: its folders are not these, and the choice is to be offered again."""
    if url.strip() != cfg.get("url", "").strip():
        cfg.update(library_folders=[], library_excluded=[], library_folders_asked=False)
        cfg.pop("send_folder", None)
    cfg["url"] = url.strip()


def read_notes_account(text):
    """The folder of Reader's Notes as a credentials file names it: in our own section, or in
    Reader's Notes' (its server and its folder make the address). {} when it says nothing."""
    try:
        root = json.loads(text)
    except Exception:
        return {}
    ours = root.get(CREDENTIALS_SECTION) if isinstance(root, dict) else None
    if isinstance(ours, dict) and isinstance(ours.get("notes_url"), str):
        return {k: ours[k] for k in NOTES_KEYS if isinstance(ours.get(k), str)}
    notes = root.get("readers-notes") if isinstance(root, dict) else None
    if isinstance(notes, dict) and isinstance(notes.get("server"), str) and notes["server"].strip():
        folder = (notes.get("folder") if isinstance(notes.get("folder"), str) else "") or "Notes"
        folder = folder.strip().strip("/") or "Notes"
        return {"notes_url": notes["server"].strip().rstrip("/") + "/" + "/".join(quote(p, safe="") for p in folder.split("/")) + "/",
                "notes_username": notes.get("username") if isinstance(notes.get("username"), str) else "",
                "notes_password": notes.get("password") if isinstance(notes.get("password"), str) else ""}
    return {}


def import_credentials(cfg, path):
    with open(os.path.expanduser(path), encoding="utf-8") as fh:
        text = fh.read()
    notes = read_notes_account(text)
    try:
        account, fallback = read_credentials(text)
    except NothingForUs:
        if not notes:
            raise
        account, fallback = None, True
    if account is not None:
        apply_credentials(cfg, account)
    cfg.update(notes)
    return fallback


# ------------------------------------------------------------------------------------------
# Colour themes: the two inks (white on black, black on white), then the palettes of the Plume
# keyboard, in its order. (key, background, text, accent, text on the accent, tile, tile2, press);
# in the two inks the accent is the text colour and the tiles are the background, so they look
# as they always did. With a palette, everything that can be clicked is a rounded card in the
# « key » colour (tile) on the « surface » (bg), the mouse over it shows « press »; what only
# reads stays on the surface.
# ------------------------------------------------------------------------------------------

PALETTES = [
    ("DARK", "#000000", "#ffffff", "#ffffff", "#000000", "#000000", "#000000", "#000000"),
    ("LIGHT", "#ffffff", "#000000", "#000000", "#ffffff", "#ffffff", "#ffffff", "#ffffff"),
    ("LAVANDE", "#1f1a2e", "#f4efff", "#b8a4ff", "#1f1a2e", "#3B3352", "#2B2540", "#5A4F78"),
    ("SAUGE", "#d9e0d4", "#1e2a21", "#4c7a5b", "#ffffff", "#F7F9F4", "#B5C2B2", "#B5C2B2"),
    ("NORDIQUE", "#2e3440", "#eceff4", "#88c0d0", "#2e3440", "#3B4252", "#353B4A", "#4C566A"),
    ("TERRACOTTA", "#e6d9cc", "#2b211b", "#c25e38", "#ffffff", "#FCF7F1", "#C8B6A5", "#C8B6A5"),
    ("COQUETTE", "#f3d9dc", "#4a1f2b", "#d2455e", "#ffffff", "#FFF7F5", "#E7BFC6", "#E7BFC6"),
    ("MILITANTE", "#f2eee4", "#121212", "#e8412e", "#ffffff", "#FFFFFF", "#D8D3C6", "#D8D3C6"),
    ("TORRIDE", "#1e0d13", "#f8e9e6", "#e02a50", "#fff4f2", "#561A2C", "#34121D", "#7A2A42"),
    ("NATURE", "#2b2a24", "#f2efe4", "#d19a4e", "#2b2a24", "#3A4733", "#2F3A2B", "#566650"),
]
INKS = ("DARK", "LIGHT")
THEME_NAMES = {"DARK": "white on black", "LIGHT": "black on white", "LAVANDE": "lavender", "SAUGE": "sage",
               "NORDIQUE": "nordic", "TERRACOTTA": "terracotta", "COQUETTE": "coquette", "MILITANTE": "activist",
               "TORRIDE": "sultry", "NATURE": "nature"}


def palette(key):
    """{bg, fg, accent, on_accent, tile, tile2, press, tiles} of a theme; `tiles` is False in the
    two inks. An unknown key gives the default, white on black."""
    for name, bg, fg, accent, on_accent, tile, tile2, press in PALETTES:
        if name == key:
            return {"bg": bg, "fg": fg, "accent": accent, "on_accent": on_accent,
                    "tile": tile.lower(), "tile2": tile2.lower(), "press": press.lower(), "tiles": name not in INKS}
    return palette(PALETTES[0][0])


def next_theme(key):
    """The theme after this one, round and round."""
    keys = [p[0] for p in PALETTES]
    return keys[(keys.index(key) + 1) % len(keys)] if key in keys else keys[0]


def theme_name(key):
    return _(THEME_NAMES.get(key, THEME_NAMES["DARK"]))


def rgba(hex_colour, alpha):
    """A style-sheet rgba() of a #rrggbb colour."""
    h = hex_colour.lstrip("#")
    return "rgba(%d,%d,%d,%s)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def blend(front, back, alpha):
    """#rrggbb of `front` laid at `alpha` over `back`."""
    f, b = front.lstrip("#"), back.lstrip("#")
    return "#" + "".join("%02x" % round(int(f[i:i + 2], 16) * alpha + int(b[i:i + 2], 16) * (1 - alpha)) for i in (0, 2, 4))


def is_dark(hex_colour):
    h = hex_colour.lstrip("#")
    return (0.299 * int(h[0:2], 16) + 0.587 * int(h[2:4], 16) + 0.114 * int(h[4:6], 16)) < 128


# ------------------------------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------------------------------

DEFAULTS = {"theme": "DARK", "dark": True, "font": "sans", "text_size": "M", "reader_pt": 0, "book_serif": False,
            "keep_awake": True, "url": "", "username": "", "password": "",
            "notes_url": "", "notes_username": "", "notes_password": "",
            # the orders of a folder's books, of all books, of the folders, of the shelf; the library by top
            # folders only; a folder with the books of the folders inside it
            "library_sort": "NAME", "all_books_sort": "NEWEST", "folder_sort": "NAME", "shelf_sort": "OPENED",
            "library_top_folders": False, "library_subfolders": False,
            # the folders of the drive that make the library (empty = the whole drive); whether the choice was offered
            "library_folders": [], "library_excluded": [], "library_folders_asked": False}
AUTO_READER_PT = 13
MIN_READER_PT, MAX_READER_PT = 8, 30


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as fh:
            saved = json.load(fh)
    except Exception:
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    cfg.update(saved)
    if "theme" not in saved:        # a config from before the themes: its ink
        cfg["theme"] = "DARK" if cfg.get("dark", True) else "LIGHT"
    if cfg["theme"] not in THEME_NAMES:
        cfg["theme"] = "DARK"
    return cfg


def save_config(cfg):
    try:
        _write_private(CONFIG_FILE, json.dumps(cfg, ensure_ascii=False, indent=1))
    except OSError:
        pass


def reader_pt(cfg):
    return cfg.get("reader_pt") or AUTO_READER_PT


def when_label(millis):
    if not millis:
        return ""
    d, today = datetime.fromtimestamp(millis / 1000), datetime.now().date()
    if d.date() == today:
        return d.strftime("%H:%M")
    if d.date() == today - timedelta(days=1):
        return _("yesterday")
    month = QtCore.QLocale().toString(QtCore.QDate(d.year, d.month, d.day), "d MMM" if d.year == today.year else "d MMM yyyy")
    return month.lower()


def date_label(millis):
    if not millis:
        return ""
    d = datetime.fromtimestamp(millis / 1000)
    return QtCore.QLocale().toString(QtCore.QDate(d.year, d.month, d.day), QtCore.QLocale.ShortFormat)


def size_label(size):
    if size <= 0:
        return ""
    if size < 1000000:
        return "%d KB" % max(1, size // 1000)
    return "%.1f MB" % (size / 1e6)


# ------------------------------------------------------------------------------------------
# Pictures of one book, read from its EPUB when a page or a contents line needs them
# ------------------------------------------------------------------------------------------

class ImageStore:
    def __init__(self, path):
        self.path = path
        self.sizes = {}
        self.pixmaps = {}

    def _bytes(self, source):
        try:
            with zipfile.ZipFile(self.path) as zf:
                return zf.read(source)
        except Exception:
            return None

    def data(self, source):
        return self._bytes(source) or b""

    def size(self, source):
        """Pixel size, or None when the entry is missing or is not a picture."""
        if source not in self.sizes:
            data = self._bytes(source)
            found = None
            if data:
                buffer = QtCore.QBuffer()
                buffer.setData(data)
                buffer.open(QtCore.QIODevice.ReadOnly)
                size = QtGui.QImageReader(buffer).size()
                if size.width() > 0 and size.height() > 0:
                    found = (size.width(), size.height())
            self.sizes[source] = found
        return self.sizes[source]

    def pixmap(self, source, width, height, crop=False):
        key = (source, width, height, crop)
        if key not in self.pixmaps:
            if len(self.pixmaps) > 40:
                self.pixmaps.clear()
            image = QtGui.QImage.fromData(self._bytes(source) or b"")
            if image.isNull():
                self.pixmaps[key] = None
            elif crop:
                scaled = image.scaled(width, height, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
                x, y = (scaled.width() - width) // 2, (scaled.height() - height) // 2
                self.pixmaps[key] = QtGui.QPixmap.fromImage(scaled.copy(x, y, width, height))
            else:
                self.pixmaps[key] = QtGui.QPixmap.fromImage(
                    image.scaled(width, height, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation))
        return self.pixmaps[key]


# ------------------------------------------------------------------------------------------
# Pages. One chapter laid out at the current width and size: pages made of whole text lines and
# of pictures. A line belongs to a page only if its whole box fits, so nothing is ever cut or
# repeated; a picture is scaled to the text width (never taller than the page) and moves to the
# next page whole.
# ------------------------------------------------------------------------------------------

LINE_BREAK = " "
INDENT_EMS = 2.0            # the reader's own indent, when the book says nothing


def _u16_offsets(text):
    """For each character of a string (and its end), its place counted in UTF-16 units."""
    if len(text.encode("utf-16-le")) == 2 * len(text):
        return range(len(text) + 1)
    out, n = [], 0
    for c in text:
        out.append(n)
        n += 2 if ord(c) > 0xFFFF else 1
    out.append(n)
    return out


class TextMap:
    """Where the characters of a laid-out string are in the chapter's text: runs of the text, in
    order (laid, place, length, in UTF-16 units), with what lies between them (an indent, the line
    between two pieces of a table cell) belonging to no place."""

    def __init__(self):
        self.laid, self.place, self.length = [], [], []

    def run(self, laid, place, n):
        if n <= 0:
            return
        if self.laid and self.laid[-1] + self.length[-1] == laid and self.place[-1] + self.length[-1] == place:
            self.length[-1] += n
            return
        self.laid.append(laid)
        self.place.append(place)
        self.length.append(n)

    @staticmethod
    def _last(values, x):
        lo, hi, r = 0, len(values) - 1, -1
        while lo <= hi:
            mid = (lo + hi) // 2
            if values[mid] <= x:
                r, lo = mid, mid + 1
            else:
                hi = mid - 1
        return r

    def to_chapter(self, laid):
        if not self.laid:
            return 0
        r = max(0, self._last(self.laid, laid))
        into = laid - self.laid[r]
        return self.place[r] if into < 0 else self.place[r] + min(into, self.length[r])

    def to_laid(self, place):
        if not self.laid:
            return 0
        r = self._last(self.place, place)
        if r < 0:
            return self.laid[0]
        return self.laid[r] + min(place - self.place[r], self.length[r])


class Lines:
    """Lines first..last of one laid-out run, placed at y on the page; `x`/`clip` for a table cell."""
    def __init__(self, y, block, first, last, x=0, clip=-1):
        self.y, self.block, self.first, self.last, self.x, self.clip = y, block, first, last, x, clip
        self.start_char = block.to_chapter(block.layout.lineAt(first).textStart())


class Picture:
    def __init__(self, y, char_base, source, width, height, x=0):
        self.y, self.start_char, self.source, self.width, self.height, self.x = y, char_base, source, width, height, x


class Rule:
    """A short centred line, drawn where the book has a rule."""
    def __init__(self, y, x1, x2, place):
        self.y, self.x1, self.x2, self.start_char = y, x1, x2, place


class Grid:
    """The borders of one table row: (x, width) of each cell."""
    def __init__(self, y, height, cells, place):
        self.y, self.height, self.cells, self.start_char = y, height, cells, place


class Frame:
    """What a page is laid out with: the reader's font and dim ink, the width and height of the
    text, the screen's density, the book's pictures, and whether it is a magazine."""
    def __init__(self, font, dim, width, page_height, images, magazine=False, density=1.0):
        self.font, self.dim, self.width, self.page_height = font, dim, width, page_height
        self.images, self.magazine, self.density = images, magazine, density
        self.em = font.pixelSize()
        # Lines sit 1.7 em apart whatever the face: 1.45 times the line of the interface fonts,
        # less for a face drawn with tall line boxes of its own (Literata).
        natural = QtGui.QFontMetricsF(font).height() / max(1, font.pixelSize())
        self.spacing = 1.7 / natural if natural > 1.3 else 1.45
        self.line_step = int(round(QtGui.QFontMetricsF(font).height() * self.spacing))

    def px(self, ems):
        return int(round(ems * self.em))


CASES = UPPER | LOWER | CAPITALIZE | SMALL_CAPS


def _cases_of(p):
    look = p.look
    if look is None:
        return None
    base = look.flags & CASES
    if not base and not any(f & CASES for _a, _b, f in p.styles or ()):
        return None
    out = [base] * len(p.text)
    for a, b, f in p.styles or ():
        for k in range(a, b):
            out[k] |= f & CASES
    return out


def _cased(c, mode, prev):
    """A character as drawn in its case: one for one, so the places do not move."""
    if not mode:
        return c
    if mode & UPPER:
        u = c.upper()
    elif mode & LOWER:
        u = c.lower()
    elif mode & CAPITALIZE and c.isalpha() and (prev is None or not prev.isalnum()):
        u = c.upper()
    elif mode & SMALL_CAPS and not mode & CAPITALIZE:
        u = c.upper()
    else:
        u = c
    return u if len(u) == 1 else c


def _marker_text(look):
    m, n = look.marker, look.number
    if m == DISC:
        return "•"
    if m == CIRCLE:
        return "◦"
    if m == SQUARE:
        return "▪"
    if m == DECIMAL:
        return "%d." % n
    if m in (LOWER_ALPHA, UPPER_ALPHA):
        s, k = "", n
        if k <= 0:
            s = str(n)
        while k > 0:
            k -= 1
            s = chr(ord("a") + k % 26) + s
            k //= 26
        return (s.upper() if m == UPPER_ALPHA else s) + "."
    if m in (LOWER_ROMAN, UPPER_ROMAN):
        if not 0 < n < 4000:
            s = str(n)
        else:
            s, k = "", n
            for v, r in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
                         (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
                while k >= v:
                    s += r
                    k -= v
        return (s.upper() if m == UPPER_ROMAN else s) + "."
    return None


MARKER_GAP = 0.4           # between a marker and its item's text, in ems


def _marker_gutter(look, f):
    """The width of a list's column of markers: its widest marker in the reader's font, and the
    gap after it. 0 for what is not a list item."""
    if not look.list_marker:
        return 0
    fm = QtGui.QFontMetricsF(f.font)
    widest = 0.0
    for n in range(look.list_from, max(look.list_from, min(look.list_to, look.list_from + 400)) + 1):
        text = _marker_text(Look(marker=look.list_marker, number=n))
        if not text:
            return 0
        widest = max(widest, fm.horizontalAdvance(text))
        if look.list_marker < DECIMAL:          # a bullet is the same for every item
            break
    return int(round(widest + f.em * MARKER_GAP))


def _hard_breaks(p):
    soft = set(p.look.soft or ()) if p.look else set()
    return {k for k, c in enumerate(p.text) if c == "\n" and k not in soft}


class _Formats:
    """QTextLayout formats on a laid-out string, from flags (Para) and sizes."""

    def __init__(self, font):
        self.font, self.ranges = font, []

    def add(self, start, length, flags, size=0.0, dim=None, base_size=1.0):
        if length <= 0:
            return
        fmt = QtGui.QTextCharFormat()
        if flags & ITALIC:
            fmt.setFontItalic(True)
        if flags & BOLD:
            fmt.setFontWeight(QtGui.QFont.Bold)
        if flags & UNDERLINE:
            fmt.setFontUnderline(True)
        if flags & STRIKE:
            fmt.setFontStrikeOut(True)
        if flags & MONO:
            fmt.setFontFamily("monospace")
            fmt.setFontStyleHint(QtGui.QFont.Monospace)
        if flags & (SUPER | SUB):
            fmt.setVerticalAlignment(QtGui.QTextCharFormat.AlignSuperScript if flags & SUPER else QtGui.QTextCharFormat.AlignSubScript)
        elif size:
            fmt.setProperty(QtGui.QTextFormat.FontPixelSize, max(1, round(self.font.pixelSize() * size)))
        if dim is not None:
            fmt.setForeground(dim)
        r = QtGui.QTextLayout.FormatRange()
        r.start, r.length, r.format = start, length, fmt
        self.ranges.append(r)


class LaidBlock:
    """A run of paragraphs as one text layout, with the top and bottom of every line.

    One string for the whole run: the paragraphs are separated by line separators; the reader's
    own indent, the book's margins, indents, list markers and drop caps are where each line is put, its sizes and the rest formats on the same string. A run never has
    space between its paragraphs (a space between paragraphs starts a new run)."""

    def __init__(self, block, start, end, base, frame, no_drop=(), width=None):
        f = frame
        font = f.font
        self.map = TextMap()
        self.drops = []             # (paragraph, laid start, laid end, letters, font, x)
        self.markers = []           # (laid start, text, x of the text)
        chunks = []                 # (laid start, first px, rest px, align, drop px)
        parts, pos, place = [], 0, base
        fm = _Formats(font)
        for i in range(start, end):
            p = block.paragraphs[i]
            look = p.look
            if i > start:
                self.map.run(pos, place - 1, 1)
                parts.append(LINE_BREAK)
                pos += 1
            para_start = pos
            prev_kind = block.paragraphs[i - 1].kind if i > 0 else None
            centred = look is not None and look.align in (CENTER, RIGHT)
            indent = (i > 0 and p.kind == NORMAL and prev_kind == NORMAL and
                      (look is None or (_isnan(look.indent) and not centred and look.drop_cap == 0 and look.marker == 0
                                        and not look.flags & MONO)))
            hard = _hard_breaks(p) if look is not None else {k for k, c in enumerate(p.text) if c == "\n"}
            cases = _cases_of(p)
            u = _u16_offsets(p.text)
            laid_of = [0] * (len(p.text) + 1)
            para_chunks = [pos]
            for k, c in enumerate(p.text):
                laid_of[k] = pos
                if c == "\n":
                    if k in hard:
                        parts.append(LINE_BREAK)
                        pos += 1
                        para_chunks.append(pos)
                    else:
                        parts.append(" ")
                        pos += 1
                else:
                    d = _cased(c, cases[k], p.text[k - 1] if k else None) if cases else c
                    parts.append(d)
                    pos += 2 if ord(d) > 0xFFFF else 1
            laid_of[len(p.text)] = pos
            # the text's places, run by run between the indents
            run_from = 0
            for q in range(1, len(p.text) + 1):
                if q == len(p.text) or laid_of[q] != laid_of[q - 1] + (u[q] - u[q - 1]):
                    self.map.run(laid_of[run_from], place + u[run_from], u[q] - u[run_from])
                    run_from = q
            para_end = pos
            place += u[len(p.text)] + 1
            if look is None:
                for a, b, flags in p.styles or ():
                    fm.add(laid_of[a], laid_of[b] - laid_of[a], flags & FLAGS)
                if p.kind == HEADING:
                    fm.add(para_start, para_end - para_start, BOLD, 1.3)
                elif p.kind == LEAD:
                    fm.add(para_start, para_end - para_start, BOLD)
                elif p.kind == SMALL:
                    fm.add(para_start, para_end - para_start, 0, 0.8, f.dim)
                for c0 in para_chunks:          # the reader's own indent, on every line of it
                    chunks.append((c0, f.px(INDENT_EMS) if indent else 0, 0, AUTO, 0))
                continue
            dropped = look.drop_cap if 0 < look.drop_cap <= len(p.text) and i not in no_drop else 0
            fm.add(para_start, para_end - para_start, 0, look.size if look.size != 1.0 else 0.0,
                   f.dim if p.kind == SMALL else None)
            fm.add(laid_of[dropped], para_end - laid_of[dropped], look.flags, look.size if look.size != 1.0 else 0.0,
                   base_size=look.size)
            for a, b, flags in p.styles or ():
                a = max(a, dropped)
                if b > a:
                    pct = flags >> SIZE_SHIFT
                    fm.add(laid_of[a], laid_of[b] - laid_of[a], flags & FLAGS, look.size * pct / 100.0 if pct else 0.0,
                           base_size=look.size)
            if cases:
                k = dropped
                while k < len(p.text):
                    if cases[k] & SMALL_CAPS and not cases[k] & (UPPER | LOWER) and p.text[k].islower():
                        e = k
                        while e < len(p.text) and cases[e] & SMALL_CAPS and p.text[e].islower():
                            e += 1
                        fm.add(laid_of[k], laid_of[e] - laid_of[k], 0, look.size * 0.8)
                        k = e
                    else:
                        k += 1
            # a list's markers sit in a column of the margin as wide as the widest of them (IV., 28.),
            # never past the margin the list stands in; the item's text begins after it
            marker = _marker_text(look)
            gutter = _marker_gutter(look, f)
            left = min(max(min(f.px(look.left), f.width * 35 // 100), f.px(look.list_left) + gutter if gutter else 0), f.width // 2)
            first = 0 if _isnan(look.indent) or dropped else f.px(look.indent)
            drop_px = 0
            if dropped:
                letters = p.text[:dropped]
                if cases:
                    letters = "".join(_cased(c, cases[k], p.text[k - 1] if k else None) for k, c in enumerate(letters))
                big = QtGui.QFont(font)
                big.setWeight(QtGui.QFont.Bold)
                cap = max(QtGui.QFontMetricsF(font).capHeight(), f.em * 0.6)
                big.setPixelSize(max(1, int(round(f.em * (f.line_step + cap) / cap))))
                drop_px = int(round(QtGui.QFontMetricsF(big).horizontalAdvance(letters) + f.em * 0.2))
                self.drops.append((i, para_start, para_end, letters, big, left))
                # the letters stay in the text, taking no room: drawn large in the margin instead
                hide = QtGui.QTextCharFormat()
                hide.setForeground(QtGui.QColor(0, 0, 0, 0))
                hide.setProperty(QtGui.QTextFormat.FontPixelSize, 1)
                hide.setFontLetterSpacingType(QtGui.QFont.AbsoluteSpacing)
                hide.setFontLetterSpacing(-1)
                r = QtGui.QTextLayout.FormatRange()
                r.start, r.length, r.format = laid_of[0], laid_of[dropped] - laid_of[0], hide
                fm.ranges.append(r)
            if marker:
                self.markers.append((para_start, marker, left))
            for n, c0 in enumerate(para_chunks):
                fp = min(max(0, left + (f.px(INDENT_EMS) if indent else 0) + (first + drop_px if n == 0 else 0)), f.width // 2)
                chunks.append((c0, fp, left, look.align, drop_px if n == 0 else 0))
        self.text = "".join(parts)
        self.layout = QtGui.QTextLayout(self.text, font)
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        justify = any(block.paragraphs[i].look is not None and block.paragraphs[i].look.align == JUSTIFY for i in range(start, end))
        if justify:
            option.setAlignment(QtCore.Qt.AlignJustify)
        self.layout.setTextOption(option)
        self.layout.setFormats(fm.ranges)
        width = f.width if width is None else width
        starts = [c[0] for c in chunks]
        self.tops, self.bottoms, self.drop_lines = [], [], []
        y, chunk_line = 0, {}
        self.layout.beginLayout()
        while True:
            line = self.layout.createLine()
            if not line.isValid():
                break
            # the chunk (a line of a paragraph between hard breaks) this line is in
            at = line.textStart()
            k = max(0, TextMap._last(starts, at))
            c0, first_px, rest_px, align, drop_px = chunks[k]
            nth = chunk_line.get(k, 0)
            chunk_line[k] = nth + 1
            margin = first_px if nth == 0 else (rest_px + (drop_px if nth == 1 else 0))
            line.setLineWidth(max(8, width - margin))
            x = margin
            if align in (CENTER, RIGHT):
                spare = width - margin - line.naturalTextWidth()
                x += max(0, spare / 2 if align == CENTER else spare)
            line.setPosition(QtCore.QPointF(x, y))
            self.tops.append(y)
            y += int(round(line.height() * f.spacing))
            self.bottoms.append(y)
        self.layout.endLayout()
        for d in self.drops:
            self.drop_lines.append(self.line_of(d[1]))

    def line_of(self, laid):
        for i in range(self.layout.lineCount()):
            line = self.layout.lineAt(i)
            if line.textStart() <= laid < line.textStart() + line.textLength():
                return i
        return max(0, self.layout.lineCount() - 1)

    def to_chapter(self, laid):
        """A place in the laid-out string as a place in the chapter (the indents are not text)."""
        return self.map.to_chapter(laid)

    def to_laid(self, place):
        return self.map.to_laid(place)

    def paint_extras(self, p, offset, first, last, fg):
        """What is drawn beside the text: list markers, drop caps (lines first..last shown)."""
        for at, text, left in self.markers:
            i = self.line_of(at)
            if first <= i <= last:
                line = self.layout.lineAt(i)
                p.setFont(self.layout.font())
                p.setPen(fg)
                fmx = QtGui.QFontMetricsF(self.layout.font())
                gap = self.layout.font().pixelSize() * MARKER_GAP
                p.drawText(QtCore.QPointF(offset.x() + left - gap - fmx.horizontalAdvance(text), offset.y() + line.y() + line.ascent()), text)
        for (_i, at, _end, letters, big, left), i in zip(self.drops, self.drop_lines):
            if first <= i <= last:
                line = self.layout.lineAt(i)
                second = self.layout.lineAt(i + 1) if i + 1 < self.layout.lineCount() else None
                base = (second.y() + second.ascent()) if second is not None else line.y() + line.ascent() + (self.bottoms[i] - self.tops[i])
                p.setFont(big)
                p.setPen(fg)
                p.drawText(QtCore.QPointF(offset.x() + left, offset.y() + base), letters)


def _same_run(a, b):
    x, y = a.look, b.look
    if x is None or y is None:
        return x is None and y is None
    return (x.align == JUSTIFY) == (y.align == JUSTIFY) and x.right == y.right and (x.cells is None) == (y.cells is None)


def _apart(p):
    look = p.look
    return look is not None and (look.above > 0 or look.rule or look.page_break or look.level == 1)


def paginate(chapter, frame):
    """Pages of the chapter. Paragraphs go in runs (LaidBlock); the space the book puts between
    them, a rule, a page break, a chapter heading on a new page come between runs; a picture
    keeps its own size unless it is large; a table is a grid of cells, each a small layout."""
    f = frame
    pages, pieces = [], []
    state = {"y": 0}
    place = 0
    block_gap = f.px(0.8)
    body_seen = False

    def new_page():
        if pieces:
            pages.append(list(pieces))
            del pieces[:]
        state["y"] = 0

    def space(px):
        if state["y"] > 0:
            state["y"] += px

    def rule(at):
        h = f.px(0.9)
        if state["y"] + h > f.page_height:
            new_page()
        w = f.width // 4
        pieces.append(Rule(state["y"] + h // 2, (f.width - w) // 2, (f.width + w) // 2, at))
        state["y"] += h

    def place_lines(laid, keep_first, drop_lines):
        count = len(laid.tops)
        height = laid.bottoms[-1] if count else 0
        if keep_first and state["y"] > 0 and state["y"] + height + keep_first > f.page_height and height + keep_first <= f.page_height:
            new_page()
        line = 0
        while line < count:
            top = laid.tops[line]
            last = line
            while last < count and laid.bottoms[last] - top <= f.page_height - state["y"]:
                last += 1
            if last < count and last - 1 > line and (last - 1) in drop_lines:
                last -= 1
            if last == line:
                if state["y"] > 0:      # try again at the top of a fresh page
                    new_page()
                    continue
                last += 1               # a single line taller than the page
            pieces.append(Lines(state["y"], laid, line, last - 1))
            state["y"] += laid.bottoms[last - 1] - top
            line = last
            if line < count:
                new_page()

    for block in chapter.blocks:
        first_of_block = True
        if isinstance(block, TextBlock):
            paras = block.paragraphs
            place_of = [0]
            for p in paras:
                place_of.append(place_of[-1] + u16(p.text) + 1)
            i = 0
            while i < len(paras):
                p = paras[i]
                look = p.look
                gap = max(block_gap if first_of_block else 0, f.px(look.above if look else 0.0))
                heading_break = look is not None and look.level == 1 and not f.magazine and body_seen
                if ((look is not None and look.page_break) or heading_break) and state["y"] > 0:
                    new_page()
                space(gap)
                if look is not None and look.rule:
                    rule(place + place_of[i])
                first_of_block = False
                if look is not None and look.cells is not None:
                    j = i + 1
                    while j < len(paras) and paras[j].look is not None and paras[j].look.cells is not None \
                            and paras[j].look.table == look.table and not _apart(paras[j]):
                        j += 1
                    rows = _table(block, i, j, place + place_of[i], place_of, place, f)
                    if rows is not None:
                        for height, edges, cells, at in rows:
                            if state["y"] + height > f.page_height and state["y"] > 0:
                                new_page()
                            pieces.append(Grid(state["y"], height, edges, at))
                            for x, w, dy, laid in cells:
                                pieces.append(Lines(state["y"] + dy, laid, 0, len(laid.tops) - 1, x, w))
                            state["y"] += height
                        i = j
                        continue
                j = i + 1
                while j < len(paras) and _same_run(p, paras[j]) and not _apart(paras[j]) \
                        and (paras[j].look is not None and paras[j].look.cells is not None) == (look is not None and look.cells is not None):
                    j += 1
                right = min(f.px(look.right if look else 0.0), f.width // 4)
                laid = LaidBlock(block, i, j, place + place_of[i], f, width=f.width - right)
                short = {d[0] for d, line in zip(laid.drops, laid.drop_lines)
                         if line == laid.line_of(max(d[1], d[2] - 1))}
                if short:
                    laid = LaidBlock(block, i, j, place + place_of[i], f, no_drop=short, width=f.width - right)
                heading = j == i + 1 and look is not None and look.level > 0
                place_lines(laid, f.line_step * 2 if heading else 0, set(laid.drop_lines))
                if any(paras[k].kind == NORMAL and (paras[k].look.level if paras[k].look else 0) == 0 for k in range(i, j)):
                    body_seen = True
                i = j
            place += block.length
        else:
            size = f.images.size(block.source) if f.images else None
            look = block.look
            if size and size[0] >= 16 and size[1] >= 16:
                natural = (look.pixels if look is not None and look.pixels > 0 else size[0]) * f.density
                if look is not None and not _isnan(look.width):
                    w = f.width * look.width
                elif look is None or natural >= f.width * 0.75:
                    w = f.width
                else:
                    w = natural
                w = max(1, min(f.width, int(w)))
                h = w * size[1] // size[0]
                if h > f.page_height:
                    h = f.page_height
                    w = h * size[0] // size[1]
                if look is not None and look.page_break and state["y"] > 0:
                    new_page()
                space(max(block_gap, f.px(look.above if look else 0.0)))
                if look is not None and look.rule:
                    rule(place)
                if state["y"] + h > f.page_height:
                    new_page()
                align = look.align if look is not None else AUTO
                x = 0 if align == LEFT else f.width - w if align == RIGHT else (f.width - w) // 2
                pieces.append(Picture(state["y"], place, block.source, w, h, x))
                state["y"] += h
            place += 1
    new_page()
    return pages or [[]]


class _Cell:
    def __init__(self, col, span, header):
        self.col, self.span, self.header, self.pieces = col, span, header, []


class _CellBlock:
    """One table cell's text, laid out at its width: the same shape as a LaidBlock."""

    def __init__(self, text, formats, mapping, font, width, spacing, aligns):
        self.map, self.drops, self.markers, self.drop_lines = mapping, [], [], []
        self.text = text
        self.layout = QtGui.QTextLayout(text, font)
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.layout.setTextOption(option)
        self.layout.setFormats(formats)
        starts = [a[0] for a in aligns]
        self.tops, self.bottoms = [], []
        y = 0
        self.layout.beginLayout()
        while True:
            line = self.layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(8, width))
            k = max(0, TextMap._last(starts, line.textStart()))
            align = aligns[k][1] if aligns else AUTO
            x = 0
            if align in (CENTER, RIGHT):
                spare = width - line.naturalTextWidth()
                x = max(0, spare / 2 if align == CENTER else spare)
            line.setPosition(QtCore.QPointF(x, y))
            self.tops.append(y)
            y += int(round(line.height() * spacing))
            self.bottoms.append(y)
        self.layout.endLayout()

    def to_chapter(self, laid):
        return self.map.to_chapter(laid)

    def to_laid(self, place):
        return self.map.to_laid(place)

    def paint_extras(self, *_args):
        pass


def _table(block, start, end, at, place_of, base, f):
    """Paragraphs start..end of a block, rows of one table, as a grid: thin borders, the columns
    shared by what they hold, each cell's text wrapped in it. None when it cannot be one (too many
    columns, a row taller than a page): the rows are then read as paragraphs."""
    rows = {}
    for i in range(start, end):
        for c in block.paragraphs[i].look.cells:
            row = rows.setdefault(c[2], {})
            cell = row.setdefault(c[3], _Cell(c[3], c[4], c[5] == 1))
            cell.pieces.append((i, c[0], c[1]))
    if not rows:
        return None
    columns = max(cell.col + cell.span for r in rows.values() for cell in r.values())
    if columns < 1 or columns > 12:
        return None
    pad = max(2, f.px(0.3))
    font = f.font
    texts = []
    for r in sorted(rows):
        made = []
        for col in sorted(rows[r]):
            cell = rows[r][col]
            parts, pos, mapping, fm, aligns = [], 0, TextMap(), _Formats(font), []
            for n, (pi, a, b) in enumerate(cell.pieces):
                p = block.paragraphs[pi]
                if n:
                    parts.append(LINE_BREAK)
                    pos += 1
                start_pos = pos
                hard = _hard_breaks(p)
                cases = _cases_of(p)
                u = _u16_offsets(p.text)
                laid_of = {}
                for k in range(a, b):
                    laid_of[k] = pos
                    ch = p.text[k]
                    if ch == "\n":
                        d = LINE_BREAK if k in hard else " "
                    else:
                        d = _cased(ch, cases[k], p.text[k - 1] if k else None) if cases else ch
                    parts.append(d)
                    pos += 2 if ord(d) > 0xFFFF else 1
                laid_of[b] = pos
                mapping.run(start_pos, base + place_of[pi] + u[a], u[b] - u[a])
                look = p.look
                fm.add(start_pos, pos - start_pos, look.flags | (BOLD if cell.header else 0), look.size if look.size != 1.0 else 0.0)
                for ra, rb_, flags in p.styles or ():
                    ra, rb_ = max(ra, a), min(rb_, b)
                    if rb_ > ra:
                        pct = flags >> SIZE_SHIFT
                        fm.add(laid_of[ra], laid_of[rb_] - laid_of[ra], flags & FLAGS, look.size * pct / 100.0 if pct else 0.0, base_size=look.size)
                aligns.append((start_pos, look.align))
            text = "".join(parts)
            # measured with its own formats: a header in bold, a word in capitals
            probe = QtGui.QTextLayout(text, font)
            probe.setFormats(fm.ranges)
            probe.beginLayout()
            wants = 0.0
            while True:
                line = probe.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(100000)
                wants = max(wants, line.naturalTextWidth())
            probe.endLayout()
            needs = 0.0
            fmw = QtGui.QFontMetricsF(QtGui.QFont(font))
            for word in re.split(r"[  ]", text):
                if word:
                    needs = max(needs, fmw.horizontalAdvance(word) * (1.08 if cell.header else 1.0))
            made.append((cell, text, fm.ranges, mapping, aligns, wants + 2 * pad + 2, needs + 2 * pad + 2))
        texts.append(made)
    wants = [1.0] * columns
    needs = [0.0] * columns
    for made in texts:
        for cell, _t, _f, _m, _a, w, n in made:
            if cell.span == 1:
                wants[cell.col] = max(wants[cell.col], w)
                needs[cell.col] = max(needs[cell.col], n)
    total = sum(wants)
    widths = [f.width * w / total for w in wants]
    short = [c for c in range(columns) if widths[c] < needs[c]]
    if short:
        wanted = sum(needs[c] - widths[c] for c in short)
        spare = sum(max(0.0, widths[c] - needs[c]) for c in range(columns) if c not in short)
        if spare > 0:
            k = min(1.0, spare / wanted)
            for c in range(columns):
                if c in short:
                    widths[c] += (needs[c] - widths[c]) * k
                else:
                    widths[c] -= max(0.0, widths[c] - needs[c]) * (wanted * k / spare)
    xs = [0]
    for c in range(columns):
        xs.append(xs[-1] + int(widths[c]))
    xs[columns] = f.width - 1
    out = []
    for made in texts:
        cells, edges, height = [], [], 0
        for cell, text, formats, mapping, aligns, _w, _n in made:
            x0, x1 = xs[cell.col], xs[min(columns, cell.col + cell.span)]
            laid = _CellBlock(text, formats, mapping, font, max(8, x1 - x0 - 2 * pad), f.spacing, aligns)
            cells.append((x0 + pad, x1 - x0 - 2 * pad, pad, laid))
            edges.append((x0, x1 - x0))
            height = max(height, (laid.bottoms[-1] if laid.bottoms else 0) + 2 * pad)
        if height > f.page_height:
            return None
        out.append((height, edges, cells, at))
    return out


def page_start(page):
    return page[0].start_char if page else 0


def page_for(pages, char_offset):
    found = 0
    for i, page in enumerate(pages):
        if page_start(page) <= char_offset:
            found = i
        else:
            break
    return found


# ------------------------------------------------------------------------------------------
# Keeping the screen awake while a page is open, as far as the system lets a program ask
# ------------------------------------------------------------------------------------------

class Awake:
    def __init__(self):
        self.cookie = None
        self.on = False

    def set(self, wanted):
        if wanted == self.on:
            return
        self.on = wanted
        try:
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000002 if wanted else 0))
            elif sys.platform.startswith("linux"):
                from PyQt5 import QtDBus
                bus = QtDBus.QDBusConnection.sessionBus()
                iface = QtDBus.QDBusInterface("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver",
                                              "org.freedesktop.ScreenSaver", bus)
                if not iface.isValid():
                    return
                if wanted:
                    reply = iface.call("Inhibit", "Reader's Books", "a page is open")
                    args = reply.arguments()
                    self.cookie = args[0] if args else None
                elif self.cookie is not None:
                    iface.call("UnInhibit", QtCore.QVariant(self.cookie))
                    self.cookie = None
        except Exception:
            pass


# ------------------------------------------------------------------------------------------
# One job on a thread of its own
# ------------------------------------------------------------------------------------------

class Step(QtCore.QObject):
    """Where a long job is, told from its thread to the window's."""
    said = QtCore.pyqtSignal(str)


class Worker(QtCore.QObject):
    done = QtCore.pyqtSignal(object, object)     # result, error

    def __init__(self, job):
        super().__init__()
        self.job = job

    @QtCore.pyqtSlot()
    def run(self):
        try:
            self.done.emit(self.job(), None)
        except Exception as exc:
            self.done.emit(None, exc)


# ------------------------------------------------------------------------------------------
# The lists: the shelf, the chapters, the library, the settings. A row is a title and a dim
# line under it, nothing else; the row one stands on is drawn inverted.
# ------------------------------------------------------------------------------------------

ROW, HINT, SECTION, RULE = "row", "hint", "section", "rule"
TOOLS, NOTE = "tools", "note"       # a page's buttons (not books), and what it asks for in small print
THUMB = 64


class Row:
    """`current` = the row one stands on (the list opens on it); `inverted` = drawn the same way
    without being it (a folder chosen for the library)."""
    def __init__(self, title="", secondary="", action=None, menu=None, kind=ROW, current=False, lines=2, thumb=None, inverted=False, thumb_size=None, tools=None):
        self.title, self.secondary, self.action, self.menu = title, secondary, action, menu
        self.tools = tools or []        # TOOLS: (label, action) per button
        self.kind, self.current, self.lines, self.thumb, self.inverted = kind, current, lines, thumb, inverted
        self.thumb_size = thumb_size or THUMB


def wrap(text, font, width, max_lines):
    """The text cut into at most `max_lines` lines of `width`, the last one ending in an
    ellipsis when there was more."""
    layout = QtGui.QTextLayout(text, font)
    metrics = QtGui.QFontMetrics(font)
    out = []
    layout.beginLayout()
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(40, width))
        start, length = line.textStart(), line.textLength()
        if len(out) == max_lines - 1 and start + length < len(text):
            out.append(metrics.elidedText(text[start:], QtCore.Qt.ElideRight, max(40, width)))
            break
        out.append(text[start:start + length].rstrip())
    layout.endLayout()
    return out or [""]


TILE_CORNER, TILE_GAP_H, TILE_GAP_V = 12, 8, 3      # a card's radius and its margins, as on the phone


class RowDelegate(QtWidgets.QStyledItemDelegate):
    PAD_H, PAD_V = 24, 11
    TOOL_H, TOOL_GAP = 40, 10

    def tool_rects(self, row, rect):
        """Where each button of a TOOLS row is drawn (and clicked)."""
        n = max(1, len(row.tools))
        left, top = rect.left() + self.PAD_H - 6, rect.top() + self.PAD_V
        width = (rect.width() - 2 * (self.PAD_H - 6) - (n - 1) * self.TOOL_GAP) // n
        return [QtCore.QRect(left + i * (width + self.TOOL_GAP), top, width, self.TOOL_H) for i in range(n)]

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.fg, self.bg = QtGui.QColor("#fff"), QtGui.QColor("#000")
        self.accent, self.on_accent = QtGui.QColor("#fff"), QtGui.QColor("#000")
        self.tile, self.press, self.tiles = QtGui.QColor("#000"), QtGui.QColor("#000"), False
        self.big, self.small = QtGui.QFont(), QtGui.QFont()

    def tool_font(self):
        f = QtGui.QFont(self.small)
        f.setPointSizeF(self.small.pointSizeF() * 1.12 if self.small.pointSizeF() > 0 else 11)
        return f

    def _row(self, index):
        i = index.data(QtCore.Qt.UserRole)
        return self.main.rows[i] if i is not None and i < len(self.main.rows) else Row(kind=RULE)

    def _width(self, row, total):
        return total - 2 * self.PAD_H - (row.thumb_size + 16 if row.thumb else 0)

    def sizeHint(self, option, index):
        return self.size_of(self._row(index), self.main.listing.viewport().width())

    def size_of(self, row, width):
        fb, fs = QtGui.QFontMetrics(self.big), QtGui.QFontMetrics(self.small)
        if row.kind == RULE:
            return QtCore.QSize(width, 17)
        if row.kind == SECTION:
            return QtCore.QSize(width, fs.height() + 20)
        if row.kind == HINT:
            return QtCore.QSize(width, len(wrap(row.title, self.small, width - 2 * self.PAD_H, 12)) * fs.height() + 2 * self.PAD_V)
        if row.kind == TOOLS:
            return QtCore.QSize(width, self.TOOL_H + 2 * self.PAD_V + (fs.height() + 6 if row.secondary else 0))
        if row.kind == NOTE:
            return QtCore.QSize(width, fs.height() * 2 + 12)
        height = len(wrap(row.title, self.big, self._width(row, width), row.lines)) * fb.height()
        if row.secondary:
            height += fs.height() + 2
        if row.thumb:
            height = max(height, row.thumb_size)
        return QtCore.QSize(width, height + 2 * self.PAD_V)

    def paint(self, p, option, index):
        row = self._row(index)
        p.save()
        inverted = row.kind == ROW and (row.current or row.inverted or bool(option.state & QtWidgets.QStyle.State_Selected))
        fg, bg = (self.on_accent, self.accent) if inverted else (self.fg, self.bg)
        if self.tiles and row.kind == ROW:
            # with a colour theme a row is a card: the accent when it is the current one, the
            # « press » colour under the mouse, the « key » colour otherwise; the text keeps its inset
            p.fillRect(option.rect, self.bg)
            if not inverted:
                bg = self.press if option.state & QtWidgets.QStyle.State_MouseOver else self.tile
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QtCore.QRectF(option.rect.adjusted(TILE_GAP_H, TILE_GAP_V, -TILE_GAP_H, -TILE_GAP_V)), TILE_CORNER, TILE_CORNER)
            p.setRenderHint(QtGui.QPainter.Antialiasing, False)
        else:
            p.fillRect(option.rect, bg)
        dim = QtGui.QColor(fg)
        dim.setAlphaF(0.6 if inverted else 0.55)
        r = option.rect.adjusted(self.PAD_H, self.PAD_V, -self.PAD_H, -self.PAD_V)
        fb, fs = QtGui.QFontMetrics(self.big), QtGui.QFontMetrics(self.small)
        if row.kind == RULE:
            if not self.tiles:          # with tiles the rows are set apart by space, not by a line
                rule = QtGui.QColor(self.fg)
                rule.setAlphaF(0.25)
                p.fillRect(r.left(), option.rect.center().y(), r.width(), 1, rule)
        elif row.kind == SECTION:
            p.setFont(self.small)
            p.setPen(dim)
            p.drawText(QtCore.QRect(r.left(), r.bottom() - fs.height() + 6, r.width(), fs.height()),
                       QtCore.Qt.AlignLeft, fs.elidedText(row.title, QtCore.Qt.ElideRight, r.width()))
        elif row.kind == TOOLS:
            # buttons, not books: a thin frame (a card with tiles), the text a size smaller
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            frame = QtGui.QColor(self.fg)
            frame.setAlphaF(0.3)
            for (label, _a), box in zip(row.tools, self.tool_rects(row, option.rect)):
                if self.tiles:
                    p.setPen(QtCore.Qt.NoPen)
                    p.setBrush(self.tile)
                else:
                    p.setPen(QtGui.QPen(frame, 1))
                    p.setBrush(QtCore.Qt.NoBrush)
                p.drawRoundedRect(QtCore.QRectF(box).adjusted(0.5, 0.5, -0.5, -0.5), TILE_CORNER if self.tiles else 8, TILE_CORNER if self.tiles else 8)
                p.setPen(self.fg)
                p.setFont(self.tool_font())
                p.drawText(box, QtCore.Qt.AlignCenter, QtGui.QFontMetrics(self.tool_font()).elidedText(label, QtCore.Qt.ElideRight, box.width() - 12))
            p.setRenderHint(QtGui.QPainter.Antialiasing, False)
            if row.secondary:
                p.setFont(self.small)
                p.setPen(dim)
                p.drawText(QtCore.QRect(option.rect.left(), option.rect.top() + self.PAD_V + self.TOOL_H + 6, option.rect.width(), fs.height()),
                           QtCore.Qt.AlignHCenter, fs.elidedText(row.secondary, QtCore.Qt.ElideRight, r.width()))
        elif row.kind == NOTE:
            p.setFont(self.tool_font())
            p.setPen(fg)
            ft = QtGui.QFontMetrics(self.tool_font())
            p.drawText(QtCore.QRect(r.left(), option.rect.top() + 4, r.width(), ft.height()), QtCore.Qt.AlignLeft, ft.elidedText("› " + row.title, QtCore.Qt.ElideRight, r.width()))
            p.setFont(self.small)
            p.setPen(dim)
            p.drawText(QtCore.QRect(r.left(), option.rect.top() + 6 + ft.height(), r.width(), fs.height()), QtCore.Qt.AlignLeft, fs.elidedText(row.secondary, QtCore.Qt.ElideRight, r.width()))
        elif row.kind == HINT:
            p.setFont(self.small)
            p.setPen(dim)
            y = r.top()
            for line in wrap(row.title, self.small, r.width(), 12):
                p.drawText(QtCore.QRect(r.left(), y, r.width(), fs.height()), QtCore.Qt.AlignLeft, line)
                y += fs.height()
        else:
            width = self._width(row, option.rect.width())
            if row.thumb:
                store, source = row.thumb
                ratio = self.main.devicePixelRatioF()
                size = row.thumb_size
                pixmap = store.pixmap(source, int(size * ratio), int(size * ratio), crop=True)
                if pixmap:
                    p.drawPixmap(QtCore.QRect(r.right() - size + 1, r.top() + (r.height() - size) // 2, size, size), pixmap)
            lines = wrap(row.title, self.big, width, row.lines)
            height = len(lines) * fb.height() + (fs.height() + 2 if row.secondary else 0)
            y = r.top() + max(0, (r.height() - height) // 2)
            p.setFont(self.big)
            p.setPen(fg)
            for line in lines:
                p.drawText(QtCore.QRect(r.left(), y, width, fb.height()), QtCore.Qt.AlignLeft, line)
                y += fb.height()
            if row.secondary:
                p.setFont(self.small)
                p.setPen(dim)
                p.drawText(QtCore.QRect(r.left(), y + 2, width, fs.height()), QtCore.Qt.AlignLeft,
                           fs.elidedText(row.secondary, QtCore.Qt.ElideRight, width))
        p.restore()


class Clickable(QtWidgets.QLabel):
    clicked = QtCore.pyqtSignal()

    def __init__(self, text="", name=None):
        super().__init__(text)
        if name:
            self.setObjectName(name)
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()


class Listing(QtWidgets.QListWidget):
    """Up and down walk the rows that do something; the rest is the list's."""
    last_press = QtCore.QPoint()

    def mousePressEvent(self, e):
        self.last_press = e.pos()
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and self.currentItem():
            self.itemActivated.emit(self.currentItem())
            return
        super().keyPressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.doItemsLayout()


# ------------------------------------------------------------------------------------------
# The reader: a page of text. The right half turns forward, the left half back; a right click
# (or the ⋯ in the corner) opens the menu.
# ------------------------------------------------------------------------------------------

class Reader(QtWidgets.QWidget):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.entry = None
        self.book = None
        self.failed = False
        self.images = None
        self.chapter = 0
        self.wanted = 0
        self.page = 0
        self.pages = None
        self.key = None
        self.highlights = []        # every highlight of the book, removed ones included
        self.shown = []             # those to draw, where their words are
        self.texts = {}             # chapter -> Text16
        self.turns = 0              # pages turned since the book was opened
        self.pressed = None         # where the button went down
        self.selecting = None       # (from, to) in the chapter, while the mouse is dragged
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

    # ---- which book ----

    def open(self, entry):
        self.entry, self.book, self.failed, self.pages, self.key = entry, None, False, None, None
        self.highlights, self.shown, self.texts, self.pressed, self.selecting = [], [], {}, None, None
        self.images = ImageStore(self.main.library.path(entry)) if entry["format"] == EPUB else None
        self.chapter, self.wanted, self.page = entry.get("chapter", 0), entry.get("charOffset", 0), 0
        self.turns = 0
        left_at = position_of(entry)        # before the first page drawn marks it as read just now
        book_id = entry["id"]

        def done(book, error):
            if not self.entry or self.entry["id"] != book_id:
                return
            self.book, self.failed = book, error is not None
            if book:
                self.chapter = min(max(0, self.chapter), len(book.chapters) - 1)
                self.set_highlights(load_highlights(entry)[0])
                self.main.sync_highlights(entry, left_at, opening=True)
            self.update()

        self.main.run(lambda: self.main.library.book(entry), done)
        self.update()

    def close_book(self):
        if self.entry and self.book and self.turns:
            self.main.sync_place(self.entry["id"])      # where it was left, for the other devices
        self.entry = self.book = self.pages = self.key = None
        self.highlights, self.shown, self.texts = [], [], {}

    # ---- highlights ----

    def set_highlights(self, highlights):
        self.highlights = highlights
        self.shown = anchor_highlights(highlights, self.book) if self.book else []
        self.update()

    def text_of(self, chapter):
        if chapter not in self.texts:
            self.texts[chapter] = Text16(chapter_text(self.book.chapters[chapter]))
        return self.texts[chapter]

    def place_at(self, pos):
        """The place in the chapter of the character under a point of the page, or None."""
        if not self.pages:
            return None
        _font, area = self.frame()
        x, y = pos.x() - area.left(), pos.y() - area.top()
        for piece in self.pages[self.page]:
            if not isinstance(piece, Lines):
                continue
            block = piece.block
            top = block.tops[piece.first]
            if not piece.y <= y < piece.y + block.bottoms[piece.last] - top:
                continue
            if piece.clip >= 0 and not piece.x <= x < piece.x + piece.clip:
                continue
            for i in range(piece.first, piece.last + 1):
                if y < piece.y + block.bottoms[i] - top:
                    line = block.layout.lineAt(i)
                    lx = float(x - piece.x)
                    return block.to_chapter(line.xToCursor(max(line.x(), min(lx, line.x() + line.naturalTextWidth()))))
        return None

    def highlight_at(self, pos):
        place = self.place_at(pos)
        if place is None:
            return None
        return next((h for h in self.shown if h["chapter"] == self.chapter and h["start"] <= place < h["end"]), None)

    def reaches_middle(self, h, left, right):
        """True when some of the highlight lies, on this page, between `left` and `right` (the
        middle third of the window), where a click can open it without taking a page-turn zone."""
        _font, area = self.frame()
        for piece in self.pages[self.page]:
            if not isinstance(piece, Lines):
                continue
            block = piece.block
            for i in range(piece.first, piece.last + 1):
                line = block.layout.lineAt(i)
                first = block.to_chapter(line.textStart())
                last = block.to_chapter(line.textStart() + line.textLength())
                if h["end"] <= first or h["start"] >= last:
                    continue
                x1 = area.left() + piece.x + line.cursorToX(block.to_laid(max(h["start"], first)))[0]
                x2 = area.left() + piece.x + (line.cursorToX(block.to_laid(min(h["end"], last)))[0] if h["end"] < last else line.x() + line.naturalTextWidth())
                if min(x1, x2) < right and max(x1, x2) > left:
                    return True
        return False

    def selection(self):
        if not self.selecting:
            return None
        start, end = self.text_of(self.chapter).words(*self.selecting)
        return (start, end) if end > start else None

    def paint_marks(self, p, area, fg, accent):
        """The band behind what is highlighted (the accent, faint), a line under what carries a
        comment (the text colour), and a stronger band behind what is being selected."""
        marks = [(h["start"], h["end"], 0.22, bool((h.get("comment") or "").strip()))
                 for h in self.shown if h["chapter"] == self.chapter]
        chosen = self.selection()
        if chosen:
            marks.append((chosen[0], chosen[1], 0.45, False))
        if not marks:
            return
        for piece in self.pages[self.page]:
            if not isinstance(piece, Lines):
                continue
            block = piece.block
            top = area.top() + piece.y - block.tops[piece.first]
            for i in range(piece.first, piece.last + 1):
                line = block.layout.lineAt(i)
                first = block.to_chapter(line.textStart())
                last = block.to_chapter(line.textStart() + line.textLength())
                for start, end, strength, commented in marks:
                    if end <= first or start >= last:
                        continue
                    x1 = line.cursorToX(block.to_laid(max(start, first)))[0]
                    x2 = line.cursorToX(block.to_laid(min(end, last)))[0] if end < last else line.x() + line.naturalTextWidth()
                    if x2 <= x1:
                        continue
                    band = QtGui.QColor(accent)
                    band.setAlphaF(strength)
                    rect = QtCore.QRectF(area.left() + piece.x + x1, top + line.y(), x2 - x1, line.height())
                    p.fillRect(rect, band)
                    if commented:
                        p.fillRect(QtCore.QRectF(rect.left(), rect.bottom() - 1, rect.width(), 2), fg)

    # ---- geometry and fonts ----

    def body_font(self):
        cfg = self.main.cfg
        if cfg.get("book_serif") and SERIF_FAMILY:
            font = QtGui.QFont(SERIF_FAMILY)
        elif cfg.get("font") == "mono":
            font = QtGui.QFont("monospace")
            font.setStyleHint(QtGui.QFont.Monospace)
        else:
            font = QtGui.QFont(SANS_FAMILY)
            font.setWeight(QtGui.QFont.Light)
        font.setPixelSize(max(8, round(reader_pt(cfg) * self.logicalDpiY() / 72.0)))
        return font

    def frame(self):
        """Where the text goes: a column no wider than a comfortable line, centred."""
        font = self.body_font()
        small = QtGui.QFontMetrics(self.main.small_font())
        pad = 24
        width = max(120, min(self.width() - 2 * pad, font.pixelSize() * 34))
        left = (self.width() - width) // 2
        top = 20 + small.height() + 14
        bottom = self.height() - 20 - small.height() - 10
        return font, QtCore.QRect(left, top, width, max(60, bottom - top))

    def layout_pages(self):
        if not self.book:
            return None
        font, area = self.frame()
        key = (self.entry["id"], self.chapter, area.width(), area.height(), font.family(), font.pixelSize(), self.main.theme)
        if key != self.key:
            dim = QtGui.QColor(self.main.colors["fg"])
            dim.setAlphaF(0.55)
            self.pages = paginate(self.book.chapters[self.chapter],
                                  Frame(font, dim, area.width(), area.height(), self.images, bool(self.book.magazine)))
            self.key = key
            self.page = min(page_for(self.pages, self.wanted), len(self.pages) - 1)
            self.wanted = page_start(self.pages[self.page])
            self.remember()
        return self.pages

    def progress(self):
        return int((self.book.chars_before(self.chapter) + page_start(self.pages[self.page])) * 100 / max(1, self.book.total))

    def remember(self):
        if self.book and self.pages:
            self.main.library.save_position(self.entry["id"], self.chapter, page_start(self.pages[self.page]), self.progress(), article=self.article())

    # ---- a magazine's articles ----

    def starts(self):
        """The chapters the articles of a magazine begin with (a long article goes on in the next ones)."""
        return sorted({a.chapter for a in self.book.magazine}) if self.book and self.book.magazine else []

    def article(self):
        before = [c for c in self.starts() if c <= self.chapter]
        return before[-1] if before else None

    def previous_article(self):
        a = self.article()
        before = [c for c in self.starts() if a is not None and c < a]
        return before[-1] if before else None

    def next_article(self):
        return next((c for c in self.starts() if c > self.chapter), None)

    def to_article(self, start):
        """Another article, where it was left (at its top the first time)."""
        if start is None:
            return
        self.turns += 1
        self.main.turned()
        at = (self.main.library.get(self.entry["id"]) or self.entry).get("places", {}).get(str(start))
        self.go_to(*(at if at else (start, 0)))

    def bar_zone(self):
        """The article bar of a magazine, above the text: ‹ previous article · contents · next ›."""
        _font, area = self.frame()
        return QtCore.QRect(area.left(), 0, area.width() - 40, area.top() - 2)

    # ---- turning ----

    def go_to(self, chapter, char_offset):
        self.chapter, self.wanted, self.key = chapter, char_offset, None
        self.update()

    def turn(self, forward):
        pages = self.layout_pages()
        if not pages:
            return
        self.turns += 1
        self.main.turned()
        if forward:
            if self.page + 1 < len(pages):
                self.page += 1
            elif self.chapter + 1 < len(self.book.chapters):
                return self.go_to(self.chapter + 1, 0)
            else:
                return
        else:
            if self.page > 0:
                self.page -= 1
            elif self.chapter > 0:
                return self.go_to(self.chapter - 1, 1 << 30)
            else:
                return
        self.wanted = page_start(pages[self.page])
        self.remember()
        self.update()

    def menu_zone(self):
        return QtCore.QRect(self.width() - 64, 0, 64, 56)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.RightButton or self.menu_zone().contains(e.pos()):
            self.main.reader_menu(e.globalPos())
        elif e.button() == QtCore.Qt.LeftButton:
            self.pressed, self.selecting = e.pos(), None

    def mouseMoveEvent(self, e):
        """Dragging across the text of a book selects a passage."""
        if self.pressed is None or not (self.entry and self.book):
            return
        if self.selecting is None and (e.pos() - self.pressed).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return
        start = self.selecting[0] if self.selecting else self.place_at(self.pressed)
        end = self.place_at(e.pos())
        if start is not None and end is not None:
            self.selecting = (start, end)
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != QtCore.Qt.LeftButton or self.pressed is None:
            return
        self.pressed = None
        if self.selecting is None and self.book and self.book.magazine and self.bar_zone().contains(e.pos()):
            zone = self.bar_zone()
            if e.x() < zone.left() + zone.width() / 3.0:
                self.to_article(self.previous_article())
            elif e.x() > zone.left() + zone.width() * 2 / 3.0:
                self.to_article(self.next_article())
            else:
                self.main.to_contents(self.entry["id"])
            return
        chosen = self.selection()
        if self.selecting is not None:
            if chosen:
                self.main.selection_menu(e.globalPos(), self.chapter, chosen[0], chosen[1])
            self.selecting = None
            self.update()
            return
        # As on a reading tablet: the left third goes back, the right third forward, the
        # middle opens the book's menu — or, on a picture, the picture on the whole window.
        # A click on a highlight opens it, except in a page-turn zone when the highlight also
        # runs through the middle, where it can be opened: a whole page highlighted still turns.
        third = self.width() / 3.0
        found = self.highlight_at(e.pos())
        if found and (third <= e.x() <= 2 * third or not self.reaches_middle(found, third, 2 * third)):
            return self.main.highlight_menu(e.globalPos(), found)
        picture = self.picture_at(e.pos())
        if e.x() < third:
            self.turn(False)
        elif e.x() > 2 * third:
            self.turn(True)
        elif picture:
            PictureView(self.main, self.images.data(picture))
        else:
            self.main.reader_menu(e.globalPos())

    def picture_at(self, pos):
        """The picture of the page under `pos`, by its source, or None."""
        if not (self.book and self.pages and self.images):
            return None
        _font, area = self.frame()
        for piece in self.pages[self.page]:
            if isinstance(piece, Picture) and QtCore.QRect(area.left() + piece.x, area.top() + piece.y,
                                                           piece.width, piece.height).contains(pos):
                return piece.source
        return None

    def wheelEvent(self, e):
        if e.angleDelta().y():
            self.turn(e.angleDelta().y() < 0)

    def keyPressEvent(self, e):
        key = e.key()
        if key in (QtCore.Qt.Key_Right, QtCore.Qt.Key_Space, QtCore.Qt.Key_PageDown, QtCore.Qt.Key_Down, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.turn(True)
        elif key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_PageUp, QtCore.Qt.Key_Up):
            self.turn(False)
        elif key in (QtCore.Qt.Key_M, QtCore.Qt.Key_Menu):
            self.main.reader_menu(self.mapToGlobal(self.menu_zone().bottomLeft()))
        elif key in (QtCore.Qt.Key_Plus, QtCore.Qt.Key_Equal):
            self.main.set_reader_size(+1)
        elif key == QtCore.Qt.Key_Minus:
            self.main.set_reader_size(-1)
        else:
            super().keyPressEvent(e)

    def resizeEvent(self, e):
        self.update()

    # ---- the page ----

    def paintEvent(self, _e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        fg, bg = QtGui.QColor(self.main.colors["fg"]), QtGui.QColor(self.main.colors["bg"])
        dim = QtGui.QColor(fg)
        dim.setAlphaF(0.55)
        p.fillRect(self.rect(), bg)
        small = self.main.small_font()
        fs = QtGui.QFontMetrics(small)
        if not self.entry:
            return
        if not self.book:
            p.setFont(self.main.big_font() if self.failed else small)
            p.setPen(fg if self.failed else dim)
            p.drawText(self.rect(), QtCore.Qt.AlignCenter, _("this file could not be read") if self.failed else "…")
            return
        pages = self.layout_pages()
        _font, area = self.frame()
        page = pages[self.page]
        p.setFont(small)
        p.setPen(dim)
        if self.book.magazine:
            # the article bar: ‹ previous article · contents · next article ›, text only
            zone = QtCore.QRect(area.left(), 20, area.width() - 40, fs.height())
            off = QtGui.QColor(fg)
            off.setAlphaF(0.2)
            p.drawText(zone, QtCore.Qt.AlignHCenter, _("contents"))
            p.setFont(self.main.big_font())
            p.setPen(dim if self.previous_article() is not None else off)
            p.drawText(zone, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, "‹")
            p.setPen(dim if self.next_article() is not None else off)
            p.drawText(zone, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, "›")
            p.setPen(dim)
        else:
            p.drawText(QtCore.QRect(area.left(), 20, area.width() - 40, fs.height()), QtCore.Qt.AlignLeft,
                       fs.elidedText(self.book.title, QtCore.Qt.ElideRight, area.width() - 40))
        p.setFont(self.main.big_font())
        p.drawText(QtCore.QRect(area.right() - 39, 20, 40, fs.height()), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, "⋯")
        self.paint_marks(p, area, fg, QtGui.QColor(self.main.colors["accent"]))
        for piece in page:
            if isinstance(piece, Lines):
                p.setPen(fg)
                offset = QtCore.QPointF(area.left() + piece.x, area.top() + piece.y - piece.block.tops[piece.first])
                for i in range(piece.first, piece.last + 1):
                    piece.block.layout.lineAt(i).draw(p, offset)
                piece.block.paint_extras(p, offset, piece.first, piece.last, fg)
            elif isinstance(piece, Rule):
                p.fillRect(QtCore.QRectF(area.left() + piece.x1, area.top() + piece.y, piece.x2 - piece.x1, 1), dim)
            elif isinstance(piece, Grid):
                pen = QtGui.QPen(dim)
                pen.setWidth(1)
                p.setPen(pen)
                p.setBrush(QtCore.Qt.NoBrush)
                for x, w in piece.cells:
                    p.drawRect(QtCore.QRect(area.left() + x, area.top() + piece.y, w, piece.height))
            else:
                ratio = self.devicePixelRatioF()
                pixmap = self.images.pixmap(piece.source, int(piece.width * ratio), int(piece.height * ratio)) if self.images else None
                if pixmap:
                    p.drawPixmap(QtCore.QRect(area.left() + piece.x, area.top() + piece.y,
                                              piece.width, piece.height), pixmap)
        # A bare number means the format had no chapter heading: not worth a label.
        title = self.book.chapters[self.chapter].title
        label = "" if title.split(" · ")[0].isdigit() else title
        where = "%d/%d · %d%%" % (self.page + 1, len(pages), self.progress())
        y = self.height() - 20 - fs.height()
        p.setFont(small)
        p.setPen(dim)
        right = fs.horizontalAdvance(where) + 16
        p.drawText(QtCore.QRect(area.left(), y, area.width() - right, fs.height()), QtCore.Qt.AlignLeft,
                   fs.elidedText(label, QtCore.Qt.ElideRight, area.width() - right))
        p.drawText(QtCore.QRect(area.left(), y, area.width(), fs.height()), QtCore.Qt.AlignRight, where)


class PictureView(QtWidgets.QWidget):
    """A picture of the book on the whole window, to read a table or a figure: it opens fitted
    to the window; the wheel (or + and −) zooms around the pointer, a drag moves it, 0 fits it
    again, a click or Esc closes it."""

    def __init__(self, main, data):
        super().__init__(main)
        self.main = main
        self.image = QtGui.QImage.fromData(data)
        self.scale, self.offset, self.fitted = 1.0, QtCore.QPointF(), True
        self.pressed, self.moved = None, False
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setCursor(QtCore.Qt.OpenHandCursor)
        main.installEventFilter(self)
        self.setGeometry(main.rect())
        self.fit()
        self.show()
        self.raise_()
        self.setFocus()

    def eventFilter(self, obj, e):
        if obj is self.main and e.type() == QtCore.QEvent.Resize:
            self.setGeometry(self.main.rect())
            if self.fitted:
                self.fit()
        return False

    def fit(self):
        if self.image.isNull():
            return
        margin = 24
        self.scale = min((self.width() - 2 * margin) / self.image.width(), (self.height() - 2 * margin) / self.image.height())
        self.offset = QtCore.QPointF((self.width() - self.image.width() * self.scale) / 2,
                                     (self.height() - self.image.height() * self.scale) / 2)
        self.fitted = True
        self.update()

    def zoom(self, factor, around):
        if self.image.isNull():
            return
        fit = min(self.width() / self.image.width(), self.height() / self.image.height())
        scale = min(max(self.scale * factor, fit * 0.5), max(fit, 1.0) * 8)
        self.offset = around - (around - self.offset) * (scale / self.scale)
        self.scale, self.fitted = scale, False
        self.update()

    def close_view(self):
        self.main.removeEventFilter(self)
        self.hide()
        self.main.reader.setFocus()
        self.deleteLater()

    def paintEvent(self, _e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QtGui.QColor(self.main.colors["bg"]))
        if not self.image.isNull():
            p.drawImage(QtCore.QRectF(self.offset, QtCore.QSizeF(self.image.width() * self.scale, self.image.height() * self.scale)), self.image)

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps:
            self.zoom(1.25 ** steps, QtCore.QPointF(e.pos()))

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self.pressed, self.moved = e.pos(), False
            self.setCursor(QtCore.Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self.pressed is None:
            return
        if not self.moved and (e.pos() - self.pressed).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return
        self.offset += QtCore.QPointF(e.pos() - self.pressed)
        self.pressed, self.moved, self.fitted = e.pos(), True, False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.RightButton or self.pressed is not None and not self.moved:
            return self.close_view()
        self.pressed = None
        self.setCursor(QtCore.Qt.OpenHandCursor)

    CLOSE_KEYS = (QtCore.Qt.Key_Escape, QtCore.Qt.Key_Back, QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Q)

    def event(self, e):
        # Esc and Backspace are the window's "back": while the picture is open, they close it
        if e.type() == QtCore.QEvent.ShortcutOverride and e.key() in self.CLOSE_KEYS:
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        key, middle = e.key(), QtCore.QPointF(self.width() / 2, self.height() / 2)
        if key in self.CLOSE_KEYS:
            self.close_view()
        elif key in (QtCore.Qt.Key_Plus, QtCore.Qt.Key_Equal):
            self.zoom(1.25, middle)
        elif key == QtCore.Qt.Key_Minus:
            self.zoom(0.8, middle)
        elif key == QtCore.Qt.Key_0:
            self.fit()


# ------------------------------------------------------------------------------------------
# The window
# ------------------------------------------------------------------------------------------

SHELF, BOOK, CHAPTERS, SETTINGS, LIBRARY, FOLDER, ALL_BOOKS, LIBRARY_FOLDERS, SEARCH = "shelf", "book", "chapters", "settings", "library", "folder", "all", "library_folders", "search"
NEWS = "news"
ISSUES = "issues"       # the issues on this computer of one magazine ("magazine", key) or of one followed folder ("folder", path)
ADD_TO_LIBRARY = "add_to_library"       # choosing the folder of the library a book of the shelf is sent to
UI_SIZES = {"S": 11, "M": 13, "L": 15}


class Main(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.theme = self.cfg.get("theme", "DARK")
        self.library = Library()
        self.remote = RemoteLibrary()
        self.following = Following()
        self.follow_progress = {}       # folder -> (done, total) while its new books are fetched; total 0 while it is listed
        self.follow_errors = {}         # folder -> why the last click did not bring everything
        self.follow_changed, self.follow_seen = 0, 0
        self.awake = Awake()
        self.stack = [self.home_screen()]
        self.rows = []
        self.threads = []
        self.importing = False
        self.import_failed = False
        # papers in PDF waiting to become books; what the converter is doing, the last failure
        self.papers, self.paper_doing, self.paper_error = [], None, ""
        self.paper_step = Step()
        self.paper_step.said.connect(self.paper_said)
        self.syncing, self.sync_again = set(), set()    # highlights on their way to the drive
        self.fetching = None            # the drive reference of the book being downloaded
        self.sending, self.sent, self.send_error = False, None, ""     # a book of the shelf on its way to the drive
        self.fetch_error = ""
        self.credentials_message = ""
        self.image_stores = {}
        self.seen_change = -1
        self.folders_before = []        # the library's folders as they were when their page was opened
        self.colors = palette(self.theme)
        self.setWindowTitle("Reader's Books")
        self.setAcceptDrops(True)
        self._build()
        self.apply_style()
        geometry = self.cfg.get("geometry")
        if geometry and len(geometry) == 4:
            self.resize(geometry[2], geometry[3])
            self.move(geometry[0], geometry[1])
        else:
            self.resize(760, 900)
        self.show_screen(reset=True)         # the library, when it is the home screen, looks for new transcripts
        self.poll = QtCore.QTimer(self)
        self.poll.timeout.connect(self.watch_scan)
        self.poll.start(400)
        self.place_timer = QtCore.QTimer(self)
        self.place_timer.setSingleShot(True)
        self.place_timer.timeout.connect(lambda: self.sync_place())
        QtCore.QTimer.singleShot(0, self.sync_shelf)
        self.sleep_timer = QtCore.QTimer(self)
        self.sleep_timer.setSingleShot(True)
        self.sleep_timer.timeout.connect(lambda: self.awake.set(False))

    # ---- building ----

    def _build(self):
        self.pages = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.pages)

        page = QtWidgets.QWidget()
        outer = QtWidgets.QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        self.column = QtWidgets.QWidget()
        self.column.setMaximumWidth(820)
        outer.addStretch(1)
        outer.addWidget(self.column, 100)
        outer.addStretch(1)
        box = QtWidgets.QVBoxLayout(self.column)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(24, 18, 16, 14)
        bar.setSpacing(12)
        self.back = Clickable("←", "sign")
        self.back.clicked.connect(self.pop)
        self.title = Clickable("", "title")
        self.title.clicked.connect(self.pop)
        self.more = Clickable("⋯", "sign")
        self.more.clicked.connect(self.page_menu)
        bar.addWidget(self.back)
        bar.addWidget(self.title, 1)
        bar.addWidget(self.more)
        box.addLayout(bar)
        box.addWidget(self._rule())

        self.listing = Listing()
        self.listing.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.listing.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.listing.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.listing.customContextMenuRequested.connect(self.row_menu)
        self.listing.viewport().setAttribute(QtCore.Qt.WA_Hover, True)      # the card under the mouse
        self.listing.itemClicked.connect(self.activate)
        self.listing.itemActivated.connect(self.activate)
        self.delegate = RowDelegate(self)
        self.listing.setItemDelegate(self.delegate)
        box.addWidget(self.listing, 1)

        self.foot_rule = self._rule()
        box.addWidget(self.foot_rule)
        self.foot_open = Clickable("", "foot")
        self.foot_open.clicked.connect(self.pick_book)
        # no library yet: one quiet line under the shelf says what it would bring, and leads to setting it up
        self.foot_invite = Clickable("", "invite")
        self.foot_invite.setWordWrap(True)
        self.foot_invite.clicked.connect(lambda: self.push((LIBRARY,)))
        box.addWidget(self.foot_open)
        box.addWidget(self.foot_invite)
        self.pages.addWidget(page)

        self.reader = Reader(self)
        self.pages.addWidget(self.reader)

        for keys, action in (("Escape", self.pop), ("Backspace", self.pop), ("Alt+Left", self.pop),
                             ("Ctrl+O", self.pick_book), ("Ctrl+Q", self.close)):
            shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(keys), self)
            shortcut.activated.connect(action)

    def _rule(self):
        line = QtWidgets.QFrame()
        line.setObjectName("sep")
        line.setFixedHeight(1)
        return line

    # ---- look ----

    def ui_family(self):
        return {"serif": SERIF_FAMILY or "serif", "mono": "monospace"}.get(self.cfg.get("font"), SANS_FAMILY)

    def _font(self, delta):
        font = QtGui.QFont(self.ui_family())
        font.setPointSize(max(7, UI_SIZES.get(self.cfg.get("text_size"), 13) + delta))
        if self.cfg.get("font", "sans") == "sans":
            font.setWeight(QtGui.QFont.Light)
        return font

    def big_font(self):
        return self._font(2)

    def small_font(self):
        return self._font(-2)

    def apply_style(self):
        self.colors = palette(self.theme)
        bg, fg, accent, on_accent = self.colors["bg"], self.colors["fg"], self.colors["accent"], self.colors["on_accent"]
        dim, rule = rgba(fg, 0.55), rgba(fg, 0.25)
        self.colors = dict(self.colors, dim=blend(fg, bg, 0.55))      # for rich text, which knows no rgba()
        s = UI_SIZES.get(self.cfg.get("text_size"), 13)
        weight = 300 if self.cfg.get("font", "sans") == "sans" else 400
        common = f"""
            QMainWindow, QWidget {{ background: {bg}; color: {fg}; font-family: "{self.ui_family()}";
                                    font-size: {s}pt; font-weight: {weight}; }}
            QLabel#title {{ font-size: {s + 5}pt; }}
            QLabel#invite {{ font-size: {s}pt; padding: 6px 24px 14px 24px; }}
            QLabel#sign {{ font-size: {s + 7}pt; padding: 0 8px; }}
            QLabel#page {{ font-size: {s - 1}pt; color: {dim}; padding: 6px 24px 14px 24px; }}
            QListWidget {{ background: {bg}; border: none; outline: none; }}
            QScrollBar:vertical {{ background: {bg}; width: 6px; }}
            QScrollBar:horizontal {{ background: {bg}; height: 0; }}
            QScrollBar::handle:vertical {{ background: {rule}; min-height: 24px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: {bg}; }}
            QMenu::item {{ padding: 8px 26px; }}
            QMenu::item:selected {{ background: {accent}; color: {on_accent}; }}
            QMenu::item:disabled {{ color: {dim}; }}
        """
        if self.colors["tiles"]:
            # a colour theme: what can be clicked is a rounded card in the « key » colour on the
            # surface, the mouse over it shows « press »; the rules become space; dialogs keep the surface
            tile, press = self.colors["tile"], self.colors["press"]
            self.setStyleSheet(common + f"""
                QLabel#foot {{ font-size: {s + 2}pt; background: {tile}; border-radius: {TILE_CORNER}px;
                               margin: {TILE_GAP_V}px {TILE_GAP_H}px; padding: 11px {24 - TILE_GAP_H}px; }}
                QLabel#foot:hover {{ background: {press}; }}
                QFrame#sep {{ background: transparent; }}
                QMenu {{ background: {tile}; color: {fg}; border: none; padding: 6px 0; }}
                QMenu::separator {{ height: 1px; background: transparent; margin: 6px 0; }}
                QLineEdit, QPlainTextEdit, QTextEdit {{ background: {tile}; color: {fg}; border: none; border-radius: 8px; padding: 8px 10px; }}
                QPushButton {{ background: {tile}; color: {fg}; border: none; border-radius: 10px; padding: 8px 18px; }}
                QPushButton:hover, QPushButton:pressed {{ background: {press}; }}
                QPushButton:default {{ background: {accent}; color: {on_accent}; }}
                QToolTip {{ background: {tile}; color: {fg}; border: none; }}
            """)
        else:
            self.setStyleSheet(common + f"""
                QLabel#foot {{ font-size: {s + 2}pt; padding: 14px 24px; }}
                QFrame#sep {{ background: {rule}; }}
                QMenu {{ background: {bg}; color: {fg}; border: 1px solid {rule}; padding: 6px 0; }}
                QMenu::separator {{ height: 1px; background: {rule}; margin: 6px 0; }}
                QLineEdit {{ background: {bg}; color: {fg}; border: 1px solid {rule}; padding: 6px; }}
                QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {fg}; padding: 6px 18px; }}
                QPushButton:default {{ background: {accent}; color: {on_accent}; }}
                QToolTip {{ background: {bg}; color: {fg}; border: 1px solid {rule}; }}
            """)
        self.delegate.fg, self.delegate.bg = QtGui.QColor(fg), QtGui.QColor(bg)
        self.delegate.accent, self.delegate.on_accent = QtGui.QColor(accent), QtGui.QColor(on_accent)
        self.delegate.tile, self.delegate.press = QtGui.QColor(self.colors["tile"]), QtGui.QColor(self.colors["press"])
        self.delegate.tiles = self.colors["tiles"]
        self.delegate.big, self.delegate.small = self.big_font(), self.small_font()
        self.listing.doItemsLayout()
        self.reader.key = None
        self.reader.update()

    def next_theme(self):
        """The theme after the current one: the other ink, then the Plume palettes."""
        self.theme = next_theme(self.theme)
        self.cfg["dark"] = is_dark(palette(self.theme)["bg"])      # for a version from before the themes
        self.set("theme", self.theme)

    def set(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)
        self.apply_style()
        self.show_screen()

    def set_reader_size(self, delta):
        """delta 0 = back to the automatic size."""
        self.set("reader_pt", 0 if delta == 0 else min(MAX_READER_PT, max(MIN_READER_PT, reader_pt(self.cfg) + delta)))

    # ---- threads ----

    def run(self, job, done):
        """One job on a thread of its own. The thread and its worker are kept in a list: a
        QThread that Python collects half way through simply stops, silently."""
        thread = QtCore.QThread(self)
        worker = Worker(job)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def finished(result, error):
            done(result, error)
            thread.quit()

        worker.done.connect(finished)
        pair = (thread, worker)
        thread.finished.connect(lambda: self.threads.remove(pair) if pair in self.threads else None)
        self.threads.append(pair)
        thread.start()

    # ---- going from one screen to another ----

    @property
    def screen(self):
        return self.stack[-1]

    def push(self, screen):
        self.fetch_error = ""
        if screen[0] == LIBRARY_FOLDERS:
            self.folders_before = (chosen_folders(self.cfg), excluded_folders(self.cfg))
        if screen[0] == ADD_TO_LIBRARY:
            self.sending, self.sent, self.send_error = False, None, ""
        self.stack.append(screen)
        self.show_screen(reset=True)

    def pop(self):
        if len(self.stack) > 1:
            self.fetch_error = ""
            left = self.stack.pop()
            # the folders of the library left changed: it syncs quietly, so folders taken back in are read again
            if left[0] == LIBRARY_FOLDERS and (chosen_folders(self.cfg), excluded_folders(self.cfg)) != self.folders_before:
                self.remote.sync_quietly(self.cfg)
            self.show_screen(reset=True)

    def home(self):
        del self.stack[1:]

    def after_moves(self):
        """Books that went on under another entry or address (see Library._moved): their note,
        when the book's name changed with it, goes from under the old name, and the highlights
        they brought go to the drive."""
        while self.library.moved:
            old, new = self.library.moved.pop(0)
            index = self.remote.index["books"]
            old_name, new_name = book_file_name(old, index), book_file_name(new, index)
            if note_file_name(old_name) != note_file_name(new_name) and notes_account(self.cfg):
                cfg = dict(self.cfg)
                self.run(lambda cfg=cfg, n=old_name: write_note(cfg, n, []), lambda _r, _e: None)
            now = self.library.get(new["id"])
            if now:
                self.sync_highlights(now)

    def home_screen(self):
        """The first screen: the library when one is set up (the shelf is then a row of it), else the shelf."""
        return (LIBRARY,) if library_configured(self.cfg) else (SHELF,)

    def rehome(self):
        """The home screen follows the library being set up or forgotten: the screens above it
        stay, the same screen just above it is folded into it."""
        home = self.home_screen()
        if self.stack[0] != home:
            self.stack[0] = home
            while len(self.stack) > 1 and self.stack[1] == home:
                del self.stack[1]

    def to_library(self):
        """To the library: back down to it when it is the home screen, else on top."""
        if self.stack[0] == (LIBRARY,):
            self.home()
            self.show_screen(reset=True)
        else:
            self.push((LIBRARY,))

    def back_label(self):
        """What a back leads to, named as the screen below calls itself."""
        below = self.stack[-2][0] if len(self.stack) > 1 else None
        if below in (LIBRARY, FOLDER, ALL_BOOKS, SEARCH, NEWS):
            return _("library")
        if below == SHELF and self.stack[0][0] != SHELF:
            return _("on this computer")
        return _("books")

    def open_entry(self, entry, from_home=False):
        """A book of the shelf opened at its page. A magazine never opened shows its contents
        first; opened before, it goes back to the article it was left at, the contents one click above."""
        if from_home:
            self.home()
        self.push((CHAPTERS, entry["id"]) if entry.get("magazine") and not entry.get("opened") else (BOOK, entry["id"]))

    def to_contents(self, book_id):
        """From an article of a magazine to its contents: back down to them, or in place of the article."""
        if len(self.stack) > 1 and self.stack[-2] == (CHAPTERS, book_id):
            self.pop()
        else:
            self.stack.pop()
            self.push((CHAPTERS, book_id))

    def show_screen(self, reset=False):
        self.rehome()
        self.after_moves()
        kind = self.screen[0]
        if kind in (BOOK, CHAPTERS) and not self.library.get(self.screen[1]):
            self.stack.pop()
            return self.show_screen(reset=True)
        if kind == BOOK:
            entry = self.library.get(self.screen[1])
            if not self.reader.entry or self.reader.entry["id"] != entry["id"] or reset:
                self.reader.open(entry)
            self.pages.setCurrentWidget(self.reader)
            self.reader.setFocus()
            self.turned()
            return
        self.reader.close_book()
        self.awake.set(False)
        if kind == LIBRARY and reset:
            self.enter_library()
        title, rows, menu = getattr(self, "screen_" + kind)()
        self.rows, self.menu_items = rows, menu
        self.title.setText(title)
        self.back.setVisible(len(self.stack) > 1)
        self.more.setVisible(bool(menu))
        shelf = kind == SHELF
        self.foot_rule.setVisible(shelf)
        self.foot_open.setVisible(shelf)
        self.foot_open.setText(_("+ open a book"))
        self.foot_invite.setVisible(shelf and not library_configured(self.cfg))
        self.foot_invite.setText(_("set up a library") + "<br><span style='color:%s'>%s</span>" % (self.colors["dim"], _("your books on your drive, on all your devices")))
        scroll = 0 if reset else self.listing.verticalScrollBar().value()
        self.listing.clear()
        current = None
        for i, row in enumerate(rows):
            item = QtWidgets.QListWidgetItem(row.title)
            item.setData(QtCore.Qt.UserRole, i)
            if row.kind != ROW or not row.action:
                item.setFlags(QtCore.Qt.NoItemFlags)
            self.listing.addItem(item)
            if row.current:
                current = item
        self.pages.setCurrentIndex(0)
        if current and reset:
            self.listing.scrollToItem(current, QtWidgets.QAbstractItemView.PositionAtCenter)
        else:
            self.listing.verticalScrollBar().setValue(scroll)
        self.listing.setFocus()

    def activate(self, item):
        i = item.data(QtCore.Qt.UserRole)
        if i is not None and i < len(self.rows) and self.rows[i].kind == TOOLS:
            rect = self.listing.visualItemRect(item)
            for (_label, action), box in zip(self.rows[i].tools, self.delegate.tool_rects(self.rows[i], rect)):
                if box.contains(self.listing.last_press):
                    self.listing.clearSelection()
                    action()
            return
        if i is not None and i < len(self.rows) and self.rows[i].action:
            self.listing.clearSelection()
            self.listing.setCurrentItem(None)
            self.rows[i].action()

    def build_menu(self, items, title=None, menu=None):
        """A menu of plain words. `items` are (label, action), None for a rule; an action that is
        itself a list of items is a submenu (the orders)."""
        menu = menu or QtWidgets.QMenu(self)
        if title:
            head = menu.addAction(QtGui.QFontMetrics(self.font()).elidedText(title, QtCore.Qt.ElideRight, 360))
            head.setEnabled(False)
            menu.addSeparator()
        for entry in items:
            if entry is None:
                menu.addSeparator()
            elif isinstance(entry[1], (list, tuple)):
                self.build_menu(entry[1], menu=menu.addMenu(entry[0]))
            else:
                menu.addAction(entry[0], entry[1])
        return menu

    def popup(self, items, where, title=None):
        self.build_menu(items, title).exec_(where)

    def page_menu(self):
        if self.menu_items:
            self.popup(self.menu_items, self.more.mapToGlobal(self.more.rect().bottomLeft()))

    def row_menu(self, point):
        item = self.listing.itemAt(point)
        i = item.data(QtCore.Qt.UserRole) if item else None
        if i is not None and i < len(self.rows) and self.rows[i].menu:
            self.popup(self.rows[i].menu(), self.listing.viewport().mapToGlobal(point), self.rows[i].title)

    def theme_item(self):
        return (theme_name(next_theme(self.theme)), self.next_theme)

    # ---- the shelf ----

    def screen_shelf(self):
        rows = []
        if self.importing:
            rows.append(Row("…", kind=HINT))
        elif self.import_failed:
            rows.append(Row(_("this file could not be read"), kind=HINT))
        if self.paper_doing:
            waiting = len(self.papers) - (0 if self.paper_doing.startswith(_("setting up the converter…")) else 1)
            rows.append(Row(self.paper_doing + (" · " + n_papers(waiting) if waiting > 0 else ""), kind=HINT))
        elif self.papers and not converter_ready():
            rows.append(Row(_("A PDF is not read as it is: it is turned into an EPUB, a book of the shelf, its figures, tables and equations as pictures; the PDF itself is left as it was. The converter is set up once: about 2 GB downloaded."), kind=HINT))
            rows.append(Row(_("set up the converter"), n_papers(len(self.papers)), self.set_up_converter))
        if self.paper_error:
            rows.append(Row(self.paper_error, kind=HINT))
        if not self.library.books and not self.importing:
            rows.append(Row(_("nothing on the shelf. Open an epub, mobi, fb2 or plain-text file, or a PDF to turn into an EPUB: from here, or by dropping it on this window.")
                            if PAPERS_POSSIBLE else
                            _("nothing on the shelf. Open an epub, mobi, fb2 or plain-text file: from here, or by dropping it on this window."), kind=HINT))
        # the shelf's order: by last opened (or added), by title, or by last added
        order = self.cfg.get("shelf_sort", "OPENED")
        books = list(self.library.books)
        if order == "TITLE":
            books.sort(key=lambda b: b["title"].lower())
        elif order == "ADDED":
            books.sort(key=lambda b: -b.get("added", 0))
        # the issues of one magazine make one row, where its latest issue would stand: a click
        # opens the latest issue where it was left, a right click lists them all
        groups, done = magazine_groups(books), set()
        for b in books:
            key = magazine_key(b["title"]) if b.get("magazine") else ""
            issues = groups.get(key)
            if issues:
                if key in done:
                    continue
                done.add(key)
                latest = issues[0]
                rows.append(Row(magazine_name(latest["title"]) + " · " + n_issues(len(issues)),
                                " · ".join((magazine_issue(latest["title"]), "%d%%" % latest.get("progress", 0) if latest.get("opened") else _("not started"))),
                                lambda latest=latest: self.open_entry(latest),
                                lambda key=key: [(_("issues on this computer"), lambda: self.push((ISSUES, "magazine", key)))]))
                continue
            rows.append(Row(b["title"], self.shelf_line(b), lambda b=b: self.open_entry(b), lambda b=b: self.shelf_menu(b)))
        menu = [(_("+ open a book"), self.pick_book), (_("library"), self.to_library),
                (_("order") + " · " + order_name(order), self.order_menu(SHELF_ORDERS, order, "shelf_sort")), None,
                self.theme_item(), (_("settings"), lambda: self.push((SETTINGS,)))]
        # the home screen without a library; with one, a page of it
        return (_("books") if len(self.stack) == 1 else _("on this computer")), rows, menu

    def shelf_line(self, b):
        return " · ".join(x for x in ("%d%%" % b.get("progress", 0) if b.get("opened") else _("not started"),
                                      when_label(b.get("opened", 0)), b["format"].lower()) if x)

    def shelf_menu(self, b):
        return ([(_("read"), lambda: self.push((BOOK, b["id"]))),
                 (_("contents") if b.get("magazine") else _("chapters"), lambda: self.push((CHAPTERS, b["id"]))),
                 (_("remove from the shelf"), lambda: self.remove(b["id"]))]
                + ([(_("add to the library"), lambda: self.push((ADD_TO_LIBRARY, b["id"])))] if can_send(self.cfg, b) else []))

    def order_menu(self, orders, order, setting):
        """The orders a list can take, the current one ticked, as a submenu."""
        return [(order_name(o) + ("  ✓" if o == order else ""), lambda o=o: self.set(setting, o)) for o in orders]

    def remove(self, book_id):
        entry = self.library.get(book_id)
        self.library.remove(book_id)
        if entry:
            self.following.removed(entry)
        if self.screen[0] in (BOOK, CHAPTERS):
            self.home()
        self.show_screen(reset=self.screen[0] != SHELF)

    def pick_book(self):
        # a PDF is opened only to be turned into an EPUB: the dialog says so
        kinds = ("%s (%s);;%s (*.pdf)" % (_("books, or a PDF to turn into an EPUB"), OPEN_FILTER, _("a PDF, turned into an EPUB"))
                 if PAPERS_POSSIBLE else "%s (%s)" % (_("books"), OPEN_FILTER))
        path, _sel = QtWidgets.QFileDialog.getOpenFileName(
            self, _("+ open a book").lstrip("+ "), self.cfg.get("last_dir") or os.path.expanduser("~"), kinds + ";;* (*)")
        if path:
            self.cfg["last_dir"] = os.path.dirname(path)
            save_config(self.cfg)
            self.import_files([path])

    def import_files(self, paths):
        """Books opened from here, dropped on the window or handed over by the file manager: they
        land on the shelf, and the last one opens."""
        papers = [p for p in paths if PAPERS_POSSIBLE and is_pdf(p)]
        paths = [p for p in paths if p not in papers]
        if papers:
            self.add_papers(papers)
        if not paths or self.importing:
            return
        self.importing, self.import_failed = True, False
        self.home()
        self.show_screen(reset=True)

        def job():
            entry = None
            failed = False
            for path in paths:
                try:
                    entry = self.library.add(path, os.path.basename(path))
                except Exception:
                    failed = True
            return entry, failed

        def done(result, _error):
            self.importing = False
            entry, failed = result if result else (None, True)
            self.import_failed = failed
            if entry:
                self.open_entry(entry, from_home=True)
            else:
                self.show_screen()

        self.run(job, done)

    # ---- papers in PDF ----

    def add_papers(self, paths):
        """Papers wait on the shelf for the converter: set up first if it is not yet, then one
        after the other; each becomes a book of the shelf."""
        self.papers += [p for p in paths if p not in self.papers]
        self.paper_error = ""
        self.home()
        self.show_screen(reset=True)
        if converter_ready():
            self.next_paper()

    def paper_said(self, text):
        self.paper_doing = text
        if self.screen[0] == SHELF:
            self.show_screen()

    def set_up_converter(self):
        if self.paper_doing:
            return
        self.paper_error = ""
        self.paper_said(_("setting up the converter…"))
        say = self.paper_step.said.emit

        def done(_result, error):
            self.paper_doing = None
            if error:
                self.paper_error = _("the converter could not be set up: %s") % error
                self.paper_said(None)
            else:
                self.next_paper()

        self.run(lambda: set_up_converter(lambda n, of: say("%s %d/%d" % (_("setting up the converter…"), n, of))), done)

    def next_paper(self):
        if self.paper_doing or not self.papers:
            return
        path = self.papers[0]
        name = os.path.splitext(os.path.basename(path))[0]
        doing = _("the PDF “%s” is being turned into an EPUB…") % name
        words = {"models": _("loading the models"), "pages": _("reading the pages"), "book": _("making the EPUB"),
                 "ocr": _("reading the scanned pages"),
                 # an issue of a magazine (magazine2epub.py)
                 "reading": _("reading the pages"), "pictures": _("making the EPUB")}
        say = self.paper_step.said.emit
        self.paper_said(doing)
        notices = []

        def stepped(word, page=None, of=None):
            say("%s %s" % (doing, words.get(word, "")) + (" %d/%d" % (page, of) if of else ""))

        def job():
            epub = convert_paper(path, stepped, notices.append)
            return self.library.add(epub, name + ".epub", move=True)

        def done(entry, error):
            self.papers.pop(0)
            self.paper_doing = None
            if error:
                self.paper_error = _("the PDF “%s” could not be turned into an EPUB: %s") % (name, error)
            elif "no-ocr" in notices:
                self.paper_error = _("“%s” is a scan: its pages are pictures. To get its text, install Tesseract (the tesseract-ocr package) and open the PDF again.") % name
            if not error and not self.papers and self.screen[0] == SHELF:
                return self.open_entry(entry, from_home=True)
            if self.papers:
                self.next_paper()
            else:
                self.paper_said(None)

        self.run(job, done)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.import_files([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    # ---- the reader's menu, the chapters ----

    def sync_place(self, book_id=None):
        entry = self.library.get(book_id or (self.reader.entry or {}).get("id", ""))
        if entry:
            self.sync_highlights(entry)

    def turned(self):
        """The screen stays awake while a page is open, until fifteen minutes after the last turn."""
        self.place_timer.start(30 * 1000)       # and the place goes to the drive once the reading pauses
        if self.cfg.get("keep_awake", True):
            self.awake.set(True)
            self.sleep_timer.start(15 * 60 * 1000)

    def reader_menu(self, where):
        entry = self.reader.entry
        if not entry:
            return
        size = reader_pt(self.cfg)
        serif = bool(self.cfg.get("book_serif"))
        book_id = entry["id"]

        def contents():
            self.to_contents(book_id)

        self.popup([
            (_("contents"), contents) if entry.get("magazine") else (_("chapters"), lambda: self.push((CHAPTERS, book_id))),
            ("%s  ·  %d → %d" % (_("larger text"), size, min(MAX_READER_PT, size + 1)), lambda: self.set_reader_size(+1)),
            ("%s  ·  %d → %d" % (_("smaller text"), size, max(MIN_READER_PT, size - 1)), lambda: self.set_reader_size(-1)),
            ("%s  ·  %s → %s" % (_("book text"), _("serif") if serif else _("sans-serif"), _("sans-serif") if serif else _("serif")),
             lambda: self.set("book_serif", not serif)),
            (_("remove from the shelf"), lambda: self.remove(book_id)),
        ] + ([(_("add to the library"), lambda: self.push((ADD_TO_LIBRARY, book_id)))] if can_send(self.cfg, entry) else [])
          + ([(_("export the highlights"), self.export_highlights)] if live_highlights(self.reader.highlights) else []) + [
            None,
            (self.back_label(), self.pop),
            self.theme_item(),
        ], where, entry["title"])

    # ---- highlights and comments ----

    def selection_menu(self, where, chapter, start, end):
        text = self.reader.text_of(chapter).cut(start, end)
        self.popup([(_("highlight"), lambda: self.add_highlight(chapter, start, end, text, False)),
                    (_("comment"), lambda: self.add_highlight(chapter, start, end, text, True)),
                    (_("copy"), lambda: self.copy_text(text)),
                    None, (_("cancel"), lambda: None)], where)

    def copy_text(self, text):
        """The passage alone, for a message or a note elsewhere: the export carries the attribution."""
        QtWidgets.QApplication.clipboard().setText(text)

    def ask_comment(self, initial=""):
        dialog = QtWidgets.QInputDialog(self)
        dialog.setWindowTitle("Reader's Books")
        dialog.setLabelText(_("comment"))
        dialog.setOption(QtWidgets.QInputDialog.UsePlainTextEditForTextInput, True)
        dialog.setOkButtonText(_("ok"))
        dialog.setCancelButtonText(_("cancel"))
        dialog.setTextValue(initial)
        for box in dialog.findChildren(QtWidgets.QPlainTextEdit):
            box.setMinimumWidth(box.fontMetrics().averageCharWidth() * 50)
        return dialog.textValue().strip() if dialog.exec_() == QtWidgets.QDialog.Accepted else None

    def add_highlight(self, chapter, start, end, text, with_comment):
        # The very passage is highlighted already: nothing to add, or its comment to write.
        same = next((h for h in self.reader.shown if (h["chapter"], h["start"], h["end"]) == (chapter, start, end)), None)
        comment = ""
        if with_comment:
            comment = self.ask_comment((same or {}).get("comment", ""))
            if comment is None:
                return
        if same:
            if with_comment:
                self.change_highlights([dict(h, comment=comment, modified=_now()) if h["id"] == same["id"] else h
                                        for h in self.reader.highlights])
            return
        self.change_highlights(self.reader.highlights + [new_highlight(chapter, start, end, text, comment)])

    def highlight_menu(self, where, found):
        """A click on a highlight: its comment if it has one, and what can be done with it."""
        comment = (found.get("comment") or "").strip()

        def edit():
            text = self.ask_comment(comment)
            if text is not None:
                self.change_highlights([dict(h, comment=text, modified=_now()) if h["id"] == found["id"] else h
                                        for h in self.reader.highlights])

        def remove():
            # Kept in the list as removed: that is what tells the other devices.
            self.change_highlights([dict(h, deleted=True, text="", comment="", modified=_now()) if h["id"] == found["id"] else h
                                    for h in self.reader.highlights])

        def copy():
            self.copy_text(self.reader.text_of(found["chapter"]).cut(found["start"], found["end"]))

        if not comment:
            return self.popup([(_("add a comment"), edit), (_("copy"), copy), (_("remove the highlight"), remove)], where)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Reader's Books")
        box = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel(comment)
        label.setWordWrap(True)
        label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        label.setMinimumWidth(label.fontMetrics().averageCharWidth() * 50)
        box.addWidget(label)
        buttons = QtWidgets.QDialogButtonBox()
        closing = buttons.addButton(_("ok"), QtWidgets.QDialogButtonBox.AcceptRole)
        editing = buttons.addButton(_("edit the comment"), QtWidgets.QDialogButtonBox.ActionRole)
        copying = buttons.addButton(_("copy"), QtWidgets.QDialogButtonBox.ActionRole)
        removing = buttons.addButton(_("remove the highlight"), QtWidgets.QDialogButtonBox.ActionRole)
        closing.setDefault(True)
        choice = []
        closing.clicked.connect(dialog.accept)
        editing.clicked.connect(lambda: (choice.append(edit), dialog.accept()))
        copying.clicked.connect(lambda: (choice.append(copy), dialog.accept()))
        removing.clicked.connect(lambda: (choice.append(remove), dialog.accept()))
        box.addWidget(buttons)
        dialog.exec_()
        if choice:
            choice[0]()

    def change_highlights(self, highlights):
        entry = self.reader.entry
        if not entry:
            return
        save_highlights(entry, highlights, True, book_file_name(entry, self.remote.index["books"]))
        self.reader.set_highlights(highlights)
        self.sync_highlights(entry)

    def sync_highlights(self, entry, position=None, opening=False):
        """One book brought in step with the drive, in the background: its highlights, its note
        in Reader's Notes, the place it was left at. `position` is the place to speak for (the one
        the book had before it was opened, when it is being opened); what could not be sent is
        sent the next time."""
        key = highlight_key(entry)
        if not sidecar_address(self.cfg, entry) and not note_only(self.cfg, entry):
            return
        if key in self.syncing:
            self.sync_again.add(key)
            return
        self.syncing.add(key)
        cfg, book_id = dict(self.cfg), entry["id"]
        name = book_file_name(entry, self.remote.index["books"])
        snapshot = dict(entry)

        def done(result, error):
            self.syncing.discard(key)
            if error is None and result is not None:
                self.synced(book_id, key, result, opening)
            if key in self.sync_again:
                self.sync_again.discard(key)
                now = self.library.get(book_id)
                if now:
                    self.sync_highlights(now)

        self.run(lambda: sync_book(cfg, snapshot, name, position), done)

    def synced(self, book_id, key, result, opening=False):
        """What a sync brought: highlights made elsewhere, and a place read later elsewhere —
        taken for the shelf, and for the page itself when the book is just being opened."""
        merged, there = result
        reader = self.reader
        reading = reader.entry is not None and highlight_key(reader.entry) == key
        if reading and merged != reader.highlights:
            reader.set_highlights(merged)
        if there and self.library.get(book_id):
            if reading and not (opening and reader.turns == 0):
                return                              # being read here: this page is the newer place
            self.library.save_position(book_id, there["chapter"], there["charOffset"], there.get("progress", 0), there["modified"])
            if reading:
                reader.go_to(there["chapter"], there["charOffset"])
            elif self.screen[0] == SHELF:
                self.show_screen()

    def sync_shelf(self):
        """At the start: every book of the shelf that came from the library, one after the
        other, so that the shelf says how far each one is wherever it was last read."""
        cfg = dict(self.cfg)
        books = [dict(b) for b in self.library.books if sidecar_address(cfg, b) or note_only(cfg, b)]
        if not books:
            return
        index = self.remote.index["books"]

        def job():
            out = []
            for b in books:
                try:
                    out.append((b["id"], highlight_key(b), sync_book(cfg, b, book_file_name(b, index))))
                except Exception:
                    pass
            return out

        def done(results, _error):
            for book_id, key, result in results or []:
                if result is not None:
                    self.synced(book_id, key, result)

        self.run(job, done)

    def export_highlights(self):
        entry = self.reader.entry
        if not entry:
            return
        name = book_file_name(entry, self.remote.index["books"])
        path, _sel = QtWidgets.QFileDialog.getSaveFileName(
            self, _("export the highlights"), os.path.join(self.cfg.get("last_dir") or os.path.expanduser("~"), note_file_name(name)),
            "%s (*.txt);;* (*)" % _("highlights"))
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(note_text(name, self.reader.highlights))
            except OSError:
                pass

    def images_of(self, entry):
        if entry["fileName"] not in self.image_stores:
            self.image_stores[entry["fileName"]] = ImageStore(self.library.path(entry))
        return self.image_stores[entry["fileName"]]

    def screen_chapters(self):
        entry = self.library.get(self.screen[1])
        try:
            book = self.library.book(entry)
        except Exception:
            return entry["title"], [Row(_("this file could not be read"), kind=HINT)], None
        book_id = entry["id"]

        def go(chapter, magazine):
            self.library.save_position(book_id, chapter, 0, entry.get("progress", 0))
            if not magazine:
                self.home()
            self.push((BOOK, book_id))

        def article(start):
            # the article where it was left, else at its top
            at = (entry.get("places") or {}).get(str(start))
            self.library.save_position(book_id, at[0] if at else start, at[1] if at else 0, entry.get("progress", 0), article=start)
            self.push((BOOK, book_id))

        rows = []
        if book.magazine:
            return entry["title"], self.contents_rows(entry, book, article), None
        # The parts a long chapter was cut into are one line: the chapter.
        listed = [(i, ch) for i, ch in enumerate(book.chapters)
                  if i == 0 or not ch.title.startswith(book.chapters[i - 1].title.split(" · ")[0] + " · ")]
        before = [i for i, _ch in listed if i <= entry.get("chapter", 0)]
        current = before[-1] if before else None
        for i, ch in listed:
            rows.append(Row(ch.title, "", lambda i=i: go(i, False), current=i == current, lines=1))
        return entry["title"], rows, None

    def contents_rows(self, entry, book, article):
        """A magazine's contents: its articles under their sections' names, with their authors
        and larger pictures, in a list that scrolls like the others, centred on the article read
        last; a click opens an article."""
        store = self.images_of(entry)
        reading = [a for a in book.magazine if a.chapter <= entry.get("chapter", 0) and entry.get("opened")]
        current = reading[-1] if reading else None
        rows = []
        for i, a in enumerate(book.magazine):
            if a.category and (i == 0 or a.category != book.magazine[i - 1].category):
                rows.append(Row(a.category.upper(), kind=SECTION))
            rows.append(Row(a.title, a.author or "", lambda a=a: article(a.chapter), current=a is current, lines=3,
                            thumb=(store, a.image) if a.image else None, thumb_size=104))
        return rows

    # ---- settings ----

    def screen_settings(self):
        cfg = self.cfg
        size = reader_pt(cfg)
        fonts = ("sans", "serif", "mono")
        sizes = ("S", "M", "L")
        font_names = {"sans": _("sans-serif"), "serif": _("serif"), "mono": _("mono")}
        rows = [
            Row(theme_name(self.theme), _("colours"), self.next_theme),
            Row(_("%d · auto", size) if not cfg.get("reader_pt") else str(size), _("reading size — click for larger"), lambda: self.set_reader_size(+1)),
            Row(_("smaller text"), "%d → %d" % (size, max(MIN_READER_PT, size - 1)), lambda: self.set_reader_size(-1)),
            Row(_("automatic size"), _("the size the app starts with"), lambda: self.set_reader_size(0)),
            Row(_("serif") if cfg.get("book_serif") else _("sans-serif"), _("book text"), lambda: self.set("book_serif", not cfg.get("book_serif"))),
            Row(font_names.get(cfg.get("font"), font_names["sans"]), _("font"),
                lambda: self.set("font", _after(fonts, cfg.get("font")))),
            Row(cfg.get("text_size", "M"), _("size of the shelf and menus"),
                lambda: self.set("text_size", _after(sizes, cfg.get("text_size", "M")))),
            Row(_("on") if cfg.get("keep_awake", True) else _("off"), _("keep the screen on while reading"),
                lambda: self.set("keep_awake", not cfg.get("keep_awake", True))),
            Row(kind=RULE),
            Row(LIBRARY_HINT(), kind=HINT),
        ]
        rows += self.account_rows()
        if library_configured(cfg):
            chosen = chosen_folders(cfg)
            excluded = excluded_folders(cfg)
            rows.append(Row(_("folders of the library"), " · ".join([n_folders_chosen(len(chosen)) if chosen else _("the whole drive")] + ([n_folders_left_out(len(excluded))] if excluded else [])), lambda: self.push((LIBRARY_FOLDERS,))))
        rows += self.credentials_rows()
        if library_started(cfg):
            rows.append(Row(_("forget the library"), _("removes the link, the login and the list of books; the shelf is kept"), self.forget_library))
        rows += [Row(kind=RULE), Row(HIGHLIGHTS_HINT(), kind=HINT),
                 Row(cfg.get("notes_url") or _("Reader's Notes folder"), _("Reader's Notes folder"), lambda: self.ask("notes_url")),
                 Row(cfg.get("notes_username") or _("same as the library"), _("username for the notes"), lambda: self.ask("notes_username")),
                 Row("••••••••" if cfg.get("notes_password") else _("same as the library"), _("password for the notes"), lambda: self.ask("notes_password"))]
        rows += [Row(kind=RULE),
                 Row("Reader's Books %s" % VERSION, _("reads epub, mobi, fb2 and txt files")),
                 Row(_("Pierre Gallaz · developed with Claude Code")),
                 Row("Literata", "The Literata Project Authors · SIL Open Font License 1.1"),
                 Row("Roboto", "Google · Apache License 2.0")]
        return _("settings"), rows, None

    # ---- the library's account ----

    def account_rows(self):
        cfg = self.cfg
        return [
            Row(cfg.get("url") or _("WebDAV address"), _("WebDAV address"), lambda: self.ask("url")),
            Row(cfg.get("username") or _("username"), _("username"), lambda: self.ask("username")),
            Row("••••••••" if cfg.get("password") else _("password"), _("password"), lambda: self.ask("password")),
        ]

    def ask(self, field):
        labels = {"url": _("WebDAV address"), "username": _("username"), "password": _("password"),
                  "notes_url": _("Reader's Notes folder"), "notes_username": _("username for the notes"), "notes_password": _("password for the notes")}
        dialog = QtWidgets.QInputDialog(self)
        dialog.setWindowTitle("Reader's Books")
        dialog.setLabelText(labels[field])
        dialog.setOkButtonText(_("ok"))
        dialog.setCancelButtonText(_("cancel"))
        secret = field.endswith("password")
        dialog.setTextEchoMode(QtWidgets.QLineEdit.Password if secret else QtWidgets.QLineEdit.Normal)
        dialog.setTextValue("" if secret else self.cfg.get(field, ""))
        # An address is long: the field is as wide as fifty characters of the text it holds.
        for line in dialog.findChildren(QtWidgets.QLineEdit):
            line.setMinimumWidth(line.fontMetrics().averageCharWidth() * 50)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        value = dialog.textValue()
        if field == "url":
            set_library_url(self.cfg, value)
        else:
            self.cfg[field] = value if secret else value.strip()
        save_config(self.cfg)
        if field.startswith("notes_"):
            return self.show_screen()
        self.account_changed()

    def account_changed(self):
        # What the drive answered to the old account no longer stands: with a new one the scan
        # is free to carry on by itself.
        self.remote.error = None
        if self.screen[0] == LIBRARY:
            self.enter_library()
        self.show_screen()

    def credentials_rows(self):
        rows = []
        if library_started(self.cfg):
            rows.append(Row(_("export credentials"), _("a file to set up another device — it holds the password"), lambda: self.credentials(True)))
        rows.append(Row(_("import credentials"), self.credentials_message, lambda: self.credentials(False)))
        return rows

    def credentials(self, export):
        start = os.path.expanduser("~/readers-books-credentials.json")
        kinds = "%s (*.json);;* (*)" % _("Reader's credentials")
        self.credentials_message = ""
        if export:
            path, _sel = QtWidgets.QFileDialog.getSaveFileName(self, _("export credentials"), start, kinds,
                                                             options=QtWidgets.QFileDialog.DontConfirmOverwrite)
        else:
            path, _sel = QtWidgets.QFileDialog.getOpenFileName(self, _("import credentials"), os.path.expanduser("~"), kinds)
        if not path:
            return
        try:
            if export:
                export_credentials(self.cfg, path)
                self.credentials_message = _("credentials exported — the file holds the password: keep it private")
            else:
                fallback = import_credentials(self.cfg, path)
                save_config(self.cfg)
                self.credentials_message = _("drive and login taken from another Reader's app") if fallback else _("credentials imported")
        except NotCredentials:
            self.credentials_message = _("not a Reader's credentials file")
        except NothingForUs:
            self.credentials_message = _("this file holds nothing for %s", "Reader's Books")
        except Exception as exc:
            self.credentials_message = _("the file cannot be read: %s", str(exc)[:120])
        self.account_changed()

    def forget_library(self):
        self.remote.forget()
        self.following.forget()
        set_library_url(self.cfg, "")
        self.cfg.update(username="", password="")
        save_config(self.cfg)
        self.show_screen()

    # ---- the library ----

    def enter_library(self):
        """A drive just set up, or set up differently, is walked at once; otherwise the drive is
        only synced by hand (« sync now », « continue the scan »), and only new transcripts are
        looked for."""
        if not library_configured(self.cfg) or self.remote.scanning:
            return
        if not self.remote.matches(self.cfg):
            self.remote.scan(self.cfg, True)
        else:
            self.remote.refresh_folder(self.cfg)

    def set_library_folders(self, folders):
        """The folders that make the library; chosen, the choice is no longer to be offered."""
        self.cfg.update(library_folders=sorted(set(f for f in folders if f)), library_folders_asked=True)
        save_config(self.cfg)
        self.show_screen()

    def set_library_excluded(self, folders):
        """The folders left out of the library; a chosen folder that is now left out is no longer chosen."""
        excluded = sorted(set(f for f in folders if f))
        chosen = [c for c in chosen_folders(self.cfg) if not left_out(excluded, c)]
        self.cfg.update(library_excluded=excluded, library_folders=chosen)
        save_config(self.cfg)
        self.show_screen()

    def offer_folders(self):
        self.cfg["library_folders_asked"] = True
        save_config(self.cfg)
        self.push((LIBRARY_FOLDERS,))

    def watch_scan(self):
        if self.remote.changed != self.seen_change or self.follow_changed != self.follow_seen:
            self.seen_change, self.follow_seen = self.remote.changed, self.follow_changed
            if self.screen[0] in (LIBRARY, FOLDER, ALL_BOOKS, LIBRARY_FOLDERS, NEWS):
                self.show_screen()

    def scan(self, fresh):
        self.remote.scan(self.cfg, fresh)
        self.show_screen()

    def stop_scan(self):
        self.remote.cancel()
        self.show_screen()

    def screen_library(self):
        cfg, remote = self.cfg, self.remote
        if not library_configured(cfg):
            return _("library"), [Row(LIBRARY_HINT(), kind=HINT)] + self.account_rows() + [Row(kind=RULE)] + self.credentials_rows(), None
        index, progress, error = remote.index, remote.progress if remote.scanning else None, remote.error
        rows = self.home_rows()
        folders, shown = remote.folders(cfg), remote.shown(cfg)
        # the tools, set apart from the books: buttons, what the sync did or does under them, and
        # what it asks for (a choice of folders, a scan to carry on, an error) in small print
        state = (_("scanning… %d folders, %d books", progress[0], progress[1]) if progress
                 else _("scanned on %s", date_label(index["scannedAt"])) if index["scannedAt"] > 0 else "")
        tools = [(_("search"), self.ask_search)] if shown else []
        tools.append((_("stop the scan"), self.stop_scan) if progress else (_("sync now"), lambda: self.scan(False)))
        rows.append(Row(kind=TOOLS, tools=tools, secondary=state))
        if error is not None and not progress:
            rows.append(Row(_("the drive refused the login") if isinstance(error, WrongLogin)
                            else _("the drive could not be read: %s", str(error)[:160] or type(error).__name__), kind=HINT))
        # once the drive was walked: keep only some of its folders?
        known = [f for f in remote.known_folders() if f[0]]
        if (not progress and index["complete"] and index["scannedAt"] > 0 and not cfg.get("library_folders_asked")
                and not chosen_folders(cfg) and len(known) > 1):
            rows.append(Row(_("keep only some folders?"), _("%d folders hold books — choose the ones for the library, or leave the whole drive", len(known)), self.offer_folders, kind=NOTE))
        unfinished = not progress and not index["complete"] and index["scannedAt"] > 0
        if unfinished:
            rows.append(Row(_("continue the scan"), _("the scan stopped after %d folders · %d books so far", index["folders"], len(index["books"])),
                            lambda: self.scan(False), kind=NOTE))
        if not progress and index["complete"] and index["failed"]:
            rows.append(Row(_("continue the scan"), _("%d folders could not be read", len(index["failed"])), lambda: self.scan(False), kind=NOTE))
        if not folders and not progress and error is None and index["complete"] and index["scannedAt"] > 0:
            rows.append(Row(_("no e-book found on the drive (epub, mobi, azw, fb2)"), kind=HINT))
        if shown:
            # then the books of the drive, and nothing else: its collections and its folders
            rows += [Row(kind=RULE), Row(_("on the drive").upper(), kind=SECTION)]
            # the newspapers and magazines, together, the newest first: there only when the library has some
            if not progress and index["scannedAt"] > 0:
                remote.sort_books(cfg, {e["source"]: e.get("magazine") for e in self.library.books if e.get("source")})
            news = remote.news(cfg)
            if news:
                sorting = remote.sorting
                rows.append(Row(_("news"), " · ".join(x for x in (
                    n_issues(len(news)), _("latest %s", date_label(remote.issue_date(news[0]))),
                    _("looking for more… %d/%d", sorting[0], sorting[1]) if sorting else "") if x),
                    lambda: self.push((NEWS,))))
            rows.append(Row(_("all books"), n_books(len(shown)), lambda: self.push((ALL_BOOKS,))))
        top = bool(cfg.get("library_top_folders"))
        for path, count, modified, spanned in folders:
            # a top folder says how many folders it spans; its books are listed with them
            line = " · ".join(x for x in (n_books(count), n_folders(spanned) if spanned > 1 else "",
                                          date_label(modified) if cfg.get("folder_sort") == "NEWEST" and modified > 0 else "") if x)
            rows.append(Row(path or _("top of the drive"), line, lambda path=path: self.push((FOLDER, path, top and bool(path))), lines=1,
                            menu=(lambda path=path: [
                                # followed: its new books are one click away, at the top of the library
                                (_("stop following this folder"), lambda: self.unfollow(path)) if self.following.get(path)
                                else (_("follow this folder") + "  ·  " + _("its new books one click away, at the top of the library"), lambda: self.follow(path)),
                                (_("leave this folder out"), lambda: self.set_library_excluded(excluded_folders(self.cfg) + [path]))]) if path else None))
        menu = []
        if not progress and (not index["complete"] or index["failed"]):
            menu.append((_("continue the scan"), lambda: self.scan(False)))
        menu.append((_("stop the scan"), self.stop_scan) if progress else (_("scan the drive again"), lambda: self.scan(True)))
        menu.append((_("every folder"), lambda: self.set("library_top_folders", False)) if top
                    else (_("group by top folder"), lambda: self.set("library_top_folders", True)))
        menu.append((_("order") + " · " + order_name(cfg.get("folder_sort", "NAME")), self.order_menu(FOLDER_ORDERS, cfg.get("folder_sort", "NAME"), "folder_sort")))
        if shown:
            menu.append((_("search"), self.ask_search))
        menu.append((_("folders of the library"), lambda: self.push((LIBRARY_FOLDERS,))))
        menu.append((_("settings"), lambda: self.push((SETTINGS,))))
        return _("library"), rows, menu

    def home_rows(self):
        """The top of the library: the book read last, one click from its page, and the books
        on this computer (the shelf)."""
        rows = []
        read = [b for b in self.library.books if b.get("opened")]
        if read:
            last = max(read, key=lambda b: b["opened"])
            rows.append(Row(last["title"], "%s · %d%%" % (_("continue reading"), last.get("progress", 0)),
                            lambda: self.push((BOOK, last["id"])), lines=1))
        rows.extend(self.followed_rows())
        rows.append(Row(_("on this computer"), n_books(len(self.library.books)), lambda: self.push((SHELF,))))
        return rows

    # ---- followed folders ----

    def followed_rows(self):
        """A row per followed folder: its name and how many new books it has, counted from the
        last listing of the drive (no network here). Nothing comes by itself: a click lists that
        folder again and fetches its new books, then opens the new one — or, when several came or
        none, the folder's issues on this computer. Right click: the issues, the whole folder, stop."""
        rows = []
        on_shelf = {b.get("source") for b in self.library.books if b.get("source")}
        for f in self.following.folders:
            folder = f["folder"]
            fresh = fresh_books(self.remote.index["books"], f, on_shelf)
            now, error = self.follow_progress.get(folder), self.follow_errors.get(folder)
            if now and not now[1]:
                line = _("looking for new books…")
            elif now:
                line = _("fetching %d of %d…", min(now[0] + 1, now[1]), now[1])
            elif error:
                line = error
            elif not fresh and f.get("checkedAt"):
                line = _("nothing new · %s", when_label(f["checkedAt"]))
            else:
                line = _("followed folder · click to fetch what is new")
            name = folder.rsplit("/", 1)[-1]
            rows.append(Row(name + (" · " + n_new(len(fresh)) if fresh else ""), line, lambda folder=folder: self.fetch_new(folder), lines=1,
                            menu=lambda folder=folder: [
                                (_("issues on this computer"), lambda: self.push((ISSUES, "folder", folder))),
                                (_("the whole folder on the drive"), lambda: self.push((FOLDER, folder, bool(self.cfg.get("library_top_folders")) and "/" not in folder))),
                                (_("stop following this folder"), lambda: self.unfollow(folder))]))
        return rows

    def follow(self, folder):
        self.following.follow(folder, self.remote.index["books"])
        self.show_screen()

    def unfollow(self, folder):
        self.following.unfollow(folder)
        self.show_screen()

    def fetch_new(self, folder):
        """One click: the folder listed again, then its new books fetched, oldest first, on a
        thread; the row says how far it is. A failure part way keeps those already fetched."""
        if folder in self.follow_progress:
            return
        cfg = dict(self.cfg)
        self.follow_progress[folder], self.follow_errors[folder] = (0, 0), ""
        self.follow_changed += 1
        self.show_screen()
        screen = self.screen

        def job():
            got, error = [], None
            try:
                self.remote.relist(cfg, folder)
                f = self.following.get(folder)
                if f is None:
                    return got, None
                on_shelf = {b.get("source") for b in self.library.books if b.get("source")}
                todo = list(reversed(fresh_books(self.remote.index["books"], f, on_shelf)))
                self.follow_progress[folder] = (0, len(todo))
                self.follow_changed += 1
                remote = remote_for(cfg)
                for book in todo:
                    tmp = os.path.join(DATA_DIR, "download.tmp")
                    remote.download(book, tmp)
                    got.append(self.library.add(tmp, book["name"], source=book["ref"], move=True, modified=book.get("modified", 0)))
                    self.following.seen(folder, book["ref"])
                    self.follow_progress[folder] = (len(got), len(todo))
                    self.follow_changed += 1
                self.following.checked(folder, self.remote.index["books"])
            except Exception as exc:
                error = exc
            return got, error

        def done(result, crash):
            got, error = result if result else ([], crash)
            self.follow_progress.pop(folder, None)
            self.follow_changed += 1
            if error is not None:
                self.follow_errors[folder] = (_("the drive refused the login") if isinstance(error, WrongLogin)
                                              else _("the book could not be fetched: %s", str(error)[:160] or type(error).__name__))
            if self.screen != screen or (error is not None and not got):
                return self.show_screen()
            if len(got) == 1:
                self.open_entry(got[0])
            else:
                self.push((ISSUES, "folder", folder))

        self.run(job, done)

    def screen_issues(self):
        """The issues on this computer of one magazine, or of one followed folder of the drive,
        the newest first. A click opens one (its contents the first time, else where it was left)."""
        kind, key = self.screen[1], self.screen[2]
        if kind == "magazine":
            issues = magazine_issues(self.library.books, key)
            title = magazine_name(issues[0]["title"]) if issues else ""
        else:
            refs = {b["ref"] for b in self.remote.index["books"] if folder_under(key, b["folder"])}
            issues = sorted((b for b in self.library.books if b.get("source") in refs), key=lambda e: -issue_time(e))
            title = key.rsplit("/", 1)[-1]
        rows = [Row(n_issues(len(issues)) if issues else _("no issue of this folder is on this computer yet"), kind=HINT)]
        for e in issues:
            rows.append(Row(magazine_issue(e["title"]) if kind == "magazine" else e["title"], self.shelf_line(e),
                            lambda e=e: self.open_entry(e), lambda e=e: self.shelf_menu(e)))
        if kind == "folder":
            rows += [Row(kind=RULE), Row(_("the whole folder on the drive"), "", lambda: self.push((FOLDER, key, False)), lines=1)]
        return title, rows, None

    def screen_library_folders(self):
        """The folders of the drive that make the library: every folder seen to hold books, the
        chosen ones inverted along with what is inside them; a click chooses or un-chooses."""
        chosen, excluded = chosen_folders(self.cfg), excluded_folders(self.cfg)
        rows = [Row(_("The whole drive is in the library. Choose folders to keep only those, with everything inside them: the library is then synced faster. Right-click a folder to leave it out: it is then neither shown nor synced, whatever else is chosen. The transcriptions of Reader's Podcasts stay unless left out."), kind=HINT),
                Row(_("the whole drive"), "", lambda: self.set_library_folders([]) if chosen else None, inverted=not chosen)]
        for path, count in self.remote.known_folders():
            if not path:
                continue
            part = part_of(chosen, path)
            out = left_out(excluded, path)
            out_by = next((e for e in excluded if e != path and folder_under(e, path)), None)
            secondary = n_books(count) + (" · " + _("left out") + " · " + _("in %s", out_by) if out_by else " · " + _("left out") if out
                                          else " · " + _("in %s", part) if part else "")

            def choose(path=path, part=part, out=out):
                if out:
                    return
                if path in chosen:
                    self.set_library_folders([f for f in chosen if f != path])
                elif part is None:
                    self.set_library_folders(chosen + [path])

            def menu(path=path):
                if path in excluded:
                    return [(_("take this folder back in"), lambda: self.set_library_excluded([f for f in excluded if f != path]))]
                return [(_("leave this folder out"), lambda: self.set_library_excluded(excluded + [path]))]

            rows.append(Row(path, secondary, choose, menu=menu, lines=1, inverted=bool(chosen) and in_library(chosen, path, excluded)))
        return _("folders of the library"), rows, None

    # ---- a book of the shelf sent to the drive ----

    def screen_add_to_library(self):
        """Where in the library a book of the shelf goes: the folders of the drive that hold
        books (those of the library, when only some folders make it), the one used last time
        first. A click sends the book there; it then stands on the shelf as a book of the
        library, and the drive's listing says so at once."""
        entry = self.library.get(self.screen[1])
        if not entry:
            self.stack.pop()
            return self.screen_shelf()
        chosen = chosen_folders(self.cfg)
        last = self.cfg.get("send_folder")
        counts = dict(self.remote.known_folders())
        folders = sorted({f for f in list(counts) + chosen + [""] if in_library(chosen, f) and not folder_under(TRANSCRIPTS_FOLDER, f)},
                         key=lambda f: (f != last, f.lower()))
        rows = [Row(entry["title"], kind=SECTION)]
        if self.sent is not None:
            rows.append(Row(_("“%s” is now in the library, in %s.", entry["title"], self.sent or _("top of the drive")), kind=HINT))
        else:
            rows.append(Row(_("The book is copied to the drive, into the folder you choose, and becomes a book of the library: its highlights and the page you are at are then kept next to it and follow it to your other devices. Nothing on the drive is written over."), kind=HINT))
        if self.sending:
            rows.append(Row(_("sending…"), kind=HINT))
        if self.send_error:
            rows.append(Row(self.send_error, kind=HINT))
        if self.sent is None:
            for f in folders:
                secondary = " · ".join(x for x in (n_books(counts[f]) if f in counts else "", _("last time") if f == last else "") if x)
                rows.append(Row(f or _("top of the drive"), secondary, lambda f=f: self.send_book(entry["id"], f), lines=1))
        return _("add to the library"), rows, None

    def send_book(self, book_id, folder):
        entry = self.library.get(book_id)
        if not entry or self.sending or self.sent is not None:
            return
        self.sending, self.send_error = True, ""
        self.show_screen()
        cfg, screen = dict(self.cfg), self.screen

        def job():
            return self.remote.send(cfg, folder, send_name(entry), self.library.path(entry))

        def done(book, error):
            self.sending = False
            if error is not None:
                self.send_error = (_("the drive refused the login") if isinstance(error, WrongLogin)
                                   else _("the book could not be sent: %s", str(error)[:160]))
            else:
                self.library.link(book_id, book["ref"], book["name"])
                self.cfg["send_folder"] = folder
                save_config(self.cfg)
                self.sent = folder
                linked = self.library.get(book_id)
                if linked:
                    self.sync_highlights(linked)        # the page it is at goes next to it right away, for the other devices
            if self.screen == screen:
                self.show_screen()

        self.run(job, done)

    def opened_on_shelf(self):
        """When each book of the library was last opened here, by its reference on the drive."""
        return {b["source"]: max(b.get("opened", 0), b.get("added", 0)) for b in self.library.books if b.get("source")}

    def screen_folder(self):
        """The books of one folder, in the chosen order: the folder alone, or with the folders
        inside it (the menu; a top folder standing for a group always has them), each book then
        naming its folder."""
        path, group = self.screen[1], len(self.screen) > 2 and self.screen[2]
        order = self.cfg.get("library_sort", "NAME")
        subfolders = group or bool(self.cfg.get("library_subfolders"))
        has_subfolders = self.remote.has_subfolders(self.cfg, path)
        opened = self.opened_on_shelf()
        books = sort_books(self.remote.books(self.cfg, path, subfolders), order, opened)
        extra = []
        if not group and has_subfolders:
            extra = [None, (_("this folder only") if subfolders else _("with subfolders"), lambda: self.set("library_subfolders", not subfolders))]
        return self.book_list(path if group else (path.rsplit("/", 1)[-1] or _("top of the drive")), books, order, "library_sort",
                              heading=" · ".join(x for x in (order_name(order), _("with subfolders") if subfolders and has_subfolders else "") if x),
                              folder=subfolders, base=path, opened=opened if order == "OPENED" else None, extra=extra)

    def screen_all(self):
        order = self.cfg.get("all_books_sort", "NEWEST")
        opened = self.opened_on_shelf()
        books = sort_books(self.remote.shown(self.cfg), order, opened)
        return self.book_list(_("all books"), books, order, "all_books_sort", folder=True, opened=opened if order == "OPENED" else None)

    def screen_news(self):
        """The library's newspapers and magazines, whatever their folder: the newest issue first."""
        books = self.remote.news(self.cfg)
        title, rows, menu = self.book_list(_("news"), books, "NEWEST", None, folder=True, dated=self.remote.issue_date,
                                           heading=" · ".join((n_issues(len(books)), _("the newest first"))))
        return title, rows, [(_("search"), self.ask_search)]

    def screen_search(self):
        """The books of the library found by the words asked: every word must be in the name, the
        author or the folder, accents and case aside; in the order of « all books »."""
        query = self.screen[1]
        order = self.cfg.get("all_books_sort", "NEWEST")
        opened = self.opened_on_shelf()
        books = sort_books(search_books(self.remote.shown(self.cfg), query), order, opened)
        title, rows, menu = self.book_list(_("search"), books, order, "all_books_sort", folder=True, opened=opened if order == "OPENED" else None,
                                           heading=" · ".join((query, n_books(len(books)), order_name(order))), searching=True)
        if not books:
            rows.append(Row(_("no book matches"), kind=HINT))
        return title, rows, menu

    def ask_search(self):
        """The words to look for; the results replace a search already open."""
        dialog = QtWidgets.QInputDialog(self)
        dialog.setWindowTitle("Reader's Books")
        dialog.setLabelText(_("title, author or folder"))
        dialog.setOkButtonText(_("search"))
        dialog.setCancelButtonText(_("cancel"))
        dialog.setTextValue(self.screen[1] if self.screen[0] == SEARCH else "")
        for line in dialog.findChildren(QtWidgets.QLineEdit):
            line.setMinimumWidth(line.fontMetrics().averageCharWidth() * 40)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        self.search(dialog.textValue())

    def search(self, query):
        query = " ".join(query.split())
        if not query:
            return
        if self.screen[0] == SEARCH:
            self.stack[-1] = (SEARCH, query)
            self.show_screen(reset=True)
        else:
            self.push((SEARCH, query))

    def book_list(self, title, books, order, setting, heading=None, folder=False, base="", opened=None, extra=(), searching=False, dated=None):
        """The drive's books under a title, the order named above them and the orders offered
        under ⋯ (`extra` = what else the menu offers). A click fetches the book (once) and opens
        it. `folder` names each book's folder on its line, as seen from `base`."""
        rows = [Row(heading if heading is not None else order_name(order), kind=SECTION)]
        if self.fetch_error:
            rows.append(Row(self.fetch_error, kind=HINT))
        on_shelf = {b.get("source") for b in self.library.books if b.get("source")}
        for b in books:
            state = _("downloading…") if self.fetching == b["ref"] else _("on the shelf") if b["ref"] in on_shelf else ""
            seen = _("opened %s", when_label(opened[b["ref"]])) if opened and opened.get(b["ref"]) else ""
            where = (relative_folder(base, b["folder"]) or (_("top of the drive") if not base else "")) if folder else ""
            line = " · ".join(x for x in (state, seen, where, date_label((dated or (lambda b: b["modified"]))(b)), _ext(b["name"]), size_label(b["size"])) if x)
            rows.append(Row(remote_title(b), line, lambda b=b: self.fetch(b)))
        menu = self.order_menu(BOOK_ORDERS, order, setting) + list(extra)
        menu += [None, (_("search again"), self.ask_search)] if searching else [None, (_("search"), self.ask_search)]
        return title, rows, menu

    def fetch(self, book):
        entry = self.library.by_source(book["ref"])
        if entry:
            return self.open_entry(entry)
        if self.fetching:
            return
        self.fetching, self.fetch_error = book["ref"], ""
        self.show_screen()
        cfg = dict(self.cfg)
        screen = self.screen

        def job():
            remote = remote_for(cfg)
            if remote is None:
                raise IOError("no library")
            tmp = os.path.join(DATA_DIR, "download.tmp")
            remote.download(book, tmp)
            return self.library.add(tmp, book["name"], source=book["ref"], move=True, modified=book.get("modified", 0))

        def done(entry, error):
            self.fetching = None
            if error is not None:
                self.fetch_error = (_("the drive refused the login") if isinstance(error, WrongLogin)
                                    else _("the book could not be fetched: %s", str(error)[:160] or _("this file could not be read")))
                self.show_screen()
            elif self.screen == screen:
                self.open_entry(entry)
            else:
                self.show_screen()

        self.run(job, done)

    # ---- leaving ----

    def closeEvent(self, event):
        self.reader.remember()
        self.place_timer.stop()
        self.reader.close_book()
        self.awake.set(False)
        self.remote.cancel()
        g = self.geometry()
        self.cfg["geometry"] = [g.x(), g.y(), g.width(), g.height()]
        save_config(self.cfg)
        deadline = QtCore.QElapsedTimer()
        deadline.start()
        while self.threads and deadline.elapsed() < 2000:
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        for thread, _worker in list(self.threads):
            thread.quit()
            thread.wait(500)
        super().closeEvent(event)


def _after(values, current):
    return values[(values.index(current) + 1) % len(values)] if current in values else values[0]


def HIGHLIGHTS_HINT():
    return _("Highlights: in any book, drag across a passage to highlight it, with a comment if you like; a click on a highlight shows its comment. In a book from the library they are kept next to the book on the drive, with the page you are at, and follow it to your other devices; in a book opened from this computer they stay on this computer, and go to the library with the book if it is added to it. The book's menu exports them. With the WebDAV address of the Reader's Notes folder given below, a note per book lists its highlights in Reader's Notes.")


def LIBRARY_HINT():
    return _("Books kept on a drive, listed by folder; a book is downloaded only when you click it. Give the WebDAV address of the drive with a username and an application password (kDrive, Nextcloud, any WebDAV server). The drive is then scanned for epub, mobi, azw and fb2 files. Highlights and the page you are at are written next to each book, so the login must be allowed to write there.")


SANS_FAMILY = "sans-serif"   # "Roboto" once the bundled font is loaded (load_bundled_fonts)
SERIF_FAMILY = ""            # "Literata" once loaded: the reading face of the book text


def bundled_fonts_dir():
    """Where the fonts shipped with the app lie: next to the script (packaging/fonts in the
    source tree, fonts/ once installed) or inside a PyInstaller bundle."""
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(getattr(sys, "_MEIPASS", ""), "fonts"), os.path.join(here, "fonts"), os.path.join(here, "packaging", "fonts")):
        if d and os.path.isdir(d):
            return d
    return None


def load_bundled_fonts():
    """Roboto and Literata travel with the app, so that every computer draws the same text
    instead of whatever the system picks."""
    global SANS_FAMILY, SERIF_FAMILY
    d = bundled_fonts_dir()
    if not d:
        return 0
    n = 0
    for name in sorted(os.listdir(d)):
        if name.lower().endswith((".ttf", ".otf")):
            fid = QtGui.QFontDatabase.addApplicationFont(os.path.join(d, name))
            if fid >= 0:
                n += 1
                families = QtGui.QFontDatabase.applicationFontFamilies(fid)
                if families and families[0].startswith("Literata"):
                    SERIF_FAMILY = families[0]
                elif families and families[0].startswith("Roboto"):
                    SANS_FAMILY = "Roboto"
    return n


def credentials_cli(argv):
    """readers-books --export-credentials FILE / --import-credentials FILE, without a window."""
    for flag in ("--export-credentials", "--import-credentials"):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                print("%s needs a file" % flag, file=sys.stderr)
                return 2
            cfg = load_config()
            try:
                if flag == "--export-credentials":
                    export_credentials(cfg, argv[i + 1])
                else:
                    import_credentials(cfg, argv[i + 1])
                    save_config(cfg)
            except NotCredentials:
                print("not a Reader's credentials file", file=sys.stderr)
                return 1
            except NothingForUs:
                print("this file holds nothing for Reader's Books", file=sys.stderr)
                return 1
            except OSError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            return 0
    return None


def main():
    code = credentials_cli(sys.argv)
    if code is not None:
        sys.exit(code)
    # Sizes in the layout are pixels and text sizes are points: without this, a scaled screen
    # (125 %, 150 %, 200 %) grows the text and not the boxes around it.
    if hasattr(QtCore.Qt, "HighDpiScaleFactorRoundingPolicy"):
        QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    load_bundled_fonts()
    app.setApplicationName("Reader's Books")
    app.setDesktopFileName("readers-books")
    here = os.path.dirname(os.path.abspath(__file__))
    for icon in (os.path.join(getattr(sys, "_MEIPASS", here), "readers-books.png"), os.path.join(here, "readers-books.png"),
                 os.path.join(here, "packaging", "readers-books.png")):
        if os.path.exists(icon):
            app.setWindowIcon(QtGui.QIcon(icon))
            break
    window = Main()
    window.show()
    # Books given on the command line, so a file manager can hand them over ("open with").
    paths = [a for a in sys.argv[1:] if not a.startswith("-") and os.path.isfile(a)]
    if paths:
        window.import_files(paths)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
