"""
═══════════════════════════════════════════════════════════════════
   BACKTEST HISTÓRICO - Bot de Futuros SMC v5
═══════════════════════════════════════════════════════════════════
   
   Descarga datos históricos de Binance y simula el bot.
   
   CÓMO USAR:
   1. Asegúrate de tener el .env con BINANCE_API_KEY
   2. Ejecuta: python backtest.py
   3. Espera los resultados (puede tardar 5-10 minutos)
   4. Revisa el reporte generado
   
   El backtest simulará los últimos 90 días de cada símbolo
   y calculará cuánto habría ganado o perdido el bot.
═══════════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
from binance.client import Client
from dotenv import load_dotenv

load_dotenv()

# Importar config y analizador
import config as cfg
import analyzer

# Configurar logging para backtest
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Backtest")


# ═══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DEL BACKTEST
# ═══════════════════════════════════════════════════════════════════

BACKTEST_DAYS = 90                  # Días a simular (90 = 3 meses)
INITIAL_CAPITAL = 600.0             # Capital inicial
RISK_PER_TRADE = 0.015              # 1.5% riesgo por trade
LEVERAGE = 10                       # Apalancamiento
MAX_POSITIONS = 2                   # Posiciones máximas
TP1_RR = 1.5                       # R:R para TP1
TP2_RR = 3.0                       # R:R para TP2
TP1_CLOSE_PCT = 0.60               # 60% cierra en TP1
COMMISSION = 0.0004                 # 0.04% por lado (taker)
SLIPPAGE = 0.0002                   # 0.02% slippage estimado


class BacktestEngine:
    """Motor de backtest histórico"""
    
    def __init__(self):
        self.api_key = os.getenv('BINANCE_API_KEY', '').strip()
        self.api_secret = os.getenv('BINANCE_API_SECRET', '').strip()
        
        if not self.api_key:
            logger.error("❌ Necesitas BINANCE_API_KEY en .env")
            sys.exit(1)
        
        logger.info("🔌 Conectando a Binance...")
        self.client = Client(self.api_key, self.api_secret)
        
        # Estado del backtest
        self.capital = INITIAL_CAPITAL
        self.open_positions: Dict[str, dict] = {}
        self.trades: List[dict] = []
        self.equity_curve: List[float] = [INITIAL_CAPITAL]
        
        logger.info(f"✅ Conectado. Capital inicial: ${INITIAL_CAPITAL}")
    
    def get_historical_klines(self, symbol: str, interval: str, 
                               days: int = BACKTEST_DAYS) -> Optional[pd.DataFrame]:
        """Descarga velas históricas de Binance"""
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days + 10)  # Buffer
            
            start_str = start_time.strftime("%d %b %Y %H:%M:%S")
            
            klines = self.client.futures_historical_klines(
                symbol=symbol,
                interval=interval,
                start_str=start_str,
                limit=1000
            )
            
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
            df.set_index('timestamp', inplace=True)
            
            return df
        except Exception as e:
            logger.error(f"Error descargando {symbol} {interval}: {e}")
            return None
    
    def simulate_trade(self, entry: float, sl: float, tp1: float, tp2: float,
                       direction: str, future_prices: pd.DataFrame) -> dict:
        """Simula un trade en datos históricos"""
        
        tp1_hit = False
        tp2_hit = False
        sl_hit = False
        exit_price = entry
        exit_reason = "timeout"
        
        # Calcular tamaño de posición
        risk_amount = self.capital * RISK_PER_TRADE
        sl_distance = abs(entry - sl) / entry
        position_usdt = risk_amount / sl_distance
        quantity = position_usdt / entry
        
        # Simular vela por vela
        for _, candle in future_prices.iterrows():
            high = candle['high']
            low = candle['low']
            
            if direction == 'LONG':
                # ¿Se tocó SL?
                if low <= sl:
                    sl_hit = True
                    exit_price = sl * (1 - SLIPPAGE)  # Slippage negativo
                    exit_reason = "SL"
                    break
                
                # ¿Se tocó TP1?
                if not tp1_hit and high >= tp1:
                    tp1_hit = True
                    # Cierra 60% en TP1
                
                # ¿Se tocó TP2?
                if tp1_hit and high >= tp2:
                    tp2_hit = True
                    exit_price = tp2
                    exit_reason = "TP2"
                    break
                    
                # Si TP1 hit pero no TP2, exit en close
                if tp1_hit and _ == future_prices.index[-1]:
                    exit_price = candle['close']
                    exit_reason = "TP1+partial"
                    break
            
            elif direction == 'SHORT':
                # ¿Se tocó SL?
                if high >= sl:
                    sl_hit = True
                    exit_price = sl * (1 + SLIPPAGE)
                    exit_reason = "SL"
                    break
                
                # ¿Se tocó TP1?
                if not tp1_hit and low <= tp1:
                    tp1_hit = True
                
                # ¿Se tocó TP2?
                if tp1_hit and low <= tp2:
                    tp2_hit = True
                    exit_price = tp2
                    exit_reason = "TP2"
                    break
                
                if tp1_hit and _ == future_prices.index[-1]:
                    exit_price = candle['close']
                    exit_reason = "TP1+partial"
                    break
        
        # Si no cerró, cerrar al último precio
        if not sl_hit and not tp2_hit and exit_reason not in ["TP1+partial"]:
            exit_price = future_prices['close'].iloc[-1]
            exit_reason = "timeout"
        
        # Calcular PnL
        if direction == 'LONG':
            if sl_hit:
                pnl_pct = (exit_price - entry) / entry
                pnl_usdt = quantity * entry * pnl_pct * LEVERAGE
            elif tp2_hit:
                # TP1 portion + TP2 portion
                pnl_tp1 = quantity * TP1_CLOSE_PCT * (tp1 - entry) * LEVERAGE
                pnl_tp2 = quantity * (1 - TP1_CLOSE_PCT) * (tp2 - entry) * LEVERAGE
                pnl_usdt = pnl_tp1 + pnl_tp2
            elif exit_reason == "TP1+partial":
                pnl_tp1 = quantity * TP1_CLOSE_PCT * (tp1 - entry) * LEVERAGE
                pnl_rest = quantity * (1 - TP1_CLOSE_PCT) * (exit_price - entry) * LEVERAGE
                pnl_usdt = pnl_tp1 + pnl_rest
            else:
                pnl_pct = (exit_price - entry) / entry
                pnl_usdt = quantity * entry * pnl_pct * LEVERAGE
        
        else:  # SHORT
            if sl_hit:
                pnl_pct = (entry - exit_price) / entry
                pnl_usdt = quantity * entry * pnl_pct * LEVERAGE
            elif tp2_hit:
                pnl_tp1 = quantity * TP1_CLOSE_PCT * (entry - tp1) * LEVERAGE
                pnl_tp2 = quantity * (1 - TP1_CLOSE_PCT) * (entry - tp2) * LEVERAGE
                pnl_usdt = pnl_tp1 + pnl_tp2
            elif exit_reason == "TP1+partial":
                pnl_tp1 = quantity * TP1_CLOSE_PCT * (entry - tp1) * LEVERAGE
                pnl_rest = quantity * (1 - TP1_CLOSE_PCT) * (entry - exit_price) * LEVERAGE
                pnl_usdt = pnl_tp1 + pnl_rest
            else:
                pnl_pct = (entry - exit_price) / entry
                pnl_usdt = quantity * entry * pnl_pct * LEVERAGE
        
        # Restar comisiones (entrada + salida)
        commission_cost = quantity * entry * LEVERAGE * COMMISSION * 2
        net_pnl = pnl_usdt - commission_cost
        
        return {
            'direction': direction,
            'entry': entry,
            'exit': exit_price,
            'sl': sl,
            'tp1': tp1,
            'tp2': tp2,
            'tp1_hit': tp1_hit,
            'tp2_hit': tp2_hit,
            'sl_hit': sl_hit,
            'exit_reason': exit_reason,
            'pnl_usdt': round(net_pnl, 2),
            'commission': round(commission_cost, 2),
            'winner': net_pnl > 0,
        }
    
    def run_backtest(self, symbols: List[str] = None) -> dict:
        """Ejecuta el backtest completo"""
        if symbols is None:
            symbols = cfg.SYMBOLS
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 INICIANDO BACKTEST HISTÓRICO - {BACKTEST_DAYS} días")
        logger.info(f"{'='*60}")
        logger.info(f"💰 Capital: ${INITIAL_CAPITAL}")
        logger.info(f"📊 Leverage: {LEVERAGE}x")
        logger.info(f"🎯 Risk/trade: {RISK_PER_TRADE*100}%")
        logger.info(f"📈 Símbolos: {len(symbols)}")
        logger.info(f"{'='*60}\n")
        
        all_signals = []
        
        # Paso 1: Descargar datos y generar señales
        logger.info("📥 Descargando datos históricos...")
        
        for symbol in symbols:
            try:
                logger.info(f"   → {symbol}...")
                
                # Descargar 3 timeframes
                df_macro = self.get_historical_klines(symbol, "4h", BACKTEST_DAYS + 30)
                df_confirm = self.get_historical_klines(symbol, "1h", BACKTEST_DAYS + 30)
                df_main = self.get_historical_klines(symbol, "15m", BACKTEST_DAYS + 30)
                
                if df_macro is None or df_confirm is None or df_main is None:
                    logger.warning(f"   ⚠️ {symbol}: datos incompletos")
                    continue
                
                # Generar señales en ventana deslizante
                backtest_start = df_main.index[-1] - timedelta(days=BACKTEST_DAYS)
                backtest_candles = df_main[df_main.index >= backtest_start]
                
                # Analizar cada vela (simulando loop del bot)
                min_idx = 50  # Necesitamos al menos 50 velas de historia
                
                for i in range(min_idx, len(backtest_candles), 4):  # Cada 4 velas (1h)
                    try:
                        candle_time = backtest_candles.index[i]
                        
                        # Datos hasta esta vela
                        df_m_slice = df_main[df_main.index <= candle_time].tail(200)
                        df_c_slice = df_confirm[df_confirm.index <= candle_time].tail(200)
                        df_mac_slice = df_macro[df_macro.index <= candle_time].tail(200)
                        
                        if len(df_m_slice) < 50:
                            continue
                        
                        # Analizar con los 4 filtros
                        signal = analyzer.analyze_symbol(df_mac_slice, df_c_slice, df_m_slice)
                        
                        if signal:
                            # Datos futuros para simular el trade
                            future_data = df_main[df_main.index > candle_time].head(100)
                            
                            if len(future_data) < 5:
                                continue
                            
                            all_signals.append({
                                'symbol': symbol,
                                'time': candle_time,
                                'signal': signal,
                                'future_data': future_data,
                            })
                    
                    except Exception as e:
                        continue
                
                time.sleep(0.3)  # Rate limit
                
            except Exception as e:
                logger.error(f"Error con {symbol}: {e}")
                continue
        
        logger.info(f"\n✅ Señales generadas: {len(all_signals)}")
        
        # Paso 2: Simular trades
        logger.info("⚙️ Simulando trades...")
        
        # Ordenar señales por tiempo
        all_signals.sort(key=lambda x: x['time'])
        
        for sig_data in all_signals:
            try:
                signal = sig_data['signal']
                future_data = sig_data['future_data']
                
                # Simular el trade
                result = self.simulate_trade(
                    entry=signal['entry'],
                    sl=signal['sl'],
                    tp1=signal['tp1'],
                    tp2=signal['tp2'],
                    direction=signal['direction'],
                    future_prices=future_data,
                )
                
                # Registrar trade
                trade = {
                    'symbol': sig_data['symbol'],
                    'time': sig_data['time'].strftime('%Y-%m-%d %H:%M'),
                    'direction': signal['direction'],
                    'score': signal['score'],
                    **result,
                }
                
                self.trades.append(trade)
                self.capital += result['pnl_usdt']
                self.equity_curve.append(self.capital)
                
            except Exception as e:
                continue
        
        # Calcular métricas
        return self._calculate_metrics()
    
    def _calculate_metrics(self) -> dict:
        """Calcula todas las métricas del backtest"""
        if not self.trades:
            return {'error': 'Sin trades'}
        
        df = pd.DataFrame(self.trades)
        
        # Métricas básicas
        total_trades = len(df)
        winners = len(df[df['winner'] == True])
        losers = len(df[df['winner'] == False])
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
        
        # PnL
        total_pnl = df['pnl_usdt'].sum()
        avg_win = df[df['winner'] == True]['pnl_usdt'].mean() if winners > 0 else 0
        avg_loss = df[df['winner'] == False]['pnl_usdt'].mean() if losers > 0 else 0
        
        # Profit Factor
        gross_profit = df[df['pnl_usdt'] > 0]['pnl_usdt'].sum()
        gross_loss = abs(df[df['pnl_usdt'] < 0]['pnl_usdt'].sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        
        # Drawdown
        equity = pd.Series(self.equity_curve)
        rolling_max = equity.expanding().max()
        drawdowns = (equity - rolling_max) / rolling_max * 100
        max_drawdown = abs(drawdowns.min())
        
        # Return
        total_return = ((self.capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
        
        # Por razón de cierre
        exits = df['exit_reason'].value_counts()
        
        # Por símbolo
        by_symbol = df.groupby('symbol').agg({
            'pnl_usdt': 'sum',
            'winner': lambda x: (x.sum() / len(x)) * 100
        }).round(2)
        by_symbol.columns = ['pnl_total', 'win_rate']
        by_symbol = by_symbol.sort_values('pnl_total', ascending=False)
        
        # Por dirección
        by_direction = df.groupby('direction').agg({
            'pnl_usdt': ['sum', 'count'],
            'winner': lambda x: (x.sum() / len(x)) * 100
        })
        
        # Expectativa por trade
        expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)
        
        return {
            'summary': {
                'capital_inicial': INITIAL_CAPITAL,
                'capital_final': round(self.capital, 2),
                'ganancia_total': round(total_pnl, 2),
                'retorno_pct': round(total_return, 2),
                'dias_backtest': BACKTEST_DAYS,
            },
            'trades': {
                'total': total_trades,
                'ganadores': winners,
                'perdedores': losers,
                'win_rate': round(win_rate, 1),
                'razon_cierre': exits.to_dict(),
            },
            'riesgo': {
                'profit_factor': round(profit_factor, 2),
                'max_drawdown_pct': round(max_drawdown, 2),
                'expectativa_por_trade': round(expectancy, 2),
                'ganancia_promedio': round(avg_win, 2),
                'perdida_promedio': round(avg_loss, 2),
            },
            'por_simbolo': by_symbol.to_dict(),
            'raw_trades': df[['symbol', 'time', 'direction', 'score', 
                               'exit_reason', 'pnl_usdt', 'winner']].to_dict('records'),
        }


def print_report(results: dict):
    """Imprime el reporte del backtest"""
    
    print(f"\n{'═'*60}")
    print(f"   📊 REPORTE DE BACKTEST - BOT SMC v3")
    print(f"{'═'*60}")
    
    s = results['summary']
    t = results['trades']
    r = results['riesgo']
    
    print(f"\n💰 CAPITAL:")
    print(f"   Inicial:     ${s['capital_inicial']:.2f}")
    print(f"   Final:       ${s['capital_final']:.2f}")
    print(f"   Ganancia:    ${s['ganancia_total']:.2f}")
    print(f"   Retorno:     {s['retorno_pct']:.1f}% en {s['dias_backtest']} días")
    
    # Retorno anualizado
    daily_return = s['retorno_pct'] / s['dias_backtest']
    annual_return = daily_return * 365
    print(f"   Anualizado:  {annual_return:.1f}%")
    
    print(f"\n📈 TRADES:")
    print(f"   Total:       {t['total']}")
    print(f"   Ganadores:   {t['ganadores']} ({t['win_rate']}%)")
    print(f"   Perdedores:  {t['perdedores']}")
    print(f"\n   Razón de cierre:")
    for reason, count in t['razon_cierre'].items():
        print(f"   - {reason}: {count}")
    
    print(f"\n📊 RIESGO:")
    print(f"   Profit Factor:    {r['profit_factor']}")
    print(f"   Max Drawdown:     {r['max_drawdown_pct']:.1f}%")
    print(f"   Expectativa/trade: ${r['expectativa_por_trade']:.2f}")
    print(f"   Ganancia prom.:   ${r['ganancia_promedio']:.2f}")
    print(f"   Pérdida prom.:    ${r['perdida_promedio']:.2f}")
    
    print(f"\n🎯 INTERPRETACIÓN:")
    
    pf = r['profit_factor']
    wr = t['win_rate']
    dd = r['max_drawdown_pct']
    ret = s['retorno_pct']
    
    if pf >= 1.5 and wr >= 50 and dd <= 20:
        print(f"   ✅ BOT RENTABLE - Buena combinación de métricas")
        print(f"   ✅ Profit Factor {pf} es excelente (>1.5)")
        print(f"   ✅ Win Rate {wr}% es bueno (>50%)")
        if dd <= 10:
            print(f"   ✅ Drawdown {dd}% es bajo (muy bueno)")
        else:
            print(f"   ⚠️ Drawdown {dd}% es aceptable (<20%)")
    elif pf >= 1.2:
        print(f"   📊 BOT MODERADO - Rentable pero con margen de mejora")
        print(f"   ⚠️ Profit Factor {pf} es aceptable (>1.2 pero <1.5)")
        if wr < 50:
            print(f"   ⚠️ Win Rate {wr}% bajo, pero R:R puede compensar")
    else:
        print(f"   ❌ BOT NO RENTABLE - Ajusta los parámetros")
        print(f"   ❌ Profit Factor {pf} es muy bajo (<1.2)")
        print(f"   💡 Prueba aumentar SCORE_MIN_TO_TRADE")
        print(f"   💡 O aumentar MIN_RR_TO_TRADE")
    
    print(f"\n🏆 TOP 5 SÍMBOLOS MÁS RENTABLES:")
    pnl_dict = results['por_simbolo']['pnl_total']
    sorted_symbols = sorted(pnl_dict.items(), key=lambda x: x[1], reverse=True)
    for i, (sym, pnl) in enumerate(sorted_symbols[:5]):
        wr_sym = results['por_simbolo']['win_rate'].get(sym, 0)
        emoji = "✅" if pnl > 0 else "❌"
        print(f"   {i+1}. {sym}: ${pnl:.2f} ({wr_sym:.0f}% WR) {emoji}")
    
    print(f"\n💡 RECOMENDACIONES:")
    
    if ret > 15:
        print(f"   ✅ Retorno de {ret:.1f}% en {s['dias_backtest']} días es excelente")
        print(f"   ✅ Mantén la configuración actual")
    elif ret > 5:
        print(f"   📊 Retorno de {ret:.1f}% es moderado")
        print(f"   💡 Prueba subir SCORE_MIN_TO_TRADE a 7.5")
    else:
        print(f"   ⚠️ Retorno de {ret:.1f}% es bajo")
        print(f"   💡 Ajusta parámetros antes de operar real")
    
    print(f"\n{'═'*60}\n")


def save_results(results: dict):
    """Guarda resultados en archivos JSON y CSV"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Guardar JSON completo
    json_file = f"backtest_{timestamp}.json"
    with open(json_file, 'w') as f:
        # Convertir datos no serializables
        results_copy = {k: v for k, v in results.items() if k != 'raw_trades'}
        json.dump(results_copy, f, indent=2, default=str)
    logger.info(f"📄 Resultados guardados: {json_file}")
    
    # Guardar trades en CSV
    if 'raw_trades' in results:
        csv_file = f"trades_{timestamp}.csv"
        df = pd.DataFrame(results['raw_trades'])
        df.to_csv(csv_file, index=False)
        logger.info(f"📊 Trades guardados: {csv_file}")
    
    return json_file


