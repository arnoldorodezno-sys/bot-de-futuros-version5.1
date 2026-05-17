"""
═══════════════════════════════════════════════════════════════════
   ANALIZADOR SMC v3 - 4 FILTROS ESTRELLA
═══════════════════════════════════════════════════════════════════
   Mismo analizador que el bot de señales v3
═══════════════════════════════════════════════════════════════════
"""

import logging
import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple
import config as cfg

logger = logging.getLogger(__name__)


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calculate_adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    up_move = high.diff()
    down_move = -low.diff()
    
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
    
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    
    return adx, plus_di, minus_di


def analyze_trend_single(df: pd.DataFrame) -> Tuple[str, float]:
    try:
        ema_200 = calculate_ema(df['close'], cfg.EMA_TREND_PERIOD)
        ema_50 = calculate_ema(df['close'], cfg.EMA_SLOW_PERIOD)
        ema_21 = calculate_ema(df['close'], cfg.EMA_FAST_PERIOD)
        
        current = df['close'].iloc[-1]
        e200 = ema_200.iloc[-1]
        e50 = ema_50.iloc[-1]
        e21 = ema_21.iloc[-1]
        
        if current > e200:
            if e21 > e50 > e200:
                gap = (current - e200) / e200
                return ('BULLISH', 1.0 if gap > 0.05 else 0.85)
            elif e21 > e50:
                return ('BULLISH', 0.7)
            else:
                return ('BULLISH', 0.4)
        elif current < e200:
            if e21 < e50 < e200:
                gap = (e200 - current) / e200
                return ('BEARISH', 1.0 if gap > 0.05 else 0.85)
            elif e21 < e50:
                return ('BEARISH', 0.7)
            else:
                return ('BEARISH', 0.4)
        return ('NEUTRAL', 0.0)
    except Exception as e:
        logger.warning(f"Error analyze_trend_single: {e}")
        return ('NEUTRAL', 0.0)


def analyze_multi_tf_trend(df_macro, df_confirm, df_main) -> Tuple[Optional[str], float]:
    try:
        trend_macro, strength_macro = analyze_trend_single(df_macro)
        trend_confirm, strength_confirm = analyze_trend_single(df_confirm)
        trend_main, strength_main = analyze_trend_single(df_main)
        
        bullish_count = sum(1 for t in [trend_macro, trend_confirm, trend_main] if t == 'BULLISH')
        bearish_count = sum(1 for t in [trend_macro, trend_confirm, trend_main] if t == 'BEARISH')
        
        if bullish_count >= 2 and bearish_count == 0:
            direction = 'LONG'
            score = (strength_macro * 0.5 + strength_confirm * 0.3 + strength_main * 0.2)
            if bullish_count == 3:
                score = min(1.0, score * 1.1)
            return (direction, round(score, 2))
        elif bearish_count >= 2 and bullish_count == 0:
            direction = 'SHORT'
            score = (strength_macro * 0.5 + strength_confirm * 0.3 + strength_main * 0.2)
            if bearish_count == 3:
                score = min(1.0, score * 1.1)
            return (direction, round(score, 2))
        return (None, 0.0)
    except Exception as e:
        logger.warning(f"Error multi_tf_trend: {e}")
        return (None, 0.0)


def analyze_adx(df: pd.DataFrame, direction: str) -> float:
    try:
        adx, plus_di, minus_di = calculate_adx(df, cfg.ADX_PERIOD)
        current_adx = adx.iloc[-1]
        current_plus_di = plus_di.iloc[-1]
        current_minus_di = minus_di.iloc[-1]
        
        if pd.isna(current_adx):
            return 0.0
        
        if direction == 'LONG' and current_plus_di < current_minus_di:
            return 0.0
        if direction == 'SHORT' and current_minus_di < current_plus_di:
            return 0.0
        
        if current_adx >= 35:
            return 1.0
        elif current_adx >= 30:
            return 0.8
        elif current_adx >= 25:
            return 0.6
        elif current_adx >= cfg.ADX_MIN_THRESHOLD:
            return 0.4
        return 0.0
    except Exception as e:
        logger.warning(f"Error adx: {e}")
        return 0.0


