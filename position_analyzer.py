"""
═══════════════════════════════════════════════════════════════════
   POSITION ANALYZER - Estrategia Position Trading
═══════════════════════════════════════════════════════════════════
   
   Timeframes: 4h (macro) + 1D (tendencia principal)
   Objetivo:   Capturar movimientos de 1-4 semanas
   
   4 FILTROS ADAPTADOS PARA 1D:
   
   1. TENDENCIA 1D (peso: 4.0) — Más peso porque es el TF macro
      - EMA 200 en 1D es el filtro más importante
      - Las 3 EMAs deben estar perfectamente alineadas
      
   2. FUERZA ADX en 1D (peso: 2.5)
      - Umbral más bajo (20) porque 1D tiene menos ruido
      - ADX > 25 en 1D = tendencia muy fuerte
      
   3. SOPORTE/RESISTENCIA + SMC en 4h (peso: 2.0)
      - S/R en 1D para validar zona de entrada
      - BOS en 4h para confirmar momentum
      
   4. MOMENTUM SEMANAL (peso: 1.5)
      - RSI en 1D en zona óptima
      - Volumen semanal confirmado
      
   Total: 10 puntos máximo
═══════════════════════════════════════════════════════════════════
"""

import logging
import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple
import config as cfg

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# INDICADORES BASE
# ═══════════════════════════════════════════════════════════════════

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    h, l, c = df['high'], df['low'], df['close']
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr_val = tr.rolling(period).mean()
    up = h.diff()
    dn = -l.diff()
    plus_dm = up.where((up > dn) & (up > 0), 0)
    minus_dm = dn.where((dn > up) & (dn > 0), 0)
    plus_di = 100 * plus_dm.rolling(period).mean() / atr_val
    minus_di = 100 * minus_dm.rolling(period).mean() / atr_val
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.rolling(period).mean(), plus_di, minus_di


# ═══════════════════════════════════════════════════════════════════
# FILTRO 1: TENDENCIA 1D (peso: 4.0)
# ═══════════════════════════════════════════════════════════════════

def analyze_daily_trend(df_daily: pd.DataFrame, df_4h: pd.DataFrame) -> Tuple[Optional[str], float]:
    """
    Tendencia en 1D con confirmación en 4h.
    Score 1.0: EMAs perfectamente alineadas + precio lejos de EMA200
    Score 0.7: EMAs alineadas pero precio cerca de EMA200
    Score 0.4: Solo EMA200 respetada
    Score 0.0: Tendencia inválida o neutral
    """
    try:
        # Calcular EMAs en 1D
        e200_d = ema(df_daily['close'], 200)
        e50_d = ema(df_daily['close'], 50)
        e21_d = ema(df_daily['close'], 21)

        price_d = df_daily['close'].iloc[-1]
        e200_val = e200_d.iloc[-1]
        e50_val = e50_d.iloc[-1]
        e21_val = e21_d.iloc[-1]

        # Calcular EMAs en 4h para confirmación
        e200_4h = ema(df_4h['close'], 200)
        e50_4h = ema(df_4h['close'], 50)
        price_4h = df_4h['close'].iloc[-1]

        # Determinar dirección
        if price_d > e200_val:
            direction = 'LONG'
            # Alineación perfecta: precio > EMA21 > EMA50 > EMA200
            if e21_val > e50_val > e200_val:
                gap_pct = (price_d - e200_val) / e200_val
                # Bonus si 4h también confirma
                confirms_4h = price_4h > e200_4h.iloc[-1]
                base = 1.0 if gap_pct > 0.05 else 0.85
                score = min(1.0, base * (1.1 if confirms_4h else 1.0))
                return (direction, round(score, 2))
            elif e21_val > e50_val:
                return (direction, 0.65)
            elif price_d > e200_val:
                return (direction, 0.4)

        elif price_d < e200_val:
            direction = 'SHORT'
            if e21_val < e50_val < e200_val:
                gap_pct = (e200_val - price_d) / e200_val
                confirms_4h = price_4h < e200_4h.iloc[-1]
                base = 1.0 if gap_pct > 0.05 else 0.85
                score = min(1.0, base * (1.1 if confirms_4h else 1.0))
                return (direction, round(score, 2))
            elif e21_val < e50_val:
                return (direction, 0.65)
            elif price_d < e200_val:
                return (direction, 0.4)

        return (None, 0.0)

    except Exception as e:
        logger.warning(f"Error analyze_daily_trend: {e}")
        return (None, 0.0)


