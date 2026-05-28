"""
Indexador RAG completo — Trading Bot Inteligente
Carga ~37 documentos ricos en ChromaDB con 5 colecciones especializadas.

Colecciones:
  - ftmo_rules          → reglas FTMO con casos límite y ejemplos numéricos
  - strategies          → las 3 estrategias con entradas, filtros y errores comunes
  - risk_management     → sizing, correlaciones, gestión de riesgo avanzada
  - market_context      → sesiones, pares, comportamiento por sesión y día
  - trading_psychology  → disciplina, reglas mentales que Claude aplica para filtrar

Ejecutar: python -m rag.indexer
"""

from loguru import logger
from rag.chroma_client import get_or_create_collection


# ════════════════════════════════════════════════════════════════════
# COLECCIÓN 1: FTMO RULES — 8 documentos
# ════════════════════════════════════════════════════════════════════

FTMO_RULES = [
    {
        "id": "ftmo_daily_drawdown",
        "text": """REGLA FTMO CRÍTICA — Drawdown Diario Máximo: 5%

Definición exacta: El drawdown diario se calcula desde el balance de INICIO DEL DÍA
(no desde el máximo histórico). Si el día empieza con $10,000, el máximo de pérdida
permitido es $500 en ese día.

Cálculo en tiempo real:
  balance_inicio_dia = balance al abrir la primera posición del día
  drawdown_actual = (balance_inicio_dia - equity_actual) / balance_inicio_dia * 100
  Si drawdown_actual >= 5.0% → STOP INMEDIATO (violación = pérdida de cuenta)

Política del sistema:
  - Alerta amarilla al 3.0% de drawdown diario
  - Alerta naranja al 4.0% (reducir tamaño de posiciones al 50%)
  - STOP automático al 4.5% (margen de seguridad de 0.5% antes del límite)
  - NUNCA alcanzar el 5.0% — es el límite de FTMO, no nuestro objetivo

Ejemplos concretos con cuenta $10,000:
  - $300 de pérdida → 3% → alerta amarilla, seguir operando normalmente
  - $400 de pérdida → 4% → alerta naranja, reducir tamaño
  - $450 de pérdida → 4.5% → STOP, no abrir más posiciones ese día
  - $500 de pérdida → 5.0% → VIOLACIÓN FTMO, pérdida de cuenta

Casos especiales:
  - Las posiciones flotantes cuentan: si tienes -$200 en drawdown realizado
    y una posición flotante de -$300, tu drawdown es -$500 = 5% = PELIGRO MÁXIMO
  - Los swaps overnight cuentan en el drawdown del día siguiente
  - El drawdown se mide en equity, no en balance (las pérdidas flotantes cuentan)""",
        "metadata": {"categoria": "ftmo", "tipo": "riesgo", "prioridad": "critica", "limite": "5pct_diario"}
    },

    {
        "id": "ftmo_total_drawdown",
        "text": """REGLA FTMO CRÍTICA — Drawdown Total Máximo: 10%

Definición exacta: El drawdown total se calcula desde el balance INICIAL de la cuenta
(el día 1), NO desde ningún máximo posterior. Con cuenta $10,000, el balance nunca
puede bajar de $9,000 en ningún momento.

Cálculo permanente:
  balance_inicial = $10,000 (fijo, nunca cambia)
  drawdown_total = (balance_inicial - equity_actual) / balance_inicial * 100
  Si drawdown_total >= 10% → cuenta CERRADA automáticamente por FTMO

Política del sistema:
  - Alerta al 6% de drawdown total → revisión de estrategia
  - Alerta crítica al 8% → solo operaciones de máxima confluencia (3/3)
  - STOP automático al 9% → no operar hasta consultar con el operador
  - 10% → pérdida de cuenta FTMO (irrecuperable)

Ejemplos concretos con cuenta $10,000:
  - Balance cae a $9,700 → 3% drawdown total → normal, seguir
  - Balance cae a $9,400 → 6% drawdown total → revisión, reducir riesgo
  - Balance cae a $9,200 → 8% drawdown total → solo señales 3/3
  - Balance cae a $9,100 → 9% drawdown total → STOP, consultar operador
  - Balance cae a $9,000 → 10% drawdown total → CUENTA CERRADA

Importante: el drawdown total es la suma acumulada de todas las pérdidas históricas,
incluyendo las posiciones actualmente abiertas. Una cuenta que ha ganado $500 y
luego pierde $1,100 tiene un drawdown total del 11% aunque haya llegado a $10,500.""",
        "metadata": {"categoria": "ftmo", "tipo": "riesgo", "prioridad": "critica", "limite": "10pct_total"}
    },

    {
        "id": "ftmo_challenge_rules",
        "text": """REGLA FTMO — Challenge Phase: Condiciones para Aprobar

Objetivo de beneficio: +10% sobre balance inicial
  Con cuenta $10,000 → necesitas llegar a $11,000 de balance
  Sin límite de tiempo desde 2024 (antes era 30 días)
  Mínimo 4 días de trading activo (días con al menos 1 operación cerrada)

Reglas adicionales del challenge:
  - Drawdown diario máximo: 5% (igual que cuenta fondeada)
  - Drawdown total máximo: 10% (igual que cuenta fondeada)
  - No hay límite de número de operaciones
  - Se permite trading de noticias (con cuidado extremo)
  - Se permite overnight y weekend si el par lo permite
  - No se permiten estrategias de martingala o grid con riesgo ilimitado

Métricas que FTMO analiza para aprobar (más allá del PnL):
  - Consistencia: no concentrar el 60%+ del PnL en un solo día
  - Drawdown controlado: nunca superar el 3% diario es señal de buena gestión
  - Diversificación: no operar siempre el mismo par
  - R:R positivo: mayoría de operaciones con R:R > 1.0

Estrategia recomendada para el challenge:
  1. Primeros 4-5 días: operar con tamaño normal (1% riesgo), objetivo +2-3% cada día
  2. Al llegar al 5-6%: reducir tamaño al 50%, proteger el progreso
  3. Al llegar al 8-9%: solo 1 operación al día, tamaño mínimo, buscar el +1% final
  4. NUNCA intentar recuperar pérdidas aumentando el tamaño

Escenario de fracaso más común: trader llega al 8% y en lugar de ir despacio,
aumenta el tamaño para terminar rápido → pierde el challenge por drawdown.""",
        "metadata": {"categoria": "ftmo", "tipo": "challenge", "prioridad": "alta"}
    },

    {
        "id": "ftmo_funded_account",
        "text": """REGLA FTMO — Cuenta Fondeada: Condiciones de Operación

Una vez aprobado el challenge y la verificación, se recibe la cuenta fondeada.

Diferencias principales con el challenge:
  - No hay objetivo de beneficio mensual obligatorio
  - Las mismas reglas de drawdown aplican (5% diario, 10% total)
  - El pago de beneficios es el último día hábil del mes (o bajo petición tras 14 días)
  - Split por defecto: 80% trader / 20% FTMO (puede subir a 90/10 con scaling)

Plan de scaling de FTMO:
  - Condición: +10% de beneficio en 4 meses con drawdown max 5% mensual
  - Resultado: aumento del 25% del tamaño de cuenta
  - Ejemplo: $10k → $12.5k → $15.6k → $19.5k (con 3 escaladas exitosas)

Reglas de preservación de cuenta fondeada:
  - No mantener posiciones en datos NFP (primer viernes de mes)
  - No mantener posiciones durante FOMC (4 veces al año)
  - Cerrar TODO antes del cierre del viernes (excepto metales con mercado 24h)
  - En caso de duda con noticias: cerrar antes, no después

Causa de pérdida de cuenta más frecuente en fondeo:
  - Drawdown diario en día de noticia inesperada (por eso el filtro macro es crítico)
  - Dejar posiciones abiertas el fin de semana con gap de apertura el lunes""",
        "metadata": {"categoria": "ftmo", "tipo": "funded", "prioridad": "alta"}
    },

    {
        "id": "ftmo_prohibited",
        "text": """REGLA FTMO — Prácticas Prohibidas

Las siguientes prácticas resultan en cancelación inmediata de la cuenta:

PROHIBIDO absolutamente:
  1. High-frequency trading (HFT): más de 200 operaciones/día
  2. Latency arbitrage: explotar diferencias de precio entre brokers
  3. Grid trading ilimitado: estrategias donde el riesgo crece sin límite
  4. Martingala: doblar el tamaño tras cada pérdida
  5. Copiar señales de cuentas FTMO propias (autoarbitraje entre cuentas)
  6. Operar durante mantenimiento del servidor del broker
  7. Usar EA que exploten bugs del servidor

ZONA GRIS (permitido pero monitorizado):
  - News trading: permitido si el riesgo es normal (no aumentar tamaño en noticias)
  - Overnight: permitido en mayoría de instrumentos
  - Weekend holding: permitido en metales (XAUUSD), prohibido en índices
  - Hedging: permitido en pares distintos, no en el mismo instrumento

Lo que NO es arbitraje prohibido:
  - Usar señales externas (TradingView, análisis propio, señales de terceros)
  - Operar múltiples pares al mismo tiempo con correlación normal
  - Cerrar y reabrir posiciones en el mismo día

El sistema debe asegurarse de NO usar estrategias grid ni martingala.
El tamaño de posición siempre es fijo por operación (1% del balance).""",
        "metadata": {"categoria": "ftmo", "tipo": "prohibido", "prioridad": "critica"}
    },

    {
        "id": "ftmo_instruments",
        "text": """REGLA FTMO — Instrumentos Permitidos y Condiciones

Instrumentos que operamos y sus especificaciones en FTMO:

XAUUSD (Oro):
  - Spread típico: 15-30 pips (0.15-0.30 USD)
  - Swap largo: aproximadamente -3.5 USD por lote por noche
  - Swap corto: aproximadamente +1.2 USD por lote por noche
  - Volatilidad diaria media: 150-200 pips (1.50-2.00 USD)
  - Mejor ventana: apertura NY (14:30-16:00 España)
  - Evitar: durante FOMC, NFP, y tensiones geopolíticas extremas

EURUSD:
  - Spread típico: 1-2 pips
  - Swap largo: aproximadamente -5.8 USD por lote por noche
  - Swap corto: aproximadamente +3.2 USD por lote por noche
  - Volatilidad diaria media: 60-90 pips
  - Mejor ventana: solapamiento Londres-NY (13:00-15:30 España)

GBPUSD:
  - Spread típico: 1.5-3 pips
  - Volatilidad diaria media: 80-120 pips
  - Mejor ventana: apertura Londres (08:00-10:00 España) y solapamiento

USDJPY:
  - Spread típico: 0.5-1.5 pips
  - Comportamiento: más tendencial, menos reversión a media
  - Mejor ventana: apertura Tokio (01:00-03:00 España) y NY

Tamaños de lote recomendados con cuenta $10,000 y 1% de riesgo ($100):
  - XAUUSD: 0.10 lotes para SL de 100 pips / 0.05 lotes para SL de 200 pips
  - EURUSD: 1.00 lote para SL de 10 pips / 0.50 lotes para SL de 20 pips
  - GBPUSD: 0.83 lotes para SL de 12 pips / 0.50 lotes para SL de 20 pips""",
        "metadata": {"categoria": "ftmo", "tipo": "instrumentos", "prioridad": "media"}
    },

    {
        "id": "ftmo_reporting",
        "text": """REGLA FTMO — Sistema de Reporting y Métricas

FTMO proporciona un dashboard con estas métricas en tiempo real:
  - Balance y equity actual
  - Drawdown diario actual y máximo histórico
  - Drawdown total actual
  - Beneficio/pérdida total
  - Número de días de trading
  - Historial completo de operaciones

Métricas que el sistema debe trackear internamente:
  1. PnL diario: suma de todas las operaciones cerradas hoy
  2. PnL acumulado del mes: para saber cuánto queda para el objetivo
  3. Drawdown máximo del día: para activar alertas preventivas
  4. Número de operaciones del día: máximo 3 por reglas propias
  5. Win rate semanal: mínimo 50% para considerar el sistema válido
  6. Profit factor semanal: ratio ganancia/pérdida, objetivo > 1.5
  7. Average RR realizado: objetivo > 1.5, alerta si cae por debajo de 1.0

El sistema debe enviar un reporte diario por Telegram al cierre de la sesión NY
(21:00 España / 15:00 NY) con todas estas métricas.""",
        "metadata": {"categoria": "ftmo", "tipo": "reporting", "prioridad": "media"}
    },

    {
        "id": "ftmo_emergency",
        "text": """PROCEDIMIENTO DE EMERGENCIA — Situaciones Críticas FTMO

ESCENARIO 1: Drawdown diario al 4%
  Acción: Cerrar todas las posiciones abiertas inmediatamente
  Acción: Enviar alerta URGENTE por Telegram al operador
  Acción: Bloquear apertura de nuevas posiciones por el resto del día
  No es necesario: cerrar el sistema, solo pausar el trading del día

ESCENARIO 2: Drawdown total al 8%
  Acción: Pausar el sistema completamente
  Acción: Notificar al operador con análisis de las pérdidas
  Acción: Solo reanudar con autorización explícita del operador
  Acción: Reducir riesgo por operación al 0.5% si se reanuda

ESCENARIO 3: Conexión MT5 perdida con posiciones abiertas
  Acción: Intentar reconectar 3 veces en 30 segundos
  Acción: Si no hay conexión, alertar URGENTE al operador
  Acción: El operador debe cerrar manualmente desde MT5
  Acción: Registrar el incidente en la base de datos

ESCENARIO 4: Error en la API de Claude durante análisis
  Acción: Usar análisis básico de reglas (sin IA) como fallback
  Acción: Solo aprobar señales con confluencia 3/3 en el fallback
  Acción: Notificar al operador que el análisis IA no está disponible

ESCENARIO 5: Noticia de alto impacto no detectada
  Acción: Si hay movimiento >50 pips en <5 minutos en XAUUSD → cerrar todo
  Acción: Si hay movimiento >30 pips en <5 minutos en EURUSD → cerrar todo
  Acción: Modo defensivo durante 30 minutos tras el movimiento extremo""",
        "metadata": {"categoria": "ftmo", "tipo": "emergencia", "prioridad": "critica"}
    },
]


