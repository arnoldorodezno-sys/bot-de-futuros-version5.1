"""
═══════════════════════════════════════════════════════════════════
   BINANCE EXCHANGE - Manejo de órdenes
═══════════════════════════════════════════════════════════════════
   
   ⚡ CARACTERÍSTICAS CRÍTICAS:
   - Coloca TP y SL como ÓRDENES REALES en Binance
   - Protección automática aunque el bot se caiga
   - Modo DRY_RUN para pruebas sin dinero
   - Reintentos automáticos
   - Logs detallados
═══════════════════════════════════════════════════════════════════
"""

import logging
import time
import math
from typing import Optional, Dict, List
from decimal import Decimal, ROUND_DOWN
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
import config as cfg

logger = logging.getLogger(__name__)



class PriceCache:
    """
    FIX #2 — WebSocket en lugar de REST para precios en tiempo real.
    
    El problema: llamar futures_klines() cada 60s por 20 símbolos = 20 requests/min.
    Con múltiples loops (análisis + gestión) se acumula y Binance bloquea (HTTP 429).
    
    La solución: mantener los últimos precios en un cache en memoria,
    actualizado por WebSocket streams. El REST solo se usa al inicio
    o cuando el WS se cae.
    """
    def __init__(self):
        self._prices: dict = {}   # symbol -> último precio
        self._lock = None         # threading.Lock (se inicializa en start)
        self._ws_active = False

    def update(self, symbol: str, price: float):
        self._prices[symbol] = price

    def get(self, symbol: str) -> float:
        return self._prices.get(symbol, 0.0)

    def is_ready(self, symbol: str) -> bool:
        return symbol in self._prices and self._prices[symbol] > 0

    def start_websocket(self, symbols: list, client):
        """Inicia stream de precios por WebSocket"""
        import threading
        self._lock = threading.Lock()

        def _stream():
            import json
            from binance import ThreadedWebsocketManager
            try:
                twm = ThreadedWebsocketManager(api_key=client.API_KEY, api_secret=client.API_SECRET)
                twm.start()

                # Suscribir a mark price streams de todos los símbolos
                streams = [f"{s.lower()}@markPrice@1s" for s in symbols]
                twm.start_futures_multiplex_socket(
                    callback=self._on_message,
                    streams=streams
                )
                self._ws_active = True
                twm.join()
            except Exception as e:
                self._ws_active = False

        t = threading.Thread(target=_stream, daemon=True)
        t.start()

    def _on_message(self, msg):
        try:
            data = msg.get('data', {})
            symbol = data.get('s', '')
            price = float(data.get('p', 0))
            if symbol and price > 0:
                with self._lock:
                    self._prices[symbol] = price
        except Exception:
            pass


# Instancia global del cache de precios
price_cache = PriceCache()


