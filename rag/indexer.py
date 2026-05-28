"""
Indexador RAG — carga documentos en ChromaDB.
Ejecutar una vez al inicio o cuando cambien los documentos.
"""
from loguru import logger
from rag.chroma_client import get_or_create_collection

# ── DOCUMENTOS FTMO ──────────────────────────────────────────
FTMO_RULES = [
    {
        "id": "ftmo_daily_drawdown",
        "text": """REGLA FTMO — Drawdown Diario Máximo: 5%
El drawdown diario máximo permitido es del 5% del balance inicial del día.
Si las pérdidas del día alcanzan el 5% del balance de inicio de sesión, 
todas las posiciones deben cerrarse y no se puede operar más ese día.
Ejemplo con cuenta $10,000: máximo $500 de pérdida diaria.
El sistema debe parar automáticamente al llegar al 4% como margen de seguridad.""",
        "metadata": {"categoria": "ftmo", "tipo": "riesgo", "prioridad": "critica"}
    },
    {
        "id": "ftmo_total_drawdown",
        "text": """REGLA FTMO — Drawdown Total Máximo: 10%
El drawdown total máximo permitido es del 10% del balance inicial de la cuenta.
Si el balance cae un 10% desde el inicio, la cuenta se cierra automáticamente.
Ejemplo con cuenta $10,000: el balance nunca puede bajar de $9,000.
El sistema debe parar al llegar al 8% de drawdown total como margen de seguridad.""",
        "metadata": {"categoria": "ftmo", "tipo": "riesgo", "prioridad": "critica"}
    },
    {
        "id": "ftmo_profit_target",
        "text": """REGLA FTMO — Objetivo de Beneficio Challenge: 10%
Durante el challenge FTMO, el objetivo es alcanzar un 10% de beneficio.
Con cuenta $10,000: necesitas llegar a $11,000.
Mínimo 4 días de trading para aprobar el challenge.
No hay límite de tiempo desde 2024.
Una vez aprobado y en cuenta fondeada, no hay objetivo de beneficio obligatorio.""",
        "metadata": {"categoria": "ftmo", "tipo": "objetivo", "prioridad": "alta"}
    },
    {
        "id": "ftmo_risk_management",
        "text": """REGLA FTMO — Gestión de Riesgo Recomendada
Riesgo máximo por operación: 1% del balance ($100 con cuenta $10,000).
Máximo 3 operaciones simultáneas abiertas.
R:R mínimo de 1.5:1 para abrir una operación.
Objetivo diario: $250 (1/20 del objetivo mensual de $5,000).
Al alcanzar $500 de beneficio diario, parar por ese día.
Al alcanzar $200 de pérdida diaria, parar por ese día.""",
        "metadata": {"categoria": "ftmo", "tipo": "riesgo", "prioridad": "alta"}
    },
    {
        "id": "ftmo_trading_hours",
        "text": """REGLA FTMO — Horarios de Trading
No mantener posiciones abiertas durante el fin de semana.
Cerrar todas las posiciones antes del cierre del mercado del viernes.
Evitar operar durante noticias de alto impacto (eventos rojo en calendario).
Las ventanas óptimas son: apertura Londres (08:00-09:00 España), 
solapamiento Londres-NY (13:00-15:00 España), apertura NY (14:30-16:00 España).""",
        "metadata": {"categoria": "ftmo", "tipo": "horario", "prioridad": "media"}
    },
]

