"""Trader Scoring Engine — Composite ranking system.

Computes a weighted composite score for each trader based on:
  w₁ × PnL (normalized)
  w₂ × Win Rate
  w₃ × Consistency (multi-period performance)
  w₄ × Volume (normalized, as a proxy for confidence)
  w₅ × ROI (PnL / Volume efficiency)

Weights are configurable via app_config table. Higher score = better copy candidate.
Score range: 0.0 to 1.0 (after normalization).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from copypoly.db.models import AppConfig, LeaderboardSnapshot, Trader, TraderPosition
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)


# ----------------------------------------------------------------
# Score Component Weights (defaults, overrideable via app_config)
# ----------------------------------------------------------------
DEFAULT_WEIGHTS = {
    "pnl": 0.30,
    "win_rate": 0.20,
    "consistency": 0.20,
    "volume": 0.10,
    "roi": 0.20,
}


# ----------------------------------------------------------------
# Eligibility Filters (defaults, overrideable via app_config)
# ----------------------------------------------------------------
DEFAULT_FILTERS = {
    "min_pnl": -1e18,              # No PnL filter — score everyone (gems may have low all-time PnL)
    "min_trades": 0,               # Minimum total trades (relaxed until we crawl trade history)
    "min_periods": 1,              # Must appear in at least 1 leaderboard period
    "min_volume": 0.0,             # Minimum total volume (relaxed: some traders have 0 vol on daily)
    "max_concentration": 0.80,     # Max % of PnL from a single market
    "require_recent_activity": 7,  # Must have activity in last N days
}


@dataclass
class TraderScore:
    """Computed score for a single trader."""

    wallet: str
    username: str | None = None

    # Raw metrics
    pnl_all: float = 0.0
    pnl_month: float = 0.0
    pnl_week: float = 0.0
    pnl_day: float = 0.0
    total_volume: float = 0.0
    total_trades: int = 0
    win_rate: float | None = None
    num_periods: int = 0  # How many leaderboard periods they appear in

    # Normalized components (0.0 → 1.0)
    pnl_score: float = 0.0
    win_rate_score: float = 0.0
    consistency_score: float = 0.0
    volume_score: float = 0.0
    roi_score: float = 0.0

    # Final composite
    composite_score: float = 0.0

    # Metadata
    eligible: bool = True
    reject_reasons: list[str] = field(default_factory=list)


async def score_all_traders() -> list[TraderScore]:
    """Score all known traders and update scores in the database.

    Steps:
        1. Load weights and filters from app_config
        2. Gather raw metrics from snapshots + positions
        3. Apply eligibility filters
        4. Normalize metrics relative to the cohort
        5. Compute weighted composite score
        6. Update traders table with new scores

    Returns:
        Sorted list of TraderScore objects (best first).
    """
    weights = await _load_weights()
    filters = await _load_filters()

    log.info("scoring_traders", weights=weights, filters=filters)

    # Step 1: Gather raw metrics for ALL traders
    raw_scores = await _gather_raw_metrics()

    if not raw_scores:
        log.warning("no_traders_to_score")
        return []

    log.info("raw_metrics_gathered", trader_count=len(raw_scores))

    # Step 2: Apply eligibility filters
    for score in raw_scores:
        _apply_filters(score, filters)

    eligible = [s for s in raw_scores if s.eligible]
    log.info(
        "eligibility_applied",
        total=len(raw_scores),
        eligible=len(eligible),
        filtered=len(raw_scores) - len(eligible),
    )

    if not eligible:
        log.warning("no_eligible_traders")
        return raw_scores

    # Step 3: Normalize metrics relative to eligible cohort
    _normalize_scores(eligible)

    # Step 4: Compute weighted composite
    for score in eligible:
        score.composite_score = (
            weights["pnl"] * score.pnl_score
            + weights["win_rate"] * score.win_rate_score
            + weights["consistency"] * score.consistency_score
            + weights["volume"] * score.volume_score
            + weights["roi"] * score.roi_score
        )

    # Step 5: Sort by composite score (descending)
    eligible.sort(key=lambda s: s.composite_score, reverse=True)

    # Step 6: Persist scores to database
    await _persist_scores(eligible)

    log.info(
        "scoring_complete",
        top_trader=eligible[0].username if eligible else None,
        top_score=round(eligible[0].composite_score, 4) if eligible else 0,
        scored_count=len(eligible),
    )

    return eligible


async def get_top_traders(limit: int = 10) -> list[TraderScore]:
    """Get the top N traders by composite score (from database).

    This reads persisted scores — no recomputation.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(Trader)
            .where(Trader.is_watched == True)  # noqa: E712
            .order_by(Trader.composite_score.desc())
            .limit(limit)
        )
        traders = result.scalars().all()

        return [
            TraderScore(
                wallet=t.wallet,
                username=t.username,
                composite_score=float(t.composite_score or 0),
                pnl_all=float(t.best_pnl_all_time or 0),
                win_rate=float(t.win_rate) if t.win_rate else None,
                total_trades=t.total_trades or 0,
            )
            for t in traders
        ]


# ================================================================
# Internal helpers
# ================================================================

