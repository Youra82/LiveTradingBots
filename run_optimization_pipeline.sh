#!/bin/bash

# Pfad zum Projektverzeichnis dynamisch ermitteln
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
VENV_PATH="$SCRIPT_DIR/code/.venv/bin/activate"
GLOBAL_OPTIMIZER="$SCRIPT_DIR/code/analysis/global_optimizer_pymoo.py"
LOCAL_REFINER="$SCRIPT_DIR/code/analysis/local_refiner_optuna.py"
CANDIDATES_FILE="$SCRIPT_DIR/code/analysis/optimization_candidates.json"

# --- Farbcodes ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- Start ---
echo -e "${BLUE}======================================================="
echo "       Automatisierte 2-Stufen-Optimierung"
echo -e "=======================================================${NC}"

# Abfragen der CPU-Kerne
read -p "Mit wie vielen CPU-Kernen soll optimiert werden? (Standard: 1): " N_CORES
N_CORES=${N_CORES:-1} # Setzt den Standardwert auf 1, falls die Eingabe leer ist

echo "Verwende $N_CORES CPU-Kerne für die Optimierung."
echo ""

# Virtuelle Umgebung aktivieren
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
else
    echo "Fehler: Virtuelle Umgebung nicht unter '$VENV_PATH' gefunden."
    echo "Bitte führe zuerst 'install.sh' aus."
    exit 1
fi

# --- Stufe 1: Globale Suche ---
echo -e "${GREEN}>>> STARTE STUFE 1: Globale Suche mit Pymoo...${NC}"
python3 "$GLOBAL_OPTIMIZER" --jobs "$N_CORES" --gen 50

# Prüfen, ob Stufe 1 erfolgreich war
if [ ! -f "$CANDIDATES_FILE" ]; then
    echo "Fehler: Stufe 1 hat keine Ergebnisse geliefert. Breche ab."
    deactivate
    exit 1
fi

# --- Stufe 2: Lokale Verfeinerung ---
echo -e "\n${GREEN}>>> STARTE STUFE 2: Lokale Verfeinerung mit Optuna...${NC}"
python3 "$LOCAL_REFINER" --jobs "$N_CORES"

echo -e "\n${BLUE}Optimierungs-Pipeline erfolgreich abgeschlossen.${NC}"

# Virtuelle Umgebung deaktivieren
deactivate
