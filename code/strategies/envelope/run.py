# code/strategies/envelope/run.py

import os
import sys
import json
import logging
import pandas as pd
import traceback
import sqlite3

# Passe den Pfad an, um die Utilities zu finden
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.append(os.path.join(PROJECT_ROOT, 'code'))

from utilities.bitget_futures import BitgetFutures
from utilities.strategy_logic import calculate_envelope_indicators
from utilities.telegram_handler import send_telegram_message

# --- Logging einrichten ---
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'livetradingbot.log')
logging.basicConfig(level=logging.INFO, format='%(asctime)s UTC: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger('envelope_bot')

# --- Konfiguration laden ---
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        return json.load(f)

params = load_config()
SYMBOL = params['market']['symbol']

# --- SQLite Datenbank-Setup ---
DB_FILE = os.path.join(os.path.dirname(__file__), f"bot_state_{SYMBOL.replace('/', '-')}.db")

def setup_database():
    """Erstellt die Datenbank und die Tabelle, falls sie nicht existieren."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_state (
            symbol TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            last_side TEXT
        )
    ''')
    # Füge einen Standardeintrag für das Symbol hinzu, falls noch keiner existiert
    cursor.execute("INSERT OR IGNORE INTO bot_state (symbol, status, last_side) VALUES (?, ?, ?)",
                   (SYMBOL, 'ok_to_trade', None))
    conn.commit()
    conn.close()

def get_bot_status():
    """Liest den aktuellen Status des Bots aus der SQLite-Datenbank."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status, last_side FROM bot_state WHERE symbol = ?", (SYMBOL,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {"status": result[0], "last_side": result[1]}
    return {"status": "ok_to_trade", "last_side": None} # Fallback

def update_bot_status(status: str, last_side: str = None):
    """Aktualisiert den Status des Bots in der SQLite-Datenbank."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE bot_state SET status = ?, last_side = ? WHERE symbol = ?",
                   (status, last_side, SYMBOL))
    conn.commit()
    conn.close()

# --- Hauptlogik ---
def main():
    logger.info(f">>> Starte Ausführung für {SYMBOL}")
    
    # --- Authentifizierung & Initialisierung ---
    try:
        key_path = os.path.abspath(os.path.join(PROJECT_ROOT, 'secret.json'))
        with open(key_path, "r") as f:
            secrets = json.load(f)
        api_setup = secrets['envelope']
        telegram_config = secrets.get('telegram', {})
        bot_token = telegram_config.get('bot_token')
        chat_id = telegram_config.get('chat_id')
    except Exception as e:
        logger.critical(f"Fehler beim Laden der API-Schlüssel: {e}")
        sys.exit(1)

    bitget = BitgetFutures(api_setup)
    setup_database() # Stellt sicher, dass die DB bereit ist
    
    send_telegram_message(bot_token, chat_id, f"🤖 Bot für *{SYMBOL}* gestartet.")
    
    try:
        timeframe = params['market']['timeframe']
        
        # --- BEREINIGUNG & DATENLADEN ---
        # KORREKTUR: Jetzt werden BEIDE Ordertypen (Limit und Trigger) storniert.
        logger.info("Storniere alte Limit-Orders...")
        orders = bitget.fetch_open_orders(SYMBOL)
        for order in orders:  
            bitget.cancel_order(order['id'], SYMBOL)

        logger.info("Storniere alte Trigger-Orders (TP/SL)...")
        trigger_orders = bitget.fetch_open_trigger_orders(SYMBOL)
        for order in trigger_orders:
            bitget.cancel_trigger_order(order['id'], SYMBOL)
        # ENDE DER KORREKTUR

        logger.info("Lade Marktdaten...")
        data = bitget.fetch_recent_ohlcv(SYMBOL, timeframe, 200)
        data = calculate_envelope_indicators(data, {**params['strategy'], **params['risk']})
        latest_complete_candle = data.iloc[-2]
        logger.info("Indikatoren berechnet.")

        # --- POSITIONS- & STATUS-CHECKS ---
        tracker_info_before = get_bot_status()
        positions = bitget.fetch_open_positions(SYMBOL)
        open_position = positions[0] if positions else None

        if open_position is None and tracker_info_before['status'] == 'in_trade':
            side = tracker_info_before.get('last_side', 'Unbekannt')
            message = f"✅ Position für *{SYMBOL}* ({side}) wurde geschlossen."
            send_telegram_message(bot_token, chat_id, message)
            logger.info(message)
            # Status wird erst zurückgesetzt, wenn der Preis zum Mittelwert zurückkehrt

        if open_position is None and tracker_info_before['status'] != "ok_to_trade":
            last_price = latest_complete_candle['close']
            resume_price = latest_complete_candle['average']
            if ('long' in str(tracker_info_before.get('last_side')) and last_price >= resume_price) or \
               ('short' in str(tracker_info_before.get('last_side')) and last_price <= resume_price):
                logger.info(f"Preis ist zum Mittelwert zurückgekehrt. Status wird auf 'ok_to_trade' zurückgesetzt.")
                update_bot_status("ok_to_trade", tracker_info_before.get('last_side'))
            else:
                logger.info(f"Status ist '{tracker_info_before['status']}'. Warte auf Rückkehr zum Mittelwert.")
                return

        tracker_info = get_bot_status()

        # --- TRADING LOGIK ---
        if open_position:
            logger.info(f"{open_position['side']} Position ist offen. Verwalte Take-Profit und Stop-Loss.")
            side = open_position['side']
            close_side = 'sell' if side == 'long' else 'buy'
            amount = float(open_position['contracts'])
            avg_entry = float(open_position['entryPrice'])
            
            # Bestehende TP/SL-Orders löschen, um sie neu zu setzen
            trigger_orders = bitget.fetch_open_trigger_orders(SYMBOL)
            for order in trigger_orders:
                bitget.cancel_trigger_order(order['id'], SYMBOL)
            
            sl_price = avg_entry * (1 - params['risk']['stop_loss_pct']/100) if side == 'long' else avg_entry * (1 + params['risk']['stop_loss_pct']/100)
            tp_price = latest_complete_candle['average']

            bitget.place_trigger_market_order(SYMBOL, close_side, amount, tp_price, reduce=True)
            bitget.place_trigger_market_order(SYMBOL, close_side, amount, sl_price, reduce=True)
            update_bot_status("in_trade", side)
            logger.info(f"TP-Order @{tp_price:.4f} und SL-Order @{sl_price:.4f} platziert/aktualisiert.")

        elif tracker_info['status'] == "ok_to_trade":
            logger.info("Keine Position offen, prüfe auf neue Einstiege.")
            
            # Dynamischen Hebel berechnen
            base_leverage = params['risk']['base_leverage']
            target_atr_pct = params['risk']['target_atr_pct']
            max_leverage = params['risk']['max_leverage']
            current_atr_pct = latest_complete_candle['atr_pct']
            
            leverage = base_leverage
            if pd.notna(current_atr_pct) and current_atr_pct > 0:
                leverage = base_leverage * (target_atr_pct / current_atr_pct)
            
            leverage = int(round(max(1.0, min(leverage, max_leverage))))
            
            logger.info(f"Aktueller ATR: {current_atr_pct:.2f}%. Ziel-ATR: {target_atr_pct}%. Berechneter Hebel: {leverage}x")

            bitget.set_margin_mode(SYMBOL, margin_mode=params['risk']['margin_mode'])
            bitget.set_leverage(SYMBOL, leverage=leverage)
            
            # --- KORRIGIERTE KAPITALBERECHNUNG ---
            free_balance = bitget.fetch_balance()['USDT']['free']
            capital_to_use = free_balance * (params['risk']['balance_fraction_pct'] / 100.0)
            
            num_grids = len(params['strategy']['envelopes_pct'])
            if num_grids == 0:
                logger.warning("Keine 'envelopes_pct' in der Konfiguration gefunden.")
                return
            
            # BUGFIX: Zähle, wie viele Seiten (Long/Short) aktiv sind, um das Kapital fair aufzuteilen.
            num_sides_active = (1 if params['behavior'].get('use_longs', False) else 0) + \
                               (1 if params['behavior'].get('use_shorts', False) else 0)
            
            if num_sides_active == 0:
                logger.warning("Sowohl 'use_longs' als auch 'use_shorts' sind deaktiviert. Es werden keine Orders platziert.")
                return

            capital_per_side = capital_to_use / num_sides_active
            notional_amount_per_order = (capital_per_side / num_grids) * leverage
            
            message = f"📈 Neue Grid-Orders für *{SYMBOL}* platziert.\n- Hebel: {leverage}x"
            send_telegram_message(bot_token, chat_id, message)
            
            if params['behavior'].get('use_longs', True):
                for i in range(num_grids):
                    entry_price = latest_complete_candle[f'band_low_{i + 1}']
                    amount = notional_amount_per_order / entry_price
                    bitget.place_limit_order(SYMBOL, 'buy', amount, entry_price)
                    logger.info(f"Platziere Long-Grid {i+1}: Entry @{entry_price:.4f}")

            if params['behavior'].get('use_shorts', True):
                for i in range(num_grids):
                    entry_price = latest_complete_candle[f'band_high_{i + 1}']
                    amount = notional_amount_per_order / entry_price
                    bitget.place_limit_order(SYMBOL, 'sell', amount, entry_price)
                    logger.info(f"Platziere Short-Grid {i+1}: Entry @{entry_price:.4f}")

    except Exception as e:
        logger.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}", exc_info=True)
        error_message = f"🚨 KRITISCHER FEHLER im Bot für *{SYMBOL}*!\n\n`{traceback.format_exc()}`"
        if len(error_message) > 4000:
            error_message = error_message[:4000] + "..."
        send_telegram_message(bot_token, chat_id, error_message)

if __name__ == "__main__":
    main()
    logger.info("<<< Ausführung abgeschlossen\n")
