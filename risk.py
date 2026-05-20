"""Position sizing — the single most important file for protecting your account."""


def position_size(balance: float, risk_pct: float, stop_distance: float,
                  contract_size: float, min_lot: float, max_lot: float,
                  lot_step: float) -> float:
    """Lots sized so that hitting the stop loss costs ~risk_pct% of balance.

    stop_distance : price distance between entry and stop loss (in quote currency)
    contract_size : units per 1.0 lot (XAUUSD is typically 100 oz)

    Returns 0.0 when the safe size is below the broker's minimum lot — in that
    case the bot SKIPS the trade rather than over-risking. Never forces a trade.
    """
    if stop_distance <= 0 or contract_size <= 0 or balance <= 0:
        return 0.0

    risk_amount = balance * risk_pct / 100.0
    raw_lots = risk_amount / (stop_distance * contract_size)

    steps = int(raw_lots / lot_step)          # round DOWN to a valid lot step
    lots = steps * lot_step

    if lots < min_lot:
        return 0.0                            # too small to size safely -> skip
    return round(min(lots, max_lot), 2)