# ═══════════════════════════════════════════════════════════════════
# FILTRO 2: FUERZA ADX EN 1D (peso: 2.5)
# ═══════════════════════════════════════════════════════════════════

def analyze_daily_adx(df_daily: pd.DataFrame, direction: str) -> float:
    """
    ADX en 1D. Umbral más bajo que en swing porque 1D tiene menos ruido.
    Score 1.0: ADX > 30 con DI correctamente alineado
    Score 0.7: ADX > 22
    Score 0.4: ADX > 18 (mínimo absoluto)
    Score 0.0: ADX muy bajo o DI contradictorio
    """
    try:
        adx_val, plus_di, minus_di = adx(df_daily, 14)
        cur_adx = adx_val.iloc[-1]
        cur_plus = plus_di.iloc[-1]
        cur_minus = minus_di.iloc[-1]

        if pd.isna(cur_adx):
            return 0.0

        # Verificar coherencia de DI con dirección
        if direction == 'LONG' and cur_plus < cur_minus:
            return 0.0
        if direction == 'SHORT' and cur_minus < cur_plus:
            return 0.0

        if cur_adx >= 30:
            return 1.0
        elif cur_adx >= 25:
            return 0.85
        elif cur_adx >= 22:
            return 0.7
        elif cur_adx >= 18:
            return 0.4
        return 0.0

    except Exception as e:
        logger.warning(f"Error analyze_daily_adx: {e}")
        return 0.0


# ═══════════════════════════════════════════════════════════════════
# FILTRO 3: SOPORTE/RESISTENCIA + SMC en 4h (peso: 2.0)
# ═══════════════════════════════════════════════════════════════════

def find_key_levels(df_daily: pd.DataFrame, direction: str) -> float:
    """
    Detecta si el precio está cerca de un nivel S/R clave en 1D.
    Busca máximos/mínimos significativos de las últimas 20 velas diarias.
    """
    try:
        recent = df_daily.tail(30)
        current = df_daily['close'].iloc[-1]

        # Encontrar pivotes (máximos y mínimos locales)
        highs = []
        lows = []

        for i in range(2, len(recent) - 2):
            h = recent['high'].iloc[i]
            l = recent['low'].iloc[i]

            # Máximo local
            if h > recent['high'].iloc[i-1] and h > recent['high'].iloc[i+1]:
                highs.append(h)

            # Mínimo local
            if l < recent['low'].iloc[i-1] and l < recent['low'].iloc[i+1]:
                lows.append(l)

        if not highs and not lows:
            return 0.3  # Sin pivotes claros pero no 0

        # En LONG: buscar precio cerca de soporte (mínimo previo)
        if direction == 'LONG' and lows:
            nearest_support = min(lows, key=lambda x: abs(x - current))
            dist_pct = abs(current - nearest_support) / current
            if dist_pct <= 0.01:
                return 1.0   # Precio exactamente en soporte
            elif dist_pct <= 0.025:
                return 0.7   # Cerca del soporte
            elif dist_pct <= 0.05:
                return 0.4   # Relativamente cerca
            return 0.2

        # En SHORT: buscar precio cerca de resistencia (máximo previo)
        elif direction == 'SHORT' and highs:
            nearest_resistance = min(highs, key=lambda x: abs(x - current))
            dist_pct = abs(current - nearest_resistance) / current
            if dist_pct <= 0.01:
                return 1.0
            elif dist_pct <= 0.025:
                return 0.7
            elif dist_pct <= 0.05:
                return 0.4
            return 0.2

        return 0.3

    except Exception as e:
        logger.warning(f"Error find_key_levels: {e}")
        return 0.3


