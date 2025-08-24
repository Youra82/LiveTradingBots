# code/analysis/genetic_optimizer.py

import random
import numpy as np
import warnings
import sys
import os
import time
import pandas as pd
from deap import base, creator, tools, algorithms

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from analysis.backtest import load_data, run_envelope_backtest
from utilities.strategy_logic import calculate_envelope_indicators

warnings.filterwarnings("ignore", category=RuntimeWarning)

# --- Globale Variablen (werden im Hauptteil befüllt) ---
HISTORICAL_DATA = None
START_CAPITAL = 1000.0
MAX_LOSS_PER_TRADE_PCT = 2.0
MINIMUM_TRADES = 10

# --- Fitness & Individuum Definition ---
creator.create("FitnessMulti", base.Fitness, weights=(1.0, -1.0)) # (PnL, -Drawdown)
creator.create("Individual", list, fitness=creator.FitnessMulti)

# --- Genpool Definition ---
toolbox = base.Toolbox()
toolbox.register("attr_avg_period",   random.randint, 5, 89)
toolbox.register("attr_sl_pct",       random.uniform, 0.5, 5.0)
toolbox.register("attr_base_lev",     random.randint, 1, 50)
toolbox.register("attr_target_atr",   random.uniform, 1.0, 5.0)
toolbox.register("attr_env_start",    random.uniform, 2.0, 10.0)
toolbox.register("attr_env_step",     random.uniform, 1.0, 10.0)
toolbox.register("attr_env_count",    random.choice,  [1, 2, 3, 4])

toolbox.register("individual", tools.initCycle, creator.Individual,
                 (toolbox.attr_avg_period, toolbox.attr_sl_pct, toolbox.attr_base_lev,
                  toolbox.attr_target_atr, toolbox.attr_env_start, toolbox.attr_env_step,
                  toolbox.attr_env_count), n=1)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)

# --- Fitness-Funktion ---
def evaluate_fitness(individual):
    avg_period = int(max(2, individual[0]))
    sl_pct = round(max(0.5, individual[1]), 2)
    base_lev = int(max(1, individual[2]))
    target_atr = round(max(0.1, individual[3]), 2)
    env_start = round(max(0.1, individual[4]), 2)
    env_step = round(max(0.1, individual[5]), 2)
    env_count = int(max(1, individual[6]))

    envelopes = [round(env_start + i * env_step, 2) for i in range(env_count)]
    
    if any(e >= 100.0 for e in envelopes):
        return -1003, 1003

    params = {
        'average_period':   avg_period, 'stop_loss_pct':    sl_pct,
        'base_leverage':    base_lev, 'max_leverage':     50.0,
        'target_atr_pct':   target_atr,
        'envelopes_pct':    envelopes,
        'start_capital':    START_CAPITAL
    }
    
    data_with_indicators = calculate_envelope_indicators(HISTORICAL_DATA.copy(), params)
    result = run_envelope_backtest(data_with_indicators.dropna(), params)

    pnl = result.get('total_pnl_pct', -100)
    
    if pnl > 50000:
        return -1002, 1002

    if result['trades_count'] < MINIMUM_TRADES: return -1000, 1000
    
    if result["trade_log"]:
        for trade in result["trade_log"]:
            loss_pct = abs(trade['pnl'] / START_CAPITAL * 100)
            if trade['pnl'] < 0 and loss_pct > MAX_LOSS_PER_TRADE_PCT: return -1001, 1001

    return pnl, result.get('max_drawdown_pct', 1.0) * 100

toolbox.register("evaluate", evaluate_fitness)
toolbox.register("mate", tools.cxBlend, alpha=0.5)
toolbox.register("mutate", tools.mutGaussian, mu=0, sigma=1.0, indpb=0.2)
toolbox.register("select", tools.selNSGA2)

