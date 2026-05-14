#!/usr/bin/env python3
"""
PumpScan Bot v25 — 24/7 Solana token detector with SPIKE detection.

Notifications via ntfy.sh (free, push to Android/iOS).

5 patterns:
  1. SPIKE 1H              — sudden +50% in 1h with strong volume (NEW!)
  2. EARLY ACCUMULATION    — micro MC ($5K-$50K) with rising volume + steady price
  3. EARLY BREAKOUT        — micro MC with first +25% on rising volume
  4. GRADUAL TREND LOW     — MC $5K-$200K, +100%/24h sane
  5. GRADUAL TREND HIGH    — MC $200K-$5M, +100%/24h sane

Sticky logic: once a token is classified as gradual trend it stays "stuck"
(pin icon) until it really dies, so you can keep watching it.

Token discovery: 3 sources combined to never miss anything:
  - DexScreener trending pairs (latest + top boosts + profiles)
  - DexScreener token search with rotating keywords + alphabet
  - Sticky tokens re-fetched every scan via tokens endpoint

Env vars:
  NTFY_TOPIC   — your private topic name      (REQUIRED)
  NTFY_SERVER  — default https://ntfy.sh
  POLL_SEC     — default 30
  MIN_LIQ      — default 1500
  DEBUG        — "1" for verbose
"""

import os
import time
import logging
import asyncio
import aiohttp

# Config
NTFY_TOPIC  = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
POLL_SEC    = int(os.environ.get("POLL_SEC", "30"))
MIN_LIQ     = float(os.environ.get("MIN_LIQ", "1500"))
DEBUG       = os.environ.get("DEBUG", "0") == "1"

DEX_BASE = "https://api.dexscreener.com"
ALLOWED_DEX = {"raydium", "pump-fun", "pumpswap", "meteora", "orca", "fluxbeam"}

# Pattern thresholds
MIN_VOL24H = 1000

# 1) SPIKE 1H (sudden hyperbolic move - the one we were missing!)
SPIKE_MIN_MC       = 5_000
SPIKE_MAX_MC       = 5_000_000
SPIKE_MIN_CHG1H    = 50
SPIKE_MAX_CHG1H    = 5000
SPIKE_MIN_VOL1H    = 3000
SPIKE_MIN_BUY_RATIO_1H = 0.50

# 2) EARLY ACCUMULATION
EARLY_ACC_MIN_MC        = 5_000
EARLY_ACC_MAX_MC        = 50_000
EARLY_ACC_MIN_VOL5M     = 800
EARLY_ACC_MIN_CHG5M     = 5
EARLY_ACC_MAX_CHG5M     = 40
EARLY_ACC_MIN_BUYRATIO  = 0.55

# 3) EARLY BREAKOUT
EARLY_BR_MIN_MC    = 5_000
EARLY_BR_MAX_MC    = 80_000
EARLY_BR_MIN_CHG5M = 25
EARLY_BR_MAX_CHG5M = 150
EARLY_BR_MIN_VOL5M = 1500

# 4+5) GRADUAL TRENDS
TREND_24H_PCT    = 100
TREND_KEEP_24H   = 40
LOW_TREND_MIN_MC  = 5_000
LOW_TREND_MAX_MC  = 200_000
HIGH_TREND_MIN_MC = 200_000
HIGH_TREND_MAX_MC = 5_000_000

D30_MS = 30 * 24 * 3600 * 1000

NOTIF_CD = {
    "SPIKE":       180,
    "EARLY_ACC":   600,
    "EARLY_BR":    300,
    "TREND_LOW":   600,
    "TREND_HIGH":  900,
}

STICKY_TTL = 4 * 3600

