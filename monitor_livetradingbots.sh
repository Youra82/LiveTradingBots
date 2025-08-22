#!/bin/bash

# --- Dynamische Pfadermittlung ---
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

# Pfade zu wichtigen Dateien und Verzeichnissen
OPTIMIZER_SCRIPT="$SCRIPT_DIR/code/analysis_livetradingbots/optimizer.py"
CACHE_DIR="$SCRIPT_DIR/code/analysis/historical_data" # Cache kann geteilt werden

# --- Farbcodes ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Funktion für den Optimizer ---
function run_optimizer() {
    echo -e "${CYAN}=======================================================${NC}"
    echo -e "${CYAN}        LiveTradingBots - ENVELOPE STRATEGY OPTIMIZER        ${NC}"
    echo -e "${CYAN}=======================================================${NC}"
    read -p "Startdatum (YYYY-MM-DD): " START_DATE
    read -p "Enddatum (YYYY-MM-DD): " END_DATE
    read -p "Handelspaar/paare (z.B. BTC ETH): " SYMBOL
    read -p "Startkapital in USDT (z.B. 1000): " START_CAPITAL
    read -p "Hebel für Simulation (z.B. 10): " LEVERAGE
    read -p "Anteil des Kapitals pro Trade in % (z.B. 100): " BALANCE_FRACTION
    read -p "Detail-Log anzeigen bis max. Trades (Enter für 30): " LOG_THRESHOLD
    
    if [ -z "$LOG_THRESHOLD" ]; then
        LOG_THRESHOLD=30
    fi

    if [ -z "$START_DATE" ] || [ -z "$END_DATE" ] || [ -z "$SYMBOL" ] || [ -z "$LEVERAGE" ] || [ -z "$START_CAPITAL" ] || [ -z "$BALANCE_FRACTION" ]; then
        echo -e "${RED}Fehler: Alle Felder müssen ausgefüllt werden.${NC}"; exit 1;
    fi

    source "$SCRIPT_DIR/code/.venv/bin/activate"

    python3 "$OPTIMIZER_SCRIPT" \
        --start "$START_DATE" \
        --end "$END_DATE" \
        --symbol "$SYMBOL" \
        --start_capital "$START_CAPITAL" \
        --leverage "$LEVERAGE" \
        --balance_fraction "$BALANCE_FRACTION" \
        --log_threshold "$LOG_THRESHOLD"

    echo -e "\n${GREEN}Optimierungslauf abgeschlossen.${NC}"
}

# --- MODUS-AUSWAHL ---
case "$1" in
    optimize)
        run_optimizer
        exit 0
        ;;
    clear-cache)
        read -p "Möchtest du den gesamten Daten-Cache löschen? [j/N]: " response
        if [[ "$response" =~ ^([jJ][aA]|[jJ])$ ]]; then
            rm -rf "$CACHE_DIR" && echo -e "${GREEN}✔ Cache wurde erfolgreich gelöscht.${NC}"
        else
            echo -e "${RED}Aktion abgebrochen.${NC}"
        fi
        exit 0
        ;;
esac

echo -e "${CYAN}=======================================================${NC}"
echo -e "${CYAN}           LiveTradingBots MONITORING (ENVELOPE)           ${NC}"
echo -e "${CYAN}=======================================================${NC}"
echo "Verwende './monitor_livetradingbots.sh <mode>', Modi: ${GREEN}optimize, clear-cache${NC}"
