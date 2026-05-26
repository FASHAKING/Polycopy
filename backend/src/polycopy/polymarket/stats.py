"""Derive trader performance metrics from Polymarket positions.

These are intentionally simple and approximate. Win rate from the positions
endpoint mixes open and resolved bets, so we treat resolved positions
(redeemable, or priced at the 0/1 extremes) as the win/loss sample and fall
back to all positions when too few have resolved. Phase 6 refines this with a
dedicated resolved-positions history.
"""

from collections import defaultdict
from dataclasses import dataclass

from polycopy.polymarket.data_api import Activity, Position

_RESOLVED_EPS = 0.02  # cur_price within 2c of 0 or 1 => effectively settled


def _is_resolved(p: Position) -> bool:
    return p.redeemable or p.cur_price <= _RESOLVED_EPS or p.cur_price >= 1 - _RESOLVED_EPS


@dataclass
class TraderStats:
    win_rate: float | None  # 0..1, None if no usable sample
    roi: float | None  # net pnl / capital deployed
    trades_count: int  # positions in the win/loss sample
    volume_usd: float  # capital deployed across all positions

    @property
    def win_rate_pct(self) -> float | None:
        return None if self.win_rate is None else round(self.win_rate * 100, 1)


def compute_stats(positions: list[Position], min_sample: int = 5) -> TraderStats:
    volume = sum(max(p.initial_value, 0.0) for p in positions)

    resolved = [p for p in positions if _is_resolved(p)]
    sample = resolved if len(resolved) >= min_sample else positions
    sample = [p for p in sample if p.initial_value > 0]

    if not sample:
        return TraderStats(win_rate=None, roi=None, trades_count=0, volume_usd=volume)

    wins = sum(1 for p in sample if p.cash_pnl > 0)
    win_rate = wins / len(sample)

    deployed = sum(p.initial_value for p in sample)
    net_pnl = sum(p.cash_pnl for p in sample)
    roi = (net_pnl / deployed) if deployed > 0 else None

    return TraderStats(
        win_rate=win_rate,
        roi=roi,
        trades_count=len(sample),
        volume_usd=volume,
    )


_SHARES_EPS = 1.0  # net share balance below this => position considered fully exited


@dataclass
class _Market:
    cash: float = 0.0  # signed: buys negative, sells/redeems positive
    bought_usd: float = 0.0
    shares: dict | None = None
    redeemed: bool = False


def compute_realized_stats(activities: list[Activity]) -> TraderStats:
    """Reconstruct realized win-rate and ROI from a trader's activity feed.

    Net cashflow is accumulated per market (conditionId): BUY is cash out,
    SELL and REDEEM are cash in. A market counts toward the win/loss sample
    once it's *settled* — either redeemed, or fully exited (net share balance
    ~0). Open positions are excluded. Win = positive net cashflow.

    REDEEMs alone would overstate win rate (losing positions resolve to $0 and
    generate no redeem), so cost basis from the buy side is essential — markets
    whose buys fall outside the fetched window are skipped as incomplete.
    """
    markets: dict[str, _Market] = defaultdict(lambda: _Market(shares=defaultdict(float)))

    for a in activities:
        m = markets[a.condition_id]
        side = (a.side or "").upper()
        if a.type == "TRADE" and side == "BUY":
            m.cash -= a.usdc_size
            m.bought_usd += a.usdc_size
            m.shares[a.outcome_index] += a.size
        elif a.type == "TRADE" and side == "SELL":
            m.cash += a.usdc_size
            m.shares[a.outcome_index] -= a.size
        elif a.type == "REDEEM":
            m.cash += a.usdc_size
            m.redeemed = True

    settled: list[_Market] = []
    for m in markets.values():
        net_shares = sum(abs(x) for x in m.shares.values())
        is_settled = m.redeemed or net_shares < _SHARES_EPS
        if is_settled and m.bought_usd > 0:
            settled.append(m)

    if not settled:
        return TraderStats(win_rate=None, roi=None, trades_count=0, volume_usd=0.0)

    wins = sum(1 for m in settled if m.cash > 0)
    win_rate = wins / len(settled)
    deployed = sum(m.bought_usd for m in settled)
    net = sum(m.cash for m in settled)
    roi = (net / deployed) if deployed > 0 else None

    return TraderStats(
        win_rate=win_rate,
        roi=roi,
        trades_count=len(settled),
        volume_usd=deployed,
    )
