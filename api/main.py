"""
Servidor principal FastAPI — Trading Bot Inteligente
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config.settings import settings
from api.webhook import router as webhook_router
from execution.telegram_bot import send_telegram_startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup y shutdown del servidor."""
    logger.info("🚀 Trading Bot arrancando...")
    await send_telegram_startup()
    yield
    logger.info("🛑 Trading Bot apagándose...")


app = FastAPI(
    title="Trading Bot Inteligente",
    description="Sistema algorítmico con IA, RAG y RL",
    version="0.2.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Routers
app.include_router(webhook_router, prefix="/webhook", tags=["Webhooks"])


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.2.0",
        "environment": settings.environment,
        "fase": "1 - Pine Scripts + Webhook"
    }


@app.get("/")
async def root():
    return {
        "bot": "Trading Bot Inteligente",
        "endpoints": {
            "health": "/health",
            "webhook": "/webhook/signal",
            "test": "/webhook/test"
        }
    }
