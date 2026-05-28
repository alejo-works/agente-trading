"""
MT5 Client — corre en Railway.
Llama al mt5_agent.py que está corriendo en el PC Windows del operador.

Variables de entorno necesarias:
    MT5_AGENT_URL    → URL pública del agente (ngrok o IP fija)
    MT5_AGENT_SECRET → secreto compartido para autenticación
"""

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
        self.headers  = {"x-agent-secret": self.secret}
        self.timeout  = 15.0  # segundos

    # ── HEALTH ────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """Verifica que el agente y MT5 están disponibles."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(f"{self.base_url}/health")
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
        Abre una orden de mercado.

        Args:
            symbol:    Par (XAUUSD, EURUSD...)
            direction: BUY o SELL
            lot_size:  Tamaño en lotes (0.10, 0.50...)
            sl_price:  Precio exacto del Stop Loss
            tp_price:  Precio exacto del Take Profit
            comment:   Comentario visible en MT5

        Returns:
            dict con ticket, precio de ejecución, y estado
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
        """Cierra una posición por su ticket."""
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
        """Calcula el P&L del día sumando posiciones abiertas + historial de hoy."""
        account = await self.get_account()
        if not account:
            return 0.0
        # El profit en account_info incluye las posiciones flotantes abiertas
        return round(account.get("profit", 0.0), 2)

    async def get_drawdown_pct(self) -> float:
        """Retorna el drawdown diario actual en porcentaje."""
        account = await self.get_account()
        if not account:
            return 0.0
        return account.get("drawdown_pct", 0.0)


# Instancia global para usar en el resto del proyecto
mt5_client = MT5Client()