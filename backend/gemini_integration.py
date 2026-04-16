import os
import json
import re
import logging
from dotenv import load_dotenv
import google.generativeai as genai
from typing import Dict, Optional

from backend.database import get_last_completed_questionnaire

load_dotenv()

GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GEMINI_API_KEYS")
    or os.getenv("GOOGLE_API_KEY")
    or os.getenv("GOOGLE_API_KEYS")
)

GEMINI_CONFIGURED = bool(GEMINI_API_KEY)

if GEMINI_CONFIGURED:
    genai.configure(api_key=GEMINI_API_KEY)

logger = logging.getLogger(__name__)


# Questionnaire definitions
QUESTIONNAIRES = {
    "PHQ4": {
        "questions": [
            "Over the last 2 weeks, how often have you been bothered by feeling nervous, anxious, or on edge?",
            "Over the last 2 weeks, how often have you been bothered by not being able to stop or control worrying?",
            "Over the last 2 weeks, how often have you been bothered by little interest or pleasure in doing things?",
            "Over the last 2 weeks, how often have you been bothered by feeling down, depressed, or hopeless?"
        ],
        "options": {
            "a": "Not at all",
            "b": "Several days",
            "c": "More than half the days",
            "d": "Nearly every day"
        }
    },
    "GAD7": {
        "questions": [
            "Feeling nervous, anxious or on edge",
            "Not being able to stop or control worrying",
            "Worrying too much about different things",
            "Trouble relaxing",
            "Being so restless that it is hard to sit still",
            "Becoming easily annoyed or irritable",
            "Feeling afraid as if something awful might happen"
        ],
        "options": {
            "a": "Not at all",
            "b": "Several days",
            "c": "More than half the days",
            "d": "Nearly every day"
        }
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
            "Thoughts that you would be better off dead, or of hurting yourself in some way"
        ],
        "options": {
            "a": "Not at all",
            "b": "Several days",
            "c": "More than half the days",
            "d": "Nearly every day"
        }
    }
}


def get_question(questionnaire: str, question_no: int) -> str:
    """Get specific question from questionnaire"""
    if questionnaire in QUESTIONNAIRES:
        questions = QUESTIONNAIRES[questionnaire]["questions"]
        if 0 <= question_no < len(questions):
            return questions[question_no]
    return ""


def get_options(questionnaire: str) -> Dict[str, str]:
    """Get options for a questionnaire"""
    if questionnaire in QUESTIONNAIRES:
        return QUESTIONNAIRES[questionnaire]["options"]
    return {}


def format_question_with_options(questionnaire: str, question_no: int) -> str:
    """Format question with options for display"""
    question = get_question(questionnaire, question_no)
    options = get_options(questionnaire)
    
    formatted = f"{question}\n\n"
    for opt_key, opt_val in options.items():
        formatted += f"{opt_key}) {opt_val}\n"
    
    return formatted


