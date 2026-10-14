"""Position sizing: lots so that hitting the stop loses ~risk_percent of balance."""
import math


def lot_size(balance, risk_percent, sl_dist, contract_size=100,
             min_lot=0.01, lot_step=0.01, max_lot=50, usd_per_acct=1.0,
             max_risk_percent=100.0):
    """
    XAUUSD P/L per lot = price move ($) * contract_size (oz).
    Standard lot = 100 oz: a $1 move = $100 per lot, $1 per 0.01 lot.
    balance / results are in the ACCOUNT currency; usd_per_acct converts
    (e.g. 1.33 means 1 GBP = 1.33 USD; use 1.0 for a USD account).
    Returns dict: lots, risk (acct ccy), risk_pct, over_max, warning.
    """
    target = balance * risk_percent / 100.0
    loss_per_lot = sl_dist * contract_size / usd_per_acct  # in account currency
    if loss_per_lot <= 0 or balance <= 0:
        return {"lots": 0.0, "risk": 0.0, "risk_pct": 0.0, "over_max": True,
                "warning": "Invalid stop distance or balance"}
    lots = math.floor(target / loss_per_lot / lot_step + 1e-9) * lot_step
    lots = min(lots, max_lot)
    warning = None
    if lots < min_lot:
        lots = min_lot
        warning = "Account too small for target risk; using minimum lot."
    lots = round(lots, 2)
    risk = round(lots * loss_per_lot, 2)
    risk_pct = risk / balance * 100
    return {"lots": lots, "risk": risk, "risk_pct": round(risk_pct, 1),
            "over_max": risk_pct > max_risk_percent, "warning": warning}