# ════════════════════════════════════════════════════════════════════
# COLECCIÓN 2: STRATEGIES — 12 documentos
# ════════════════════════════════════════════════════════════════════

STRATEGY_DOCS = [
    {
        "id": "smc_fundamentals",
        "text": """ESTRATEGIA SMC — Fundamentos de Smart Money Concepts

Concepto central: Los grandes jugadores institucionales (bancos, hedge funds, market
makers) dejan huellas en el precio. SMC enseña a identificar esas huellas y operar
en la misma dirección que el dinero institucional.

Jerarquía de temporalidades (OBLIGATORIO respetar este orden):
  H4 → Contexto: ¿cuál es la tendencia mayor? ¿Dónde están los niveles clave?
  H1 → Setup: ¿hay BOS? ¿Dónde está el Order Block relevante?
  M15 → Entrada: ¿el precio ha llegado al OB/FVG? ¿Hay confirmación?
  M5 → Ajuste fino del SL (opcional, solo traders experimentados)

Por qué este orden es crítico:
  - Si en H4 el precio es bajista, NO operar largos en H1 aunque el setup sea perfecto
  - Si en H1 hay BOS alcista pero en H4 hay resistencia fuerte, reducir tamaño 50%
  - Una confluencia de temporalidades es más importante que cualquier indicador

Concepto de Market Structure:
  - HH (Higher High): cada máximo más alto que el anterior → tendencia alcista
  - HL (Higher Low): cada mínimo más alto que el anterior → tendencia alcista
  - LH (Lower High): cada máximo más bajo que el anterior → tendencia bajista
  - LL (Lower Low): cada mínimo más bajo que el anterior → tendencia bajista
  - BOS (Break of Structure): cuando el precio supera un HH o LL significativo
  - MSB (Market Structure Break): BOS con cierre de vela, más confirmación que BOS""",
        "metadata": {"categoria": "estrategia", "nombre": "SMC", "subtipo": "fundamentos"}
    },

    {
        "id": "smc_order_blocks",
        "text": """ESTRATEGIA SMC — Order Blocks: Identificación y Uso

Definición: Un Order Block (OB) es la última vela bajista antes de un movimiento
alcista fuerte (para OB alcista), o la última vela alcista antes de un movimiento
bajista fuerte (para OB bajista).

Identificación de OB alcista (para entradas LONG):
  1. Busca un movimiento alcista fuerte de 3+ velas que rompe estructura
  2. La vela inmediatamente anterior a ese movimiento es el OB
  3. El OB es la zona entre el open y close de esa vela bajista
  4. Si hay múltiples velas bajistas antes del movimiento, tomar la más reciente

Calidad del Order Block (escala 1-3):
  Alta calidad (3/3):
    - El movimiento posterior superó claramente la estructura anterior
    - El OB no ha sido tocado desde que se formó (virgen)
    - Está en alineación con la tendencia H4
  Calidad media (2/3):
    - El movimiento posterior fue moderado
    - El OB ha sido tocado pero no cerrado
    - Contexto neutral en H4
  Baja calidad (1/3): no operar, buscar otro setup

Entrada en OB:
  - Precio entra en la zona del OB (entre open y close de la vela OB)
  - Esperar vela de confirmación alcista (engulfing, martillo, pin bar)
  - Stop Loss: por debajo del mínimo del OB (con 5-10 pips de margen)
  - Take Profit: próximo nivel de resistencia o mínimo 1.5R

Invalidación del OB:
  - Si el precio CIERRA por debajo del OB → OB invalidado, no entrar
  - Un simple toque del mínimo no invalida el OB, solo el cierre por debajo""",
        "metadata": {"categoria": "estrategia", "nombre": "SMC", "subtipo": "order_blocks"}
    },

    {
        "id": "smc_fvg",
        "text": """ESTRATEGIA SMC — Fair Value Gaps: Identificación y Uso

Definición: Un Fair Value Gap (FVG) o imbalance es una zona de precio donde no hubo
trading real — el precio se movió tan rápido que dejó un hueco entre el máximo de
una vela y el mínimo de la siguiente (o viceversa).

Identificación de FVG alcista (para entradas LONG):
  Vela 1: cualquier vela
  Vela 2: vela alcista fuerte (el movimiento que crea el FVG)
  Vela 3: cualquier vela
  FVG = zona entre high de vela 1 y low de vela 3
  Condición: el high de vela 1 < low de vela 3 (hay un hueco real)

Calidad del FVG:
  - FVG grande (>20 pips en XAUUSD, >10 pips en EURUSD): alta calidad
  - FVG reciente (últimas 10-20 velas): alta calidad, más probable el fill
  - FVG en zona confluente (dentro de OB): máxima calidad
  - FVG antiguo (>50 velas): menor probabilidad, usar solo como soporte adicional

Comportamiento del precio ante FVG:
  - El precio tiende a "rellenar" los FVGs antes de continuar la tendencia
  - No todos los FVGs se rellenan: los más relevantes son los que están en tendencia
  - Un FVG se considera "filled" cuando el precio lo toca, no necesariamente lo cierra

Uso en la estrategia:
  - Si el precio retrocede a un FVG alcista y rebota → entrada LONG
  - Si el FVG coincide con un OB → confluencia de máxima calidad
  - SL: por debajo del FVG completo
  - TP: próximo nivel de resistencia""",
        "metadata": {"categoria": "estrategia", "nombre": "SMC", "subtipo": "fvg"}
    },

    {
        "id": "smc_entry_checklist",
        "text": """ESTRATEGIA SMC — Checklist de Entrada Completo

LONG setup — verificar en orden:

□ H4 CONTEXTO:
  ✓ Tendencia H4 alcista (HH + HL) o neutral
  ✗ NO operar si H4 es bajista con LH + LL claramente definidos

□ H1 ESTRUCTURA:
  ✓ BOS alcista confirmado en H1 (vela que CIERRA por encima del HH anterior)
  ✓ Identificado el OB relevante en H1 o H4
  ✗ NO operar si el último BOS fue bajista en H1

□ M15 ZONA DE ENTRADA:
  ✓ Precio retrocede al OB o FVG identificado
  ✓ FVG presente en M15 que refuerza la zona
  ✓ El precio no ha cerrado por debajo del OB (invalidaría el setup)

□ M15 CONFIRMACIÓN:
  ✓ Vela de reversión alcista: engulfing, martillo, pin bar, morning star
  ✓ El volumen en la vela de confirmación es mayor que las 3 velas anteriores
  ✓ RSI no está sobrecomprado (>70) en M15

□ GESTIÓN:
  ✓ SL: 5-10 pips por debajo del mínimo del OB
  ✓ TP: siguiente resistencia con mínimo 1.5R
  ✓ Tamaño: 1% del balance (o 0.5% si confluencia es 2/3)

SHORT setup — exactamente lo inverso de cada punto anterior.

Regla de oro: si tienes duda en CUALQUIER punto del checklist, NO operar.
Un setup impecable aparece 2-4 veces por semana. La paciencia es la estrategia.""",
        "metadata": {"categoria": "estrategia", "nombre": "SMC", "subtipo": "checklist"}
    },

    {
        "id": "smc_common_mistakes",
        "text": """ESTRATEGIA SMC — Errores Comunes y Cómo Evitarlos

Error 1: Operar contra la tendencia H4
  Situación: H4 bajista, pero en H1 hay un BOS alcista
  Tentación: parece un buen setup de reversión
  Realidad: en tendencia bajista fuerte, los BOS alcistas en H1 suelen ser trampas
  Solución: solo operar en dirección de H4. Excepción: si hay nivel mayor (semanal/mensual)

Error 2: Entrar sin esperar confirmación en M15
  Situación: precio llega al OB en M15 y entra sin vela de confirmación
  Realidad: el precio puede seguir bajando a través del OB
  Solución: esperar siempre el cierre de la vela de confirmación en M15

Error 3: Confundir OB con cualquier vela bajista
  Situación: tomar como OB velas bajistas que no preceden un BOS
  Realidad: el OB solo es válido si el movimiento posterior fue un BOS real
  Solución: primero identificar el BOS, luego buscar hacia atrás el OB que lo causó

Error 4: OB invalidado y seguir esperando entrada
  Situación: el precio cierra por debajo del OB pero el trader sigue esperando
  Realidad: un OB roto es una resistencia potencial, ya no es soporte
  Solución: si el precio cierra por debajo del OB, invalidar y buscar otro setup

Error 5: Ignorar la macro antes de entrar
  Situación: setup SMC perfecto pero hay CPI en 20 minutos
  Realidad: una noticia puede hacer saltar el SL en segundos
  Solución: siempre verificar el calendario económico antes de entrar

Error 6: SL demasiado ajustado
  Situación: poner SL en el mínimo exacto del OB sin margen
  Realidad: el precio suele testear el nivel exacto antes de rebotar
  Solución: SL siempre 5-10 pips por debajo del mínimo del OB""",
        "metadata": {"categoria": "estrategia", "nombre": "SMC", "subtipo": "errores"}
    },

    {
        "id": "orb_fundamentals",
        "text": """ESTRATEGIA ORB — Opening Range Breakout: Fundamentos

Concepto: La apertura de la sesión de Nueva York (9:30am ET / 14:30 España) crea
un rango de precios en los primeros 15-30 minutos. Este rango refleja el equilibrio
inicial entre compradores y vendedores. Cuando el precio rompe ese rango con convicción,
generalmente continúa en la dirección del breakout.

Por qué funciona en la apertura NY:
  - Es la sesión de mayor volumen del mundo (forex + equities + futuros)
  - Los grandes participantes (bancos, fondos) colocan sus órdenes en la apertura
  - El rango inicial refleja el "precio justo" según el consenso de apertura
  - Una ruptura indica que los compradores/vendedores han ganado el control

Timing exacto (horario España):
  Invierno (CET, GMT+1): 14:30 → apertura, 15:00 → rango definido
  Verano (CEST, GMT+2): 15:30 → apertura, 16:00 → rango definido

Definición del rango:
  - High del rango (ORB High): máximo de las primeras 30 velas de 1 minuto
  - Low del rango (ORB Low): mínimo de las primeras 30 velas de 1 minuto
  - Rango válido: entre 50-200 pips en XAUUSD, 10-50 pips en EURUSD
  - Si el rango es <50 pips en XAUUSD → mercado muy quieto, señal menos fiable
  - Si el rango es >300 pips en XAUUSD → volatilidad extrema, evitar ORB ese día

Ventana de validez: el breakout solo es válido en las primeras 2 horas de sesión.
  Invierno España: 14:30-16:30
  Verano España: 15:30-17:30
  Después de esas horas, el ORB pierde relevancia estadística.""",
        "metadata": {"categoria": "estrategia", "nombre": "ORB", "subtipo": "fundamentos"}
    },

    {
        "id": "orb_entry_rules",
        "text": """ESTRATEGIA ORB — Reglas de Entrada y Gestión

Condición de entrada LONG:
  1. Precio cierra por ENCIMA del ORB High en vela M15 (no solo toca, cierra)
  2. El breakout no es la primera vela (ideal: 2ª o 3ª vela tras el cierre del rango)
  3. El volumen en la vela de breakout es notablemente mayor que las anteriores
  4. Opcional: retest del ORB High antes de entrar (entrada más conservadora)

Condición de entrada SHORT:
  1. Precio cierra por DEBAJO del ORB Low en vela M15
  2. Resto de condiciones igual que el LONG

Gestión de la operación:
  Stop Loss: al otro lado del rango
    - Para LONG: SL = ORB Low - 5 pips (margen de seguridad)
    - Para SHORT: SL = ORB High + 5 pips
  
  Take Profit:
    - TP1 = tamaño del rango desde el punto de entrada (1R)
    - TP2 = 2× tamaño del rango desde el punto de entrada (2R)
    - Estrategia: cerrar 50% en TP1, mover SL a breakeven, dejar correr el 50% restante

Filtros adicionales:
  - Dirección de la tendencia diaria (D1): si el precio viene cayendo toda la semana,
    preferir breakouts SHORT sobre los LONG
  - Calendario macro: si hay datos a las 15:00-15:30 España, esperar a que pasen
  - No operar ORB los viernes: la liquidez cae a la tarde y los stops son frecuentes

Ejemplos de tamaños de lote con cuenta $10,000 y 1% de riesgo:
  XAUUSD con rango de 100 pips (SL = 105 pips):
    Lote = 100 / (105 × 10) = 0.095 ≈ 0.10 lotes
  EURUSD con rango de 25 pips (SL = 30 pips):
    Lote = 100 / (30 × 10) = 0.33 lotes""",
        "metadata": {"categoria": "estrategia", "nombre": "ORB", "subtipo": "entrada"}
    },

    {
        "id": "orb_context_filters",
        "text": """ESTRATEGIA ORB — Filtros de Contexto y Días a Evitar

Días con mejor rendimiento histórico para ORB:
  - Martes y miércoles: mayor volumen institucional, breakouts más limpios
  - Jueves: bueno en días con datos macro importantes
  - Lunes: volumen de apertura de semana, funciona bien tras fin de semana tranquilo

Días a evitar o reducir tamaño:
  - Lunes tras fin de semana con noticias geopolíticas importantes → volatilidad caótica
  - Viernes: liquidez cae a partir de las 16:00 España, los falsos breakouts aumentan
  - Día del FOMC (4 veces al año): mercado errático, no operar ORB
  - Día del NFP (primer viernes de mes): volatilidad extrema, ORB no funciona bien

Contexto macroeconómico favorable para ORB:
  - Días con datos de segundo nivel (confianza consumidor, ventas minoristas menores)
  - Días con discursos de Fed que no sean sobre política monetaria de emergencia
  - Semanas tranquilas sin grandes eventos programados

Contexto macroeconómico desfavorable:
  - CPI (inflación): falsos breakouts frecuentes, esperar 30 min tras el dato
  - NFP: extremadamente volátil, el rango inicial es no representativo
  - FOMC meetings: price action completamente diferente a lo normal

Filtro de gap de apertura:
  - Si XAUUSD abre con gap >50 pips respecto al cierre del día anterior:
    → el rango ORB puede ser distorsionado
    → reducir tamaño al 50% o no operar ORB ese día
    → usar SMC como estrategia alternativa""",
        "metadata": {"categoria": "estrategia", "nombre": "ORB", "subtipo": "filtros"}
    },

    {
        "id": "bbrsi_fundamentals",
        "text": """ESTRATEGIA BB+RSI — Bollinger Bands + RSI: Fundamentos

Concepto: Las Bollinger Bands miden la volatilidad relativa del precio. Cuando el
precio toca la banda exterior (±2 desviaciones estándar), estadísticamente el precio
está "lejos" de su media y tiene alta probabilidad de regresar hacia ella. El RSI
confirma si esa zona extrema coincide con una condición de sobrecompra/sobreventa.

Parámetros exactos del sistema:
  Bollinger Bands:
    - Longitud (período): 20 velas
    - Desviación estándar: 2.0
    - Fuente: close (precio de cierre)
  RSI:
    - Longitud: 14 velas
    - Zona de sobreventa para LONG: RSI < 35 (más conservador que el clásico 30)
    - Zona de sobrecompra para SHORT: RSI > 65 (más conservador que el clásico 70)

Por qué estos niveles de RSI (35/65 en lugar de 30/70):
  - En mercados tendenciales, el RSI puede quedarse en zona extrema mucho tiempo
  - Usar 35/65 da señales antes, pero requiere confirmación de vela obligatoria
  - Reduce el riesgo de entrar al final de una tendencia fuerte

Cuándo funciona mejor esta estrategia:
  - Mercados en rango (sin tendencia clara en H4): eficacia >70%
  - Pares con alta correlación a media móvil (EURUSD en horarios de baja volatilidad)
  - Después de un movimiento fuerte que ha "agotado" la tendencia temporal

Cuándo NO funciona y hay que evitarla:
  - Mercados en tendencia fuerte (H4 claramente alcista o bajista): el precio puede
    rebotar en la banda y seguir en la misma dirección
  - Durante noticias de alto impacto: las bandas se expanden y la señal pierde valor
  - XAUUSD en días de alta volatilidad (>300 pips de rango diario): evitar BB+RSI""",
        "metadata": {"categoria": "estrategia", "nombre": "BB_RSI", "subtipo": "fundamentos"}
    },

    {
        "id": "bbrsi_entry_rules",
        "text": """ESTRATEGIA BB+RSI — Reglas de Entrada y Confirmaciones

LONG setup (precio en zona de valor inferior):

Paso 1 — Identificar la zona:
  ✓ Precio toca o cruza la banda inferior de Bollinger en M15 o H1
  ✓ RSI en ese momento está por debajo de 35
  ✓ El contexto H4 no es bajista fuerte (no hay tendencia de LH+LL marcada)

Paso 2 — Esperar confirmación:
  ✓ Vela de reversión alcista confirmada en M15 o H1:
    - Martillo (Hammer): cuerpo pequeño arriba, sombra larga abajo (>2× el cuerpo)
    - Engulfing alcista: vela alcista que envuelve completamente la bajista anterior
    - Pin bar alcista: similar al martillo
    - Morning Star: patrón de 3 velas (bajista → doji → alcista)
  ✓ RSI ha girado hacia arriba (aunque sea solo 1-2 puntos)
  ✓ El precio ha cerrado DENTRO de las bandas (no sigue fuera)

Paso 3 — Gestión:
  SL: por debajo del mínimo de la vela de confirmación + 5 pips de margen
  TP1: banda media de Bollinger (media de 20 períodos) — primer objetivo
  TP2: banda superior de Bollinger — objetivo extendido (solo en contexto alcista H4)
  R:R mínimo: si TP1 (banda media) no da 1.5R, no operar

SHORT setup — exactamente inverso:
  - Precio toca banda superior + RSI > 65 + vela de reversión bajista
  - SL: por encima del máximo de la vela de confirmación + 5 pips
  - TP1: banda media. TP2: banda inferior.

Regla de salida anticipada:
  Si el precio llega a la banda media pero el RSI no ha vuelto a zona neutral (40-60),
  considerar cerrar el 100% (la reversión puede no tener fuerza suficiente).""",
        "metadata": {"categoria": "estrategia", "nombre": "BB_RSI", "subtipo": "entrada"}
    },

    {
        "id": "confluence_system",
        "text": """SISTEMA DE CONFLUENCIA — Las 3 Estrategias Combinadas

El sistema genera señal solo cuando 2 o 3 estrategias están alineadas en la misma
dirección en el mismo par. Una sola estrategia nunca es suficiente para operar.

Score de confluencia:
  3/3 → SEÑAL FUERTE: SMC + ORB + BB_RSI todas en la misma dirección
    → Tamaño: 1.0% del balance (cantidad normal)
    → Prioridad máxima, operar si el calendario lo permite
  
  2/3 → SEÑAL MODERADA: 2 de las 3 estrategias alineadas
    → Tamaño: 0.5% del balance (mitad)
    → Operar solo si las 2 estrategias activas son de alta calidad
  
  1/3 → NO OPERAR: solo 1 estrategia activa
    → Nunca operar con 1/3, sin excepciones, sin importar cuán bueno parezca el setup

Cómo calcular el score:
  1. SMC activo: BOS confirmado + OB o FVG identificado en la dirección de la señal
  2. ORB activo: dentro de la ventana horaria (primeras 2h de NY) + breakout confirmado
  3. BB_RSI activo: precio en banda exterior + RSI en zona extrema + vela confirmada

Nota importante sobre ORB:
  El ORB solo puede estar activo entre las 14:30-16:30 (invierno) o 15:30-17:30 (verano)
  España. Fuera de esa ventana, el score máximo posible es 2/3 (SMC + BB_RSI).
  Esto es normal y las señales 2/3 fuera del horario ORB son completamente válidas.

Dirección: TODAS las estrategias activas deben señalar la misma dirección.
  ✓ Válido: SMC LONG + BB_RSI LONG = 2/3 LONG
  ✗ Inválido: SMC LONG + ORB SHORT = contradicción, NO operar aunque sean 2/3""",
        "metadata": {"categoria": "estrategia", "nombre": "CONFLUENCIA", "subtipo": "sistema"}
    },

    {
        "id": "strategy_timing",
        "text": """VENTANAS HORARIAS — Cuándo Operar Cada Estrategia

Horarios en España (CET invierno / CEST verano):

08:00/09:00 — Apertura Londres:
  Estrategia primaria: SMC en H1
  Condiciones: mercado abriendo, Order Blocks de Asia relevantes
  Pares: GBPUSD (mejor), EURUSD (bueno), XAUUSD (moderado)
  Evitar: ORB (es apertura Londres, no NY), BB+RSI (volatilidad de apertura)

13:00/14:00 — Solapamiento Londres-NY:
  Estrategia primaria: SMC + ORB (preparación para apertura NY)
  Condiciones: máxima liquidez, movimientos institucionales frecuentes
  Pares: todos los pares del sistema
  Nota: vigilar el rango pre-apertura para el ORB de NY

14:30/15:30 — Apertura Nueva York (ventana PRIORITARIA):
  Estrategia primaria: ORB (primeros 30 min para definir rango) + SMC
  Confluencia máxima disponible: 3/3 (ORB + SMC + BB_RSI)
  Pares: XAUUSD (mejor para ORB), EURUSD (segundo)
  Esta es la ventana de mayor probabilidad del sistema

16:00-18:00/17:00-19:00 — Media sesión NY:
  Estrategia primaria: BB+RSI (consolidación post-apertura)
  Condiciones: el movimiento de apertura se ha completado, el mercado consolida
  El ORB ya no es válido (han pasado las 2 horas de ventana)
  Pares: cualquiera con volatilidad moderada

19:00/20:00 — Tarde NY:
  Estrategia primaria: SMC en H1/H4
  Condiciones: preparación para el cierre
  Pares: EURUSD (cierra bien la sesión), XAUUSD (continúa con liquidez)

Regla absoluta: el sistema NO procesa señales fuera de las ventanas activas.
Fuera de ventana → webhook descartado automáticamente → sin análisis → sin alerta.""",
        "metadata": {"categoria": "estrategia", "nombre": "TIMING", "subtipo": "horarios"}
    },
]


