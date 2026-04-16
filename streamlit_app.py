import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover
    genai = None

st.set_page_config(page_title="Mental Health Assessment", page_icon="MH", layout="wide")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

DB_PATH = "mental_health_single.db"
ARCHIVE_DB_PATH = "questionnaire_archive_single.db"

ANXIETY_SUPPORT_VIDEO = "https://rhlaiservice2.blob.core.windows.net/mcare/anxiety/Anxiety-coping.m3u8"
DEPRESSION_SUPPORT_VIDEO = "https://rhlaiservice2.blob.core.windows.net/mcare/depression/depression.m3u8"
SUICIDE_SUPPORT_VIDEO = "https://rhlaiservice2.blob.core.windows.net/mcare/suicide/suicide.m3u8"

ANXIETY_SELF_HELP = """
Anxiety may sometimes seem random; but there is usually an underlying cause related to genetics, brain function, or co-occurring health conditions. Professional help can assist in uncovering these deeper factors. Symptoms of anxiety can be triggered or worsened by specific factors such as caffeine, certain medications, financial concerns, and stress.

You can identify personal triggers by journaling, therapy, and self-reflection.

Techniques to Help Overcome Anxiety
Effective coping strategies to manage anxiety include:
1. Grounding: A technique to feel calm by engaging in your current environment.
   - Name 3 things you see.
   - Identify 3 sounds you hear.
   - Move or touch 3 things (e.g., your limbs or objects).
2. Breathing Exercises: Take a deep breath, hold for 2-5 seconds, and then breathe out.
3. Meditation: Practice re-centering your body and mind.
4. Massage: Helps ease physical tension.

If these techniques are not effective, or for underlying causes, seek professional help from a health care professional.
"""

DEPRESSION_SELF_HELP = """
Depression is a common condition which is like a passing mood or a day of feeling down. It can be managed using the following strategies:
1. Challenge negative thoughts by replacing them with balanced ones. Identify negative thoughts like "I am worthless" and replace them with balanced ones like "I am struggling, but that does not mean I am worthless."
2. Engage in small, meaningful activities like taking a walk, regular exercise, etc.
3. Maintaining a healthy routine (consistent sleep/meals). Go to bed and wake up at the same time daily; avoid screens before bed.
4. Break problems into smaller, manageable parts instead of feeling overwhelmed.
5. Write down 2-3 things you are thankful for each day.
6. Isolation makes depression worse; connecting with friends, family or support groups helps to lighten your thoughts.
7. Limit the use of alcohol and caffeine.

If you feel that you cannot cope with the symptoms, seek professional help: A doctor, psychologist, or counselor can provide support and treatment options.
"""

SUICIDE_SELF_HELP = """
When suicidal thoughts come, they often feel overwhelming and permanent. However, there are coping strategies that can help you to connect with the present.
1. Ground Yourself in the Present: Use the 5-4-3-2-1 technique (seeing, touching, hearing, smelling, tasting) to reconnect to the here and now when thoughts feel overwhelming.
2. Hold something comforting like a soft object or a pet.
3. A written safety plan can guide you when you are in crisis. It usually includes:
   Warning signs: What thoughts, feelings, or behaviors tell me I am in danger?
   Coping strategies: What can I do right now to feel safer (walk, breathe, music, call a friend)?
   Safe spaces or distractions: Where can I go or what can I do that feels calming (a park, my room, faith community)?
   People I can contact include friend/family, Counselor, Helpline.
   Remove or avoid anything that you could use to harm yourself.
4. Reach out immediately to a trusted person (call, text, or write) as isolation fuels suicidal thinking. Send a simple message like, "I am not okay right now. Can we talk?"
5. Listen to calming music or pray, meditate, or read a meaningful passage.
6. Try challenging hopeless thoughts like "I cannot handle this" to "I have handled hard things before, even when I did not think I could."
7. When you are in crisis, it is easy to forget why life matters. Write a list of things, big or small, that have meaning to you like people who care about you, dreams or goals you have not yet tried, pets, nature, music, kindness, faith, learning - anything that sparks life. Keep this list somewhere you can reach for it when you feel low.
8. Get Professional Support
"""

