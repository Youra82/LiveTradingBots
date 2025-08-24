# code/analysis/backtest.py

import os
import sys
import json
import pandas as pd
import numpy as np
import warnings
from datetime import timedelta

warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utilities.bitget_futures import BitgetFutures
from utilities.strategy_logic import calculate_envelope_indicators

def load_data(symbol, timeframe, start_date_str, end_date_str):
    cache_dir = os.path.join(os.path.dirname(__file__), '..', 'analysis', 'historical_data')
    os.makedirs(cache_dir, exist_ok=True)
    symbol_filename = symbol.replace('/', '-').replace(':', '-')
    cache_file = os.path.join(cache_dir, f"{symbol_filename}_{timeframe}.csv")
    if os.path.exists(cache_file):
        data = pd.read_csv(cache_file, index_col='timestamp', parse_dates=True)
        data.index = pd.to_datetime(data.index, utc=True)
        required_start = pd.to_datetime(start_date_str, utc=True)
        if data.index.min() <= required_start and data.index.max() >= pd.to_datetime(end_date_str, utc=True):
            return data.loc[start_date_str:end_date_str]
    try:
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        key_path = os.path.abspath(os.path.join(project_root, 'secret.json'))
        with open(key_path, "r") as f: secrets = json.load(f)
        api_setup = secrets.get('envelope', secrets.get('bitget_example'))
        bitget = BitgetFutures(api_setup)
        download_start = (pd.to_datetime(start_date_str) - timedelta(days=50)).strftime('%Y-%m-%d')
        download_end = (pd.to_datetime(end_date_str) + timedelta(days=1)).strftime('%Y-%m-%d')
        full_data = bitget.fetch_historical_ohlcv(symbol, timeframe, download_start, download_end)
        if full_data is not None and not full_data.empty:
            full_data.to_csv(cache_file)
            return full_data.loc[start_date_str:end_date_str]
        else: return pd.DataFrame()
    except Exception as e:
        print(f"Fehler beim Daten-Download für {timeframe}: {e}"); return pd.DataFrame()

def run_envelope_backtest(data, params):
    base_leverage = params.get('base_leverage', 10.0)
    target_atr_pct = params.get('target_atr_pct', 1.5)
    max_leverage = params.get('max_leverage', 50.0)
    
    balance_fraction = params.get('balance_fraction', 100) / 100
    stop_loss_pct = params.get('stop_loss_pct', 0.4) / 100
    envelopes = params.get('envelopes_pct', [])
    fee_pct = 0.05 / 100

    start_capital = params.get('start_capital', 1000)
    current_capital = start_capital
    trades_count, wins_count = 0, 0
    trade_log = []
    
    peak_capital = start_capital
    max_drawdown_pct = 0.0
    
    open_positions = []
    
    for i in range(1, len(data)):
        current_candle = data.iloc[i]
        
        if open_positions:
            avg_entry_price = np.mean([p['entry_price'] for p in open_positions])
            total_amount = sum([p['amount'] for p in open_positions])
            side = open_positions[0]['side']
            avg_leverage = np.mean([p['leverage'] for p in open_positions])

            sl_price = avg_entry_price * (1 - stop_loss_pct) if side == 'long' else avg_entry_price * (1 + stop_loss_pct)
            if (side == 'long' and current_candle['low'] <= sl_price) or (side == 'short' and current_candle['high'] >= sl_price):
                pnl = (sl_price - avg_entry_price) * total_amount if side == 'long' else (avg_entry_price - sl_price) * total_amount
                pnl -= (avg_entry_price * total_amount) * fee_pct
                current_capital += pnl
                trades_count += 1
                trade_log.append({
                    "timestamp": str(current_candle.name), "side": side, "entry": avg_entry_price, 
                    "exit": sl_price, "pnl": pnl, "balance": current_capital, "reason": "Stop-Loss", "leverage": avg_leverage
                })
                open_positions = []

            tp_price = current_candle['average']
            if not open_positions: pass
            elif (side == 'long' and current_candle['high'] >= tp_price) or (side == 'short' and current_candle['low'] <= tp_price):
                pnl = (tp_price - avg_entry_price) * total_amount if side == 'long' else (avg_entry_price - tp_price) * total_amount
                pnl -= (avg_entry_price * total_amount) * fee_pct
                current_capital += pnl
                trades_count += 1
                wins_count += 1
                trade_log.append({
                    "timestamp": str(current_candle.name), "side": side, "entry": avg_entry_price, 
                    "exit": tp_price, "pnl": pnl, "balance": current_capital, "reason": "Take-Profit", "leverage": avg_leverage
                })
                open_positions = []

            if not open_positions:
                if current_capital <= 0: current_capital = 0
                peak_capital = max(peak_capital, current_capital)
                drawdown = (peak_capital - current_capital) / peak_capital if peak_capital > 0 else 0
                max_drawdown_pct = max(max_drawdown_pct, drawdown)
                if current_capital == 0: break
                continue

        if not open_positions:
            current_atr_pct = current_candle['atr_pct']
            leverage = base_leverage
            if pd.notna(current_atr_pct) and current_atr_pct > 0:
                leverage = base_leverage * (target_atr_pct / current_atr_pct)
            
            leverage = int(round(max(1.0, min(leverage, max_leverage))))

            for j, e_pct in enumerate(envelopes):
                band_low = current_candle[f'band_low_{j+1}']
                if current_candle['low'] <= band_low:
                    amount = (current_capital * balance_fraction / len(envelopes)) * leverage / band_low
                    open_positions.append({'side': 'long', 'entry_price': band_low, 'amount': amount, 'leverage': leverage})

            for j, e_pct in enumerate(envelopes):
                band_high = current_candle[f'band_high_{j+1}']
                if current_candle['high'] >= band_high:
                    amount = (current_capital * balance_fraction / len(envelopes)) * leverage / band_high
                    open_positions.append({'side': 'short', 'entry_price': band_high, 'amount': amount, 'leverage': leverage})

    win_rate = (wins_count / trades_count * 100) if trades_count > 0 else 0
    final_pnl_pct = ((current_capital / start_capital) - 1) * 100
    
    return {
        "total_pnl_pct": final_pnl_pct, "trades_count": trades_count,
        "win_rate": win_rate, "params": params, "end_capital": current_capital,
        "max_drawdown_pct": max_drawdown_pct, "trade_log": trade_log
    }
