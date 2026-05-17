# 🤖 Bot de Futuros SMC v5

Bot profesional para trading automático en Binance Futures con análisis SMC.

## ⚡ Características v3

### 🎯 Análisis (4 Filtros Estrella):
1. **Tendencia Multi-Timeframe** (4h + 1h + 15m)
2. **Fuerza ADX** (filtra mercados laterales)
3. **Confirmación SMC** (BOS + Sweep + Order Block)
4. **Timing + Momentum** (RSI + Volumen + Engulfing)

### 💼 Gestión Profesional:
- ✅ **TP/SL REALES** en Binance (no en memoria)
- ✅ **TP escalonado**: 60% en TP1, 40% en TP2
- ✅ **Break Even** automático a 1R
- ✅ **Trailing Stop** desde 2R
- ✅ **Risk management**: 1.5% por trade
- ✅ **Max drawdown diario**: 5%
- ✅ **Cooldown post-pérdida**

## 🔧 Configuración (Arnoldo)

```python
INITIAL_CAPITAL = 600.0          # $600 USDT
LEVERAGE = 10                    # 10x
MAX_CONCURRENT_POSITIONS = 2     # 2 trades simultáneos
RISK_PER_TRADE_PCT = 0.015       # 1.5% riesgo/trade = $9
SCORE_MIN_TO_TRADE = 7.0         # Score alto (selectivo)
MIN_RR_TO_TRADE = 2.0            # R:R mínimo 1:2
```

## 🚦 Modos de Operación

### 🔵 MODO DRY_RUN (Recomendado para empezar)
```python
DRY_RUN = True
PAPER_TRADING = True
```
Simula todo, NO opera con dinero real.

### 🔴 MODO LIVE (Cuando estés listo)
```python
DRY_RUN = False
PAPER_TRADING = False
```
⚠️ Opera con DINERO REAL.

## 📊 Mensaje de Telegram al abrir trade

```
🟢 POSICIÓN ABIERTA
━━━━━━━━━━━━━━━━━━━━━
LONG | BTCUSDT
⭐ Score: 8.2/10

💰 Entrada: $62,450.00
🛑 Stop Loss: $61,800.00 (-1.04%)
🎯 TP1 (60%): $63,750.00 (+2.08%)
🎯 TP2 (40%): $65,050.00 (+4.16%)

📊 Cantidad: 0.014
💵 Posición: $874.30
💸 Notional: $8,743.00 (con leverage)
📐 R:R → 1:2.0

🔗 Confluencias: MULTI-TF + ADX + BOS + SWEEP + OB + RSI + VOL
```

## 🚀 Instalación

### Local (Windows):
1. Copiar `.env.example` a `.env`
2. Llenar credenciales
3. Doble clic en `iniciar_bot.bat`

### Railway (24/7):
1. Subir a GitHub
2. Conectar a Railway
3. Configurar variables en Railway
4. Deploy automático

## 📋 Variables de Entorno (Railway)

```
BINANCE_API_KEY=tu_api_key
BINANCE_API_SECRET=tu_api_secret
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_CHAT_ID=tu_chat_id
LOG_LEVEL=INFO
```

## ⚠️ Riesgos y Advertencias

- ⚠️ El trading con apalancamiento es **MUY RIESGOSO**
- ⚠️ Puedes perder todo tu capital
- ⚠️ Empieza con **DRY_RUN=true** por 2 semanas
- ⚠️ Comienza con cantidades pequeñas
- ⚠️ Este bot **NO garantiza ganancias**
- ⚠️ Es solo una herramienta de análisis técnico

## 🎯 Estrategia Recomendada

### Semana 1-2: DRY_RUN
- DRY_RUN=true, PAPER_TRADING=true
- Verificar que detecta señales correctas
- Verificar gestión de posiciones

### Semana 3-4: Live con poco capital
- DRY_RUN=false con $100-200
- Verificar que abre/cierra correctamente
- Ajustar si necesario

### Mes 2+: Capital completo
- Usar $600 si los resultados son positivos
- Mantener configuración estable
- Revisar resultados semanalmente

## 📈 Métricas a Monitorear

Después de 20-30 trades, calcula:
- **Win Rate** (debería ser > 50%)
- **Profit Factor** (debería ser > 1.5)
- **Drawdown máximo** (no mayor a 10%)
- **R múltiplos** (mantener R:R 1:2 o mejor)
