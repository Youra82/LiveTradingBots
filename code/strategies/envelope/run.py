import os
import sys
import json
from datetime import datetime
import logging

# Passe den Pfad an, um die Utilities zu finden
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.append(os.path.join(PROJECT_ROOT, 'code'))

from utilities.bitget_futures import BitgetFutures
from utilities.strategy_logic import calculate_envelope_indicators

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

# --- Authentifizierung & Initialisierung ---
logger.info(f">>> Starte Ausführung für {params['symbol']}")
try:
    key_path = os.path.abspath(os.path.join(PROJECT_ROOT, 'secret.json'))
    with open(key_path, "r") as f:
        api_setup = json.load(f)['envelope']
except Exception as e:
    logger.critical(f"Fehler beim Laden der API-Schlüssel: {e}")
    sys.exit(1)

bitget = BitgetFutures(api_setup)
tracker_file = os.path.join(os.path.dirname(__file__), f"tracker_{params['symbol'].replace('/', '-')}.json")

# --- Tracker-Funktionen ---
if not os.path.exists(tracker_file):
    with open(tracker_file, 'w') as file:
        json.dump({"status": "ok_to_trade", "last_side": None, "stop_loss_ids": []}, file)

def read_tracker_file(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def update_tracker_file(file_path, data):
    with open(file_path, 'w') as file:
        json.dump(data, file)

def main():
    try:
        # --- BEREINIGUNG & DATENLADEN ---
        logger.info("Storniere alte Orders...")
        orders = bitget.fetch_open_orders(params['symbol'])
        for order in orders: bitget.cancel_order(order['id'], params['symbol'])
        
        trigger_orders = bitget.fetch_open_trigger_orders(params['symbol'])
        long_orders_left, short_orders_left = 0, 0
        for order in trigger_orders:
            if order['side'] == 'buy': long_orders_left += 1
            elif order['side'] == 'sell': short_orders_left += 1
            bitget.cancel_trigger_order(order['id'], params['symbol'])
        logger.info(f"Orders storniert. Verbleibende Trigger: {long_orders_left} Longs, {short_orders_left} Shorts")

        logger.info("Lade Marktdaten...")
        data = bitget.fetch_recent_ohlcv(params['symbol'], params['timeframe'], 100).iloc[:-1]
        data = calculate_envelope_indicators(data, params)
        logger.info("Indikatoren berechnet.")

        # --- POSITIONS- & STATUS-CHECKS ---
        tracker_info = read_tracker_file(tracker_file)
        positions = bitget.fetch_open_positions(params['symbol'])
        open_position = positions[0] if positions else None

        if open_position is None and tracker_info['status'] != "ok_to_trade":
            last_price = data['close'].iloc[-1]
            resume_price = data['average'].iloc[-1]
            if ('long' == tracker_info['last_side'] and last_price >= resume_price) or \
               ('short' == tracker_info['last_side'] and last_price <= resume_price):
                logger.info(f"Status wird auf 'ok_to_trade' zurückgesetzt.")
                update_tracker_file(tracker_file, {"status": "ok_to_trade", "last_side": tracker_info['last_side']})
                tracker_info['status'] = "ok_to_trade"
            else:
                logger.info(f"Status ist weiterhin '{tracker_info['status']}'. Warte auf Rückkehr zum Mittelwert.")
                return

        # --- TRADING LOGIK ---
        if open_position:
            logger.info(f"{open_position['side']} Position ist offen. Verwalte Take-Profit und Stop-Loss.")
            side = open_position['side']
            close_side = 'sell' if side == 'long' else 'buy'
            amount = open_position['contracts']
            avg_entry = float(open_position['entryPrice'])
            
            sl_price = avg_entry * (1 - params['stop_loss_pct']/100) if side == 'long' else avg_entry * (1 + params['stop_loss_pct']/100)
            tp_price = data['average'].iloc[-1]

            bitget.place_trigger_market_order(params['symbol'], close_side, amount, tp_price, reduce=True)
            sl_order = bitget.place_trigger_market_order(params['symbol'], close_side, amount, sl_price, reduce=True)
            update_tracker_file(tracker_file, {"status": "in_trade", "last_side": side, "stop_loss_ids": [sl_order['id']]})
            logger.info(f"TP-Order @{tp_price:.4f} und SL-Order @{sl_price:.4f} platziert/aktualisiert.")

        elif tracker_info['status'] == "ok_to_trade":
            logger.info("Keine Position offen, prüfe auf neue Einstiege.")
            bitget.set_margin_mode(params['symbol'], margin_mode=params['margin_mode'])
            bitget.set_leverage(params['symbol'], leverage=params['leverage'])
            
            balance = params['balance_fraction_pct']/100 * params['leverage'] * bitget.fetch_balance()['USDT']['total']
            amount_per_grid = balance / len(params['envelopes'])
            
            info_update = {"status": "ok_to_trade", "last_side": tracker_info['last_side'], "stop_loss_ids": []}

            # LONG ORDERS
            if params['use_longs']:
                for i, e_pct in enumerate(params['envelopes_pct']):
                    entry_price = data[f'band_low_{i + 1}'].iloc[-1]
                    amount = amount_per_grid / entry_price
                    sl_price = entry_price * (1 - params['stop_loss_pct']/100)
                    
                    bitget.place_limit_order(params['symbol'], 'buy', amount, entry_price)
                    sl_order = bitget.place_trigger_market_order(params['symbol'], 'sell', amount, sl_price, reduce=True)
                    info_update["stop_loss_ids"].append(sl_order['id'])
                    logger.info(f"Platziere Long-Grid {i+1}: Entry @{entry_price:.4f}, SL @{sl_price:.4f}")

            # SHORT ORDERS
            if params['use_shorts']:
                for i, e_pct in enumerate(params['envelopes_pct']):
                    entry_price = data[f'band_high_{i + 1}'].iloc[-1]
                    amount = amount_per_grid / entry_price
                    sl_price = entry_price * (1 + params['stop_loss_pct']/100)
                    
                    bitget.place_limit_order(params['symbol'], 'sell', amount, entry_price)
                    sl_order = bitget.place_trigger_market_order(params['symbol'], 'buy', amount, sl_price, reduce=True)
                    info_update["stop_loss_ids"].append(sl_order['id'])
                    logger.info(f"Platziere Short-Grid {i+1}: Entry @{entry_price:.4f}, SL @{sl_price:.4f}")
            
            update_tracker_file(tracker_file, info_update)

    except Exception as e:
        logger.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}", exc_info=True)

if __name__ == "__main__":
    main()
    logger.info("<<< Ausführung abgeschlossen\n")
