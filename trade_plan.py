"""
Mechanical position sizing -- NOT financial advice. Given a direction, entry
price, and a stop price (the caller decides where the stop comes from --
a trend-line safety line or a POC reaction candle, see strategy_engine.py),
sizes the trade to config.RISK_BUDGET_DOLLARS at config.REWARD_RISK_RATIO.
"""

from dataclasses import dataclass

import config


@dataclass
class TradePlan:
    direction: str   # "BUY" or "SELL"
    entry: float
    stop: float
    target: float
    qty: float
    risk_dollars: float
    reward_risk: float
    atr: float = None   # the ATR value used in deriving the stop, for transparency


def build_trade_plan(direction, entry_price, stop_price, atr_value=None):
    if entry_price is None or stop_price is None:
        return None

    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share <= 0:
        return None

    # Fractional quantity (matches portfolio.json's existing fractional
    # share precision) lands risk almost exactly on the budget without
    # needing to search for a whole-share quantity inside a tolerance band.
    qty = round(config.RISK_BUDGET_DOLLARS / risk_per_share, config.TRADE_QTY_DECIMALS)
    if qty <= 0:
        return None

    target = (entry_price + config.REWARD_RISK_RATIO * risk_per_share if direction == "BUY"
              else entry_price - config.REWARD_RISK_RATIO * risk_per_share)

    return TradePlan(
        direction=direction,
        entry=round(entry_price, 2),
        stop=round(stop_price, 2),
        target=round(target, 2),
        qty=qty,
        risk_dollars=round(qty * risk_per_share, 2),
        reward_risk=config.REWARD_RISK_RATIO,
        atr=round(atr_value, 4) if atr_value is not None else None,
    )
