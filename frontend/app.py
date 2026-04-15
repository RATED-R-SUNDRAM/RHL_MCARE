import streamlit as st
import requests

st.set_page_config(page_title="Mental Health Chatbot", page_icon="🧠", layout="centered")

BACKEND_URL = st.secrets.get("backend_url", "http://localhost:8000")

if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "current_state" not in st.session_state:
    st.session_state.current_state = "PHQ4"
if "progress_message" not in st.session_state:
    st.session_state.progress_message = ""
if "last_prompt" not in st.session_state:
    st.session_state.last_prompt = ""
if "error_message" not in st.session_state:
    st.session_state.error_message = ""


def reset_chat():
    st.session_state.session_id = None
    st.session_state.chat_history = []
    st.session_state.current_state = "PHQ4"
    st.session_state.progress_message = ""
    st.session_state.last_prompt = ""
    st.session_state.error_message = ""


def send_message(user_id: str, message: str):
    payload = {"user_id": user_id, "message": message}
    try:
        response = requests.post(f"{BACKEND_URL}/chat", json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        st.session_state.error_message = f"Backend request failed: {exc}"
        return None


st.title("Mental Health Assessment Chatbot")
st.write(
    "This chat connects to the backend assessment API. Start by choosing a user ID and typing `yes` to begin the questionnaire."
)

with st.sidebar:
    st.header("Settings")
    backend_url = st.text_input("Backend URL", value=BACKEND_URL)
    if backend_url != BACKEND_URL:
        st.write("Restart app to apply backend URL change.")

st.text_input("User ID", key="user_id_input")
col1, col2 = st.columns([1, 1])
with col1:
    if st.button("Start / Switch User"):
        st.session_state.user_id = st.session_state.user_id_input.strip()
        reset_chat()
        if not st.session_state.user_id:
            st.session_state.error_message = "Enter a valid user ID before starting."
        else:
            st.session_state.error_message = ""
with col2:
    if st.button("Clear Chat"):
        reset_chat()

if st.session_state.error_message:
    st.error(st.session_state.error_message)

if not st.session_state.user_id:
    st.info("Enter a user ID and click Start / Switch User to begin.")
    st.stop()

if st.session_state.chat_history:
    for item in st.session_state.chat_history:
        if item["role"] == "user":
            st.markdown(f"**You:** {item['message']}")
        else:
            st.markdown(f"**Bot:** {item['message']}")
else:
    st.info("Type 'yes' to start the questionnaire.")

if st.session_state.progress_message:
    st.markdown(f"**Status:** {st.session_state.progress_message}")

user_message = st.text_input("Your answer", key="user_message_input")
if st.button("Send"):
    if not user_message.strip():
        st.warning("Please type a response before sending.")
    else:
        if not st.session_state.user_id:
            st.warning("Please set a user ID first.")
        else:
            st.session_state.chat_history.append({"role": "user", "message": user_message})
            backend_response = send_message(st.session_state.user_id, user_message)
            if backend_response:
                st.session_state.session_id = backend_response.get("session_id")
                st.session_state.current_state = backend_response.get("current_state", st.session_state.current_state)
                st.session_state.progress_message = backend_response.get("progress_message", "")
                bot_text = backend_response.get("next_question", "")
                if backend_response.get("clarification_needed"):
                    bot_text = f"{bot_text}\n\n(Please clarify your answer.)"
                st.session_state.chat_history.append({"role": "bot", "message": bot_text})
                st.session_state.last_prompt = bot_text

if st.session_state.session_id:
    st.sidebar.success(f"Session ID: {st.session_state.session_id}")
    st.sidebar.write(f"Current state: {st.session_state.current_state}")
    if st.session_state.progress_message:
        st.sidebar.write(st.session_state.progress_message)

if st.session_state.last_prompt and not st.session_state.chat_history[-1]["role"] == "bot":
    st.info(st.session_state.last_prompt)

st.markdown("---")
st.caption("The app sends chat inputs to the FastAPI backend and displays the bot's next question.")
