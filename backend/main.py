from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.schemas import ChatRequest, ChatResponse, SessionInfo, ResultsSummary
from backend.database import (
    init_db,
    get_or_create_user,
    get_user_session,
    get_db_connection,
    save_completed_questionnaire
)
from backend.gemini_integration import (
    get_severity_level,
    get_recommendations,
    format_question_with_options,
    orchestrate_flow
)
from backend.utils import (
    save_response,
    update_tracker_progress,
    get_tracker,
    get_recent_history,
    get_session_scores,
    get_risk_flags,
    save_score,
    save_risk_flag,
    calculate_questionnaire_score,
    end_session,
    update_session_state,
    get_session_responses,
    option_to_score
)
import time
import logging

# Support video links for moderate scores
ANXIETY_SUPPORT_VIDEO = "https://rhlaiservice2.blob.core.windows.net/mcare/anxiety/Anxiety-coping.m3u8"
DEPRESSION_SUPPORT_VIDEO = "https://rhlaiservice2.blob.core.windows.net/mcare/depression/depression.m3u8"
SUICIDE_SUPPORT_VIDEO = "https://rhlaiservice2.blob.core.windows.net/mcare/suicide/suicide.m3u8"

# Self-help guidelines
ANXIETY_SELF_HELP = """
Anxiety may sometimes seem random; but there is usually an underlying cause related to genetics, brain function, or co-occurring health conditions. Professional help can assist in uncovering these deeper factors. Symptoms of anxiety can be triggered or worsened by specific factors such as caffeine, certain medications, financial concerns, and stress.

You can identify personal triggers by journaling, therapy, and self-reflection.

Techniques to Help Overcome Anxiety
Effective coping strategies to manage anxiety include:
1. Grounding: A technique to feel calm by engaging in your current environment.
   • Name 3 things you see.
   • Identify 3 sounds you hear.
   • Move or touch 3 things (e.g., your limbs or objects).
2. Breathing Exercises: Take a deep breath, hold for 2-5 seconds, and then breathe out.
3. Meditation: Practice re-centering your body and mind.
4. Massage: Helps ease physical tension.

If these techniques are not effective, or for underlying causes, seek professional help from a health care professional.
"""

DEPRESSION_SELF_HELP = """
Depression is a common condition which is like a passing mood or a day of feeling down. It can be managed using the following strategies:
1. Challenge negative thoughts by replacing them with balanced ones. Identify negative thoughts like "I’m worthless" and replace them with balanced ones like "I’m struggling, but that doesn’t mean I’m worthless."
2. Engage in small, meaningful activities like taking a walk, regular exercise, etc.
3. Maintaining a healthy routine (consistent sleep/meals). Go to bed and wake up at the same time daily; avoid screens before bed.
4. Break problems into smaller, manageable parts instead of feeling overwhelmed.
5. Write down 2–3 things you’re thankful for each day.
6. Isolation makes depression worse; connecting with friends, family or support groups helps to lighten your thoughts.
7. Limit the use of alcohol and caffeine.

If you feel that you cannot cope with the symptoms, seek professional help: A doctor, psychologist, or counselor can provide support and treatment options.
"""

SUICIDE_SELF_HELP = """
When suicidal thoughts come, they often feel overwhelming and permanent. However, there are coping strategies that can help you to connect with the present.
1. Ground Yourself in the Present: Use the 5-4-3-2-1 technique (seeing, touching, hearing, smelling, tasting) to reconnect to the here and now when thoughts feel overwhelming.
2. Hold something comforting like a soft object or a pet.
3. A written safety plan can guide you when you’re in crisis. It usually includes:
   Warning signs: What thoughts, feelings, or behaviors tell me I’m in danger?
   Coping strategies: What can I do right now to feel safer (walk, breathe, music, call a friend)?
   Safe spaces or distractions: Where can I go or what can I do that feels calming (a park, my room, faith community)?
   People I can contact include friend/family, Counselor, Helpline.
   Remove or avoid anything that you could use to harm yourself.
4. Reach out immediately to a trusted person (call, text, or write) as isolation fuels suicidal thinking. Send a simple message like, "I'm not okay right now. Can we talk?"
5. Listen to calming music or pray, meditate, or read a meaningful passage.
6. Try challenging hopeless thoughts like "I can’t handle this" to "I’ve handled hard things before, even when I didn’t think I could."
7. When you’re in crisis, it’s easy to forget why life matters. Write a list of things, big or small, that have meaning to you like people who care about you, dreams or goals you haven’t yet tried, pets, nature, music, kindness, faith, learning - anything that sparks life. Keep this list somewhere you can reach for it when you feel low.
8. Get Professional Support
"""