def detect_bos(df: pd.DataFrame, direction: str) -> float:
    try:
        recent = df.tail(50)
        current_close = recent['close'].iloc[-1]
        
        if direction == 'LONG':
            prev_high = recent['high'].iloc[:-5].max()
            if current_close > prev_high:
                strength = (current_close - prev_high) / prev_high
                if strength > 0.01:
                    return 1.0
                elif strength > 0.005:
                    return 0.7
                else:
                    return 0.4
        elif direction == 'SHORT':
            prev_low = recent['low'].iloc[:-5].min()
            if current_close < prev_low:
                strength = (prev_low - current_close) / prev_low
                if strength > 0.01:
                    return 1.0
                elif strength > 0.005:
                    return 0.7
                else:
                    return 0.4
        return 0.0
    except:
        return 0.0


def detect_sweep(df: pd.DataFrame, direction: str) -> float:
    try:
        recent = df.tail(cfg.SWEEP_LOOKBACK)
        
        if direction == 'LONG':
            prev_low = recent['low'].iloc[:-3].min()
            recent_low = recent['low'].iloc[-3:].min()
            current_close = recent['close'].iloc[-1]
            
            if recent_low < prev_low and current_close > prev_low:
                penetration = (prev_low - recent_low) / prev_low
                recovery = (current_close - recent_low) / recent_low
                
                if penetration < 0.005 and recovery > 0.01:
                    return 1.0
                elif recovery > 0.005:
                    return 0.7
                else:
                    return 0.4
        elif direction == 'SHORT':
            prev_high = recent['high'].iloc[:-3].max()
            recent_high = recent['high'].iloc[-3:].max()
            current_close = recent['close'].iloc[-1]
            
            if recent_high > prev_high and current_close < prev_high:
                penetration = (recent_high - prev_high) / prev_high
                recovery = (recent_high - current_close) / recent_high
                
                if penetration < 0.005 and recovery > 0.01:
                    return 1.0
                elif recovery > 0.005:
                    return 0.7
                else:
                    return 0.4
        return 0.0
    except:
        return 0.0


def detect_order_block(df: pd.DataFrame, direction: str) -> float:
    """
    FIX #3 — SMC Estático eliminado.
    En lugar de revisar una ventana fija de 10 velas,
    detectamos pivotes REALES (máximos/mínimos locales confirmados).
    Un pivote real requiere al menos 2 velas a cada lado que lo validen.
    Esto evita que el bot confunda pausas laterales con OBs institucionales.
    """
    try:
        # Necesitamos al menos 30 velas para detectar pivotes confiables
        if len(df) < 30:
            return 0.0

        avg_volume = df['volume'].rolling(20).mean()
        best_quality = 0.0

        # Buscar pivotes en las últimas 50 velas (excluyendo las 3 más recientes)
        lookback = df.tail(50).reset_index(drop=True)
        n = len(lookback)

        for i in range(2, n - 3):  # mínimo 2 velas de contexto a cada lado
            h = lookback['high'].iloc[i]
            l = lookback['low'].iloc[i]
            o = lookback['open'].iloc[i]
            c = lookback['close'].iloc[i]
            v = lookback['volume'].iloc[i]

            # Promedio de volumen de los últimas 20 velas hasta este punto
            avg_v = avg_volume.iloc[-(n - i)] if not pd.isna(avg_volume.iloc[-(n - i)]) else v
            vol_ratio = v / avg_v if avg_v > 0 else 1.0

            body = abs(c - o)
            candle_range = h - l
            body_ratio = body / candle_range if candle_range > 0 else 0

            if direction == 'LONG':
                # OB alcista: vela bajista JUSTO ANTES de un mínimo pivote
                # El pivote es mínimo local si está rodeado de velas con lows más altos
                is_pivot_low = (
                    lookback['low'].iloc[i] < lookback['low'].iloc[i - 1] and
                    lookback['low'].iloc[i] < lookback['low'].iloc[i - 2] and
                    lookback['low'].iloc[i] < lookback['low'].iloc[i + 1] and
                    lookback['low'].iloc[i] < lookback['low'].iloc[i + 2]
                )
                is_bearish_candle = c < o  # Vela roja = zona institucional de acumulación

                if is_pivot_low and is_bearish_candle:
                    if vol_ratio > 2.0 and body_ratio > 0.6:
                        best_quality = max(best_quality, 1.0)
                    elif vol_ratio > 1.5 and body_ratio > 0.4:
                        best_quality = max(best_quality, 0.75)
                    elif vol_ratio > 1.2:
                        best_quality = max(best_quality, 0.5)

            elif direction == 'SHORT':
                # OB bajista: vela alcista JUSTO ANTES de un máximo pivote
                is_pivot_high = (
                    lookback['high'].iloc[i] > lookback['high'].iloc[i - 1] and
                    lookback['high'].iloc[i] > lookback['high'].iloc[i - 2] and
                    lookback['high'].iloc[i] > lookback['high'].iloc[i + 1] and
                    lookback['high'].iloc[i] > lookback['high'].iloc[i + 2]
                )
                is_bullish_candle = c > o  # Vela verde = zona institucional de distribución

                if is_pivot_high and is_bullish_candle:
                    if vol_ratio > 2.0 and body_ratio > 0.6:
                        best_quality = max(best_quality, 1.0)
                    elif vol_ratio > 1.5 and body_ratio > 0.4:
                        best_quality = max(best_quality, 0.75)
                    elif vol_ratio > 1.2:
                        best_quality = max(best_quality, 0.5)

        return best_quality
    except Exception as e:
        logger.warning(f"Error detect_order_block: {e}")
        return 0.0

