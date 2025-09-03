#!/bin/bash

# Bricht das Skript bei Fehlern sofort ab
set -e

echo "--- Starte die erweiterte Einrichtung des Trading Bots (inkl. PM2) ---"

# 1. Eigener Pfad finden, damit das Skript von überall funktioniert
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
CODE_DIR="$SCRIPT_DIR/code"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

echo "Projektverzeichnis ist: $SCRIPT_DIR"

# 2. Server-Pakete aktualisieren und installieren
echo "Aktualisiere den Server..."
sudo apt-get update -y > /dev/null
# <<< NEU: nodejs und npm für PM2 hinzugefügt >>>
echo "Installiere System-Abhängigkeiten (python, pip, venv, nodejs, npm)..."
sudo apt-get install python3-pip python3-venv nodejs npm -y > /dev/null

# 3. Python Virtual Environment erstellen und Pakete installieren
echo "Installiere virtuelle Umgebung und Python-Pakete..."
cd "$CODE_DIR"
if [ ! -d ".venv" ]; then
    echo "Erstelle Python Virtual Environment in '$CODE_DIR/.venv'..."
    python3 -m venv .venv
fi

echo "Aktiviere Umgebung und installiere Anforderungen aus requirements.txt..."
source .venv/bin/activate
pip install -r "$REQUIREMENTS_FILE" > /dev/null
deactivate
echo "Python-Umgebung ist bereit."

# <<< NEUER ABSCHNITT: PM2 installieren >>>
echo "Installiere den Prozess-Manager PM2 global..."
sudo npm install pm2 -g > /dev/null
echo "PM2 wurde erfolgreich installiert."

# --- Finale Anweisungen für den Benutzer ---
echo -e "\n------------------------------------------------------------------"
echo -e "✅ Installation erfolgreich abgeschlossen!"
echo -e "------------------------------------------------------------------"
echo -e "\nDein System ist jetzt vollständig vorbereitet."
echo -e "Führe jetzt bitte diese ZWEI EINMALIGEN Schritte manuell aus,"
echo -e "um den Autostart für deinen Bot nach Server-Neustarts zu aktivieren:\n"

echo -e "  Schritt 1: Generiere den Autostart-Befehl für dein System."
echo -e "  Führe dazu aus:"
echo -e "  \033[0;32mpm2 startup\033[0m\n"
echo -e "  -> PM2 wird dir einen Befehl ausgeben. KOPIERE diesen Befehl."

echo -e "  Schritt 2: Führe den kopierten Befehl aus, um den Dienst zu registrieren."
echo -e "  Er sieht in etwa so aus: sudo env PATH=...\n"

echo -e "Danach kannst du deinen Bot wie besprochen starten und speichern:"
echo -e "1. Bot starten: \033[0;32mpm2 start <pfad/zu/run.py> --name \"envelope-bot\" --interpreter python3\033[0m"
echo -e "2. Prozessliste für Neustarts speichern: \033[0;32mpm2 save\033[0m\n"