class BinanceExchange:
    """Maneja todas las operaciones con Binance Futures"""
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = None
        self.dry_run = cfg.DRY_RUN
        self.paper_trading = cfg.PAPER_TRADING
        
        # Cache para info de símbolos
        self._symbol_info_cache = {}
        
        if not self.dry_run:
            self._connect()
        else:
            logger.info("🔵 MODO DRY_RUN: Sin conexión real, simulando")
            self._connect()  # Igual conectamos para obtener precios
    
    def _connect(self):
        """Conecta a Binance Futures"""
        for attempt in range(1, cfg.MAX_RETRIES + 1):
            try:
                logger.info(f"🔌 Conectando a Binance Futures (intento {attempt})...")
                self.client = Client(self.api_key, self.api_secret)
                # Verificar conexión
                server_time = self.client.futures_time()
                logger.info(f"✅ Conectado a Binance Futures")
                # FIX #2: Iniciar WebSocket para precios en tiempo real
                try:
                    price_cache.start_websocket(cfg.SYMBOLS, self.client)
                    logger.info("🔌 WebSocket de precios iniciado (sin rate limits)")
                except Exception as ws_err:
                    logger.warning(f"⚠️ WebSocket no disponible, usando REST: {ws_err}")
                return
            except BinanceAPIException as e:
                logger.error(f"❌ Error API: {e}")
                if attempt < cfg.MAX_RETRIES:
                    time.sleep(cfg.RETRY_DELAY_SECONDS)
            except Exception as e:
                logger.error(f"❌ Error: {e}")
                if attempt < cfg.MAX_RETRIES:
                    time.sleep(cfg.RETRY_DELAY_SECONDS)
        
        raise Exception("No se pudo conectar a Binance")
    
    def get_account_balance(self) -> float:
        """Obtiene el balance USDT en futures"""
        if self.dry_run:
            return cfg.INITIAL_CAPITAL
        
        try:
            balance = self.client.futures_account_balance()
            for asset in balance:
                if asset['asset'] == 'USDT':
                    return float(asset['balance'])
            return 0.0
        except Exception as e:
            logger.error(f"Error obteniendo balance: {e}")
            return 0.0
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """Obtiene info del símbolo (precision, etc)"""
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        
        try:
            info = self.client.futures_exchange_info()
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    # Extraer filtros importantes
                    price_filter = next((f for f in s['filters'] if f['filterType'] == 'PRICE_FILTER'), {})
                    lot_filter = next((f for f in s['filters'] if f['filterType'] == 'LOT_SIZE'), {})
                    notional_filter = next((f for f in s['filters'] if f['filterType'] == 'MIN_NOTIONAL'), {})
                    
                    symbol_data = {
                        'symbol': symbol,
                        'pricePrecision': s.get('pricePrecision', 4),
                        'quantityPrecision': s.get('quantityPrecision', 3),
                        'tickSize': float(price_filter.get('tickSize', '0.0001')),
                        'stepSize': float(lot_filter.get('stepSize', '0.001')),
                        'minQty': float(lot_filter.get('minQty', '0.001')),
                        'minNotional': float(notional_filter.get('notional', '5.0')),
                    }
                    self._symbol_info_cache[symbol] = symbol_data
                    return symbol_data
            
            logger.warning(f"No se encontró info para {symbol}")
            return {}
        except Exception as e:
            logger.error(f"Error obteniendo info de {symbol}: {e}")
            return {}
    
    def round_price(self, symbol: str, price: float) -> float:
        """Redondea precio según tick size del símbolo"""
        info = self.get_symbol_info(symbol)
        if not info:
            return round(price, 4)
        
        tick_size = info['tickSize']
        precision = info['pricePrecision']
        
        # Redondear al tick size más cercano
        rounded = round(price / tick_size) * tick_size
        return float(Decimal(str(rounded)).quantize(Decimal(str(tick_size))))
    
    def round_quantity(self, symbol: str, quantity: float) -> float:
        """Redondea cantidad según step size"""
        info = self.get_symbol_info(symbol)
        if not info:
            return round(quantity, 3)
        
        step_size = info['stepSize']
        precision = info['quantityPrecision']
        
        # Redondear hacia abajo al step más cercano
        rounded = math.floor(quantity / step_size) * step_size
        return float(Decimal(str(rounded)).quantize(Decimal(str(step_size)), rounding=ROUND_DOWN))
    
    def calculate_position_size(self, symbol: str, entry: float, sl: float) -> float:
        """
        Calcula el tamaño de la posición según el riesgo configurado.
        
        Fórmula:
        - Capital * Risk% = Cantidad a arriesgar en USDT
        - SL distance = |entry - sl| / entry
        - Position size = Risk amount / SL distance / entry
        """
        capital = self.get_account_balance()
        if capital <= 0:
            logger.error("Capital insuficiente")
            return 0.0
        
        # Cantidad máxima a arriesgar
        risk_amount = capital * cfg.RISK_PER_TRADE_PCT
        
        # Distancia al SL en %
        sl_distance_pct = abs(entry - sl) / entry
        
        if sl_distance_pct <= 0:
            logger.error("SL distance es 0")
            return 0.0
        
        # Tamaño de posición en USDT (sin apalancamiento)
        position_size_usdt = risk_amount / sl_distance_pct
        
        # Cantidad de monedas
        quantity = position_size_usdt / entry
        
        # Redondear según el símbolo
        quantity = self.round_quantity(symbol, quantity)
        
        # Verificar mínimo notional
        info = self.get_symbol_info(symbol)
        if info:
            notional = quantity * entry
            if notional < info['minNotional']:
                # Ajustar al mínimo
                min_quantity = info['minNotional'] / entry
                quantity = self.round_quantity(symbol, min_quantity * 1.05)  # 5% buffer
                logger.warning(f"Cantidad ajustada al mínimo: {quantity}")
        
        return quantity
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Configura el apalancamiento"""
        if self.dry_run:
            logger.info(f"[DRY_RUN] Leverage {symbol} = {leverage}x")
            return True
        
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            logger.info(f"✅ Leverage {symbol}: {leverage}x")
            return True
        except BinanceAPIException as e:
            logger.error(f"Error configurando leverage: {e}")
            return False
    
    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> bool:
        """Configura tipo de margen"""
        if self.dry_run:
            return True
        
        try:
            self.client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
            logger.info(f"✅ Margin type {symbol}: {margin_type}")
            return True
        except BinanceAPIException as e:
            # Error 4046 = ya está en ese modo, ignorar
            if e.code == -4046:
                return True
            logger.warning(f"Margin type: {e}")
            return False
    
    def open_position_with_protection(self, symbol: str, direction: str, 
                                        entry: float, sl: float, tp1: float, tp2: float,
                                        quantity: float) -> Optional[Dict]:
        """
        ⚡ FUNCIÓN CRÍTICA: Abre posición CON TP y SL REALES en Binance
        
        Retorna dict con todas las órdenes creadas:
        {
            'entry_order': ...,
            'sl_order': ...,
            'tp1_order': ...,
            'tp2_order': ...,
        }
        """
        side = 'BUY' if direction == 'LONG' else 'SELL'
        opposite_side = 'SELL' if direction == 'LONG' else 'BUY'
        
        # Redondear precios y cantidades
        entry = self.round_price(symbol, entry)
        sl = self.round_price(symbol, sl)
        tp1 = self.round_price(symbol, tp1)
        tp2 = self.round_price(symbol, tp2)
        quantity = self.round_quantity(symbol, quantity)
        
        # Calcular cantidades para TP1 y TP2
        # FIX #4 — Step Size decimales
        # El 60% puede dar decimales que Binance rechaza (ej: 0.1234 en símbolo con step 0.1)
        # Solución: redondear qty_tp1 HACIA ABAJO al step más cercano,
        # y qty_tp2 = total - tp1 (nunca superar el total poseído).
        qty_tp1 = self.round_quantity(symbol, quantity * cfg.TP1_CLOSE_PCT)

        # Verificar que qty_tp1 sea al menos el mínimo permitido
        info = self.get_symbol_info(symbol) or {}
        min_qty = float(info.get('minQty', 0.0))
        step_size = float(info.get('stepSize', 0.001))

        if qty_tp1 < min_qty:
            # Si el 60% es menor que el mínimo, cerrar todo en un solo TP
            qty_tp1 = quantity
            qty_tp2 = 0.0
        else:
            # qty_tp2 = lo que queda exactamente según el step del exchange
            raw_tp2 = quantity - qty_tp1
            qty_tp2 = self.round_quantity(symbol, raw_tp2)
            # Si queda tan poco que no alcanza el mínimo, agruparlo en TP1
            if qty_tp2 < min_qty:
                qty_tp1 = quantity
                qty_tp2 = 0.0
        
        if self.dry_run:
            logger.info(f"[DRY_RUN] {symbol} {direction}")
            logger.info(f"  Entry: {entry} | SL: {sl} | TP1: {tp1} | TP2: {tp2}")
            logger.info(f"  Qty total: {quantity} | TP1 qty: {qty_tp1} | TP2 qty: {qty_tp2}")
            return {
                'entry_order': {'orderId': f'DRY_{int(time.time())}', 'price': entry, 'quantity': quantity},
                'sl_order': {'orderId': f'DRY_SL_{int(time.time())}', 'stopPrice': sl},
                'tp1_order': {'orderId': f'DRY_TP1_{int(time.time())}', 'stopPrice': tp1, 'quantity': qty_tp1},
                'tp2_order': {'orderId': f'DRY_TP2_{int(time.time())}', 'stopPrice': tp2, 'quantity': qty_tp2},
                'dry_run': True,
            }
        
        try:
            # 1. ORDEN DE ENTRADA (MARKET)
            logger.info(f"🚀 Abriendo {direction} en {symbol}...")
            entry_order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity,
            )
            logger.info(f"✅ Entrada ejecutada: {entry_order.get('orderId')}")
            
            # Pequeña pausa para que se procese
            time.sleep(0.5)
            
            orders_result = {'entry_order': entry_order}
            
            # 2. STOP LOSS (STOP_MARKET con reduceOnly)
            try:
                sl_order = self.client.futures_create_order(
                    symbol=symbol,
                    side=opposite_side,
                    type='STOP_MARKET',
                    stopPrice=sl,
                    quantity=quantity,
                    reduceOnly=True,
                    timeInForce='GTC',
                )
                logger.info(f"🛑 SL colocado en {sl}")
                orders_result['sl_order'] = sl_order
            except Exception as e:
                logger.error(f"❌ Error colocando SL: {e}")
                # Si falla el SL, cerrar la posición inmediatamente por seguridad
                self.client.futures_create_order(
                    symbol=symbol,
                    side=opposite_side,
                    type='MARKET',
                    quantity=quantity,
                    reduceOnly=True,
                )
                logger.error("⚠️ Posición cerrada por seguridad (SL falló)")
                return None
            
            # 3. TAKE PROFIT 1 (TAKE_PROFIT_MARKET parcial)
            try:
                tp1_order = self.client.futures_create_order(
                    symbol=symbol,
                    side=opposite_side,
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=tp1,
                    quantity=qty_tp1,
                    reduceOnly=True,
                    timeInForce='GTC',
                )
                logger.info(f"🎯 TP1 colocado en {tp1} (qty: {qty_tp1})")
                orders_result['tp1_order'] = tp1_order
            except Exception as e:
                logger.warning(f"⚠️ Error colocando TP1: {e}")
            
            # 4. TAKE PROFIT 2 (TAKE_PROFIT_MARKET resto)
            if qty_tp2 > 0:
                try:
                    tp2_order = self.client.futures_create_order(
                        symbol=symbol,
                        side=opposite_side,
                        type='TAKE_PROFIT_MARKET',
                        stopPrice=tp2,
                        quantity=qty_tp2,
                        reduceOnly=True,
                        timeInForce='GTC',
                    )
                    logger.info(f"🎯 TP2 colocado en {tp2} (qty: {qty_tp2})")
                    orders_result['tp2_order'] = tp2_order
                except Exception as e:
                    logger.warning(f"⚠️ Error colocando TP2: {e}")
            
            return orders_result
            
        except BinanceAPIException as e:
            logger.error(f"❌ Error API abriendo posición: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error abriendo posición: {e}", exc_info=True)
            return None
    
    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """Cancela una orden específica"""
        if self.dry_run:
            return True
        try:
            self.client.futures_cancel_order(symbol=symbol, orderId=order_id)
            return True
        except Exception as e:
            logger.warning(f"Error cancelando orden {order_id}: {e}")
            return False
    
    def cancel_all_orders(self, symbol: str) -> bool:
        """Cancela TODAS las órdenes pendientes del símbolo"""
        if self.dry_run:
            return True
        try:
            self.client.futures_cancel_all_open_orders(symbol=symbol)
            logger.info(f"✅ Órdenes canceladas: {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error cancelando órdenes: {e}")
            return False
    
    def close_position(self, symbol: str, direction: str, quantity: float) -> bool:
        """Cierra una posición a mercado"""
        side = 'SELL' if direction == 'LONG' else 'BUY'
        
        if self.dry_run:
            logger.info(f"[DRY_RUN] Cerrando {symbol}")
            return True
        
        try:
            self.cancel_all_orders(symbol)
            time.sleep(0.3)
            
            self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity,
                reduceOnly=True,
            )
            logger.info(f"✅ Posición cerrada: {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error cerrando: {e}")
            return False
    
    def get_open_positions(self) -> List[Dict]:
        """Obtiene todas las posiciones abiertas"""
        if self.dry_run:
            return []
        
        try:
            positions = self.client.futures_position_information()
            # Filtrar solo posiciones con cantidad > 0
            return [p for p in positions if float(p['positionAmt']) != 0]
        except Exception as e:
            logger.error(f"Error obteniendo posiciones: {e}")
            return []
    
    def get_klines(self, symbol: str, interval: str, limit: int = 200) -> Optional[pd.DataFrame]:
        """Obtiene velas históricas"""
        for attempt in range(1, cfg.MAX_RETRIES + 1):
            try:
                klines = self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
                if not klines:
                    return None
                
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])
                
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df
            except Exception as e:
                logger.warning(f"Error obteniendo klines {symbol} {interval}: {e}")
                if attempt < cfg.MAX_RETRIES:
                    time.sleep(cfg.RETRY_DELAY_SECONDS)
        return None
    
    def update_stop_loss(self, symbol: str, direction: str, new_sl: float, quantity: float, old_sl_order_id: int = None) -> Optional[Dict]:
        """Actualiza el SL (cancela el anterior y crea uno nuevo)"""
        if self.dry_run:
            return {'orderId': f'DRY_SL_NEW_{int(time.time())}', 'stopPrice': new_sl}
        
        side = 'SELL' if direction == 'LONG' else 'BUY'
        new_sl = self.round_price(symbol, new_sl)
        
        try:
            # Cancelar SL anterior
            if old_sl_order_id:
                self.cancel_order(symbol, old_sl_order_id)
            
            # Crear nuevo SL
            new_order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='STOP_MARKET',
                stopPrice=new_sl,
                quantity=quantity,
                reduceOnly=True,
                timeInForce='GTC',
            )
            logger.info(f"🔄 SL actualizado: {symbol} -> {new_sl}")
            return new_order
        except Exception as e:
            logger.error(f"Error actualizando SL: {e}")
            return None
