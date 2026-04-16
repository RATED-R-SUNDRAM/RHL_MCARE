import re
from typing import Dict, List, Optional

import streamlit as st

st.set_page_config(
    page_title="Mental Health Assessment",
    page_icon="MH",
    layout="wide",
)

# ----------------------------
# Constants and questionnaires
# ----------------------------
ANXIETY_SUPPORT_VIDEO = "https://rhlaiservice2.blob.core.windows.net/mcare/anxiety/Anxiety-coping.m3u8"
DEPRESSION_SUPPORT_VIDEO = "https://rhlaiservice2.blob.core.windows.net/mcare/depression/depression.m3u8"
SUICIDE_SUPPORT_VIDEO = "https://rhlaiservice2.blob.core.windows.net/mcare/suicide/suicide.m3u8"

ANXIETY_SELF_HELP = (
    "Anxiety may seem random, but there is usually an underlying cause related to stress, health, "
    "or life situation. You can identify personal triggers by journaling and self-reflection.\n\n"
    "Techniques to help reduce anxiety:\n"
    "1. Grounding: Name 3 things you see, 3 things you hear, and 3 things you can touch.\n"
    "2. Breathing: Inhale deeply, hold for 2-5 seconds, then exhale slowly.\n"
    "3. Meditation: Re-center your body and mind.\n"
    "4. Gentle movement or massage can ease physical tension.\n\n"
    "If these techniques are not enough, seek professional support from a healthcare provider."
)

DEPRESSION_SELF_HELP = (
    "Depression can be managed with practical daily strategies:\n"
    "1. Challenge negative thoughts and replace them with balanced ones.\n"
    "2. Do small, meaningful activities (walk, light exercise, simple tasks).\n"
    "3. Keep a healthy routine (sleep and meals at regular times).\n"
    "4. Break problems into smaller steps.\n"
    "5. Write 2-3 things you are thankful for each day.\n"
    "6. Stay connected to trusted people or support groups.\n"
    "7. Limit alcohol and caffeine.\n\n"
    "If symptoms feel hard to manage, seek professional help from a doctor, psychologist, or counselor."
)

SUICIDE_SELF_HELP = (
    "When suicidal thoughts come, they can feel overwhelming and permanent, but support is available.\n"
    "1. Use grounding (5-4-3-2-1 senses method) to reconnect to the present moment.\n"
    "2. Hold something comforting (a soft object, pet, or blanket).\n"
    "3. Use a safety plan: warning signs, coping steps, safe spaces, and trusted contacts.\n"
    "4. Reach out immediately to a trusted person by call or text.\n"
    "5. Use calming practices (music, prayer, meditation, meaningful reading).\n"
    "6. Challenge hopeless thoughts with realistic self-support statements.\n"
    "7. Keep a written list of reasons to stay safe and keep going.\n"
    "8. Get professional support immediately."
)

QUESTIONNAIRES: Dict[str, Dict[str, List[str]]] = {
    "PHQ4": {
        "questions": [
            "Over the last 2 weeks, how often have you been bothered by feeling nervous, anxious, or on edge?",
            "Over the last 2 weeks, how often have you been bothered by not being able to stop or control worrying?",
            "Over the last 2 weeks, how often have you been bothered by little interest or pleasure in doing things?",
            "Over the last 2 weeks, how often have you been bothered by feeling down, depressed, or hopeless?",
        ],
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
        ],
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
        ],
    },
}

OPTION_TO_SCORE = {"a": 0, "b": 1, "c": 2, "d": 3}


# ----------------------------
# Helper logic
# ----------------------------
def format_question(questionnaire: str, question_idx: int) -> str:
    q = QUESTIONNAIRES[questionnaire]["questions"][question_idx]
    return (
        f"**{questionnaire} Assessment**\\n\\n"
        f"**Question {question_idx + 1} of {len(QUESTIONNAIRES[questionnaire]['questions'])}**\\n\\n"
        f"{q}\\n\\n"
        "a) Not at all  \\n"
        "b) Several days  \\n"
        "c) More than half the days  \\n"
        "d) Nearly every day"
    )


def get_severity(questionnaire: str, score: int) -> str:
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


def extract_option(user_text: str) -> Optional[str]:
    text = user_text.strip().lower()
    direct = re.fullmatch(r"\s*([abcd])\s*\)?\s*", text)
    if direct:
        return direct.group(1)

    if "not at all" in text:
        return "a"
    if "several days" in text:
        return "b"
    if "more than half" in text:
        return "c"
    if "nearly every" in text:
        return "d"
    return None


def is_affirmative(text: str) -> bool:
    return bool(re.search(r"\b(yes|y|ok|okay|sure|continue|go ahead|start|ready)\b", text.lower()))


