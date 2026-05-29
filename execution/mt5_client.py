"""
MT5 Client — corre en Railway.
Llama al mt5_agent.py que está corriendo en el PC Windows del operador.

Variables de entorno necesarias:
    MT5_AGENT_URL    → URL pública del agente (ngrok o IP fija)
    MT5_AGENT_SECRET → secreto compartido para autenticación
"""

import asyncio
import httpx
from loguru import logger
from config.settings import settings


class MT5Client:
    """
    Cliente HTTP que se comunica con el MT5 Agent en Windows.
    Railway no puede correr MT5 directamente (solo Windows),
    por eso usamos este patrón agente-cliente.
    """

    def __init__(self):
        self.base_url = settings.mt5_agent_url.rstrip("/")
        self.secret   = settings.mt5_agent_secret
        self.headers  = {"x-agent-secret": self.secret, "ngrok-skip-browser-warning": "true"}
        self.timeout  = 15.0

        # Tickets que el monitor está vigilando activamente
        # clave: ticket, valor: dict con symbol, sl, tp, lot_size
        self._monitored: dict[int, dict] = {}

    # ── HEALTH ────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """Verifica que el agente y MT5 están disponibles."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    f"{self.base_url}/health",
                    headers=self.headers,
                )
                r.raise_for_status()
                return r.json()
        except httpx.ConnectError:
            return {"status": "agent_offline", "error": "No se puede conectar al agente MT5"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── ÓRDENES ───────────────────────────────────────────────

    async def open_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        sl_price: float,
        tp_price: float,
        comment: str = "TradingBot",
    ) -> dict:
        """
        Abre una orden de mercado y la añade al monitor automáticamente.
        """
        payload = {
            "symbol":    symbol,
            "direction": direction,
            "lot_size":  lot_size,
            "sl_price":  sl_price,
            "tp_price":  tp_price,
            "comment":   comment,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/order/open",
                    json=payload,
                    headers=self.headers,
                )
                r.raise_for_status()
                result = r.json()
                logger.info(
                    f"✅ Orden ejecutada — {symbol} {direction} "
                    f"{lot_size} lotes | Ticket: {result['ticket']}"
                )

                # Añadir al monitor automáticamente
                ticket = result["ticket"]
                self._monitored[ticket] = {
                    "symbol":     symbol,
                    "direction":  direction,
                    "lot_size":   lot_size,
                    "sl_price":   sl_price,
                    "tp_price":   tp_price,
                    "open_price": result["price"],
                }
                logger.info(f"👁 Monitor activado para ticket {ticket}")

                return result

        except httpx.HTTPStatusError as e:
            error = e.response.json().get("detail", str(e))
            logger.error(f"❌ Error al abrir orden: {error}")
            return {"status": "error", "error": error}
        except httpx.ConnectError:
            logger.error("❌ Agente MT5 no disponible — ¿está el PC encendido?")
            return {"status": "agent_offline", "error": "Agente MT5 no disponible"}
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return {"status": "error", "error": str(e)}

    async def close_order(self, ticket: int) -> dict:
        """Cierra una posición por su ticket y la elimina del monitor."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/order/close",
                    json={"ticket": ticket},
                    headers=self.headers,
                )
                r.raise_for_status()
                result = r.json()
                logger.info(f"✅ Posición cerrada — Ticket: {ticket} | P&L: ${result['profit']:.2f}")

                # Eliminar del monitor
                self._monitored.pop(ticket, None)

                return result

        except httpx.HTTPStatusError as e:
            error = e.response.json().get("detail", str(e))
            logger.error(f"❌ Error al cerrar orden {ticket}: {error}")
            return {"status": "error", "error": error}
        except Exception as e:
            logger.error(f"❌ Error inesperado al cerrar: {e}")
            return {"status": "error", "error": str(e)}

    # ── CONSULTAS ─────────────────────────────────────────────

    async def get_positions(self) -> list[dict]:
        """Devuelve todas las posiciones abiertas."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    f"{self.base_url}/positions",
                    headers=self.headers,
                )
                r.raise_for_status()
                return r.json().get("positions", [])
        except Exception as e:
            logger.error(f"Error obteniendo posiciones: {e}")
            return []

    async def get_account(self) -> dict | None:
        """Devuelve el estado actual de la cuenta MT5."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    f"{self.base_url}/account",
                    headers=self.headers,
                )
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.error(f"Error obteniendo cuenta: {e}")
            return None

    # ── HELPERS ───────────────────────────────────────────────

    async def is_available(self) -> bool:
        """Retorna True si el agente MT5 está disponible y conectado."""
        health = await self.health_check()
        return health.get("status") == "ok"

    async def get_daily_pnl(self) -> float:
        """Retorna el P&L flotante actual de todas las posiciones abiertas."""
        account = await self.get_account()
        if not account:
            return 0.0
        return round(account.get("profit", 0.0), 2)

    async def get_drawdown_pct(self) -> float:
        """Retorna el drawdown diario actual en porcentaje."""
        account = await self.get_account()
        if not account:
            return 0.0
        return account.get("drawdown_pct", 0.0)

    # ── MONITOR EN TIEMPO REAL ────────────────────────────────

    async def start_monitor(self) -> None:
        """
        Loop de monitorización que corre en background.
        Comprueba cada 30 segundos el estado de las posiciones vigiladas.
        Se activa automáticamente al arrancar el servidor (lifespan).

        Detecta y notifica:
          - Posición cerrada por TP → notifica beneficio
          - Posición cerrada por SL → notifica pérdida
          - Drawdown diario >= 4% → alerta de emergencia FTMO
          - Agente MT5 offline → alerta al operador
        """
        from execution.telegram_bot import send_telegram, send_order_result

        logger.info("👁 Monitor MT5 iniciado — revisando cada 30 segundos")

        consecutive_errors = 0

        while True:
            await asyncio.sleep(30)

            try:
                # ── Verificar agente disponible ───────────────
                if not await self.is_available():
                    consecutive_errors += 1
                    if consecutive_errors == 3:  # Solo alertar tras 3 fallos (90 seg)
                        await send_telegram(
                            "⚠️ *Agente MT5 no responde*\n"
                            "Verifica que el PC está encendido y `mt5_agent.py` corriendo.\n"
                            "Las posiciones abiertas no están siendo monitorizadas."
                        )
                        logger.warning("⚠️ Agente MT5 no disponible — 3 intentos fallidos")
                    continue

                consecutive_errors = 0  # Reset si responde

                # ── Verificar drawdown FTMO ───────────────────
                account = await self.get_account()
                if account:
                    drawdown = account.get("drawdown_pct", 0.0)

                    if drawdown >= 4.0:
                        logger.warning(f"🚨 Drawdown crítico: {drawdown}%")
                        await send_telegram(
                            f"🚨 *ALERTA DRAWDOWN CRÍTICO*\n"
                            f"Drawdown actual: *{drawdown}%*\n"
                            f"Límite FTMO: 5%\n\n"
                            f"⛔ Cierra todas las posiciones AHORA para proteger la cuenta."
                        )
                    elif drawdown >= 3.0:
                        logger.warning(f"⚠️ Drawdown en zona de alerta: {drawdown}%")
                        await send_telegram(
                            f"⚠️ *Drawdown en zona de alerta: {drawdown}%*\n"
                            f"Considera reducir exposición. Límite FTMO: 5%"
                        )

                # ── Verificar posiciones monitorizadas ────────
                if not self._monitored:
                    continue  # Nada que vigilar

                # Obtener posiciones abiertas reales en MT5
                open_positions = await self.get_positions()
                open_tickets   = {p["ticket"] for p in open_positions}

                # Detectar posiciones que ya no están abiertas (cerradas por SL/TP)
                closed_tickets = [t for t in list(self._monitored.keys())
                                  if t not in open_tickets]

                for ticket in closed_tickets:
                    info   = self._monitored.pop(ticket)
                    symbol = info["symbol"]

                    await send_order_result(
                        ticket=ticket,
                        symbol=symbol,
                        profit=0.0,  # Se actualizará con /history en siguiente versión
                    )
                    logger.info(f"📋 Posición {ticket} cerrada detectada por monitor")

            except asyncio.CancelledError:
                logger.info("👁 Monitor MT5 detenido")
                break
            except Exception as e:
                logger.error(f"Error en monitor MT5: {e}")


# Instancia global para usar en el resto del proyecto
mt5_client = MT5Client()