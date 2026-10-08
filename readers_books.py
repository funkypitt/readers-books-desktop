#!/usr/bin/env python3
"""Reader's Books — a shelf as a plain list; books as pages of text cut at whole lines.

The desktop twin of the Android app: the same shelf, the same reader (EPUB, MOBI, FB2, TXT; the
place in each book kept), the same magazine contents, the same optional library on a drive (a
public kDrive share link or a WebDAV address), the same credentials file. One file, PyQt5.
"""
import json
import locale
import os
import re
import shutil
import struct
import sys
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urljoin, urlparse

import requests
from PyQt5 import QtCore, QtGui, QtWidgets

APP = "readers-books"
VERSION = "1.0.0"
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

# ------------------------------------------------------------------------------------------
# Six languages, the English text as the key — the same wording as the phone
# ------------------------------------------------------------------------------------------

STRINGS = {
 "fr": {
  "yesterday": "hier",
  "this file could not be read": "ce fichier n'a pas pu être lu",
  "+ open a book": "+ ouvrir un livre",
  "library": "bibliothèque",
  "black on white": "noir sur blanc",
  "white on black": "blanc sur noir",
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
  "kDrive share link": "lien de partage kDrive",
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
  "top of the drive": "racine du drive",
  "scanned on %s": "parcouru le %s",
  "stop the scan": "arrêter le parcours",
  "scan the drive again": "parcourir le drive à nouveau",
  "by name": "par nom",
  "newest first": "les plus récents d'abord",
  "oldest first": "les plus anciens d'abord",
  "by author": "par auteur",
  "last opened first": "les derniers ouverts d'abord",
  "downloading…": "téléchargement…",
  "on the shelf": "sur l'étagère",
  "opened %s": "ouvert %s",
  "the book could not be fetched: %s": "le livre n'a pas pu être récupéré : %s",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Paste the link of a public kDrive share, or give the WebDAV address of the drive with a username and an application password. The drive is then scanned for epub, mobi, azw and fb2 files.": "Des livres gardés sur un drive, listés par dossier ; un livre n'est téléchargé que lorsqu'on clique dessus. Collez le lien d'un partage kDrive public, ou donnez l'adresse WebDAV du drive avec un nom d'utilisateur et un mot de passe d'application. Le drive est alors parcouru à la recherche de fichiers epub, mobi, azw et fb2.",
 },
 "de": {
  "yesterday": "gestern",
  "this file could not be read": "diese Datei konnte nicht gelesen werden",
  "+ open a book": "+ ein Buch öffnen",
  "library": "Bibliothek",
  "black on white": "Schwarz auf Weiß",
  "white on black": "Weiß auf Schwarz",
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
  "kDrive share link": "kDrive-Freigabelink",
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
  "top of the drive": "Wurzel des Drives",
  "scanned on %s": "durchsucht am %s",
  "stop the scan": "Suche anhalten",
  "scan the drive again": "Drive erneut durchsuchen",
  "by name": "nach Name",
  "newest first": "neueste zuerst",
  "oldest first": "älteste zuerst",
  "by author": "nach Autor",
  "last opened first": "zuletzt geöffnete zuerst",
  "downloading…": "wird heruntergeladen…",
  "on the shelf": "im Regal",
  "opened %s": "geöffnet %s",
  "the book could not be fetched: %s": "das Buch konnte nicht geholt werden: %s",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Paste the link of a public kDrive share, or give the WebDAV address of the drive with a username and an application password. The drive is then scanned for epub, mobi, azw and fb2 files.": "Bücher auf einem Drive, nach Ordnern aufgelistet; ein Buch wird erst heruntergeladen, wenn Sie es anklicken. Fügen Sie den Link einer öffentlichen kDrive-Freigabe ein, oder geben Sie die WebDAV-Adresse des Drives mit Benutzername und Anwendungspasswort an. Das Drive wird dann nach epub-, mobi-, azw- und fb2-Dateien durchsucht.",
 },
 "es": {
  "yesterday": "ayer",
  "this file could not be read": "no se pudo leer este archivo",
  "+ open a book": "+ abrir un libro",
  "library": "biblioteca",
  "black on white": "negro sobre blanco",
  "white on black": "blanco sobre negro",
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
  "kDrive share link": "enlace compartido de kDrive",
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
  "top of the drive": "raíz del drive",
  "scanned on %s": "recorrido el %s",
  "stop the scan": "detener el recorrido",
  "scan the drive again": "recorrer el drive de nuevo",
  "by name": "por nombre",
  "newest first": "los más recientes primero",
  "oldest first": "los más antiguos primero",
  "by author": "por autor",
  "last opened first": "los últimos abiertos primero",
  "downloading…": "descargando…",
  "on the shelf": "en la estantería",
  "opened %s": "abierto %s",
  "the book could not be fetched: %s": "no se pudo obtener el libro: %s",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Paste the link of a public kDrive share, or give the WebDAV address of the drive with a username and an application password. The drive is then scanned for epub, mobi, azw and fb2 files.": "Libros guardados en un drive, listados por carpeta; un libro solo se descarga cuando haces clic en él. Pega el enlace de un recurso compartido público de kDrive, o indica la dirección WebDAV del drive con un nombre de usuario y una contraseña de aplicación. Entonces se recorre el drive buscando archivos epub, mobi, azw y fb2.",
 },
 "pt": {
  "yesterday": "ontem",
  "this file could not be read": "não foi possível ler este ficheiro",
  "+ open a book": "+ abrir um livro",
  "library": "biblioteca",
  "black on white": "preto sobre branco",
  "white on black": "branco sobre preto",
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
  "kDrive share link": "ligação de partilha kDrive",
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
  "top of the drive": "raiz da drive",
  "scanned on %s": "percorrida a %s",
  "stop the scan": "parar o percurso",
  "scan the drive again": "percorrer a drive de novo",
  "by name": "por nome",
  "newest first": "mais recentes primeiro",
  "oldest first": "mais antigos primeiro",
  "by author": "por autor",
  "last opened first": "os últimos abertos primeiro",
  "downloading…": "a descarregar…",
  "on the shelf": "na estante",
  "opened %s": "aberto %s",
  "the book could not be fetched: %s": "não foi possível obter o livro: %s",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Paste the link of a public kDrive share, or give the WebDAV address of the drive with a username and an application password. The drive is then scanned for epub, mobi, azw and fb2 files.": "Livros guardados numa drive, listados por pasta; um livro só é descarregado quando clica nele. Cole a ligação de uma partilha pública kDrive, ou indique o endereço WebDAV da drive com um nome de utilizador e uma palavra-passe de aplicação. A drive é então percorrida à procura de ficheiros epub, mobi, azw e fb2.",
 },
 "ru": {
  "yesterday": "вчера",
  "this file could not be read": "этот файл не удалось прочитать",
  "+ open a book": "+ открыть книгу",
  "library": "библиотека",
  "black on white": "чёрным по белому",
  "white on black": "белым по чёрному",
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
  "kDrive share link": "ссылка kDrive",
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
  "top of the drive": "корень диска",
  "scanned on %s": "просмотрено %s",
  "stop the scan": "остановить просмотр",
  "scan the drive again": "просмотреть диск заново",
  "by name": "по имени",
  "newest first": "сначала новые",
  "oldest first": "сначала старые",
  "by author": "по автору",
  "last opened first": "сначала недавно открытые",
  "downloading…": "загрузка…",
  "on the shelf": "на полке",
  "opened %s": "открыта %s",
  "the book could not be fetched: %s": "не удалось получить книгу: %s",
  "Books kept on a drive, listed by folder; a book is downloaded only when you click it. Paste the link of a public kDrive share, or give the WebDAV address of the drive with a username and an application password. The drive is then scanned for epub, mobi, azw and fb2 files.": "Книги на диске, перечисленные по папкам; книга загружается только когда вы щёлкаете по ней. Вставьте ссылку на публичную папку kDrive или укажите адрес WebDAV диска с именем пользователя и паролем приложения. Затем диск просматривается в поисках файлов epub, mobi, azw и fb2.",
 },
}

