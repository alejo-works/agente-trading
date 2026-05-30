"""
Webhook — recibe señales de TradingView y callbacks de Telegram.
Fase 2: análisis completo con Claude + RAG.
Fase 3: botones EJECUTAR / IGNORAR conectados a MT5.
"""
from fastapi import APIRouter, Request, HTTPException, Header
from loguru import logger
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import pytz

from config.settings import settings
from execution.telegram_bot import send_telegram, send_signal_alert, handle_telegram_callback
from execution.daily_manager import check_limits, register_trade_opened, register_trade_closed, get_state_summary
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

def score_label(score: int) -> str:
    if score >= 3:
        return "⭐⭐⭐ FUERTE"
    elif score == 2:
        return "⭐⭐ MODERADA"
    return "⭐ DÉBIL"

def safe_text(text: str) -> str:
    """Elimina caracteres Markdown que rompen el parser de Telegram."""
    return text.replace("_", " ").replace("*", " ").replace("`", " ").replace("[", " ").replace("]", " ")


def build_telegram_message(signal: Signal, analysis=None) -> str:
    """Mensaje de texto plano (sin botones) — usado para el aviso inicial mientras Claude analiza."""
    emoji  = direction_emoji(signal.direction)
    h_esp  = hora_espana()
    h_ny   = hora_ny()
    smc_ok = "✅" if float(signal.smc or 0) > 0 else "—"
    orb_ok = "✅" if float(signal.orb or 0) > 0 else "—"
    bb_ok  = "✅" if float(signal.bb_rsi or 0) > 0 else "—"

    if analysis:
        decision_emoji = "✅ GO" if analysis.decision == "GO" else "❌ NO-GO"
        pip_decimals = 3 if "JPY" in signal.pair else 5
        entry = signal.price_float
        sl    = entry - analysis.sl_pips * 0.0001 if signal.direction == "LONG" else entry + analysis.sl_pips * 0.0001
        tp    = entry + analysis.tp_pips * 0.0001 if signal.direction == "LONG" else entry - analysis.tp_pips * 0.0001
        rr    = round(analysis.tp_pips / analysis.sl_pips, 1) if analysis.sl_pips > 0 else 0
        reasoning = safe_text(analysis.reasoning)

        msg = (
            f"{emoji} *{signal.direction} — {signal.pair}*\n"
            f"⏰ {h_esp} España | {h_ny} NY\n\n"
            f"📊 *Confluencia: {signal.score_int}/3 {score_label(signal.score_int)}*\n"
            f"• SMC:    {smc_ok}\n"
            f"• ORB:    {orb_ok}\n"
            f"• BB+RSI: {bb_ok}\n\n"
            f"🤖 *IA: {decision_emoji}*\n"
            f"{reasoning}\n\n"
            f"📍 Entrada: `{entry:.{pip_decimals}f}`\n"
            f"🛑 SL: `{sl:.{pip_decimals}f}` ({analysis.sl_pips} pips)\n"
            f"✅ TP: `{tp:.{pip_decimals}f}` ({analysis.tp_pips} pips)\n"
            f"📐 R:R 1:{rr} | Riesgo: {analysis.risk_size}%\n"
            f"🎯 Probabilidad: *{analysis.probability}%*"
        )
    else:
        msg = (
            f"{emoji} *{signal.direction} — {signal.pair}*\n"
            f"⏰ {h_esp} España | {h_ny} NY\n"
            f"📊 Confluencia: {signal.score_int}/3 {score_label(signal.score_int)}\n"
            f"🤖 Analizando con IA..."
        )

    return msg