QUESTIONNAIRES = {
    "PHQ4": {
        "questions": [
            "Over the last 2 weeks, how often have you been bothered by feeling nervous, anxious, or on edge?",
            "Over the last 2 weeks, how often have you been bothered by not being able to stop or control worrying?",
            "Over the last 2 weeks, how often have you been bothered by little interest or pleasure in doing things?",
            "Over the last 2 weeks, how often have you been bothered by feeling down, depressed, or hopeless?",
        ]
    },
    "GAD7": {
        "questions": [
            "Feeling nervous, anxious or on edge",
            "Not being able to stop or control worrying",
            "Worrying too much about different things",
            "Trouble relaxing",
            "Being so restless that it is hard to sit still",
            "Becoming easily annoyed or irritable",
            "Feeling afraid as if something awful might happen",
        ]
    },
    "PHQ9": {
        "questions": [
            "Little interest or pleasure in doing things",
            "Feeling down, depressed, or hopeless",
            "Trouble falling or staying asleep, or sleeping too much",
            "Feeling tired or having little energy",
            "Poor appetite or overeating",
            "Feeling bad about yourself or that you are a failure, or have let your family down",
            "Trouble concentrating on things, such as reading the newspaper or watching television",
            "Moving or speaking so slowly that other people could have noticed, or being so fidgety that you have been moving around a lot more than usual",
            "Thoughts that you would be better off dead, or of hurting yourself in some way",
        ]
    },
}

OPTIONS = {
    "a": "Not at all",
    "b": "Several days",
    "c": "More than half the days",
    "d": "Nearly every day",
}


# ----------------------------
# Optional Gemini setup
# ----------------------------
def get_api_key() -> Optional[str]:
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]

    return (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GEMINI_API_KEYS")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_API_KEYS")
    )


def configure_gemini() -> bool:
    api_key = get_api_key()
    if not api_key or genai is None:
        return False
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception:
        return False


def check_gemini_response() -> Dict[str, str]:
    if not GEMINI_CONFIGURED:
        return {"ok": "false", "message": "Gemini not configured."}

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content("Respond with exactly: OK")
        text = (response.text or "").strip()
        if text:
            return {"ok": "true", "message": f"Gemini response received: {text[:120]}"}
        return {"ok": "false", "message": "Gemini returned an empty response."}
    except Exception as e:
        return {"ok": "false", "message": f"Gemini check failed: {e}"}


GEMINI_CONFIGURED = configure_gemini()


