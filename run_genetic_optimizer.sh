#!/bin/bash

# Pfad zum Skript dynamisch ermitteln
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
OPTIMIZER_SCRIPT="$SCRIPT_DIR/code/analysis/genetic_optimizer.py"

echo "======================================================="
echo "       LiveTradingBots - GENETIC ALGORITHM OPTIMIZER"
echo "======================================================="

# Virtuelle Umgebung aktivieren
source "$SCRIPT_DIR/code/.venv/bin/activate"

# Das Python-Skript ausführen
python3 "$OPTIMIZER_SCRIPT"

echo -e "\nGenetische Optimierung abgeschlossen."
