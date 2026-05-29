"""
MT5 Agent — corre en tu PC Windows con MetaTrader 5 abierto.
Expone una mini API local que Railway llama para ejecutar órdenes.

Instalación en Windows:
    pip install fastapi uvicorn MetaTrader5

Arrancar:
    python mt5_agent.py

Mantenerlo corriendo mientras operas.
"""

import MetaTrader5 as mt5
import uvicorn
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime
import os

# ── CONFIGURACIÓN ─────────────────────────────────────────────
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "MetaQuotes-Demo")
AGENT_SECRET = os.getenv("MT5_AGENT_SECRET", "cambia-esto-por-un-secreto")
AGENT_PORT   = int(os.getenv("MT5_AGENT_PORT", "8001"))

app = FastAPI(title="MT5 Agent", version="1.0.0")


# ── MODELOS ───────────────────────────────────────────────────
class OrderRequest(BaseModel):
    symbol: str          # "XAUUSD", "EURUSD"
    direction: str       # "BUY" o "SELL"
    lot_size: float      # 0.10
    sl_price: float      # precio exacto del stop loss
    tp_price: float      # precio exacto del take profit
    comment: str = "TradingBot"


class CloseRequest(BaseModel):
    ticket: int          # número de ticket de la orden


# ── AUTENTICACIÓN ─────────────────────────────────────────────
def verify_secret(x_agent_secret: str = Header(...)):
    if x_agent_secret != AGENT_SECRET:
        raise HTTPException(status_code=401, detail="Secreto inválido")


# ── CONEXIÓN MT5 ──────────────────────────────────────────────
def connect_mt5() -> bool:
    """Conecta o reconecta a MT5."""
    if not mt5.initialize():
        return False
    if MT5_LOGIN:
        return mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)
    return True


def ensure_connected() -> None:
    """Lanza excepción si MT5 no está conectado."""
    if not mt5.terminal_info():
        if not connect_mt5():
            raise HTTPException(
                status_code=503,
                detail=f"MT5 no disponible: {mt5.last_error()}"
            )


# ── ARRANQUE ──────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    if connect_mt5():
        info = mt5.account_info()
        print(f"✅ MT5 conectado — Cuenta: {info.login} | Balance: ${info.balance:.2f}")
    else:
        print(f"❌ MT5 no conectado: {mt5.last_error()}")
        print("   Asegúrate de que MetaTrader 5 está abierto y el trading algorítmico activado")


@app.on_event("shutdown")
async def shutdown():
    mt5.shutdown()
    print("MT5 desconectado")


# ── ENDPOINTS ─────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Comprueba que el agente y MT5 están vivos."""
    terminal = mt5.terminal_info()
    if not terminal:
        return {"status": "mt5_disconnected", "error": str(mt5.last_error())}

    account = mt5.account_info()
    return {
        "status": "ok",
        "mt5_connected": True,
        "account": account.login,
        "balance": account.balance,
        "equity": account.equity,
        "server": account.server,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/order/open")
async def open_order(req: OrderRequest, x_agent_secret: str = Header(...)):
    """Abre una orden de mercado con SL y TP."""
    verify_secret(x_agent_secret)
    ensure_connected()

    # Dirección
    order_type = mt5.ORDER_TYPE_BUY if req.direction == "BUY" else mt5.ORDER_TYPE_SELL

    # Precio actual
    tick = mt5.symbol_info_tick(req.symbol)
    if not tick:
        raise HTTPException(status_code=400, detail=f"Símbolo {req.symbol} no disponible")

    price = tick.ask if req.direction == "BUY" else tick.bid

    # Construir la solicitud
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       req.symbol,
        "volume":       req.lot_size,
        "type":         order_type,
        "price":        price,
        "sl":           req.sl_price,
        "tp":           req.tp_price,
        "deviation":    20,           # slippage máximo en puntos
        "magic":        234000,       # identificador del bot
        "comment":      req.comment,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Error MT5 {result.retcode}: {result.comment}"
        )

    return {
        "status": "executed",
        "ticket": result.order,
        "symbol": req.symbol,
        "direction": req.direction,
        "lot_size": req.lot_size,
        "price": result.price,
        "sl": req.sl_price,
        "tp": req.tp_price,
        "comment": req.comment,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/order/close")
async def close_order(req: CloseRequest, x_agent_secret: str = Header(...)):
    """Cierra una posición por su número de ticket."""
    verify_secret(x_agent_secret)
    ensure_connected()

    # Buscar la posición
    position = mt5.positions_get(ticket=req.ticket)
    if not position:
        raise HTTPException(status_code=404, detail=f"Ticket {req.ticket} no encontrado")

    pos = position[0]
    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(pos.symbol)
    close_price = tick.bid if pos.type == 0 else tick.ask

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       pos.symbol,
        "volume":       pos.volume,
        "type":         close_type,
        "position":     req.ticket,
        "price":        close_price,
        "deviation":    20,
        "magic":        234000,
        "comment":      "Bot close",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Error al cerrar {result.retcode}: {result.comment}"
        )

    return {
        "status": "closed",
        "ticket": req.ticket,
        "symbol": pos.symbol,
        "profit": pos.profit,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/positions")
async def get_positions(x_agent_secret: str = Header(...)):
    """Devuelve todas las posiciones abiertas."""
    verify_secret(x_agent_secret)
    ensure_connected()

    positions = mt5.positions_get()
    if positions is None:
        return {"positions": [], "count": 0}

    result = []
    for p in positions:
        result.append({
            "ticket":     p.ticket,
            "symbol":     p.symbol,
            "direction":  "BUY" if p.type == 0 else "SELL",
            "lot_size":   p.volume,
            "open_price": p.price_open,
            "sl":         p.sl,
            "tp":         p.tp,
            "profit":     p.profit,
            "open_time":  datetime.fromtimestamp(p.time).isoformat(),
        })

    return {"positions": result, "count": len(result)}


@app.get("/account")
async def get_account(x_agent_secret: str = Header(...)):
    """Devuelve el estado actual de la cuenta."""
    verify_secret(x_agent_secret)
    ensure_connected()

    info = mt5.account_info()
    return {
        "login":          info.login,
        "balance":        info.balance,
        "equity":         info.equity,
        "margin":         info.margin,
        "free_margin":    info.margin_free,
        "profit":         info.profit,
        "server":         info.server,
        "currency":       info.currency,
        "leverage":       info.leverage,
        "drawdown_pct":   round((info.balance - info.equity) / info.balance * 100, 2)
                          if info.balance > 0 else 0,
    }


# ── ARRANQUE DEL SERVIDOR ─────────────────────────────────────
if __name__ == "__main__":
    print(f"🤖 MT5 Agent arrancando en http://localhost:{AGENT_PORT}")
    print(f"   Railway llamará a este agente para ejecutar órdenes")
    print(f"   Mantén esta ventana abierta mientras operas\n")
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