# Setup logging for latency tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mental Health Assessment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint - processes user message through centralized orchestrator"""
    request_start = time.time()

    user_id = request.user_id.strip()
    message = request.message.strip()

    if not user_id or not message:
        raise HTTPException(status_code=400, detail="user_id and message required")

    get_or_create_user(user_id)
    session = get_user_session(user_id)
    session_id = session['session_id']
    trackers = get_tracker(session_id)
    current_state = session['current_state']
    recent_history = get_recent_history(session_id, limit=5)

    orch_result = orchestrate_flow(message, current_state, trackers, recent_history, session_id, user_id)
    logger.log(logging.INFO, f"Orchestrator result: {orch_result}")
    action = orch_result.get('action', 'CLARIFY')
    questionnaire = orch_result.get('questionnaire')
    question_number = orch_result.get('question_number', 0)
    interpreted_option = orch_result.get('interpreted_option')
    confidence = orch_result.get('confidence', 'low')
    next_message = orch_result.get('next_message', '')
    update_progress = orch_result.get('update_progress', False)
    complete_questionnaire = orch_result.get('complete_questionnaire', False)

    if action in ["UPDATE_STATUS", "COMPLETE_ASSESSMENT"] and questionnaire and interpreted_option:
        score = option_to_score(interpreted_option)
        if score < 0:
            raise HTTPException(status_code=400, detail="Invalid option")

        save_response(session_id, questionnaire, question_number, score, message, confidence)
        if update_progress:
            update_tracker_progress(session_id, questionnaire)

        tracker = get_tracker(session_id)
        max_questions_by_questionnaire = {"PHQ4": 4, "GAD7": 7, "PHQ9": 9}
        is_complete = False
        if questionnaire in max_questions_by_questionnaire:
            current_progress = tracker.get(f"{questionnaire.lower()}_progress", 0)
            if current_progress >= max_questions_by_questionnaire[questionnaire] or question_number + 1 >= max_questions_by_questionnaire[questionnaire]:
                is_complete = True

        session_closed = False
        if is_complete or action == "COMPLETE_ASSESSMENT":
            total_score = calculate_questionnaire_score(session_id, questionnaire)
            severity = get_severity_level(questionnaire, total_score)
            save_score(session_id, questionnaire, total_score, severity)
            save_completed_questionnaire(user_id, questionnaire, get_session_responses(session_id, questionnaire))

            if questionnaire == "PHQ4":
                responses = get_session_responses(session_id, "PHQ4")
                anxiety_score = sum(responses[:2]) if len(responses) >= 2 else 0
                depression_score = sum(responses[2:4]) if len(responses) >= 4 else 0
                gad7_needed = 1 if anxiety_score >= 2 else 0
                phq9_needed = 1 if depression_score >= 2 else 0

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE trackers SET gad7_needed = ?, phq9_needed = ? WHERE session_id = ?",
                    (gad7_needed, phq9_needed, session_id)
                )
                conn.commit()
                conn.close()

                if gad7_needed or phq9_needed:
                    update_session_state(session_id, "PHQ4_RESULTS")
                    if not next_message or next_message == "Thank you. Let's continue.":
                        follow_up = []
                        if gad7_needed:
                            follow_up.append("anxiety")
                        if phq9_needed:
                            follow_up.append("mood")
                        follow_up_text = " and ".join(follow_up)
                        next_message = (
                            f"✅ **PHQ-4 Complete** (Score: {total_score}/12 - {severity})\n\n"
                            f"Thanks for completing the first screening. If you have any questions about these results, feel free to ask now. "
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
                    session_closed = True

            elif questionnaire == "GAD7":
                tracker = get_tracker(session_id)
                if total_score <= 4:
                    supportive_note = "You’re doing well. Keep up the good work and lead a stress-free life."
                elif total_score <= 9:
                    supportive_note = (
                        f"Take care. This short support video may help you manage anxiety: {ANXIETY_SUPPORT_VIDEO}\n\n"
                        f"**Self-help guidelines for anxiety:**\n{ANXIETY_SELF_HELP}"
                    )
                else:
                    supportive_note = (
                        "Scores above 9 should indicate signs of anxiety and the person is asked to seek professional help. "
                        "I’m sorry you’re feeling this way. It may help to reach out to a mental health expert for support. "
                        "You deserve caring help."
                    )

                if tracker.get('phq9_needed'):
                    update_session_state(session_id, "PHQ9")
                    next_message = (
                        f"✅ **GAD-7 Complete** (Score: {total_score}/21 - {severity})\n\n"
                        f"{supportive_note}\n\n"
                        "I’ve recorded your anxiety responses. Now I have one more set of questions about how you're feeling emotionally.\n\n"
                        "**Question 1 of 9**\n\n"
                        f"{format_question_with_options('PHQ9', 0)}"
                    )
                    question_number = 0
                else:
                    update_session_state(session_id, "COMPLETED")
                    end_session(session_id)
                    next_message = (
                        f"✅ **GAD-7 Complete** (Score: {total_score}/21 - {severity})\n\n"
                        f"{supportive_note}"
                    )
                    session_closed = True

            elif questionnaire == "PHQ9":
                responses = get_session_responses(session_id, "PHQ9")
                q9_score = responses[8] if len(responses) > 8 else 0
                if q9_score > 0:
                    save_risk_flag(session_id, "suicide_ideation", f"Q9 score: {q9_score}")
                    update_session_state(session_id, "COMPLETED")
                    end_session(session_id)

                    resources = "🚨 **IMPORTANT - Suicide Risk Detected**\n\nIf you're having suicidal thoughts:\n"
                    resources += "• **National Suicide Prevention Lifeline (US):** 988\n"
                    resources += "• **Crisis Text Line:** Text HOME to 741741\n"
                    resources += "• **International Association for Suicide Prevention:** https://www.iasp.info/resources/Crisis_Centres/\n\n"
                    resources += f"**For coping strategies, see this video:** {SUICIDE_SUPPORT_VIDEO}\n\n"
                    resources += f"**Self-help guidelines for suicide:**\n{SUICIDE_SELF_HELP}\n\n"
                    resources += "**Please reach out to a mental health professional or emergency services immediately.**"

                    next_message = (
                        f"✅ **PHQ-9 Complete** (Score: {total_score}/27 - {severity})\n\n"
                        f"{resources}"
                    )
                    session_closed = True
                else:
                    if total_score >= 10:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE trackers SET gad7_needed = ?, phq4_needed = ? WHERE session_id = ?",
                            (1, 1, session_id)
                        )
                        conn.commit()
                        conn.close()

                    if total_score <= 4:
                        supportive_note = "You’re doing well. Keep up the good work and lead a stress-free life."
                    elif total_score <= 9:
                        supportive_note = (
                            f"Take care. This short support video may help you cope: {DEPRESSION_SUPPORT_VIDEO}\n\n"
                            f"**Self-help guidelines for depression:**\n{DEPRESSION_SELF_HELP}"
                        )
                    else:
                        supportive_note = (
                            "Scores above 9 should indicate signs of major depressive disorder and the person is asked to seek professional help. "
                            "I’m sorry you’re going through this. It could really help to reach out to a mental health expert for support. "
                            "You’re not alone in this."
                        )

                    update_session_state(session_id, "COMPLETED")
                    end_session(session_id)
                    next_message = (
                        f"✅ **PHQ-9 Complete** (Score: {total_score}/27 - {severity})\n\n"
                        f"{supportive_note}"
                    )
                    session_closed = True

            if session_closed:
                pass

    if action == "ASK_QUESTION" and questionnaire:
        update_session_state(session_id, questionnaire)

    if action == "UPDATE_STATUS" and questionnaire and update_progress and not complete_questionnaire:
        update_session_state(session_id, questionnaire)
        next_question_number = question_number + 1
        next_message = f"""Thank you. Let's continue.

**{questionnaire} Assessment**

**Question {next_question_number + 1}**

{format_question_with_options(questionnaire, next_question_number)}"""
        question_number = next_question_number

    if action == "ASK_QUESTION" and questionnaire and not next_message:
        next_message = f"""**{questionnaire} Assessment**

**Question {question_number + 1}**

{format_question_with_options(questionnaire, question_number)}"""

    if not next_message:
        next_message = "I didn't understand that. Can you please clarify your response?"

    session = get_user_session(user_id)
    current_state = session['current_state']
    total_questions = 0
    if questionnaire == 'PHQ9':
        total_questions = 9
    elif questionnaire == 'GAD7':
        total_questions = 7
    elif questionnaire == 'PHQ4':
        total_questions = 4

    total_time = time.time() - request_start
    logger.warning(f"[REQUEST_TIME] {total_time:.3f}s | Action: {action} | State: {current_state}")

    return ChatResponse(
        session_id=session_id,
        current_state=current_state,
        next_question=next_message,
        question_number=question_number,
        total_questions=total_questions,
        progress_message=f"Action: {action}"
    )
