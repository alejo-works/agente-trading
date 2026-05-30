"""
Bot de Telegram — alertas con botones de acción.
Fase 1: envío de mensajes de texto.
Fase 3: botones EJECUTAR / IGNORAR conectados a MT5.

Flujo:
  1. Llega señal → send_signal_alert() envía mensaje con botones
  2. Usuario pulsa EJECUTAR → Telegram envía callback a /webhook/telegram
  3. El handler ejecuta la orden en MT5 y confirma por Telegram
"""
import json
import httpx
from loguru import logger
from config.settings import settings

TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

# Almacén en memoria de señales pendientes de ejecutar
# clave: callback_data, valor: dict con los parámetros de la orden
_pending_signals: dict[str, dict] = {}


# ── MENSAJES BÁSICOS ──────────────────────────────────────────

async def send_telegram(message: str, parse_mode: str = "Markdown", reply_markup: dict = None) -> bool:
    """Envía un mensaje de texto al chat configurado."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram no configurado — TOKEN o CHAT_ID vacíos")
        return False

    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info("✅ Telegram: mensaje enviado")
                return True
            else:
                logger.error(f"❌ Telegram error {response.status_code}: {response.text}")
                return False
    except Exception as e:
        logger.error(f"❌ Telegram excepción: {e}")
        return False


async def answer_callback(callback_query_id: str, text: str) -> None:
    """Responde al callback de un botón (elimina el 'reloj' en Telegram)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{TELEGRAM_API}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
            )
    except Exception as e:
        logger.warning(f"Error respondiendo callback: {e}")


async def edit_message_text(chat_id: str, message_id: int, text: str) -> None:
    """Edita un mensaje existente (para actualizar el estado tras ejecutar)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{TELEGRAM_API}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
    except Exception as e:
        logger.warning(f"Error editando mensaje: {e}")


# ── ALERTA DE SEÑAL CON BOTONES ───────────────────────────────

async def send_signal_alert(signal: dict, analysis: dict) -> bool:
    """
    Envía la alerta de señal con botones EJECUTAR / IGNORAR.

    Args:
        signal: dict con symbol, direction, entry, sl, tp, lot_size, strategies, score
        analysis: dict con probability, reasoning del análisis de Claude

    Returns:
        True si el mensaje se envió correctamente
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False

    # Guardar señal en memoria para cuando el usuario pulse EJECUTAR
    signal_id = f"{signal['symbol']}_{signal['direction']}_{int(signal.get('entry', 0) * 10000)}"
    _pending_signals[signal_id] = {
        "symbol":    signal["symbol"],
        "direction": signal["direction"],
        "lot_size":  signal.get("lot_size", 0.01),
        "sl_price":  signal["sl"],
        "tp_price":  signal["tp"],
        "comment":   f"Bot {signal['symbol']} {signal['direction']}",
    }

    # Emoji según confluencia
    score = signal.get("score", 0)
    stars = "⭐" * score
    color = "🟢" if signal["direction"] in ("BUY", "LONG") else "🔴"
    strength = "FUERTE" if score == 3 else "MODERADA"

    # Estrategias activas
    strategies = signal.get("strategies", [])
    strat_lines = "\n".join([f"  • {s} ✅" for s in strategies])

    # R:R
    entry = signal.get("entry", 0)
    sl    = signal.get("sl", 0)
    tp    = signal.get("tp", 0)
    risk  = abs(entry - sl)
    reward = abs(tp - entry)
    rr = round(reward / risk, 1) if risk > 0 else 0

    # Probabilidad
    prob = analysis.get("probability", 0)
    go   = analysis.get("decision", "NO-GO")
    reasoning = analysis.get("reasoning", "Sin análisis disponible")

    message = f"""
{color} *SEÑAL {strength} — {signal['symbol']}*
⏰ Apertura NY

📊 *Confluencia: {score}/3* {stars}
{strat_lines}

🤖 *Análisis IA:*
_{reasoning}_

📍 Entrada: `{entry}`
🛑 Stop Loss: `{sl}`
✅ Take Profit: `{tp}`
📐 R:R: 1:{rr} | Lote: `{signal.get('lot_size', 0.01)}`
🎯 Probabilidad IA: *{prob}%*
""".strip()

    # Botones inline
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ EJECUTAR AUTO", "callback_data": f"execute_{signal_id}"},
            {"text": "❌ IGNORAR",       "callback_data": f"ignore_{signal_id}"},
        ]]
    }

    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id":      settings.telegram_chat_id,
        "text":         message,
        "parse_mode":   "Markdown",
        "reply_markup": keyboard,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"✅ Alerta enviada: {signal['symbol']} {signal['direction']} {score}/3")
                return True
            else:
                logger.error(f"❌ Error enviando alerta: {response.text}")
                return False
    except Exception as e:
        logger.error(f"❌ Excepción enviando alerta: {e}")
        return False


