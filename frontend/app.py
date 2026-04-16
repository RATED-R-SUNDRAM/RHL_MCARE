import streamlit as st
import requests
import os
from pathlib import Path

st.set_page_config(
    page_title="Mental Health Assessment",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern chatbot look
st.markdown("""
<style>
    .app-header {
        width: 100%;
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        padding: 18px 20px;
        border-radius: 20px;
        background: linear-gradient(135deg, #f7f9fc, #ffffff);
        box-shadow: 0 12px 28px rgba(0,0,0,0.08);
        margin-bottom: 20px;
        position: sticky;
        top: 0;
        z-index: 999;
    }
    .header-item {
        font-size: 0.95rem;
        color: #2e3a59;
        margin: 0;
    }
    .status-pill {
        padding: 10px 16px;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        font-weight: 600;
        font-size: 0.95rem;
    }
    .status-pill.online {
        background: #e6f4ea;
        color: #166538;
    }
    .status-pill.offline {
        background: #fce8e6;
        color: #7f1d1d;
    }
    .chat-box {
        border: 1px solid #e4e8ef;
        border-radius: 20px;
        background: #ffffff;
        padding: 22px;
        min-height: 460px;
        max-height: 680px;
        overflow-y: auto;
        box-shadow: inset 0 0 0 1px rgba(58, 66, 86, 0.04);
    }
    .user-message {
        background-color: #0d6efd;
        color: white;
        padding: 14px 18px;
        border-radius: 18px;
        margin: 10px 0;
        margin-left: auto;
        width: fit-content;
        max-width: 72%;
        text-align: right;
        word-break: break-word;
    }
    .bot-message {
        background-color: #f1f5fb;
        color: #1f2937;
        padding: 14px 18px;
        border-radius: 18px;
        margin: 10px 0;
        width: fit-content;
        max-width: 78%;
        word-break: break-word;
    }
    .empty-chat {
        color: #6b7280;
        font-style: italic;
        padding: 22px;
    }
    .chat-title {
        margin-bottom: 14px;
        font-weight: 700;
        font-size: 1.05rem;
    }
</style>
""", unsafe_allow_html=True)

def get_backend_url():
    try:
        return st.secrets.get("backend_url", None)
    except (FileNotFoundError, AttributeError):
        pass
    env_url = os.getenv("BACKEND_URL")
    if env_url:
        return env_url
    return os.getenv("BACKEND_URL", "http://localhost:8000")

BACKEND_URL = get_backend_url()

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "session_active" not in st.session_state:
    st.session_state.session_active = False
if "backend_available" not in st.session_state:
    st.session_state.backend_available = False
if "input_key" not in st.session_state:
    st.session_state.input_key = 0
if "session_id" not in st.session_state:
    st.session_state.session_id = None

def check_backend_health():
    try:
        response = requests.get(f"{BACKEND_URL}/docs", timeout=3)
        return response.status_code == 200
    except:
        return False

def send_message(user_id: str, message: str):
    try:
        response = requests.post(
            f"{BACKEND_URL}/chat",
            json={"user_id": user_id, "message": message},
            timeout=15
        )
        response.raise_for_status()
        st.session_state.backend_available = True
        return response.json()
    except Exception as e:
        st.session_state.backend_available = False
        return None

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    st.subheader("Backend Connection")
    st.write(f"**URL:** {BACKEND_URL}")
    
    if st.button("🔗 Test Connection", use_container_width=True):
        if check_backend_health():
            st.success("✅ Backend connected")
            st.session_state.backend_available = True
        else:
            st.error("❌ Backend not responding")
            st.session_state.backend_available = False
    
    with st.expander("📖 Help & FAQ"):
        st.markdown("""
### Getting Started
1. Enter your User ID
2. Click "Start Assessment"
3. Answer each question (a, b, c, or d)

### Assessment Phases
- **PHQ-4**: 4 screening questions
- **GAD-7**: 7 anxiety questions (if needed)
- **PHQ-9**: 9 depression questions (if needed)

### Tips
- Answer honestly for accurate results
- All data is private and secure
- Read each question carefully before answering
        """)
    
    st.divider()
    st.caption("v1.0 Mental Health Assessment")

# Main title
st.title("🧠 Mental Health Assessment Chatbot")
st.markdown("Phased screening for anxiety, depression, and suicidal ideation")

status_text = "✅ Connected to backend" if st.session_state.backend_available else "⚠️ Backend not connected"
status_class = "status-pill online" if st.session_state.backend_available else "status-pill offline"
st.markdown(f"""
<div class="app-header">
  <div class="header-item"><strong>User ID:</strong> {st.session_state.user_id or 'Not set'}</div>
  <div class="header-item"><strong>Session ID:</strong> {st.session_state.session_id or '-'}</div>
  <div class="{status_class}">{status_text}</div>
</div>
""", unsafe_allow_html=True)

# User ID section
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    user_id_input = st.text_input("Your User ID", placeholder="e.g., user_001", key="uid")
with col2:
    if st.button("Start", use_container_width=True, type="primary"):
        if not user_id_input.strip():
            st.error("Please enter a User ID")
        elif not st.session_state.backend_available:
            if not check_backend_health():
                st.error("❌ Backend not responding. Check Settings.")
            else:
                st.session_state.backend_available = True
                st.session_state.user_id = user_id_input.strip()
                st.session_state.session_active = True
                st.session_state.chat_history = []
                st.session_state.input_key = 0
                st.rerun()
        else:
            st.session_state.user_id = user_id_input.strip()
            st.session_state.session_active = True
            st.session_state.chat_history = []
            st.session_state.input_key = 0
            st.rerun()

with col3:
    if st.button("Reset", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.session_active = False
        st.session_state.user_id = None
        st.session_state.input_key = 0
        st.rerun()

# Show connection status
if st.session_state.backend_available:
    st.success("✅ Connected to backend")
elif st.session_state.user_id:
    st.warning("⚠️ Backend not connected. Try 'Test Connection' in Settings.")

# Main chat area - only show if user is active
if not st.session_state.user_id:
    st.info("👤 Enter your User ID and click 'Start' to begin the assessment.")
    st.stop()

# Chat history display
st.markdown("### Conversation")
chat_html = '<div class="chat-box">'
if st.session_state.chat_history:
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            chat_html += f'<div class="user-message">You: {msg["message"]}</div>'
        else:
            bot_msg = msg["message"]
            chat_html += f'<div class="bot-message">{bot_msg}</div>'
else:
    chat_html += '<div class="empty-chat">💬 Chat will appear here</div>'
chat_html += '</div>'
st.markdown(chat_html, unsafe_allow_html=True)

# Input section
st.markdown("### Your Response")
col1, col2 = st.columns([4, 1])

with col1:
    user_input = st.text_input(
        "Type your answer (a, b, c, d or describe)...",
        placeholder="Press Enter to send...",
        key=f"msg_{st.session_state.input_key}",
        label_visibility="collapsed"
    )

with col2:
    send_btn = st.button("Send", use_container_width=True, type="primary")

# Process message on send button click
if send_btn and user_input.strip():
    # Add user message
    st.session_state.chat_history.append({"role": "user", "message": user_input})
    
    # Get backend response
    if st.session_state.backend_available:
        backend_response = send_message(st.session_state.user_id, user_input)
        
        if backend_response:
            st.session_state.session_id = backend_response.get("session_id")
            bot_text = backend_response.get("next_question", "No response from backend")
            
            # Add bot message
            st.session_state.chat_history.append({"role": "bot", "message": bot_text})
            
            # Increment key to clear input
            st.session_state.input_key += 1
            st.rerun()
        else:
            st.error("❌ Failed to get response from backend")
    else:
        st.error("❌ Backend not connected")

# Session info in sidebar
if st.session_state.session_id:
    st.sidebar.divider()
    st.sidebar.markdown(f"**Session ID:** {st.session_state.session_id}")
    st.sidebar.markdown(f"**User:** {st.session_state.user_id}")
