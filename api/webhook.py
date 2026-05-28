"""
Webhook — recibe señales de TradingView y las procesa.
Fase 1: parsea la señal y envía alerta básica por Telegram.
"""
from fastapi import APIRouter, Request, HTTPException, Header
from loguru import logger
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import pytz

from config.settings import settings
from execution.telegram_bot import send_telegram

router = APIRouter()

# ── MODELO DE SEÑAL ──────────────────────────────────────────
class Signal(BaseModel):
    type: str = "CONFLUENCIA"         # CONFLUENCIA | SMC | ORB | BB_RSI
    direction: str                     # LONG | SHORT
    pair: str                          # EURUSD, XAUUSD...
    timeframe: str                     # 15, 60...
    score: Optional[str] = "0"        # 1, 2 o 3
    price: str                         # precio de cierre
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


# ── HELPERS ──────────────────────────────────────────────────
def hora_espana() -> str:
    """Devuelve la hora actual en España (CET/CEST)."""
    tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(tz)
    return now.strftime("%H:%M")

def hora_ny() -> str:
    """Devuelve la hora actual en Nueva York."""
    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    return now.strftime("%H:%M")

def score_emoji(score: int) -> str:
    if score >= 3:
        return "⭐⭐⭐ FUERTE"
    elif score == 2:
        return "⭐⭐ MODERADA"
    return "⭐ DÉBIL"

def direction_emoji(direction: str) -> str:
    return "🟢" if direction == "LONG" else "🔴"

def build_telegram_message(signal: Signal) -> str:
    """Construye el mensaje de Telegram para la señal recibida."""
    emoji  = direction_emoji(signal.direction)
    score  = score_emoji(signal.score_int)
    h_esp  = hora_espana()
    h_ny   = hora_ny()

    # Estrategias activas
    smc_ok    = "✅" if float(signal.smc or 0) > 0    else "—"
    orb_ok    = "✅" if float(signal.orb or 0) > 0    else "—"
    bbrsi_ok  = "✅" if float(signal.bb_rsi or 0) > 0 else "—"

    msg = f"""
{emoji} *SEÑAL {signal.direction} — {signal.pair}*
⏰ {h_esp} España | {h_ny} NY

📊 *Confluencia: {signal.score_int}/3 {score}*
• SMC:    {smc_ok}
• ORB:    {orb_ok}
• BB+RSI: {bbrsi_ok}

💰 *Precio:* `{signal.price_float:.5f}`
📐 *Temporalidad:* M{signal.timeframe}

🤖 _Análisis IA en construcción — Fase 2_
""".strip()

    return msg


# ── ENDPOINT PRINCIPAL ───────────────────────────────────────
@router.post("/signal")
async def receive_signal(
    request: Request,
    x_webhook_secret: Optional[str] = Header(None)
):
    """
    Recibe el webhook de TradingView con la señal de confluencia.
    Valida, parsea y envía alerta básica por Telegram.
    """
    # Validar secret
    if x_webhook_secret != settings.webhook_secret:
        logger.warning("Webhook rechazado — secret inválido")
        raise HTTPException(status_code=401, detail="No autorizado")

    # Parsear payload
    try:
        payload = await request.json()
        logger.info(f"Señal recibida: {payload}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {e}")

    # Validar score mínimo
    score = int(float(payload.get("score", 0)))
    if score < 2:
        logger.info(f"Señal descartada — score {score}/3 insuficiente")
        return {"status": "ignored", "reason": "score < 2"}

    # Construir señal
    try:
        signal = Signal(**payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Señal inválida: {e}")

    # Enviar a Telegram
    mensaje = build_telegram_message(signal)
    await send_telegram(mensaje)

    logger.info(f"✅ Señal procesada: {signal.direction} {signal.pair} {signal.score_int}/3")
    return {
        "status": "ok",
        "direction": signal.direction,
        "pair": signal.pair,
        "score": signal.score_int
    }


@router.get("/test")
async def test_signal():
    """
    Endpoint de prueba — simula una señal sin TradingView.
    Útil mientras no tenemos plan Plus.
    GET https://tu-app.railway.app/webhook/test
    """
    test_signal = Signal(
        direction="LONG",
        pair="EURUSD",
        timeframe="15",
        score="3",
        price="1.16505",
        smc="1",
        orb="1",
        bb_rsi="1"
    )
    mensaje = build_telegram_message(test_signal)
    await send_telegram(mensaje)
    return {"status": "test enviado", "mensaje": mensaje}
