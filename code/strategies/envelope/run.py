# code/strategies/envelope/run.py

import os
import sys
import json
import logging
import pandas as pd
import traceback
import sqlite3
import time # <<< NEU für die Endlosschleife

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.append(os.path.join(PROJECT_ROOT, 'code'))

from utilities.bitget_futures import BitgetFutures
from utilities.strategy_logic import calculate_envelope_indicators
from utilities.telegram_handler import send_telegram_message

# ... (Logging-Setup bleibt gleich) ...
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'livetradingbot.log')
logging.basicConfig(level=logging.INFO, format='%(asctime)s UTC: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger('envelope_bot')


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        return json.load(f)

params = load_config()
SYMBOL = params['market']['symbol']
DB_FILE = os.path.join(os.path.dirname(__file__), f"bot_state_{SYMBOL.replace('/', '-')}.db")

def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_state (
            symbol TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            last_side TEXT,
            start_capital REAL,
            is_active INTEGER DEFAULT 1
        )
    ''')
    # <<< NEU: Startkapital und Aktiv-Status hinzugefügt >>>
    cursor.execute("INSERT OR IGNORE INTO bot_state (symbol, status, start_capital, is_active) VALUES (?, ?, ?, ?)",
                   (SYMBOL, 'ok_to_trade', -1, 1))
    conn.commit()
    conn.close()

def get_bot_status():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # <<< NEU: Alle Statusfelder abrufen >>>
    cursor.execute("SELECT status, last_side, start_capital, is_active FROM bot_state WHERE symbol = ?", (SYMBOL,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {"status": result[0], "last_side": result[1], "start_capital": result[2], "is_active": bool(result[3])}
    return {"status": "ok_to_trade", "last_side": None, "start_capital": -1, "is_active": True}

# <<< NEU: Mehrere Statusfelder gleichzeitig aktualisieren >>>
def update_bot_status(status: str = None, last_side: str = None, start_capital: float = None, is_active: bool = None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    current_status = get_bot_status()
    
    # Nur die Felder aktualisieren, die übergeben wurden
    status = status if status is not None else current_status['status']
    last_side = last_side if last_side is not None else current_status['last_side']
    start_capital = start_capital if start_capital is not None else current_status['start_capital']
    is_active_int = int(is_active) if is_active is not None else int(current_status['is_active'])

    cursor.execute("UPDATE bot_state SET status = ?, last_side = ?, start_capital = ?, is_active = ? WHERE symbol = ?",
                   (status, last_side, start_capital, is_active_int, SYMBOL))
    conn.commit()
    conn.close()

def main():
    logger.info(f">>> Starte Ausführung für {SYMBOL}")
    
    try:
        key_path = os.path.abspath(os.path.join(PROJECT_ROOT, 'secret.json'))
        with open(key_path, "r") as f: secrets = json.load(f)
        api_setup = secrets['envelope']
        telegram_config = secrets.get('telegram', {})
        bot_token = telegram_config.get('bot_token')
        chat_id = telegram_config.get('chat_id')
    except Exception as e:
        logger.critical(f"Fehler beim Laden der API-Schlüssel: {e}")
        return # Skript beenden, wenn Keys nicht geladen werden können

    bitget = BitgetFutures(api_setup)
    
    try:
        # <<< VERBESSERUNG 4 (Notschalter) >>>
        bot_state = get_bot_status()
        if not bot_state['is_active']:
            logger.warning("NOTSCHALTER AKTIV: Bot ist aufgrund von hohem Drawdown deaktiviert. Keine Aktionen werden ausgeführt.")
            return

        balance_info = bitget.fetch_balance()
        current_capital = balance_info['USDT']['total']
        
        if bot_state['start_capital'] < 0:
            update_bot_status(start_capital=current_capital)
            logger.info(f"Startkapital erstmalig auf {current_capital:.2f} USDT gesetzt.")
            bot_state['start_capital'] = current_capital

        drawdown_pct = ((bot_state['start_capital'] - current_capital) / bot_state['start_capital']) * 100
        global_dd_limit = params['risk'].get('global_drawdown_limit_pct', 999)

        if drawdown_pct >= global_dd_limit:
            update_bot_status(is_active=False)
            logger.critical(f"GLOBALER NOTSCHALTER AUSGELÖST! Drawdown von {drawdown_pct:.2f}% hat das Limit von {global_dd_limit}% erreicht.")
            message = f"🚨 NOTSCHALTER FÜR *{SYMBOL}* AKTIVIERT 🚨\n\n- Globaler Drawdown: {drawdown_pct:.2f}%\n- Limit: {global_dd_limit}%\n\nDer Bot wird keine neuen Trades mehr eröffnen."
            send_telegram_message(bot_token, chat_id, message)
            
            logger.info("Storniere alle offenen Limit-Orders aufgrund des Notschalters...")
            orders = bitget.fetch_open_orders(SYMBOL)
            for order in orders:
                bitget.cancel_order(order['id'], SYMBOL)
            return

        # ... (Rest der Logik von hier an)
        
        timeframe = params['market']['timeframe']
        
        logger.info("Storniere alte Limit-Orders...")
        orders = bitget.fetch_open_orders(SYMBOL)
        for order in orders:  
            bitget.cancel_order(order['id'], SYMBOL)

        logger.info("Storniere alte Trigger-Orders (TP/SL)...")
        trigger_orders = bitget.fetch_open_trigger_orders(SYMBOL)
        for order in trigger_orders:
            bitget.cancel_trigger_order(order['id'], SYMBOL)

        logger.info("Lade Marktdaten...")
        # <<< NEU: Daten für Trendfilter-Timeframe laden, falls abweichend >>>
        trend_filter_cfg = params['strategy'].get('trend_filter', {})
        main_data = bitget.fetch_recent_ohlcv(SYMBOL, timeframe, 500)
        
        if trend_filter_cfg.get('enabled'):
            tf_timeframe = trend_filter_cfg.get('timeframe', timeframe)
            if tf_timeframe != timeframe:
                tf_data = bitget.fetch_recent_ohlcv(SYMBOL, tf_timeframe, trend_filter_cfg.get('period', 200) + 50)
                tf_sma = ta.trend.sma_indicator(tf_data['close'], window=trend_filter_cfg.get('period', 200))
                # Resample trend sma to main timeframe
                main_data['trend_sma'] = tf_sma.reindex(main_data.index, method='ffill')
            else:
                 main_data = calculate_envelope_indicators(main_data, {**params['strategy'], **params['risk']})
        else:
             main_data = calculate_envelope_indicators(main_data, {**params['strategy'], **params['risk']})
       
        latest_complete_candle = main_data.iloc[-2]
        logger.info("Indikatoren berechnet.")

        tracker_info_before = get_bot_status()
        positions = bitget.fetch_open_positions(SYMBOL)
        open_position = positions[0] if positions else None
        
        # ... (Logik für Positionsschließung bleibt gleich)

        if open_position is None and tracker_info_before['status'] != "ok_to_trade":
            # ...
            update_bot_status(status="ok_to_trade") # Nur Status aktualisieren
            # ...

        tracker_info = get_bot_status()

        if open_position:
            # ...
            update_bot_status(status="in_trade", last_side=side)
            # ...

        elif tracker_info['status'] == "ok_to_trade":
            logger.info("Keine Position offen, prüfe auf neue Einstiege.")
            
            # ... (Hebelberechnung bleibt gleich)
            
            # <<< VERBESSERUNG 1 (Strategie): Trendfilter im Live-Handel anwenden >>>
            can_go_long = params['behavior'].get('use_longs', True)
            can_go_short = params['behavior'].get('use_shorts', True)

            if trend_filter_cfg.get('enabled') and 'trend_sma' in latest_complete_candle and pd.notna(latest_complete_candle['trend_sma']):
                if latest_complete_candle['close'] < latest_complete_candle['trend_sma']:
                    can_go_long = False
                    logger.info("Trendfilter: Longs deaktiviert (Preis unter SMA).")
                if latest_complete_candle['close'] > latest_complete_candle['trend_sma']:
                    can_go_short = False
                    logger.info("Trendfilter: Shorts deaktiviert (Preis über SMA).")
            
            # ...
            num_sides_active = (1 if can_go_long else 0) + (1 if can_go_short else 0)
            # ...

            if can_go_long:
                # ... (Long-Order-Platzierung)
            if can_go_short:
                # ... (Short-Order-Platzierung)

    except Exception as e:
        logger.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}", exc_info=True)
        error_message = f"🚨 KRITISCHER FEHLER im Bot für *{SYMBOL}*!\n\n`{traceback.format_exc()}`"
        if len(error_message) > 4000: error_message = error_message[:4000] + "..."
        send_telegram_message(bot_token, chat_id, error_message)

# <<< VERBESSERUNG 3 (Betrieb): PM2-kompatible Endlosschleife >>>
if __name__ == "__main__":
    setup_database() # Datenbank einmalig beim Start initialisieren
    while True:
        try:
            main()
            logger.info("<<< Ausführung abgeschlossen")
        except Exception as e:
            logger.critical(f"KRITISCHER FEHLER in der Hauptschleife: {e}", exc_info=True)
        
        # Warte 60 Sekunden bis zur nächsten Ausführung
        sleep_duration = 60
        logger.info(f"Warte {sleep_duration} Sekunden bis zum nächsten Durchlauf...\n")
        time.sleep(sleep_duration)