def parse_response_with_gemini(
    questionnaire: str,
    question_no: int,
    user_response: str
) -> Dict:
    """Use Gemini to parse user response with ReAct chain-of-thought prompting"""
    if not GEMINI_CONFIGURED:
        logger.warning("Gemini not configured, using fallback response parsing.")
        return fallback_parse_response(user_response)

    try:
        question = get_question(questionnaire, question_no)
        options = get_options(questionnaire)
        
        opt_text = "\n".join([f"{k}) {v}" for k, v in options.items()])
        
        # ReAct Chain-of-Thought Prompting for better reasoning
        prompt = f"""You are a mental health assessment chatbot. Analyze the user's response using structured reasoning.

CURRENT QUESTION:
"{question}"

AVAILABLE OPTIONS:
{opt_text}

USER RESPONSE:
"{user_response}"

---
THINK STEP BY STEP (ReAct Chain-of-Thought):

1. OBSERVATION: What exactly did the user write?
2. RELEVANCE: Is this response attempting to answer the question topic?
3. ANALYSIS: Classify the response:
   - OFF-TOPIC: Ignores question, asks something else, refuses to answer
   - DIRECT: Clear letter/number/option phrase match
   - SEMANTIC: Describes feelings or a situation matching an option but not explicit
   - AMBIGUOUS: Unclear, contradictory, or multiple meanings
4. ACTION: Determine confidence and required action
5. REASONING: Explain your decision

---
RESPONSE (ONLY VALID JSON):

IF user is ON-TOPIC and answering:
  {{
    "confidence": "high",
    "option": "a",
    "reason": "User explicitly said option A or equivalent"
  }}
  OR
  {{
    "confidence": "medium",
    "option": "b",
    "ask_confirm": true,
    "reason": "User described situation matching option B, need confirmation"
  }}
  OR
  {{
    "confidence": "low",
    "reason": "Answer unclear or ambiguous, user needs to choose explicitly"
  }}

IF user is OFF-TOPIC:
  {{
    "confidence": "low",
    "is_offtopic": true,
    "reason": "User is asking about something unrelated to the question"
  }}

Return ONLY the JSON object, no markdown backticks, no extra text."""

        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        
        # Parse response
        response_text = response.text.strip()
        
        # Try to extract JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON in response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {"confidence": "low", "action": "clarify", "reason": "Could not parse"}
        
        return result
    
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        # Fallback: try simple parsing
        return fallback_parse_response(user_response)


def fallback_parse_response(user_response: str) -> Dict:
    """Fallback response parsing without Gemini"""
    response_lower = user_response.lower().strip()
    
    # Direct option matching
    if response_lower in ['a', 'option a', 'a)', 'not at all', '0']:
        return {"confidence": "high", "option": "a", "reason": "Option A matched"}
    elif response_lower in ['b', 'option b', 'b)', 'several days', '1']:
        return {"confidence": "high", "option": "b", "reason": "Option B matched"}
    elif response_lower in ['c', 'option c', 'c)', 'more than half', '2']:
        return {"confidence": "high", "option": "c", "reason": "Option C matched"}
    elif response_lower in ['d', 'option d', 'd)', 'nearly every', '3']:
        return {"confidence": "high", "option": "d", "reason": "Option D matched"}
    else:
        return {"confidence": "low", "action": "clarify", "reason": "Response unclear"}


def get_severity_level(questionnaire: str, score: int) -> str:
    """Determine severity level based on score"""
    
    if questionnaire == "PHQ4":
        if score <= 2:
            return "Minimal"
        elif score <= 5:
            return "Mild"
        elif score <= 8:
            return "Moderate"
        else:
            return "Severe"
    
    elif questionnaire == "GAD7":
        if score <= 4:
            return "Minimal Anxiety"
        elif score <= 9:
            return "Mild Anxiety"
        elif score <= 14:
            return "Moderate Anxiety"
        else:
            return "Severe Anxiety"
    
    elif questionnaire == "PHQ9":
        if score <= 4:
            return "Minimal Depression"
        elif score <= 9:
            return "Mild Depression"
        elif score <= 14:
            return "Moderate Depression"
        elif score <= 19:
            return "Moderately Severe Depression"
        else:
            return "Severe Depression"
    
    return "Unknown"


def get_recommendations(questionnaire: str, score: int, severity: str) -> list:
    """Generate recommendations based on scores"""
    recommendations = []
    
    base_recommendations = [
        "Consider speaking with a mental health professional",
        "Practice stress management and relaxation techniques",
        "Maintain regular exercise and sleep schedule",
        "Consider joining a support group"
    ]
    
    if questionnaire == "GAD7" and score >= 10:
        recommendations.append("Anxiety appears significant. Consult a healthcare provider.")
    
    if questionnaire == "PHQ9" and score >= 10:
        recommendations.append("Depression symptoms are notable. Professional help recommended.")
    
    if score <= 4:
        recommendations = ["Continue healthy habits", "Regular self-care practices recommended"]
    
    return recommendations[:3]  # Return top 3


def _is_affirmative(text: str) -> bool:
    return bool(re.search(r"\b(yes|yep|sure|ok|okay|start|continue|go ahead|ready|let's do it|let's start)\b", text, re.I))


