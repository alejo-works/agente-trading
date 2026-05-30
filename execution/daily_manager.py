"""
Daily Manager — Fase 4
Gestiona objetivos diarios, límites FTMO y parada automática.

Lógica central:
  - Calcula daily_target desde monthly_target automáticamente
  - Monitoriza P&L y drawdown en tiempo real
  - Para el bot automáticamente al alcanzar límites
  - Envía reporte diario al cierre NY (21:00 España)
  - Resetea contadores a medianoche
"""

import asyncio
from datetime import datetime, time as dtime
from loguru import logger
import pytz

from config.settings import settings

# ── ESTADO DIARIO (en memoria, se resetea a medianoche) ───────
_state = {
    "paused":          False,   # True = bot pausado, no procesa señales
    "pause_reason":    "",      # Razón de la pausa
    "trades_today":    0,       # Número de operaciones del día
    "pnl_today":       0.0,     # P&L realizado del día
    "daily_pnl_peak":  0.0,     # Máximo P&L alcanzado hoy
    "waiting_confirm": False,   # True = esperando confirmación del operador
    "date":            None,    # Fecha del estado actual
}

TZ_MADRID = pytz.timezone("Europe/Madrid")
TZ_NY     = pytz.timezone("America/New_York")


# ── GETTERS DE ESTADO ─────────────────────────────────────────

def is_paused() -> bool:
    """Retorna True si el bot está pausado y no debe procesar señales."""
    _check_date_reset()
    return _state["paused"]

def get_pause_reason() -> str:
    return _state["pause_reason"]

def is_waiting_confirm() -> bool:
    return _state["waiting_confirm"]

def get_trades_today() -> int:
    _check_date_reset()
    return _state["trades_today"]

def get_pnl_today() -> float:
    return _state["pnl_today"]

def get_state_summary() -> dict:
    """Retorna un resumen completo del estado para mostrar en Telegram."""
    return {
        "paused":          _state["paused"],
        "pause_reason":    _state["pause_reason"],
        "trades_today":    _state["trades_today"],
        "pnl_today":       _state["pnl_today"],
        "daily_target":    settings.daily_target_usd,
        "max_profit":      settings.daily_max_profit_usd,
        "max_loss":        settings.daily_max_loss_usd,
        "waiting_confirm": _state["waiting_confirm"],
    }


# ── SETTERS DE ESTADO ─────────────────────────────────────────

def register_trade_opened() -> None:
    """Registra que se ha abierto una operación."""
    _state["trades_today"] += 1
    logger.info(f"📊 Operaciones hoy: {_state['trades_today']}/{settings.max_trades_per_day}")

def register_trade_closed(profit: float) -> None:
    """Registra el resultado de una operación cerrada y verifica límites."""
    _state["pnl_today"] += profit
    _state["pnl_today"] = round(_state["pnl_today"], 2)

    if _state["pnl_today"] > _state["daily_pnl_peak"]:
        _state["daily_pnl_peak"] = _state["pnl_today"]

    logger.info(f"💰 P&L hoy: ${_state['pnl_today']:.2f} | Objetivo: ${settings.daily_target_usd:.0f}")

def confirm_continue() -> None:
    """El operador confirma continuar después de alcanzar el máximo de beneficio."""
    _state["paused"]          = False
    _state["pause_reason"]    = ""
    _state["waiting_confirm"] = False
    logger.info("✅ Operador confirmó continuar — bot reanudado")

def resume_bot() -> None:
    """Reanuda el bot manualmente."""
    _state["paused"]          = False
    _state["pause_reason"]    = ""
    _state["waiting_confirm"] = False


# ── RESET DIARIO ──────────────────────────────────────────────

def _check_date_reset() -> None:
    """Resetea el estado si ha cambiado el día."""
    today = datetime.now(TZ_MADRID).date()
    if _state["date"] != today:
        logger.info(f"🔄 Reset diario — nuevo día: {today}")
        _state.update({
            "paused":          False,
            "pause_reason":    "",
            "trades_today":    0,
            "pnl_today":       0.0,
            "daily_pnl_peak":  0.0,
            "waiting_confirm": False,
            "date":            today,
        })


# ── VERIFICACIÓN DE LÍMITES ───────────────────────────────────

