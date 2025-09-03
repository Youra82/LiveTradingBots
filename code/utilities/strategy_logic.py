# code/utilities/strategy_logic.py

import pandas as pd
import ta

def calculate_envelope_indicators(data, params):
    """
    Berechnet den gleitenden Durchschnitt, die Envelopes und den ATR-Indikator
    und fügt sie als neue Spalten zu den Daten hinzu.
    VERBESSERUNG: Verwendet einen sauberen "Best-Practice"-Ansatz, um Indikatoren
    in einem separaten DataFrame zu erstellen und sie dann zu den Originaldaten
    hinzuzufügen. Dies vermeidet `SettingWithCopyWarning`s und ist performanter.
    """
    avg_type = params.get('average_type', 'DCM')
    avg_period = int(params.get('average_period', 5))
    envelopes = params.get('envelopes_pct', [])
    atr_period = params.get('atr_period', 14)

    # 1. Alle Indikator-Berechnungen durchführen
    if avg_type == 'DCM':
        average = ta.volatility.DonchianChannel(data['high'], data['low'], data['close'], window=avg_period).donchian_channel_mband()
    elif avg_type == 'SMA':
        average = ta.trend.sma_indicator(data['close'], window=avg_period)
    elif avg_type == 'WMA':
        average = ta.trend.wma_indicator(data['close'], window=avg_period)
    else:
        raise ValueError(f"Der Durchschnittstyp {avg_type} wird nicht unterstützt")

    atr = ta.volatility.AverageTrueRange(data['high'], data['low'], data['close'], window=atr_period).average_true_range()
    atr_pct = (atr / data['close']) * 100

    # 2. Einen neuen, leeren DataFrame für die Indikatoren erstellen
    indicators = pd.DataFrame(index=data.index)

    # 3. Dem neuen DataFrame die berechneten Spalten zuweisen
    indicators['average'] = average
    indicators['atr'] = atr
    indicators['atr_pct'] = atr_pct
    
    # Symmetrische Berechnung der Envelopes
    for i, e_pct in enumerate(envelopes):
        e = e_pct / 100
        indicators[f'band_high_{i + 1}'] = average * (1 + e)
        indicators[f'band_low_{i + 1}'] = average * (1 - e)
    
    # 4. Den Original-DataFrame mit dem Indikatoren-DataFrame verbinden
    return data.join(indicators)

