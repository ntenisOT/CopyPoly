"""Quick smoke test — verify all APIs return real data."""
import asyncio
import json

from copypoly.api.data import DataAPIClient
from copypoly.api.gamma import GammaAPIClient
from copypoly.api.clob import ClobAPIClient


async def test_data_api():
    print("\n=== DATA API (Leaderboard) ===")
    client = DataAPIClient()
    try:
        lb = await client.get_leaderboard(period="ALL", category="OVERALL", limit=5)
        print(f"Entries returned: {len(lb)}")

        if isinstance(lb, dict):
            print(f"Response is dict with keys: {list(lb.keys())}")
            # Try to find the actual list
            for key in ["data", "results", "leaderboard"]:
                if key in lb:
                    lb = lb[key]
                    print(f"Found list under key '{key}', count: {len(lb)}")
                    break

        if isinstance(lb, list) and lb:
            for entry in lb[:3]:
                rank = entry.get("rank", "?")
                name = entry.get("userName", "anon")
                pnl = entry.get("pnl", 0)
                vol = entry.get("vol", 0)
                wallet = entry.get("proxyWallet", "?")[:10]
                print(f"  Rank {rank}: {name} (wallet: {wallet}...) PnL=${pnl:,.2f} Vol=${vol:,.2f}")
        elif isinstance(lb, list):
            print("  WARNING: Empty list returned!")
        else:
            print(f"  Unexpected response type: {type(lb)}")
            print(f"  First 500 chars: {str(lb)[:500]}")
    finally:
        await client.close()


async def test_gamma_api():
    print("\n=== GAMMA API (Markets) ===")
    client = GammaAPIClient()
    try:
        markets = await client.get_markets(limit=5)
        print(f"Markets returned: {len(markets)}")

        if isinstance(markets, list) and markets:
            for m in markets[:3]:
                q = m.get("question", "?")[:60]
                liq = float(m.get("liquidity", 0) or 0)
                vol = float(m.get("volume", 0) or 0)
                cid = m.get("conditionId", "?")[:16]
                print(f"  {q}...")
                print(f"    Liquidity=${liq:,.0f} Volume=${vol:,.0f} CondID={cid}...")
        elif isinstance(markets, dict):
            print(f"  Response is dict with keys: {list(markets.keys())}")
            print(f"  First 500 chars: {str(markets)[:500]}")
        else:
            print(f"  Unexpected: {type(markets)}")
    finally:
        await client.close()


async def test_clob_api():
    print("\n=== CLOB API (Order Book) ===")
    # First get a token_id from gamma
    gamma = GammaAPIClient()
    try:
        markets = await gamma.get_markets(limit=1)
        if not markets:
            print("  No markets to test with!")
            return

        market = markets[0] if isinstance(markets, list) else {}
        tokens = market.get("tokens", [])
        if not tokens:
            print(f"  Market has no tokens: {json.dumps(market, indent=2)[:300]}")
            return

        token_id = tokens[0].get("token_id", "")
        print(f"  Testing with token: {token_id[:20]}...")
    finally:
        await gamma.close()

    clob = ClobAPIClient()
    try:
        spread = await clob.get_spread(token_id)
        print(f"  Best Bid: {spread['best_bid']:.4f}")
        print(f"  Best Ask: {spread['best_ask']:.4f}")
        print(f"  Spread:   {spread['spread']:.4f}")
        print(f"  Midpoint: {spread['midpoint']:.4f}")
    finally:
        await clob.close()


async def main():
    print("CopyPoly API Smoke Test")
    print("=" * 50)

    await test_data_api()
    await test_gamma_api()
    await test_clob_api()

    print("\n" + "=" * 50)
    print("SMOKE TEST COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
