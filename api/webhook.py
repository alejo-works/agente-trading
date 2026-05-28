"""
Webhook — recibe señales de TradingView y las procesa con IA.
Fase 2: análisis completo con Claude + RAG.
"""
from fastapi import APIRouter, Request, HTTPException, Header
from loguru import logger
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import pytz

from config.settings import settings
from execution.telegram_bot import send_telegram
from ai.analyzer import analyze_signal

router = APIRouter()


class Signal(BaseModel):
    type: str = "CONFLUENCIA"
    direction: str
    pair: str
    timeframe: str
    score: Optional[str] = "0"
    price: str
    time: Optional[str] = None
    smc: Optional[str] = "0"
    orb: Optional[str] = "0"
    bb_rsi: Optional[str] = "0"

    @property
    def score_int(self) -> int:
        try:
            return int(float(self.score))
        except:
            return 0

    @property
    def price_float(self) -> float:
        try:
            return float(self.price)
        except:
            return 0.0


def hora_espana() -> str:
    tz = pytz.timezone("Europe/Madrid")
    return datetime.now(tz).strftime("%H:%M")

def hora_ny() -> str:
    tz = pytz.timezone("America/New_York")
    return datetime.now(tz).strftime("%H:%M")

def direction_emoji(direction: str) -> str:
    return "🟢" if direction == "LONG" else "🔴"

def score_emoji(score: int) -> str:
    if score >= 3:
        return "⭐⭐⭐ FUERTE"
    elif score == 2:
        return "⭐⭐ MODERADA"
    return "⭐ DÉBIL"


def build_telegram_message(signal: Signal, analysis=None) -> str:
    emoji  = direction_emoji(signal.direction)
    h_esp  = hora_espana()
    h_ny   = hora_ny()
    smc_ok = "✅" if float(signal.smc or 0) > 0 else "—"
    orb_ok = "✅" if float(signal.orb or 0) > 0 else "—"
    bb_ok  = "✅" if float(signal.bb_rsi or 0) > 0 else "—"

    if analysis:
        decision_emoji = "✅ GO" if analysis.decision == "GO" else "❌ NO-GO"
        pip_decimals = 3 if "JPY" in signal.pair else 5
        entry  = signal.price_float
        sl     = entry - analysis.sl_pips * 0.0001 if signal.direction == "LONG" else entry + analysis.sl_pips * 0.0001
        tp     = entry + analysis.tp_pips * 0.0001 if signal.direction == "LONG" else entry - analysis.tp_pips * 0.0001
        rr     = round(analysis.tp_pips / analysis.sl_pips, 1) if analysis.sl_pips > 0 else 0

        msg = f"""
{emoji} *{signal.direction} — {signal.pair}*
⏰ {h_esp} España | {h_ny} NY

📊 *Confluencia: {signal.score_int}/3 {score_emoji(signal.score_int)}*
• SMC:    {smc_ok}
• ORB:    {orb_ok}
• BB+RSI: {bb_ok}

🤖 *Análisis IA: {decision_emoji}*
_{analysis.reasoning}_

📍 Entrada: `{entry:.{pip_decimals}f}`
🛑 Stop Loss: `{sl:.{pip_decimals}f}` ({analysis.sl_pips} pips)
✅ Take Profit: `{tp:.{pip_decimals}f}` ({analysis.tp_pips} pips)
📐 R:R: 1:{rr} | Riesgo: {analysis.risk_size}%
🎯 Probabilidad IA: *{analysis.probability}%*
""".strip()
    else:
        msg = f"""
{emoji} *SEÑAL {signal.direction} — {signal.pair}*
⏰ {h_esp} España | {h_ny} NY
📊 Confluencia: {signal.score_int}/3 {score_emoji(signal.score_int)}
🤖 _Analizando con IA..._
""".strip()

    return msg


@router.post("/signal")
async def receive_signal(
    request: Request,
    x_webhook_secret: Optional[str] = Header(None)
):
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="No autorizado")

    try:
        payload = await request.json()
        logger.info(f"Señal recibida: {payload}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {e}")

    score = int(float(payload.get("score", 0)))
    if score < 2:
        return {"status": "ignored", "reason": "score < 2"}

    signal = Signal(**payload)

    # Envía alerta inmediata mientras Claude analiza
    await send_telegram(build_telegram_message(signal))

    # Análisis con Claude + RAG
    try:
        analysis = await analyze_signal(
            direction=signal.direction,
            pair=signal.pair,
            price=signal.price_float,
            score=signal.score_int,
            timeframe=signal.timeframe,
            smc_active=float(signal.smc or 0) > 0,
            orb_active=float(signal.orb or 0) > 0,
            bb_rsi_active=float(signal.bb_rsi or 0) > 0,
            daily_pnl=0.0,       # TODO Fase 4: leer de PostgreSQL
            daily_drawdown_pct=0.0,
            trades_today=0,
        )
        # Envía análisis completo
        await send_telegram(build_telegram_message(signal, analysis))
        logger.info(f"✅ Análisis completado: {analysis.decision} {analysis.probability}%")

    except Exception as e:
        logger.error(f"Error en análisis IA: {e}")
        await send_telegram(f"⚠️ Error en análisis IA: {e}\nRevisar manualmente.")

    return {"status": "ok", "pair": signal.pair, "direction": signal.direction}


@router.get("/test")
async def test_signal():
    """Simula señal 3/3 para probar el pipeline completo."""
    signal = Signal(
        direction="LONG", pair="EURUSD",
        timeframe="15", score="3", price="1.16505",
        smc="1", orb="1", bb_rsi="1"
    )

    await send_telegram(build_telegram_message(signal))

    analysis = await analyze_signal(
        direction="LONG", pair="EURUSD",
        price=1.16505, score=3, timeframe="15",
        smc_active=True, orb_active=True, bb_rsi_active=True,
    )

    await send_telegram(build_telegram_message(signal, analysis))
    return {"status": "test enviado", "decision": analysis.decision, "prob": analysis.probability}