# ── DOCUMENTOS ESTRATEGIAS ────────────────────────────────────
STRATEGY_DOCS = [
    {
        "id": "strategy_smc",
        "text": """ESTRATEGIA SMC — Smart Money Concepts
Temporalidad: H4 para contexto, H1 para setup, M15 para entrada.
Condiciones LONG:
- BOS (Break of Structure) alcista confirmado en H1
- Order Block identificado en H4 o H1
- FVG (Fair Value Gap) presente en M15
- Precio retrocede al OB/FVG sin cerrarlo
- Vela de confirmación alcista en M15
Condiciones SHORT: Exactamente inverso al LONG.
Señal válida: BOS + FVG confirmados. Señal fuerte: BOS + OB + FVG.
El OB es la última vela bajista antes de un movimiento alcista fuerte (para LONG).
El FVG es un hueco de precio entre 3 velas consecutivas sin solapamiento.""",
        "metadata": {"categoria": "estrategia", "nombre": "SMC", "prioridad": "alta"}
    },
    {
        "id": "strategy_orb",
        "text": """ESTRATEGIA ORB — Opening Range Breakout
Temporalidad: M5 para definir rango, M15 para entrada.
Ventana: primeros 30 minutos de apertura NY (13:30-14:00 UTC / 14:30-15:00 CET España).
Condiciones LONG:
- Rango definido en los primeros 30 min de apertura NY
- Precio cierra por encima del High del rango en M15
- Volumen confirma el breakout (opcional)
- Solo válido en las primeras 2 horas de sesión NY
Condiciones SHORT: Precio cierra por debajo del Low del rango.
Targets: TP1 = tamaño del rango (1R), TP2 = 2x tamaño del rango (2R).
Stop Loss: al otro lado del rango (Low para LONG, High para SHORT).
Esta estrategia es muy efectiva en XAUUSD y EURUSD en días de alta volatilidad.""",
        "metadata": {"categoria": "estrategia", "nombre": "ORB", "prioridad": "alta"}
    },
    {
        "id": "strategy_bb_rsi",
        "text": """ESTRATEGIA BB+RSI — Bollinger Bands + RSI
Temporalidad: H1 para contexto, M15 para entrada.
Parámetros: BB longitud 20, desviación 2. RSI longitud 14.
Condiciones LONG:
- Precio toca o cruza banda inferior de Bollinger (desviación 2)
- RSI por debajo de 35 y girando al alza
- Vela de reversión confirmada (martillo, engulfing alcista)
- Contexto H4 no bajista (no operar contra tendencia mayor)
Condiciones SHORT: 
- Precio toca banda superior
- RSI por encima de 65 y girando a la baja
- Vela de reversión bajista
Esta estrategia funciona mejor en mercados en rango/consolidación.
Evitar en tendencias fuertes donde el precio puede seguir en las bandas.""",
        "metadata": {"categoria": "estrategia", "nombre": "BB_RSI", "prioridad": "alta"}
    },
    {
        "id": "strategy_confluence",
        "text": """SISTEMA DE CONFLUENCIA — 3 Estrategias
El sistema requiere mínimo 2/3 estrategias alineadas para generar señal.
Score 3/3: SMC + ORB + BB_RSI alineadas → Señal FUERTE, tamaño normal (1% riesgo).
Score 2/3: 2 estrategias alineadas → Señal MODERADA, tamaño reducido (0.5% riesgo).
Score 1/3: Solo 1 estrategia → NO OPERAR bajo ningún concepto.
La dirección debe ser la misma en todas las estrategias activas.
Si SMC dice LONG y ORB dice SHORT, no hay confluencia válida.""",
        "metadata": {"categoria": "estrategia", "nombre": "CONFLUENCIA", "prioridad": "critica"}
    },
    {
        "id": "strategy_macro_filter",
        "text": """FILTRO MACROECONÓMICO — Noticias de Alto Impacto
No operar 15 minutos antes ni 15 minutos después de noticias de alto impacto (rojo).
Noticias críticas para USD: NFP, CPI, FOMC, PIB, Ventas minoristas.
Noticias críticas para EUR: BCE, IPC europeo, PIB eurozona.
Si hay noticia de alto impacto en los próximos 30 minutos, reducir tamaño al 50%.
Si hay noticia en los próximos 15 minutos, no abrir nuevas posiciones.""",
        "metadata": {"categoria": "filtro", "nombre": "MACRO", "prioridad": "alta"}
    },
]


def index_all_documents() -> None:
    """Indexa todos los documentos en ChromaDB."""
    logger.info("Iniciando indexación de documentos RAG...")

    # FTMO Rules
    ftmo_col = get_or_create_collection("ftmo_rules")
    for doc in FTMO_RULES:
        ftmo_col.upsert(
            ids=[doc["id"]],
            documents=[doc["text"]],
            metadatas=[doc["metadata"]]
        )
    logger.info(f"✅ FTMO: {len(FTMO_RULES)} documentos indexados")

    # Estrategias
    strat_col = get_or_create_collection("strategies")
    for doc in STRATEGY_DOCS:
        strat_col.upsert(
            ids=[doc["id"]],
            documents=[doc["text"]],
            metadatas=[doc["metadata"]]
        )
    logger.info(f"✅ Estrategias: {len(STRATEGY_DOCS)} documentos indexados")

    logger.info("✅ Indexación RAG completada")


if __name__ == "__main__":
    index_all_documents()