async def _load_weights() -> dict[str, float]:
    """Load scoring weights from app_config, falling back to defaults."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(AppConfig.value).where(AppConfig.key == "scoring_weights")
        )
        row = result.scalar()

    if row and isinstance(row, dict):
        return {k: float(row.get(k, v)) for k, v in DEFAULT_WEIGHTS.items()}
    return dict(DEFAULT_WEIGHTS)


async def _load_filters() -> dict[str, float]:
    """Load eligibility filters from app_config, falling back to defaults."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(AppConfig.value).where(AppConfig.key == "scoring_filters")
        )
        row = result.scalar()

    if row and isinstance(row, dict):
        return {k: float(row.get(k, v)) for k, v in DEFAULT_FILTERS.items()}
    return {k: float(v) for k, v in DEFAULT_FILTERS.items()}


async def _gather_raw_metrics() -> list[TraderScore]:
    """Build raw TraderScore objects from database data."""
    scores: dict[str, TraderScore] = {}

    async with async_session_factory() as session:
        # Get all traders with their leaderboard snapshots
        result = await session.execute(
            select(Trader)
        )
        traders = result.scalars().all()

        for trader in traders:
            ts = TraderScore(
                wallet=trader.wallet,
                username=trader.username,
                total_trades=trader.total_trades or 0,
                win_rate=float(trader.win_rate) if trader.win_rate else None,
            )
            scores[trader.wallet] = ts

        # Get best PnL per period from snapshots
        for period_key, attr in [
            ("all", "pnl_all"),
            ("month", "pnl_month"),
            ("week", "pnl_week"),
            ("day", "pnl_day"),
        ]:
            result = await session.execute(
                text("""
                    SELECT trader_wallet, MAX(pnl) as best_pnl, MAX(volume) as best_vol
                    FROM leaderboard_snapshots
                    WHERE period = :period
                    GROUP BY trader_wallet
                """),
                {"period": period_key},
            )

            for row in result.fetchall():
                wallet = row[0]
                if wallet in scores:
                    setattr(scores[wallet], attr, float(row[1] or 0))
                    if attr == "pnl_all":
                        scores[wallet].total_volume = float(row[2] or 0)

        # Count how many periods each trader appears in
        result = await session.execute(
            text("""
                SELECT trader_wallet, COUNT(DISTINCT period) as num_periods
                FROM leaderboard_snapshots
                GROUP BY trader_wallet
            """)
        )
        for row in result.fetchall():
            if row[0] in scores:
                scores[row[0]].num_periods = row[1]

    return list(scores.values())


def _apply_filters(score: TraderScore, filters: dict[str, float]) -> None:
    """Check if a trader meets eligibility criteria."""
    score.eligible = True
    score.reject_reasons = []

    if score.pnl_all < filters["min_pnl"]:
        score.eligible = False
        score.reject_reasons.append(f"PnL {score.pnl_all:.0f} < {filters['min_pnl']:.0f}")

    if score.total_trades < filters["min_trades"]:
        score.eligible = False
        score.reject_reasons.append(f"Trades {score.total_trades} < {filters['min_trades']:.0f}")

    if score.num_periods < filters["min_periods"]:
        score.eligible = False
        score.reject_reasons.append(f"Periods {score.num_periods} < {filters['min_periods']:.0f}")

    if score.total_volume < filters["min_volume"]:
        score.eligible = False
        score.reject_reasons.append(f"Volume {score.total_volume:.0f} < {filters['min_volume']:.0f}")


def _normalize_scores(scores: list[TraderScore]) -> None:
    """Normalize all metrics relative to the cohort using min-max scaling."""

    def _min_max(values: list[float]) -> tuple[float, float]:
        mn, mx = min(values), max(values)
        return (mn, mx) if mx > mn else (mn, mn + 1)

    # PnL normalization (use log scale for better distribution)
    import math

    pnl_values = [s.pnl_all for s in scores]
    pnl_min, pnl_max = _min_max(pnl_values)
    for s in scores:
        s.pnl_score = (s.pnl_all - pnl_min) / (pnl_max - pnl_min)

    # Win rate (already 0-1 if available, else penalize)
    for s in scores:
        if s.win_rate is not None:
            s.win_rate_score = min(max(s.win_rate, 0), 1)
        else:
            s.win_rate_score = 0.5  # Neutral if unknown

    # Consistency: normalized count of periods (1-4 → 0-1)
    max_periods = max(s.num_periods for s in scores)
    for s in scores:
        s.consistency_score = s.num_periods / max_periods if max_periods > 0 else 0

    # Volume normalization
    vol_values = [s.total_volume for s in scores]
    vol_min, vol_max = _min_max(vol_values)
    for s in scores:
        s.volume_score = (s.total_volume - vol_min) / (vol_max - vol_min)

    # ROI: PnL / Volume ratio (capped at 1.0)
    for s in scores:
        if s.total_volume > 0:
            roi = s.pnl_all / s.total_volume
            s.roi_score = min(roi, 1.0)
        else:
            s.roi_score = 0.0


async def _persist_scores(scores: list[TraderScore]) -> None:
    """Write computed scores back to the traders table."""
    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        for score in scores:
            await session.execute(
                update(Trader)
                .where(Trader.wallet == score.wallet)
                .values(
                    composite_score=round(score.composite_score, 4),
                    best_pnl_all_time=score.pnl_all,
                    best_pnl_monthly=score.pnl_month,
                    best_pnl_weekly=score.pnl_week,
                    best_pnl_daily=score.pnl_day,
                    last_scored_at=now,
                    updated_at=now,
                )
            )

        await session.commit()

    log.info("scores_persisted", count=len(scores))
