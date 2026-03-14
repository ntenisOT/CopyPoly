"""
Polymarket PnL Calculator — exact replica of pnl-subgraph logic.

Source: github.com/Polymarket/polymarket-subgraph/tree/main/pnl-subgraph/src/
"""

COLLATERAL_SCALE = 10**6  # 6-decimal USDC
FIFTY_CENTS = 500_000     # 0.50 in scaled form


class PositionTracker:
    """Tracks a single token position (one side of a market)."""

    def __init__(self, token_id: str = ""):
        self.token_id = token_id
        self.amount: int = 0           # current holdings (scaled)
        self.avg_price: int = 0        # weighted avg buy price (scaled)
        self.realized_pnl: int = 0     # realized PnL (scaled)
        self.total_bought: int = 0     # total shares ever "bought" (scaled)

    def buy(self, price: int, amount: int):
        """Process a buy event. price and amount are scaled integers."""
        if amount <= 0:
            return
        # Weighted avg price: (avgPrice * current + price * new) / (current + new)
        numerator = self.avg_price * self.amount + price * amount
        denominator = self.amount + amount
        if denominator > 0:
            self.avg_price = numerator // denominator
        self.amount += amount
        self.total_bought += amount

    def sell(self, price: int, amount: int):
        """Process a sell event. price and amount are scaled integers."""
        # Cap at current holdings (matches subgraph adjustedAmount logic)
        adjusted = min(amount, self.amount)
        if adjusted <= 0:
            return
        # realizedPnl += adjusted * (price - avgPrice) / COLLATERAL_SCALE
        delta_pnl = adjusted * (price - self.avg_price) // COLLATERAL_SCALE
        self.realized_pnl += delta_pnl
        self.amount -= adjusted

    # ── Convenience for float inputs ──
    def buy_f(self, price: float, shares: float):
        self.buy(int(price * COLLATERAL_SCALE), int(shares * COLLATERAL_SCALE))

    def sell_f(self, price: float, shares: float):
        self.sell(int(price * COLLATERAL_SCALE), int(shares * COLLATERAL_SCALE))

    # ── Read values as floats ──
    @property
    def amount_f(self) -> float:
        return self.amount / COLLATERAL_SCALE

    @property
    def avg_price_f(self) -> float:
        return self.avg_price / COLLATERAL_SCALE

    @property
    def realized_pnl_f(self) -> float:
        return self.realized_pnl / COLLATERAL_SCALE

    @property
    def total_bought_f(self) -> float:
        return self.total_bought / COLLATERAL_SCALE

    def __repr__(self):
        return (f"Position(amount={self.amount_f:.6f}, avgPrice={self.avg_price_f:.6f}, "
                f"pnl={self.realized_pnl_f:.6f}, totalBought={self.total_bought_f:.6f})")


def process_order_fill(trackers: dict, event: dict):
    """
    Process an OrderFilled event from the orderbook subgraph.
    
    Important: the pnl-subgraph only tracks the MAKER's perspective.
    'account' = maker address. 'the taker is always the exchange!'
    
    If makerAssetId == "0": maker is BUYING (giving USDC, getting tokens)
      - account = maker, side = BUY
      - positionId = takerAssetId, baseAmount = takerAmountFilled, quoteAmount = makerAmountFilled
    Else: maker is SELLING (giving tokens, getting USDC)
      - account = maker, side = SELL
      - positionId = makerAssetId, baseAmount = makerAmountFilled, quoteAmount = takerAmountFilled
    """
    maker_asset = event["makerAssetId"]
    taker_asset = event["takerAssetId"]
    maker_amount = int(event["makerAmountFilled"])
    taker_amount = int(event["takerAmountFilled"])

    if maker_asset == "0":
        # Maker is BUYING: gave USDC, got tokens
        position_id = taker_asset
        base_amount = taker_amount    # shares
        quote_amount = maker_amount   # USDC
        side = "BUY"
    else:
        # Maker is SELLING: gave tokens, got USDC
        position_id = maker_asset
        base_amount = maker_amount    # shares
        quote_amount = taker_amount   # USDC
        side = "SELL"

    # price = quoteAmount * COLLATERAL_SCALE / baseAmount
    if base_amount > 0:
        price = quote_amount * COLLATERAL_SCALE // base_amount
    else:
        return

    if position_id not in trackers:
        trackers[position_id] = PositionTracker(position_id)

    if side == "BUY":
        trackers[position_id].buy(price, base_amount)
    else:
        trackers[position_id].sell(price, base_amount)


def process_merge(trackers: dict, condition_position_ids: list, amount: int):
    """Merge = SELL at $0.50 for both outcomes."""
    for pid in condition_position_ids:
        if pid not in trackers:
            trackers[pid] = PositionTracker(pid)
        trackers[pid].sell(FIFTY_CENTS, amount)


def process_split(trackers: dict, condition_position_ids: list, amount: int):
    """Split = BUY at $0.50 for both outcomes."""
    for pid in condition_position_ids:
        if pid not in trackers:
            trackers[pid] = PositionTracker(pid)
        trackers[pid].buy(FIFTY_CENTS, amount)


def process_redeem(trackers: dict, condition_position_ids: list,
                   payout_numerators: list, payout_denominator: int,
                   amounts: list = None):
    """Redeem = SELL at resolution price for remaining amount."""
    for i, pid in enumerate(condition_position_ids):
        if pid not in trackers:
            trackers[pid] = PositionTracker(pid)
        tracker = trackers[pid]
        # Amount to redeem = what user holds (for standard CTF)
        # or specified amounts (for NegRisk)
        redeem_amount = amounts[i] if amounts else tracker.amount
        if payout_denominator > 0:
            price = payout_numerators[i] * COLLATERAL_SCALE // payout_denominator
        else:
            price = 0
        tracker.sell(price, redeem_amount)
