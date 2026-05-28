"""Schemas SQLAlchemy."""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Signal(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True)
    received_at = Column(DateTime, default=datetime.utcnow)
    pair = Column(String(10), nullable=False)
    direction = Column(String(5), nullable=False)
    timeframe = Column(String(5))
    confluence_score = Column(Integer)
    smc_signal = Column(Boolean, default=False)
    orb_signal = Column(Boolean, default=False)
    bb_rsi_signal = Column(Boolean, default=False)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    payload_raw = Column(JSON)
    ai_decision = Column(String(10))
    ai_reasoning = Column(Text)
    ai_probability = Column(Float)

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer)
    mt5_ticket = Column(Integer)
    pair = Column(String(10))
    direction = Column(String(5))
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    lot_size = Column(Float)
    opened_at = Column(DateTime)
    closed_at = Column(DateTime)
    close_price = Column(Float)
    pnl_usd = Column(Float)
    pnl_pct = Column(Float)
    result = Column(String(10))
    confluence_score = Column(Integer)
    session = Column(String(20))
    market_context = Column(JSON)