def analyze_smc_confirmation(df: pd.DataFrame, direction: str) -> Tuple[float, list]:
    try:
        bos_score = detect_bos(df, direction)
        sweep_score = detect_sweep(df, direction)
        ob_score = detect_order_block(df, direction)
        
        smc_score = (bos_score * 0.4 + sweep_score * 0.3 + ob_score * 0.3)
        
        present = sum(1 for s in [bos_score, sweep_score, ob_score] if s >= 0.4)
        if present == 3:
            smc_score = min(1.0, smc_score * 1.15)
        
        confluences = []
        if bos_score >= 0.4:
            confluences.append('BOS')
        if sweep_score >= 0.4:
            confluences.append('SWEEP')
        if ob_score >= 0.4:
            confluences.append('OB')
        
        return (round(smc_score, 2), confluences)
    except:
        return (0.0, [])


def detect_engulfing(df: pd.DataFrame, direction: str) -> float:
    try:
        if len(df) < 2:
            return 0.0
        
        prev = df.iloc[-2]
        curr = df.iloc[-1]
        
        prev_body = abs(prev['close'] - prev['open'])
        curr_body = abs(curr['close'] - curr['open'])
        
        if direction == 'LONG':
            if (prev['close'] < prev['open'] and 
                curr['close'] > curr['open'] and
                curr['close'] > prev['open'] and
                curr['open'] < prev['close'] and
                curr_body > prev_body * 1.1):
                return 1.0
        elif direction == 'SHORT':
            if (prev['close'] > prev['open'] and
                curr['close'] < curr['open'] and
                curr['close'] < prev['open'] and
                curr['open'] > prev['close'] and
                curr_body > prev_body * 1.1):
                return 1.0
        return 0.0
    except:
        return 0.0


def analyze_rsi(df: pd.DataFrame, direction: str) -> float:
    try:
        rsi = calculate_rsi(df['close'], cfg.RSI_PERIOD)
        current_rsi = rsi.iloc[-1]
        
        if pd.isna(current_rsi):
            return 0.0
        
        if direction == 'LONG':
            low, high = cfg.RSI_LONG_OPTIMAL
            if low <= current_rsi <= high:
                return 1.0
            elif 30 <= current_rsi < low or high < current_rsi <= 60:
                return 0.7
            elif current_rsi < cfg.RSI_OVERBOUGHT:
                return 0.4
            return 0.0
        elif direction == 'SHORT':
            low, high = cfg.RSI_SHORT_OPTIMAL
            if low <= current_rsi <= high:
                return 1.0
            elif 60 < current_rsi <= 70 or 40 <= current_rsi < low:
                return 0.7
            elif current_rsi > cfg.RSI_OVERSOLD:
                return 0.4
            return 0.0
        return 0.0
    except:
        return 0.0


def analyze_volume(df: pd.DataFrame) -> float:
    try:
        volume_ma = df['volume'].rolling(window=cfg.VOLUME_MA_PERIOD).mean()
        current_volume = df['volume'].iloc[-1]
        avg_volume = volume_ma.iloc[-1]
        
        if pd.isna(avg_volume) or avg_volume == 0:
            return 0.0
        
        ratio = current_volume / avg_volume
        
        if ratio >= 2.5:
            return 1.0
        elif ratio >= 1.8:
            return 0.85
        elif ratio >= 1.4:
            return 0.7
        elif ratio >= 1.2:
            return 0.5
        elif ratio >= 1.0:
            return 0.3
        return 0.0
    except:
        return 0.0