def _is_negative(text: str) -> bool:
    return bool(re.search(r"\b(no|not now|skip|later|quit|cancel|stop|end|done|finished|don't want)\b", text, re.I))


def _is_quit_request(text: str) -> bool:
    return bool(re.search(r"\b(quit|stop|end|cancel|done for now|finished)\b", text, re.I))


def _is_offtopic(text: str) -> bool:
    return bool(re.search(r"\b(weather|movies|sports|jokes|news|song|music|family|work|life|politics)\b", text, re.I))


def local_orchestrator_fallback(user_message: str, current_state: str, trackers: dict, recent_history: list, user_id: Optional[str] = None) -> dict:
    """Fallback orchestrator behavior when Gemini API is unavailable."""
    user_text = user_message.strip()
    lower_text = user_text.lower()

    if current_state == "PHQ4_PENDING":
        prompt = (
            "I have a few friendly questions that can help me assess how you're feeling. "
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
                "complete_questionnaire": False
            }

        if _is_negative(lower_text):
            return {
                "action": "CLARIFY",
                "questionnaire": "PHQ4",
                "question_number": 0,
                "interpreted_option": None,
                "confidence": "high",
                "next_message": (
                    "No problem. When you're ready, just say 'yes' and I can start the screening questions."
                ),
                "reasoning": "User declined to start the screening questions for now.",
                "update_progress": False,
                "complete_questionnaire": False
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
            "complete_questionnaire": False
        }

    if current_state == "PHQ4_RESULTS":
        if _is_affirmative(lower_text):
            if trackers.get("gad7_needed"):
                return {
                    "action": "ASK_QUESTION",
                    "questionnaire": "GAD7",
                    "question_number": 0,
                    "interpreted_option": None,
                    "confidence": "high",
                    "next_message": "",
                    "reasoning": "User agreed to continue with anxiety follow-up questions.",
                    "update_progress": False,
                    "complete_questionnaire": False
                }
            if trackers.get("phq9_needed"):
                return {
                    "action": "ASK_QUESTION",
                    "questionnaire": "PHQ9",
                    "question_number": 0,
                    "interpreted_option": None,
                    "confidence": "high",
                    "next_message": "",
                    "reasoning": "User agreed to continue with mood follow-up questions.",
                    "update_progress": False,
                    "complete_questionnaire": False
                }
            return {
                "action": "COMPLETE_ASSESSMENT",
                "questionnaire": None,
                "question_number": 0,
                "interpreted_option": None,
                "confidence": "high",
                "next_message": "I understand. We can finish here if you'd like.",
                "reasoning": "No follow-up is needed or user agreed after completion.",
                "update_progress": False,
                "complete_questionnaire": False
            }

        if _is_negative(lower_text):
            return {
                "action": "COMPLETE_ASSESSMENT",
                "questionnaire": None,
                "question_number": 0,
                "interpreted_option": None,
                "confidence": "high",
                "next_message": "Okay. You can restart the follow-up questions anytime if you'd like.",
                "reasoning": "User declined follow-up questions.",
                "update_progress": False,
                "complete_questionnaire": False
            }

        return {
            "action": "CLARIFY",
            "questionnaire": None,
            "question_number": 0,
            "interpreted_option": None,
            "confidence": "low",
            "next_message": "If you prefer, we can retake the primary screening questions first. Otherwise reply 'yes' to continue with the follow-up questions or 'no' to stop.",
            "reasoning": "Awaiting clear follow-up consent or decline.",
            "update_progress": False,
            "complete_questionnaire": False
        }

    if _is_quit_request(lower_text):
        return {
            "action": "COMPLETE_ASSESSMENT",
            "questionnaire": current_state if current_state in ["PHQ9", "GAD7", "PHQ4"] else None,
            "question_number": trackers.get(f"{current_state.lower()}_progress", 0) if current_state in ["PHQ9", "GAD7", "PHQ4"] else 0,
            "interpreted_option": None,
            "confidence": "low",
            "next_message": "I understand. We can stop here. If you'd like, you can restart the assessment anytime.",
            "reasoning": "User requested to stop the questionnaire.",
            "update_progress": False,
            "complete_questionnaire": False
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
                "complete_questionnaire": progress + 1 >= max_questions
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
                "complete_questionnaire": False
            }

        if _is_affirmative(lower_text) and current_state in ["PHQ9", "GAD7", "PHQ4"]:
            return {
                "action": "REDIRECT",
                "questionnaire": current_state,
                "question_number": progress,
                "interpreted_option": None,
                "confidence": "low",
                "next_message": "I hear you. Let's keep going with the current set of questions — please answer the current question.",
                "reasoning": "User provided an affirmative response during an active questionnaire.",
                "update_progress": False,
                "complete_questionnaire": False
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
            "complete_questionnaire": False
        }

    if current_state == "COMPLETED":
        if _is_affirmative(lower_text) or _is_negative(lower_text):
            return {
                "action": "COMPLETE_ASSESSMENT",
                "questionnaire": None,
                "question_number": 0,
                "interpreted_option": None,
                "confidence": "high",
                "next_message": "This session is already complete. If you'd like, you can start a new screening anytime.",
                "reasoning": "User responded after the session was complete.",
                "update_progress": False,
                "complete_questionnaire": False
            }
        return {
            "action": "CLARIFY",
            "questionnaire": None,
            "question_number": 0,
            "interpreted_option": None,
            "confidence": "low",
            "next_message": "This session is complete. If you want to start again, just say 'start'.",
            "reasoning": "Session complete and awaiting user instruction.",
            "update_progress": False,
            "complete_questionnaire": False
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
        "complete_questionnaire": False
    }