# ════════════════════════════════════════════════════════════════════
# COLECCIÓN 3: RISK MANAGEMENT — 7 documentos
# ════════════════════════════════════════════════════════════════════

RISK_DOCS = [
    {
        "id": "risk_position_sizing",
        "text": """GESTIÓN DE RIESGO — Cálculo de Tamaño de Posición

Fórmula base:
  riesgo_usd = balance × riesgo_pct / 100
  lote = riesgo_usd / (sl_pips × valor_pip_por_lote)

Valores de pip por lote estándar (lote = 100,000 unidades):
  EURUSD: $10 por pip por lote estándar ($1 por pip con mini lote 0.10)
  GBPUSD: $10 por pip por lote estándar
  USDJPY: ~$9.1 por pip por lote estándar (varía con el tipo de cambio)
  XAUUSD: $10 por pip por lote estándar (1 pip = $0.10 en precio del oro)
    Nota: en XAUUSD, 1 pip = 0.01 USD en precio, no 0.0001 como en Forex

Ejemplos completos con balance $10,000 y riesgo 1% ($100):

  XAUUSD, SL de 15 pips (1.50 USD en precio):
    lote = 100 / (15 × 10) = 100 / 150 = 0.67 lotes → usar 0.65 (redondear abajo)
  
  XAUUSD, SL de 50 pips:
    lote = 100 / (50 × 10) = 100 / 500 = 0.20 lotes
  
  EURUSD, SL de 20 pips:
    lote = 100 / (20 × 10) = 100 / 200 = 0.50 lotes
  
  EURUSD, SL de 35 pips:
    lote = 100 / (35 × 10) = 100 / 350 = 0.29 lotes → usar 0.28

Reglas de ajuste de tamaño:
  - Confluencia 3/3: usar 100% del lote calculado
  - Confluencia 2/3: usar 50% del lote calculado
  - Drawdown diario > 2%: reducir al 50% de lo normal
  - Drawdown total > 6%: reducir al 50% de lo normal
  - Ambos drawdowns elevados: reducir al 25% o no operar

Mínimos y máximos:
  - Tamaño mínimo de operación: 0.01 lotes (micro lote)
  - Tamaño máximo por operación: 2.00 lotes (con balance $10k, muy excepcional)
  - Nunca superar 2% de riesgo por operación bajo ninguna circunstancia""",
        "metadata": {"categoria": "riesgo", "subtipo": "sizing"}
    },

    {
        "id": "risk_rr_management",
        "text": """GESTIÓN DE RIESGO — Risk:Reward y Gestión de Operación Abierta

R:R mínimo para abrir operación: 1.5:1
  Esto significa que el Take Profit debe estar al menos 1.5× más lejos que el Stop Loss.
  Ejemplo: SL = 20 pips → TP mínimo = 30 pips
  Con R:R 1.5 y Win Rate 50% → el sistema es rentable a largo plazo

R:R objetivos por estrategia:
  SMC: objetivo R:R 2:1 o 3:1 (el OB al próximo nivel puede dar mucho recorrido)
  ORB: TP1 = 1R (tamaño del rango), TP2 = 2R (se busca R:R mínimo 1.5)
  BB+RSI: TP1 = banda media (R:R variable según el ancho de las bandas)

Gestión de la operación en curso (trailing y ajustes):

  Al llegar al 50% del TP (0.75R):
    → Mover SL a breakeven (precio de entrada)
    → Eliminar el riesgo de la operación

  Al llegar a TP1 (1R):
    → Cerrar 50% de la posición
    → SL del 50% restante: al precio de entrada (ya en breakeven)
    → Dejar correr el resto hacia TP2

  Al llegar a TP2 (2R o más):
    → Cerrar el 100% de la posición restante
    → Registrar resultado en base de datos

Reglas de salida anticipada:
  Cerrar si el precio toca la banda media (BB+RSI) sin alcanzar el TP
  Cerrar si aparece vela de reversión fuerte contra nuestra posición
  Cerrar 30 minutos antes de una noticia de alto impacto
  Cerrar al 4% de drawdown diario (regla FTMO)

Nunca hacer:
  - Mover el SL más lejos para "darle más espacio" (ampliación de riesgo)
  - Promediar pérdidas (añadir a una posición perdedora)
  - Cancelar el TP para "dejar correr más" sin un plan claro""",
        "metadata": {"categoria": "riesgo", "subtipo": "rr_management"}
    },

    {
        "id": "risk_correlation",
        "text": """GESTIÓN DE RIESGO — Correlación entre Pares y Riesgo Acumulado

Correlaciones importantes para el sistema:

Alta correlación positiva (movimiento similar):
  EURUSD ↔ GBPUSD: correlación ~0.80-0.90
    → Si tienes EURUSD LONG y GBPUSD LONG simultáneos, el riesgo real es ~2×
    → Nunca operar ambos al mismo tiempo con tamaño normal
    → Si vas a operar ambos: reducir cada uno al 50% del tamaño habitual

  XAUUSD ↔ EURUSD: correlación ~0.50-0.70 (variable)
    → En crisis del dólar, ambos suben. No son independientes.
    → Posiciones simultáneas en LONG: considerar riesgo acumulado

Alta correlación negativa (movimiento opuesto):
  EURUSD ↔ USDJPY: correlación ~-0.60 a -0.80
    → EURUSD LONG + USDJPY LONG son como operaciones opuestas al USD
    → Pueden coexistir con mejor diversificación que EUR+GBP

Regla del sistema para correlaciones:
  Máximo 2 posiciones abiertas simultáneamente
  Si las 2 posiciones son en pares con correlación >0.70: riesgo máximo = 1.5% total
  Si los pares tienen correlación <0.50: riesgo total puede ser 2% (1% cada uno)

Riesgo acumulado diario:
  El riesgo acumulado de todas las operaciones abiertas nunca debe superar el 3%
  Ejemplo: 3 operaciones abiertas a 1% cada una = 3% de riesgo acumulado = límite
  Con pérdidas ya realizadas de 1%: máximo 2% adicional en posiciones abiertas""",
        "metadata": {"categoria": "riesgo", "subtipo": "correlacion"}
    },

    {
        "id": "risk_daily_management",
        "text": """GESTIÓN DE RIESGO — Protocolo Diario de Operaciones

Inicio del día (antes de las 08:00 España):
  1. Verificar balance y estado de la cuenta en MT5
  2. Calcular el drawdown acumulado del mes (alertar si >5%)
  3. Revisar el calendario económico (Forex Factory) para el día
  4. Marcar las noticias de alto impacto (rojo) con sus horarios en España
  5. Determinar qué pares están "limpios" para operar (sin noticias en 2h)

Durante el día:
  6. Primera señal del día → verificar todas las condiciones + ejecutar si válida
  7. Tras primera operación: actualizar drawdown diario y P&L en curso
  8. Segunda señal: verificar que el drawdown diario permite más operaciones
  9. Tras segunda operación: si ya hay beneficio del 1%, evaluar si continuar
  10. Tercera señal: solo si el drawdown diario está por debajo del 2%

Reglas de parada del día:
  STOP si beneficio diario >= $500 (200% del objetivo diario) → bot en pausa
  STOP si pérdida diaria >= $200 (2% del balance) → bot en pausa
  STOP si drawdown diario >= 4.5% → EMERGENCIA, bot en pausa + alerta urgente
  STOP si se han cerrado 3 operaciones (ganadoras o perdedoras) → límite de operaciones

Cierre del día (21:00 España / cierre NY):
  11. Verificar que no hay posiciones abiertas (cerrar si las hay)
  12. Calcular P&L del día y enviarlo por Telegram
  13. Actualizar la base de datos con las operaciones del día
  14. Verificar métricas de la semana para el motor RL""",
        "metadata": {"categoria": "riesgo", "subtipo": "protocolo_diario"}
    },

    {
        "id": "risk_macro_filter",
        "text": """GESTIÓN DE RIESGO — Filtro Macroeconómico Detallado

Clasificación de noticias por impacto en nuestros pares:

IMPACTO CRÍTICO — No operar, cerrar posiciones abiertas si las hay:
  USD (afecta XAUUSD, EURUSD, GBPUSD, USDJPY):
    - NFP (Non-Farm Payrolls): primer viernes de cada mes, 14:30 España (invierno)
    - CPI (Consumer Price Index): mensual, generalmente martes 14:30 España
    - FOMC Decision: 8 veces al año, miércoles 20:00 España
    - FOMC Meeting Minutes: 3 semanas después de cada reunión
    - Fed Chair Press Conference: tras las decisiones de tipos

  EUR (afecta EURUSD directamente):
    - BCE Decision on interest rates: 6 veces al año, 14:15 España
    - Lagarde Press Conference: 45 min después de la decisión BCE

IMPACTO ALTO — Reducir tamaño al 50%, evitar entrar 15 min antes/después:
  USD: Retail Sales, PPI, GDP primera estimación, ISM Manufacturing
  EUR: Flash CPI, German IFO, ZEW Economic Sentiment
  GBP: BOE Decision, UK CPI, UK GDP
  JPY: BOJ Decision, Japan CPI

IMPACTO MEDIO — Vigilar pero no cambiar estrategia:
  USD: Jobless Claims (semanal, jueves 14:30 España)
  EUR: Eurozone PMI
  Discursos de miembros de la Fed (no el chairman)

Reglas de ventana temporal:
  - 30 minutos antes de noticia crítica → NO abrir nuevas posiciones
  - 15 minutos antes de noticia alta → NO abrir nuevas posiciones
  - 15 minutos después de cualquier noticia de impacto → esperar la volatilidad
  - Si hay noticia en los próximos 30 min y tienes posición abierta:
    Evaluar si cerrar en beneficio o poner SL en breakeven""",
        "metadata": {"categoria": "riesgo", "subtipo": "macro_filter"}
    },

    {
        "id": "risk_performance_metrics",
        "text": """GESTIÓN DE RIESGO — Métricas de Rendimiento y Evaluación

Métricas semanales que el sistema debe calcular:

Win Rate (tasa de acierto):
  win_rate = operaciones_ganadoras / total_operaciones × 100
  Objetivo: > 50%
  Alarma: si cae por debajo del 40% en 2 semanas consecutivas → revisar estrategia

Profit Factor:
  profit_factor = suma_ganancias_brutas / suma_pérdidas_brutas
  Objetivo: > 1.5
  Aceptable: > 1.2
  Alarma: si cae por debajo de 1.0 → el sistema está perdiendo dinero en neto

Average R:R Realizado:
  rr_realizado = ganancia_media_por_op / pérdida_media_por_op
  Objetivo: > 1.5
  Alarma: si cae por debajo de 1.0 → los TP están mal calibrados

Sharpe Ratio (mensual):
  sharpe = (retorno_medio_diario - 0) / desviación_estándar_retornos_diarios
  Objetivo: > 1.5
  Interpretación: mide rentabilidad ajustada por riesgo

Calmar Ratio:
  calmar = retorno_anualizado / max_drawdown
  Objetivo: > 2.0
  Mide cuánto se gana por cada unidad de drawdown máximo

Evaluación por estrategia:
  El motor RL debe trackear el win rate y profit factor de CADA estrategia por separado:
  - Win rate SMC separado de ORB separado de BB+RSI
  - Si una estrategia tiene win rate <40% por 3 semanas → peso reducido en confluencia
  - Si una estrategia tiene win rate >65% → considerar operar con 1/3 en ese contexto""",
        "metadata": {"categoria": "riesgo", "subtipo": "metricas"}
    },

    {
        "id": "risk_drawdown_recovery",
        "text": """GESTIÓN DE RIESGO — Recuperación tras Drawdown

El drawdown es inevitable. El problema no es tener drawdown — es cómo reaccionar a él.

Respuestas incorrectas al drawdown (aumentan el problema):
  ✗ Aumentar el tamaño para recuperar más rápido (lo más peligroso)
  ✗ Operar más operaciones al día (más exposición = más riesgo)
  ✗ Bajar el R:R mínimo para "tener más probabilidad" de ganar
  ✗ Cambiar de estrategia a mitad de un drawdown

Respuesta correcta al drawdown (protocolo del sistema):

Drawdown diario 2-3%:
  → Continuar operando normalmente, es parte del plan
  → No cambiar nada, el sistema tiene drawdowns de hasta 3% que son normales

Drawdown diario 3-4%:
  → Reducir tamaño al 50% para las siguientes operaciones del día
  → Máximo 1 operación más si el setup es 3/3

Drawdown diario >4%:
  → STOP. No operar más en el día. Mañana empezamos de nuevo.

Drawdown total 5-7%:
  → Reducir tamaño al 75% de lo normal
  → Solo señales con confluencia 3/3
  → Revisar si hay error sistemático en el sistema

Drawdown total 7-9%:
  → Reducir tamaño al 50% de lo normal
  → Solo 1 operación al día con confluencia 3/3
  → Alerta al operador para revisión manual del sistema

Tiempo de recuperación matemático:
  Con R:R 1.5 y win rate 55%, un drawdown del 5% se recupera estadísticamente
  en 6-8 operaciones rentables. Con riesgo reducido al 50%, puede tardar el doble
  pero el riesgo de llegar al 10% es mucho menor.""",
        "metadata": {"categoria": "riesgo", "subtipo": "recuperacion"}
    },
]