# ── HANDLER DE CALLBACKS (botones) ───────────────────────────

async def handle_telegram_callback(update: dict) -> None:
    """
    Procesa el callback cuando el usuario pulsa EJECUTAR o IGNORAR.
    Este método es llamado desde el endpoint /webhook/telegram de FastAPI.
    """
    from execution.mt5_client import mt5_client

    callback_query = update.get("callback_query", {})
    if not callback_query:
        return

    callback_id   = callback_query["id"]
    callback_data = callback_query.get("data", "")
    chat_id       = str(callback_query["message"]["chat"]["id"])
    message_id    = callback_query["message"]["message_id"]
    original_text = callback_query["message"].get("text", "")

    # ── EJECUTAR ──────────────────────────────────────────────
    if callback_data.startswith("execute_"):
        signal_id = callback_data.replace("execute_", "")
        signal    = _pending_signals.get(signal_id)

        if not signal:
            await answer_callback(callback_id, "⚠️ Señal expirada o ya ejecutada")
            return

        await answer_callback(callback_id, "⏳ Ejecutando orden...")

        # Verificar que el agente MT5 está disponible
        if not await mt5_client.is_available():
            await answer_callback(callback_id, "❌ MT5 no disponible")
            await send_telegram(
                "❌ *Error:* El agente MT5 no está disponible.\n"
                "Verifica que el PC está encendido y el agente corriendo."
            )
            return

        # Ejecutar la orden
        result = await mt5_client.open_order(**signal)

        if result.get("status") == "executed":
            ticket = result["ticket"]
            price  = result["price"]

            # Eliminar de pendientes
            del _pending_signals[signal_id]

            # Editar el mensaje original para mostrar que fue ejecutado
            await edit_message_text(
                chat_id,
                message_id,
                original_text + f"\n\n✅ *EJECUTADO* | Ticket: `{ticket}` | Precio: `{price}`",
            )

            # Mensaje de confirmación
            await send_telegram(
                f"✅ *Orden ejecutada correctamente*\n"
                f"🎫 Ticket: `{ticket}`\n"
                f"💰 Precio: `{price}`\n"
                f"📊 {signal['symbol']} {signal['direction']} {signal['lot_size']} lotes\n"
                f"🛑 SL: `{signal['sl_price']}` | ✅ TP: `{signal['tp_price']}`"
            )
            logger.info(f"✅ Orden ejecutada desde Telegram — Ticket: {ticket}")

        else:
            error = result.get("error", "Error desconocido")
            await send_telegram(f"❌ *Error al ejecutar:* {error}")
            logger.error(f"❌ Error ejecutando desde Telegram: {error}")

    # ── IGNORAR ───────────────────────────────────────────────
    elif callback_data.startswith("ignore_"):
        signal_id = callback_data.replace("ignore_", "")

        # Eliminar de pendientes
        _pending_signals.pop(signal_id, None)

        await answer_callback(callback_id, "❌ Señal ignorada")
        await edit_message_text(
            chat_id,
            message_id,
            original_text + "\n\n❌ *IGNORADA*",
        )
        logger.info(f"Señal ignorada por el operador: {signal_id}")


# ── MENSAJES DE SISTEMA ───────────────────────────────────────

async def send_telegram_startup() -> None:
    """Mensaje de inicio del servidor."""
    from datetime import datetime
    import pytz
    tz   = pytz.timezone("Europe/Madrid")
    hora = datetime.now(tz).strftime("%H:%M")

    msg = f"""
🤖 *Trading Bot iniciado*
⏰ {hora} España
🟢 Servidor online y escuchando señales
📡 Esperando confluencias 2/3 o 3/3...
""".strip()

    await send_telegram(msg)


async def send_order_result(ticket: int, symbol: str, profit: float) -> None:
    """Notifica el resultado de una operación cerrada."""
    emoji = "✅" if profit >= 0 else "❌"
    msg = (
        f"{emoji} *Operación cerrada*\n"
        f"🎫 Ticket: `{ticket}`\n"
        f"📊 {symbol}\n"
        f"💰 Resultado: `{'+'if profit>=0 else ''}{profit:.2f} USD`"
    )
    await send_telegram(msg)
