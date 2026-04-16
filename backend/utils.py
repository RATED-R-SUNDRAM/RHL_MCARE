from backend.database import get_db_connection
from datetime import datetime


def save_response(session_id: int, questionnaire: str, question_no: int, 
                 score: int, raw_response: str, confidence: str) -> int:
    """Save response to database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO responses 
        (session_id, questionnaire, question_no, score, raw_response, gemini_confidence, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, questionnaire, question_no, score, raw_response, confidence, datetime.now()))
    
    conn.commit()
    response_id = cursor.lastrowid
    conn.close()
    
    return response_id


def update_tracker_progress(session_id: int, questionnaire: str):
    """Increment progress for a questionnaire"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    field_name = f"{questionnaire.lower()}_progress"
    
    cursor.execute(f"""
        UPDATE trackers
        SET {field_name} = {field_name} + 1
        WHERE session_id = ?
    """, (session_id,))
    
    conn.commit()
    conn.close()


def get_tracker(session_id: int):
    """Get tracker status for session"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM trackers WHERE session_id = ?", (session_id,))
    tracker = cursor.fetchone()
    conn.close()
    
    return dict(tracker) if tracker else None


def get_session_scores(session_id: int):
    """Get all scores for a session"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM scores WHERE session_id = ?", (session_id,))
    scores = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in scores]


def get_risk_flags(session_id: int):
    """Get risk flags for a session"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM risk_flags WHERE session_id = ?", (session_id,))
    flags = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in flags]


def save_score(session_id: int, questionnaire: str, total_score: int, severity_level: str):
    """Save calculated score to database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO scores 
        (session_id, questionnaire, total_score, severity_level, calculated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, questionnaire, total_score, severity_level, datetime.now()))
    
    conn.commit()
    conn.close()


def save_risk_flag(session_id: int, risk_type: str, flag_details: str):
    """Save risk flag to database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO risk_flags 
        (session_id, risk_type, flag_details, flagged_at)
        VALUES (?, ?, ?, ?)
    """, (session_id, risk_type, flag_details, datetime.now()))
    
    conn.commit()
    conn.close()


def get_session_responses(session_id: int, questionnaire: str):
    """Get all responses for a questionnaire in session"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT score FROM responses 
        WHERE session_id = ? AND questionnaire = ?
        ORDER BY question_no ASC
    """, (session_id, questionnaire))
    
    responses = cursor.fetchall()
    conn.close()
    
    return [row[0] for row in responses]


def get_recent_history(session_id: int, limit: int = 5):
    """Return recent raw responses for a session to preserve conversational momentum"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT questionnaire, question_no, raw_response, gemini_confidence, timestamp
        FROM responses
        WHERE session_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (session_id, limit))
    rows = cursor.fetchall()
    conn.close()

    history = []
    for row in reversed(rows):
        history.append({
            "user": row["raw_response"],
            "bot": f"Answered {row['questionnaire']} Q{row['question_no'] + 1} (confidence={row['gemini_confidence']})",
            "questionnaire": row["questionnaire"],
            "question_no": row["question_no"],
            "confidence": row["gemini_confidence"],
            "timestamp": row["timestamp"]
        })
    return history


def calculate_questionnaire_score(session_id: int, questionnaire: str) -> int:
    """Calculate total score for a questionnaire"""
    scores = get_session_responses(session_id, questionnaire)
    return sum(scores)


def option_to_score(option: str) -> int:
    """Convert option letter to score (0-3)"""
    mapping = {'a': 0, 'b': 1, 'c': 2, 'd': 3}
    return mapping.get(option.lower(), -1)


def end_session(session_id: int):
    """Mark session as ended"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE sessions
        SET ended_at = ?
        WHERE session_id = ?
    """, (datetime.now(), session_id))
    
    conn.commit()
    conn.close()


def reset_session_trackers(session_id: int):
    """Reset all trackers for new assessment"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE trackers
        SET phq4_needed = 0, phq4_progress = 0,
            gad7_needed = 0, gad7_progress = 0,
            phq9_needed = 0, phq9_progress = 0
        WHERE session_id = ?
    """, (session_id,))
    
    conn.commit()
    conn.close()


def update_session_state(session_id: int, new_state: str):
    """Update current session state"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE sessions
        SET current_state = ?
        WHERE session_id = ?
    """, (new_state, session_id))
    
    conn.commit()
    conn.close()


def get_session_data(session_id: int):
    """Get complete session data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    session = cursor.fetchone()
    
    if not session:
        conn.close()
        return None
    
    session_dict = dict(session)
    
    # Get tracker
    cursor.execute("SELECT * FROM trackers WHERE session_id = ?", (session_id,))
    tracker = cursor.fetchone()
    session_dict['tracker'] = dict(tracker) if tracker else None
    
    conn.close()
    return session_dict