# ════════════════════════════════════════════════════════════════════
# COLECCIÓN 4: MARKET CONTEXT — 6 documentos
# ════════════════════════════════════════════════════════════════════

MARKET_CONTEXT_DOCS = [
    {
        "id": "market_xauusd",
        "text": """CONTEXTO DE MERCADO — XAUUSD (Oro) Comportamiento Detallado

Características específicas de XAUUSD:
  - El oro es un activo de refugio: sube en incertidumbre geopolítica, crisis bancarias,
    inflación elevada y debilidad del dólar
  - Correlación negativa con el USD: cuando el DXY (Dollar Index) sube, el oro cae
  - Correlación positiva con los bonos: cuando los bonos suben (yields bajan), el oro sube
  - Sesión de mayor volatilidad: apertura NY (14:30 España) y solapamiento NY/Londres

Comportamiento por sesión:
  Asia (01:00-08:00 España):
    Movimiento medio: 30-60 pips, rango estrecho
    Suele establecer el rango de la noche que sirve de referencia para Europa
    Liquidez baja → posibles falsas rupturas de niveles

  Londres (08:00-13:00 España):
    Movimiento medio: 60-100 pips
    Frecuentemente establece el mínimo o máximo del día
    Los Order Blocks de la sesión asiática son targets frecuentes

  Nueva York (13:00-21:00 España):
    Movimiento medio: 100-200 pips
    La apertura (14:30) es el momento de mayor volatilidad
    El solapamiento Londres-NY (13:00-15:00) es el momento con más volumen

Niveles de soporte/resistencia relevantes para XAUUSD:
  - Cifras redondas (2300, 2350, 2400, etc.): imanes de precio, cuidado con SL cerca
  - Previous Day High/Low: niveles muy respetados por el mercado institucional
  - Semanal High/Low: niveles de reversión importantes para operaciones swing

Correlaciones a monitorizar diariamente:
  Si DXY (Dollar Index) baja → sesgo alcista XAUUSD
  Si DXY sube → sesgo bajista XAUUSD
  Si hay tensión geopolítica → gold spike, usar ORB con precaución extra""",
        "metadata": {"categoria": "mercado", "par": "XAUUSD", "subtipo": "comportamiento"}
    },

    {
        "id": "market_eurusd",
        "text": """CONTEXTO DE MERCADO — EURUSD Comportamiento Detallado

Características de EURUSD:
  - El par más líquido del mundo (>25% del volumen Forex diario global)
  - Menor spread, menor volatilidad relativa que XAUUSD
  - Muy sensible a diferenciales de tipos BCE vs Fed
  - Comportamiento más predecible en tendencias que el oro

Comportamiento por sesión:
  Asia (01:00-08:00 España):
    Movimiento mínimo: 15-25 pips típicamente
    Rango estrecho, útil para identificar niveles para la apertura de Londres

  Londres (08:00-13:00 España):
    Establecimiento de tendencia del día
    El primer impulso de Londres suele indicar la dirección del día
    SMC funciona muy bien en esta sesión con Order Blocks de Asia

  Nueva York (13:00-21:00 España):
    El solapamiento 13:00-15:00 es el mejor momento para EURUSD
    Después de las 17:00 la volatilidad cae notablemente
    ORB en EURUSD funciona bien en días con datos USD

Niveles clave para EURUSD:
  - 1.0000 (paridad): nivel psicológico extremo
  - Niveles del 00 y 50 (1.0800, 1.0850): imanes de precio
  - Máximos/mínimos semanales: puntos de reversión habituales

Factores que mueven EURUSD:
  Alcista (EUR/USD sube): BCE hawkish, datos económicos europeos fuertes,
    Fed dovish, datos USD débiles, apetito de riesgo global
  Bajista (EUR/USD cae): Fed hawkish, datos USD fuertes, BCE dovish,
    crisis política en Europa, risk-off (fuga a refugio)""",
        "metadata": {"categoria": "mercado", "par": "EURUSD", "subtipo": "comportamiento"}
    },

    {
        "id": "market_sessions_detail",
        "text": """CONTEXTO DE MERCADO — Sesiones y Características de Liquidez

SESIÓN DE TOKIO (Asia):
  Horario España invierno: 01:00-09:00 (GMT+1)
  Horario España verano: 02:00-10:00 (GMT+2)
  Pares más activos: USDJPY, AUDUSD, NZDUSD, pares JPY
  Para nuestros pares (EURUSD, XAUUSD): baja liquidez, evitar operar
  Uso: identificar rangos de Asia que serán targets en Londres

SESIÓN DE LONDRES:
  Horario España invierno: 08:00-17:00 (cierre oficial 16:30)
  Horario España verano: 09:00-18:00
  Momento clave: primer impulso entre 08:00-10:00
  Pares más activos: todos los pares EUR, GBP y XAUUSD
  Característica: establece frecuentemente el máximo o mínimo del día
  Trampa frecuente: falso impulso en la primera hora que luego se revierte

SESIÓN DE NUEVA YORK:
  Horario España invierno: 14:30-21:00 (cierre oficial 23:00 pero liquidez cae)
  Horario España verano: 15:30-22:00
  Apertura oficial equities: 15:30 España / 9:30 NY
  Momento de mayor volumen: 14:30-16:00 España (solapamiento + apertura)
  Característica: el movimiento de NY puede confirmar o revertir el de Londres

SOLAPAMIENTO LONDRES-NY (ventana de oro):
  Horario España invierno: 14:30-17:00
  Horario España verano: 15:30-18:00
  Esta es la ventana de MÁXIMA LIQUIDEZ del mercado Forex
  Las mejores operaciones del sistema suelen ocurrir en esta ventana
  El ORB es exclusivo de esta ventana (apertura NY)

LIQUIDEZ BAJA — Evitar operar:
  Viernes 19:00+ España: liquidez cayendo, spread subiendo
  Entre sesiones (11:00-13:00 España): mínima liquidez europea
  Días festivos USD (4 de julio, Thanksgiving, Christmas): evitar todos los pares USD""",
        "metadata": {"categoria": "mercado", "subtipo": "sesiones"}
    },

    {
        "id": "market_weekly_patterns",
        "text": """CONTEXTO DE MERCADO — Patrones por Día de la Semana

Patrones estadísticos observados en Forex/Gold (no son reglas fijas):

LUNES:
  Comportamiento habitual: digestión del gap de apertura, tendencia no clara
  Primera hora errática mientras el mercado "descubre el precio"
  Si hay gap del fin de semana → el primer movimiento puede ser rellenar el gap
  Estrategia: más cauteloso, esperar confirmación adicional, reducir tamaño 25%
  ORB lunes: menos fiable que martes-jueves

MARTES:
  Estadísticamente el mejor día para tendencias claras en XAUUSD
  Frecuentemente el inicio de la tendencia de la semana
  ORB más fiable, SMC con buenos setups institucionales
  Estrategia: tamaño normal, buscar activamente setups

MIÉRCOLES:
  Día del FOMC (cuando aplica, 8 veces al año): evitar todo
  En semanas sin FOMC: similar a martes, buen día para tendencias
  Media semana: si el mercado ha establecido tendencia, es buen día para seguirla

JUEVES:
  Publicación de Jobless Claims (14:30 España): cuidado en esa hora
  Tras los Claims: puede haber buenas oportunidades de ORB o SMC
  En Europa: a veces hay datos del BCE que afectan a EURUSD
  Estrategia: normal, con atención al horario de claims

VIERNES:
  Primer viernes: NFP (14:30 España) → NO operar nada ese día
  Otros viernes: liquidez cayendo desde las 18:00 España
  Cierre de posiciones semanales de institucionales → movimientos erráticos 17:00+
  Estrategia: reducir tamaño, no abrir posiciones después de las 18:00 España
  OBLIGATORIO: cerrar todas las posiciones antes de las 21:00 (cierre semana)""",
        "metadata": {"categoria": "mercado", "subtipo": "patrones_semanales"}
    },

    {
        "id": "market_price_action",
        "text": """CONTEXTO DE MERCADO — Price Action: Velas y Patrones de Confirmación

Patrones de vela de reversión ALCISTA (para confirmar entradas LONG):

Martillo (Hammer):
  - Cuerpo pequeño en la parte superior de la vela
  - Sombra inferior al menos 2× el tamaño del cuerpo
  - Poca o ninguna sombra superior
  - Contexto: aparece tras movimiento bajista, en soporte o OB
  - Fiabilidad: alta en zona de valor (OB, FVG, banda BB inferior)

Engulfing Alcista:
  - La vela actual (alcista) envuelve completamente el cuerpo de la vela anterior (bajista)
  - El cierre de la vela alcista está por encima del máximo de la bajista
  - Cuanto mayor es el engulfing, más fuerte es la señal
  - Fiabilidad: muy alta, especialmente en zona de OB o FVG

Pin Bar Alcista:
  - Mínimo significativamente más bajo que la media de barras recientes
  - Cierre en el tercio superior de la vela
  - Similar al martillo pero puede tener cuerpo más grande
  - Fiabilidad: alta en H1 y H4, moderada en M15

Patrones de vela de reversión BAJISTA (para SHORT):
  Estrella fugaz (Shooting Star): inverso del martillo
  Engulfing Bajista: inverso del engulfing alcista
  Pin Bar Bajista: inverso del pin bar alcista

Velas de continuación (no reversión — no entrar contra ellas):
  Vela marubozu alcista: sin sombras, cuerpo completo verde → continuación alcista fuerte
  Vela marubozu bajista: sin sombras, cuerpo completo rojo → continuación bajista fuerte
  Doji: apertura = cierre, mucha incertidumbre → esperar la siguiente vela

Regla práctica:
  Nunca entrar basándose solo en la vela de confirmación.
  La vela de confirmación es el último filtro de una cadena de condiciones.
  Una vela de confirmación perfecta en el lugar equivocado no vale nada.""",
        "metadata": {"categoria": "mercado", "subtipo": "price_action"}
    },

    {
        "id": "market_macro_calendar",
        "text": """CONTEXTO DE MERCADO — Calendario Macroeconómico: Guía de Consulta

Fuentes de datos macroeconómicos recomendadas:
  - Forex Factory (forexfactory.com): el más completo, actualizado en tiempo real
  - Investing.com/economic-calendar: alternativa con más datos globales
  - Fed Reserve website (federalreserve.gov): para fechas FOMC exactas

Cómo leer el calendario antes de operar:

Paso 1: Identificar el color de impacto
  🔴 Rojo (alto impacto): puede mover el mercado >50 pips en XAUUSD o >20 en EURUSD
  🟠 Naranja (medio impacto): puede mover 20-50 pips en XAUUSD
  🟡 Amarillo (bajo impacto): movimiento menor, generalmente <20 pips

Paso 2: Verificar el horario en España
  Forex Factory muestra en hora local del usuario o ET (NY time)
  Ajuste ET → España invierno: ET + 6 horas
  Ajuste ET → España verano: ET + 6 horas (en verano americano) o +5 (transición)

Paso 3: Evaluar si afecta a nuestros pares
  Datos USD → afecta a TODOS nuestros pares (EURUSD, XAUUSD, USDJPY)
  Datos EUR → afecta principalmente a EURUSD
  Datos GBP → afecta principalmente a GBPUSD

Paso 4: Tomar decisión
  Noticia roja en próximas 2h → no abrir nuevas posiciones
  Noticia roja en próximos 30min + posición abierta → evaluar cierre
  Noticia roja en próxima hora + posición con +1R → mover SL a breakeven

Semanas especialmente peligrosas:
  Primera semana del mes: NFP + ISM Manufacturing + posibles datos de empleo
  Semana de FOMC: miércoles toda la tarde/noche española
  Semana de BCE: jueves con la decisión y la conferencia de Lagarde""",
        "metadata": {"categoria": "mercado", "subtipo": "macro_calendar"}
    },
]


