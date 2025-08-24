#!/bin/bash

# Pfad zum Skript dynamisch ermitteln
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
OPTIMIZER_SCRIPT="$SCRIPT_DIR/code/analysis/genetic_optimizer.py"
CACHE_DIR="$SCRIPT_DIR/code/analysis/historical_data"

# --- Farbcodes ---
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Funktion zum Starten des Optimizers ---
function run_optimizer() {
    echo "======================================================="
    echo "       LiveTradingBots - GENETIC ALGORITHM OPTIMIZER"
    echo "======================================================="

    # Virtuelle Umgebung aktivieren
    source "$SCRIPT_DIR/code/.venv/bin/activate"

    # Das Python-Skript ausführen
    python3 "$OPTIMIZER_SCRIPT"

    echo -e "\nGenetische Optimierung abgeschlossen."
}

# --- MODUS-AUSWAHL ---
case "$1" in
    clear-cache)
        read -p "Möchtest du den gesamten Daten-Cache wirklich löschen? [j/N]: " response
        if [[ "$response" =~ ^([jJ][aA]|[jJ])$ ]]; then
            rm -rf "$CACHE_DIR"
            mkdir -p "$CACHE_DIR" # Erstellt den leeren Ordner neu
            echo -e "${GREEN}✔ Cache wurde erfolgreich gelöscht.${NC}"
        else
            echo -e "${RED}Aktion abgebrochen.${NC}"
        fi
        exit 0
        ;;
    *) # Standardaktion, wenn kein oder ein unbekanntes Argument gegeben wird
        run_optimizer
        exit 0
        ;;
esac
