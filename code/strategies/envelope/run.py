import os
import sys
import json
from datetime import datetime
import logging
import pandas as pd

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
logger.info(f">>> Starte Ausführung für {params['market']['symbol']}")
try:
    key_path = os.path.abspath(os.path.join(PROJECT_ROOT, 'secret.json'))
    with open(key_path, "r") as f:
        api_setup = json.load(f)['envelope']
except Exception as e:
    logger.critical(f"Fehler beim Laden der API-Schlüssel: {e}")
    sys.exit(1)

bitget = BitgetFutures(api_setup)
tracker_file = os.path.join(os.path.dirname(__file__), f"tracker_{params['market']['symbol'].replace('/', '-')}.json")

# --- Tracker-Funktionen ---
if not os.path.exists(tracker_file):
    with open(tracker_file, 'w') as file:
        json.dump({"status": "ok_to_trade", "last_side": None}, file)

def read_tracker_file(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def update_tracker_file(file_path, data):
    with open(file_path, 'w') as file:
        json.dump(data, file)

def main():
    try:
        symbol = params['market']['symbol']
        timeframe = params['market']['timeframe']
        
        # --- BEREINIGUNG & DATENLADEN ---
        logger.info("Storniere alte Limit-Orders...")
        orders = bitget.fetch_open_orders(symbol)
        for order in orders: 
            bitget.cancel_order(order['id'], symbol)

        logger.info("Lade Marktdaten...")
        data = bitget.fetch_recent_ohlcv(symbol, timeframe, 200)
        
        data = calculate_envelope_indicators(data, {**params['strategy'], **params['risk']})
        latest_complete_candle = data.iloc[-2]
        logger.info("Indikatoren berechnet.")

        # --- POSITIONS- & STATUS-CHECKS ---
        tracker_info = read_tracker_file(tracker_file)
        positions = bitget.fetch_open_positions(symbol)
        open_position = positions[0] if positions else None

        if open_position is None and tracker_info['status'] != "ok_to_trade":
            last_price = latest_complete_candle['close']
            resume_price = latest_complete_candle['average']
            if ('long' in tracker_info.get('last_side', '') and last_price >= resume_price) or \
               ('short' in tracker_info.get('last_side', '') and last_price <= resume_price):
                logger.info(f"Status wird auf 'ok_to_trade' zurückgesetzt.")
                update_tracker_file(tracker_file, {"status": "ok_to_trade", "last_side": tracker_info.get('last_side')})
                tracker_info['status'] = "ok_to_trade"
            else:
                logger.info(f"Status ist '{tracker_info['status']}'. Warte auf Rückkehr zum Mittelwert.")
                return

        # --- TRADING LOGIK ---
        if open_position:
            logger.info(f"{open_position['side']} Position ist offen. Verwalte Take-Profit und Stop-Loss.")
            side = open_position['side']
            close_side = 'sell' if side == 'long' else 'buy'
            amount = open_position['contracts']
            avg_entry = float(open_position['entryPrice'])
            
            trigger_orders = bitget.fetch_open_trigger_orders(symbol)
            for order in trigger_orders:
                bitget.cancel_trigger_order(order['id'], symbol)
            
            sl_price = avg_entry * (1 - params['risk']['stop_loss_pct']/100) if side == 'long' else avg_entry * (1 + params['risk']['stop_loss_pct']/100)
            tp_price = latest_complete_candle['average']

            bitget.place_trigger_market_order(symbol, close_side, amount, tp_price, reduce=True)
            bitget.place_trigger_market_order(symbol, close_side, amount, sl_price, reduce=True)
            update_tracker_file(tracker_file, {"status": "in_trade", "last_side": side})
            logger.info(f"TP-Order @{tp_price:.4f} und SL-Order @{sl_price:.4f} platziert/aktualisiert.")

        elif tracker_info['status'] == "ok_to_trade":
            logger.info("Keine Position offen, prüfe auf neue Einstiege.")
            
            base_leverage = params['risk']['base_leverage']
            target_atr_pct = params['risk']['target_atr_pct']
            max_leverage = params['risk']['max_leverage']
            current_atr_pct = latest_complete_candle['atr_pct']
            
            leverage = base_leverage
            if pd.notna(current_atr_pct) and current_atr_pct > 0:
                leverage = base_leverage * (target_atr_pct / current_atr_pct)
            
            leverage = int(round(max(1.0, min(leverage, max_leverage))))
            
            logger.info(f"Aktueller ATR: {current_atr_pct:.2f}%. Ziel-ATR: {target_atr_pct}%. Berechneter Hebel: {leverage}x")

            bitget.set_margin_mode(symbol, margin_mode=params['risk']['margin_mode'])
            bitget.set_leverage(symbol, leverage=leverage)
            
            balance = params['risk']['balance_fraction_pct']/100 * bitget.fetch_balance()['USDT']['total']
            amount_per_grid = (balance * leverage) / len(params['strategy']['envelopes_pct'])
            
            if params['behavior'].get('use_longs', True):
                for i, e_pct in enumerate(params['strategy']['envelopes_pct']):
                    entry_price = latest_complete_candle[f'band_low_{i + 1}']
                    amount = amount_per_grid / entry_price
                    bitget.place_limit_order(symbol, 'buy', amount, entry_price)
                    logger.info(f"Platziere Long-Grid {i+1}: Entry @{entry_price:.4f}")

            if params['behavior'].get('use_shorts', True):
                for i, e_pct in enumerate(params['strategy']['envelopes_pct']):
                    entry_price = latest_complete_candle[f'band_high_{i + 1}']
                    amount = amount_per_grid / entry_price
                    bitget.place_limit_order(symbol, 'sell', amount, entry_price)
                    logger.info(f"Platziere Short-Grid {i+1}: Entry @{entry_price:.4f}")

    except Exception as e:
        logger.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}", exc_info=True)

if __name__ == "__main__":
    main()
    logger.info("<<< Ausführung abgeschlossen\n")