def analyze_bos_4h(df_4h: pd.DataFrame, direction: str) -> float:
    """BOS en 4h para confirmar momentum"""
    try:
        recent = df_4h.tail(50)
        current = recent['close'].iloc[-1]

        if direction == 'LONG':
            prev_high = recent['high'].iloc[:-5].max()
            if current > prev_high:
                strength = (current - prev_high) / prev_high
                return 1.0 if strength > 0.01 else 0.6
        elif direction == 'SHORT':
            prev_low = recent['low'].iloc[:-5].min()
            if current < prev_low:
                strength = (prev_low - current) / prev_low
                return 1.0 if strength > 0.01 else 0.6
        return 0.0

    except:
        return 0.0


def analyze_sr_and_smc(df_daily: pd.DataFrame, df_4h: pd.DataFrame, direction: str) -> Tuple[float, list]:
    """Combina S/R en 1D con BOS en 4h"""
    try:
        sr_score = find_key_levels(df_daily, direction)
        bos_score = analyze_bos_4h(df_4h, direction)

        # S/R tiene más peso (70%) que BOS (30%)
        combined = (sr_score * 0.7) + (bos_score * 0.3)

        confluences = []
        if sr_score >= 0.4:
            confluences.append('S/R')
        if bos_score >= 0.4:
            confluences.append('BOS-4h')

        return (round(combined, 2), confluences)

    except Exception as e:
        logger.warning(f"Error analyze_sr_and_smc: {e}")
        return (0.0, [])


# ═══════════════════════════════════════════════════════════════════
# FILTRO 4: MOMENTUM SEMANAL (peso: 1.5)
# ═══════════════════════════════════════════════════════════════════

def analyze_daily_rsi(df_daily: pd.DataFrame, direction: str) -> float:
    """
    RSI en 1D. Zonas óptimas diferentes al swing:
    LONG: RSI entre 45-60 (tendencia fuerte, no sobrecomprada)
    SHORT: RSI entre 40-55 (tendencia fuerte, no sobrevendida)
    """
    try:
        rsi_val = rsi(df_daily['close'], 14)
        cur_rsi = rsi_val.iloc[-1]

        if pd.isna(cur_rsi):
            return 0.0

        if direction == 'LONG':
            if 45 <= cur_rsi <= 60:
                return 1.0
            elif 35 <= cur_rsi < 45 or 60 < cur_rsi <= 70:
                return 0.7
            elif 30 <= cur_rsi < 35 or 70 < cur_rsi <= 80:
                return 0.4
            return 0.0

        elif direction == 'SHORT':
            if 40 <= cur_rsi <= 55:
                return 1.0
            elif 30 <= cur_rsi < 40 or 55 < cur_rsi <= 65:
                return 0.7
            elif 20 <= cur_rsi < 30 or 65 < cur_rsi <= 75:
                return 0.4
            return 0.0

        return 0.0

    except Exception as e:
        logger.warning(f"Error analyze_daily_rsi: {e}")
        return 0.0


def analyze_weekly_volume(df_daily: pd.DataFrame) -> float:
    """
    Volumen semanal: compara la semana actual vs las últimas 4 semanas.
    En position trading el volumen diario tiene más significado.
    """
    try:
        # Volumen de las últimas 5 velas vs promedio de 20 velas
        vol_ma = df_daily['volume'].rolling(20).mean()
        recent_vol = df_daily['volume'].tail(5).mean()
        avg_vol = vol_ma.iloc[-1]

        if pd.isna(avg_vol) or avg_vol == 0:
            return 0.3

        ratio = recent_vol / avg_vol

        if ratio >= 1.5:
            return 1.0
        elif ratio >= 1.2:
            return 0.7
        elif ratio >= 1.0:
            return 0.5
        else:
            return 0.2

    except Exception as e:
        logger.warning(f"Error analyze_weekly_volume: {e}")
        return 0.3


