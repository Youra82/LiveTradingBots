import pandas as pd
import ta

def calculate_envelope_indicators(data, params):
    """
    Berechnet den gleitenden Durchschnitt und die Envelopes.
    """
    avg_type = params.get('average_type', 'DCM')
    avg_period = params.get('average_period', 5)
    envelopes = params.get('envelopes_pct', [])

    if avg_type == 'DCM':
        ta_obj = ta.volatility.DonchianChannel(data['high'], data['low'], data['close'], window=avg_period)
        data['average'] = ta_obj.donchian_channel_mband()
    elif avg_type == 'SMA':
        data['average'] = ta.trend.sma_indicator(data['close'], window=avg_period)
    elif avg_type == 'EMA':
        data['average'] = ta.trend.ema_indicator(data['close'], window=avg_period)
    elif avg_type == 'WMA':
        data['average'] = ta.trend.wma_indicator(data['close'], window=avg_period)
    else:
        raise ValueError(f"Der Durchschnittstyp {avg_type} wird nicht unterstützt")

    for i, e_pct in enumerate(envelopes):
        e = e_pct / 100 # Konvertiere Prozent zu Dezimal
        data[f'band_high_{i + 1}'] = data['average'] / (1 - e)
        data[f'band_low_{i + 1}'] = data['average'] * (1 - e)
    
    return data