PLURALS = {
 "en": ("%d book", "%d books"), "fr": ("%d livre", "%d livres"), "de": ("%d Buch", "%d Bücher"),
 "es": ("%d libro", "%d libros"), "pt": ("%d livro", "%d livros"),
 "ru": ("%d книга", "%d книги", "%d книг"),
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


def n_books(n):
    """« 1 book », « 3 books » — with the three Russian forms."""
    forms = PLURALS.get(LANG) or PLURALS["en"]
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


class Para:
    __slots__ = ("text", "kind")

    def __init__(self, text, kind=NORMAL):
        self.text, self.kind = text, kind


class TextBlock:
    def __init__(self, paragraphs):
        self.paragraphs = paragraphs
        self.length = sum(u16(p.text) + 1 for p in paragraphs)


class ImageBlock:
    """A picture inside the book file; `source` is its entry in the EPUB."""
    length = 1

    def __init__(self, source):
        self.source = source


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
_SMALLPRINT = re.compile(r"\bcategory\b|\bauthor\b|\bbyline\b|caption|\bcredit\b|\bseparator\b")
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


def to_blocks(text, image):
    """Paragraphs with their kind, and the pictures between them. `image` maps an `src` to what
    the reader can load, or None to drop it. Kinds are marked with control characters before the
    tags are stripped."""
    s = _COMMENTS.sub("", text)
    s = _SVG_IMAGE.sub(lambda m: '<img src="%s"/>' % m.group(1), s)

    def picture(m):
        found = image(m.group(1))
        return "\n\n%s%s\n\n" % (IMG, found) if found else " "
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
    s = _BR.sub("\n", s)
    s = _PARA_BREAK.sub("\n\n", s)
    s = _ANY_TAG.sub("", s)
    s = decode_entities(s)
    s = _SPACES.sub(" ", s)
    blocks, paras = [], []
    for raw in _BLANK_LINE.split(s):
        para = "\n".join(line.strip() for line in raw.split("\n") if line.strip())
        if not para:
            continue
        if para.startswith(IMG):
            if paras:
                blocks.append(TextBlock(paras))
                paras = []
            blocks.append(ImageBlock(para[1:].split("\n")[0].strip()))
            continue
        kind, t = NORMAL, para
        while len(t) > 1 and t[0] == MARK:
            kind = {"H": HEADING, "L": LEAD, "S": SMALL}.get(t[1], kind)
            t = t[2:].lstrip()
        t = _MARKS.sub("", t)
        if t in ("---", "♦"):       # the pipeline's separators
            continue
        if t:
            paras.append(Para(t, kind))
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

            blocks = to_blocks(text, image)
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
        blocks = to_blocks(section, lambda src: None)
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
                    t = p.text
                    while len(t) > limit:
                        cut = t.rfind(" ", 0, limit + 1)
                        if cut < limit // 2:
                            cut = limit
                        state["part"].append(Para(t[:cut], p.kind))
                        t = t[cut:].lstrip()
                        flush_part()
                    if t:
                        state["part"].append(Para(t, p.kind))
                        state["size"] += u16(t)
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

    def save_position(self, book_id, chapter, char_offset, progress):
        with self.lock:
            e = self.get(book_id)
            if e:
                e.update(chapter=chapter, charOffset=char_offset, progress=progress, opened=_now())
                self._save()

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

    def add(self, source_path, display_name, source=None, move=False):
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
            os.replace(tmp, os.path.join(BOOKS_DIR, file_name))
            self.cache[file_name] = book
            same = next((b for b in self.books if b["title"] == book.title and b["format"] == fmt), None)
            entry = {"id": book_id, "fileName": file_name, "title": book.title, "format": fmt, "added": _now(),
                     "opened": same["opened"] if same else 0, "chapter": same["chapter"] if same else 0,
                     "charOffset": same["charOffset"] if same else 0, "progress": same["progress"] if same else 0,
                     "magazine": book.magazine is not None, "source": source or (same.get("source") if same else None)}
            if same:
                try:
                    os.remove(self.path(same))
                except OSError:
                    pass
                self.cache.pop(same["fileName"], None)
                self.books = [b for b in self.books if b["id"] != same["id"]]
            self.books.append(entry)
            self._save()
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
# The library on a drive: a WebDAV server or a public kDrive share link. A folder is named by an
# opaque reference, so a scan can be stopped and carried on later. Nothing is downloaded until a
# book is asked for.
# ------------------------------------------------------------------------------------------

BOOK_EXTENSIONS = ("epub", "mobi", "azw", "azw3", "fb2")     # no PDF; no TXT, a drive is full of them
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


_PROPFIND = ('<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/>'
             '<d:getcontentlength/><d:getlastmodified/></d:prop></d:propfind>')


class WebDav:
    def __init__(self, url, username, password):
        self.base = url.strip() if url.strip().endswith("/") else url.strip() + "/"
        self.session = requests.Session()
        self.session.auth = (username.encode("utf-8"), password.encode("utf-8"))
        self.session.headers["User-Agent"] = AGENT

    def roots(self):
        return [self.base]

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
        return {"name": name, "folder": "/".join(parts), "ref": href, "size": size, "modified": modified}

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
        for event, node in ET.iterparse(stream, events=("start", "end")):
            tag = node.tag.rsplit("}", 1)[-1]
            if event == "start":
                if tag == "response":
                    href, is_dir, size, modified = None, False, 0, 0
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
            elif tag == "response":
                if href:
                    full = urljoin(requested, href)
                    if full.rstrip("/") != requested.rstrip("/"):
                        out.append((full, is_dir, size, modified))
                node.clear()
        return out

    def download(self, book, dest, progress=None):
        with self.session.get(book["ref"], stream=True, timeout=(30, 90)) as r:
            _check(r)
            _save_stream(r, dest, progress)


class KDriveShare:
    """A public kDrive share link (https://kdrive.infomaniak.com/app/share/<drive>/<uuid>): no
    login. A folder reference is "<id>|<path>"."""
    BASE = "https://kdrive.infomaniak.com"

    def __init__(self, link):
        m = re.search(r"/app/share/(\d+)/([a-z0-9-]+)", link.strip())
        if not m:
            raise ValueError("not a kDrive share link")
        self.drive, self.uuid = m.group(1), m.group(2)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = AGENT

    def _get(self, url):
        r = self.session.get(url, timeout=(30, 90))
        _check(r)
        return r.json()

    def roots(self):
        data = self._get("%s/2/app/%s/share/%s/init" % (self.BASE, self.drive, self.uuid)).get("data") or {}
        if not data.get("file_id"):
            raise IOError("no file id")
        return ["%s|" % data["file_id"]]

    def list_all(self):
        return None

    def list(self, folder):
        fid, _sep, path = folder.partition("|")
        dirs, books, cursor = [], [], None
        while True:
            url = "%s/3/app/%s/share/%s/files/%s/files?limit=200" % (self.BASE, self.drive, self.uuid, fid)
            answer = self._get(url + ("&cursor=" + cursor if cursor else ""))
            for o in answer.get("data") or []:
                name, oid = o.get("name"), o.get("id")
                if not name or oid is None:
                    continue
                if o.get("type") == "dir":
                    if not skip_folder(name):
                        dirs.append("%s|%s" % (oid, name if not path else path + "/" + name))
                elif _ext(name) in BOOK_EXTENSIONS:
                    books.append({"name": name, "folder": path, "ref": str(oid), "size": int(o.get("size") or 0),
                                  "modified": int(o.get("last_modified_at") or 0) * 1000})
            cursor = answer.get("cursor") if answer.get("has_more") else None
            if not cursor:
                return dirs, books

    def download(self, book, dest, progress=None):
        url = "%s/2/app/%s/share/%s/files/%s/download" % (self.BASE, self.drive, self.uuid, book["ref"])
        with self.session.get(url, stream=True, timeout=(30, 90)) as r:
            _check(r)
            _save_stream(r, dest, progress)


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
    """A share link alone, or an address with a login: either reaches the library."""
    return bool(cfg.get("share", "").strip() or (cfg.get("url", "").strip() and cfg.get("username", "").strip() and cfg.get("password")))


def library_started(cfg):
    return bool(cfg.get("share") or cfg.get("url") or cfg.get("username") or cfg.get("password"))


def remote_for(cfg):
    """The share link wins over the address; None when nothing usable is set."""
    try:
        if cfg.get("share", "").strip():
            return KDriveShare(cfg["share"])
        if library_configured(cfg):
            return WebDav(cfg["url"], cfg["username"].strip(), cfg["password"])
    except Exception:
        pass
    return None


def source_key(cfg):
    if cfg.get("share", "").strip():
        return "share:" + cfg["share"].strip()
    return "dav:%s@%s" % (cfg.get("url", "").strip(), cfg.get("username", "").strip())


EMPTY_INDEX = {"scannedAt": 0, "source": "", "books": [], "complete": True, "frontier": [], "failed": [], "folders": 0}


class RemoteLibrary:
    """The drive's e-books as scanned so far, kept on disk so the library opens at once.

    `complete` = the whole tree was walked; otherwise `frontier` holds the folders still to
    list, so a scan that was stopped (window closed, network gone) carries on where it was.
    `failed` = folders the server would not list after three tries."""

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

    @property
    def scanning(self):
        return self.thread is not None and self.thread.is_alive()

    def matches(self, cfg):
        return self.index["source"] == source_key(cfg) and self.index["scannedAt"] > 0

    def folders(self):
        counts = {}
        for b in self.index["books"]:
            counts[b["folder"]] = counts.get(b["folder"], 0) + 1
        return sorted(counts.items(), key=lambda kv: kv[0].lower())

    def books(self, folder):
        return [b for b in self.index["books"] if b["folder"] == folder]

    def scan(self, cfg, fresh):
        """From scratch, or carrying on from the saved frontier and the folders that failed."""
        remote = remote_for(cfg)
        if self.scanning or remote is None:
            return
        fresh = fresh or not self.matches(cfg)
        start = dict(EMPTY_INDEX, source=source_key(cfg), complete=False) if fresh else dict(self.index)
        self.error = None
        self.stop = threading.Event()
        self.progress = (start["folders"], len(start["books"]), len(start["failed"]))
        self.thread = threading.Thread(target=self._run, args=(remote, start, fresh, self.stop), daemon=True)
        self.thread.start()

    def cancel(self):
        self.stop.set()
        self.progress = None
        self.changed += 1

    def forget(self):
        self.cancel()
        self.index = dict(EMPTY_INDEX)
        try:
            os.remove(INDEX_FILE)
        except OSError:
            pass

    def _save(self, index):
        self.index = index
        try:
            _write_private(INDEX_FILE, json.dumps(index, ensure_ascii=False))
        except OSError:
            pass
        self.changed += 1

    def _run(self, remote, start, fresh, stop):
        try:
            self._walk(remote, start, fresh, stop)
        except Exception as exc:
            if not stop.is_set():
                self.error = exc
        finally:
            if not stop.is_set():
                self.progress = None
            self.changed += 1

    def _walk(self, remote, index, fresh, stop):
        if fresh:
            everything = remote.list_all()
            if everything is not None:
                self._save(dict(index, books=everything, complete=True, frontier=[], failed=[],
                                folders=len({b["folder"] for b in everything}), scannedAt=_now()))
                return
            index = dict(index, frontier=remote.roots())
        # A pool of workers over one queue, so a slow folder holds nobody else back. Folders that
        # failed last time get another chance now.
        lock = threading.Lock()
        books = list(index["books"])
        queue = list(dict.fromkeys(index["frontier"] + index["failed"]))
        in_flight, failed = set(), []
        state = {"folders": index["folders"], "fatal": None, "dirty": False}

        def snapshot(complete):
            with lock:
                state["dirty"] = False
                return dict(index, books=list(books), frontier=[] if complete else queue + sorted(in_flight),
                            failed=list(failed), folders=state["folders"], scannedAt=_now(), complete=complete)

        def worker():
            while not stop.is_set():
                with lock:
                    if state["fatal"] or state["folders"] + len(in_flight) >= MAX_FOLDERS:
                        return
                    if queue:
                        folder = queue.pop(0)
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
                        queue.extend(result[0])
                        books.extend(result[1])
                        state["folders"] += 1
                    elif isinstance(error, WrongLogin):
                        # Back on the list: once the login is put right, the scan carries on
                        # from this very folder instead of finding nothing left to do.
                        state["fatal"] = error
                        queue.insert(0, folder)
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
        everything."""
        attempt = 0
        while True:
            try:
                return remote.list(folder), None
            except WrongLogin as exc:
                return None, exc
            except (IOError, requests.RequestException, ET.ParseError, ValueError) as exc:
                attempt += 1
                if attempt >= ATTEMPTS or stop.wait(RETRY_PAUSE * attempt * attempt):
                    return None, exc


# ------------------------------------------------------------------------------------------
# The Reader's credentials file, the same for every Reader's app: one JSON file, one section
# per app. Exporting merges our section into a file that may hold the others'. It holds the
# password.
# ------------------------------------------------------------------------------------------

CREDENTIALS_FORMAT = "readers-credentials"
CREDENTIALS_SECTION = "readers-books"
CREDENTIALS_FALLBACK = "magazine-reader"          # reaches the same kind of drive
SERVER_FALLBACKS = ("readers-scanner", "readers-notes", "readers-recorder")   # their "server", never their folder
CREDENTIAL_KEYS = ("share", "url", "username", "password")


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
    data[CREDENTIALS_SECTION] = {k: cfg[k] for k in CREDENTIAL_KEYS if cfg.get(k)}
    _write_private(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_credentials(text):
    """What a file brings for us: ({share, url, username, password} with None for what it does
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
            return {"share": None, "url": text_of(s, "server"), "username": text_of(s, "username"),
                    "password": text_of(s, "password")}, True
    raise NothingForUs()


def apply_credentials(cfg, account):
    """A file that names a share link replaces the whole account: a link and an address never
    both apply."""
    if account["share"] is not None:
        cfg.update(share=account["share"].strip(), url="", username="", password="")
    else:
        cfg.update(share="", url=(account["url"] if account["url"] is not None else cfg.get("url", "")).strip(),
                   username=(account["username"] if account["username"] is not None else cfg.get("username", "")).strip(),
                   password=account["password"] if account["password"] is not None else cfg.get("password", ""))


def import_credentials(cfg, path):
    with open(os.path.expanduser(path), encoding="utf-8") as fh:
        account, fallback = read_credentials(fh.read())
    apply_credentials(cfg, account)
    return fallback


# ------------------------------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------------------------------

DEFAULTS = {"dark": True, "font": "sans", "text_size": "M", "reader_pt": 0, "book_serif": False,
            "keep_awake": True, "share": "", "url": "", "username": "", "password": "",
            "library_sort": "NAME", "all_books_sort": "NEWEST"}
AUTO_READER_PT = 13
MIN_READER_PT, MAX_READER_PT = 8, 30


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except Exception:
        pass
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
INDENT = "  "


class Lines:
    """Lines first..last of one laid-out block, placed at y on the page."""
    def __init__(self, y, char_base, block, first, last):
        self.y, self.block, self.first, self.last = y, block, first, last
        self.start_char = char_base + block.layout.lineAt(first).textStart()


class Picture:
    def __init__(self, y, char_base, source, width, height):
        self.y, self.start_char, self.source, self.width, self.height = y, char_base, source, width, height


class LaidBlock:
    """One run of paragraphs as a single text layout, with the top and bottom of every line.

    One string for the whole run: the paragraphs are separated by line separators and indented
    with em spaces, headings, leads and small print are formats on that same string."""

    def __init__(self, block, font, dim, width):
        parts, formats, pos = [], [], 0
        for i, p in enumerate(block.paragraphs):
            if i:
                parts.append(LINE_BREAK)
                pos += 1
            indent = i > 0 and p.kind == NORMAL and block.paragraphs[i - 1].kind == NORMAL
            text = (INDENT if indent else "") + p.text.replace("\n", LINE_BREAK + (INDENT if indent else ""))
            length = u16(text)
            if p.kind != NORMAL:
                fmt = QtGui.QTextCharFormat()
                f = QtGui.QFont(font)
                if p.kind == HEADING:
                    f.setPixelSize(round(font.pixelSize() * 1.3))
                    f.setWeight(QtGui.QFont.Bold)
                elif p.kind == LEAD:
                    f.setWeight(QtGui.QFont.Bold)
                else:
                    f.setPixelSize(round(font.pixelSize() * 0.8))
                    fmt.setForeground(dim)
                fmt.setFont(f)
                r = QtGui.QTextLayout.FormatRange()
                r.start, r.length, r.format = pos, length, fmt
                formats.append(r)
            parts.append(text)
            pos += length
        self.layout = QtGui.QTextLayout("".join(parts), font)
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.layout.setTextOption(option)
        self.layout.setFormats(formats)
        # Lines sit 1.7 em apart whatever the face: 1.45 times the line of the interface fonts,
        # less for a face drawn with tall line boxes of its own (Literata).
        natural = QtGui.QFontMetricsF(font).height() / max(1, font.pixelSize())
        spacing = 1.7 / natural if natural > 1.3 else 1.45
        self.tops, self.bottoms = [], []
        y = 0
        self.layout.beginLayout()
        while True:
            line = self.layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            line.setPosition(QtCore.QPointF(0, y))
            self.tops.append(y)
            y += int(round(line.height() * spacing))
            self.bottoms.append(y)
        self.layout.endLayout()


def paginate(chapter, font, dim, width, page_height, images):
    pages, pieces = [], []
    state = {"y": 0}
    char_base = 0
    gap = int(font.pixelSize() * 0.8)

    def new_page():
        if pieces:
            pages.append(list(pieces))
            del pieces[:]
        state["y"] = 0

    for block in chapter.blocks:
        if isinstance(block, TextBlock):
            laid = LaidBlock(block, font, dim, width)
            if state["y"] > 0:
                state["y"] += gap
            line, count = 0, len(laid.tops)
            while line < count:
                top = laid.tops[line]
                last = line
                while last < count and laid.bottoms[last] - top <= page_height - state["y"]:
                    last += 1
                if last == line:
                    if state["y"] > 0:      # try again at the top of a fresh page
                        new_page()
                        continue
                    last += 1               # a single line taller than the page
                pieces.append(Lines(state["y"], char_base, laid, line, last - 1))
                state["y"] += laid.bottoms[last - 1] - top
                line = last
                if line < count:
                    new_page()
        else:
            size = images.size(block.source) if images else None
            if size and size[0] >= 48 and size[1] >= 48:
                w = width
                h = w * size[1] // size[0]
                if h > page_height:
                    h = page_height
                    w = h * size[0] // size[1]
                if state["y"] > 0:
                    state["y"] += gap
                if state["y"] + h > page_height:
                    new_page()
                pieces.append(Picture(state["y"], char_base, block.source, w, h))
                state["y"] += h
        char_base += block.length
    new_page()
    return pages or [[]]


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
THUMB = 64


class Row:
    def __init__(self, title="", secondary="", action=None, menu=None, kind=ROW, current=False, lines=2, thumb=None):
        self.title, self.secondary, self.action, self.menu = title, secondary, action, menu
        self.kind, self.current, self.lines, self.thumb = kind, current, lines, thumb


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


class RowDelegate(QtWidgets.QStyledItemDelegate):
    PAD_H, PAD_V = 24, 11

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.fg, self.bg = QtGui.QColor("#fff"), QtGui.QColor("#000")
        self.big, self.small = QtGui.QFont(), QtGui.QFont()

    def _row(self, index):
        i = index.data(QtCore.Qt.UserRole)
        return self.main.rows[i] if i is not None and i < len(self.main.rows) else Row(kind=RULE)

    def _width(self, row, total):
        return total - 2 * self.PAD_H - (THUMB + 16 if row.thumb else 0)

    def sizeHint(self, option, index):
        row = self._row(index)
        width = self.main.listing.viewport().width()
        fb, fs = QtGui.QFontMetrics(self.big), QtGui.QFontMetrics(self.small)
        if row.kind == RULE:
            return QtCore.QSize(width, 17)
        if row.kind == SECTION:
            return QtCore.QSize(width, fs.height() + 20)
        if row.kind == HINT:
            return QtCore.QSize(width, len(wrap(row.title, self.small, width - 2 * self.PAD_H, 12)) * fs.height() + 2 * self.PAD_V)
        height = len(wrap(row.title, self.big, self._width(row, width), row.lines)) * fb.height()
        if row.secondary:
            height += fs.height() + 2
        if row.thumb:
            height = max(height, THUMB)
        return QtCore.QSize(width, height + 2 * self.PAD_V)

    def paint(self, p, option, index):
        row = self._row(index)
        p.save()
        inverted = row.kind == ROW and (row.current or bool(option.state & QtWidgets.QStyle.State_Selected))
        fg, bg = (self.bg, self.fg) if inverted else (self.fg, self.bg)
        p.fillRect(option.rect, bg)
        dim = QtGui.QColor(fg)
        dim.setAlphaF(0.6 if inverted else 0.55)
        r = option.rect.adjusted(self.PAD_H, self.PAD_V, -self.PAD_H, -self.PAD_V)
        fb, fs = QtGui.QFontMetrics(self.big), QtGui.QFontMetrics(self.small)
        if row.kind == RULE:
            rule = QtGui.QColor(self.fg)
            rule.setAlphaF(0.25)
            p.fillRect(r.left(), option.rect.center().y(), r.width(), 1, rule)
        elif row.kind == SECTION:
            p.setFont(self.small)
            p.setPen(dim)
            p.drawText(QtCore.QRect(r.left(), r.bottom() - fs.height() + 6, r.width(), fs.height()),
                       QtCore.Qt.AlignLeft, fs.elidedText(row.title, QtCore.Qt.ElideRight, r.width()))
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
                pixmap = store.pixmap(source, int(THUMB * ratio), int(THUMB * ratio), crop=True)
                if pixmap:
                    p.drawPixmap(QtCore.QRect(r.right() - THUMB + 1, r.top() + (r.height() - THUMB) // 2, THUMB, THUMB), pixmap)
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
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

    # ---- which book ----

    def open(self, entry):
        self.entry, self.book, self.failed, self.pages, self.key = entry, None, False, None, None
        self.images = ImageStore(self.main.library.path(entry)) if entry["format"] == EPUB else None
        self.chapter, self.wanted, self.page = entry.get("chapter", 0), entry.get("charOffset", 0), 0
        book_id = entry["id"]

        def done(book, error):
            if not self.entry or self.entry["id"] != book_id:
                return
            self.book, self.failed = book, error is not None
            if book:
                self.chapter = min(max(0, self.chapter), len(book.chapters) - 1)
            self.update()

        self.main.run(lambda: self.main.library.book(entry), done)
        self.update()

    def close_book(self):
        self.entry = self.book = self.pages = self.key = None

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
        key = (self.entry["id"], self.chapter, area.width(), area.height(), font.family(), font.pixelSize(), self.main.dark)
        if key != self.key:
            dim = QtGui.QColor(self.main.colors["fg"])
            dim.setAlphaF(0.55)
            self.pages = paginate(self.book.chapters[self.chapter], font, dim, area.width(), area.height(), self.images)
            self.key = key
            self.page = min(page_for(self.pages, self.wanted), len(self.pages) - 1)
            self.wanted = page_start(self.pages[self.page])
            self.remember()
        return self.pages

    def progress(self):
        return int((self.book.chars_before(self.chapter) + page_start(self.pages[self.page])) * 100 / max(1, self.book.total))

    def remember(self):
        if self.book and self.pages:
            self.main.library.save_position(self.entry["id"], self.chapter, page_start(self.pages[self.page]), self.progress())

    # ---- turning ----

    def go_to(self, chapter, char_offset):
        self.chapter, self.wanted, self.key = chapter, char_offset, None
        self.update()

    def turn(self, forward):
        pages = self.layout_pages()
        if not pages:
            return
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
            self.turn(e.x() > self.width() / 2)

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
        p.drawText(QtCore.QRect(area.left(), 20, area.width() - 40, fs.height()), QtCore.Qt.AlignLeft,
                   fs.elidedText(self.book.title, QtCore.Qt.ElideRight, area.width() - 40))
        p.setFont(self.main.big_font())
        p.drawText(QtCore.QRect(area.right() - 39, 20, 40, fs.height()), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, "⋯")
        for piece in page:
            if isinstance(piece, Lines):
                p.setPen(fg)
                offset = QtCore.QPointF(area.left(), area.top() + piece.y - piece.block.tops[piece.first])
                for i in range(piece.first, piece.last + 1):
                    piece.block.layout.lineAt(i).draw(p, offset)
            else:
                ratio = self.devicePixelRatioF()
                pixmap = self.images.pixmap(piece.source, int(piece.width * ratio), int(piece.height * ratio)) if self.images else None
                if pixmap:
                    p.drawPixmap(QtCore.QRect(area.left() + (area.width() - piece.width) // 2, area.top() + piece.y,
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


# ------------------------------------------------------------------------------------------
# The window
# ------------------------------------------------------------------------------------------

SHELF, BOOK, CHAPTERS, SETTINGS, LIBRARY, FOLDER, ALL_BOOKS = "shelf", "book", "chapters", "settings", "library", "folder", "all"
UI_SIZES = {"S": 11, "M": 13, "L": 15}


class Main(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.dark = bool(self.cfg.get("dark", True))
        self.library = Library()
        self.remote = RemoteLibrary()
        self.awake = Awake()
        self.stack = [(SHELF,)]
        self.rows = []
        self.threads = []
        self.importing = False
        self.import_failed = False
        self.fetching = None            # the drive reference of the book being downloaded
        self.fetch_error = ""
        self.credentials_message = ""
        self.image_stores = {}
        self.seen_change = -1
        self.colors = {"bg": "#000000", "fg": "#ffffff"}
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
        self.show_screen()
        self.poll = QtCore.QTimer(self)
        self.poll.timeout.connect(self.watch_scan)
        self.poll.start(400)
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
        self.listing.itemClicked.connect(self.activate)
        self.listing.itemActivated.connect(self.activate)
        self.delegate = RowDelegate(self)
        self.listing.setItemDelegate(self.delegate)
        box.addWidget(self.listing, 1)

        self.foot_rule = self._rule()
        box.addWidget(self.foot_rule)
        self.foot_open = Clickable("", "foot")
        self.foot_open.clicked.connect(self.pick_book)
        self.foot_library = Clickable("", "foot")
        self.foot_library.clicked.connect(lambda: self.push((LIBRARY,)))
        box.addWidget(self.foot_open)
        box.addWidget(self.foot_library)
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
        bg, fg = ("#000000", "#ffffff") if self.dark else ("#ffffff", "#000000")
        dim = "rgba(255,255,255,0.55)" if self.dark else "rgba(0,0,0,0.55)"
        rule = "rgba(255,255,255,0.25)" if self.dark else "rgba(0,0,0,0.25)"
        s = UI_SIZES.get(self.cfg.get("text_size"), 13)
        weight = 300 if self.cfg.get("font", "sans") == "sans" else 400
        self.colors = {"bg": bg, "fg": fg}
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {bg}; color: {fg}; font-family: "{self.ui_family()}";
                                    font-size: {s}pt; font-weight: {weight}; }}
            QLabel#title {{ font-size: {s + 5}pt; }}
            QLabel#sign {{ font-size: {s + 7}pt; padding: 0 8px; }}
            QLabel#foot {{ font-size: {s + 2}pt; padding: 14px 24px; }}
            QFrame#sep {{ background: {rule}; }}
            QListWidget {{ background: {bg}; border: none; outline: none; }}
            QScrollBar:vertical {{ background: {bg}; width: 6px; }}
            QScrollBar:horizontal {{ background: {bg}; height: 0; }}
            QScrollBar::handle:vertical {{ background: {rule}; min-height: 24px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: {bg}; }}
            QMenu {{ background: {bg}; color: {fg}; border: 1px solid {rule}; padding: 6px 0; }}
            QMenu::item {{ padding: 8px 26px; }}
            QMenu::item:selected {{ background: {fg}; color: {bg}; }}
            QMenu::item:disabled {{ color: {dim}; }}
            QMenu::separator {{ height: 1px; background: {rule}; margin: 6px 0; }}
            QLineEdit {{ background: {bg}; color: {fg}; border: 1px solid {rule}; padding: 6px; }}
            QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {fg}; padding: 6px 18px; }}
            QPushButton:default {{ background: {fg}; color: {bg}; }}
            QToolTip {{ background: {bg}; color: {fg}; border: 1px solid {rule}; }}
        """)
        self.delegate.fg, self.delegate.bg = QtGui.QColor(fg), QtGui.QColor(bg)
        self.delegate.big, self.delegate.small = self.big_font(), self.small_font()
        self.listing.doItemsLayout()
        self.reader.key = None
        self.reader.update()

    def toggle_theme(self):
        self.dark = not self.dark
        self.set("dark", self.dark)

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
        self.stack.append(screen)
        self.show_screen(reset=True)

    def pop(self):
        if len(self.stack) > 1:
            self.fetch_error = ""
            self.stack.pop()
            self.show_screen(reset=True)

    def home(self):
        del self.stack[1:]

    def open_entry(self, entry, from_home=False):
        if from_home:
            self.home()
        self.push((CHAPTERS, entry["id"]) if entry.get("magazine") else (BOOK, entry["id"]))

    def show_screen(self, reset=False):
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
        self.foot_library.setVisible(shelf and library_configured(self.cfg))
        self.foot_library.setText(_("library"))
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
        if i is not None and i < len(self.rows) and self.rows[i].action:
            self.listing.clearSelection()
            self.listing.setCurrentItem(None)
            self.rows[i].action()

    def popup(self, items, where, title=None):
        """A menu of plain words. `items` are (label, action), None for a rule."""
        menu = QtWidgets.QMenu(self)
        if title:
            head = menu.addAction(QtGui.QFontMetrics(self.font()).elidedText(title, QtCore.Qt.ElideRight, 360))
            head.setEnabled(False)
            menu.addSeparator()
        for entry in items:
            if entry is None:
                menu.addSeparator()
            else:
                menu.addAction(entry[0], entry[1])
        menu.exec_(where)

    def page_menu(self):
        if self.menu_items:
            self.popup(self.menu_items, self.more.mapToGlobal(self.more.rect().bottomLeft()))

    def row_menu(self, point):
        item = self.listing.itemAt(point)
        i = item.data(QtCore.Qt.UserRole) if item else None
        if i is not None and i < len(self.rows) and self.rows[i].menu:
            self.popup(self.rows[i].menu(), self.listing.viewport().mapToGlobal(point), self.rows[i].title)

    def theme_item(self):
        return (_("black on white") if self.dark else _("white on black"), self.toggle_theme)

    # ---- the shelf ----

    def screen_shelf(self):
        rows = []
        if self.importing:
            rows.append(Row("…", kind=HINT))
        elif self.import_failed:
            rows.append(Row(_("this file could not be read"), kind=HINT))
        if not self.library.books and not self.importing:
            rows.append(Row(_("nothing on the shelf. Open an epub, mobi, fb2 or plain-text file: from here, or by dropping it on this window."), kind=HINT))
        for b in self.library.books:
            line = " · ".join(x for x in ("%d%%" % b.get("progress", 0) if b.get("opened") else _("not started"),
                                          when_label(b.get("opened", 0)), b["format"].lower()) if x)
            rows.append(Row(b["title"], line, lambda b=b: self.open_entry(b), lambda b=b: [
                (_("read"), lambda: self.push((BOOK, b["id"]))),
                (_("contents") if b.get("magazine") else _("chapters"), lambda: self.push((CHAPTERS, b["id"]))),
                (_("remove from the shelf"), lambda: self.remove(b["id"]))]))
        menu = [(_("+ open a book"), self.pick_book), (_("library"), lambda: self.push((LIBRARY,))), None,
                self.theme_item(), (_("settings"), lambda: self.push((SETTINGS,)))]
        return _("books"), rows, menu

    def remove(self, book_id):
        self.library.remove(book_id)
        if self.screen[0] in (BOOK, CHAPTERS):
            self.home()
        self.show_screen(reset=self.screen[0] != SHELF)

    def pick_book(self):
        path, _sel = QtWidgets.QFileDialog.getOpenFileName(
            self, _("+ open a book").lstrip("+ "), self.cfg.get("last_dir") or os.path.expanduser("~"),
            "%s (%s);;* (*)" % (_("books"), OPEN_FILTER))
        if path:
            self.cfg["last_dir"] = os.path.dirname(path)
            save_config(self.cfg)
            self.import_files([path])

    def import_files(self, paths):
        """Books opened from here, dropped on the window or handed over by the file manager: they
        land on the shelf, and the last one opens."""
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

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.import_files([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    # ---- the reader's menu, the chapters ----

    def turned(self):
        """The screen stays awake while a page is open, until fifteen minutes after the last turn."""
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
            self.home()
            self.push((CHAPTERS, book_id))

        self.popup([
            (_("contents"), contents) if entry.get("magazine") else (_("chapters"), lambda: self.push((CHAPTERS, book_id))),
            ("%s  ·  %d → %d" % (_("larger text"), size, min(MAX_READER_PT, size + 1)), lambda: self.set_reader_size(+1)),
            ("%s  ·  %d → %d" % (_("smaller text"), size, max(MIN_READER_PT, size - 1)), lambda: self.set_reader_size(-1)),
            ("%s  ·  %s → %s" % (_("book text"), _("serif") if serif else _("sans-serif"), _("sans-serif") if serif else _("serif")),
             lambda: self.set("book_serif", not serif)),
            (_("remove from the shelf"), lambda: self.remove(book_id)),
            None,
            (_("books"), self.pop),
            self.theme_item(),
        ], where, entry["title"])

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

        rows = []
        if book.magazine:
            store = self.images_of(entry)
            reading = [a for a in book.magazine if a.chapter <= entry.get("chapter", 0) and entry.get("opened")]
            current = reading[-1] if reading else None
            for i, a in enumerate(book.magazine):
                if a.category and (i == 0 or a.category != book.magazine[i - 1].category):
                    rows.append(Row(a.category.upper(), kind=SECTION))
                rows.append(Row(a.title, a.author or "", lambda a=a: go(a.chapter, True), current=a is current, lines=3,
                                thumb=(store, a.image) if a.image else None))
            return entry["title"], rows, None
        # The parts a long chapter was cut into are one line: the chapter.
        listed = [(i, ch) for i, ch in enumerate(book.chapters)
                  if i == 0 or not ch.title.startswith(book.chapters[i - 1].title.split(" · ")[0] + " · ")]
        before = [i for i, _ch in listed if i <= entry.get("chapter", 0)]
        current = before[-1] if before else None
        for i, ch in listed:
            rows.append(Row(ch.title, "", lambda i=i: go(i, False), current=i == current, lines=1))
        return entry["title"], rows, None

    # ---- settings ----

    def screen_settings(self):
        cfg = self.cfg
        size = reader_pt(cfg)
        fonts = ("sans", "serif", "mono")
        sizes = ("S", "M", "L")
        font_names = {"sans": _("sans-serif"), "serif": _("serif"), "mono": _("mono")}
        rows = [
            Row(_("white on black") if self.dark else _("black on white"), _("colours"), self.toggle_theme),
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
        rows += self.account_rows() + self.credentials_rows()
        if library_started(cfg):
            rows.append(Row(_("forget the library"), _("removes the link, the login and the list of books; the shelf is kept"), self.forget_library))
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
            Row(cfg.get("share") or _("kDrive share link"), _("kDrive share link"), lambda: self.ask("share")),
            Row(cfg.get("url") or _("WebDAV address"), _("WebDAV address"), lambda: self.ask("url")),
            Row(cfg.get("username") or _("username"), _("username"), lambda: self.ask("username")),
            Row("••••••••" if cfg.get("password") else _("password"), _("password"), lambda: self.ask("password")),
        ]

    def ask(self, field):
        labels = {"share": _("kDrive share link"), "url": _("WebDAV address"), "username": _("username"), "password": _("password")}
        dialog = QtWidgets.QInputDialog(self)
        dialog.setWindowTitle("Reader's Books")
        dialog.setLabelText(labels[field])
        dialog.setOkButtonText(_("ok"))
        dialog.setCancelButtonText(_("cancel"))
        dialog.setTextEchoMode(QtWidgets.QLineEdit.Password if field == "password" else QtWidgets.QLineEdit.Normal)
        dialog.setTextValue("" if field == "password" else self.cfg.get(field, ""))
        # An address is long: the field is as wide as fifty characters of the text it holds.
        for line in dialog.findChildren(QtWidgets.QLineEdit):
            line.setMinimumWidth(line.fontMetrics().averageCharWidth() * 50)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        value = dialog.textValue()
        self.cfg[field] = value if field == "password" else value.strip()
        save_config(self.cfg)
        self.account_changed()

    def account_changed(self):
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
        start = os.path.expanduser("~/readers-credentials.json")
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
        self.cfg.update(share="", url="", username="", password="")
        save_config(self.cfg)
        self.show_screen()

    # ---- the library ----

    def enter_library(self):
        """A drive just set up, or set up differently, is walked at once; a walk cut short
        carries on."""
        if not library_configured(self.cfg) or self.remote.scanning:
            return
        if not self.remote.matches(self.cfg):
            self.remote.scan(self.cfg, True)
        elif not self.remote.index["complete"] and self.remote.error is None:
            self.remote.scan(self.cfg, False)

    def watch_scan(self):
        if self.remote.changed != self.seen_change:
            self.seen_change = self.remote.changed
            if self.screen[0] in (LIBRARY, FOLDER, ALL_BOOKS):
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
        rows = []
        if progress:
            rows.append(Row(_("scanning… %d folders, %d books", progress[0], progress[1]), kind=HINT))
        if error is not None and not progress:
            rows.append(Row(_("the drive refused the login") if isinstance(error, WrongLogin)
                            else _("the drive could not be read: %s", str(error)[:160] or type(error).__name__), kind=HINT))
        unfinished = not progress and not index["complete"] and index["scannedAt"] > 0
        if unfinished:
            rows.append(Row(_("continue the scan"), _("the scan stopped after %d folders · %d books so far", index["folders"], len(index["books"])),
                            lambda: self.scan(False)))
        if not progress and index["complete"] and index["failed"]:
            rows.append(Row(_("continue the scan"), _("%d folders could not be read", len(index["failed"])), lambda: self.scan(False)))
        folders = remote.folders()
        if not folders and not progress and error is None and index["complete"] and index["scannedAt"] > 0:
            rows.append(Row(_("no e-book found on the drive (epub, mobi, azw, fb2)"), kind=HINT))
        if index["books"]:
            rows.append(Row(_("all books"), n_books(len(index["books"])), lambda: self.push((ALL_BOOKS,))))
        for path, count in folders:
            rows.append(Row(path or _("top of the drive"), n_books(count), lambda path=path: self.push((FOLDER, path)), lines=1))
        if index["scannedAt"] > 0 and not progress and index["complete"]:
            rows.append(Row(_("scanned on %s", date_label(index["scannedAt"])), kind=HINT))
        menu = []
        if not progress and (not index["complete"] or index["failed"]):
            menu.append((_("continue the scan"), lambda: self.scan(False)))
        menu.append((_("stop the scan"), self.stop_scan) if progress else (_("scan the drive again"), lambda: self.scan(True)))
        menu.append((_("settings"), lambda: self.push((SETTINGS,))))
        return _("library"), rows, menu

    def screen_folder(self):
        path = self.screen[1]
        order = self.cfg.get("library_sort", "NAME")
        books = self.remote.books(path)
        if order == "NEWEST":
            books.sort(key=lambda b: (-b["modified"], b["name"].lower()))
        elif order == "OLDEST":
            books.sort(key=lambda b: (b["modified"], b["name"].lower()))
        else:
            books.sort(key=lambda b: b["name"].lower())
        names = {"NAME": _("by name"), "NEWEST": _("newest first"), "OLDEST": _("oldest first")}
        return self.book_list(path.rsplit("/", 1)[-1] or _("top of the drive"), books, names, order, "library_sort")

    def screen_all(self):
        order = self.cfg.get("all_books_sort", "NEWEST")
        # When each book was last opened here, by its reference on the drive.
        opened = {b["source"]: max(b.get("opened", 0), b.get("added", 0)) for b in self.library.books if b.get("source")}
        books = list(self.remote.index["books"])
        if order == "NAME":
            books.sort(key=lambda b: b["name"].lower())
        elif order == "AUTHOR":     # books whose author is not known go last, by name
            books.sort(key=lambda b: (not remote_author(b), remote_author(b).lower(), remote_title(b).lower()))
        elif order == "OPENED":
            books.sort(key=lambda b: (-opened.get(b["ref"], 0), b["name"].lower()))
        else:
            books.sort(key=lambda b: (-b["modified"], b["name"].lower()))
        names = {"NEWEST": _("newest first"), "NAME": _("by name"), "AUTHOR": _("by author"), "OPENED": _("last opened first")}
        return self.book_list(_("all books"), books, names, order, "all_books_sort", folder=True,
                              opened=opened if order == "OPENED" else None)

    def book_list(self, title, books, names, order, setting, folder=False, opened=None):
        """The drive's books under a title, the order named above them and the orders offered
        under ⋯. A click fetches the book (once) and opens it."""
        rows = [Row(names.get(order, ""), kind=SECTION)]
        if self.fetch_error:
            rows.append(Row(self.fetch_error, kind=HINT))
        on_shelf = {b.get("source") for b in self.library.books if b.get("source")}
        for b in books:
            state = _("downloading…") if self.fetching == b["ref"] else _("on the shelf") if b["ref"] in on_shelf else ""
            seen = _("opened %s", when_label(opened[b["ref"]])) if opened and opened.get(b["ref"]) else ""
            where = (remote_folder_name(b) or _("top of the drive")) if folder else ""
            line = " · ".join(x for x in (state, seen, where, date_label(b["modified"]), _ext(b["name"]), size_label(b["size"])) if x)
            rows.append(Row(remote_title(b), line, lambda b=b: self.fetch(b)))
        menu = [(label + ("  ✓" if key == order else ""), lambda key=key: self.set(setting, key)) for key, label in names.items()]
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
            return self.library.add(tmp, book["name"], source=book["ref"], move=True)

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


def LIBRARY_HINT():
    return _("Books kept on a drive, listed by folder; a book is downloaded only when you click it. Paste the link of a public kDrive share, or give the WebDAV address of the drive with a username and an application password. The drive is then scanned for epub, mobi, azw and fb2 files.")


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
