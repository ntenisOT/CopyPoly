"""
PHASE 2: Verify FULL ACCOUNT — all 22 positions for Theo4.
Processes ALL on-chain events through the PnL calculator and compares to PM.

Key rules from source code:
- Only MAKER fills count (pnl-subgraph: 'the taker is always the exchange!')
- MERGE = SELL at $0.50 for both YES/NO
- SPLIT = BUY at $0.50 for both YES/NO
- REDEEM = SELL at resolution price (curPrice from closed-positions)
- NegRisk conversions handled separately
"""
import asyncio
import httpx
from collections import defaultdict
from pnl_calculator import PositionTracker, COLLATERAL_SCALE, FIFTY_CENTS

WALLET = "0x56687bf447db6ffa42ffe2204a05edaa20f55839"
ORDERBOOK_SG = "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/orderbook-subgraph/0.0.1/gn"
ACTIVITY_SG  = "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/activity-subgraph/0.0.3/gn"


def parse_log_index(event_id: str) -> int:
    parts = event_id.split("_")
    if len(parts) > 1:
        try:
            return int(parts[-1], 16)
        except ValueError:
            pass
    return 0


async def fetch_maker_fills(client):
    """Fetch ALL maker fills from orderbook subgraph."""
    events = []
    last_id = ""
    page = 0
    while True:
        q = f"""{{ orderFilledEvents(first:1000, orderBy:id, orderDirection:asc,
          where:{{maker:"{WALLET.lower()}", id_gt:"{last_id}"}}) {{
          id timestamp makerAssetId takerAssetId makerAmountFilled takerAmountFilled }} }}"""
        resp = await client.post(ORDERBOOK_SG, json={"query": q}, timeout=30)
        data = resp.json()["data"]["orderFilledEvents"]
        if not data:
            break
        for e in data:
            events.append((int(e["timestamp"]), parse_log_index(e["id"]), "FILL", e))
        last_id = data[-1]["id"]
        page += 1
        if page % 5 == 0:
            print(f"    page {page}... ({len(events)} fills)")
        if len(data) < 1000:
            break
        await asyncio.sleep(0.1)
    print(f"    Total: {len(events)} maker fills")
    return events


async def fetch_merges(client):
    """Fetch ALL merges from activity subgraph."""
    events = []
    last_id = ""
    while True:
        q = f"""{{ merges(first:1000, where:{{stakeholder:"{WALLET.lower()}", id_gt:"{last_id}"}}, orderBy:id) {{
          id timestamp condition amount }} }}"""
        resp = await client.post(ACTIVITY_SG, json={"query": q}, timeout=15)
        data = resp.json()["data"]["merges"]
        if not data:
            break
        for m in data:
            events.append((int(m["timestamp"]), parse_log_index(m["id"]), "MERGE", m))
        last_id = data[-1]["id"]
        if len(data) < 1000:
            break
    print(f"    Total: {len(events)} merges")
    return events


async def fetch_splits(client):
    """Fetch ALL splits."""
    events = []
    last_id = ""
    while True:
        q = f"""{{ splits(first:1000, where:{{stakeholder:"{WALLET.lower()}", id_gt:"{last_id}"}}, orderBy:id) {{
          id timestamp condition amount }} }}"""
        resp = await client.post(ACTIVITY_SG, json={"query": q}, timeout=15)
        data = resp.json()["data"]["splits"]
        if not data:
            break
        for s in data:
            events.append((int(s["timestamp"]), parse_log_index(s["id"]), "SPLIT", s))
        last_id = data[-1]["id"]
        if len(data) < 1000:
            break
    print(f"    Total: {len(events)} splits")
    return events


async def fetch_redemptions(client, conditions):
    """Fetch redemptions per condition (wallet-level queries timeout)."""
    events = []
    for cond in conditions:
        resp = await client.post(ACTIVITY_SG, json={"query": f"""{{
          redemptions(first:100, where:{{redeemer:"{WALLET.lower()}", condition:"{cond}"}}) {{
            id timestamp condition payout }} }}"""}, timeout=10)
        data = resp.json()
        if "data" in data:
            for rd in data["data"]["redemptions"]:
                events.append((int(rd["timestamp"]), parse_log_index(rd["id"]), "REDEEM", rd))
    print(f"    Total: {len(events)} redemptions")
    return events