# Discovery
SEARCH_ALPHABET = [
    'aa','ab','ac','ad','ae','af','ag','ah','ai','aj','ak','al','am','an','ao','ap','ar','as','at','au','av','aw','ax','ay','az',
    'ba','be','bi','bl','bo','br','bu','by',
    'ca','ce','ch','ci','cl','co','cr','cu','cy',
    'da','de','di','do','dr','du',
    'ea','el','em','en','er','es','et','eu','ev','ex',
    'fa','fe','fi','fl','fo','fr','fu',
    'ga','ge','gi','gl','go','gr','gu',
    'ha','he','hi','ho','hu',
    'ic','id','if','il','im','in','ir','is','it',
    'ja','je','jo','ju',
    'ka','ke','ki','ko','ku',
    'la','le','li','lo','lu',
    'ma','me','mi','mo','mu','my',
    'na','ne','ni','no','nu',
    'ob','oc','od','of','oh','ok','ol','om','on','op','or','os','ot','ou','ov','ow','ox',
    'pa','pe','ph','pi','pl','po','pr','pu',
    'ra','re','ri','ro','ru',
    'sa','sc','se','sh','si','sk','sl','sn','so','sp','st','su','sw','sy',
    'ta','te','th','ti','to','tr','tu','tw','ty',
    'ub','un','up','us','ut',
    'va','ve','vi','vo',
    'wa','we','wh','wi','wo','wr',
    'ya','ye','yo','yu',
    'za','ze','zi','zo'
]
SEARCH_PER_CYCLE = 22
WATCHLIST = [
    'sol','pump','meme','dog','cat','ai','inu','baby','elon','trump','wif','bonk',
    'goblin','bull','troll','apple','frog','pepe','shiba','floki','moon','retardio',
    'fartcoin','jeo','pnut','peanut','mew','popcat','hanta','virus','spencer','pratt',
    'animal','twt','vote','crisis','crypto','niche','xanim'
]

# Logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pumpscan")

# State
notif_cd: dict = {}
search_offset = 0
trend_sticky: dict = {}
ntfy_queue: asyncio.Queue = asyncio.Queue(maxsize=300)


# Utils
def fmt(v) -> str:
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        return "—"
    if n == 0: return "—"
    if n >= 1e9: return f"${n/1e9:.2f}B"
    if n >= 1e6: return f"${n/1e6:.2f}M"
    if n >= 1e3: return f"${n/1e3:.1f}K"
    return f"${n:.0f}"


def fmt_age(ms: int) -> str:
    if ms < 0: return "?"
    m = ms // 60_000
    if m < 60: return f"{m}min"
    h = ms // 3_600_000
    if h < 24: return f"{h}h"
    d = ms // 86_400_000
    if d < 30: return f"{d}g"
    return f"{d // 30}m"


def normalize_ts(ts):
    try:
        n = float(ts)
    except (TypeError, ValueError):
        return None
    if n <= 0: return None
    return int(n) if n > 1e12 else int(n * 1000)


def parse_pair(p: dict):
    if not p or p.get("chainId") != "solana":
        return None
    if p.get("dexId") not in ALLOWED_DEX:
        return None
    ca = normalize_ts(p.get("pairCreatedAt"))
    if ca is None: return None
    age_ms = int(time.time() * 1000) - ca
    if age_ms <= 0: return None
    liq = (p.get("liquidity") or {}).get("usd") or 0
    if liq < MIN_LIQ: return None
    vol = p.get("volume") or {}
    if (vol.get("h24") or 0) < MIN_VOL24H:
        return None
    chg = p.get("priceChange") or {}
    base = p.get("baseToken") or {}
    txns24 = (p.get("txns") or {}).get("h24") or {}
    txns1h = (p.get("txns") or {}).get("h1")  or {}
    txns5m = (p.get("txns") or {}).get("m5")  or {}
    info = p.get("info") or {}
    img = info.get("imageUrl") or ""
    return {
        "key":   p.get("pairAddress") or "",
        "sym":   (base.get("symbol") or "?").upper(),
        "name":  base.get("name") or "",
        "addr":  base.get("address") or "",
        "ageMs": age_ms,
        "vol5m":  vol.get("m5")  or 0,
        "vol1h":  vol.get("h1")  or 0,
        "vol6h":  vol.get("h6")  or 0,
        "vol24h": vol.get("h24") or 0,
        "chg5m":  chg.get("m5")  or 0,
        "chg1h":  chg.get("h1")  or 0,
        "chg6h":  chg.get("h6")  or 0,
        "chg24h": chg.get("h24") or 0,
        "liq":   liq,
        "mcap":  p.get("marketCap") or p.get("fdv") or 0,
        "buys24":  txns24.get("buys")  or 0,
        "sells24": txns24.get("sells") or 0,
        "buys1h":  txns1h.get("buys")  or 0,
        "sells1h": txns1h.get("sells") or 0,
        "buys5m":  txns5m.get("buys")  or 0,
        "sells5m": txns5m.get("sells") or 0,
        "url": p.get("url") or f"https://dexscreener.com/solana/{p.get('pairAddress','')}",
        "img": img,
    }


