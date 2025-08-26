import ccxt
import time
import pandas as pd
from typing import Any, Optional, Dict, List


class BitgetFutures():
    def __init__(self, api_setup: Optional[Dict[str, Any]] = None) -> None:

        if api_setup == None:
            self.session = ccxt.bitget()
        else:
            api_setup.setdefault("options", {"defaultType": "future"})
            self.session = ccxt.bitget(api_setup)

        self.markets = self.session.load_markets()
    
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        try:
            return self.session.fetch_ticker(symbol)
        except Exception as e:
            raise Exception(f"Failed to fetch ticker for {symbol}: {e}")

    def fetch_min_amount_tradable(self, symbol: str) -> float:
        try:
            return self.markets[symbol]['limits']['amount']['min']
        except Exception as e:
            raise Exception(f"Failed to fetch minimum amount tradable: {e}")      
        
    def amount_to_precision(self, symbol: str, amount: float) -> str:
        try:
            return self.session.amount_to_precision(symbol, amount)
        except Exception as e:
            raise Exception(f"Failed to convert amount {amount} {symbol} to precision", e)

    def price_to_precision(self, symbol: str, price: float) -> str:
        try:
            return self.session.price_to_precision(symbol, price)
        except Exception as e:
            raise Exception(f"Failed to convert price {price} to precision for {symbol}", e)

    def fetch_balance(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if params is None:
            params = {}
        try:
            return self.session.fetch_balance(params)
        except Exception as e:
            raise Exception(f"Failed to fetch balance: {e}")

    def fetch_order(self, id: str, symbol: str) -> Dict[str, Any]:
        try:
            return self.session.fetch_order(id, symbol)
        except Exception as e:
            raise Exception(f"Failed to fetch order {id} info for {symbol}: {e}")

    def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        try:
            return self.session.fetch_open_orders(symbol)
        except Exception as e:
            raise Exception(f"Failed to fetch open orders: {e}")

    def fetch_open_trigger_orders(self, symbol: str) -> List[Dict[str, Any]]:
        try:
            return self.session.fetch_open_orders(symbol, params={'stop': True})
        except Exception as e:
            raise Exception(f"Failed to fetch open trigger orders: {e}")

    def fetch_closed_trigger_orders(self, symbol: str) -> List[Dict[str, Any]]:
        try:
            return self.session.fetch_closed_orders(symbol, params={'stop': True})
        except Exception as e:
            raise Exception(f"Failed to fetch closed trigger orders: {e}")

    def cancel_order(self, id: str, symbol: str) -> Dict[str, Any]:
        try:
            return self.session.cancel_order(id, symbol)
        except Exception as e:
            raise Exception(f"Failed to cancel the {symbol} order {id}", e)

    def cancel_trigger_order(self, id: str, symbol: str) -> Dict[str, Any]:
        try:
            return self.session.cancel_order(id, symbol, params={'stop': True})
        except Exception as e:
            raise Exception(f"Failed to cancel the {symbol} trigger order {id}", e)

    def fetch_open_positions(self, symbol: str) -> List[Dict[str, Any]]:
        try:
            positions = self.session.fetch_positions([symbol], params={'productType': 'USDT-FUTURES', 'marginCoin': 'USDT'})
            real_positions = []
            for position in positions:
                if float(position['contracts']) > 0:
                    real_positions.append(position)
            return real_positions
        except Exception as e:
            raise Exception(f"Failed to fetch open positions: {e}")

    def set_margin_mode(self, symbol: str, margin_mode: str = 'isolated') -> None:
        try:
            self.session.set_margin_mode(
                margin_mode,
                symbol,
                params={'productType': 'USDT-FUTURES', 'marginCoin': 'USDT'},
            )
        except Exception as e:
            raise Exception(f"Failed to set margin mode: {e}")

    def set_leverage(self, symbol: str, leverage: int = 1) -> None:
        try:
            # Für Bitget muss der Hebel für Long und Short separat gesetzt werden
            self.session.set_leverage(
                leverage,
                symbol,
                params={
                    'productType': 'USDT-FUTURES',
                    'marginCoin': 'USDT',
                    'holdSide': 'long',
                },
            )
            self.session.set_leverage(
                leverage,
                symbol,
                params={
                    'productType': 'USDT-FUTURES',
                    'marginCoin': 'USDT',
                    'holdSide': 'short',
                },
            )
        except Exception as e:
            raise Exception(f"Failed to set leverage: {e}")

    def fetch_recent_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        timeframe_in_ms = self.session.parse_timeframe(timeframe) * 1000
        since = self.session.milliseconds() - limit * timeframe_in_ms
        all_ohlcv = []
        try:
            all_ohlcv = self.session.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        except Exception as e:
            raise Exception(f"Failed to fetch OHLCV data for {symbol} in timeframe {timeframe}: {e}")

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        return df

    def fetch_historical_ohlcv(self, symbol: str, timeframe: str, start_date_str: str, end_date_str: str) -> pd.DataFrame:
        from datetime import datetime, timezone
        start_ts = int(datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        all_ohlcv = []
        while start_ts < end_ts:
            try:
                ohlcv = self.session.fetch_ohlcv(symbol, timeframe, since=start_ts, limit=1000)
                if not ohlcv: break
                all_ohlcv.extend(ohlcv)
                last_timestamp = ohlcv[-1][0]
                if last_timestamp >= start_ts:
                     start_ts = last_timestamp + 1
                else: break
            except Exception as e:
                raise Exception(f"Failed to fetch historical OHLCV data for {symbol}: {e}")
        if not all_ohlcv: return pd.DataFrame()
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df.set_index('timestamp', inplace=True)
        df = df[~df.index.duplicated(keep='first')]
        df.sort_index(inplace=True)
        return df

    def place_limit_order(self, symbol: str, side: str, amount: float, price: float, reduce: bool = False) -> Dict[str, Any]:
        try:
            params = {'reduceOnly': reduce}
            amount_str = self.session.amount_to_precision(symbol, amount)
            price_str = self.session.price_to_precision(symbol, price)
            return self.session.create_order(symbol, 'limit', side, float(amount_str), float(price_str), params=params)
        except Exception as e:
            raise Exception(f"Failed to place limit order of {amount} {symbol} at price {price}: {e}")

    def place_trigger_market_order(self, symbol: str, side: str, amount: float, trigger_price: float, reduce: bool = False) -> Optional[Dict[str, Any]]:
        try:
            amount_str = self.session.amount_to_precision(symbol, amount)
            trigger_price_str = self.session.price_to_precision(symbol, trigger_price)
            params = {
                'reduceOnly': reduce,
                'stopPrice': trigger_price_str,
            }
            return self.session.create_order(symbol, 'market', side, float(amount_str), params=params)
        except Exception as err:
            raise err
