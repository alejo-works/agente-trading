"""
Servidor principal FastAPI — Trading Bot Inteligente
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config.settings import settings
from api.webhook import router as webhook_router
from execution.telegram_bot import send_telegram_startup
from rag.indexer import index_all_documents
from execution.mt5_client import mt5_client
from execution.daily_manager import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup y shutdown del servidor."""
    logger.info("Arrancando Trading Bot...")
    index_all_documents()
    asyncio.create_task(mt5_client.start_monitor())
    asyncio.create_task(start_scheduler())
    await send_telegram_startup()
    yield
    logger.info("Trading Bot apagandose...")


app = FastAPI(
    title="Trading Bot Inteligente",
    description="Sistema algoritmico con IA, RAG y RL",
    version="0.4.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(webhook_router, prefix="/webhook", tags=["Webhooks"])


@app.get("/health")
async def health():
    from execution.daily_manager import get_state_summary
    state = get_state_summary()
    return {
        "status":      "ok",
        "version":     "0.4.0",
        "environment": settings.environment,
        "fase":        "4 - Panel de objetivos",
        "bot_paused":  state["paused"],
        "pnl_today":   state["pnl_today"],
        "trades_today": state["trades_today"],
    }


@app.get("/")
async def root():
    return {
        "bot": "Trading Bot Inteligente",
        "endpoints": {
            "health":  "/health",
            "webhook": "/webhook/signal",
            "test":    "/webhook/test"
        }
    }