# PumpScan Bot v25 — 24/7 Solana detector con ntfy

Funziona **anche con Chrome chiuso, telefono spento, app non aperta**.
Bot Python su server gratuito + push notifications via ntfy.sh.

## Novità v25 rispetto a v24

- ⚡ **SPIKE 1H** — nuovo pattern: cattura pump iperbolici tipo Spencer Pratt (+647%/24h) o animaltwt (+105%/1h) che v24 mancava
- 📌 **Sticky migliorato** — i token in trend restano memorizzati 4h con icona pin, alert ridotto anche se cool-downano
- 🖼️ **Icona token** nella notifica (foto da DexScreener), fallback emoji se manca
- 📋 **Contract address** sempre incluso nel corpo della notifica
- 🛡️ **Anti-honeypot** — buy ratio 24h < 35% → token scartato dai trend
- 🔍 **Watchlist espansa** (spencer, pratt, animal, vote, crisis...) per non perdere meme di nicchia
- 👴 Età token estesa fino a 30 giorni (v24 fermava a 15)

## Cosa rileva

⚡ **Spike 1h** — +50% in 1 ora con volume e buy pressure (pump improvviso)

🌱 **Accumulazione precoce** — micro-cap ($5K-$50K MC) con volume crescente e prezzo stabile

🚀 **Breakout precoce** — micro-cap ($5K-$80K MC) con +25-150% in 5 minuti

🟢 **Trend basso MC** — token MC $5K-$200K con +100%/24h e crescita sana

📈 **Trend alto MC** — token MC $200K-$5M con +100%/24h e crescita sana

📌 **Trend sticky** — token già notificati ma ancora vivi, alert ridotto

## Setup in 10 minuti

### 1. Scegli un nome canale ntfy unico

Inventa una stringa **lunga e segreta** (es. `pumpscan-marco-x9k2m7`).
**Chiunque conosca il nome può ricevere i tuoi alert** → tienilo privato.

### 2. Installa l'app ntfy sul telefono

- **Android**: cerca "ntfy" sul Play Store → apri l'app → premi "+" → metti il nome canale del passo 1 → fine.
- **iOS**: cerca "ntfy" sull'App Store → stesso procedimento.

Da quel momento il telefono riceve push native (anche con app chiusa, schermo spento, ecc).

### 3. Carica il codice su GitHub

1. Vai su https://github.com/new
2. Crea repo (es. `pumpscan-bot`), pubblico o privato
3. Carica i 5 file di questa cartella: `bot.py`, `requirements.txt`, `Procfile`, `render.yaml`, `README.md`

### 4. Deploya su Render.com (gratis, sempre attivo)

1. Vai su https://render.com → **Sign up** con GitHub
2. Dashboard → **New +** → **Background Worker**
3. Connetti il repo `pumpscan-bot`
4. Configurazione:
   - **Name**: pumpscan-bot
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Plan**: **Free**
5. **Environment Variables** → aggiungi:
   - `NTFY_TOPIC` = il nome canale del passo 1 (es. `pumpscan-marco-x9k2m7`)
   - `NTFY_SERVER` = `https://ntfy.sh`
   - `POLL_SEC` = `30`
   - `MIN_LIQ` = `1500`
6. **Create Background Worker**

In ~2 minuti ricevi sull'app ntfy il messaggio "🟢 PumpScan v25 attivo".
Da quel momento sei a posto: notifiche 24/7, niente da tenere aperto.

## Se avevi già v24 su Render

Stessa repo, basta sostituire i file:
1. Su GitHub → repo `pumpscan-bot` → carica i nuovi file (sovrascrivi)
2. Render rileva il push e fa auto-redeploy
3. Le env vars restano, non devi rifare niente

## Variabili — modifica al volo

Su Render → tuo servizio → **Environment** → cambia → Save → auto-redeploy.

| Variabile | Default | Descrizione |
|---|---|---|
| `NTFY_TOPIC` | (richiesto) | Nome canale ntfy unico |
| `NTFY_SERVER` | `https://ntfy.sh` | Server ntfy |
| `POLL_SEC` | `30` | Secondi tra scansioni (15-60) |
| `MIN_LIQ` | `1500` | Liquidità minima USD |
| `DEBUG` | `0` | `1` per log dettagliati |

## Note

- **Render free**: 750 ore/mese, basta per 1 worker sempre acceso
- **Background Worker** resta sempre attivo (no sleep dopo 15min, quello vale solo per Web Service)
- **ntfy.sh free**: senza limiti pratici, no account, no API key
- Cooldown per token: 3-15 min per pattern, niente spam
- Sticky TTL: 4 ore, dopo il token viene rimosso se non è più trending

## Test locale

```bash
pip install -r requirements.txt
python simulate.py     # 39 unit test sui detector
export NTFY_TOPIC=tuo-topic
python bot.py
```

## Privacy

Il nome canale ntfy è la tua chiave. Tutti gli alert passano per `https://ntfy.sh/<TOPIC>` come HTTPS. Per maggior controllo: ntfy self-hosted (vedi docs.ntfy.sh) o nome canale lungo random (UUID).