async def check_limits(drawdown_pct: float = 0.0) -> tuple[bool, str]:
    """
    Verifica todos los límites antes de permitir una nueva señal.
    Retorna (puede_operar: bool, razón: str)

    Límites verificados:
      1. Bot pausado manualmente o por límite
      2. Máximo de operaciones del día
      3. Máximo de pérdida diaria ($200)
      4. Máximo de beneficio diario ($500) → pausa con confirmación
      5. Drawdown FTMO >= 4.5% → parada de emergencia
    """
    from execution.telegram_bot import send_telegram

    _check_date_reset()

    # 1. Bot pausado
    if _state["paused"]:
        return False, _state["pause_reason"]

    # 2. Máximo de operaciones
    if _state["trades_today"] >= settings.max_trades_per_day:
        return False, f"Límite de {settings.max_trades_per_day} operaciones diarias alcanzado"

    # 3. Pérdida máxima diaria
    if _state["pnl_today"] <= -settings.daily_max_loss_usd:
        _pause_bot(
            reason=f"Pérdida máxima diaria alcanzada (${abs(_state['pnl_today']):.2f})",
            waiting_confirm=False,
        )
        await send_telegram(
            f"🛑 *Bot pausado — Pérdida máxima diaria*\n"
            f"P&L hoy: `${_state['pnl_today']:.2f}`\n"
            f"Límite: `${settings.daily_max_loss_usd:.0f}`\n\n"
            f"El bot no operará más hoy. Mañana se reanuda automáticamente."
        )
        return False, "Pérdida máxima diaria alcanzada"

    # 4. Beneficio máximo diario → pausa con confirmación
    if _state["pnl_today"] >= settings.daily_max_profit_usd:
        _pause_bot(
            reason=f"Beneficio máximo diario alcanzado (${_state['pnl_today']:.2f})",
            waiting_confirm=True,
        )
        await send_telegram(
            f"🎯 *Bot pausado — Objetivo máximo alcanzado*\n"
            f"P&L hoy: `+${_state['pnl_today']:.2f}`\n"
            f"Objetivo máximo: `${settings.daily_max_profit_usd:.0f}`\n\n"
            f"¿Deseas continuar operando hoy?",
            reply_markup={
                "inline_keyboard": [[
                    {"text": "✅ Continuar", "callback_data": "confirm_continue"},
                    {"text": "🛑 Parar por hoy", "callback_data": "stop_today"},
                ]]
            }
        )
        return False, "Beneficio máximo diario alcanzado — esperando confirmación"

    # 5. Drawdown FTMO crítico
    if drawdown_pct >= 4.5:
        _pause_bot(
            reason=f"Drawdown FTMO crítico ({drawdown_pct:.1f}%)",
            waiting_confirm=False,
        )
        await send_telegram(
            f"🚨 *EMERGENCIA FTMO — Bot pausado*\n"
            f"Drawdown actual: `{drawdown_pct:.1f}%`\n"
            f"Límite FTMO: `5%`\n\n"
            f"⛔ Cierra todas las posiciones AHORA.\n"
            f"El bot no operará más hoy."
        )
        return False, f"Drawdown FTMO crítico: {drawdown_pct:.1f}%"

    return True, "ok"


def _pause_bot(reason: str, waiting_confirm: bool = False) -> None:
    """Pausa el bot con una razón."""
    _state["paused"]          = True
    _state["pause_reason"]    = reason
    _state["waiting_confirm"] = waiting_confirm
    logger.warning(f"🛑 Bot pausado: {reason}")


# ── REPORTE DIARIO ────────────────────────────────────────────

async def send_daily_report() -> None:
    """Envía el reporte diario por Telegram al cierre NY (21:00 España)."""
    from execution.telegram_bot import send_telegram
    from execution.mt5_client import mt5_client

    hora_esp = datetime.now(TZ_MADRID).strftime("%d/%m/%Y")

    # Obtener estado de la cuenta MT5
    account = await mt5_client.get_account()
    balance  = account.get("balance", 0) if account else 0
    equity   = account.get("equity", 0) if account else 0

    pnl        = _state["pnl_today"]
    trades     = _state["trades_today"]
    target     = settings.daily_target_usd
    monthly    = settings.monthly_target_usd

    # Emojis según resultado
    pnl_emoji    = "✅" if pnl >= target else ("⚠️" if pnl > 0 else "❌")
    target_emoji = "🎯 CONSEGUIDO" if pnl >= target else f"${target - pnl:.0f} restante"

    msg = (
        f"📊 *REPORTE DIARIO — {hora_esp}*\n\n"
        f"💰 P&L del día: `{'+'if pnl>=0 else ''}{pnl:.2f} USD` {pnl_emoji}\n"
        f"🎯 Objetivo diario: `${target:.0f}` — {target_emoji}\n\n"
        f"📈 Operaciones: `{trades}/{settings.max_trades_per_day}`\n"
        f"💼 Balance: `${balance:.2f}`\n"
        f"📊 Equity: `${equity:.2f}`\n\n"
        f"📅 Objetivo mensual: `${monthly:.0f}`\n"
        f"⏰ Sesión NY cerrada — bot en pausa hasta mañana"
    )

    await send_telegram(msg)
    logger.info(f"📊 Reporte diario enviado — P&L: ${pnl:.2f}")


# ── SCHEDULER ─────────────────────────────────────────────────

async def start_scheduler() -> None:
    """
    Loop que corre en background y ejecuta tareas programadas:
      - 21:00 España → reporte diario + pausa nocturna
      - 00:01 España → reset de contadores del día
    Comprueba cada minuto.
    """
    logger.info("⏰ Scheduler iniciado")
    last_report_date = None
    last_reset_date  = None

    while True:
        await asyncio.sleep(60)  # Comprobar cada minuto

        try:
            now_madrid = datetime.now(TZ_MADRID)
            today      = now_madrid.date()
            hour       = now_madrid.hour
            minute     = now_madrid.minute

            # ── Reporte diario a las 21:00 España ────────────
            if hour == 21 and minute == 0 and last_report_date != today:
                last_report_date = today
                await send_daily_report()
                # Pausar el bot hasta mañana
                _pause_bot(reason="Cierre de sesión NY — reanuda mañana", waiting_confirm=False)
                logger.info("🌙 Bot pausado por cierre de sesión NY")

            # ── Reset de contadores a las 00:01 ──────────────
            if hour == 0 and minute == 1 and last_reset_date != today:
                last_reset_date = today
                _check_date_reset()  # Fuerza el reset
                logger.info("🔄 Contadores del día reseteados")

        except asyncio.CancelledError:
            logger.info("⏰ Scheduler detenido")
            break
        except Exception as e:
            logger.error(f"Error en scheduler: {e}")