@app.get("/results/{session_id}", response_model=ResultsSummary)
async def get_results(session_id: int):
    """Get assessment results for a session"""
    scores_list = get_session_scores(session_id)
    flags = get_risk_flags(session_id)
    
    results = {"session_id": session_id, "risk_flags": [f"{flag['risk_type']}" for flag in flags]}
    recommendations = []
    
    for score in scores_list:
        if score['questionnaire'] == "PHQ4":
            results['phq4_score'] = score['total_score']
            results['phq4_severity'] = score['severity_level']
        elif score['questionnaire'] == "GAD7":
            results['gad7_score'] = score['total_score']
            results['gad7_severity'] = score['severity_level']
            recommendations.extend(get_recommendations("GAD7", score['total_score'], score['severity_level']))
        elif score['questionnaire'] == "PHQ9":
            results['phq9_score'] = score['total_score']
            results['phq9_severity'] = score['severity_level']
            recommendations.extend(get_recommendations("PHQ9", score['total_score'], score['severity_level']))
    
    results['recommendations'] = list(set(recommendations))[:5]
    return ResultsSummary(**results)


@app.get("/session/{user_id}", response_model=SessionInfo)
async def get_session_info(user_id: str):
    """Get current session info for user"""
    get_or_create_user(user_id)
    session = get_user_session(user_id)
    tracker = get_tracker(session['session_id'])
    
    return SessionInfo(
        session_id=session['session_id'],
        user_id=user_id,
        current_state=session['current_state'],
        phq4_progress=tracker['phq4_progress'],
        gad7_progress=tracker['gad7_progress'],
        phq9_progress=tracker['phq9_progress'],
        can_resume=not session['ended_at']
    )


@app.post("/reset_session/{user_id}")
async def reset_session(user_id: str):
    """Reset session for user to start fresh"""
    get_or_create_user(user_id)
    session = get_user_session(user_id)
    end_session(session['session_id'])
    new_session = get_user_session(user_id)
    return {"message": "Session reset", "session_id": new_session['session_id']}


@app.get("/")
async def root():
    """Health check"""
    return {"status": "Mental Health Assessment API is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
