"""
Configuración central del Trading Bot.
Todos los parámetros de objetivos, riesgo y ejecución están aquí.
"""
from pydantic_settings import BaseSettings
from pydantic import computed_field
from typing import Literal


class Settings(BaseSettings):
    # Entorno
    environment: Literal["development", "production"] = "development"
    webhook_secret: str = "cambia_esto_por_algo_seguro"

    # APIs externas
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    database_url: str = "postgresql://localhost/tradingbot"

    # MetaTrader 5
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = ""

    # OBJETIVOS DE TRADING
    account_size: float = 10_000.0
    monthly_target_usd: float = 5_000.0

    @computed_field
    @property
    def daily_target_usd(self) -> float:
        return self.monthly_target_usd / 20

    @computed_field
    @property
    def daily_max_profit_usd(self) -> float:
        return self.daily_target_usd * 2

    @computed_field
    @property
    def daily_max_loss_usd(self) -> float:
        return self.account_size * 0.02

    # REGLAS FTMO — hardcoded, NO modificar
    max_daily_drawdown_pct: float = 5.0
    max_total_drawdown_pct: float = 10.0
    profit_target_pct: float = 10.0

    # GESTIÓN DE RIESGO
    risk_per_trade_pct: float = 1.0
    max_trades_per_day: int = 3
    min_rr_ratio: float = 1.5

    @computed_field
    @property
    def risk_per_trade_usd(self) -> float:
        return self.account_size * (self.risk_per_trade_pct / 100)

    # MODO DE EJECUCIÓN
    execution_mode: Literal["manual", "semi-auto", "full-auto"] = "semi-auto"

    # PARES ACTIVOS
    active_pairs: list = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]
    priority_pair: str = "XAUUSD"

    # MODELO IA
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 1000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
