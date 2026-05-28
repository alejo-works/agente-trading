"""
Recibe y valida los webhooks de TradingView.
TODO: Implementar en Fase 1.
"""
from fastapi import APIRouter, Request, HTTPException, Header

router = APIRouter()

@router.post("/signal")
async def receive_signal(request: Request, x_webhook_secret: str = Header(None)):
    payload = await request.json()
    return {"status": "received"}