async def main():
    async with httpx.AsyncClient() as client:
        # ── 1. Get PM official data ──
        print("Fetching PM closed-positions...")
        r = await client.get("https://data-api.polymarket.com/closed-positions",
                             params={"user": WALLET, "limit": 100}, timeout=10)
        all_pos = r.json()

        r_lb = await client.get("https://data-api.polymarket.com/v1/leaderboard",
                                params={"timePeriod": "all", "user": WALLET}, timeout=10)
        lb_pnl = float(r_lb.json()[0].get("pnl", 0))

        # Build lookup: asset -> PM data, condition -> [asset_ids]
        pm_by_asset = {}
        cond_to_assets = defaultdict(list)
        for p in all_pos:
            pm_by_asset[p["asset"]] = p
            cond = p.get("conditionId", "")
            cond_to_assets[cond].append(p["asset"])
            if p.get("oppositeAsset"):
                cond_to_assets[cond].append(p["oppositeAsset"])

        # Deduplicate
        for c in cond_to_assets:
            cond_to_assets[c] = list(set(cond_to_assets[c]))

        print(f"  {len(all_pos)} positions, {len(cond_to_assets)} conditions")

        # ── 2. Fetch all events ──
        print("\nFetching maker fills...")
        fill_events = await fetch_maker_fills(client)

        print("Fetching merges...")
        merge_events = await fetch_merges(client)

        print("Fetching splits...")
        split_events = await fetch_splits(client)

        print("Fetching redemptions...")
        redeem_events = await fetch_redemptions(client, cond_to_assets.keys())

    # ── 3. Combine and sort ALL events ──
    all_events = fill_events + merge_events + split_events + redeem_events
    all_events.sort(key=lambda x: (x[0], x[1]))
    print(f"\nTotal events: {len(all_events)}")

    # ── 4. Process through calculator ──
    trackers = {}  # asset_id -> PositionTracker

    for ts, log_idx, etype, raw in all_events:
        if etype == "FILL":
            maker_asset = raw["makerAssetId"]
            taker_asset = raw["takerAssetId"]
            maker_amount = int(raw["makerAmountFilled"])
            taker_amount = int(raw["takerAmountFilled"])

            if maker_asset == "0":
                # BUY: gave USDC, got tokens
                pos_id = taker_asset
                base = taker_amount
                quote = maker_amount
            else:
                # SELL: gave tokens, got USDC
                pos_id = maker_asset
                base = maker_amount
                quote = taker_amount

            if base <= 0:
                continue
            price = quote * COLLATERAL_SCALE // base

            if pos_id not in trackers:
                trackers[pos_id] = PositionTracker(pos_id)

            if maker_asset == "0":
                trackers[pos_id].buy(price, base)
            else:
                trackers[pos_id].sell(price, base)

        elif etype == "MERGE":
            cond = raw["condition"]
            amount = int(raw["amount"])
            assets = cond_to_assets.get(cond, [])
            for asset in assets:
                if asset not in trackers:
                    trackers[asset] = PositionTracker(asset)
                trackers[asset].sell(FIFTY_CENTS, amount)

        elif etype == "SPLIT":
            cond = raw["condition"]
            amount = int(raw["amount"])
            assets = cond_to_assets.get(cond, [])
            for asset in assets:
                if asset not in trackers:
                    trackers[asset] = PositionTracker(asset)
                trackers[asset].buy(FIFTY_CENTS, amount)

        elif etype == "REDEEM":
            cond = raw["condition"]
            assets = cond_to_assets.get(cond, [])
            for asset in assets:
                if asset not in trackers:
                    continue
                tracker = trackers[asset]
                pm = pm_by_asset.get(asset, {})
                # Resolution price from PM's curPrice
                cur_price = pm.get("curPrice", 0)
                res_price = int(cur_price * COLLATERAL_SCALE)
                tracker.sell(res_price, tracker.amount)

    # ── 5. Compare to PM ──
    print()
    print("=" * 100)
    print("PHASE 2: PER-POSITION COMPARISON")
    print("=" * 100)
    print(f"  {'Title':<45} {'Out':>5} {'Field':<12} {'Calc':>14} {'PM':>14} {'Delta':>10} {'Match':>5}")
    print("  " + "-" * 98)

    matches = 0
    total = 0
    total_calc_pnl = 0.0
    total_pm_pnl = 0.0

    for p in sorted(all_pos, key=lambda x: abs(x.get("realizedPnl", 0))):
        asset = p["asset"]
        tracker = trackers.get(asset)
        if not tracker:
            print(f"  {p.get('title','')[:45]:<45} {p.get('outcome',''):>5} -- NO TRACKER --")
            continue

        pm_tb = p.get("totalBought", 0)
        pm_avg = p.get("avgPrice", 0)
        pm_pnl = p.get("realizedPnl", 0)
        title = p.get("title", "")[:45]
        outcome = p.get("outcome", "")[:5]

        tb_ok = abs(tracker.total_bought_f - pm_tb) < max(0.01, pm_tb * 0.0001)
        avg_ok = abs(tracker.avg_price_f - pm_avg) < 0.001
        pnl_ok = abs(tracker.realized_pnl_f - pm_pnl) < max(0.01, abs(pm_pnl) * 0.0001)

        all_ok = tb_ok and avg_ok and pnl_ok
        if all_ok:
            matches += 1
        total += 1
        total_calc_pnl += tracker.realized_pnl_f
        total_pm_pnl += pm_pnl

        status = "OK" if all_ok else "XX"

        # Print totalBought
        print(f"  {title:<45} {outcome:>5} {'totalBought':<12} {tracker.total_bought_f:>14,.6f} {pm_tb:>14,.6f} "
              f"{tracker.total_bought_f - pm_tb:>10,.6f} {'OK' if tb_ok else 'XX'}")
        # Print avgPrice
        print(f"  {'':<45} {'':<5} {'avgPrice':<12} {tracker.avg_price_f:>14,.6f} {pm_avg:>14,.6f} "
              f"{tracker.avg_price_f - pm_avg:>10,.6f} {'OK' if avg_ok else 'XX'}")
        # Print realizedPnl
        print(f"  {'':<45} {'':<5} {'realizedPnl':<12} {tracker.realized_pnl_f:>14,.6f} {pm_pnl:>14,.6f} "
              f"{tracker.realized_pnl_f - pm_pnl:>10,.6f} {'OK' if pnl_ok else 'XX'}")
        # Print remaining amount
        print(f"  {'':<45} {'':<5} {'amount':<12} {tracker.amount_f:>14,.6f}")
        print()

    # ── Summary ──
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"  Positions matched: {matches}/{total}")
    print(f"  Calc total PnL:    ${total_calc_pnl:>14,.2f}")
    print(f"  PM total PnL:      ${total_pm_pnl:>14,.2f}")
    print(f"  Delta:             ${total_calc_pnl - total_pm_pnl:>14,.2f}")
    print(f"  Leaderboard PnL:   ${lb_pnl:>14,.2f}")
    print(f"  LB - Calc delta:   ${lb_pnl - total_calc_pnl:>14,.2f}")

if __name__ == "__main__":
    asyncio.run(main())
