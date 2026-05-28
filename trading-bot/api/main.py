"""
Servidor principal FastAPI — Trading Bot Inteligente
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Trading Bot Inteligente",
    description="Sistema algorítmico con IA, RAG y RL",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "fase": "0 - Setup inicial"}


@app.get("/")
async def root():
    return {"bot": "Trading Bot Inteligente", "version": "0.1.0"}

# Fase 1: descomentar cuando estén listos los routers
# from api.webhook import router as webhook_router
# app.include_router(webhook_router, prefix="/webhook")
