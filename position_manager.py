"""
═══════════════════════════════════════════════════════════════════
   POSITION MANAGER
═══════════════════════════════════════════════════════════════════
   Gestiona posiciones abiertas:
   - Break Even automático
   - Trailing Stop
   - Detección de cierre por TP/SL
═══════════════════════════════════════════════════════════════════
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
import config as cfg

logger = logging.getLogger(__name__)


class Position:
    """Representa una posición abierta"""
    
    def __init__(self, symbol: str, direction: str, entry: float, sl: float,
                  tp1: float, tp2: float, quantity: float, orders: dict, score: float):
        self.symbol = symbol
        self.direction = direction
        self.entry = entry
        self.initial_sl = sl
        self.current_sl = sl
        self.tp1 = tp1
        self.tp2 = tp2
        self.quantity = quantity
        self.remaining_quantity = quantity
        self.orders = orders  # {entry_order, sl_order, tp1_order, tp2_order}
        self.score = score
        
        # Estado
        self.opened_at = datetime.utcnow()
        self.break_even_set = False
        self.trailing_active = False
        self.tp1_hit = False
        self.tp2_hit = False
        self.closed = False
        self.close_reason = None
        self.pnl = 0.0
        
        # SL distance original
        self.sl_distance = abs(entry - sl)
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'entry': self.entry,
            'sl': self.current_sl,
            'tp1': self.tp1,
            'tp2': self.tp2,
            'quantity': self.quantity,
            'remaining': self.remaining_quantity,
            'score': self.score,
            'break_even': self.break_even_set,
            'trailing': self.trailing_active,
            'tp1_hit': self.tp1_hit,
            'opened_at': self.opened_at.isoformat(),
        }
    
    def calculate_current_rr(self, current_price: float) -> float:
        """Calcula el R:R actual"""
        if self.sl_distance == 0:
            return 0.0
        
        if self.direction == 'LONG':
            profit_distance = current_price - self.entry
        else:
            profit_distance = self.entry - current_price
        
        return profit_distance / self.sl_distance


class PositionManager:
    """Gestiona todas las posiciones abiertas"""
    
    def __init__(self, exchange, telegram=None):
        self.exchange = exchange
        self.telegram = telegram
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.closed_today = []
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
    
    def add_position(self, position: Position):
        """Agrega una posición al gestor"""
        self.positions[position.symbol] = position
        logger.info(f"📊 Posición registrada: {position.symbol} {position.direction}")
    
    def remove_position(self, symbol: str, reason: str = "manual"):
        """Quita una posición del gestor"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.closed = True
            pos.close_reason = reason
            self.closed_today.append(pos)
            del self.positions[symbol]
            logger.info(f"🔚 Posición removida: {symbol} ({reason})")
    
    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions
    
    def count_positions(self) -> int:
        return len(self.positions)
    
    def can_open_new(self) -> bool:
        """¿Se puede abrir una nueva posición?"""
        if self.count_positions() >= cfg.MAX_CONCURRENT_POSITIONS:
            return False
        
        # Verificar drawdown diario
        if self.daily_pnl < 0:
            balance = self.exchange.get_account_balance()
            if balance > 0:
                drawdown_pct = abs(self.daily_pnl) / balance
                if drawdown_pct >= cfg.MAX_DAILY_DRAWDOWN_PCT:
                    logger.warning(f"⚠️ Drawdown diario alcanzado: {drawdown_pct*100:.2f}%")
                    return False
        
        # Verificar pérdidas consecutivas
        if self.consecutive_losses >= cfg.MAX_CONSECUTIVE_LOSSES:
            logger.warning(f"⚠️ {cfg.MAX_CONSECUTIVE_LOSSES} pérdidas consecutivas - cooldown")
            return False
        
        return True
    
    def manage_all_positions(self):
        """Gestiona todas las posiciones abiertas"""
        if not self.positions:
            return
        
        # Sincronizar con Binance (detectar cierres por TP/SL)
        self._sync_with_binance()
        
        # Para cada posición activa, evaluar break even y trailing
        for symbol, position in list(self.positions.items()):
            try:
                self._manage_position(position)
            except Exception as e:
                logger.error(f"Error gestionando {symbol}: {e}", exc_info=True)
    
    def _sync_with_binance(self):
        """Verifica qué posiciones siguen abiertas en Binance"""
        if cfg.DRY_RUN:
            return
        
        try:
            binance_positions = self.exchange.get_open_positions()
            binance_symbols = {p['symbol'] for p in binance_positions if float(p['positionAmt']) != 0}
            
            # Detectar posiciones cerradas (no están en Binance pero sí en nuestro tracker)
            for symbol in list(self.positions.keys()):
                if symbol not in binance_symbols:
                    pos = self.positions[symbol]
                    # Calcular PnL aproximado (necesitaríamos el precio de cierre real)
                    logger.info(f"🔚 Detectado cierre: {symbol}")
                    
                    # Determinar razón (TP/SL/manual)
                    reason = "TP/SL hit"
                    
                    # Notificar
                    if self.telegram:
                        self.telegram.send_position_closed(pos, reason)
                    
                    self.remove_position(symbol, reason)
        except Exception as e:
            logger.error(f"Error sincronizando: {e}")
    
    def _manage_position(self, position: Position):
        """Gestiona una posición individual: break even y trailing"""
        if position.closed:
            return
        
        try:
            # Obtener precio actual
            ticker = self.exchange.client.futures_symbol_ticker(symbol=position.symbol)
            current_price = float(ticker['price'])
            
            # Calcular R:R actual
            current_rr = position.calculate_current_rr(current_price)
            
            # BREAK EVEN
            if cfg.ENABLE_BREAK_EVEN and not position.break_even_set:
                if current_rr >= cfg.BREAK_EVEN_TRIGGER_RR:
                    self._set_break_even(position)
            
            # TRAILING STOP
            if cfg.ENABLE_TRAILING_STOP and position.break_even_set:
                if current_rr >= cfg.TRAILING_ACTIVATION_RR:
                    self._update_trailing_stop(position, current_price)
        
        except Exception as e:
            logger.error(f"Error gestionando posición {position.symbol}: {e}")
    
    def _set_break_even(self, position: Position):
        """Mueve el SL a break even (entrada + buffer)"""
        try:
            # Calcular nuevo SL
            if position.direction == 'LONG':
                new_sl = position.entry * (1 + cfg.BREAK_EVEN_BUFFER_PCT)
            else:
                new_sl = position.entry * (1 - cfg.BREAK_EVEN_BUFFER_PCT)
            
            # Obtener ID del SL anterior
            old_sl_id = position.orders.get('sl_order', {}).get('orderId')
            
            # Actualizar en Binance
            new_order = self.exchange.update_stop_loss(
                position.symbol,
                position.direction,
                new_sl,
                position.remaining_quantity,
                old_sl_id
            )
            
            if new_order:
                position.current_sl = new_sl
                position.break_even_set = True
                position.orders['sl_order'] = new_order
                logger.info(f"✅ Break Even activado: {position.symbol} (SL: {new_sl})")
                
                if self.telegram:
                    self.telegram.send_break_even(position)
        
        except Exception as e:
            logger.error(f"Error en break even {position.symbol}: {e}")
    
    def _update_trailing_stop(self, position: Position, current_price: float):
        """Actualiza el trailing stop"""
        try:
            # Calcular nuevo SL
            if position.direction == 'LONG':
                new_sl = current_price * (1 - cfg.TRAILING_DISTANCE_PCT)
                # Solo actualizar si es mejor (más alto) que el actual
                if new_sl <= position.current_sl:
                    return
            else:
                new_sl = current_price * (1 + cfg.TRAILING_DISTANCE_PCT)
                # Solo actualizar si es mejor (más bajo) que el actual
                if new_sl >= position.current_sl:
                    return
            
            old_sl_id = position.orders.get('sl_order', {}).get('orderId')
            
            new_order = self.exchange.update_stop_loss(
                position.symbol,
                position.direction,
                new_sl,
                position.remaining_quantity,
                old_sl_id
            )
            
            if new_order:
                position.current_sl = new_sl
                position.trailing_active = True
                position.orders['sl_order'] = new_order
                logger.info(f"📈 Trailing actualizado: {position.symbol} -> SL: {new_sl}")
        
        except Exception as e:
            logger.error(f"Error en trailing {position.symbol}: {e}")
    
    def reset_daily(self):
        """Resetea contadores diarios"""
        logger.info(f"🔄 Reset diario - PnL del día: {self.daily_pnl:.2f}")
        self.closed_today = []
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
