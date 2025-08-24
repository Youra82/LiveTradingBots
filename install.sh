#!/bin/bash

echo "--- Starte die Einrichtung des Trading Bots ---"

# 1. Eigener Pfad finden
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
CODE_DIR="$SCRIPT_DIR/code"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

# 2. Server-Pakete aktualisieren und installieren
echo "Aktualisiere den Server..."
sudo apt-get update -y
echo "Installiere pip und venv..."
sudo apt-get install python3-pip python3-venv -y

# 3. Python Virtual Environment erstellen und Pakete installieren
echo "Installiere virtuelle Umgebung und Pakete..."
cd "$CODE_DIR"
if [ ! -d ".venv" ]; then
    echo "Erstelle Python Virtual Environment (.venv)..."
    python3 -m venv .venv
fi

echo "Aktiviere Umgebung und installiere Anforderungen..."
source .venv/bin/activate
pip install -r "$REQUIREMENTS_FILE"
deactivate

echo -e "\n\n✔ --- Einrichtung erfolgreich abgeschlossen! ---"