# ════════════════════════════════════════════════════════════════════
# COLECCIÓN 5: TRADING PSYCHOLOGY — 4 documentos
# ════════════════════════════════════════════════════════════════════

PSYCHOLOGY_DOCS = [
    {
        "id": "psych_discipline_rules",
        "text": """PSICOLOGÍA DE TRADING — Reglas de Disciplina que Claude Aplica

Estas reglas son los filtros finales que Claude aplica antes de dar un GO.
Si alguna de estas condiciones se cumple, Claude añade una advertencia o da NO-GO.

REGLA 1 — Revenge Trading (operar para recuperar):
  Señal de alerta: 2+ operaciones perdedoras consecutivas en el día
  Comportamiento común del operador: querer "recuperar" con la siguiente operación
  Impacto: la siguiente operación se toma con bias emocional, no racional
  Respuesta del sistema: tras 2 pérdidas consecutivas → requerir setup 3/3 mínimo
  Si la señal es solo 2/3 tras 2 pérdidas → NO-GO automático

REGLA 2 — FOMO (Fear Of Missing Out):
  Señal de alerta: el mercado ha hecho un movimiento grande sin nosotros
  Comportamiento: entrar tarde en un movimiento ya desarrollado
  Realidad: entrar tarde en un movimiento aumenta el riesgo de coger el giro
  Respuesta del sistema: si la señal llega >30min después del inicio del movimiento,
    advertir que puede ser una entrada tarde — Claude lo menciona en el análisis

REGLA 3 — Overconfidence tras racha ganadora:
  Señal de alerta: 3+ operaciones ganadoras consecutivas
  Comportamiento: aumentar el tamaño creyendo que "el sistema es infalible ahora"
  Realidad: el tamaño siempre es el 1% fijo, independientemente de rachas
  Respuesta del sistema: tras 3 ganancias consecutivas, recordar que el tamaño
    sigue siendo el mismo — no aumentarlo bajo ninguna circunstancia

REGLA 4 — Paralysis by Analysis:
  Señal de alerta: el operador lleva 30+ minutos evaluando un setup sin decidir
  Comportamiento: buscar confirmación adicional indefinidamente
  Realidad: si la señal es 3/3 y el checklist está completo, entrar o no entrar
  Respuesta del sistema: el análisis de Claude es determinístico — GO o NO-GO,
    no hay respuesta intermedia de "tal vez si ves X más"

REGLA 5 — Operar para alcanzar el objetivo diario:
  Señal de alerta: el operador está por debajo del objetivo diario y la sesión cierra
  Comportamiento: forzar una operación para "llegar al objetivo"
  Realidad: los objetivos son mensuales, no diarios — un día malo no arruina el mes
  Respuesta del sistema: si el sistema ha dado NO-GO, ese NO-GO es firme""",
        "metadata": {"categoria": "psicologia", "subtipo": "disciplina"}
    },

    {
        "id": "psych_signal_quality",
        "text": """PSICOLOGÍA DE TRADING — Evaluación de Calidad de Señal

Claude usa este framework para convertir el análisis técnico en una puntuación de
confianza (probability score) que se muestra en la alerta de Telegram.

Puntuación base según confluencia:
  3/3 estrategias alineadas: puntuación base = 70%
  2/3 estrategias alineadas: puntuación base = 55%

Bonificadores (suman a la puntuación base):
  +5%  → Contexto H4 claramente alineado con la dirección
  +5%  → Vela de confirmación perfecta (engulfing o pin bar limpio)
  +5%  → Sin noticias de alto impacto en próximas 2 horas
  +5%  → Nivel de soporte/resistencia mayor (semanal/mensual) coincide
  +5%  → Histórico: este tipo de setup ha funcionado >65% en últimas 10 ocasiones (RL)
  +3%  → Volumen notablemente mayor en la vela de breakout/confirmación
  +3%  → Múltiples timeframes confirman (H4, H1, M15 todos alineados)

Penalizadores (restan a la puntuación base):
  -10% → Hay noticia de impacto medio en próxima hora
  -10% → Día viernes después de las 17:00 España
  -10% → Spread actual >30% sobre el spread medio (alta volatilidad del broker)
  -10% → Drawdown diario ya en 2%+ (sesión comprometida)
  -5%  → Setup tarde (>30 min desde el inicio del movimiento)
  -5%  → Día lunes con gap de apertura
  -5%  → Correlación negativa con posición ya abierta

Umbrales de decisión:
  Puntuación >= 75% → GO con tamaño completo
  Puntuación 65-74% → GO con tamaño reducido (75% del normal)
  Puntuación 55-64% → GO solo si confluencia es 3/3, tamaño 50%
  Puntuación < 55% → NO-GO, comunicar razón al operador""",
        "metadata": {"categoria": "psicologia", "subtipo": "calidad_señal"}
    },

    {
        "id": "psych_claude_reasoning",
        "text": """PSICOLOGÍA DE TRADING — Cómo Claude Debe Razonar Cada Señal

Estructura del análisis que Claude hace en cada señal:

PASO 1 — Verificación de condiciones básicas (rápido, 2 segundos):
  ¿Estamos dentro de la ventana horaria? → Si no, NO-GO automático
  ¿El drawdown diario permite operar? → Si >4.5%, NO-GO automático
  ¿El número de operaciones del día es <3? → Si ya hay 3, NO-GO automático
  ¿Hay noticia crítica en próximos 15 min? → Si sí, NO-GO automático

PASO 2 — Análisis técnico (el núcleo del razonamiento):
  ¿El contexto H4 apoya la dirección de la señal?
  ¿Los Order Blocks/FVGs identificados son de calidad alta/media/baja?
  ¿La vela de confirmación es clara o ambigua?
  ¿Los niveles de SL/TP hacen sentido con el contexto del mercado?

PASO 3 — Consulta al RAG (contexto adicional):
  ¿Qué dice el historial de este tipo de setup en condiciones similares?
  ¿Hay patrones aprendidos por el RL que sean relevantes?
  ¿Las condiciones macro actuales favorecen este tipo de operación?

PASO 4 — Cálculo de la puntuación de confianza:
  Aplicar la tabla de bonificadores y penalizadores
  Determinar GO/NO-GO y el tamaño adecuado

PASO 5 — Redacción del análisis para Telegram:
  El análisis debe ser conciso (3-5 líneas), sin jerga innecesaria
  Mencionar los 2-3 factores más importantes que llevaron a la decisión
  Ser honesto sobre la incertidumbre: "el setup es bueno pero hay noticia en 45 min"
  Dar el GO o NO-GO de forma clara, nunca ambigua

Tono del análisis de Claude:
  Profesional pero accesible, no técnico en exceso
  Mencionar riesgos reales, no solo los positivos
  Si hay duda genuina, decir "setup borderline, considera reducir tamaño"
  Nunca prometer resultados: "alta probabilidad" no es "garantía".""",
        "metadata": {"categoria": "psicologia", "subtipo": "razonamiento_claude"}
    },

    {
        "id": "psych_learning_mindset",
        "text": """PSICOLOGÍA DE TRADING — Mentalidad de Aprendizaje Continuo

El sistema aprende, pero el operador también debe aprender con él.
Estas son las prácticas que hacen que el sistema mejore con el tiempo:

Registro de cada operación (obligatorio):
  No solo el resultado (ganó/perdió), sino:
  - Qué estaba bien en el setup
  - Qué dudas tenías antes de entrar
  - Qué pasó diferente a lo esperado
  - Qué harías diferente la próxima vez
  Este log va a la base de datos y el motor RL lo usa para mejorar

Revisión semanal (30 minutos cada viernes):
  1. Revisar todas las operaciones de la semana
  2. Identificar si hay un patrón de errores repetido
  3. Verificar si el sistema RL ha ajustado los pesos correctamente
  4. Decidir si hay algún parámetro que cambiar para la semana siguiente

Lo que NO debe cambiar semana a semana:
  - El riesgo por operación (1% fijo)
  - El R:R mínimo (1.5)
  - Las reglas de drawdown (inviolables)
  - El sistema de confluencia (2/3 mínimo)

Lo que SÍ puede ajustarse con datos:
  - Los niveles de RSI para BB+RSI (si el 35/65 resulta demasiado conservador)
  - El período del rango ORB (30 min vs 15 min según los resultados)
  - Los pesos de cada estrategia en la confluencia (si una funciona mejor)
  - Las ventanas horarias (si la tarde NY resulta ser menos productiva)

Mentalidad correcta ante el drawdown:
  El drawdown no es un fallo del sistema — es parte del sistema.
  Un sistema con 60% de win rate GARANTIZA que habrá rachas de 4-5 pérdidas.
  La gestión correcta del drawdown ES la habilidad, no evitar que ocurra.""",
        "metadata": {"categoria": "psicologia", "subtipo": "mentalidad"}
    },
]