def orchestrate_flow(user_message: str, current_state: str, trackers: dict, recent_history: list, session_id: int, user_id: str) -> dict:
    """Centralized LLM orchestrator for chatbot flow using ReAct reasoning"""
    
    if not GEMINI_CONFIGURED:
        logger.warning("Gemini is not configured; using local fallback orchestrator.")
        return local_orchestrator_fallback(user_message, current_state, trackers, recent_history, user_id)

    tracker_summary = f"""
Current State: {current_state}
PHQ9 Progress: {trackers.get('phq9_progress', 0)}/9
GAD7 Progress: {trackers.get('gad7_progress', 0)}/7
PHQ4 Progress: {trackers.get('phq4_progress', 0)}/4
PHQ9 Needed: {trackers.get('phq9_needed', False)}
GAD7 Needed: {trackers.get('gad7_needed', False)}
"""

    history_summary = "\n".join([f"User: {h['user']}\nBot: {h['bot']}" for h in recent_history[-5:]])  # Last 5 exchanges

    prompt = f"""You are the central orchestrator for a mental health assessment chatbot. Your role is to manage the entire conversation flow intelligently.

PRIMARY GOAL: Always start with the PHQ-4 screening questions first. After PHQ-4, suggest anxiety follow-up if the first two items sum to 2 or more, and suggest depression follow-up if the last two items sum to 2 or more.

CURRENT CONTEXT:
{tracker_summary}

RECENT CONVERSATION HISTORY (last 5 exchanges):
{history_summary}

USER'S LATEST MESSAGE:
"{user_message}"

QUESTIONNAIRES OVERVIEW:
- PHQ-4: 4 internal screening questions to assess how the user is feeling first
- GAD7: 7 internal anxiety follow-up questions if the first two PHQ-4 items score 2 or higher
- PHQ9: 9 internal mood/depression follow-up questions if the last two PHQ-4 items score 2 or higher

RULES FOR THIS ORCHESTRATOR:
1. If the user has not yet consented to start, ask permission before beginning any questions.
2. Refer to the initial screening as a set of primary questions to assess how they are feeling.
3. Refer to the anxiety follow-up as questions to assess anxiety and the depression follow-up as questions to assess mood.
4. Once the user agrees and the initial screening starts, continue those questions until completion unless the user explicitly says quit.
5. If the user asks an unrelated question mid-questionnaire, acknowledge them briefly and redirect to the current question.
6. After the initial screening completes, ask permission before offering any follow-up questions.
7. If the user asks something else when follow-up consent is requested, suggest retaking the primary screening questions.
8. Keep responses friendly, supportive, and conversational, not rude or overly formal.
9. When a questionnaire finishes, acknowledge completion explicitly and use score thresholds to choose the closing tone:
   - GAD-7 score 0-4: Encourage good work and stress-free life.
   - GAD-7 score 5-9: Provide self-help guidelines and anxiety video link.
   - GAD-7 score >9: Recommend professional help.
   - PHQ-9 score 0-4: Encourage good work and stress-free life.
   - PHQ-9 score 5-9: Provide self-help guidelines and depression video link.
   - PHQ-9 score >9: Recommend professional help.
   - PHQ-9 suicide positive: Override with suicide resources and video link.
10. Use tracker progress and prior history to infer whether the screening is active, completed, or awaiting follow-up consent.

THINK STEP BY STEP (REAct Chain-of-Thought):
1. OBSERVATION: What kind of message is this? (question answer, consent, off-topic, quit request, retake request)
2. STATUS: What is current_state, how many questions have been answered, and what does recent_history show?
3. ANALYSIS: Does this message belong to the current questionnaire flow or is it a diversion?
4. DECISION: Choose the best action based on state, progress, and user intent.
5. RESPONSE: Compose a compassionate, on-track reply.

EXAMPLES:

Example 1 - New session permission:
User: "Hi"
History: none
Trackers: PHQ9 progress 0
Analysis: User has not started assessment yet.
Decision: ASK_CONSENT
Next: "I have a few friendly questions that can help me assess how you're feeling. Would you like to start now?"

Example 2 - Started PHQ-9 and answered first question:
User: "a"
History: PHQ-9 question 1 asked
Trackers: PHQ9 progress 0
Analysis: User response is a valid answer to the current question.
Decision: UPDATE_STATUS, ASK_QUESTION next.

Example 3 - Mid-questionnaire chitchat:
User: "Do you think this is normal?"
History: PHQ-9 questions 1-3 answered
Trackers: PHQ9 progress 3
Analysis: User is off-topic while questionnaire is active.
Decision: REDIRECT
Next: "I hear you. Right now I'm here to ask a few questions about how you're feeling, then we can discuss it more. Please answer the current question."

Example 4 - Explicit quit during questionnaire:
User: "I want to stop"
History: PHQ-9 questions in progress
Trackers: PHQ9 progress 2
Analysis: User wants to end the flow.
Decision: COMPLETE_ASSESSMENT
Next: "I understand. We can stop here and come back to this later if you'd like."

Example 5 - Retake request after previous completion:
User: "Can I take that again?"
History: prior completed PHQ-9 exists
Trackers: PHQ9 progress 0
Analysis: User is asking for a retake.
Decision: ASK_CONSENT
Next: "Sure — I can ask a few questions again to see how you're feeling now. Would you like to start?"

Example 6 - GAD-7 completed and PHQ-9 needed:
User: "d"
History: GAD-7 question 7 answered and the current session has PHQ-9 needed
Trackers: GAD7 progress 6, PHQ9 needed true
Analysis: User finished the anxiety follow-up and should receive a completion summary before moving to the next questionnaire.
Decision: ASK_QUESTION
questionnaire: PHQ9
question_number: 0
Next: "✅ GAD-7 Complete (Score: 13/21 - Moderate Anxiety)\n\nI’ve recorded your anxiety responses. Now I have one more set of questions about how you're feeling emotionally.\n\n**Question 1 of 9**\n\n..."

Example 7 - GAD-7 completed with low score:
User: "c"
History: GAD-7 question 7 answered
Trackers: GAD7 progress 6, PHQ9 needed false
Analysis: User finished anxiety screening with a low score.
Decision: COMPLETE_ASSESSMENT
questionnaire: null
question_number: 0
Next: "✅ GAD-7 Complete (Score: 3/21 - Minimal Anxiety)\n\nYou’re doing well. Keep up the good work and lead a stress-free life."

Example 8 - GAD-7 completed with moderate score:
User: "c"
History: GAD-7 question 7 answered
Trackers: GAD7 progress 6, PHQ9 needed false
Analysis: User finished anxiety screening with a moderate score.
Decision: COMPLETE_ASSESSMENT
questionnaire: null
question_number: 0
Next: "✅ GAD-7 Complete (Score: 7/21 - Mild Anxiety)\n\nTake care. This short support video may help you manage anxiety: https://rhlaiservice2.blob.core.windows.net/mcare/anxiety/Anxiety-coping.m3u8\n\n**Self-help guidelines for anxiety:** [full text]"

Example 9 - GAD-7 completed with high score:
User: "d"
History: GAD-7 question 7 answered
Trackers: GAD7 progress 6, PHQ9 needed false
Analysis: User finished anxiety screening with a high score.
Decision: COMPLETE_ASSESSMENT
questionnaire: null
question_number: 0
Next: "✅ GAD-7 Complete (Score: 15/21 - Severe Anxiety)\n\nScores above 9 should indicate signs of anxiety and the person is asked to seek professional help. I’m sorry you’re feeling this way. It may help to reach out to a mental health expert for support. You deserve caring help."

Example 10 - PHQ-9 completed with moderate score:
User: "c"
History: PHQ-9 question 9 answered
Trackers: PHQ9 progress 8
Analysis: User finished mood screening with a moderate score.
Decision: COMPLETE_ASSESSMENT
questionnaire: null
question_number: 0
Next: "✅ PHQ-9 Complete (Score: 7/27 - Mild Depression)\n\nTake care. This short support video may help you cope: https://rhlaiservice2.blob.core.windows.net/mcare/depression/depression.m3u8\n\n**Self-help guidelines for depression:** [full text]"

Example 11 - PHQ-9 completed with high score:
User: "d"
History: PHQ-9 question 9 answered
Trackers: PHQ9 progress 8
Analysis: User finished mood screening with a high score.
Decision: COMPLETE_ASSESSMENT
questionnaire: null
question_number: 0
Next: "✅ PHQ-9 Complete (Score: 12/27 - Moderate Depression)\n\nScores above 9 should indicate signs of major depressive disorder and the person is asked to seek professional help. I’m sorry you’re going through this. It could really help to reach out to a mental health expert for support. You’re not alone in this."

Example 12 - PHQ-9 completed with suicide risk:
User: "b"
History: PHQ-9 question 9 answered with suicide positive
Trackers: PHQ9 progress 8
Analysis: User finished mood screening with suicide ideation.
Decision: COMPLETE_ASSESSMENT
questionnaire: null
question_number: 0
Next: "✅ PHQ-9 Complete (Score: 15/27 - Moderate Depression)\n\n🚨 **IMPORTANT - Suicide Risk Detected**\n\nIf you're having suicidal thoughts: [resources]\n\n**For coping strategies, see this video:** https://rhlaiservice2.blob.core.windows.net/mcare/suicide/suicide.m3u8\n\n**Self-help guidelines for suicide:** [full text]\n\n**Please reach out to a mental health professional or emergency services immediately.**"

OUTPUT FORMAT (ONLY VALID JSON):
{{
  "action": "ASK_QUESTION|CLARIFY|CONFIRM|UPDATE_STATUS|COMPLETE_ASSESSMENT|REDIRECT|ASK_CONSENT",
  "questionnaire": "PHQ9|GAD7|PHQ4|null",
  "question_number": 0-8,
  "interpreted_option": "a|b|c|d|null",
  "confidence": "high|medium|low",
  "next_message": "Exact text to send to user",
  "reasoning": "Brief explanation of decision",
  "update_progress": true/false,
  "complete_questionnaire": true/false
}}

Return ONLY the JSON object."""

    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        logger.info(f"[ORCHESTRATOR LOG] Session {session_id}: {response_text}")
        
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {
                    "action": "CLARIFY",
                    "next_message": "I didn't understand that. Can you please clarify?",
                    "reasoning": "Failed to parse LLM response"
                }
        
        return result
    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
        return local_orchestrator_fallback(user_message, current_state, trackers, recent_history, user_id)


if __name__ == "__main__":
    # Test
    result = parse_response_with_gemini("PHQ4", 0, "a")
    print(result)
