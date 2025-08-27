# code/utilities/strategy_logic.py

import pandas as pd
import ta

def calculate_envelope_indicators(data, params):
    """
    Berechnet den gleitenden Durchschnitt, die Envelopes und den ATR-Indikator.
    VERBESSERUNG: Die Berechnung der Envelopes wurde auf eine symmetrische Methode umgestellt.
    """
    data_copy = data.copy()
    avg_type = params.get('average_type', 'DCM')
    avg_period = int(params.get('average_period', 5))
    envelopes = params.get('envelopes_pct', [])

    # Berechnung des gleitenden Durchschnitts
    if avg_type == 'DCM':
        ta_obj = ta.volatility.DonchianChannel(data_copy['high'], data_copy['low'], data_copy['close'], window=avg_period)
        average = ta_obj.donchian_channel_mband()
    elif avg_type == 'SMA':
        average = ta.trend.sma_indicator(data_copy['close'], window=avg_period)
    elif avg_type == 'WMA':
        average = ta.trend.wma_indicator(data_copy['close'], window=avg_period)
    else:
        raise ValueError(f"Der Durchschnittstyp {avg_type} wird nicht unterstützt")

    # DataFrame für neue Indikatoren vorbereiten, um Fragmentierung zu vermeiden
    indicator_series = {'average': average}
    
    # Symmetrische Berechnung der Envelopes
    for i, e_pct in enumerate(envelopes):
        e = e_pct / 100
        # VERBESSERUNG: Symmetrische Berechnung für obere und untere Bänder
        indicator_series[f'band_high_{i + 1}'] = average * (1 + e)
        indicator_series[f'band_low_{i + 1}'] = average * (1 - e)
    
    # ATR-Berechnung
    atr_period = params.get('atr_period', 14)  
    atr_indicator = ta.volatility.AverageTrueRange(data_copy['high'], data_copy['low'], data_copy['close'], window=atr_period)
    indicator_series['atr'] = atr_indicator.average_true_range()
    indicator_series['atr_pct'] = (indicator_series['atr'] / data_copy['close']) * 100

    # Alle neuen Spalten auf einmal hinzufügen
    indicators_df = pd.DataFrame(indicator_series, index=data_copy.index)
    
    return pd.concat([data_copy, indicators_df], axis=1)