def dedupe(rows):
    by_addr = {}
    for r in rows:
        if r["addr"]:
            by_addr.setdefault(r["addr"], []).append(r)
    seen, out = set(), []
    for group in by_addr.values():
        best = max(group, key=lambda x: x.get("liq") or 0)
        if best["key"] not in seen:
            seen.add(best["key"])
            out.append(best)
    for r in rows:
        if not r["addr"] and r["key"] not in seen:
            seen.add(r["key"])
            out.append(r)
    return out


# Detectors
def _ratio_5m(r):
    t = (r["buys5m"] or 0) + (r["sells5m"] or 0)
    return (r["buys5m"] / t) if t else 0.5

def _ratio_1h(r):
    t = (r["buys1h"] or 0) + (r["sells1h"] or 0)
    return (r["buys1h"] / t) if t else 0.5


def detect_spike_1h(r):
    """NEW: sudden hyperbolic move in last hour."""
    if r["ageMs"] > D30_MS: return False
    mc = r["mcap"] or 0
    if not (SPIKE_MIN_MC <= mc <= SPIKE_MAX_MC): return False
    if r["chg1h"] < SPIKE_MIN_CHG1H or r["chg1h"] > SPIKE_MAX_CHG1H: return False
    if r["vol1h"] < SPIKE_MIN_VOL1H: return False
    if _ratio_1h(r) < SPIKE_MIN_BUY_RATIO_1H: return False
    if r["chg5m"] < -20: return False
    return True


def detect_early_accumulation(r):
    if r["ageMs"] > D30_MS: return False
    mc = r["mcap"] or 0
    if not (EARLY_ACC_MIN_MC <= mc <= EARLY_ACC_MAX_MC): return False
    if r["vol5m"] < EARLY_ACC_MIN_VOL5M: return False
    if r["chg5m"] < EARLY_ACC_MIN_CHG5M or r["chg5m"] > EARLY_ACC_MAX_CHG5M: return False
    if _ratio_5m(r) < EARLY_ACC_MIN_BUYRATIO: return False
    if r["chg24h"] < -20: return False
    return True


def detect_early_breakout(r):
    if r["ageMs"] > D30_MS: return False
    mc = r["mcap"] or 0
    if not (EARLY_BR_MIN_MC <= mc <= EARLY_BR_MAX_MC): return False
    if r["chg5m"] < EARLY_BR_MIN_CHG5M or r["chg5m"] > EARLY_BR_MAX_CHG5M: return False
    if r["vol5m"] < EARLY_BR_MIN_VOL5M: return False
    if _ratio_5m(r) < 0.55: return False
    return True


def is_trending_strict(r):
    if r["ageMs"] > D30_MS: return False
    if r["chg24h"] < TREND_24H_PCT: return False
    if r["vol24h"] < 5000: return False
    if r["liq"] < 2000: return False
    if r["chg1h"] < -30: return False
    if r["chg6h"] < -50: return False
    if r["chg24h"] > 0 and r["chg1h"] / r["chg24h"] > 0.85:
        return False
    # Anti-honeypot: troppi sell rispetto ai buy in 24h
    t24 = (r["buys24"] or 0) + (r["sells24"] or 0)
    if t24 >= 20 and (r["buys24"] / t24) < 0.35:
        return False
    return True


