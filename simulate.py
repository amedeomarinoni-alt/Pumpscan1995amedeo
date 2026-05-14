#!/usr/bin/env python3
"""
Simulatore offline: testa detector e logica sticky su tanti casi reali.
"""
import sys, importlib.util, time, os

# Stub aiohttp per ambiente senza rete
class _Stub:
    def __getattr__(self, name): return _Stub()
    def __call__(self, *a, **k): return _Stub()
sys.modules['aiohttp'] = _Stub()
sys.modules['aiohttp'].ClientTimeout = _Stub
sys.modules['aiohttp'].TCPConnector  = _Stub
sys.modules['aiohttp'].ClientSession = _Stub
sys.modules['aiohttp'].ClientError   = Exception

os.environ["NTFY_TOPIC"] = "dummy"
spec = importlib.util.spec_from_file_location("bot", "/home/claude/v25/bot.py")
bot = importlib.util.module_from_spec(spec)
sys.modules["bot"] = bot
spec.loader.exec_module(bot)

PASSED = 0
FAILED = 0
def check(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        print(f"  ✅ {name}")
        PASSED += 1
    else:
        print(f"  ❌ {name}  {detail}")
        FAILED += 1


def make(**kw):
    """Build a fake row with sensible defaults."""
    r = {
        "key": "PAIR_" + kw.get("sym", "X"),
        "sym": kw.get("sym", "X"),
        "name": "", "addr": "ADDR_" + kw.get("sym", "X"),
        "ageMs": 24*3600*1000,
        "vol5m": 0, "vol1h": 0, "vol6h": 0, "vol24h": 5000,
        "chg5m": 0, "chg1h": 0, "chg6h": 0, "chg24h": 0,
        "liq": 5000, "mcap": 100_000,
        "buys24": 100, "sells24": 80,
        "buys1h": 20, "sells1h": 10,
        "buys5m": 5, "sells5m": 3,
        "url": "https://dexscreener.com/x",
        "img": "https://example.com/x.png",
    }
    r.update(kw)
    r["key"] = "PAIR_" + r["sym"]
    r["addr"] = "ADDR_" + r["sym"]
    return r


print("\n" + "="*70)
print("TEST 1: Spencer Pratt (caso reale che il bot v24 ha mancato)")
print("="*70)
# Dati: MC $658K, 1H 22.54%, 6H 13.14%, 24H 647%, vol $69K
spencer = make(sym="PRATT", ageMs=2*24*3600*1000, mcap=658_000,
               vol24h=69_000, vol6h=20_000, vol1h=8000, vol5m=2000,
               chg5m=8.5, chg1h=22.5, chg6h=13.1, chg24h=647,
               liq=30_000, buys1h=80, sells1h=40)
check("Spencer è SPIKE 1H? (1h +22% < 50, no)", not bot.detect_spike_1h(spencer))
check("Spencer è TREND HIGH? (MC 658K, +647%/24h)", bot.detect_trend_high(spencer))
check("Spencer NON è TREND LOW (MC > 200K)", not bot.detect_trend_low(spencer))

# Simulo Spencer al momento dello spike vero (l'iperbole nel grafico)
spencer_spike = make(sym="PRATT", ageMs=2*24*3600*1000, mcap=500_000,
                     vol24h=80_000, vol6h=40_000, vol1h=25_000, vol5m=8000,
                     chg5m=15, chg1h=80, chg6h=120, chg24h=400,
                     liq=30_000, buys1h=120, sells1h=50)
check("Spencer durante spike → SPIKE 1H (1h +80%)", bot.detect_spike_1h(spencer_spike))


print("\n" + "="*70)
print("TEST 2: animaltwt (Niche Baby type, MC piccolo, +275% 24h)")
print("="*70)
# Dati: MC $36K, 5M 15.11%, 1H 105%, 6H 60.50%, 24H 275%, vol $27K, liq $16K
animaltwt = make(sym="ANIMALTWT", ageMs=12*3600*1000, mcap=36_000,
                 vol24h=27_000, vol6h=15_000, vol1h=7000, vol5m=844,
                 chg5m=15.11, chg1h=105, chg6h=60.5, chg24h=275,
                 liq=16_000, buys1h=30, sells1h=20)
check("animaltwt è TREND LOW (MC 36K, +275%/24h)", bot.detect_trend_low(animaltwt))
check("animaltwt è anche SPIKE 1H (+105%)", bot.detect_spike_1h(animaltwt))


print("\n" + "="*70)
print("TEST 3: AI - Artificial Inu (MC $98K, +210% 24h, ma 1H -4.4%)")
print("="*70)
# Dati immagine: MC $98K, 1H -4.4%, 24H 210%, vol $885K, liq $27K
ai = make(sym="AI", ageMs=12*3600*1000, mcap=98_000,
          vol24h=885_000, vol6h=300_000, vol1h=40_000, vol5m=8000,
          chg5m=-2, chg1h=-4.4, chg6h=30, chg24h=210,
          liq=27_000, buys1h=60, sells1h=80)
check("AI è TREND LOW (MC 98K, +210%/24h, healthy)", bot.detect_trend_low(ai))
check("AI NON è SPIKE (1H negativa)", not bot.detect_spike_1h(ai))


print("\n" + "="*70)
print("TEST 4: XAnimals (MC $61K, +76% 24h, +35% 1H, vol $270K)")
print("="*70)
xa = make(sym="XANIMALS", ageMs=7*3600*1000, mcap=61_000,
          vol24h=270_000, vol6h=100_000, vol1h=30_000, vol5m=5000,
          chg5m=2, chg1h=35, chg6h=50, chg24h=76,
          liq=20_000, buys1h=80, sells1h=40)
check("XAnimals NON è TREND LOW (24H<100%)", not bot.detect_trend_low(xa))
check("XAnimals è SPIKE 1H (+35%)? No, sotto 50%", not bot.detect_spike_1h(xa))
# proviamo con 1h più alta
xa2 = dict(xa); xa2["chg1h"] = 65; xa2 = make(**{k:v for k,v in xa2.items() if k != "key" and k != "addr"})
check("XAnimals con 1h +65% → SPIKE 1H", bot.detect_spike_1h(xa2))


print("\n" + "="*70)
print("TEST 5: PUMP token grosso (MC $682M, scartato)")
print("="*70)
pump_big = make(sym="PUMP", mcap=682_000_000, vol24h=608_000,
                chg5m=0.3, chg1h=1.1, chg6h=2, chg24h=3.6,
                liq=1_200_000)
check("PUMP grosso NON è TREND HIGH (MC > 5M)", not bot.detect_trend_high(pump_big))
check("PUMP grosso NON è SPIKE", not bot.detect_spike_1h(pump_big))


print("\n" + "="*70)
print("TEST 6: Honeypot - pump artificiale senza buy ratio")
print("="*70)
honey = make(sym="HONEY", ageMs=2*3600*1000, mcap=20_000,
             vol24h=10_000, vol1h=5000, vol5m=1000,
             chg5m=60, chg1h=120, chg6h=80, chg24h=200,
             liq=2000, buys1h=5, sells1h=50, buys5m=2, sells5m=20)
check("Honey NON è SPIKE (buy ratio <50%)", not bot.detect_spike_1h(honey))
check("Honey NON è EARLY BREAKOUT (buy ratio basso)", not bot.detect_early_breakout(honey))


print("\n" + "="*70)
print("TEST 7: Early breakout su pumpfun fresco")
print("="*70)
fresh = make(sym="FRESH", ageMs=30*60*1000, mcap=20_000,
             vol24h=5000, vol1h=2000, vol5m=2500,
             chg5m=40, chg1h=60, chg6h=40, chg24h=80,
             liq=3000, buys5m=15, sells5m=5)
check("Fresh è EARLY BREAKOUT", bot.detect_early_breakout(fresh))


print("\n" + "="*70)
print("TEST 8: Sticky logic — token resta 'stuck' anche se scende un po'")
print("="*70)
# Simulo Spencer in 2 momenti
bot.trend_sticky.clear()
bot.notif_cd.clear()

# scan 1: Spencer è full trend
spencer1 = make(sym="PRATT", ageMs=2*24*3600*1000, mcap=658_000,
                vol24h=69_000, vol1h=8000, chg1h=22.5, chg6h=13.1, chg24h=647,
                liq=30_000)
if bot.detect_trend_high(spencer1):
    bot.trend_sticky[spencer1["key"]] = {"ts": time.time(), "bucket": "high",
                                          "sym": "PRATT", "addr": spencer1["addr"]}
check("Spencer è entrato in sticky high", spencer1["key"] in bot.trend_sticky)

# scan 2: Spencer scende un po' (24h ora +200%, 1h -10%, ma vol e liq OK)
spencer_cool = make(sym="PRATT", ageMs=2*24*3600*1000+3600_000, mcap=400_000,
                    vol24h=50_000, vol1h=5000, chg1h=-10, chg6h=-5, chg24h=200,
                    liq=25_000)
healthy_cool = bot.is_trending_healthy(spencer_cool)
check("Spencer raffreddato è ancora healthy → sticky resta", healthy_cool)

# scan 3: Spencer è morto (24h scende sotto 40%)
spencer_dead = make(sym="PRATT", ageMs=2*24*3600*1000+3*3600_000, mcap=200_000,
                    vol24h=10_000, vol1h=1000, chg1h=-30, chg6h=-40, chg24h=20,
                    liq=15_000)
healthy_dead = bot.is_trending_healthy(spencer_dead)
check("Spencer morto NON è healthy → sticky cade", not healthy_dead)


print("\n" + "="*70)
print("TEST 9: Notifiche - icona token, CA presente")
print("="*70)
n = bot.notif_spike(animaltwt)
check("Notif SPIKE ha titolo ⚡", "⚡" in n["title"])
check("Notif SPIKE ha CA in body", "CA:" in n["body"] and animaltwt["addr"] in n["body"])
check("Notif SPIKE ha icon URL", n["icon"] == animaltwt["img"])
check("Notif SPIKE ha priorità urgent", n["priority"] == "urgent")

# Token senza immagine → icon = None, ma notifica funziona
no_img = make(sym="NOIMG", img="")
no_img.update({"chg1h": 70, "vol1h": 5000, "mcap": 30_000, "buys1h": 10, "sells1h": 5})
no_img_n = bot.notif_spike(no_img)
check("Token senza img → icon None (fallback emoji)", no_img_n["icon"] is None)
check("Notif funziona ugualmente", "⚡" in no_img_n["title"])


print("\n" + "="*70)
print("TEST 10: Cooldown evita spam")
print("="*70)
bot.notif_cd.clear()
k = "PAIR_TEST"
first = bot.can_notify(k, "SPIKE")
second = bot.can_notify(k, "SPIKE")
check("Prima volta passa", first)
check("Subito dopo blocca", not second)


print("\n" + "="*70)
print("TEST 11: Cooldown per pattern diverso non blocca")
print("="*70)
bot.notif_cd.clear()
a = bot.can_notify("PAIR_X", "SPIKE")
b = bot.can_notify("PAIR_X", "TREND_HIGH")
check("Pattern diversi non si bloccano a vicenda", a and b)


print("\n" + "="*70)
print("TEST 12: Spike di +5000% (bug visualizzazione, scartato)")
print("="*70)
moon = make(sym="MOON", mcap=10_000, vol1h=10000,
            chg1h=99999, chg5m=20, chg6h=200, chg24h=10000,
            buys1h=50, sells1h=20)
check("Spike anomalo (>5000%) viene scartato", not bot.detect_spike_1h(moon))


print("\n" + "="*70)
print("TEST 13: Liquidità troppo bassa scarta")
print("="*70)
rugproof = make(sym="RUG", liq=500, mcap=20_000, vol1h=5000,
                chg1h=80, vol24h=10000, buys1h=20, sells1h=10)
# liq < MIN_LIQ rende parse_pair = None, ma qui passo già parsed
# verifico che is_trending_strict richieda liq >= 2000
check("Liquidità bassa scarta trend", not bot.is_trending_strict(rugproof))


print("\n" + "="*70)
print("TEST 14: Dedupe — stesso token con 2 pair sceglie liq più alta")
print("="*70)
rows = [
    {"key": "P1", "addr": "TOK", "liq": 5000, "sym": "X"},
    {"key": "P2", "addr": "TOK", "liq": 12000, "sym": "X"},
    {"key": "P3", "addr": "OTHER", "liq": 3000, "sym": "Y"},
]
out = bot.dedupe(rows)
check("Dedupe sceglie il pair con liq più alta",
      any(r["key"] == "P2" for r in out) and not any(r["key"] == "P1" for r in out))
check("Token diverso resta", any(r["key"] == "P3" for r in out))


print("\n" + "="*70)
print("TEST 15: fmt() su valori grandi/piccoli/None")
print("="*70)
check("fmt 1.5M", bot.fmt(1_500_000) == "$1.50M")
check("fmt 30K",  bot.fmt(30_000) == "$30.0K")
check("fmt None", bot.fmt(None) == "—")
check("fmt 0",    bot.fmt(0) == "—")


print("\n" + "="*70)
print("TEST 16: fmt_age formattazione")
print("="*70)
check("12h → 12h",  bot.fmt_age(12*3600*1000) == "12h")
check("2g → 2g",    bot.fmt_age(2*24*3600*1000) == "2g")
check("45min",      bot.fmt_age(45*60*1000) == "45min")


print("\n" + "="*70)
print(f"RISULTATO: {PASSED} OK / {FAILED} KO")
print("="*70)
if FAILED > 0:
    sys.exit(1)
