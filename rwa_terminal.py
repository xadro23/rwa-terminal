#!/usr/bin/env python3
"""
RWA Terminal — CoinMarketCap Real World Assets explorer (CLI + agent tool)
Endpoints used (all on Startup tier and above):
  - /v5/real-world-assets/assets/list    — paginated tracked RWA assets w/ tokenized quotes
  - /v5/real-world-assets/quotes/latest  — per-asset token breakdown + issuer attribution
  - /v5/real-world-assets/issuers/list   — token issuers with linked-token counts
  - /v1/key/info                         — plan/credit status
Commands:
  python rwa_terminal.py top [--type stock|commodity|currency|government_security|etf|real_estate] [--limit N]
  python rwa_terminal.py spread <SYMBOL>            # per-issuer premium/discount vs aggregate
  python rwa_terminal.py issuers [--limit N]
  python rwa_terminal.py status                     # credit usage
Requires: CMC_API_KEY in .env
"""
import os, sys, json, argparse, urllib.request, urllib.parse

def load_key():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    with open(p) as f:
        for line in f:
            if line.startswith("CMC_API_KEY="):
                return line.strip().split("=", 1)[1]
    raise SystemExit("CMC_API_KEY missing in .env")

API = "https://pro-api.coinmarketcap.com"
KEY = load_key()

def get(path, params=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"X-CMC_PRO_API_KEY": KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def fmt_usd(x):
    if x >= 1e9: return f"${x/1e9:,.2f}B"
    if x >= 1e6: return f"${x/1e6:,.2f}M"
    if x >= 1e3: return f"${x/1e3:,.1f}K"
    return f"${x:,.2f}"

def cmd_top(args):
    params = {"limit": args.limit}
    if args.type: params["asset_type"] = args.type
    d = get("/v5/real-world-assets/assets/list", params)["data"]
    rows = d["rwa_assets"]
    print(f"\nRWA Top {len(rows)} (of {d['total_size']} tracked)\n")
    print(f"{'#':>4} {'SYMBOL':<10} {'NAME':<28} {'TYPE':<12} {'MCAP':>12} {'VOL 24H':>12} {'PRICE':>12}")
    for a in rows:
        print(f"{a.get('rwa_rank') or '-':>4} {a['symbol']:<10} {a['name'][:27]:<28} {a['asset_type']:<12} "
              f"{fmt_usd(a['tokenized_market_cap']):>12} {fmt_usd(a['tokenized_volume_24h']):>12} {a['average_tokenized_price']:>12,.2f}")

def cmd_spread(args):
    d = get("/v5/real-world-assets/quotes/latest", {"symbol": args.symbol.upper()})["data"]
    for a in d["rwa_assets"]:
        avg = a["average_tokenized_price"]
        print(f"\n{a['name']} ({a['symbol']}) — aggregate tokenized price: {avg:,.2f} USD")
        print(f"{'TOKEN':<12} {'ISSUER':<26} {'PRICE':>12} {'PREMIUM':>9} {'MCAP':>12}")
        toks = sorted(a.get("tokens", []), key=lambda t: -(t.get("market_cap") or 0))
        for t in toks:
            dev = (t["price"] / avg - 1) * 100
            print(f"{t['symbol']:<12} {t['issuer_name'][:25]:<26} {t['price']:>12,.2f} {dev:>+8.2f}% {fmt_usd(t.get('market_cap') or 0):>12}")

def cmd_issuers(args):
    d = get("/v5/real-world-assets/issuers/list", {"limit": args.limit})["data"]
    rows = d["issuers"]
    print(f"\nRWA Issuers ({len(rows)} shown of {d['total_size']})\n")
    for i in rows:
        print(f"{i.get('issuer_id','')[:10]:<12} {i['name'][:40]:<42} tokens: {i.get('num_tokens','?')}")

def cmd_status(_):
    d = get("/v1/key/info")["data"]
    pl, us = d["plan"], d["usage"]
    print(f"\nPlan: {pl['credit_limit_monthly']} credits/mo | rate {pl['rate_limit_minute']}/min")
    print(f"Used this month: {us['current_month']['credits_used']} | left: {us['current_month']['credits_left']}")

def main():
    ap = argparse.ArgumentParser(prog="rwa_terminal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("top"); t.add_argument("--type"); t.add_argument("--limit", type=int, default=25)
    s = sub.add_parser("spread"); s.add_argument("symbol")
    i = sub.add_parser("issuers"); i.add_argument("--limit", type=int, default=50)
    sub.add_parser("status")
    args = ap.parse_args()
    {"top": cmd_top, "spread": cmd_spread, "issuers": cmd_issuers, "status": cmd_status}[args.cmd](args)

if __name__ == "__main__":
    main()
