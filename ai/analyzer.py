"""
Analyzer — orquesta RAG + Claude para analizar cada señal.
Devuelve decisión GO/NO-GO con razonamiento y probabilidad.
"""
import json
from loguru import logger
from dataclasses import dataclass

import anthropic
from config.settings import settings
from rag.retriever import get_context_for_signal
from ai.prompts import build_analysis_prompt, SYSTEM_PROMPT


@dataclass
class AnalysisResult:
    decision: str        # GO | NO-GO
    reasoning: str       # Explicación en 2-3 frases
    probability: int     # 0-100
    risk_size: float     # % de riesgo recomendado (0.5 o 1.0)
    sl_pips: float       # Stop loss sugerido en pips
    tp_pips: float       # Take profit sugerido en pips


async def analyze_signal(
    direction: str,
    pair: str,
    price: float,
    score: int,
    timeframe: str,
    smc_active: bool = False,
    orb_active: bool = False,
    bb_rsi_active: bool = False,
    daily_pnl: float = 0.0,
    daily_drawdown_pct: float = 0.0,
    trades_today: int = 0,
) -> AnalysisResult:
    """
    Analiza una señal de confluencia con Claude + RAG.
    """
    strategies_active = []
    if smc_active:
        strategies_active.append("SMC")
    if orb_active:
        strategies_active.append("ORB")
    if bb_rsi_active:
        strategies_active.append("BB_RSI")

    # 1. Obtener contexto RAG
    logger.info(f"Recuperando contexto RAG para {direction} {pair} {score}/3")
    rag_context = get_context_for_signal(
        direction=direction,
        pair=pair,
        score=score,
        strategies_active=strategies_active
    )

    # 2. Construir prompt
    prompt = build_analysis_prompt(
        direction=direction,
        pair=pair,
        price=price,
        score=score,
        timeframe=timeframe,
        strategies_active=strategies_active,
        rag_context=rag_context,
        daily_pnl=daily_pnl,
        daily_drawdown_pct=daily_drawdown_pct,
        trades_today=trades_today,
    )

    # 3. Llamar a Claude
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    logger.info("Enviando señal a Claude para análisis...")
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    logger.info(f"Claude respondió: {raw[:100]}...")

    # 4. Parsear respuesta JSON
    try:
        # Claude devuelve JSON limpio según el prompt
        clean = raw.strip()
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        data = json.loads(clean)

        return AnalysisResult(
            decision=data.get("decision", "NO-GO"),
            reasoning=data.get("reasoning", "Sin razonamiento disponible"),
            probability=int(data.get("probability", 50)),
            risk_size=float(data.get("risk_size", 0.5)),
            sl_pips=float(data.get("sl_pips", 15)),
            tp_pips=float(data.get("tp_pips", 25)),
        )
    except Exception as e:
        logger.error(f"Error parseando respuesta Claude: {e}\nRaw: {raw}")
        return AnalysisResult(
            decision="NO-GO",
            reasoning="Error en el análisis IA. Revisar manualmente.",
            probability=0,
            risk_size=0.0,
            sl_pips=0,
            tp_pips=0,
        )
