# code/analysis/backtest.py
# (load_data Funktion bleibt unverändert)
# ...

def run_envelope_backtest(data, params):
    # ... (Parameter-Initialisierung bleibt gleich) ...
    
    # <<< NEU: Trendfilter-Parameter holen >>>
    trend_filter_params = params.get('trend_filter', {})
    trend_filter_enabled = trend_filter_params.get('enabled', False)

    for i in range(1, len(data)):
        current_candle = data.iloc[i]
        previous_candle = data.iloc[i-1]
        
        if open_positions:
            # ... (Logik für offene Positionen bleibt unverändert) ...

        if not open_positions:
            # ... (Hebelberechnung bleibt unverändert) ...

            # <<< VERBESSERUNG 1 (Strategie): Logik für Trendfilter >>>
            can_go_long = True
            can_go_short = True
            if trend_filter_enabled and 'trend_sma' in current_candle and pd.notna(current_candle['trend_sma']):
                if current_candle['close'] < current_candle['trend_sma']:
                    can_go_long = False # Preis unter Trend-SMA -> keine Longs
                if current_candle['close'] > current_candle['trend_sma']:
                    can_go_short = False # Preis über Trend-SMA -> keine Shorts

            if can_go_long:
                for j, e_pct in enumerate(envelopes):
                    band_low = current_candle[f'band_low_{j+1}']
                    if current_candle['low'] <= band_low:
                        amount = (current_capital * balance_fraction / len(envelopes)) * leverage / band_low
                        open_positions.append({'side': 'long', 'entry_price': band_low, 'amount': amount, 'leverage': leverage})
                        break # Verhindert, dass mehrere Longs in einer Kerze öffnen

            if not open_positions and can_go_short:
                for j, e_pct in enumerate(envelopes):
                    band_high = current_candle[f'band_high_{j+1}']
                    if current_candle['high'] >= band_high:
                        amount = (current_capital * balance_fraction / len(envelopes)) * leverage / band_high
                        open_positions.append({'side': 'short', 'entry_price': band_high, 'amount': amount, 'leverage': leverage})
                        break # Verhindert, dass mehrere Shorts in einer Kerze öffnen

    # ... (Rest der Funktion bleibt unverändert) ...
    win_rate = (wins_count / trades_count * 100) if trades_count > 0 else 0
    final_pnl_pct = ((current_capital / start_capital) - 1) * 100
    
    return {
        "total_pnl_pct": final_pnl_pct, "trades_count": trades_count,
        "win_rate": win_rate, "params": params, "end_capital": current_capital,
        "max_drawdown_pct": max_drawdown_pct, "trade_log": trade_log
    }