def main():
    """Función principal del backtest"""
    print(f"\n{'═'*60}")
    print(f"   🤖 BACKTEST HISTÓRICO - BOT FUTUROS SMC v3")
    print(f"{'═'*60}")
    print(f"   Esto analizará {BACKTEST_DAYS} días de datos históricos")
    print(f"   Puede tardar 5-15 minutos dependiendo de los símbolos")
    print(f"{'═'*60}\n")
    
    # Confirmar
    print("¿Continuar? (s/n): ", end="")
    try:
        resp = input().strip().lower()
        if resp != 's':
            print("Cancelado.")
            return
    except EOFError:
        pass  # En Railway/CI no hay input
    
    start_time = time.time()
    
    try:
        engine = BacktestEngine()
        
        # Opción 1: Solo los 5 principales (más rápido)
        quick_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        
        # Opción 2: Todos los 20 (más completo)
        all_symbols = cfg.SYMBOLS
        
        # Preguntar qué backtest hacer
        print("\n¿Qué backtest hacer?")
        print("1. Rápido (5 símbolos, ~3 min)")
        print("2. Completo (20 símbolos, ~15 min)")
        print("Selecciona (1/2): ", end="")
        
        try:
            choice = input().strip()
        except EOFError:
            choice = "1"
        
        if choice == "2":
            symbols = all_symbols
            logger.info(f"Backtest COMPLETO con {len(symbols)} símbolos")
        else:
            symbols = quick_symbols
            logger.info(f"Backtest RÁPIDO con {len(symbols)} símbolos")
        
        # Ejecutar backtest
        results = engine.run_backtest(symbols)
        
        elapsed = time.time() - start_time
        logger.info(f"\n⏱️ Backtest completado en {elapsed/60:.1f} minutos")
        
        # Mostrar reporte
        print_report(results)
        
        # Guardar resultados
        json_file = save_results(results)
        
        print(f"\n✅ Backtest completado. Resultados guardados en {json_file}")
        
    except KeyboardInterrupt:
        print("\n⚠️ Backtest cancelado")
    except Exception as e:
        logger.error(f"❌ Error en backtest: {e}", exc_info=True)


if __name__ == "__main__":
    main()
