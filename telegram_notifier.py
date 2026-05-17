"""
═══════════════════════════════════════════════════════════════════
   TELEGRAM NOTIFIER - Bot de Futuros v5
═══════════════════════════════════════════════════════════════════
"""

import logging
import requests
import time
from datetime import datetime
import config as cfg

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.enabled = bool(bot_token and chat_id)
        
        if not self.enabled:
            logger.warning("⚠️ Telegram DESACTIVADO")
        else:
            logger.info("✅ Telegram ACTIVADO")
            self.test_connection()
    
    def test_connection(self) -> bool:
        try:
            test_url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
            response = requests.get(test_url, timeout=10)
            if response.status_code == 200:
                bot_info = response.json()
                if bot_info.get('ok'):
                    username = bot_info['result'].get('username')
                    logger.info(f"✅ Conectado a: @{username}")
                    return True
            return False
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def send_message(self, text: str) -> bool:
        if not self.enabled:
            return False
        
        for attempt in range(1, cfg.MAX_RETRIES + 1):
            try:
                response = requests.post(
                    self.api_url,
                    data={
                        'chat_id': self.chat_id,
                        'text': text,
                        'parse_mode': 'HTML',
                        'disable_web_page_preview': True,
                    },
                    timeout=cfg.TELEGRAM_TIMEOUT,
                )
                if response.status_code == 200 and response.json().get('ok'):
                    return True
            except Exception as e:
                logger.warning(f"Error Telegram (intento {attempt}): {e}")
                if attempt < cfg.MAX_RETRIES:
                    time.sleep(cfg.RETRY_DELAY_SECONDS)
        return False
    
    def send_startup(self):
        mode = "🔵 DRY_RUN (Simulado)" if cfg.DRY_RUN else "🔴 LIVE TRADING — DINERO REAL"
        text = (
            f"🚀 <b>Bot de Futuros v5 INICIADO</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Modo: {mode}\n"
            f"💰 Capital: ${cfg.INITIAL_CAPITAL}\n"
            f"📊 Leverage: {cfg.LEVERAGE}x\n"
            f"🎯 Risk/trade: {cfg.RISK_PER_TRADE_PCT*100}%\n"
            f"📈 Max posiciones: {cfg.MAX_CONCURRENT_POSITIONS}\n"
            f"⭐ Score mín: {cfg.SCORE_MIN_TO_TRADE}/10\n"
            f"📐 R:R mín: 1:{cfg.MIN_RR_TO_TRADE}\n"
            f"💪 ADX mín: {cfg.ADX_MIN_THRESHOLD}\n\n"
            f"<b>📋 4 Filtros Estrella:</b>\n"
            f"1️⃣ Tendencia Multi-Timeframe\n"
            f"2️⃣ Fuerza ADX\n"
            f"3️⃣ Confirmación SMC\n"
            f"4️⃣ Timing+Momentum\n\n"
            f"<b>⚙️ Características:</b>\n"
            f"✅ TP/SL reales en Binance\n"
            f"✅ Break Even automático\n"
            f"✅ Trailing Stop\n"
            f"✅ TP escalonado (60% + 40%)\n"
            f"✅ Stop por drawdown {cfg.MAX_DAILY_DRAWDOWN_PCT*100}%/día"
        )
        return self.send_message(text)
    
    def send_position_opened(self, symbol: str, signal: dict, quantity: float, orders: dict):
        direction = signal['direction']
        emoji = "🟢" if direction == 'LONG' else "🔴"
        strategy = signal.get('strategy', 'SWING')

        if direction == 'LONG':
            sl_sign, tp_sign = "-", "+"
        else:
            sl_sign, tp_sign = "+", "-"

        entry = signal['entry']
        if entry > 1000:
            fmt = ",.2f"
        elif entry > 1:
            fmt = ",.4f"
        else:
            fmt = ",.6f"

        position_value = quantity * entry
        notional = position_value * cfg.LEVERAGE

        # Etiqueta de estrategia
        if strategy == 'POSITION':
            strat_label = "📅 POSITION TRADE (1-4 semanas)"
            tp1_label = "TP1 (50%)"
            tp2_label = "TP2 (50%)"
        else:
            strat_label = "⚡ SWING TRADE (2-7 días)"
            tp1_label = "TP1 (60%)"
            tp2_label = "TP2 (40%)"

        details = signal.get('detail_scores', {})
        detail_lines = "\n".join(
            f"  {'📈' if k == 'daily_trend' or k == 'multi_tf_trend' else '💪' if 'adx' in k else '🎯' if 'smc' in k or 'sr' in k else '⏱️'} {k}: <b>{v}/1.0</b>"
            for k, v in details.items()
        )

        text = (
            f"{emoji} <b>POSICIÓN ABIERTA</b> — {strat_label}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>{direction}</b> | <b>{symbol}</b>\n"
            f"⭐ Score: {signal['score']}/10\n\n"
            f"💰 Entrada: <code>${entry:{fmt}}</code>\n"
            f"🛑 Stop Loss: <code>${signal['sl']:{fmt}}</code> ({sl_sign}{signal['sl_pct']}%)\n"
            f"🎯 {tp1_label}: <code>${signal['tp1']:{fmt}}</code> ({tp_sign}{signal['tp1_pct']}%)\n"
            f"🎯 {tp2_label}: <code>${signal['tp2']:{fmt}}</code> ({tp_sign}{signal['tp2_pct']}%)\n\n"
            f"📐 R:R → 1:{signal['rr']}\n"
            f"📊 Cantidad: {quantity} | 💵 ${position_value:.2f} | 💸 ${notional:.2f}\n\n"
            f"<b>🔍 Filtros:</b>\n{detail_lines}\n\n"
            f"🔗 {' + '.join(signal['confluences'])}"
        )
        return self.send_message(text)
    
    def send_break_even(self, position):
        emoji = "🟢" if position.direction == 'LONG' else "🔴"
        text = (
            f"⚡ <b>BREAK EVEN ACTIVADO</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} {position.direction} | {position.symbol}\n"
            f"🛑 SL movido a: <code>${position.current_sl:.4f}</code>\n\n"
            f"✅ Trade SIN RIESGO ahora"
        )
        return self.send_message(text)
    
    def send_position_closed(self, position, reason: str = "TP/SL"):
        emoji = "🟢" if position.direction == 'LONG' else "🔴"
        text = (
            f"🔚 <b>POSICIÓN CERRADA</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} {position.direction} | {position.symbol}\n"
            f"📊 Razón: {reason}\n"
            f"💰 Entrada: ${position.entry:.4f}\n"
            f"🛑 SL final: ${position.current_sl:.4f}\n"
            f"Score: {position.score}/10"
        )
        return self.send_message(text)
    
    def send_daily_report(self, stats: dict):
        text = (
            f"📅 <b>REPORTE DIARIO</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Trades: {stats['total_trades']}\n"
            f"✅ Ganadores: {stats['winners']}\n"
            f"❌ Perdedores: {stats['losers']}\n"
            f"🎯 Win Rate: {stats['win_rate']:.1f}%\n"
            f"💰 PnL día: ${stats['daily_pnl']:.2f}\n"
            f"💵 Capital: ${stats['capital']:.2f}"
        )
        return self.send_message(text)
    
    def send_error(self, error: str):
        text = (
            f"⚠️ <b>ERROR EN BOT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<code>{error[:300]}</code>"
        )
        return self.send_message(text)
    
    def send_warning(self, warning: str):
        text = (
            f"⚠️ <b>{warning}</b>"
        )
        return self.send_message(text)