def analyze_weekly_momentum(df_daily: pd.DataFrame, direction: str) -> Tuple[float, list]:
    """Combina RSI en 1D + volumen semanal"""
    try:
        rsi_score = analyze_daily_rsi(df_daily, direction)
        vol_score = analyze_weekly_volume(df_daily)

        combined = (rsi_score * 0.6) + (vol_score * 0.4)

        confluences = []
        if rsi_score >= 0.4:
            confluences.append('RSI-1D')
        if vol_score >= 0.4:
            confluences.append('VOL-W')

        return (round(combined, 2), confluences)

    except Exception as e:
        logger.warning(f"Error analyze_weekly_momentum: {e}")
        return (0.0, [])


# ═══════════════════════════════════════════════════════════════════
# ANÁLISIS PRINCIPAL POSITION TRADING
# ═══════════════════════════════════════════════════════════════════

POSITION_WEIGHTS = {
    'daily_trend': 4.0,
    'daily_adx': 2.5,
    'sr_smc': 2.0,
    'weekly_momentum': 1.5,
}
POSITION_TOTAL_WEIGHT = sum(POSITION_WEIGHTS.values())


def analyze_position_trade(df_daily: pd.DataFrame, df_4h: pd.DataFrame) -> Optional[Dict]:
    """
    Analiza un símbolo para position trading (1D + 4h).
    
    Retorna señal o None si no hay setup válido.
    Las señales son más raras pero de mayor calidad.
    """
    try:
        # FIX #1: Eliminar vela viva — solo analizar velas confirmadas
        df_daily = df_daily.iloc[:-1].copy()
        df_4h    = df_4h.iloc[:-1].copy()

        if len(df_daily) < 50 or len(df_4h) < 50:
            return None

        # FILTRO 1: Tendencia 1D (filtro más importante)
        direction, trend_score = analyze_daily_trend(df_daily, df_4h)
        if direction is None or trend_score < 0.5:
            return None

        # FILTRO 2: ADX en 1D (filtro de calidad)
        adx_score = analyze_daily_adx(df_daily, direction)
        if adx_score < 0.4:
            # Mercado lateral en 1D → descartar
            return None

        # FILTRO 3: S/R + SMC en 4h
        sr_score, sr_confluences = analyze_sr_and_smc(df_daily, df_4h, direction)

        # FILTRO 4: Momentum semanal
        momentum_score, momentum_confluences = analyze_weekly_momentum(df_daily, direction)

        # Score ponderado
        weighted_sum = (
            trend_score * POSITION_WEIGHTS['daily_trend'] +
            adx_score * POSITION_WEIGHTS['daily_adx'] +
            sr_score * POSITION_WEIGHTS['sr_smc'] +
            momentum_score * POSITION_WEIGHTS['weekly_momentum']
        )
        score = (weighted_sum / POSITION_TOTAL_WEIGHT) * 10

        # Score mínimo más alto para position trading
        if score < cfg.POSITION_SCORE_MIN:
            return None

        # Calcular precios con ATR en 1D (stops más amplios)
        current_price = df_daily['close'].iloc[-1]
        atr_daily = atr(df_daily, 14).iloc[-1]

        # SL más amplio en position trading (1.5-2x ATR diario)
        sl_distance = min(atr_daily * 2.0, current_price * cfg.POSITION_MAX_SL_PCT)

        if direction == 'LONG':
            sl = current_price - sl_distance
            tp1 = current_price + (sl_distance * cfg.POSITION_TP1_RR)
            tp2 = current_price + (sl_distance * cfg.POSITION_TP2_RR)
        else:
            sl = current_price + sl_distance
            tp1 = current_price - (sl_distance * cfg.POSITION_TP1_RR)
            tp2 = current_price - (sl_distance * cfg.POSITION_TP2_RR)

        rr = abs(tp1 - current_price) / abs(current_price - sl)

        if rr < cfg.POSITION_MIN_RR:
            return None

        # Confluencias
        confluences = ['TEND-1D', 'ADX-1D'] + sr_confluences + momentum_confluences

        return {
            'strategy': 'POSITION',
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
                'daily_trend': round(trend_score, 2),
                'daily_adx': round(adx_score, 2),
                'sr_smc': round(sr_score, 2),
                'weekly_momentum': round(momentum_score, 2),
            },
        }

    except Exception as e:
        logger.error(f"Error analyze_position_trade: {e}", exc_info=True)
        return None
