import os
import sys
import json
import pandas as pd
import warnings
from itertools import product
import argparse
import time
import ast

warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from analysis.backtest import load_data, run_envelope_backtest
from utilities.strategy_logic import calculate_envelope_indicators

def get_user_params():
    params_to_test = {}
    print("\n--- Parameter für Envelope-Strategie konfigurieren ---")
    
    avg_periods = input("Werte für 'average_period' eingeben (z.B. '5 10 15'): ")
    params_to_test['average_period'] = [int(p) for p in avg_periods.split()]

    stop_losses = input("Werte für 'stop_loss_pct' in % eingeben (z.B. '0.4 0.6'): ")
    params_to_test['stop_loss_pct'] = [float(p) for p in stop_losses.split()]
    
    env_count_input = input("Anzahl der Envelopes/Grids pro Testlauf (z.B. '3 4'): ")
    env_counts = [int(c) for c in env_count_input.split()]

    env_starts_input = input("Start-Prozent der 1. Envelope (z.B. '5 7'): ")
    env_starts = [float(s) for s in env_starts_input.split()]
    
    env_steps_input = input("Schrittweite in % zwischen Envelopes (z.B. '2 4'): ")
    env_steps = [float(s) for s in env_steps_input.split()]

    # Erzeuge alle Envelope-Kombinationen
    envelope_combos = []
    for count in env_counts:
        for start in env_starts:
            for step in env_steps:
                envelope_combos.append([start + i * step for i in range(count)])
    params_to_test['envelopes_pct'] = envelope_combos

    return params_to_test

def run_optimization(start_date, end_date, symbols, start_capital, leverage, balance_fraction, log_threshold):
    grand_total_results = []
    
    param_grid = get_user_params()
    timeframe_input = input("Zu testende Timeframe(s) eingeben (z.B. 15m 1h 4h): ")
    timeframes_to_run = timeframe_input.split()
    
    for symbol_short in symbols:
        if '/' not in symbol_short:
            symbol = f"{symbol_short.upper()}/USDT:USDT"
            print(f"\nINFO: Symbol '{symbol_short}' wird als '{symbol}' verarbeitet.")
        else:
            symbol = symbol_short.upper()

        for timeframe in timeframes_to_run:
            print("\n" + "="*60)
            print(f"=== OPTIMIERE: {symbol} auf TIMEFRAME: {timeframe.upper()} ===")
            print("="*60)

            print("\nLade historische Daten...")
            data = load_data(symbol, timeframe, start_date, end_date)
            if data.empty:
                print(f"Nicht genügend Daten. Überspringe {symbol} auf {timeframe}.")
                continue

            keys, values = zip(*param_grid.items())
            param_combinations = [dict(zip(keys, v)) for v in product(*values)]
            total_runs = len(param_combinations)

            print(f"\nEs werden insgesamt {total_runs} Varianten simuliert.")
            confirm = input("Möchten Sie mit der Berechnung fortfahren? [j/N]: ")
            if confirm.lower() != 'j':
                print("Optimierung abgebrochen.")
                continue

            all_results_for_run = []
            for i, params_to_test in enumerate(param_combinations):
                print(f"\r  -> Simuliere Variante {i+1}/{total_runs}...", end="", flush=True)
                
                temp_data = data.copy()
                temp_data = calculate_envelope_indicators(temp_data, params_to_test)

                base_params = {'symbol': symbol, 'timeframe': timeframe, 'start_capital': start_capital, 'leverage': leverage, 'balance_fraction': balance_fraction}
                current_params = {**base_params, **params_to_test}
                
                result = run_envelope_backtest(temp_data.dropna(), current_params)
                all_results_for_run.append(result)
            print(" Fertig.")

            if not all_results_for_run: continue
            grand_total_results.extend(all_results_for_run)

    if not grand_total_results:
        print("\nKeine Ergebnisse für eine Gesamtauswertung vorhanden."); return

    print("\n" + "#"*70)
    print("##########      FINALE GESAMTAUSWERTUNG (TOP 10 ALLER LÄUFE)     ##########")
    print("#"*70)
    final_df = pd.DataFrame(grand_total_results)
    final_df['trade_log'] = final_df['trade_log'].apply(lambda x: json.dumps(x))
    params_df = pd.json_normalize(final_df['params'])
    final_df = pd.concat([final_df.drop('params', axis=1), params_df], axis=1)
    overall_best = final_df.sort_values(by='total_pnl_pct', ascending=False).head(10)

    for i, row in overall_best.reset_index(drop=True).iterrows():
        print("\n" + "="*40); print(f"            --- GLOBALER PLATZ {i+1} ---"); print("="*40)
        print(f"  HANDELSPAAR: {row['symbol']}"); print(f"  TIMEFRAME:   {row['timeframe']}")
        print("\n  LEISTUNG:")
        print(f"    Gewinn (PnL):       {row['total_pnl_pct']:.2f} % (Hebel: {row['leverage']:.0f}x)")
        print(f"    Endkapital:         {row['end_capital']:.2f} USDT")
        print(f"    Anzahl Trades:      {int(row['trades_count'])}")
        print(f"    Max. Drawdown:      {row.get('max_drawdown_pct', 0)*100:.2f}%")
        
        print("\n  BESTE PARAMETER:")
        print(f"    average_period      {row['average_period']}")
        print(f"    stop_loss_pct       {row['stop_loss_pct']}%")
        # Envelopes schön formatieren
        envelopes_nice = [round(e, 2) for e in row['envelopes_pct']]
        print(f"    envelopes_pct       {envelopes_nice}")
        
        if int(row['trades_count']) < log_threshold and 'trade_log' in row and not pd.isna(row['trade_log']):
            try:
                trade_log_list = json.loads(row['trade_log'])
                if trade_log_list:
                    print("\n  DETAILLIERTE HANDELS-CHRONIK (GERINGE ANZAHL):")
                    print("    Datum        | Seite  | Einstieg | Ausstieg | Gewinn (USDT) | Kontostand")
                    print("    -------------------------------------------------------------------------")
                    for trade in trade_log_list:
                        side_str = trade['side'].capitalize().ljust(5)
                        entry_str = f"{trade['entry']:.4f}".ljust(10)
                        exit_str = f"{trade['exit']:.4f}".ljust(10)
                        pnl_str = f"{trade['pnl']:+9.2f}".ljust(13)
                        balance_str = f"{trade['balance']:.2f} USDT"
                        print(f"    {trade['date']} | {side_str} | {entry_str} | {exit_str} | {pnl_str} | {balance_str}")
            except Exception:
                pass
    print("\n" + "="*40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimizer für die Envelope-Strategie.")
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--start_capital', type=float, default=1000.0)
    parser.add_argument('--leverage', type=float, default=10.0)
    parser.add_argument('--balance_fraction', type=float, default=100.0)
    parser.add_argument('--log_threshold', type=int, default=30)
    args = parser.parse_args()
    symbols_to_run = args.symbol.split()
    run_optimization(args.start, args.end, symbols_to_run, args.start_capital, args.leverage, args.balance_fraction, args.log_threshold)