# ----------------------------
# DB layer (embedded backend)
# ----------------------------
def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_archive_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(ARCHIVE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_session TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            current_state TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS responses (
            response_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            questionnaire TEXT,
            question_no INTEGER,
            score INTEGER,
            raw_response TEXT,
            gemini_confidence TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            score_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            questionnaire TEXT,
            total_score INTEGER,
            severity_level TEXT,
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_flags (
            flag_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            risk_type TEXT,
            flag_details TEXT,
            flagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS trackers (
            tracker_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            phq4_needed INTEGER DEFAULT 1,
            phq4_progress INTEGER DEFAULT 0,
            gad7_needed INTEGER DEFAULT 0,
            gad7_progress INTEGER DEFAULT 0,
            phq9_needed INTEGER DEFAULT 0,
            phq9_progress INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
        """
    )

    conn.commit()
    conn.close()

    archive_conn = get_archive_connection()
    archive_cursor = archive_conn.cursor()
    archive_cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS completed_questionnaires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            year INTEGER,
            month INTEGER,
            date INTEGER,
            time TEXT,
            questionnaire TEXT,
            responses TEXT,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    archive_conn.commit()
    archive_conn.close()


def get_or_create_user(user_id: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, last_session) VALUES (?, ?)",
            (user_id, datetime.now()),
        )
    conn.commit()
    conn.close()


def get_user_session(user_id: str) -> Dict:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY started_at DESC LIMIT 1",
        (user_id,),
    )
    session = cursor.fetchone()

    if session and not session["ended_at"]:
        conn.close()
        return dict(session)

    cursor.execute(
        "INSERT INTO sessions (user_id, current_state) VALUES (?, ?)",
        (user_id, "PHQ4_PENDING"),
    )
    session_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO trackers (session_id, phq4_needed, phq4_progress, gad7_needed, gad7_progress, phq9_needed, phq9_progress)
        VALUES (?, 1, 0, 0, 0, 0, 0)
        """,
        (session_id,),
    )

    conn.commit()
    cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    new_session = cursor.fetchone()
    conn.close()
    return dict(new_session)


def get_tracker(session_id: int) -> Dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trackers WHERE session_id = ?", (session_id,))
    tracker = cursor.fetchone()
    conn.close()
    return dict(tracker) if tracker else {}


def get_recent_history(session_id: int, limit: int = 5) -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT questionnaire, question_no, raw_response, gemini_confidence, timestamp
        FROM responses
        WHERE session_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (session_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()

    history = []
    for row in reversed(rows):
        history.append(
            {
                "user": row["raw_response"],
                "bot": f"Answered {row['questionnaire']} Q{row['question_no'] + 1}",
            }
        )
    return history


def save_response(session_id: int, questionnaire: str, question_no: int, score: int, raw: str, confidence: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO responses (session_id, questionnaire, question_no, score, raw_response, gemini_confidence, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, questionnaire, question_no, score, raw, confidence, datetime.now()),
    )
    conn.commit()
    conn.close()


def update_tracker_progress(session_id: int, questionnaire: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    field_name = f"{questionnaire.lower()}_progress"
    cursor.execute(f"UPDATE trackers SET {field_name} = {field_name} + 1 WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def get_session_responses(session_id: int, questionnaire: str) -> List[int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT score FROM responses
        WHERE session_id = ? AND questionnaire = ?
        ORDER BY question_no ASC
        """,
        (session_id, questionnaire),
    )
    rows = cursor.fetchall()
    conn.close()
    return [int(r[0]) for r in rows]


def save_score(session_id: int, questionnaire: str, total_score: int, severity: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scores (session_id, questionnaire, total_score, severity_level, calculated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, questionnaire, total_score, severity, datetime.now()),
    )
    conn.commit()
    conn.close()


def save_risk_flag(session_id: int, risk_type: str, details: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO risk_flags (session_id, risk_type, flag_details, flagged_at)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, risk_type, details, datetime.now()),
    )
    conn.commit()
    conn.close()


def save_completed_questionnaire(user_id: str, questionnaire: str, responses: List[int]) -> None:
    now = datetime.now()
    conn = get_archive_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO completed_questionnaires (user_id, year, month, date, time, questionnaire, responses)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            now.year,
            now.month,
            now.day,
            now.strftime("%H:%M:%S"),
            questionnaire,
            json.dumps(responses),
        ),
    )
    conn.commit()
    conn.close()


def update_session_state(session_id: int, new_state: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET current_state = ? WHERE session_id = ?", (new_state, session_id))
    conn.commit()
    conn.close()


def end_session(session_id: int) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET ended_at = ? WHERE session_id = ?", (datetime.now(), session_id))
    conn.commit()
    conn.close()


# ----------------------------
# Orchestration + tools logic
# ----------------------------
def option_to_score(option: str) -> int:
    mapping = {"a": 0, "b": 1, "c": 2, "d": 3}
    return mapping.get(option.lower(), -1)


def get_question(questionnaire: str, question_no: int) -> str:
    if questionnaire in QUESTIONNAIRES and 0 <= question_no < len(QUESTIONNAIRES[questionnaire]["questions"]):
        return QUESTIONNAIRES[questionnaire]["questions"][question_no]
    return ""


def format_question_with_options(questionnaire: str, question_no: int) -> str:
    question = get_question(questionnaire, question_no)
    return (
        f"{question}\n\n"
        "a) Not at all\n"
        "b) Several days\n"
        "c) More than half the days\n"
        "d) Nearly every day"
    )


def get_severity_level(questionnaire: str, score: int) -> str:
    if questionnaire == "PHQ4":
        if score <= 2:
            return "Minimal"
        if score <= 5:
            return "Mild"
        if score <= 8:
            return "Moderate"
        return "Severe"

    if questionnaire == "GAD7":
        if score <= 4:
            return "Minimal Anxiety"
        if score <= 9:
            return "Mild Anxiety"
        if score <= 14:
            return "Moderate Anxiety"
        return "Severe Anxiety"

    if score <= 4:
        return "Minimal Depression"
    if score <= 9:
        return "Mild Depression"
    if score <= 14:
        return "Moderate Depression"
    if score <= 19:
        return "Moderately Severe Depression"
    return "Severe Depression"


def fallback_parse_response(user_response: str) -> Dict:
    response_lower = user_response.lower().strip()
    if response_lower in ["a", "option a", "a)", "not at all", "0"]:
        return {"confidence": "high", "option": "a", "reason": "Option A matched"}
    if response_lower in ["b", "option b", "b)", "several days", "1"]:
        return {"confidence": "high", "option": "b", "reason": "Option B matched"}
    if response_lower in ["c", "option c", "c)", "more than half", "2"]:
        return {"confidence": "high", "option": "c", "reason": "Option C matched"}
    if response_lower in ["d", "option d", "d)", "nearly every", "3"]:
        return {"confidence": "high", "option": "d", "reason": "Option D matched"}
    return {"confidence": "low", "reason": "Response unclear"}


def _is_affirmative(text: str) -> bool:
    return bool(re.search(r"\b(yes|yep|sure|ok|okay|start|continue|go ahead|ready|lets do it|lets start)\b", text, re.I))


def _is_negative(text: str) -> bool:
    return bool(re.search(r"\b(no|not now|skip|later|quit|cancel|stop|end|done|finished|dont want)\b", text, re.I))


def _is_quit_request(text: str) -> bool:
    return bool(re.search(r"\b(quit|stop|end|cancel|done for now|finished)\b", text, re.I))


def _is_offtopic(text: str) -> bool:
    return bool(re.search(r"\b(weather|movies|sports|jokes|news|song|music|family|work|life|politics)\b", text, re.I))


def local_orchestrator_fallback(user_message: str, current_state: str, trackers: dict, recent_history: list, user_id: Optional[str] = None) -> dict:
    user_text = user_message.strip()
    lower_text = user_text.lower()

    if current_state == "PHQ4_PENDING":
        prompt = (
            "I have a few friendly questions that can help me assess how you are feeling. "
            "Would you like to start now?"
        )

        if _is_affirmative(lower_text):
            return {
                "action": "ASK_QUESTION",
                "questionnaire": "PHQ4",
                "question_number": 0,
                "interpreted_option": None,
                "confidence": "high",
                "next_message": "",
                "reasoning": "User gave permission to start PHQ-4.",
                "update_progress": False,
                "complete_questionnaire": False,
            }

        if _is_negative(lower_text):
            return {
                "action": "CLARIFY",
                "questionnaire": "PHQ4",
                "question_number": 0,
                "interpreted_option": None,
                "confidence": "high",
                "next_message": "No problem. When you are ready, just say yes and I can start the screening questions.",
                "reasoning": "User declined to start the screening questions for now.",
                "update_progress": False,
                "complete_questionnaire": False,
            }

        return {
            "action": "ASK_CONSENT",
            "questionnaire": "PHQ4",
            "question_number": 0,
            "interpreted_option": None,
            "confidence": "medium",
            "next_message": prompt,
            "reasoning": "Asking permission to begin the screening questions.",
            "update_progress": False,
            "complete_questionnaire": False,
        }

    if current_state == "PHQ4_RESULTS":
        if _is_affirmative(lower_text):
            if trackers.get("gad7_needed"):
                q = "GAD7"
            elif trackers.get("phq9_needed"):
                q = "PHQ9"
            else:
                q = None
            return {
                "action": "ASK_QUESTION" if q else "COMPLETE_ASSESSMENT",
                "questionnaire": q,
                "question_number": 0,
                "interpreted_option": None,
                "confidence": "high",
                "next_message": "",
                "reasoning": "User agreed to continue with follow-up questions.",
                "update_progress": False,
                "complete_questionnaire": False,
            }
        if _is_negative(lower_text):
            return {
                "action": "COMPLETE_ASSESSMENT",
                "questionnaire": None,
                "question_number": 0,
                "interpreted_option": None,
                "confidence": "high",
                "next_message": "Okay. You can restart the follow-up questions anytime if you like.",
                "reasoning": "User declined follow-up questions.",
                "update_progress": False,
                "complete_questionnaire": False,
            }
        return {
            "action": "CLARIFY",
            "questionnaire": None,
            "question_number": 0,
            "interpreted_option": None,
            "confidence": "low",
            "next_message": "If you prefer, we can retake the primary screening questions first. Otherwise reply yes to continue with follow-up questions or no to stop.",
            "reasoning": "Awaiting clear follow-up consent or decline.",
            "update_progress": False,
            "complete_questionnaire": False,
        }

    if _is_quit_request(lower_text):
        return {
            "action": "COMPLETE_ASSESSMENT",
            "questionnaire": None,
            "question_number": 0,
            "interpreted_option": None,
            "confidence": "high",
            "next_message": "I understand. We can stop here. If you like, you can restart the assessment anytime.",
            "reasoning": "User requested to stop the questionnaire.",
            "update_progress": False,
            "complete_questionnaire": False,
        }

    if current_state in ["PHQ9", "GAD7", "PHQ4"]:
        progress = trackers.get(f"{current_state.lower()}_progress", 0)
        max_questions = 9 if current_state == "PHQ9" else 7 if current_state == "GAD7" else 4
        parse_result = fallback_parse_response(user_message)

        if parse_result.get("confidence") == "high":
            return {
                "action": "UPDATE_STATUS",
                "questionnaire": current_state,
                "question_number": progress,
                "interpreted_option": parse_result["option"],
                "confidence": "high",
                "next_message": "Thank you. Let's continue.",
                "reasoning": "Direct answer detected for the current questionnaire.",
                "update_progress": True,
                "complete_questionnaire": progress + 1 >= max_questions,
            }

        if _is_offtopic(lower_text):
            return {
                "action": "REDIRECT",
                "questionnaire": current_state,
                "question_number": progress,
                "interpreted_option": None,
                "confidence": "low",
                "next_message": "I understand, but let's keep going with the questionnaire. Please answer the current question.",
                "reasoning": "The user message appears unrelated to the assessment.",
                "update_progress": False,
                "complete_questionnaire": False,
            }

        if _is_affirmative(lower_text):
            return {
                "action": "REDIRECT",
                "questionnaire": current_state,
                "question_number": progress,
                "interpreted_option": None,
                "confidence": "low",
                "next_message": "I hear you. Let's keep going with the current set of questions - please answer the current question.",
                "reasoning": "User provided an affirmative response during an active questionnaire.",
                "update_progress": False,
                "complete_questionnaire": False,
            }

        return {
            "action": "CLARIFY",
            "questionnaire": current_state,
            "question_number": progress,
            "interpreted_option": None,
            "confidence": "low",
            "next_message": "I didn't understand that. Please answer using one of the options a, b, c, or d.",
            "reasoning": "Could not interpret the user's answer.",
            "update_progress": False,
            "complete_questionnaire": False,
        }

    if current_state == "COMPLETED":
        if _is_affirmative(lower_text) or _is_negative(lower_text):
            return {
                "action": "COMPLETE_ASSESSMENT",
                "questionnaire": None,
                "question_number": 0,
                "interpreted_option": None,
                "confidence": "high",
                "next_message": "This session is already complete. If you like, you can start a new screening anytime.",
                "reasoning": "User responded after session completion.",
                "update_progress": False,
                "complete_questionnaire": False,
            }

        return {
            "action": "CLARIFY",
            "questionnaire": None,
            "question_number": 0,
            "interpreted_option": None,
            "confidence": "low",
            "next_message": "This session is complete. If you want to start again, just say start.",
            "reasoning": "Session complete and awaiting instruction.",
            "update_progress": False,
            "complete_questionnaire": False,
        }

    return {
        "action": "CLARIFY",
        "questionnaire": None,
        "question_number": 0,
        "interpreted_option": None,
        "confidence": "low",
        "next_message": "Let's continue with the questionnaire. Please answer the current question.",
        "reasoning": "Default fallback when no specific flow matches.",
        "update_progress": False,
        "complete_questionnaire": False,
    }


def orchestrate_flow(user_message: str, current_state: str, trackers: dict, recent_history: list, session_id: int, user_id: str) -> dict:
    if not GEMINI_CONFIGURED:
        logger.warning("Gemini is not configured; using local fallback orchestrator.")
        result = local_orchestrator_fallback(user_message, current_state, trackers, recent_history, user_id)
        result["orchestrator_source"] = "fallback"
        return result

    tracker_summary = f"""
Current State: {current_state}
PHQ9 Progress: {trackers.get('phq9_progress', 0)}/9
GAD7 Progress: {trackers.get('gad7_progress', 0)}/7
PHQ4 Progress: {trackers.get('phq4_progress', 0)}/4
PHQ9 Needed: {trackers.get('phq9_needed', False)}
GAD7 Needed: {trackers.get('gad7_needed', False)}
"""

    history_summary = "\n".join([f"User: {h['user']}\nBot: {h['bot']}" for h in recent_history[-5:]])

    prompt = f"""You are the central orchestrator for a mental health assessment chatbot. Your role is to manage the entire conversation flow intelligently.

PRIMARY GOAL: Always start with the PHQ-4 screening questions first. After PHQ-4, suggest anxiety follow-up if the first two items sum to 2 or more, and suggest depression follow-up if the last two items sum to 2 or more.

CURRENT CONTEXT:
{tracker_summary}

RECENT CONVERSATION HISTORY (last 5 exchanges):
{history_summary}

USER'S LATEST MESSAGE:
"{user_message}"

OUTPUT FORMAT (ONLY VALID JSON):
{{
  "action": "ASK_QUESTION|CLARIFY|CONFIRM|UPDATE_STATUS|COMPLETE_ASSESSMENT|REDIRECT|ASK_CONSENT",
  "questionnaire": "PHQ9|GAD7|PHQ4|null",
  "question_number": 0,
  "interpreted_option": "a|b|c|d|null",
  "confidence": "high|medium|low",
  "next_message": "Exact text to send to user",
  "reasoning": "Brief explanation of decision",
  "update_progress": true,
  "complete_questionnaire": false
}}

Return ONLY the JSON object."""

    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        response_text = (response.text or "").strip()
        logger.info("[ORCHESTRATOR LOG] Session %s: %s", session_id, response_text)

        st.session_state["last_gemini_response"] = response_text or "<empty>"

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {
                    "action": "CLARIFY",
                    "next_message": "I didn't understand that. Can you please clarify?",
                    "reasoning": "Failed to parse LLM response",
                    "update_progress": False,
                    "complete_questionnaire": False,
                }

        result["orchestrator_source"] = "gemini"
        return result
    except Exception as e:
        logger.error("Gemini orchestrator error: %s", e)
        st.session_state["last_gemini_response"] = f"error: {e}"

    result = local_orchestrator_fallback(user_message, current_state, trackers, recent_history, user_id)
    result["orchestrator_source"] = "fallback"
    return result


# ----------------------------
# Chat processing (embedded main.py logic)
# ----------------------------
def process_chat(user_id: str, message: str) -> Dict:
    request_start = time.time()

    user_id = user_id.strip()
    message = message.strip()
    if not user_id or not message:
        return {"next_question": "user_id and message are required."}

    get_or_create_user(user_id)
    session = get_user_session(user_id)
    session_id = int(session["session_id"])
    trackers = get_tracker(session_id)
    current_state = session["current_state"]
    recent_history = get_recent_history(session_id, limit=5)

    orch = orchestrate_flow(message, current_state, trackers, recent_history, session_id, user_id)
    action = orch.get("action", "CLARIFY")
    questionnaire = orch.get("questionnaire")
    question_number = int(orch.get("question_number", 0))
    interpreted_option = orch.get("interpreted_option")
    confidence = orch.get("confidence", "low")
    orchestrator_source = orch.get("orchestrator_source", "fallback")
    next_message = orch.get("next_message", "")
    update_progress = bool(orch.get("update_progress", False))
    complete_questionnaire = bool(orch.get("complete_questionnaire", False))

    if action in ["UPDATE_STATUS", "COMPLETE_ASSESSMENT"] and questionnaire and interpreted_option:
        score = option_to_score(interpreted_option)
        if score < 0:
            return {"next_question": "Invalid option. Use a, b, c, or d."}

        save_response(session_id, questionnaire, question_number, score, message, confidence)
        if update_progress:
            update_tracker_progress(session_id, questionnaire)

        tracker = get_tracker(session_id)
        max_questions = {"PHQ4": 4, "GAD7": 7, "PHQ9": 9}
        current_progress = int(tracker.get(f"{questionnaire.lower()}_progress", 0))
        is_complete = current_progress >= max_questions[questionnaire] or question_number + 1 >= max_questions[questionnaire]

        if is_complete or action == "COMPLETE_ASSESSMENT":
            responses = get_session_responses(session_id, questionnaire)
            total_score = sum(responses)
            severity = get_severity_level(questionnaire, total_score)
            save_score(session_id, questionnaire, total_score, severity)
            save_completed_questionnaire(user_id, questionnaire, responses)

            if questionnaire == "PHQ4":
                anxiety_score = sum(responses[:2]) if len(responses) >= 2 else 0
                depression_score = sum(responses[2:4]) if len(responses) >= 4 else 0
                gad7_needed = 1 if anxiety_score >= 2 else 0
                phq9_needed = 1 if depression_score >= 2 else 0

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE trackers SET gad7_needed = ?, phq9_needed = ? WHERE session_id = ?",
                    (gad7_needed, phq9_needed, session_id),
                )
                conn.commit()
                conn.close()

                if gad7_needed or phq9_needed:
                    update_session_state(session_id, "PHQ4_RESULTS")
                    follow_up = []
                    if gad7_needed:
                        follow_up.append("anxiety")
                    if phq9_needed:
                        follow_up.append("mood")
                    follow_up_text = " and ".join(follow_up)
                    next_message = (
                        f"✅ **PHQ-4 Complete** (Score: {total_score}/12 - {severity})\n\n"
                        "Thanks for completing the first screening. If you have any questions about these results, feel free to ask now. "
                        f"Otherwise, I recommend taking the PHQ-4 again periodically or continuing with follow-up questions about {follow_up_text}. "
                        "Would you like to continue?"
                    )
                else:
                    update_session_state(session_id, "COMPLETED")
                    end_session(session_id)
                    next_message = (
                        f"✅ **PHQ-4 Complete** (Score: {total_score}/12 - {severity})\n\n"
                        "Your screening does not indicate further follow-up questions right now. "
                        "If you want, you can review the results again later."
                    )

            elif questionnaire == "GAD7":
                if total_score <= 4:
                    note = "You’re doing well. Keep up the good work and lead a stress-free life."
                elif total_score <= 9:
                    note = (
                        f"Take care. This short support video may help you manage anxiety: {ANXIETY_SUPPORT_VIDEO}\n\n"
                        f"**Self-help guidelines for anxiety:**\n{ANXIETY_SELF_HELP}"
                    )
                else:
                    note = (
                        "Scores above 9 should indicate signs of anxiety and the person is asked to seek professional help. "
                        "I’m sorry you’re feeling this way. It may help to reach out to a mental health expert for support. "
                        "You deserve caring help."
                    )

                tracker = get_tracker(session_id)
                if tracker.get("phq9_needed"):
                    update_session_state(session_id, "PHQ9")
                    next_message = (
                        f"✅ **GAD-7 Complete** (Score: {total_score}/21 - {severity})\n\n"
                        f"{note}\n\n"
                        "I’ve recorded your anxiety responses. Now I have one more set of questions about how you're feeling emotionally.\n\n"
                        "**Question 1 of 9**\n\n"
                        f"{format_question_with_options('PHQ9', 0)}"
                    )
                    question_number = 0
                else:
                    update_session_state(session_id, "COMPLETED")
                    end_session(session_id)
                    next_message = f"✅ **GAD-7 Complete** (Score: {total_score}/21 - {severity})\n\n{note}"

            elif questionnaire == "PHQ9":
                q9_score = responses[8] if len(responses) > 8 else 0
                update_session_state(session_id, "COMPLETED")
                end_session(session_id)
                if q9_score > 0:
                    save_risk_flag(session_id, "suicide_ideation", f"Q9 score: {q9_score}")
                    next_message = (
                        f"✅ **PHQ-9 Complete** (Score: {total_score}/27 - {severity})\n\n"
                        "🚨 **IMPORTANT - Suicide Risk Detected**\n\n"
                        "If you're having suicidal thoughts:\n"
                        "• **National Suicide Prevention Lifeline (US):** 988\n"
                        "• **Crisis Text Line:** Text HOME to 741741\n"
                        "• **International Association for Suicide Prevention:** https://www.iasp.info/resources/Crisis_Centres/\n\n"
                        f"**For coping strategies, see this video:** {SUICIDE_SUPPORT_VIDEO}\n\n"
                        f"**Self-help guidelines for suicide:**\n{SUICIDE_SELF_HELP}\n\n"
                        "**Please reach out to a mental health professional or emergency services immediately.**"
                    )
                else:
                    if total_score <= 4:
                        note = "You’re doing well. Keep up the good work and lead a stress-free life."
                    elif total_score <= 9:
                        note = (
                            f"Take care. This short support video may help you cope: {DEPRESSION_SUPPORT_VIDEO}\n\n"
                            f"**Self-help guidelines for depression:**\n{DEPRESSION_SELF_HELP}"
                        )
                    else:
                        note = (
                            "Scores above 9 should indicate signs of major depressive disorder and the person is asked to seek professional help. "
                            "I’m sorry you’re going through this. It could really help to reach out to a mental health expert for support. "
                            "You’re not alone in this."
                        )
                    next_message = f"✅ **PHQ-9 Complete** (Score: {total_score}/27 - {severity})\n\n{note}"

    if action == "ASK_QUESTION" and questionnaire:
        update_session_state(session_id, questionnaire)

    if action == "UPDATE_STATUS" and questionnaire and update_progress and not complete_questionnaire:
        update_session_state(session_id, questionnaire)
        next_q = question_number + 1
        next_message = (
            "Thank you. Let's continue.\n\n"
            f"**{questionnaire} Assessment**\n\n"
            f"**Question {next_q + 1}**\n\n"
            f"{format_question_with_options(questionnaire, next_q)}"
        )
        question_number = next_q

    if action == "ASK_QUESTION" and questionnaire and not next_message:
        next_message = (
            f"**{questionnaire} Assessment**\n\n"
            f"**Question {question_number + 1}**\n\n"
            f"{format_question_with_options(questionnaire, question_number)}"
        )

    if not next_message:
        next_message = "I didn't understand that. Can you please clarify your response?"

    session = get_user_session(user_id)
    total_time = time.time() - request_start
    logger.warning("[REQUEST_TIME] %.3fs | Action: %s | State: %s", total_time, action, session["current_state"])

    return {
        "session_id": int(session["session_id"]),
        "current_state": session["current_state"],
        "next_question": next_message,
        "question_number": question_number,
        "orchestrator_source": orchestrator_source,
        "request_time_sec": round(total_time, 3),
    }


# ----------------------------
# Streamlit UI
# ----------------------------
init_db()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "last_gemini_response" not in st.session_state:
    st.session_state.last_gemini_response = ""
if "last_orchestrator_source" not in st.session_state:
    st.session_state.last_orchestrator_source = "-"
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = "-"

st.title("Mental Health Assessment - Single File")
st.caption("Embedded UI + orchestration + storage in one deployable Streamlit file")

with st.sidebar:
    st.subheader("Session")
    uid = st.text_input("User ID", value=st.session_state.user_id, placeholder="user_001")
    if st.button("Start Session", use_container_width=True):
        if uid.strip():
            st.session_state.user_id = uid.strip()
            st.session_state.chat_history = []
            greeting = "I have a few friendly questions that can help me assess how you are feeling. Would you like to start now?"
            st.session_state.chat_history.append({"role": "assistant", "content": greeting})
            st.rerun()
        else:
            st.warning("Enter a user ID.")

    if st.button("Reset Chat", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.session_id = None
        st.rerun()

    if st.button("Check Gemini Response", use_container_width=True):
        check = check_gemini_response()
        if check.get("ok") == "true":
            st.success(check.get("message", "Gemini check passed."))
        else:
            st.error(check.get("message", "Gemini check failed."))

    st.markdown("---")
    st.write(f"Gemini enabled: {'Yes' if GEMINI_CONFIGURED else 'No (fallback mode)'}")
    st.write("Secret needed for Gemini: GEMINI_API_KEY")
    st.write(f"Last orchestrator source: {st.session_state.last_orchestrator_source}")
    st.write(f"Last request time (s): {st.session_state.last_request_time}")
    if st.session_state.last_gemini_response:
        st.caption("Last Gemini response snapshot")
        st.code(st.session_state.last_gemini_response[:800])

if not st.session_state.user_id:
    st.info("Enter a user ID and start a session from the sidebar.")
    st.stop()

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Type your answer (a/b/c/d) or any question...")
if prompt:
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    result = process_chat(st.session_state.user_id, prompt)
    st.session_state.session_id = result.get("session_id")
    st.session_state.last_orchestrator_source = result.get("orchestrator_source", "-")
    st.session_state.last_request_time = result.get("request_time_sec", "-")
    st.session_state.chat_history.append({"role": "assistant", "content": result.get("next_question", "No response")})
    st.rerun()