# ════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL DE INDEXACIÓN
# ════════════════════════════════════════════════════════════════════

def index_all_documents() -> dict:
    """
    Indexa todos los documentos en ChromaDB.
    Retorna un resumen de cuántos documentos se indexaron por colección.
    """
    logger.info("━━━ Iniciando indexación completa del RAG ━━━")
    summary = {}

    collections = [
        ("ftmo_rules",        FTMO_RULES,           "Reglas FTMO"),
        ("strategies",        STRATEGY_DOCS,         "Estrategias de trading"),
        ("risk_management",   RISK_DOCS,             "Gestión de riesgo"),
        ("market_context",    MARKET_CONTEXT_DOCS,   "Contexto de mercado"),
        ("trading_psychology", PSYCHOLOGY_DOCS,      "Psicología de trading"),
    ]

    total = 0
    for collection_name, docs, label in collections:
        col = get_or_create_collection(collection_name)
        col.upsert(
            ids=[d["id"] for d in docs],
            documents=[d["text"] for d in docs],
            metadatas=[d["metadata"] for d in docs],
        )
        count = len(docs)
        total += count
        summary[collection_name] = count
        logger.info(f"  ✅ {label}: {count} documentos indexados")

    logger.info(f"━━━ Indexación completada: {total} documentos en total ━━━")
    return summary