def format_time(seconds):
    if seconds < 60: return f"{seconds:.1f} Sekunden"
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    if minutes < 60: return f"{minutes} Minuten und {remaining_seconds} Sekunden"
    hours = int(minutes // 60)
    remaining_minutes = int(minutes % 60)
    return f"{hours} Stunden, {remaining_minutes} Minuten und {remaining_seconds} Sekunden"

def get_validated_input(prompt, data_type, error_message="Ungültige Eingabe. Bitte eine gültige Zahl eingeben."):
    while True:
        user_input_str = input(prompt)
        if not user_input_str:
            print("! Bitte einen Wert angeben, die Eingabe darf nicht leer sein.")
            continue
        try:
            return data_type(user_input_str)
        except ValueError:
            print(f"! {error_message}")

# --- Hauptprozess der Evolution ---
def main(num_generations):
    NGEN = num_generations
    MU = 100
    CXPB = 0.7
    MUTPB = 0.2

    pop = toolbox.population(n=MU)
    hof = tools.HallOfFame(10)
    
    print("\nStarte genetische Optimierung...")
    
    fitnesses = toolbox.map(toolbox.evaluate, pop)
    for ind, fit in zip(pop, fitnesses):
        ind.fitness.values = fit
    
    hof.update(pop)

    for g in range(1, NGEN + 1):
        offspring = toolbox.select(pop, len(pop))
        offspring = list(map(toolbox.clone, offspring))

        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < CXPB:
                toolbox.mate(child1, child2)
                del child1.fitness.values
                del child2.fitness.values
        
        for mutant in offspring:
            if random.random() < MUTPB:
                toolbox.mutate(mutant)
                del mutant.fitness.values

        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit
        
        pop[:] = offspring
        hof.update(pop)
        
        print(f"\rGeneration {g}/{NGEN} abgeschlossen.", end="", flush=True)
    
    return hof


if __name__ == "__main__":
    
    print("\n--- Testumgebung definieren ---")
    symbol_input = get_validated_input("Handelspaar(e) eingeben (z.B. BTC ETH): ", str)
    timeframe_input = get_validated_input("Zeitfenster eingeben (z.B. 1h 4h): ", str)
    start_date = get_validated_input("Startdatum eingeben (JJJJ-MM-TT): ", str)
    end_date = get_validated_input("Enddatum eingeben (JJJJ-MM-TT): ", str)
    
    symbols_to_run = symbol_input.split()
    timeframes_to_run = timeframe_input.split()

    print("\n--- Ziele und Regeln für die Optimierung festlegen ---")
    START_CAPITAL = get_validated_input("Startkapital in USDT eingeben (z.B. 1000): ", float)
    MAX_LOSS_PER_TRADE_PCT = get_validated_input("Maximaler Verlust pro Trade in % des Startkapitals (z.B. 2.0): ", float)
    MINIMUM_TRADES = get_validated_input("Mindestanzahl an Trades für ein gültiges Ergebnis (z.B. 20): ", int)
    
    print("\nAnzahl der Generationen festlegen:")
    print(" -> Mehr Generationen = Gründlichere Suche, aber längere Dauer.")
    print(" -> Weniger Generationen = Schneller Test, aber evtl. nicht das beste Ergebnis.")
    ngen_input = get_validated_input("Anzahl der Generationen eingeben (z.B. 50): ", int)
    
    grand_hall_of_fame = []

    # NEU: Äußere Schleife für die Handelspaare
    for symbol_short in symbols_to_run:
        symbol = f"{symbol_short.upper()}/USDT:USDT"
        print("\n" + "#"*80)
        print(f"####### OPTIMIERE HANDELSPAAR: {symbol.upper()} #######".center(80))
        print("#"*80)

        # Innere Schleife für die Zeitfenster
        for timeframe in timeframes_to_run:
            print("\n" + "="*80)
            print(f"=== STARTE OPTIMIERUNG FÜR TIMEFRAME: {timeframe.upper()} ===".center(80))
            print("="*80)

            print(f"\nLade historische Daten für {symbol} ({timeframe}) von {start_date} bis {end_date}...")
            HISTORICAL_DATA = load_data(symbol, timeframe, start_date, end_date)

            if HISTORICAL_DATA is None or HISTORICAL_DATA.empty:
                print(f"Fehler beim Laden der Daten für {timeframe}. Überspringe dieses Zeitfenster.")
                continue
            
            print("Daten erfolgreich geladen.")

            print("\nFühre kurzen Benchmark zur Zeitschätzung durch...")
            num_benchmarks = 3
            benchmark_times = []
            for _ in range(num_benchmarks):
                start_b = time.time()
                individual = toolbox.individual()
                evaluate_fitness(individual)
                end_b = time.time()
                benchmark_times.append(end_b - start_b)
            
            if not benchmark_times or sum(benchmark_times) == 0:
                print("Benchmark konnte nicht durchgeführt werden. Überspringe Zeitschätzung.")
            else:
                avg_time_per_run = sum(benchmark_times) / len(benchmark_times)
                population_size = 100
                total_evaluations = population_size + (ngen_input * population_size)
                estimated_total_time = avg_time_per_run * total_evaluations
                print(f"Durchschnittliche Berechnungszeit pro Variante: {avg_time_per_run:.3f} Sekunden.")
                print(f"Geschätzte Gesamtdauer für ~{total_evaluations} Berechnungen: {format_time(estimated_total_time)}")
            
            hof_for_timeframe = main(num_generations=ngen_input)
            
            for champion in hof_for_timeframe:
                grand_hall_of_fame.append({'champion': champion, 'symbol': symbol, 'timeframe': timeframe})
    
    print("\n\n" + "#"*80)
    print("##########   GLOBALE GESAMTAUSWERTUNG (TOP 10 ALLER LÄUFE)   ##########".center(80))
    print("#"*80)
    
    if not grand_hall_of_fame:
        print("Keine gültigen Ergebnisse gefunden, um eine Gesamtauswertung zu erstellen.")
    else:
        sorted_hof = sorted(grand_hall_of_fame, key=lambda x: x['champion'].fitness.values[0], reverse=True)
        
        for i, entry in enumerate(sorted_hof[:10]):
            champion = entry['champion']
            symbol = entry['symbol']
            timeframe = entry['timeframe']

            HISTORICAL_DATA = load_data(symbol, timeframe, start_date, end_date)
            
            avg_period_final = int(max(2, champion[0]))
            sl_pct_final = round(max(0.5, champion[1]), 2)
            base_lev_final = int(max(1, champion[2]))
            target_atr_final = round(max(0.1, champion[3]), 2)
            env_start_final = round(max(0.1, champion[4]), 2)
            env_step_final = round(max(0.1, champion[5]), 2)
            env_count_final = int(max(1, champion[6]))
            envelopes = [round(env_start_final + j * env_step_final, 2) for j in range(env_count_final)]
            
            params = {
                'average_period':   avg_period_final, 'stop_loss_pct':    sl_pct_final,
                'base_leverage':    base_lev_final, 'max_leverage':     50.0,
                'target_atr_pct':   target_atr_final, 'envelopes_pct': envelopes,
                'start_capital':    START_CAPITAL
            }
            
            data_with_indicators = calculate_envelope_indicators(HISTORICAL_DATA.copy(), params)
            final_result = run_envelope_backtest(data_with_indicators.dropna(), params)
            
            print("\n" + "="*50); print(f"                 --- GLOBALER PLATZ {i+1} ---"); print("="*50)
            print(f"  HANDELSPAAR: {symbol}"); print(f"  TIMEFRAME:   {timeframe}")
            print("\n  LEISTUNG:")
            print(f"    Gewinn (PnL):      {final_result['total_pnl_pct']:.2f} %")
            print(f"    Startkapital:      {START_CAPITAL:.2f} USDT")
            print(f"    Endkapital:        {final_result['end_capital']:.2f} USDT")
            print(f"    Anzahl Trades:     {int(final_result['trades_count'])}")
            print(f"    Max. Drawdown:     {final_result.get('max_drawdown_pct', 0)*100:.2f}%")
            
            print("\n  ERMITTELTE EINSTELLWERTE:")
            print(f"    average_period     {params['average_period']}")
            print(f"    stop_loss_pct      {params['stop_loss_pct']}%")
            print(f"    base_leverage      {params['base_leverage']}x (Max: {params['max_leverage']}x)")
            print(f"    target_atr_pct     {params['target_atr_pct']}%")
            print(f"    envelopes_pct      {params['envelopes_pct']}")
            
            trade_log_list = final_result.get('trade_log', [])
            if trade_log_list:
                print("\n  DETAILLIERTE HANDELS-CHRONIK:")
                log_display_limit = 20
                if len(trade_log_list) > log_display_limit:
                    display_list = trade_log_list[:10] + [None] + trade_log_list[-10:]
                    print(f"  (Zeige die ersten 10 und letzten 10 von {len(trade_log_list)} Trades)")
                else:
                    display_list = trade_log_list
                
                print("  " + "-"*102)
                print("  {:^28} | {:<7} | {:<7} | {:>10} | {:>10} | {:>17} | {:>18}".format(
                    "Datum & Uhrzeit (UTC)", "Seite", "Hebel", "Einstieg", "Ausstieg", "Gewinn je Trade", "Neuer Kontostand"
                ))
                print("  " + "-"*102)

                for trade in display_list:
                    if trade is None:
                        print("  ...".center(104))
                        continue
                    side_str = trade['side'].capitalize().ljust(7)
                    leverage_str = f"{int(trade.get('leverage', 0))}x".ljust(7)
                    entry_str = f"{trade['entry']:.4f}".rjust(10)
                    exit_str = f"{trade['exit']:.4f}".rjust(10)
                    pnl_str = f"{trade['pnl']:+9.2f} USDT".rjust(17)
                    balance_str = f"{trade['balance']:.2f} USDT".rjust(18)
                    print(f"  {trade['timestamp']:<28} | {side_str} | {leverage_str} | {entry_str} | {exit_str} | {pnl_str} | {balance_str}")
                print("  " + "-"*102)
        print("\n" + "="*50)
