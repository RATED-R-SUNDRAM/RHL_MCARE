# 🚀 Quick Start (Copy-Paste Commands)

## Prerequisites
```bash
# Install Python 3.8+ first, then:
pip install -r requirements.txt
```

## One-Time Setup
```bash
# Copy environment template
copy .env.example .env

# Edit .env and add your Gemini API key:
# GEMINI_API_KEY=your_actual_key_here
```

---

## Run Locally (2 Terminals)

### Terminal 1: Backend
```powershell
cd d:\RHL_MCARE
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Wait for: `Uvicorn running on http://0.0.0.0:8000`

### Terminal 2: Frontend
```powershell
cd d:\RHL_MCARE
streamlit run frontend/app.py
```

Browser will open to: `http://localhost:8501`

---

## Verify It Works

1. In Streamlit UI, click **"Test Connection"** in Settings
   - Should show: ✅ Backend connected
   
2. Enter user ID: `test123`

3. Click **"Start / Switch User"**

4. Type: `yes`

5. Click **"Send"**

6. Should see first questionnaire question

---

## Troubleshooting

### Error: "Backend not reachable"
```powershell
# Check if backend is running
netstat -ano | findstr :8000

# If not running, start it:
uvicorn backend.main:app --reload
```

### Error: "No secrets found"
```bash
# Create secrets file
mkdir .streamlit
echo backend_url = "http://localhost:8000" > .streamlit/secrets.toml
```

### Port already in use
```powershell
# Kill process on port 8000
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process

# Or use different port:
uvicorn backend.main:app --reload --port 8001
```

---

## Files You Need

```
d:\RHL_MCARE\
├── .env ← Copy from .env.example + add GEMINI_API_KEY
├── .env.example ← Template
├── .streamlit/
│   └── secrets.toml ← Already exists
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── gemini_integration.py
│   ├── schemas.py
│   └── utils.py
├── frontend/
│   └── app.py
└── requirements.txt
```

---

## Expected Output

### Backend startup (✅)
```
INFO:     Uvicorn running on http://0.0.0.0:8000 [Press ENTER to quit]
INFO:     Application startup complete
```

### Frontend startup (✅)
```
Collecting Streamlit usage statistics...
You can disable this at any time by running:
	$ streamlit config set browser.gatherUsageStats false

  You can now view your Streamlit app in your browser.
  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

---

## That's it! 🎉

Your app is now running locally. Follow the Streamlit UI prompts to start the questionnaire.

For production deployment, see `SETUP_GUIDE.md`