def is_trending_healthy(r):
    if r["ageMs"] > D30_MS: return False
    if r["chg24h"] < TREND_KEEP_24H: return False
    if r["chg1h"] < -40: return False
    if r["vol24h"] < 3000: return False
    if r["liq"] < 1500: return False
    return True


def detect_trend_low(r):
    mc = r["mcap"] or 0
    if not (LOW_TREND_MIN_MC <= mc <= LOW_TREND_MAX_MC): return False
    return is_trending_strict(r)


def detect_trend_high(r):
    mc = r["mcap"] or 0
    if not (HIGH_TREND_MIN_MC <= mc <= HIGH_TREND_MAX_MC): return False
    return is_trending_strict(r)


def trend_quality(r):
    if r["chg24h"] <= 0: return 0
    burst = max(0.0, 1 - max(0, r["chg1h"]) / r["chg24h"])
    six   = min(1.0, max(0, r["chg6h"]) / r["chg24h"])
    return int(round(burst * 70 + six * 30))


# HTTP / DexScreener
async def fetch_json(session, path):
    url = DEX_BASE + path
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


def next_search_batch():
    global search_offset
    out = list(WATCHLIST)
    for i in range(SEARCH_PER_CYCLE):
        out.append(SEARCH_ALPHABET[(search_offset + i) % len(SEARCH_ALPHABET)])
    search_offset = (search_offset + SEARCH_PER_CYCLE) % len(SEARCH_ALPHABET)
    return out


async def fetch_all(session):
    tasks = [
        fetch_json(session, "/latest/dex/pairs/solana"),
        fetch_json(session, "/token-boosts/latest/v1"),
        fetch_json(session, "/token-boosts/top/v1"),
        fetch_json(session, "/token-profiles/latest/v1"),
    ]
    for s in next_search_batch():
        tasks.append(fetch_json(session, f"/latest/dex/search?q={s}"))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    main, boosts_l, boosts_t, profiles, *searches = results

    raw = []
    if isinstance(main, dict) and "pairs" in main:
        raw.extend(main["pairs"])
    for s in searches:
        if isinstance(s, dict) and "pairs" in s:
            raw.extend(s["pairs"])

    addrs = []
    for src in (boosts_l, boosts_t, profiles):
        if isinstance(src, list):
            for it in src:
                if isinstance(it, dict) and it.get("chainId") == "solana" and it.get("tokenAddress"):
                    addrs.append(it["tokenAddress"])

    for k, st in list(trend_sticky.items()):
        if st.get("addr"):
            addrs.append(st["addr"])

    if addrs:
        unique = list(dict.fromkeys(addrs))[:180]
        sub_tasks = []
        for i in range(0, len(unique), 30):
            chunk = unique[i:i+30]
            sub_tasks.append(fetch_json(session, "/latest/dex/tokens/" + ",".join(chunk)))
        for sr in await asyncio.gather(*sub_tasks, return_exceptions=True):
            if isinstance(sr, dict) and "pairs" in sr:
                raw.extend(sr["pairs"])

    parsed = [r for r in (parse_pair(p) for p in raw) if r]
    return dedupe(parsed)