def analyze_timing_momentum(df: pd.DataFrame, direction: str) -> Tuple[float, list]:
    try:
        rsi_score = analyze_rsi(df, direction)
        vol_score = analyze_volume(df)
        engulfing_score = detect_engulfing(df, direction)
        
        score = (rsi_score * 0.4 + vol_score * 0.4 + engulfing_score * 0.2)
        
        confluences = []
        if rsi_score >= 0.4:
            confluences.append('RSI')
        if vol_score >= 0.4:
            confluences.append('VOL')
        if engulfing_score >= 0.4:
            confluences.append('ENGULF')
        
        return (round(score, 2), confluences)
    except:
        return (0.0, [])


def analyze_symbol(df_macro, df_confirm, df_main) -> Optional[Dict]:
    """Análisis principal con 4 filtros estrella"""
    try:
        # FIX #1: Eliminar vela viva (no cerrada) — evita repainting
        df_main    = df_main.iloc[:-1].copy()
        df_confirm = df_confirm.iloc[:-1].copy()
        df_macro   = df_macro.iloc[:-1].copy()

        if len(df_main) < 50 or len(df_confirm) < 50 or len(df_macro) < 50:
            return None
        
        # FILTRO 1: Multi-TF Trend
        direction, trend_score = analyze_multi_tf_trend(df_macro, df_confirm, df_main)
        if direction is None or trend_score < 0.4:
            return None
        
        # FILTRO 2: ADX
        adx_score = analyze_adx(df_main, direction)
        if adx_score < 0.4:
            return None
        
        # FILTRO 3: SMC
        smc_score, smc_confluences = analyze_smc_confirmation(df_main, direction)
        
        # FILTRO 4: Timing
        timing_score, timing_confluences = analyze_timing_momentum(df_main, direction)
        
        # Score ponderado
        weighted_sum = (
            trend_score * cfg.WEIGHTS['multi_tf_trend'] +
            adx_score * cfg.WEIGHTS['adx_strength'] +
            smc_score * cfg.WEIGHTS['smc_confirmation'] +
            timing_score * cfg.WEIGHTS['timing_momentum']
        )
        total_weight = sum(cfg.WEIGHTS.values())
        score = (weighted_sum / total_weight) * 10
        
        if score < cfg.SCORE_MIN_TO_TRADE:
            return None
        
        # Calcular precios
        current_price = df_main['close'].iloc[-1]
        atr_value = calculate_atr(df_main, cfg.ATR_PERIOD).iloc[-1]
        
        if cfg.USE_ATR_SL:
            sl_distance = min(atr_value * cfg.ATR_SL_MULTIPLIER, current_price * cfg.MAX_SL_PCT)
        else:
            sl_distance = current_price * cfg.MAX_SL_PCT
        
        if direction == 'LONG':
            sl = current_price - sl_distance
            tp1 = current_price + (sl_distance * cfg.TP1_RR)
            tp2 = current_price + (sl_distance * cfg.TP2_RR)
        else:
            sl = current_price + sl_distance
            tp1 = current_price - (sl_distance * cfg.TP1_RR)
            tp2 = current_price - (sl_distance * cfg.TP2_RR)
        
        rr = abs(tp1 - current_price) / abs(current_price - sl)
        
        if rr < cfg.MIN_RR_TO_TRADE:
            return None
        
        confluences = ['MULTI-TF', 'ADX'] + smc_confluences + timing_confluences
        
        return {
            'direction': direction,
            'score': round(score, 1),
            'entry': current_price,
            'sl': sl,
            'tp1': tp1,
            'tp2': tp2,
            'rr': round(rr, 2),
            'sl_pct': round(abs(current_price - sl) / current_price * 100, 2),
            'tp1_pct': round(abs(tp1 - current_price) / current_price * 100, 2),
            'tp2_pct': round(abs(tp2 - current_price) / current_price * 100, 2),
            'confluences': confluences,
            'detail_scores': {
                'multi_tf_trend': round(trend_score, 2),
                'adx_strength': round(adx_score, 2),
                'smc_confirmation': round(smc_score, 2),
                'timing_momentum': round(timing_score, 2),
            },
        }
    except Exception as e:
        logger.error(f"Error analizando: {e}", exc_info=True)
        return None
