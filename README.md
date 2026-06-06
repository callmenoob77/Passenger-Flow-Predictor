# ✈️ Hecatron — Fog Copilot

A passenger rerouting system that helps travelers find alternative transport when flights are cancelled due to fog at Iasi Airport (LRIA).

> **How it works:** The system checks your flight status. If your flight is at risk of fog or cancelled, it maps out alternative flights, trains, and buses, ranking them by latency, price, and transfers to show you the best backup plan.

---

## 🛠️ Quick Setup & Running Locally

Follow these steps to set up and run the project locally on your machine.

### Prerequisites
Make sure you have the following installed:
* **Python 3.10+** & `pip`
* **Node.js 18+** & `npm`

---

### Step 1: Configure Environment Variables (`.env`)

A `.env` file is used to store private credentials securely (like database connections and API keys). 

1. At the root of the project, copy the template file to create a `.env` file:
   ```bash
   cp .env.example .env
   ```
2. Open the newly created `.env` file and verify or fill in:
   * **`SUPABASE_CONN_STRING`**: The connection string to your Supabase PostgreSQL instance.
   * **`AVIATIONSTACK_API_KEY`**: Your API key for live flight validation (optional for local testing since our local mock flight list has pre-configured real flights).

---

### Step 2: Run the Backend (FastAPI API)

1. Open a new terminal window and navigate to the `rerouting` directory:
   ```bash
   cd rerouting
   ```
2. Activate your virtual environment (if you use one):
   * **Linux/macOS**: `source ../venv/bin/activate`
   * **Windows (CMD)**: `..\venv\Scripts\activate.bat`
   * **Windows (PowerShell)**: `..\venv\Scripts\Activate.ps1`
3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the backend API server:
   ```bash
   python3 -m uvicorn api:app --reload --port 8000
   ```
   *The API will be running locally at `http://127.0.0.1:8000`.*

---

### Step 3: Run the Frontend (React + Vite)

1. Open a second terminal window and navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install the frontend dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   *The website will open locally in your browser at `http://localhost:5173/`.*

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/flight/{flight_number}` | Look up a flight details and departure schedules (e.g. `RO 6769`, `OS 704`, `RO 708`) |
| `POST` | `/subscribe` | Register a passenger's email subscription for automated weather notifications |
| `POST` | `/refund` | Submit passenger claim info for ticket refund or 110% airline credits |
| `POST` | `/reroute` | Search for available ranked ground and air alternative travel options |

---

## 🔌 Transport Adapters

The rerouting engine uses a plug-and-play **adapter pattern** — each transport source implements the same interface. If one adapter fails, it's skipped and the rest still work.

| Adapter | Source | Data |
|---|---|---|
| `adapter_flixbus.py` | FlixBus public API (no key needed) | Real-time bus trips with prices |
| `adapter_train.py` | Static CFR timetable (hardcoded) | Iasi → Bucharest trains |
| `adapter_gflights_cached.py` | Pre-scraped Google Flights JSON | 7 days of cached flight data |

### Scoring

Alternatives are ranked by a weighted score *(lower = better)*:

```
score = 1.0 × arrival_lateness_hours + 0.05 × price_eur + 1.5 × transfers
```

Options departing less than **1 hour** after the cancelled flight are filtered out (the passenger needs time to react). Ground transport over **10 hours** is also removed.

---

## 🖥️ Frontend Screens

1. **Home (Screen 1)** — Enter your flight number and email for alerts (automatically registers you in Supabase).
2. **Flight Status (Screen 2)** — See dynamic route information (IAS ➔ Dest), schedule details, and status.
3. **Flight Cancelled (Screen 3)** — EU261 options: request refund or view rerouting alternatives.
4. **Alternatives (Screen 4)** — Ranked options showing flights, buses, and trains with prices, times, and booking links.
5. **Refund Claim (Screen 5)** — Submit passenger personal info and booking PNR reference for claiming credits or original refund.

---

## 🌦️ Data Pipeline

The system ingests METAR weather observations for Iasi Airport (LRIA):

- **`backfill_metar.py`** — Load historical data.
- **`live_ingest.py`** — Runs periodically (cron / GitHub Actions) to keep data fresh.
- **`create_subscriptions_table.py`** — Inits the subscriptions table.
- **`create_refunds_table.py`** — Inits the refund claims table.