# ntfy.sh push
async def ntfy_send(session, title, body, priority="default", tags=None, click_url=None, icon=None):
    if not NTFY_TOPIC:
        return False
    headers = {
        "Title": title.encode("utf-8"),
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = ",".join(tags)
    if click_url:
        headers["Click"] = click_url
    if icon:
        headers["Icon"] = icon
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    try:
        async with session.post(url, data=body.encode("utf-8"), headers=headers,
                                timeout=aiohttp.ClientTimeout(total=15)) as r:
            return r.status == 200
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("ntfy send failed: %s", e)
        return False


async def ntfy_worker(session):
    while True:
        item = await ntfy_queue.get()
        try:
            await ntfy_send(session, item["title"], item["body"],
                            priority=item.get("priority", "default"),
                            tags=item.get("tags"), click_url=item.get("click"),
                            icon=item.get("icon"))
        except Exception as e:
            log.warning("ntfy worker error: %s", e)
        finally:
            ntfy_queue.task_done()
        await asyncio.sleep(0.7)


def enqueue_notif(title, body, priority="default", tags=None, click=None, icon=None):
    try:
        ntfy_queue.put_nowait({
            "title": title, "body": body, "priority": priority,
            "tags": tags or [], "click": click, "icon": icon,
        })
    except asyncio.QueueFull:
        log.warning("ntfy queue full, dropping notification")


# Notification builders
def _safe_icon(r):
    img = r.get("img") or ""
    if img.startswith("http"):
        return img
    return None


def notif_spike(r):
    return {
        "title": f"⚡ {r['sym']} SPIKE 1H +{r['chg1h']:.0f}%",
        "body":  (f"1H +{r['chg1h']:.0f}% · 5M {r['chg5m']:+.1f}% · 24H {r['chg24h']:+.0f}%\n"
                  f"MC {fmt(r['mcap'])} · Vol1h {fmt(r['vol1h'])} · Liq {fmt(r['liq'])}\n"
                  f"Età {fmt_age(r['ageMs'])} · Buy1h {_ratio_1h(r)*100:.0f}%\n"
                  f"CA: {r['addr']}"),
        "priority": "urgent",
        "tags": ["zap"],
        "click": r["url"],
        "icon":  _safe_icon(r),
    }


def notif_early_acc(r):
    return {
        "title": f"🌱 {r['sym']} ACCUMULAZIONE precoce",
        "body":  (f"MC {fmt(r['mcap'])} · 5M +{r['chg5m']:.1f}% · Vol5m {fmt(r['vol5m'])}\n"
                  f"24H {r['chg24h']:+.0f}% · Buy5m {_ratio_5m(r)*100:.0f}%\n"
                  f"Età {fmt_age(r['ageMs'])} · Liq {fmt(r['liq'])}\n"
                  f"CA: {r['addr']}"),
        "priority": "high",
        "tags": ["seedling"],
        "click": r["url"],
        "icon":  _safe_icon(r),
    }


def notif_early_br(r):
    return {
        "title": f"🚀 {r['sym']} BREAKOUT precoce +{r['chg5m']:.0f}%",
        "body":  (f"MC {fmt(r['mcap'])} · 5M +{r['chg5m']:.1f}%\n"
                  f"Vol5m {fmt(r['vol5m'])} · Buy {_ratio_5m(r)*100:.0f}%\n"
                  f"Età {fmt_age(r['ageMs'])} · Liq {fmt(r['liq'])}\n"
                  f"CA: {r['addr']}"),
        "priority": "urgent",
        "tags": ["rocket"],
        "click": r["url"],
        "icon":  _safe_icon(r),
    }


def notif_trend(r, low_or_high, sticky=False):
    label = "TREND BASSO MC" if low_or_high == "low" else "TREND ALTO MC"
    icon  = "🟢" if low_or_high == "low" else "📈"
    if sticky:
        label = "📌 " + label
    return {
        "title": f"{icon} {r['sym']} {label} +{r['chg24h']:.0f}%/24h",
        "body":  (f"24H +{r['chg24h']:.0f}% · 6H {r['chg6h']:+.1f}% · 1H {r['chg1h']:+.1f}%\n"
                  f"MC {fmt(r['mcap'])} · Vol {fmt(r['vol24h'])} · Liq {fmt(r['liq'])}\n"
                  f"Età {fmt_age(r['ageMs'])} · Qualità {trend_quality(r)}/100\n"
                  f"CA: {r['addr']}"),
        "priority": "high" if not sticky else "default",
        "tags": ["chart_with_upwards_trend"] if not sticky else ["pushpin"],
        "click": r["url"],
        "icon":  _safe_icon(r),
    }


# Main scan loop
def can_notify(key, pattern):
    cd = notif_cd.setdefault(key, {})
    last = cd.get(pattern, 0)
    if time.time() - last >= NOTIF_CD[pattern]:
        cd[pattern] = time.time()
        return True
    return False


async def scan_once(session, first):
    rows = await fetch_all(session)
    if not rows:
        log.warning("no rows fetched")
        return 0

    sent = 0
    counts = {"SPIKE": 0, "EARLY_ACC": 0, "EARLY_BR": 0, "TREND_LOW": 0, "TREND_HIGH": 0}

    now = time.time()
    for k, st in list(trend_sticky.items()):
        if now - st["ts"] > STICKY_TTL:
            trend_sticky.pop(k, None)

    for r in rows:
        k = r["key"]

        if not first and detect_spike_1h(r) and can_notify(k, "SPIKE"):
            enqueue_notif(**notif_spike(r))
            counts["SPIKE"] += 1
            sent += 1

        if not first:
            if detect_early_breakout(r) and can_notify(k, "EARLY_BR"):
                enqueue_notif(**notif_early_br(r))
                counts["EARLY_BR"] += 1
                sent += 1
            elif detect_early_accumulation(r) and can_notify(k, "EARLY_ACC"):
                enqueue_notif(**notif_early_acc(r))
                counts["EARLY_ACC"] += 1
                sent += 1

        if detect_trend_low(r):
            trend_sticky[k] = {"ts": now, "bucket": "low", "sym": r["sym"], "addr": r["addr"]}
            if not first and can_notify(k, "TREND_LOW"):
                enqueue_notif(**notif_trend(r, "low"))
                counts["TREND_LOW"] += 1
                sent += 1
        elif k in trend_sticky and trend_sticky[k]["bucket"] == "low":
            if is_trending_healthy(r):
                trend_sticky[k]["ts"] = now
            else:
                trend_sticky.pop(k, None)

        if detect_trend_high(r):
            trend_sticky[k] = {"ts": now, "bucket": "high", "sym": r["sym"], "addr": r["addr"]}
            if not first and can_notify(k, "TREND_HIGH"):
                enqueue_notif(**notif_trend(r, "high"))
                counts["TREND_HIGH"] += 1
                sent += 1
        elif k in trend_sticky and trend_sticky[k]["bucket"] == "high":
            if is_trending_healthy(r):
                trend_sticky[k]["ts"] = now
            else:
                trend_sticky.pop(k, None)

    log.info("scan: rows=%d sent=%d spike=%d acc=%d br=%d trL=%d trH=%d sticky=%d",
             len(rows), sent, counts["SPIKE"], counts["EARLY_ACC"], counts["EARLY_BR"],
             counts["TREND_LOW"], counts["TREND_HIGH"], len(trend_sticky))
    return sent


async def main():
    if not NTFY_TOPIC:
        log.error("NTFY_TOPIC missing! Set it as environment variable.")
        return
    if "/" in NTFY_TOPIC or " " in NTFY_TOPIC:
        log.error("NTFY_TOPIC must contain only letters/numbers/dashes (no slash, no spaces).")
        return

    log.info("PumpScan v25 starting")
    log.info("ntfy: %s/%s — install ntfy app & subscribe to that topic", NTFY_SERVER, NTFY_TOPIC)
    log.info("polling every %ss", POLL_SEC)

    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=30)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        worker_task = asyncio.create_task(ntfy_worker(session))

        await ntfy_send(session, "🟢 PumpScan v25 attivo",
                        f"Scansione DexScreener Solana ogni {POLL_SEC}s.\n"
                        f"⚡ spike 1h\n🚀 breakout precoce\n🌱 accumulazione\n"
                        f"🟢 trend basso MC\n📈 trend alto MC\n📌 trend ancora attivi",
                        priority="low", tags=["green_circle"])

        first = True
        try:
            while True:
                t0 = time.time()
                try:
                    await scan_once(session, first)
                except Exception as e:
                    log.exception("scan error: %s", e)
                first = False
                elapsed = time.time() - t0
                wait = max(1, POLL_SEC - elapsed)
                log.debug("scan took %.1fs, sleeping %.1fs", elapsed, wait)
                await asyncio.sleep(wait)
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("interrupted")
