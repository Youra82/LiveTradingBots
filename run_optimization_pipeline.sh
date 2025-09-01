#!/bin/bash

# Pfad zum Projektverzeichnis dynamisch ermitteln
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
VENV_PATH="$SCRIPT_DIR/code/.venv/bin/activate"
GLOBAL_OPTIMIZER="$SCRIPT_DIR/code/analysis/global_optimizer_pymoo.py"
LOCAL_REFINER="$SCRIPT_DIR/code/analysis/local_refiner_optuna.py"
CANDIDATES_FILE="$SCRIPT_DIR/code/analysis/optimization_candidates.json"
CACHE_DIR="$SCRIPT_DIR/code/analysis/historical_data"

# --- Farbcodes ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

function run_optimizer() {
    echo -e "${BLUE}======================================================="
    echo "       Automatisierte 2-Stufen-Optimierung"
    echo -e "=======================================================${NC}"

    read -p "Mit wie vielen CPU-Kernen soll optimiert werden? (Standard: 1): " N_CORES
    N_CORES=${N_CORES:-1}

    if [ -f "$VENV_PATH" ]; then
        source "$VENV_PATH"
    else
        echo "Fehler: Virtuelle Umgebung nicht gefunden. Bitte 'install.sh' ausführen."
        exit 1
    fi

    # Stufe 1: Globale Suche
    echo -e "${GREEN}>>> STARTE STUFE 1: Globale Suche mit Pymoo...${NC}"
    python3 "$GLOBAL_OPTIMIZER" --jobs "$N_CORES"

    if [ ! -f "$CANDIDATES_FILE" ]; then
        echo "Fehler: Stufe 1 hat keine Ergebnisse geliefert. Breche ab."
        deactivate
        exit 1
    fi

    # Stufe 2: Lokale Verfeinerung
    echo -e "\n${GREEN}>>> STARTE STUFE 2: Lokale Verfeinerung mit Optuna...${NC}"
    python3 "$LOCAL_REFINER" --jobs "$N_CORES"

    echo -e "\n${BLUE}Optimierungs-Pipeline erfolgreich abgeschlossen.${NC}"
    deactivate
}

# --- MODUS-AUSWAHL ---
case "$1" in
    clear-cache)
        read -p "Möchtest du den gesamten Daten-Cache wirklich löschen? [j/N]: " response
        if [[ "$response" =~ ^([jJ][aA]|[jJ])$ ]]; then
            rm -rfv "$CACHE_DIR"/*
            echo -e "${GREEN}✔ Cache wurde erfolgreich gelöscht.${NC}"
        else
            echo -e "${RED}Aktion abgebrochen.${NC}"
        fi
        exit 0
        ;;
    *) 
        run_optimizer
        exit 0
        ;;
esac
