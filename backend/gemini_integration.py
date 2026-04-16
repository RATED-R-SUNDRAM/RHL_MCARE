import os
import json
import re
from dotenv import load_dotenv
import google.generativeai as genai
from typing import Dict, Optional

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEYS")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


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
2. RELEVANCE: Is this response attempting to answer about the question topic?
3. ANALYSIS: Classify the response:
   - OFF-TOPIC: Ignores question, asks something else, refuses to answer
   - DIRECT: Clear letter/number/option phrase match
   - SEMANTIC: Describes feeling/situation matching an option but not explicit
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
        print(f"Gemini API error: {e}")
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


if __name__ == "__main__":
    # Test
    result = parse_response_with_gemini("PHQ4", 0, "a")
    print(result)