def query_rag(query: str, collection_names: list[str] = None, n_results: int = 3) -> list[dict]:
    """
    Consulta el RAG con una query en lenguaje natural.
    Busca en las colecciones especificadas (o en todas si no se indica).
    Retorna los documentos más relevantes con su puntuación de similitud.

    Args:
        query: La pregunta o contexto a buscar
        collection_names: Lista de colecciones donde buscar. Si None, busca en todas.
        n_results: Número de resultados por colección

    Returns:
        Lista de dicts con {text, metadata, collection, distance}
    """
    all_collections = ["ftmo_rules", "strategies", "risk_management",
                       "market_context", "trading_psychology"]
    search_in = collection_names or all_collections

    results = []
    for col_name in search_in:
        col = get_or_create_collection(col_name)
        try:
            res = col.query(
                query_texts=[query],
                n_results=min(n_results, col.count()),
            )
            for i, doc in enumerate(res["documents"][0]):
                results.append({
                    "text": doc,
                    "metadata": res["metadatas"][0][i],
                    "collection": col_name,
                    "distance": res["distances"][0][i],
                })
        except Exception as e:
            logger.warning(f"Error consultando {col_name}: {e}")

    # Ordenar por distancia (menor = más relevante)
    results.sort(key=lambda x: x["distance"])
    return results


