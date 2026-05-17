"""
═══════════════════════════════════════════════════════════════════
   BOT DE FUTUROS SMC v5 - CONFIGURACIÓN
═══════════════════════════════════════════════════════════════════
   
   Configurado para Arnoldo:
   - Capital: $600 USDT
   - Apalancamiento: 10x
   - Posiciones máx: 2
   - 24/7
   
═══════════════════════════════════════════════════════════════════
"""

# ═══════════════════════════════════════════════════════════════════
# MODO DE OPERACIÓN
# ═══════════════════════════════════════════════════════════════════
# ⚠️ CRÍTICO: Mantén estos valores para empezar SEGURO
# Solo cambia DRY_RUN=false cuando estés 100% seguro

TESTNET = False              # No usar testnet
DRY_RUN = False              # 🔴 LIVE TRADING — Opera con dinero real
PAPER_TRADING = False        # 🔴 LIVE TRADING — Opera con dinero real

# ═══════════════════════════════════════════════════════════════════
# CAPITAL Y RIESGO
# ═══════════════════════════════════════════════════════════════════
INITIAL_CAPITAL = 600               # Capital de prueba real
RISK_PER_TRADE_PCT = 0.015            # 1.5% por trade = $1.50
MAX_DAILY_DRAWDOWN_PCT = 0.05         # 5% pérdida máxima/día = $5
MAX_CONSECUTIVE_LOSSES = 3             # Cooldown después de 3 pérdidas

# ═══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE OPERACIONES
# ═══════════════════════════════════════════════════════════════════
LEVERAGE = 10                          # Apalancamiento 10x
MAX_CONCURRENT_POSITIONS = 2           # Máximo 2 trades abiertos
MARGIN_TYPE = "ISOLATED"               # ISOLATED (más seguro) o CROSSED

# ═══════════════════════════════════════════════════════════════════
# GESTIÓN DE TAKE PROFIT (Sistema escalonado)
# ═══════════════════════════════════════════════════════════════════
# TP1 al 1.5R (60% de la posición se cierra)
# TP2 al 3R (40% restante)
TP1_RR = 1.5
TP1_CLOSE_PCT = 0.60                   # Cierra 60% en TP1
TP2_RR = 3.0
TP2_CLOSE_PCT = 0.40                   # Cierra 40% en TP2

# ═══════════════════════════════════════════════════════════════════
# BREAK EVEN Y TRAILING STOP
# ═══════════════════════════════════════════════════════════════════
ENABLE_BREAK_EVEN = True               # Mueve SL a entrada cuando alcanza X R
BREAK_EVEN_TRIGGER_RR = 1.0            # A 1R, SL = entrada (+pequeño buffer)
BREAK_EVEN_BUFFER_PCT = 0.001          # 0.1% sobre entrada (cubre comisiones)

ENABLE_TRAILING_STOP = True            # Activa trailing stop
TRAILING_ACTIVATION_RR = 2.0           # Activa trailing en 2R
TRAILING_DISTANCE_PCT = 0.008          # 0.8% de distancia

# ═══════════════════════════════════════════════════════════════════
# STOP LOSS Y RIESGO
# ═══════════════════════════════════════════════════════════════════
MAX_SL_PCT = 0.015                     # Stop Loss máximo 1.5%
USE_ATR_SL = True                      # Usar ATR para SL dinámico
ATR_SL_MULTIPLIER = 1.5                # 1.5x ATR

# ═══════════════════════════════════════════════════════════════════
# SÍMBOLOS A OPERAR
# ═══════════════════════════════════════════════════════════════════
SYMBOLS = [
    # ═══ TIER 1: Mayor liquidez y volumen ═══
    "BTCUSDT",      # Bitcoin - El rey, tendencias más limpias
    "ETHUSDT",      # Ethereum - 2do mayor volumen
    "SOLUSDT",      # Solana - Alta volatilidad y liquidez
    "BNBUSDT",      # BNB - Muy líquido en Binance
    "XRPUSDT",      # XRP - Alto volumen en futuros

    # ═══ TIER 2: Alta liquidez y buenas tendencias ═══
    "DOGEUSDT",     # Dogecoin - Muy alto volumen
    "ADAUSDT",      # Cardano - Movimientos claros
    "AVAXUSDT",     # Avalanche - Tendencias SMC excelentes
    "LINKUSDT",     # Chainlink - Muy respetado en SMC
    "DOTUSDT",      # Polkadot - Buenos movimientos

    # ═══ TIER 3: Liquidez media, alta oportunidad ═══
    "NEARUSDT",     # NEAR Protocol - Tendencias claras
    "APTUSDT",      # Aptos - Alta volatilidad, buenas señales
    "ARBUSDT",      # Arbitrum - L2 con buen volumen
    "SUIUSDT",      # SUI - Nueva pero muy líquida
    "INJUSDT",      # Injective - Tendencias fuertes

    # ═══ TIER 4: Clásicos con buen volumen ═══
    "LTCUSDT",      # Litecoin - Clásico, movimientos predecibles
    "ATOMUSDT",     # Cosmos - Tendencias lentas pero confiables
    "AAVEUSDT",     # AAVE - DeFi, buenas tendencias
    "OPUSDT",       # Optimism - L2 activo
    "SEIUSDT",      # SEI - Alto potencial, buena liquidez
]

