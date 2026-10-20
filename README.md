# 🍽️ SmartCanteen AI

**Full-Stack Machine Learning & Analytics Platform for Sustainable University Dining**

SmartCanteen AI is a production-grade web application engineered to predict food waste, classify operational risk levels, calculate financial losses, and provide data-driven portion recommendations for university dining halls.

Refactored from a monolithic prototype into a modern **React (Vite + TypeScript) + FastAPI** architecture with SQLite prediction persistence and scikit-learn machine learning inference.

---

## 🏗️ System Architecture

```text
React 19 + Vite Frontend (TypeScript + Tailwind CSS)
    │
    │  HTTP / JSON via TanStack Query (Port 5173 / 3000)
    ▼
FastAPI Python Backend (Port 8000)
    │
    ├── Analytics Service ─── Raw Canteen Dataset (2,600 CSV records)
    │
    ├── Prediction Service ── Trained Random Forest Models (.pkl)
    │                            ├── waste_regression_model.pkl
    │                            └── waste_risk_classifier.pkl
    │
    ├── Recommendation Service (Dynamic calculations)
    │
    └── SQLite Persistence ─── data/predictions.db
```

---

## 📁 Repository Structure

```text
SmartCanteen_AI/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI app entrypoint & lifespan
│   │   ├── api/
│   │   │   ├── health.py               # GET /api/health
│   │   │   ├── metadata.py             # GET /api/metadata
│   │   │   ├── analytics.py            # Summary, distributions, records, CSV export
│   │   │   ├── predictions.py          # POST /api/predict, GET/DELETE history
│   │   │   └── models_info.py          # GET /api/models/metrics
│   │   ├── core/
│   │   │   ├── config.py               # Dynamic paths and CORS configuration
│   │   │   └── database.py             # SQLite persistence for prediction history
│   │   ├── schemas/                    # Pydantic v2 validation schemas
│   │   ├── services/
│   │   │   ├── analytics_service.py    # Dataset filtering, KPIs, and aggregation
│   │   │   ├── prediction_service.py   # Feature alignment & model inference
│   │   │   └── recommendation_service.py # Data-driven operational recommendations
│   │   └── tests/                      # Pytest automated test suite (13 tests)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/                 # UI primitives, layout, and charts
│   │   │   ├── dashboard/              # FilterBar, KpiGrid, ChartsSection, Recommendations
│   │   │   ├── layout/                 # Navbar, Footer
│   │   │   └── ui/                     # Card, Button, RiskBadge, Skeleton
│   │   ├── layouts/
│   │   │   └── RootLayout.tsx          # Frame with live API health pulse
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx       # Interactive charts, KPIs & insights
│   │   │   ├── PredictPage.tsx         # AI Prediction sandbox form & cards
│   │   │   ├── HistoryPage.tsx         # SQLite prediction audit table & clear dialog
│   │   │   ├── ModelsPage.tsx          # Model governance, metrics & limitations
│   │   │   └── DataExplorerPage.tsx    # Paginated data grid with CSV export
│   │   ├── services/
│   │   │   └── api.ts                  # Typed client with TanStack Query
│   │   ├── types/                      # TypeScript contracts
│   │   └── lib/                        # Formatting & utility helpers
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── vite.config.ts
├── data/
│   └── raw/
│       └── SmartCanteen_Final_Dataset.csv # 2,600 historical records
├── models/
│   ├── waste_regression_model.pkl      # Random Forest Regressor
│   ├── waste_risk_classifier.pkl       # Random Forest Classifier
│   ├── regression_features.pkl         # 13 aligned feature columns
│   └── classification_features.pkl     # 13 aligned feature columns
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 🚀 Quickstart: Running Locally

### 1. Prerequisites
- **Node.js** v18+ (tested on Node v24)
- **Python** 3.10+ (tested on Python 3.11/3.12/3.14)

### 2. Backend Setup
From the repository root:
```bash
# 1. Install backend dependencies
pip install -r requirements.txt

# 2. Run backend automated test suite
pytest backend/app/tests -v

# 3. Start the FastAPI server
python -m uvicorn backend.app.main:app --reload --port 8000
```
- API Health: `http://localhost:8000/api/health`
- Swagger Interactive Docs: `http://localhost:8000/api/docs`

### 3. Frontend Setup
In a new terminal:
```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install frontend dependencies
npm install --legacy-peer-deps

# 3. Start Vite development server
npm run dev
```
Open your browser at `http://localhost:5173`.

---

## 🐳 Running with Docker Compose

Run both the FastAPI backend and React frontend (served via Nginx) in isolated containers:
```bash
docker compose up --build
```
- Frontend application: `http://localhost:3000`
- Backend API & Swagger: `http://localhost:8000/api/docs`

---

## 📊 Application Features

### 1. Analytics Dashboard (`/`)
- **Real-Time KPIs**: Total Food Waste (kg), Average Waste per Event (kg), Total Financial Loss ($), Matching Records Count, and Average Waste per Meal Service.
- **Multi-Dimension Filters**: Filter by date range, meal period (Breakfast, Lunch, Dinner), canteen section (A, B, C, D), and food category (Meat, Rice, Soup, Vegetables).
- **Interactive Recharts**:
  - Waste by Food Category (Bar Chart)
  - Waste by Meal Period (Bar Chart)
  - Waste by Canteen Section (Bar Chart)
  - Financial Loss by Category (Bar Chart)
  - Waste Risk Distribution (Donut Chart: Low, Medium, High)
  - Daily Waste & Cost Loss Trend (Dual-axis Area Chart)
- **Dynamic AI Recommendations**: Real calculations pinpoint peak waste hours, high-loss categories, and section surpluses.

### 2. AI Prediction Sandbox (`/predict`)
- Input observation date, meal, canteen section, food category, and dish unit price ($/kg).
- Executes dual-model inference:
  - **Random Forest Regressor**: Predicts expected food waste volume (kg).
  - **Random Forest Classifier**: Classifies operational risk tier (`Low`, `Medium`, `High`).
  - **Financial Loss Calculation**: `predicted_waste_kg × unit_price_per_kg`.
- Automatically logs every prediction to SQLite.

### 3. Prediction Audit History (`/history`)
- Persistent log stored in SQLite (`data/predictions.db`).
- Filter by risk level or meal period.
- Includes action to clear history with modal confirmation.

### 4. Model Governance & Insights (`/models`)
- Transparent reporting of the existing models' evaluation metrics:
  - **Regression**: MAE = 1.32 kg, RMSE = 1.55 kg, R² = -0.128
  - **Classification**: Accuracy = 35.38%, Macro F1 = 35.42%
- Transparent explanation of model behavior, dummy encoding, baseline categories, and future improvements (attendance sensor integration, lag features, GBDTs).

### 5. Data Explorer & CSV Export (`/data`)
- Server-side paginated data table of all 2,600 raw records.
- Text search and column sorting.
- 1-click **Export Filtered CSV** streaming from the backend.

---

## 🧪 Testing

Run backend tests:
```bash
pytest backend/app/tests -v
```
All 13 automated tests verify:
- Health and metadata endpoints
- Unfiltered and filtered KPI aggregations
- Category, meal, section, and time-series distributions
- Dynamic recommendation generation
- Prediction inference pipeline and validation errors
- SQLite prediction persistence and history clearing
- Transparency of model governance metrics