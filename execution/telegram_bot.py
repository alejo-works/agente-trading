"""
Bot de Telegram — alertas básicas de señales.
Fase 1: envío de mensajes de texto.
Fase 3: botones de acción (EJECUTAR / IGNORAR).
"""
import httpx
from loguru import logger
from config.settings import settings


TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_bot_token}"


async def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """
    Envía un mensaje al chat configurado.
    Retorna True si fue exitoso.
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram no configurado — TOKEN o CHAT_ID vacíos")
        return False

    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }

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


async def send_telegram_startup() -> None:
    """Mensaje de inicio del servidor — confirma que el bot está vivo."""
    from datetime import datetime
    import pytz
    tz = pytz.timezone("Europe/Madrid")
    hora = datetime.now(tz).strftime("%H:%M")

    msg = f"""
🤖 *Trading Bot iniciado*
⏰ {hora} España
🟢 Servidor online y escuchando señales
📡 Esperando confluencias 2/3 o 3/3...
""".strip()

    await send_telegram(msg)
