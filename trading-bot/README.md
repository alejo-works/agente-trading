# 🤖 Trading Bot Inteligente

Sistema de trading algorítmico con IA, RAG y Reinforcement Learning.

## Stack
- FastAPI · Claude API · ChromaDB · PostgreSQL · MetaTrader 5 · Telegram

## Arquitectura
Ver `docs/arquitectura.md`

## Fases
- [ ] Fase 0 — Setup inicial ← AQUÍ ESTAMOS
- [ ] Fase 1 — Señales Pine Script
- [ ] Fase 2 — Cerebro IA (RAG + Claude)
- [ ] Fase 3 — Conexión MT5
- [ ] Fase 4 — Panel de objetivos
- [ ] Fase 5 — Backtesting
- [ ] Fase 6 — RL Engine v1
- [ ] Fase 7 — Producción FTMO
- [ ] Fase 8 — Deep Learning v2

## Inicio rápido
```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn api.main:app --reload
```
