#!/bin/bash

# --- AUTOMATISCHE KORREKTUR (wird nur einmal ausgeführt, falls nötig) ---
# Prüft, ob secret.json fälschlicherweise noch von Git verfolgt wird
if git ls-files --error-unmatch secret.json > /dev/null 2>&1; then
    echo "Führe einmalige Korrektur durch: 'secret.json' wird aus der Git-Verfolgung entfernt."
    echo "Deine Datei und deine Keys bleiben dabei erhalten."
    git rm --cached secret.json
    git commit -m "Korrektur: secret.json wird nicht mehr verfolgt"
fi

# --- DEIN NORMALER UPDATE-PROZESS ---
echo "Setze lokale Codedateien auf den Stand von GitHub zurück..."
git reset --hard origin/main

echo "Hole die neuesten Updates und lösche veraltete Dateien..."
git pull

echo "✅ Bot ist jetzt auf dem neuesten Stand. Deine 'secret.json' wurde nicht verändert."
