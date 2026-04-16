from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.schemas import ChatRequest, ChatResponse, SessionInfo, ResultsSummary
from backend.database import init_db, get_or_create_user, get_user_session, get_db_connection
from backend.gemini_integration import (
    parse_response_with_gemini, 
    get_severity_level,
    get_recommendations,
    get_question,
    format_question_with_options,
    QUESTIONNAIRES
)
from backend.utils import (
    save_response,
    update_tracker_progress,
    get_tracker,
    get_session_scores,
    get_risk_flags,
    save_score,
    save_risk_flag,
    calculate_questionnaire_score,
    end_session,
    update_session_state,
    get_session_data,
    get_session_responses,
    option_to_score
)

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
    """Main chat endpoint - processes user message and returns next question"""
    
    user_id = request.user_id.strip()
    message = request.message.strip()
    
    if not user_id or not message:
        raise HTTPException(status_code=400, detail="user_id and message required")
    
    get_or_create_user(user_id)
    session = get_user_session(user_id)
    session_id = session['session_id']
    tracker = get_tracker(session_id)
    current_state = session['current_state']
    
    # ==================== INITIAL OFFER ====================
    if current_state == "PHQ4" and tracker['phq4_progress'] == 0 and message.lower() not in ["a", "b", "c", "d"]:
        if message.lower() in ["yes", "ok", "start", "y", "take test"]:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE trackers SET phq4_progress = -1 WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()
            
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question=f"**Question 1 of 4 - PHQ-4 Screening**\n\n{format_question_with_options('PHQ4', 0)}",
                question_number=1,
                total_questions=4,
                progress_message="Starting PHQ-4 Screening"
            )
        elif message.lower() in ["no", "n", "skip"]:
            end_session(session_id)
            return ChatResponse(
                session_id=session_id,
                current_state="COMPLETED",
                next_question="Thank you for visiting. You can restart anytime.",
                question_number=0,
                total_questions=0,
                progress_message="Session ended"
            )
        else:
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question="Would you like to take a mental health assessment? Please respond with **Yes** or **No**",
                question_number=0,
                total_questions=4,
                progress_message="Awaiting assessment decision",
                clarification_needed=True,
                clarification_prompt="Please answer 'Yes' or 'No'"
            )
    
    # ==================== HANDLE PHQ4 ====================
    if current_state == "PHQ4" and tracker['phq4_progress'] >= -1 and tracker['phq4_progress'] < 4:
        parse_result = parse_response_with_gemini(
            "PHQ4", 
            tracker['phq4_progress'] if tracker['phq4_progress'] >= 0 else 0,
            message
        )
        
        # OFF-TOPIC: User not answering the question
        if parse_result.get('is_offtopic'):
            question_idx = tracker['phq4_progress'] if tracker['phq4_progress'] >= 0 else 0
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question=f"I appreciate your comment, but let's focus on the assessment. Please answer:\n\n**Question {question_idx + 1} of 4 - PHQ-4**\n\n{format_question_with_options('PHQ4', question_idx)}",
                question_number=question_idx + 1,
                total_questions=4,
                progress_message=f"Question {question_idx + 1} of 4 - Please answer the question",
                clarification_needed=True,
                clarification_prompt="Please choose: a, b, c, or d"
            )
        
        # LOW CONFIDENCE: Unclear response
        if parse_result.get('confidence') == 'low':
            question_idx = tracker['phq4_progress'] if tracker['phq4_progress'] >= 0 else 0
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question=f"I didn't quite understand. Could you choose one of the options?\n\n**Question {question_idx + 1} of 4 - PHQ-4**\n\n{format_question_with_options('PHQ4', question_idx)}",
                question_number=question_idx + 1,
                total_questions=4,
                progress_message=f"Question {question_idx + 1} of 4 - Clarification needed",
                clarification_needed=True,
                clarification_prompt="Please choose an option: a, b, c, or d"
            )
        
        # MEDIUM CONFIDENCE: Ask for confirmation
        if parse_result.get('confidence') == 'medium' and parse_result.get('ask_confirm'):
            question_idx = tracker['phq4_progress'] if tracker['phq4_progress'] >= 0 else 0
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question=f"Just to confirm: Did you mean **option {parse_result['option'].upper()}** - *{QUESTIONNAIRES['PHQ4']['options'][parse_result['option']]}*?",
                question_number=question_idx + 1,
                total_questions=4,
                progress_message=f"Question {question_idx + 1} of 4 - Confirm",
                clarification_needed=True
            )
        
        # HIGH CONFIDENCE: Save response
        option = parse_result.get('option', 'a').lower()
        score = option_to_score(option)
        
        if score < 0:
            raise HTTPException(status_code=400, detail="Invalid option")
        
        question_idx = tracker['phq4_progress'] if tracker['phq4_progress'] >= 0 else 0
        
        save_response(
            session_id,
            "PHQ4",
            question_idx,
            score,
            message,
            parse_result.get('confidence', 'unknown')
        )
        
        # UPDATE PROGRESS: Set to 1 after first answer (not 0!)
        if tracker['phq4_progress'] == -1:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE trackers SET phq4_progress = 1 WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()
        else:
            update_tracker_progress(session_id, "PHQ4")
        
        tracker = get_tracker(session_id)
        
        # CHECK IF COMPLETE
        if tracker['phq4_progress'] == 4:
            phq4_score = calculate_questionnaire_score(session_id, "PHQ4")
            phq4_severity = get_severity_level("PHQ4", phq4_score)
            save_score(session_id, "PHQ4", phq4_score, phq4_severity)
            
            responses = get_session_responses(session_id, "PHQ4")
            anxiety_score = responses[0] + responses[1]
            depression_score = responses[2] + responses[3]
            
            gad7_needed = anxiety_score >= 3
            phq9_needed = depression_score >= 3
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE trackers SET gad7_needed = ?, phq9_needed = ? WHERE session_id = ?",
                (int(gad7_needed), int(phq9_needed), session_id)
            )
            conn.commit()
            conn.close()
            
            if gad7_needed:
                update_session_state(session_id, "GAD7")
                return ChatResponse(
                    session_id=session_id,
                    current_state="GAD7",
                    next_question=f"✅ **PHQ-4 Complete** (Score: {phq4_score}/12 - {phq4_severity})\n\n---\n\n**Starting GAD-7 Assessment (7 questions)**\n\n**Question 1 of 7 - GAD-7**\n\n{format_question_with_options('GAD7', 0)}",
                    question_number=1,
                    total_questions=7,
                    progress_message="Starting GAD-7 Assessment"
                )
            elif phq9_needed:
                update_session_state(session_id, "PHQ9")
                return ChatResponse(
                    session_id=session_id,
                    current_state="PHQ9",
                    next_question=f"✅ **PHQ-4 Complete** (Score: {phq4_score}/12 - {phq4_severity})\n\n---\n\n**Starting PHQ-9 Assessment (9 questions)**\n\n**Question 1 of 9 - PHQ-9**\n\n{format_question_with_options('PHQ9', 0)}",
                    question_number=1,
                    total_questions=9,
                    progress_message="Starting PHQ-9 Assessment"
                )
            else:
                update_session_state(session_id, "COMPLETED")
                end_session(session_id)
                recommendations = get_recommendations("PHQ4", phq4_score, phq4_severity)
                return ChatResponse(
                    session_id=session_id,
                    current_state="COMPLETED",
                    next_question=f"✅ **Assessment Complete!**\n\n**PHQ-4 Score: {phq4_score}/12 ({phq4_severity})**\n\nYour screening shows minimal symptoms. Keep up healthy habits!\n\n💡 **Recommendations:**\n" + "\n".join([f"• {r}" for r in recommendations]),
                    question_number=0,
                    total_questions=0,
                    progress_message="Assessment Complete"
                )
        else:
            question_idx = tracker['phq4_progress']
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question=f"**Question {question_idx + 1} of 4 - PHQ-4**\n\n{format_question_with_options('PHQ4', question_idx)}",
                question_number=question_idx + 1,
                total_questions=4,
                progress_message=f"Question {question_idx + 1} of 4"
            )
    
    # ==================== HANDLE GAD7 ====================
    if current_state == "GAD7" and tracker['gad7_progress'] < 7:
        parse_result = parse_response_with_gemini("GAD7", tracker['gad7_progress'], message)
        
        if parse_result.get('is_offtopic') or parse_result.get('confidence') == 'low':
            return ChatResponse(
                session_id=session_id,
                current_state="GAD7",
                next_question=f"Please focus on the question. Choose one option:\n\n**Question {tracker['gad7_progress'] + 1} of 7 - GAD-7**\n\n{format_question_with_options('GAD7', tracker['gad7_progress'])}",
                question_number=tracker['gad7_progress'] + 1,
                total_questions=7,
                progress_message=f"Question {tracker['gad7_progress'] + 1} of 7",
                clarification_needed=True,
                clarification_prompt="Please choose: a, b, c, or d"
            )
        
        option = parse_result.get('option', 'a').lower()
        score = option_to_score(option)
        save_response(session_id, "GAD7", tracker['gad7_progress'], score, message, parse_result.get('confidence'))
        update_tracker_progress(session_id, "GAD7")
        tracker = get_tracker(session_id)
        
        if tracker['gad7_progress'] == 7:
            gad7_score = calculate_questionnaire_score(session_id, "GAD7")
            gad7_severity = get_severity_level("GAD7", gad7_score)
            save_score(session_id, "GAD7", gad7_score, gad7_severity)
            
            if tracker['phq9_needed']:
                update_session_state(session_id, "PHQ9")
                return ChatResponse(
                    session_id=session_id,
                    current_state="PHQ9",
                    next_question=f"✅ **GAD-7 Complete** (Score: {gad7_score}/21 - {gad7_severity})\n\n---\n\n**Starting PHQ-9 Assessment (9 questions)**\n\n**Question 1 of 9 - PHQ-9**\n\n{format_question_with_options('PHQ9', 0)}",
                    question_number=1,
                    total_questions=9,
                    progress_message="Starting PHQ-9 Assessment"
                )
            else:
                update_session_state(session_id, "COMPLETED")
                end_session(session_id)
                recommendations = get_recommendations("GAD7", gad7_score, gad7_severity)
                return ChatResponse(
                    session_id=session_id,
                    current_state="COMPLETED",
                    next_question=f"✅ **Assessment Complete!**\n\n**GAD-7 Score: {gad7_score}/21 ({gad7_severity})**\n\n💡 **Recommendations:**\n" + "\n".join([f"• {r}" for r in recommendations]),
                    question_number=0,
                    total_questions=0,
                    progress_message="Assessment Complete"
                )
        else:
            return ChatResponse(
                session_id=session_id,
                current_state="GAD7",
                next_question=f"**Question {tracker['gad7_progress'] + 1} of 7 - GAD-7**\n\n{format_question_with_options('GAD7', tracker['gad7_progress'])}",
                question_number=tracker['gad7_progress'] + 1,
                total_questions=7,
                progress_message=f"Question {tracker['gad7_progress'] + 1} of 7"
            )
    
    # ==================== HANDLE PHQ9 ====================
    if current_state == "PHQ9" and tracker['phq9_progress'] < 9:
        parse_result = parse_response_with_gemini("PHQ9", tracker['phq9_progress'], message)
        
        if parse_result.get('is_offtopic') or parse_result.get('confidence') == 'low':
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ9",
                next_question=f"Please focus on the question. Choose one option:\n\n**Question {tracker['phq9_progress'] + 1} of 9 - PHQ-9**\n\n{format_question_with_options('PHQ9', tracker['phq9_progress'])}",
                question_number=tracker['phq9_progress'] + 1,
                total_questions=9,
                progress_message=f"Question {tracker['phq9_progress'] + 1} of 9",
                clarification_needed=True,
                clarification_prompt="Please choose: a, b, c, or d"
            )
        
        option = parse_result.get('option', 'a').lower()
        score = option_to_score(option)
        save_response(session_id, "PHQ9", tracker['phq9_progress'], score, message, parse_result.get('confidence'))
        update_tracker_progress(session_id, "PHQ9")
        tracker = get_tracker(session_id)
        
        if tracker['phq9_progress'] == 9:
            phq9_score = calculate_questionnaire_score(session_id, "PHQ9")
            phq9_severity = get_severity_level("PHQ9", phq9_score)
            save_score(session_id, "PHQ9", phq9_score, phq9_severity)
            
            responses = get_session_responses(session_id, "PHQ9")
            q9_score = responses[8]
            
            if q9_score > 0:
                save_risk_flag(session_id, "suicide_ideation", f"Q9 score: {q9_score}")
                update_session_state(session_id, "COMPLETED")
                end_session(session_id)
                
                resources = "🚨 **IMPORTANT - Suicide Risk Detected**\n\nIf you're having suicidal thoughts:\n"
                resources += "• **National Suicide Prevention Lifeline (US):** 988\n"
                resources += "• **Crisis Text Line:** Text HOME to 741741\n"
                resources += "• **International Association for Suicide Prevention:** https://www.iasp.info/resources/Crisis_Centres/\n\n"
                resources += "**Please reach out to a mental health professional or emergency services immediately.**"
                
                return ChatResponse(
                    session_id=session_id,
                    current_state="COMPLETED",
                    next_question=f"✅ **Assessment Complete**\n\n**PHQ-9 Score: {phq9_score}/27 ({phq9_severity})\n\n{resources}",
                    question_number=0,
                    total_questions=0,
                    progress_message="Assessment Complete - Suicide Risk Detected"
                )
            else:
                update_session_state(session_id, "COMPLETED")
                end_session(session_id)
                recommendations = get_recommendations("PHQ9", phq9_score, phq9_severity)
                return ChatResponse(
                    session_id=session_id,
                    current_state="COMPLETED",
                    next_question=f"✅ **Assessment Complete!**\n\n**PHQ-9 Score: {phq9_score}/27 ({phq9_severity})**\n\n💡 **Recommendations:**\n" + "\n".join([f"• {r}" for r in recommendations]),
                    question_number=0,
                    total_questions=0,
                    progress_message="Assessment Complete"
                )
        else:
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ9",
                next_question=f"**Question {tracker['phq9_progress'] + 1} of 9 - PHQ-9**\n\n{format_question_with_options('PHQ9', tracker['phq9_progress'])}",
                question_number=tracker['phq9_progress'] + 1,
                total_questions=9,
                progress_message=f"Question {tracker['phq9_progress'] + 1} of 9"
            )
    
    raise HTTPException(status_code=400, detail="Invalid state")


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
