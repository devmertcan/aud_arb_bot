from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal
from decimal import Decimal
from datetime import datetime

Number = Decimal

class Quote(BaseModel):
    ts: float                # unix epoch seconds
    bid: Number
    bid_sz: Number
    ask: Number
    ask_sz: Number

class BestBook(BaseModel):
    exchange: str
    pair: str
    quote: Quote

class Opportunity(BaseModel):
    ts: float
    pair: str
    buy_ex: str
    sell_ex: str
    buy_price: Number
    sell_price: Number
    qty: Number
    raw_bps: Number
    net_bps: Number
    profit_aud: Number
    confidence: float
    latency_ms: int = 0

class RuntimeConfig(BaseModel):
    max_trade_aud: Number
    min_profit_bps_after_fees: Number
    min_confidence: float
    stale_ms: int
    slippage_bps_buffer: Number
    rest_poll_ms: int
    csv_flush_every: int
    dashboard_host: str
    dashboard_port: int
