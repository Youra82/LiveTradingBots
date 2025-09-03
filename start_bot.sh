#!/bin/bash

# Definiere den Pfad zu deinem Projekt
PROJECT_DIR="/home/ubuntu/LiveTradingBots"

# Aktiviere die virtuelle Umgebung
source "$PROJECT_DIR/code/.venv/bin/activate"

# Wechsle in das Verzeichnis deines Skripts, um sicherzustellen,
# dass alle relativen Pfade (z.B. zur DB) korrekt funktionieren.
cd "$PROJECT_DIR/code/strategies/envelope"

# Führe das Python-Skript aus
python3 run.py
