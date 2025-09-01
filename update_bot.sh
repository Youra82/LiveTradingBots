#!/bin/bash

SECRET_FILE="secret.json"
BACKUP_FILE="secret.json.bak"

echo "--- Sicheres Update wird ausgeführt ---"

# Schritt 1: Das Wichtigste zuerst - Backup der Keys erstellen
echo "1. Erstelle ein Backup von '$SECRET_FILE' nach '$BACKUP_FILE'..."
cp "$SECRET_FILE" "$BACKUP_FILE"

# Schritt 2: Alle lokalen Änderungen (inkl. deiner Keys) sicher "beiseite legen"
echo "2. Lege alle lokalen Änderungen mit 'git stash' sicher beiseite..."
git stash push --include-untracked

# Schritt 3: Den neuesten Stand von GitHub holen
echo "3. Hole die neuesten Updates von GitHub..."
git pull

# Schritt 4: Die "beiseite gelegten" Änderungen wieder zurückholen
# Dies holt deine Keys in secret.json zurück, falls sie gestashed wurden.
echo "4. Hole die lokalen Änderungen (deine Keys) aus dem Zwischenspeicher zurück..."
git stash pop

# Schritt 5: Absolute Sicherheit - Backup wiederherstellen
# Dieser Schritt stellt sicher, dass der Inhalt von secret.json exakt dem vor dem Update entspricht.
echo "5. Stelle zur absoluten Sicherheit den Inhalt von '$SECRET_FILE' aus dem Backup wieder her..."
cp "$BACKUP_FILE" "$SECRET_FILE"

echo "✅ Update abgeschlossen. Deine Keys in '$SECRET_FILE' sind sicher und unverändert."
