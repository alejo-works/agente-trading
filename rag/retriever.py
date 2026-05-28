"""
Retriever RAG — busca contexto relevante dado una señal de trading.
"""
from loguru import logger
from rag.chroma_client import get_or_create_collection


def get_context_for_signal(
    direction: str,
    pair: str,
    score: int,
    strategies_active: list[str]
) -> str:
    """
    Recupera el contexto RAG relevante para una señal.
    Devuelve un string listo para pasar a Claude.
    """
    context_parts = []

    # 1. Reglas FTMO relevantes
    ftmo_col = get_or_create_collection("ftmo_rules")
    ftmo_results = ftmo_col.query(
        query_texts=[f"reglas riesgo drawdown {direction} operación"],
        n_results=3
    )
    if ftmo_results["documents"][0]:
        context_parts.append("=== REGLAS FTMO (INVIOLABLES) ===")
        for doc in ftmo_results["documents"][0]:
            context_parts.append(doc)

    # 2. Contexto de estrategias activas
    strat_col = get_or_create_collection("strategies")
    query = f"estrategia {' '.join(strategies_active)} {direction} {pair} confluencia"
    strat_results = strat_col.query(
        query_texts=[query],
        n_results=3
    )
    if strat_results["documents"][0]:
        context_parts.append("\n=== ESTRATEGIAS ACTIVAS ===")
        for doc in strat_results["documents"][0]:
            context_parts.append(doc)

    return "\n\n".join(context_parts)