def is_negative(text: str) -> bool:
    return bool(re.search(r"\b(no|n|not now|later|skip|stop)\b", text.lower()))


def is_restart_request(text: str) -> bool:
    return bool(re.search(r"\b(restart|retake|again|new test|start phq4)\b", text.lower()))


def start_questionnaire(questionnaire: str) -> str:
    st.session_state.current_state = questionnaire
    st.session_state.current_question_idx = 0
    return format_question(questionnaire, 0)


def reset_assessment_state() -> None:
    st.session_state.current_state = "PHQ4_PENDING"
    st.session_state.current_question_idx = 0
    st.session_state.responses = {"PHQ4": [], "GAD7": [], "PHQ9": []}
    st.session_state.need_gad7 = False
    st.session_state.need_phq9 = False


def phq4_completion_message(total_score: int, severity: str, need_gad7: bool, need_phq9: bool) -> str:
    follow_up = []
    if need_gad7:
        follow_up.append("anxiety")
    if need_phq9:
        follow_up.append("mood")

    follow_up_text = " and ".join(follow_up)
    return (
        f"## PHQ-4 Complete\\n"
        f"Score: {total_score}/12 ({severity})\\n\\n"
        "Thanks for completing the first screening. If you have any questions about these results, feel free to ask now. "
        f"Otherwise, I recommend taking PHQ-4 again periodically or continuing with follow-up questions about {follow_up_text}. "
        "Would you like to continue?"
    )


def gad7_supportive_note(score: int) -> str:
    if score <= 4:
        return "You are doing well. Keep up the good work and lead a stress-free life."
    if score <= 9:
        return (
            f"Take care. This short support video may help you manage anxiety: {ANXIETY_SUPPORT_VIDEO}\\n\\n"
            f"**Self-help guidelines for anxiety:**\\n{ANXIETY_SELF_HELP}"
        )
    return (
        "Scores above 9 indicate signs of anxiety and suggest professional support. "
        "I am sorry you are feeling this way. It may help to reach out to a mental health expert."
    )


def phq9_supportive_note(score: int) -> str:
    if score <= 4:
        return "You are doing well. Keep up the good work and lead a stress-free life."
    if score <= 9:
        return (
            f"Take care. This short support video may help you cope: {DEPRESSION_SUPPORT_VIDEO}\\n\\n"
            f"**Self-help guidelines for depression:**\\n{DEPRESSION_SELF_HELP}"
        )
    return (
        "Scores above 9 indicate signs of major depressive disorder and suggest professional help. "
        "I am sorry you are going through this. You are not alone, and support is available."
    )


def suicide_message(total_score: int, severity: str) -> str:
    return (
        f"## PHQ-9 Complete\\n"
        f"Score: {total_score}/27 ({severity})\\n\\n"
        "## IMPORTANT - Suicide Risk Detected\\n\\n"
        "If you are having suicidal thoughts:\\n"
        "- National Suicide Prevention Lifeline (US): 988\\n"
        "- Crisis Text Line: Text HOME to 741741\\n"
        "- International resources: https://www.iasp.info/resources/Crisis_Centres/\\n\\n"
        f"For coping strategies, see this video: {SUICIDE_SUPPORT_VIDEO}\\n\\n"
        f"**Self-help guidelines for suicide:**\\n{SUICIDE_SELF_HELP}\\n\\n"
        "Please reach out to a mental health professional or emergency services immediately."
    )


