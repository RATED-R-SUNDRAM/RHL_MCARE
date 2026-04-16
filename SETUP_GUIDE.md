# Mental Health Assessment Chatbot - Setup Guide

## Overview
This application consists of:
- **Backend**: FastAPI server that processes questionnaires and interacts with Gemini API
- **Frontend**: Streamlit UI that communicates with the backend

---

## Prerequisites
- Python 3.8+
- pip (Python package installer)
- Git (for version control)

---

## Installation

### 1. Clone and Install Dependencies
```bash
cd d:\RHL_MCARE
pip install -r requirements.txt
```

### 2. Create Local .env File
```bash
# Copy the template
copy .env.example .env

# Edit .env and set:
BACKEND_URL=http://localhost:8000
GEMINI_API_KEY=your_actual_gemini_key_here
```

---

## Local Development Setup

### Terminal 1: Start Backend
```bash
# From project root
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Wait for message: `Uvicorn running on http://0.0.0.0:8000`

### Terminal 2: Start Frontend
```bash
# From project root
streamlit run frontend/app.py
```

Frontend will open at `http://localhost:8501`

---

## Local Testing Checklist

1. ✅ Backend is running on `http://localhost:8000`
   - Go to http://localhost:8000/docs to see API docs

2. ✅ Frontend starts without errors on `http://localhost:8501`

3. ✅ Click "Test Connection" in sidebar → should show ✅ Backend connected

4. ✅ Enter a test user ID (e.g., "test_user_1") and click "Start / Switch User"

5. ✅ Type "yes" and click "Send" → should start PHQ-4 questionnaire

---

## Deployment on Streamlit Cloud

### Step 1: Prepare Code
- Ensure `.env` is in `.gitignore` ✅
- Ensure `.streamlit/` folder exists with `config.toml`
- Push clean code to GitHub (no secrets)

### Step 2: Create Streamlit Cloud App
1. Go to https://share.streamlit.io/
2. Click "New app"
3. Connect your GitHub repo
4. Select branch: `main`
5. Set main file path: `frontend/app.py`

### Step 3: Add Secrets in Streamlit Cloud Dashboard
1. In Streamlit Cloud dashboard for your app
2. Click ⚙️ Settings
3. Click "Secrets"
4. Paste the TOML content:
```toml
backend_url = "https://your-deployed-backend.com"
gemini_api_key = "your_gemini_key_here"
```

### Step 4: Deploy Backend (if needed)
If running backend locally during testing, you'll need to deploy it for cloud use:
- Options: Heroku, Railway, AWS, Google Cloud, or similar
- Update `backend_url` in Streamlit secrets accordingly

---

## Configuration Files

### `.env` (Local Only - Git Ignored)
```
BACKEND_URL=http://localhost:8000
GEMINI_API_KEY=your_key_here
```

### `.streamlit/secrets.toml` (Local Development)
```toml
backend_url = "http://localhost:8000"
```

### `.streamlit/config.toml` (Optional)
```toml
[theme]
primaryColor = "#0084ff"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
```

---

## Troubleshooting

### ❌ "Backend not reachable"
**Cause**: Backend API is not running

**Fix**:
1. Open terminal and run: `uvicorn backend.main:app --reload`
2. Wait for it to start
3. Click "Test Connection" in Streamlit

### ❌ "Connection refused [WinError 10061]"
**Cause**: Backend not listening on port 8000

**Fix**:
1. Check if port 8000 is in use: `netstat -ano | findstr :8000` (Windows)
2. Try different port: `uvicorn backend.main:app --port 8001`
3. Update `BACKEND_URL=http://localhost:8001` in Streamlit settings

### ❌ "StreamlitSecretNotFoundError"
**Cause**: No `.streamlit/secrets.toml` in local

**Fix**:
- Create `.streamlit/` folder
- Create `secrets.toml` with:
  ```toml
  backend_url = "http://localhost:8000"
  ```

### ❌ Streamlit Cloud: Backend URL is wrong
**Fix**: 
1. Go to Streamlit Cloud dashboard
2. Click app settings
3. Update `backend_url` in Secrets
4. Redeploy app

---

## What's Required

### Locally
- ✅ Python 3.8+
- ✅ All packages from `requirements.txt`
- ✅ `.env` file with `BACKEND_URL` and `GEMINI_API_KEY`
- ✅ Backend running on `http://localhost:8000`

### On Streamlit Cloud
- ✅ GitHub repo (public or private)
- ✅ Streamlit account (free tier works)
- ✅ Backend deployed somewhere accessible (or local backend if testing)
- ✅ Secrets set in Streamlit Cloud dashboard:
  - `backend_url`: Your backend URL
  - `gemini_api_key`: Your Gemini key

---

## Environment Precedence (Frontend)

The frontend looks for `BACKEND_URL` in this order:
1. `.streamlit/secrets.toml` (if using Streamlit)
2. `BACKEND_URL` environment variable (from `.env`)
3. Default: `http://localhost:8000`

This allows flexibility for local dev and cloud deployment.

---

## Quick Start Summary

### For Local Testing
```bash
# Terminal 1
uvicorn backend.main:app --reload

# Terminal 2
streamlit run frontend/app.py

# In browser: http://localhost:8501
# Click "Test Connection" → should pass
# Enter user ID → type "yes" → see questions
```

### For Production (Streamlit Cloud)
```bash
# Push to GitHub
git add .
git commit -m "Ready for deployment"
git push origin main

# Deploy via Streamlit Cloud UI
# Set secrets in dashboard
# Done!
```

---

## Support

- Backend docs: http://localhost:8000/docs (local) or /docs on deployed URLs
- Streamlit docs: https://docs.streamlit.io/
- Gemini API docs: https://ai.google.dev/