# ── SEÑALES DE TRADINGVIEW ────────────────────────────────────

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

    # Verificar limites del dia antes de procesar
    from execution.mt5_client import mt5_client
    drawdown_pct = await mt5_client.get_drawdown_pct()
    can_trade, reason = await check_limits(drawdown_pct=drawdown_pct)
    if not can_trade:
        logger.info(f"Senal descartada por limite: {reason}")
        return {"status": "blocked", "reason": reason}

    # Mensaje inmediato mientras Claude analiza
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
            daily_pnl=0.0,
            daily_drawdown_pct=0.0,
            trades_today=0,
        )
        logger.info(f"✅ Análisis: {analysis.decision} {analysis.probability}%")

        # Calcular SL y TP en precio real
        entry = signal.price_float
        sl = (entry - analysis.sl_pips * 0.0001
              if signal.direction == "LONG"
              else entry + analysis.sl_pips * 0.0001)
        tp = (entry + analysis.tp_pips * 0.0001
              if signal.direction == "LONG"
              else entry - analysis.tp_pips * 0.0001)

        # Calcular lote (1% de riesgo con $10,000)
        risk_usd = 10000 * (analysis.risk_size / 100)
        lot_size = round(risk_usd / (analysis.sl_pips * 10), 2)
        lot_size = max(0.01, min(lot_size, 2.0))  # entre 0.01 y 2.0

        # Estrategias activas
        strategies = []
        if float(signal.smc or 0) > 0:   strategies.append("SMC")
        if float(signal.orb or 0) > 0:   strategies.append("ORB")
        if float(signal.bb_rsi or 0) > 0: strategies.append("BB+RSI")

        if analysis.decision == "GO":
            # Enviar alerta CON botones EJECUTAR / IGNORAR
            await send_signal_alert(
                signal={
                    "symbol":     signal.pair,
                    "direction":  "BUY" if signal.direction == "LONG" else "SELL",
                    "entry":      entry,
                    "sl":         round(sl, 5),
                    "tp":         round(tp, 5),
                    "lot_size":   lot_size,
                    "score":      signal.score_int,
                    "strategies": strategies,
                },
                analysis={
                    "probability": analysis.probability,
                    "decision":    analysis.decision,
                    "reasoning":   safe_text(analysis.reasoning),
                },
            )
        else:
            # NO-GO: enviar mensaje informativo sin botones
            await send_telegram(build_telegram_message(signal, analysis))

    except Exception as e:
        logger.error(f"Error análisis IA: {e}")
        await send_telegram("⚠️ Error en análisis IA\nRevisar manualmente.")

    return {"status": "ok", "pair": signal.pair, "direction": signal.direction}


# ── CALLBACKS DE TELEGRAM (botones) ──────────────────────────

@router.post("/telegram")
async def telegram_callback(request: Request):
    """
    Recibe los callbacks de Telegram cuando el usuario pulsa
    EJECUTAR o IGNORAR en la alerta de señal.

    Este endpoint debe registrarse como webhook en Telegram:
    https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://TU-RAILWAY.app/webhook/telegram
    """
    try:
        update = await request.json()
        logger.info(f"Callback Telegram: {update}")
        await handle_telegram_callback(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error procesando callback Telegram: {e}")
        return {"ok": False, "error": str(e)}


# ── TEST ──────────────────────────────────────────────────────

@router.get("/test")
async def test_signal():
    """Simula una señal 3/3 completa con botones EJECUTAR / IGNORAR."""
    signal = Signal(
        direction="LONG", pair="EURUSD",
        timeframe="15", score="3", price="1.16505",
        smc="1", orb="1", bb_rsi="1"
    )

    # Aviso inmediato
    await send_telegram(build_telegram_message(signal))

    # Análisis IA
    analysis = await analyze_signal(
        direction="LONG", pair="EURUSD",
        price=1.16505, score=3, timeframe="15",
        smc_active=True, orb_active=True, bb_rsi_active=True,
    )

    # Alerta con botones
    await send_signal_alert(
        signal={
            "symbol":     "EURUSD",
            "direction":  "BUY",
            "entry":      1.16505,
            "sl":         1.16305,
            "tp":         1.16905,
            "lot_size":   0.10,
            "score":      3,
            "strategies": ["SMC", "ORB", "BB+RSI"],
        },
        analysis={
            "probability": analysis.probability,
            "decision":    analysis.decision,
            "reasoning":   safe_text(analysis.reasoning),
        },
    )

    return {"status": "ok", "decision": analysis.decision, "prob": analysis.probability}