def handle_user_message(user_text: str) -> str:
    state = st.session_state.current_state

    if state == "PHQ4_PENDING":
        if is_affirmative(user_text) or is_restart_request(user_text):
            return start_questionnaire("PHQ4")
        return (
            "I have a few friendly questions that can help me assess how you are feeling. "
            "Would you like to start now?"
        )

    if state in {"PHQ4", "GAD7", "PHQ9"}:
        opt = extract_option(user_text)
        if not opt:
            return "Please answer with a, b, c, or d so I can score this question correctly."

        questionnaire = state
        st.session_state.responses[questionnaire].append(OPTION_TO_SCORE[opt])
        st.session_state.current_question_idx += 1

        total_questions = len(QUESTIONNAIRES[questionnaire]["questions"])
        if st.session_state.current_question_idx < total_questions:
            return format_question(questionnaire, st.session_state.current_question_idx)

        total_score = sum(st.session_state.responses[questionnaire])
        severity = get_severity(questionnaire, total_score)

        if questionnaire == "PHQ4":
            responses = st.session_state.responses["PHQ4"]
            anxiety_sub = responses[0] + responses[1]
            mood_sub = responses[2] + responses[3]
            st.session_state.need_gad7 = anxiety_sub >= 2
            st.session_state.need_phq9 = mood_sub >= 2

            if st.session_state.need_gad7 or st.session_state.need_phq9:
                st.session_state.current_state = "PHQ4_RESULTS"
                return phq4_completion_message(
                    total_score,
                    severity,
                    st.session_state.need_gad7,
                    st.session_state.need_phq9,
                )

            st.session_state.current_state = "COMPLETED"
            return (
                f"## PHQ-4 Complete\\n"
                f"Score: {total_score}/12 ({severity})\\n\\n"
                "Your screening does not indicate follow-up questions right now. "
                "If you want, ask any question now, and when ready you can retake PHQ-4."
            )

        if questionnaire == "GAD7":
            note = gad7_supportive_note(total_score)
            if st.session_state.need_phq9:
                msg = (
                    f"## GAD-7 Complete\\n"
                    f"Score: {total_score}/21 ({severity})\\n\\n"
                    f"{note}\\n\\n"
                    "I have recorded your anxiety responses. Next, I will ask PHQ-9 for mood screening.\\n\\n"
                )
                return msg + start_questionnaire("PHQ9")

            st.session_state.current_state = "COMPLETED"
            return (
                f"## GAD-7 Complete\\n"
                f"Score: {total_score}/21 ({severity})\\n\\n"
                f"{note}\\n\\n"
                "If you would like to ask anything about your result, type your question. "
                "When ready, you can retake PHQ-4."
            )

        q9_score = st.session_state.responses["PHQ9"][8]
        st.session_state.current_state = "COMPLETED"
        if q9_score > 0:
            return suicide_message(total_score, severity)

        note = phq9_supportive_note(total_score)
        return (
            f"## PHQ-9 Complete\\n"
            f"Score: {total_score}/27 ({severity})\\n\\n"
            f"{note}\\n\\n"
            "If you have questions about your result, ask now. "
            "When ready, you can retake PHQ-4."
        )

    if state == "PHQ4_RESULTS":
        if is_affirmative(user_text):
            if st.session_state.need_gad7:
                return start_questionnaire("GAD7")
            return start_questionnaire("PHQ9")

        if is_negative(user_text):
            st.session_state.current_state = "COMPLETED"
            return (
                "No problem. We can stop here for now. "
                "If you want, ask any question about your result, or retake PHQ-4 later."
            )

        return (
            "Good question. I can help explain your screening summary. "
            "When you are ready, reply 'yes' to continue follow-up questions or 'no' to stop for now."
        )

    text_lower = user_text.lower()
    if "start phq4" in text_lower:
        reset_assessment_state()
        return start_questionnaire("PHQ4")

    if is_restart_request(user_text) or is_affirmative(user_text):
        return (
            "If you want, we can run PHQ-4 again. "
            "Reply with 'start PHQ4' to restart now. "
            "You can also ask any question first."
        )

    return (
        "Thanks for sharing. If you want to retake the screening, reply 'start PHQ4'. "
        "If not, feel free to ask any follow-up question."
    )


# ----------------------------
# Streamlit UI
# ----------------------------
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "current_state" not in st.session_state:
    st.session_state.current_state = "PHQ4_PENDING"
if "current_question_idx" not in st.session_state:
    st.session_state.current_question_idx = 0
if "responses" not in st.session_state:
    st.session_state.responses = {"PHQ4": [], "GAD7": [], "PHQ9": []}
if "need_gad7" not in st.session_state:
    st.session_state.need_gad7 = False
if "need_phq9" not in st.session_state:
    st.session_state.need_phq9 = False

st.title("Mental Health Assessment - Single File Streamlit App")
st.caption("PHQ-4 -> GAD-7 / PHQ-9 flow with built-in logic for direct Streamlit deployment")

with st.sidebar:
    st.subheader("Session")
    new_user_id = st.text_input("User ID", value=st.session_state.user_id, placeholder="e.g., user_001")

    if st.button("Start / Update User", use_container_width=True):
        st.session_state.user_id = new_user_id.strip()
        if not st.session_state.user_id:
            st.warning("Please enter a user ID.")
        else:
            if not st.session_state.chat_history:
                st.session_state.chat_history.append(
                    {
                        "role": "assistant",
                        "content": (
                            "I have a few friendly questions that can help me assess how you are feeling. "
                            "Would you like to start now?"
                        ),
                    }
                )
            st.rerun()

    if st.button("Reset Session", use_container_width=True):
        st.session_state.chat_history = []
        reset_assessment_state()
        st.rerun()

    st.markdown("---")
    st.write(f"Current state: {st.session_state.current_state}")

if not st.session_state.user_id:
    st.info("Enter a User ID in the sidebar and click 'Start / Update User'.")
    st.stop()

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Type your message or answer (a, b, c, d)...")
if prompt:
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    bot_reply = handle_user_message(prompt)
    st.session_state.chat_history.append({"role": "assistant", "content": bot_reply})
    st.rerun()
