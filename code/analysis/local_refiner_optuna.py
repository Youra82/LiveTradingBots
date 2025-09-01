# code/analysis/local_refiner_optuna.py

import json
import os
import sys
import argparse
import optuna
import numpy as np

# --- Pfade und Module laden ---
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from analysis.backtest import load_data, run_envelope_backtest
from utilities.strategy_logic import calculate_envelope_indicators

optuna.logging.set_verbosity(optuna.logging.WARNING)

# --- Globale Variablen ---
HISTORICAL_DATA = None
START_CAPITAL = 1000.0
BASE_PARAMS = {}

def objective(trial):
    """Die Zielfunktion für eine einzelne Optuna-Studie."""
    base_avg_period = BASE_PARAMS.get('average_period', 20)
    base_sl_pct = BASE_PARAMS.get('stop_loss_pct', 2.0)
    base_leverage = BASE_PARAMS.get('base_leverage', 10)
    base_target_atr = BASE_PARAMS.get('target_atr_pct', 2.0)
    base_envelopes = BASE_PARAMS.get('envelopes_pct', [5.0, 10.0])

    avg_period = trial.suggest_int('average_period', max(5, base_avg_period - 10), base_avg_period + 10)
    sl_pct = trial.suggest_float('stop_loss_pct', max(0.5, base_sl_pct * 0.8), base_sl_pct * 1.2)
    base_lev = trial.suggest_int('base_leverage', max(1, base_leverage - 5), base_leverage + 5)
    target_atr = trial.suggest_float('target_atr_pct', max(0.5, base_target_atr * 0.8), base_target_atr * 1.2)
    
    if not base_envelopes: return -1000
    
    env_start = trial.suggest_float('env_start', max(0.5, base_envelopes[0] * 0.8), base_envelopes[0] * 1.2)
    
    if len(base_envelopes) > 1:
        step = base_envelopes[1] - base_envelopes[0]
        env_step = trial.suggest_float('env_step', max(0.5, step * 0.8), step * 1.2)
        envelopes = [round(env_start + i * env_step, 2) for i in range(len(base_envelopes))]
    else:
        envelopes = [round(env_start, 2)]

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
    drawdown = result.get('max_drawdown_pct', 1.0)
    
    # Score = PnL, bestraft durch Drawdown. Ein DD von 0.2 (20%) reduziert den PnL-Score um 20%.
    score = pnl * (1 - drawdown)
    
    return score if np.isfinite(score) else -1000

def main(n_jobs):
    print("\n--- [Stufe 2/2] Lokale Verfeinerung mit Optuna ---")
    
    input_file = os.path.join(os.path.dirname(__file__), 'optimization_candidates.json')
    if not os.path.exists(input_file):
        print(f"Fehler: '{input_file}' nicht gefunden. Bitte zuerst 'global_optimizer_pymoo.py' ausführen.")
        return

    with open(input_file, 'r') as f:
        candidates = json.load(f)

    print(f"Lade {len(candidates)} Kandidaten zur Verfeinerung...")
    
    best_overall_trial = None
    best_overall_score = -float('inf')
    best_overall_info = {}

    for i, candidate in enumerate(candidates):
        print(f"\n===== Verfeinere Kandidat {i+1}/{len(candidates)} für {candidate['symbol']} ({candidate['timeframe']}) =====")
        
        global HISTORICAL_DATA, BASE_PARAMS, START_CAPITAL
        HISTORICAL_DATA = load_data(candidate['symbol'], candidate['timeframe'], candidate['start_date'], candidate['end_date'])
        BASE_PARAMS = candidate['params']
        START_CAPITAL = candidate['start_capital']
        
        if HISTORICAL_DATA.empty:
            print("Konnte Daten nicht laden. Überspringe.")
            continue
            
        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=200, n_jobs=n_jobs)
        
        best_trial = study.best_trial
        print(f"Bester Score in dieser Runde: {best_trial.value:.2f}")

        if best_trial.value > best_overall_score:
            best_overall_score = best_trial.value
            best_overall_trial = best_trial
            best_overall_info = candidate

    if best_overall_trial:
        print("\n\n" + "="*80)
        print("    +++ FINALES BESTES ERGEBNIS NACH GLOBALER & LOKALER OPTIMIERUNG +++")
        print("="*80)
        print(f"  HANDELSPAAR: {best_overall_info['symbol']}")
        print(f"  TIMEFRAME:   {best_overall_info['timeframe']}")
        print(f"\n  PERFORMANCE-SCORE: {best_overall_score:.2f} (PnL, gewichtet mit Drawdown)")
        
        # Finalen Backtest mit den besten Parametern durchführen, um volle Statistiken zu erhalten
        final_params_dict = best_overall_trial.params
        if 'env_start' in final_params_dict:
            base_envelopes_count = len(best_overall_info['params']['envelopes_pct'])
            env_start = final_params_dict.pop('env_start')
            env_step = final_params_dict.pop('env_step', 0)
            final_params_dict['envelopes_pct'] = [round(env_start + i * env_step, 2) for i in range(base_envelopes_count)]

        final_params = {**final_params_dict, 'start_capital': START_CAPITAL}
        data_with_indicators = calculate_envelope_indicators(HISTORICAL_DATA.copy(), final_params)
        final_result = run_envelope_backtest(data_with_indicators.dropna(), final_params)

        print("\n  FINALE PERFORMANCE-METRIKEN:")
        print(f"    - Gesamtgewinn (PnL): {final_result['total_pnl_pct']:.2f} %")
        print(f"    - Max. Drawdown:      {final_result['max_drawdown_pct']*100:.2f} %")
        print(f"    - Anzahl Trades:      {final_result['trades_count']}")
        print(f"    - Win-Rate:           {final_result['win_rate']:.2f} %")

        print("\n  OPTIMIERTE EINSTELLUNGEN:")
        for key, value in final_params_dict.items():
            print(f"    - {key}: {value}")
        print("\n" + "="*80)
    else:
        print("Kein gültiges Ergebnis nach der Verfeinerung gefunden.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stufe 2: Lokale Parameter-Verfeinerung mit Optuna.")
    parser.add_argument('--jobs', type=int, default=1, help='Anzahl der CPU-Kerne für die Optimierung.')
    args = parser.parse_args()
    main(n_jobs=args.jobs)