# ═══════════════════════════════════════════════════════════════════
# TIMEFRAMES
# ═══════════════════════════════════════════════════════════════════
TIMEFRAME_MACRO = "4h"
TIMEFRAME_CONFIRM = "1h"
TIMEFRAME_MAIN = "15m"

# ═══════════════════════════════════════════════════════════════════
# FILTROS DE CALIDAD (más estrictos para dinero real)
# ═══════════════════════════════════════════════════════════════════
SCORE_MIN_TO_TRADE = 7.0               # Score mínimo (más alto que señales)
MIN_RR_TO_TRADE = 2.0                  # R:R mínimo 1:2
ADX_MIN_THRESHOLD = 25                 # ADX más exigente

# ═══════════════════════════════════════════════════════════════════
# PESOS DE FILTROS
# ═══════════════════════════════════════════════════════════════════
WEIGHTS = {
    'multi_tf_trend': 3.0,
    'adx_strength': 2.0,
    'smc_confirmation': 3.0,
    'timing_momentum': 2.0,
}


# ═══════════════════════════════════════════════════════════════════
# POSITION TRADING — Parámetros separados
# ═══════════════════════════════════════════════════════════════════
ENABLE_POSITION_TRADING = True         # Activar segunda estrategia
TIMEFRAME_POSITION_MACRO = "1d"
TIMEFRAME_POSITION_CONFIRM = "4h"
POSITION_SCORE_MIN = 7.5
POSITION_MIN_RR = 3.0
POSITION_MAX_SL_PCT = 0.04
POSITION_TP1_RR = 2.0
POSITION_TP2_RR = 4.0
POSITION_TP1_CLOSE_PCT = 0.50
POSITION_TP2_CLOSE_PCT = 0.50
POSITION_RISK_PCT = 0.01
POSITION_COOLDOWN_HOURS = 48
POSITION_BREAK_EVEN_RR = 1.5
POSITION_TRAILING_ACTIVATION_RR = 2.5

# ═══════════════════════════════════════════════════════════════════
# FILTROS DE HORARIO (opcional)
# ═══════════════════════════════════════════════════════════════════
ENABLE_TIME_FILTER = False             # Desactivado por ahora (24/7)
ALLOWED_HOURS_UTC = list(range(0, 24)) # Si se activa, qué horas permitir

# Evitar horas de baja liquidez (cuando enable=True)
AVOID_HOURS_UTC = []                   # [22, 23, 0, 1] = evitar madrugada UTC

# ═══════════════════════════════════════════════════════════════════
# LOOPS Y TIMING
# ═══════════════════════════════════════════════════════════════════
EVALUATE_INTERVAL_SECONDS = 60         # Buscar nuevas operaciones cada 60s
MANAGE_INTERVAL_SECONDS = 15           # Gestionar posiciones cada 15s
SIGNAL_COOLDOWN_MINUTES = 120          # 2 horas entre trades del mismo símbolo

# ═══════════════════════════════════════════════════════════════════
# INDICADORES
# ═══════════════════════════════════════════════════════════════════
EMA_TREND_PERIOD = 200
EMA_FAST_PERIOD = 21
EMA_SLOW_PERIOD = 50
RSI_PERIOD = 14
ADX_PERIOD = 14
ATR_PERIOD = 14
VOLUME_MA_PERIOD = 20

# RSI zones
RSI_LONG_OPTIMAL = (40, 55)
RSI_SHORT_OPTIMAL = (45, 60)
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# Otros
CANDLES_LIMIT = 200
SWEEP_LOOKBACK = 20
OB_LOOKBACK = 10

# ═══════════════════════════════════════════════════════════════════
# REINTENTOS
# ═══════════════════════════════════════════════════════════════════
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
TELEGRAM_TIMEOUT = 30

# ═══════════════════════════════════════════════════════════════════
# LOGS Y MONITOREO
# ═══════════════════════════════════════════════════════════════════
LOG_LEVEL = "INFO"
ENABLE_DAILY_REPORT = True
DAILY_REPORT_HOUR_UTC = 0              # Reporte a las 00:00 UTC

# ═══════════════════════════════════════════════════════════════════
# COMISIONES (para cálculos precisos)
# ═══════════════════════════════════════════════════════════════════
TAKER_FEE = 0.0004                     # 0.04% (Binance futures taker)
MAKER_FEE = 0.0002                     # 0.02% (Binance futures maker)
