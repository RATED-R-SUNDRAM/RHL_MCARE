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
    .user-message {
        background-color: #007AFF;
        color: white;
        padding: 12px 16px;
        border-radius: 18px;
        margin: 8px 0;
        margin-left: auto;
        width: fit-content;
        max-width: 70%;
        text-align: right;
    }
    .bot-message {
        background-color: #E9ECEF;
        color: #000;
        padding: 12px 16px;
        border-radius: 18px;
        margin: 8px 0;
        width: fit-content;
        max-width: 70%;
    }
    .chat-container {
        display: flex;
        flex-direction: column;
        height: 500px;
    }
    .question-format {
        font-weight: bold;
        color: #1f77b4;
        font-size: 16px;
        margin-top: 10px;
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
chat_container = st.container(border=True, height=400)

with chat_container:
    if st.session_state.chat_history:
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="user-message">You: {msg["message"]}</div>', unsafe_allow_html=True)
            else:
                # Format bot message with proper markdown
                bot_msg = msg["message"]
                st.markdown(f'<div class="bot-message">{bot_msg}</div>', unsafe_allow_html=True)
    else:
        st.markdown("💬 *Chat will appear here*")

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
