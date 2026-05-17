"""
═══════════════════════════════════════════════════════════════════
   BOT DE FUTUROS SMC v3 - MAIN
═══════════════════════════════════════════════════════════════════
   
   Bot profesional con:
   - 4 filtros estrella (Multi-TF, ADX, SMC, Timing)
   - TP/SL REALES en Binance
   - Break Even automático
   - Trailing Stop
   - TP escalonado (60% + 40%)
   - Gestión de riesgo estricta
   - Modo DRY_RUN para pruebas
═══════════════════════════════════════════════════════════════════
"""

import os
import sys
import time
import signal as sys_signal
import logging
from datetime import datetime, timedelta
from typing import Dict

from dotenv import load_dotenv
load_dotenv()

import config as cfg

# Logging
logging.basicConfig(
    level=getattr(logging, cfg.LOG_LEVEL),
    format='%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("FuturesBotV5")

from apscheduler.schedulers.background import BackgroundScheduler
from binance_exchange import BinanceExchange
from position_manager import PositionManager, Position
from telegram_notifier import TelegramNotifier
import analyzer
import position_analyzer


class FuturesBotV5:
    """Bot de Futuros v5 - 4 filtros estrella + TP/SL reales"""
    
    def __init__(self):
        # Credenciales
        self.api_key = os.getenv('BINANCE_API_KEY', '').strip()
        self.api_secret = os.getenv('BINANCE_API_SECRET', '').strip()
        self.tg_token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
        self.tg_chat_id = os.getenv('TELEGRAM_CHAT_ID', '').strip()
        
        self._validate_credentials()
        
        # Inicializar componentes
        self.exchange = BinanceExchange(self.api_key, self.api_secret)
        self.telegram = TelegramNotifier(self.tg_token, self.tg_chat_id)
        self.position_manager = PositionManager(self.exchange, self.telegram)
        
        # Estado
        self.last_signals: Dict[str, datetime] = {}
        self.running = True
        self.scheduler = BackgroundScheduler()
        self.daily_stats = {
            'total_trades': 0,
            'winners': 0,
            'losers': 0,
            'win_rate': 0.0,
            'daily_pnl': 0.0,
            'capital': cfg.INITIAL_CAPITAL,
        }
        
        # Configurar leverage en todos los símbolos
        self._configure_symbols()
        
        logger.info("=" * 60)
        # ── Verificar balance real antes de operar ─────────────────
        real_balance = self.exchange.get_account_balance()
        if real_balance < 10.0 and not cfg.DRY_RUN:
            logger.error(f"❌ Balance insuficiente: ${real_balance:.2f} — mínimo $10 USDT")
            self.telegram.send_error(f"Balance insuficiente: ${real_balance:.2f}")
            raise SystemExit("Balance insuficiente")
        if not cfg.DRY_RUN:
            logger.info(f"💵 Balance real en Binance: ${real_balance:.2f} USDT")
        logger.info("🚀 BOT DE FUTUROS SMC v3 - INICIANDO")
        logger.info("=" * 60)
        logger.info(f"💰 Capital: ${cfg.INITIAL_CAPITAL}")
        logger.info(f"📊 Leverage: {cfg.LEVERAGE}x")
        logger.info(f"🎯 Risk/trade: {cfg.RISK_PER_TRADE_PCT*100}%")
        logger.info(f"📈 Max posiciones: {cfg.MAX_CONCURRENT_POSITIONS}")
        logger.info(f"⭐ Score mínimo: {cfg.SCORE_MIN_TO_TRADE}/10")
        logger.info(f"📐 R:R mínimo: 1:{cfg.MIN_RR_TO_TRADE}")
        logger.info(f"🔵 DRY_RUN: {cfg.DRY_RUN}")
        logger.info(f"💵 PAPER: {cfg.PAPER_TRADING}")
        logger.info("=" * 60)
    
    def _validate_credentials(self):
        missing = []
        if not self.api_key:
            missing.append("BINANCE_API_KEY")
        if not self.api_secret:
            missing.append("BINANCE_API_SECRET")
        
        if missing:
            logger.error(f"❌ Faltan: {', '.join(missing)}")
            sys.exit(1)
    
    def _configure_symbols(self):
        """Configura leverage y margin type para todos los símbolos"""
        logger.info("⚙️ Configurando símbolos...")
        for symbol in cfg.SYMBOLS:
            try:
                self.exchange.set_leverage(symbol, cfg.LEVERAGE)
                self.exchange.set_margin_type(symbol, cfg.MARGIN_TYPE)
                time.sleep(0.1)
            except Exception as e:
                logger.warning(f"Error configurando {symbol}: {e}")
    
    def can_evaluate_symbol(self, symbol: str) -> bool:
        """¿Se puede evaluar este símbolo?"""
        # Ya tenemos posición abierta
        if self.position_manager.has_position(symbol):
            return False
        
        # Cooldown desde última señal
        if symbol in self.last_signals:
            elapsed = datetime.utcnow() - self.last_signals[symbol]
            if elapsed < timedelta(minutes=cfg.SIGNAL_COOLDOWN_MINUTES):
                return False
        
        return True
    
    def is_trading_hour(self) -> bool:
        """Verifica si estamos en horario de trading"""
        if not cfg.ENABLE_TIME_FILTER:
            return True
        
        current_hour = datetime.utcnow().hour
        if current_hour in cfg.AVOID_HOURS_UTC:
            return False
        if current_hour not in cfg.ALLOWED_HOURS_UTC:
            return False
        return True
    
    def evaluate_all_symbols(self):
        """Evalúa todos los símbolos con ESTRATEGIA DUAL (Swing + Position)"""
        if not self.is_trading_hour():
            logger.debug("Fuera de horario de trading")
            return

        if not self.position_manager.can_open_new():
            logger.debug(f"No se pueden abrir más posiciones (max: {cfg.MAX_CONCURRENT_POSITIONS})")
            return

        logger.info(f"🔍 Buscando setups [{len(cfg.SYMBOLS)} símbolos | Swing + Position]...")
        signals_found = 0

        for symbol in cfg.SYMBOLS:
            try:
                if not self.can_evaluate_symbol(symbol):
                    continue

                if not self.position_manager.can_open_new():
                    break

                # ── ESTRATEGIA 1: SWING TRADING (15m + 1h + 4h) ──────────────
                swing_signal = None
                try:
                    df_macro = self.exchange.get_klines(symbol, cfg.TIMEFRAME_MACRO, cfg.CANDLES_LIMIT)
                    df_confirm = self.exchange.get_klines(symbol, cfg.TIMEFRAME_CONFIRM, cfg.CANDLES_LIMIT)
                    df_main = self.exchange.get_klines(symbol, cfg.TIMEFRAME_MAIN, cfg.CANDLES_LIMIT)

                    if df_macro is not None and df_confirm is not None and df_main is not None:
                        swing_signal = analyzer.analyze_symbol(df_macro, df_confirm, df_main)
                        if swing_signal:
                            swing_signal['strategy'] = 'SWING'
                except Exception as e:
                    logger.debug(f"Swing error {symbol}: {e}")

                # ── ESTRATEGIA 2: POSITION TRADING (4h + 1D) ─────────────────
                position_signal = None
                if cfg.ENABLE_POSITION_TRADING:
                    try:
                        df_daily = self.exchange.get_klines(symbol, cfg.TIMEFRAME_POSITION_MACRO, cfg.CANDLES_LIMIT)
                        df_4h = self.exchange.get_klines(symbol, cfg.TIMEFRAME_POSITION_CONFIRM, cfg.CANDLES_LIMIT)

                        if df_daily is not None and df_4h is not None:
                            position_signal = position_analyzer.analyze_position_trade(df_daily, df_4h)
                    except Exception as e:
                        logger.debug(f"Position error {symbol}: {e}")

                # ── SELECCIONAR LA MEJOR SEÑAL ────────────────────────────────
                # Si ambas dan señal, elegir la de mayor score
                # Si solo una da señal, usar esa
                chosen_signal = None

                if swing_signal and position_signal:
                    # Ambas señales: elegir mayor score
                    if position_signal['score'] >= swing_signal['score']:
                        chosen_signal = position_signal
                        logger.info(f"📊 {symbol}: Position ({position_signal['score']}) > Swing ({swing_signal['score']})")
                    else:
                        chosen_signal = swing_signal
                        logger.info(f"📊 {symbol}: Swing ({swing_signal['score']}) > Position ({position_signal['score']})")
                elif swing_signal:
                    chosen_signal = swing_signal
                elif position_signal:
                    chosen_signal = position_signal

                if chosen_signal:
                    strat = chosen_signal.get('strategy', 'SWING')
                    logger.info(
                        f"🎯 [{strat}] {symbol} {chosen_signal['direction']} | "
                        f"Score: {chosen_signal['score']}/10 | R:R: 1:{chosen_signal['rr']}"
                    )

                    if self._open_position(symbol, chosen_signal):
                        self.last_signals[symbol] = datetime.utcnow()
                        signals_found += 1
                else:
                    logger.debug(f"   {symbol}: sin setup")

            except Exception as e:
                logger.error(f"Error con {symbol}: {e}", exc_info=True)

        if signals_found == 0:
            logger.info(f"   Sin nuevas oportunidades")
        else:
            logger.info(f"✅ Posiciones nuevas: {signals_found}")
    
    def _open_position(self, symbol: str, signal: dict) -> bool:
        """Abre una nueva posición con TP/SL en Binance"""
        try:
            entry = signal['entry']
            sl = signal['sl']
            tp1 = signal['tp1']
            tp2 = signal['tp2']
            
            # Calcular cantidad según riesgo
            quantity = self.exchange.calculate_position_size(symbol, entry, sl)
            
            if quantity <= 0:
                logger.warning(f"❌ Cantidad calculada inválida: {symbol}")
                return False
            
            # Verificar tamaño mínimo
            info = self.exchange.get_symbol_info(symbol)
            if info:
                notional = quantity * entry
                if notional < info.get('minNotional', 5.0):
                    logger.warning(f"❌ Notional muy pequeño: {symbol} ({notional:.2f})")
                    return False
            
            # ⚡ ABRIR POSICIÓN CON TP Y SL EN BINANCE
            orders = self.exchange.open_position_with_protection(
                symbol=symbol,
                direction=signal['direction'],
                entry=entry,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                quantity=quantity,
            )
            
            if not orders:
                logger.error(f"❌ No se pudo abrir posición: {symbol}")
                return False
            
            # Registrar posición
            position = Position(
                symbol=symbol,
                direction=signal['direction'],
                entry=entry,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                quantity=quantity,
                orders=orders,
                score=signal['score'],
            )
            self.position_manager.add_position(position)
            
            # Notificar
            self.telegram.send_position_opened(symbol, signal, quantity, orders)
            self.daily_stats['total_trades'] += 1
            
            return True
        
        except Exception as e:
            logger.error(f"Error abriendo {symbol}: {e}", exc_info=True)
            self.telegram.send_error(f"Error abriendo {symbol}: {str(e)[:200]}")
            return False
    
    def manage_positions(self):
        """Gestiona posiciones abiertas (break even, trailing)"""
        try:
            self.position_manager.manage_all_positions()
        except Exception as e:
            logger.error(f"Error gestionando posiciones: {e}")
    
    def send_daily_report(self):
        """Envía reporte diario"""
        try:
            stats = self.daily_stats.copy()
            stats['capital'] = self.exchange.get_account_balance()
            
            if stats['total_trades'] > 0:
                stats['win_rate'] = (stats['winners'] / stats['total_trades']) * 100
            
            self.telegram.send_daily_report(stats)
            
            # Reset
            self.daily_stats = {
                'total_trades': 0,
                'winners': 0,
                'losers': 0,
                'win_rate': 0.0,
                'daily_pnl': 0.0,
                'capital': stats['capital'],
            }
            self.position_manager.reset_daily()
        except Exception as e:
            logger.error(f"Error en reporte: {e}")
    
    def start(self):
        """Inicia el bot"""
        try:
            # Notificar inicio
            self.telegram.send_startup()
            
            # Programar reporte diario
            if cfg.ENABLE_DAILY_REPORT:
                self.scheduler.add_job(
                    self.send_daily_report,
                    'cron',
                    hour=cfg.DAILY_REPORT_HOUR_UTC,
                    minute=0
                )
            
            # Job de gestión de posiciones (cada 15s)
            self.scheduler.add_job(
                self.manage_positions,
                'interval',
                seconds=cfg.MANAGE_INTERVAL_SECONDS,
                next_run_time=datetime.utcnow()
            )
            
            self.scheduler.start()
            
            # Manejadores
            sys_signal.signal(sys_signal.SIGINT, self._stop_handler)
            sys_signal.signal(sys_signal.SIGTERM, self._stop_handler)
            
            logger.info("✅ Bot iniciado. Buscando oportunidades...")
            logger.info("=" * 60)
            
            # Loop principal: evaluar nuevos setups
            while self.running:
                try:
                    cycle_start = time.time()
                    self.evaluate_all_symbols()
                    
                    elapsed = time.time() - cycle_start
                    sleep_time = max(0, cfg.EVALUATE_INTERVAL_SECONDS - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                except KeyboardInterrupt:
                    self.running = False
                    break
                except Exception as e:
                    logger.error(f"Error en loop principal: {e}", exc_info=True)
                    try:
                        self.telegram.send_error(str(e)[:200])
                    except:
                        pass
                    time.sleep(cfg.RETRY_DELAY_SECONDS)
        
        except Exception as e:
            logger.error(f"Error fatal: {e}", exc_info=True)
        finally:
            self._cleanup()
    
    def _stop_handler(self, signum, frame):
        logger.info(f"🛑 Deteniendo bot...")
        self.running = False
    
    def _cleanup(self):
        logger.info("🧹 Limpiando...")
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
        except:
            pass
        logger.info("👋 Bot detenido")


def main():
    try:
        bot = FuturesBotV5()
        bot.start()
    except KeyboardInterrupt:
        logger.info("👋 Detenido por usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
