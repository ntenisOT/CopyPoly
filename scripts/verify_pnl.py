"""Check if Polymarket uses 'size' (shares) instead of 'usdcSize' for PnL."""
import httpx
import asyncio
from collections import defaultdict

WALLET = "0x56687bf447db6ffa42ffe2204a05edaa20f55839"
PM_PNL = 22053934


async def main():
    all_events = []
    offset = 0
    async with httpx.AsyncClient() as c:
        while True:
            r = await c.get(
                "https://data-api.polymarket.com/v1/activity",
                params={"user": WALLET, "limit": 100, "offset": offset},
                timeout=30,
            )
            events = [e for e in r.json() if isinstance(e, dict)]
            all_events.extend(events)
            if len(events) < 100:
                break
            offset += 100

    # Try PnL using "size" (shares) for REDEEM instead of usdcSize
    # Winning shares redeem at $1.00 each, so size = payout in USDC
    buy_usdc = sum(float(e.get("usdcSize", 0) or 0) for e in all_events if e.get("type") == "TRADE" and e.get("side") == "BUY")
    sell_usdc = sum(float(e.get("usdcSize", 0) or 0) for e in all_events if e.get("type") == "TRADE" and e.get("side") == "SELL")

    redeem_usdc_size = sum(float(e.get("usdcSize", 0) or 0) for e in all_events if e.get("type") == "REDEEM")
    redeem_size = sum(float(e.get("size", 0) or 0) for e in all_events if e.get("type") == "REDEEM")

    merge_usdc = sum(float(e.get("usdcSize", 0) or 0) for e in all_events if e.get("type") == "MERGE")
    merge_size = sum(float(e.get("size", 0) or 0) for e in all_events if e.get("type") == "MERGE")

    reward_usdc = sum(float(e.get("usdcSize", 0) or 0) for e in all_events if e.get("type") == "REWARD")

    # Formula 1: PnL = sell + redeem(usdcSize) + reward - buy - merge(usdcSize)
    pnl1 = sell_usdc + redeem_usdc_size + reward_usdc - buy_usdc - merge_usdc

    # Formula 2: PnL = sell + redeem(size) + reward - buy - merge(size)
    pnl2 = sell_usdc + redeem_size + reward_usdc - buy_usdc - merge_size

    # Formula 3: Polymarket might compute PnL per-position:
    # For each buy: paid X for shares with face value Y at price P
    # PnL per buy = face_value * resolved_payout - cost
    # Where face_value = size, cost = usdcSize
    buy_size = sum(float(e.get("size", 0) or 0) for e in all_events if e.get("type") == "TRADE" and e.get("side") == "BUY")
    # If winning: PnL = shares_bought * 1.0 - cost_paid
    # But we need to know which trades won. Let's try: PnL = redeem - cost_of_redeemed_markets
    
    by_cond = defaultdict(lambda: {"buy_usdc": 0.0, "buy_shares": 0.0, "redeem_shares": 0.0, "merge_usdc": 0.0, "title": ""})
    for e in all_events:
        cid = e.get("conditionId", "?")
        if e.get("type") == "TRADE" and e.get("side") == "BUY":
            by_cond[cid]["buy_usdc"] += float(e.get("usdcSize", 0) or 0)
            by_cond[cid]["buy_shares"] += float(e.get("size", 0) or 0)
            by_cond[cid]["title"] = (e.get("title") or "")[:50]
        elif e.get("type") == "REDEEM":
            by_cond[cid]["redeem_shares"] += float(e.get("size", 0) or 0)
        elif e.get("type") == "MERGE":
            by_cond[cid]["merge_usdc"] += float(e.get("usdcSize", 0) or 0)

    # Formula 3: Per-condition PnL = shares_redeemed - cost_of_that_condition
    pnl3 = 0.0
    for cid, d in by_cond.items():
        # Redeemed shares are worth $1 each
        pnl_cond = d["redeem_shares"] - d["buy_usdc"] - d["merge_usdc"]
        pnl3 += pnl_cond

    print(f"Redemption comparison:")
    print(f"  redeem usdcSize: ${redeem_usdc_size:,.0f}")
    print(f"  redeem size:     ${redeem_size:,.0f}")
    print(f"  merge usdcSize:  ${merge_usdc:,.0f}")
    print(f"  merge size:      ${merge_size:,.0f}")
    print()
    print(f"Formula 1 (usdcSize for all):   ${pnl1:,.0f}  (diff: ${abs(pnl1 - PM_PNL):,.0f})")
    print(f"Formula 2 (size for redeem):     ${pnl2:,.0f}  (diff: ${abs(pnl2 - PM_PNL):,.0f})")
    print(f"Formula 3 (per-condition):       ${pnl3:,.0f}  (diff: ${abs(pnl3 - PM_PNL):,.0f})")
    print(f"Polymarket:                      ${PM_PNL:,}")
    print()

    # Check if redeem_usdc_size == redeem_size (they should be for 1:1 redemption)
    print(f"redeem_usdc_size == redeem_size? {redeem_usdc_size == redeem_size}")
    print(f"buy shares: {buy_size:,.0f}, buy USDC: {buy_usdc:,.0f}")
    print(f"Avg buy price: {buy_usdc / buy_size:.4f}" if buy_size > 0 else "N/A")


asyncio.run(main())
