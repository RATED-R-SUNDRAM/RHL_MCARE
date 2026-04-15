from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.schemas import ChatRequest, ChatResponse, SessionInfo, ResultsSummary
from backend.database import init_db, get_or_create_user, get_user_session, get_db_connection
from backend.gemini_integration import (
    parse_response_with_gemini, 
    option_to_score,
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
    get_session_responses
)

app = FastAPI(title="Mental Health Assessment API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
init_db()


# ==================== ENDPOINTS ====================

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint - processes user message and returns next question"""
    
    user_id = request.user_id.strip()
    message = request.message.strip()
    
    if not user_id or not message:
        raise HTTPException(status_code=400, detail="user_id and message required")
    
    # Get or create user
    get_or_create_user(user_id)
    
    # Get or create session
    session = get_user_session(user_id)
    session_id = session['session_id']
    
    # Get tracker
    tracker = get_tracker(session_id)
    current_state = session['current_state']
    
    # ==================== INITIAL OFFER ====================
    if current_state == "PHQ4" and tracker['phq4_progress'] == 0:
        if message.lower() in ["yes", "ok", "start", "y", "take test"]:
            # Start PHQ4
            question_num = 0
            question_text = get_question("PHQ4", question_num)
            
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question=format_question_with_options("PHQ4", question_num),
                question_number=1,
                total_questions=4,
                progress_message="Question 1 of 4 for PHQ-4 (Screening)"
            )
        elif message.lower() in ["no", "n", "skip"]:
            end_session(session_id)
            return ChatResponse(
                session_id=session_id,
                current_state="COMPLETED",
                next_question="Thank you for visiting. Goodbye!",
                question_number=0,
                total_questions=0,
                progress_message="Session ended"
            )
        else:
            # Unclear response - ask for clarification
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question="Would you like to take this assessment? (Yes/No)",
                question_number=0,
                total_questions=4,
                progress_message="Clarification needed",
                clarification_needed=True,
                clarification_prompt="Please respond with 'Yes' or 'No'"
            )
    
    # ==================== HANDLE PHQ4 ====================
    if current_state == "PHQ4" and tracker['phq4_progress'] < 4:
        # Parse response with Gemini
        parse_result = parse_response_with_gemini(
            "PHQ4", 
            tracker['phq4_progress'], 
            message
        )
        
        # Handle low confidence
        if parse_result.get('confidence') == 'low':
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question=format_question_with_options("PHQ4", tracker['phq4_progress']),
                question_number=tracker['phq4_progress'] + 1,
                total_questions=4,
                progress_message=f"Question {tracker['phq4_progress'] + 1} of 4 for PHQ-4",
                clarification_needed=True,
                clarification_prompt="Please choose an option (a, b, c, or d)"
            )
        
        # Handle medium confidence
        if parse_result.get('confidence') == 'medium' and parse_result.get('ask_confirm'):
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question=f"Did you mean option {parse_result['option'].upper()}? ({QUESTIONNAIRES['PHQ4']['options'][parse_result['option']]})",
                question_number=tracker['phq4_progress'] + 1,
                total_questions=4,
                progress_message=f"Question {tracker['phq4_progress'] + 1} of 4 for PHQ-4 (Confirm)",
                clarification_needed=True
            )
        
        # High confidence - save response
        option = parse_result.get('option', 'a').lower()
        score = option_to_score(option)
        
        if score < 0:
            raise HTTPException(status_code=400, detail="Invalid option")
        
        # Save to database
        save_response(
            session_id,
            "PHQ4",
            tracker['phq4_progress'],
            score,
            message,
            parse_result.get('confidence', 'unknown')
        )
        
        # Update progress
        update_tracker_progress(session_id, "PHQ4")
        tracker = get_tracker(session_id)
        
        # Check if PHQ4 is complete
        if tracker['phq4_progress'] == 4:
            # Calculate PHQ4 score and determine next questionnaire
            phq4_score = calculate_questionnaire_score(session_id, "PHQ4")
            phq4_severity = get_severity_level("PHQ4", phq4_score)
            save_score(session_id, "PHQ4", phq4_score, phq4_severity)
            
            # Get anxiety and depression sub-scores
            responses = get_session_responses(session_id, "PHQ4")
            anxiety_score = responses[0] + responses[1]  # Q1 + Q2
            depression_score = responses[2] + responses[3]  # Q3 + Q4
            
            # Determine if GAD7 or PHQ9 needed
            gad7_needed = anxiety_score >= 3
            phq9_needed = depression_score >= 3
            
            # Update tracker
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trackers
                SET gad7_needed = ?, phq9_needed = ?
                WHERE session_id = ?
            """, (int(gad7_needed), int(phq9_needed), session_id))
            conn.commit()
            conn.close()
            
            # Determine next state
            if gad7_needed:
                update_session_state(session_id, "GAD7")
                question_num = 0
                return ChatResponse(
                    session_id=session_id,
                    current_state="GAD7",
                    next_question=format_question_with_options("GAD7", question_num),
                    question_number=1,
                    total_questions=7,
                    progress_message="Screening complete. Starting GAD-7 (Anxiety Assessment) - Question 1 of 7"
                )
            elif phq9_needed:
                update_session_state(session_id, "PHQ9")
                question_num = 0
                return ChatResponse(
                    session_id=session_id,
                    current_state="PHQ9",
                    next_question=format_question_with_options("PHQ9", question_num),
                    question_number=1,
                    total_questions=9,
                    progress_message="Screening complete. Starting PHQ-9 (Depression Assessment) - Question 1 of 9"
                )
            else:
                update_session_state(session_id, "COMPLETED")
                end_session(session_id)
                recommendations = get_recommendations("PHQ4", phq4_score, phq4_severity)
                return ChatResponse(
                    session_id=session_id,
                    current_state="COMPLETED",
                    next_question=f"Assessment complete! Your screening score indicates minimal symptoms. Keep up healthy habits!\n\nRecommendations: {', '.join(recommendations)}",
                    question_number=0,
                    total_questions=0,
                    progress_message="Assessment Complete"
                )
        else:
            # Continue with next question
            question_num = tracker['phq4_progress']
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ4",
                next_question=format_question_with_options("PHQ4", question_num),
                question_number=question_num + 1,
                total_questions=4,
                progress_message=f"Question {question_num + 1} of 4 for PHQ-4"
            )
    
    # ==================== HANDLE GAD7 ====================
    if current_state == "GAD7" and tracker['gad7_progress'] < 7:
        parse_result = parse_response_with_gemini("GAD7", tracker['gad7_progress'], message)
        
        if parse_result.get('confidence') == 'low':
            return ChatResponse(
                session_id=session_id,
                current_state="GAD7",
                next_question=format_question_with_options("GAD7", tracker['gad7_progress']),
                question_number=tracker['gad7_progress'] + 1,
                total_questions=7,
                progress_message=f"Question {tracker['gad7_progress'] + 1} of 7 for GAD-7",
                clarification_needed=True,
                clarification_prompt="Please choose an option (a, b, c, or d)"
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
            
            # Check if PHQ9 also needed
            if tracker['phq9_needed']:
                update_session_state(session_id, "PHQ9")
                return ChatResponse(
                    session_id=session_id,
                    current_state="PHQ9",
                    next_question=format_question_with_options("PHQ9", 0),
                    question_number=1,
                    total_questions=9,
                    progress_message=f"GAD-7 Complete (Score: {gad7_score} - {gad7_severity}). Starting PHQ-9 - Question 1 of 9"
                )
            else:
                update_session_state(session_id, "COMPLETED")
                end_session(session_id)
                recommendations = get_recommendations("GAD7", gad7_score, gad7_severity)
                return ChatResponse(
                    session_id=session_id,
                    current_state="COMPLETED",
                    next_question=f"Assessment Complete!\nGAD-7 Score: {gad7_score} ({gad7_severity})\n\nRecommendations: {', '.join(recommendations)}",
                    question_number=0,
                    total_questions=0,
                    progress_message="Assessment Complete"
                )
        else:
            return ChatResponse(
                session_id=session_id,
                current_state="GAD7",
                next_question=format_question_with_options("GAD7", tracker['gad7_progress']),
                question_number=tracker['gad7_progress'] + 1,
                total_questions=7,
                progress_message=f"Question {tracker['gad7_progress'] + 1} of 7 for GAD-7"
            )
    
    # ==================== HANDLE PHQ9 ====================
    if current_state == "PHQ9" and tracker['phq9_progress'] < 9:
        parse_result = parse_response_with_gemini("PHQ9", tracker['phq9_progress'], message)
        
        if parse_result.get('confidence') == 'low':
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ9",
                next_question=format_question_with_options("PHQ9", tracker['phq9_progress']),
                question_number=tracker['phq9_progress'] + 1,
                total_questions=9,
                progress_message=f"Question {tracker['phq9_progress'] + 1} of 9 for PHQ-9",
                clarification_needed=True,
                clarification_prompt="Please choose an option (a, b, c, or d)"
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
            
            # Check Q9 (suicide) - get response score
            responses = get_session_responses(session_id, "PHQ9")
            q9_score = responses[8]  # Last question
            
            if q9_score > 0:
                # Suicide risk - flag and provide resources
                save_risk_flag(session_id, "suicide_ideation", f"Q9 score: {q9_score}")
                update_session_state(session_id, "COMPLETED")
                end_session(session_id)
                
                resources = "IMPORTANT: If you're having suicidal thoughts:\n"
                resources += "- National Suicide Prevention Lifeline: 988 (US)\n"
                resources += "- Crisis Text Line: Text HOME to 741741\n"
                resources += "- International Association for Suicide Prevention: https://www.iasp.info/resources/Crisis_Centres/\n"
                resources += "\nPlease reach out to a mental health professional or emergency services immediately."
                
                return ChatResponse(
                    session_id=session_id,
                    current_state="COMPLETED",
                    next_question=f"Assessment Complete!\nPHQ-9 Score: {phq9_score} ({phq9_severity})\n\n{resources}",
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
                    next_question=f"Assessment Complete!\nPHQ-9 Score: {phq9_score} ({phq9_severity})\n\nRecommendations: {', '.join(recommendations)}",
                    question_number=0,
                    total_questions=0,
                    progress_message="Assessment Complete"
                )
        else:
            return ChatResponse(
                session_id=session_id,
                current_state="PHQ9",
                next_question=format_question_with_options("PHQ9", tracker['phq9_progress']),
                question_number=tracker['phq9_progress'] + 1,
                total_questions=9,
                progress_message=f"Question {tracker['phq9_progress'] + 1} of 9 for PHQ-9"
            )
    
    # Error handling
    raise HTTPException(status_code=400, detail="Invalid state")


@app.get("/results/{session_id}", response_model=ResultsSummary)
async def get_results(session_id: int):
    """Get assessment results for a session"""
    
    scores_list = get_session_scores(session_id)
    flags = get_risk_flags(session_id)
    
    results = {
        "session_id": session_id,
        "risk_flags": [f"{flag['risk_type']}" for flag in flags]
    }
    
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
    
    # Create new session
    new_session = get_user_session(user_id)
    
    return {"message": "Session reset", "session_id": new_session['session_id']}


@app.get("/")
async def root():
    """Health check"""
    return {"status": "Mental Health Assessment API is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
