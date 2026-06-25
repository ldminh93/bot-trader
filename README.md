# Futures Operator

A paper-first Binance USDT-M Futures trading bot with a Next.js operations console and a Django execution engine.

## Safety model

Paper trading is the default and works without Binance credentials. Real orders require every gate below:

1. `ENABLE_LIVE_TRADING=true` on the backend.
2. An active encrypted Binance API credential.
3. Explicit `live_mode_requested=true` in the user bot configuration.
4. Successful symbol precision and minimum-notional validation.

Keep withdrawals disabled on every API key. Start on Binance Futures testnet and validate the strategy with paper data before considering live mode.

## Stack

- Next.js 15, TypeScript, Tailwind CSS 4, shadcn-compatible components, Recharts
- Django 5, Django REST Framework, Simple JWT
- Django Channels with JWT-authenticated WebSockets
- PostgreSQL, Redis, Celery worker and beat
- Binance USDT-M Futures REST API with deterministic mock fallback for public market data
- Docker Compose

## Quick start with Docker

Copy the environment file:

```bash
cp .env.example .env
```

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Place the result in `FERNET_KEY`, then start the stack:

```bash
docker compose up --build
```

The backend container runs migrations on startup. To create an administrator:

```bash
docker compose exec backend python manage.py createsuperuser
```

Open:

- Frontend: http://localhost:3333
- Django admin: http://localhost:8080/admin/
- API status: http://localhost:8080/api/status

Register a user, sign in, select a symbol, and press **Start bot**. The Celery beat scheduler evaluates active bots every five seconds. Public Binance failures automatically use deterministic mock market data so the paper workflow remains usable.

## Local development

Backend:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/manage.py migrate
python backend/manage.py runserver 0.0.0.0:8080
```

In separate terminals:

```bash
cd backend && ../.venv/bin/celery -A config worker -l info
```

```bash
cd backend && ../.venv/bin/celery -A config beat -l info
```

Frontend:

```bash
cd frontend
nvm use
npm install
npm run dev
```

The frontend requires Node 20. Run `nvm use` inside `frontend` before installing dependencies or starting Next.js.

Redis must be reachable at `REDIS_URL` for Channels and Celery. SQLite is used automatically when `DATABASE_URL` is absent; PostgreSQL is used by Docker Compose.

## Environment variables

Backend:

- `DJANGO_SECRET_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `BINANCE_TESTNET=true`
- `ENABLE_LIVE_TRADING=false`
- `FERNET_KEY`
- `CORS_ALLOWED_ORIGINS`

Local Django and Celery processes load backend-safe values from the project-root `.env`.
Docker-only `DATABASE_URL` and `REDIS_URL` values are left to Docker Compose, so local
development keeps its SQLite and localhost defaults. Restart every backend, Celery
worker, and Celery beat process after changing trading environment flags.

Frontend:

- `NEXT_PUBLIC_API_URL=http://localhost:8080/api`
- `NEXT_PUBLIC_WS_URL=ws://localhost:8080/ws`

## API

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/bot/config`
- `PUT /api/bot/config`
- `POST /api/bot/start`
- `POST /api/bot/stop`
- `GET /api/market/snapshot?symbol=BTCUSDT`
- `GET /api/trades`
- `GET /api/trades/stats`
- `GET /api/logs`
- `POST /api/binance/credentials`
- `GET /api/binance/connection-test`

WebSocket updates are available at `/ws/bot/?token=<access-token>`.

## Strategy implementation

The engine calculates SMA 7/25/99, ATR 14, ADX 14, volume MA20, taker-volume delta, CVD, slopes, and recent swing levels. It classifies the signal timeframe as SIDEWAY, EARLY, CONFIRMED, or WEAK uptrend/downtrend. Scores combine trend state, moving-average direction, price location, three-candle delta, CVD, open interest, funding, top-trader positioning, and volume expansion.

Entries require a score of at least 75, an EARLY or CONFIRMED trend state, available daily risk, no conflicting open position, and a valid location relative to MA25. EARLY states use 50% of configured risk; CONFIRMED states use 100%. Position sizing uses account risk divided by stop distance. Paper positions take 30% at 1R, 40% at 2R, leave 30% for 3R or the ATR trail, and move the stop to breakeven at 1R. Early exits require any three configured 15m deterioration conditions, and opposite entries wait for a newly closed signal candle.

## Tests

```bash
cd backend
pytest
```

The suite covers indicator calculations, trend classification, signal scoring, risk sizing, paper fills, fees, partial exits, and breakeven behavior.
