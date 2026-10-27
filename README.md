# Rundlauf (Android-App)

Dieses Projekt baut aus der Rundlauf-Webseite eine Android-App mit Hintergrund-GPS.
Gebaut wird automatisch bei GitHub (Actions). Die APK landet unter "Releases".

Ablauf: Repository anlegen, alle Dateien hochladen, Action "APK bauen" starten, Rundlauf.apk installieren.
Wichtig: Der Ordner ".github/workflows" muss im Repository liegen. Falls er beim Hochladen fehlt,
lege die Datei dort von Hand an und kopiere den Inhalt aus "build-apk.yml".
