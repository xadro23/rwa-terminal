#!/usr/bin/env python3
"""
build_dashboard.py — fetches live CoinMarketCap RWA data and renders a static,
self-contained dashboard (index.html) that can be deployed to GitHub Pages.

Endpoints used:
  /v5/real-world-assets/assets/list     (top 250 assets with tokenized aggregate quotes)
  /v5/real-world-assets/quotes/latest   (per-token + per-issuer breakdown for top assets)
  /v5/real-world-assets/issuers/list    (issuer registry with token counts)
  /v1/key/info                          (plan + credit telemetry shown in the footer)

Usage: python3 build_dashboard.py
"""
import os, json, urllib.request, urllib.parse, datetime, html

API = "https://pro-api.coinmarketcap.com"
KEY = None
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")) as f:
    for line in f:
        if line.startswith("CMC_API_KEY="):
            KEY = line.strip().split("=", 1)[1]
if not KEY:
    raise SystemExit("CMC_API_KEY missing in .env")

def get(path, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-CMC_PRO_API_KEY": KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())

def main():
    print("fetching /v5/real-world-assets/assets/list ...")
    lst = get("/v5/real-world-assets/assets/list", {"limit": 250})["data"]
    assets = lst["rwa_assets"]
    total = lst["total_size"]

    print("fetching /v5/real-world-assets/issuers/list ...")
    issuers = get("/v5/real-world-assets/issuers/list", {"limit": 250})["data"]

    top = [a for a in assets if a.get("has_tokens")][:40]
    syms = ",".join(a["symbol"] for a in top)
    print(f"fetching /v5/real-world-assets/quotes/latest for {len(top)} assets ...")
    q = get("/v5/real-world-assets/quotes/latest", {"symbol": syms, "skip_invalid": "true"})["data"]
    quotes = {a["symbol"]: a for a in q["rwa_assets"]}

    print("fetching /v1/key/info ...")
    keyinfo = get("/v1/key/info")["data"]

    # ---- aggregate by asset type ----
    by_type = {}
    for a in assets:
        t = a.get("asset_type") or "other"
        d = by_type.setdefault(t, {"mcap": 0.0, "vol": 0.0, "n": 0})
        d["mcap"] += a.get("tokenized_market_cap") or 0
        d["vol"] += a.get("tokenized_volume_24h") or 0
        d["n"] += 1

    # ---- issuer dominance from per-token data ----
    iss_map = {}
    for sym, a in quotes.items():
        for t in a.get("tokens") or []:
            k = t.get("issuer_name") or "Unknown"
            e = iss_map.setdefault(k, {"mcap": 0.0, "n_tokens": 0, "assets": set()})
            e["mcap"] += t.get("market_cap") or 0
            e["n_tokens"] += 1
            e["assets"].add(sym)
    issuer_rows = sorted(
        [{"name": k, "mcap": v["mcap"], "n_tokens": v["n_tokens"], "n_assets": len(v["assets"])} for k, v in iss_map.items()],
        key=lambda x: -x["mcap"])[:15]

    # ---- spread table (largest premium/discount among top assets' tokens) ----
    spreads = []
    for sym, a in quotes.items():
        avg = a.get("average_tokenized_price") or 0
        if not avg:
            continue
        for t in a.get("tokens") or []:
            if not t.get("market_cap") or not t.get("price"):
                continue
            dev = (t["price"] / avg - 1) * 100
            spreads.append({"asset": sym, "asset_name": a["name"], "token": t["symbol"],
                            "issuer": t.get("issuer_name"), "price": t["price"], "dev": dev,
                            "mcap": t["market_cap"]})
    spreads.sort(key=lambda x: -abs(x["dev"]))
    # keep meaningful deviations (>0.2%) so denomination quirks don't dominate
    spreads = [s for s in spreads if abs(s["dev"]) > 0.2][:15]

    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    payload = {
        "generated": now,
        "total_assets": total,
        "assets": [{k: a.get(k) for k in ("rwa_rank","symbol","name","asset_type","rwa_id","tokenized_market_cap","tokenized_volume_24h","average_tokenized_price")} for a in assets[:60]],
        "types": by_type,
        "issuers": issuer_rows,
        "issuer_registry": [{"name": i["name"], "tokens": i.get("num_tokens"), "website": i.get("website")} for i in issuers["issuers"][:20]],
        "spreads": spreads,
        "key": {"plan_monthly": keyinfo["plan"]["credit_limit_monthly"],
                "used": keyinfo["usage"]["current_month"]["credits_used"],
                "left": keyinfo["usage"]["current_month"]["credits_left"]},
    }

    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
    with open(tpl_path) as f:
        tpl = f.read()
    out = tpl.replace("__DATA__", json.dumps(payload))
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(out_path, "w") as f:
        f.write(out)
    print(f"wrote {out_path} ({len(out)/1024:.1f} KB) — {total} assets tracked, {len(assets)} sampled")

if __name__ == "__main__":
    main()