def get_context_for_signal(
    pair: str,
    direction: str,
    strategies: list[str],
    session: str,
) -> str:
    """
    Genera el contexto RAG completo para que Claude analice una señal.
    Combina documentos relevantes de todas las colecciones en un texto estructurado.

    Args:
        pair: Par de divisas (XAUUSD, EURUSD, etc.)
        direction: LONG o SHORT
        strategies: Lista de estrategias activas (["SMC", "ORB", "BB_RSI"])
        session: Sesión activa (london_open, ny_open, ny_session, etc.)

    Returns:
        String con el contexto completo para incluir en el prompt de Claude
    """
    context_parts = []

    # 1. Reglas FTMO relevantes (siempre incluir riesgo)
    ftmo_results = query_rag(
        f"drawdown riesgo reglas {pair}",
        collection_names=["ftmo_rules"],
        n_results=2,
    )
    if ftmo_results:
        context_parts.append("=== REGLAS FTMO RELEVANTES ===")
        for r in ftmo_results[:2]:
            context_parts.append(r["text"])

    # 2. Estrategias activas
    for strategy in strategies:
        strat_results = query_rag(
            f"estrategia {strategy} entrada {direction} checklist",
            collection_names=["strategies"],
            n_results=2,
        )
        if strat_results:
            context_parts.append(f"=== ESTRATEGIA {strategy} ===")
            for r in strat_results[:2]:
                context_parts.append(r["text"])

    # 3. Contexto del par
    market_results = query_rag(
        f"{pair} comportamiento sesión {session}",
        collection_names=["market_context"],
        n_results=2,
    )
    if market_results:
        context_parts.append(f"=== CONTEXTO DE MERCADO: {pair} ===")
        for r in market_results[:2]:
            context_parts.append(r["text"])

    # 4. Gestión de riesgo para el sizing
    risk_results = query_rag(
        "tamaño posición sizing riesgo porcentaje",
        collection_names=["risk_management"],
        n_results=1,
    )
    if risk_results:
        context_parts.append("=== GESTIÓN DE RIESGO ===")
        context_parts.append(risk_results[0]["text"])

    # 5. Puntuación de confianza y psicología
    psych_results = query_rag(
        "puntuación confianza calidad señal evaluación",
        collection_names=["trading_psychology"],
        n_results=1,
    )
    if psych_results:
        context_parts.append("=== EVALUACIÓN DE CALIDAD ===")
        context_parts.append(psych_results[0]["text"])

    return "\n\n".join(context_parts)


if __name__ == "__main__":
    # Indexar todos los documentos
    summary = index_all_documents()

    # Test rápido de una query
    logger.info("\n━━━ Test de consulta RAG ━━━")
    test_results = query_rag(
        "XAUUSD apertura NY ORB breakout confirmación entrada",
        n_results=2,
    )
    for r in test_results[:3]:
        logger.info(f"  [{r['collection']}] distancia={r['distance']:.3f}")
        logger.info(f"  → {r['text'][:100]}...")

    logger.info("\n━━━ Test de contexto para señal ━━━")
    context = get_context_for_signal(
        pair="XAUUSD",
        direction="LONG",
        strategies=["ORB", "SMC"],
        session="ny_open",
    )
    logger.info(f"Contexto generado: {len(context)} caracteres")