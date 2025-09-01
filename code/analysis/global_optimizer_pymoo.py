# code/analysis/global_optimizer_pymoo.py

import json
import numpy as np
import os
import sys
import argparse
from multiprocessing import Pool

from pymoo.core.problem import StarmapParallelization, Problem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination

# --- Pfade und Module laden ---
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from analysis.backtest import load_data, run_envelope_backtest
from utilities.strategy_logic import calculate_envelope_indicators

# --- Globale Variablen ---
HISTORICAL_DATA = None
START_CAPITAL = 1000.0
MAX_LOSS_PER_TRADE_PCT = 2.0
MINIMUM_TRADES = 10

# --- Problem-Definition für Pymoo ---
class EnvelopeOptimizationProblem(Problem):
    def __init__(self, **kwargs):
        # Parameter: avg_period, sl_pct, base_lev, target_atr, env_start, env_step, env_count
        super().__init__(n_var=7, n_obj=2, n_constr=0, xl=[5, 0.5, 1, 1.0, 2.0, 1.0, 1], xu=[89, 5.0, 50, 5.0, 10.0, 10.0, 4], **kwargs)

    def _evaluate(self, x, out, *args, **kwargs):
        results = []
        for individual in x:
            # --- Parameter aus dem Vektor extrahieren ---
            avg_period = int(round(individual[0]))
            sl_pct = round(individual[1], 2)
            base_lev = int(round(individual[2]))
            target_atr = round(individual[3], 2)
            env_start = round(individual[4], 2)
            env_step = round(individual[5], 2)
            env_count = int(round(individual[6]))

            envelopes = [round(env_start + i * env_step, 2) for i in range(env_count)]
            
            # --- Fitness-Funktion ---
            if any(e >= 100.0 for e in envelopes):
                results.append([-1003, 1003]) # Pymoo minimiert, daher -PnL
                continue

            params = {
                'average_period': avg_period, 'stop_loss_pct': sl_pct,
                'base_leverage': base_lev, 'max_leverage': 50.0,
                'target_atr_pct': target_atr,
                'envelopes_pct': envelopes,
                'start_capital': START_CAPITAL
            }
            
            data_with_indicators = calculate_envelope_indicators(HISTORICAL_DATA.copy(), params)
            result = run_envelope_backtest(data_with_indicators.dropna(), params)

            pnl = result.get('total_pnl_pct', -1000)
            drawdown = result.get('max_drawdown_pct', 1.0) * 100

            if pnl > 50000: pnl = -1002
            if result['trades_count'] < MINIMUM_TRADES: pnl = -1000
            
            if result["trade_log"]:
                for trade in result["trade_log"]:
                    loss_pct = abs(trade['pnl'] / START_CAPITAL * 100)
                    if trade['pnl'] < 0 and loss_pct > MAX_LOSS_PER_TRADE_PCT:
                        pnl = -1001
                        break
            
            # Pymoo minimiert Ziele, daher müssen wir den Gewinn negieren.
            results.append([-pnl, drawdown])
        
        out["F"] = np.array(results)

def main(n_procs, n_gen):
    print("\n--- [Stufe 1/2] Globale Suche mit Pymoo ---")
    symbol_input = input("Handelspaar(e) eingeben (z.B. BTC ETH): ")
    timeframe_input = input("Zeitfenster eingeben (z.B. 1h 4h): ")
    start_date = input("Startdatum eingeben (JJJJ-MM-TT): ")
    end_date = input("Enddatum eingeben (JJJJ-MM-TT): ")
    
    global START_CAPITAL, MAX_LOSS_PER_TRADE_PCT, MINIMUM_TRADES
    START_CAPITAL = float(input("Startkapital in USDT eingeben (z.B. 1000): "))
    MAX_LOSS_PER_TRADE_PCT = float(input("Maximaler Verlust pro Trade in % (z.B. 2.0): "))
    MINIMUM_TRADES = int(input("Mindestanzahl an Trades (z.B. 20): "))
    
    symbols_to_run = symbol_input.split()
    timeframes_to_run = timeframe_input.split()

    all_champions = []

    for symbol_short in symbols_to_run:
        for timeframe in timeframes_to_run:
            symbol = f"{symbol_short.upper()}/USDT:USDT"
            print(f"\n===== Optimiere {symbol} auf {timeframe} =====")
            
            global HISTORICAL_DATA
            HISTORICAL_DATA = load_data(symbol, timeframe, start_date, end_date)
            if HISTORICAL_DATA.empty:
                print(f"Keine Daten für {symbol} ({timeframe}). Überspringe.")
                continue

            with Pool(n_procs) as pool:
                problem = EnvelopeOptimizationProblem(parallelization=StarmapParallelization(pool.starmap))
                algorithm = NSGA2(pop_size=100)
                termination = get_termination("n_gen", n_gen)

                print(f"Starte globale Optimierung mit {n_procs} CPU-Kernen für {n_gen} Generationen...")
                res = minimize(problem, algorithm, termination, seed=1, save_history=False, verbose=True)

                print("Globale Suche abgeschlossen. Analysiere Ergebnisse...")
                valid_indices = [i for i, f in enumerate(res.F) if f[0] < 0]
                if not valid_indices:
                    print("Keine profitablen Ergebnisse in diesem Lauf gefunden.")
                    continue
                
                best_indices = sorted(valid_indices, key=lambda i: res.F[i][0])[:5]
                
                for i in best_indices:
                    champion_params = res.X[i]
                    pnl = -res.F[i][0]
                    drawdown = res.F[i][1]
                    param_dict = {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'start_date': start_date,
                        'end_date': end_date,
                        'start_capital': START_CAPITAL,
                        'pnl': pnl,
                        'drawdown': drawdown,
                        'params': {
                            'average_period': int(round(champion_params[0])),
                            'stop_loss_pct': round(champion_params[1], 2),
                            'base_leverage': int(round(champion_params[2])),
                            'target_atr_pct': round(champion_params[3], 2),
                            'envelopes_pct': [round(round(champion_params[4], 2) + j * round(champion_params[5], 2), 2) for j in range(int(round(champion_params[6])))]
                        }
                    }
                    all_champions.append(param_dict)

    if not all_champions:
        print("\nKeine vielversprechenden Kandidaten gefunden. Prozess wird beendet.")
        return

    output_file = os.path.join(os.path.dirname(__file__), 'optimization_candidates.json')
    with open(output_file, 'w') as f:
        json.dump(all_champions, f, indent=4)
        
    print(f"\n--- Globale Suche beendet. Top {len(all_champions)} Kandidaten in '{output_file}' gespeichert. ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stufe 1: Globale Parameter-Optimierung mit Pymoo.")
    parser.add_argument('--jobs', type=int, default=1, help='Anzahl der CPU-Kerne für die Optimierung.')
    parser.add_argument('--gen', type=int, default=50, help='Anzahl der Generationen.')
    args = parser.parse_args()
    main(n_procs=args.jobs, n_gen=args.gen)
