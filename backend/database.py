import sqlite3
import os
from datetime import datetime

DB_PATH = "mental_health.db"


def get_db_connection():
    """Create database connection with row factory for dict-like access"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database with all required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_session TIMESTAMP
        )
    """)

    # Session tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            current_state TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # Questionnaire responses
    cursor.execute("""
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
    """)

    # Scores summary
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            score_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            questionnaire TEXT,
            total_score INTEGER,
            severity_level TEXT,
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
    """)

    # Risk flags
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_flags (
            flag_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            risk_type TEXT,
            flag_details TEXT,
            flagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
    """)

    # Trackers per session
    cursor.execute("""
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
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


def get_or_create_user(user_id: str):
    """Get or create user in database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, last_session) VALUES (?, ?)",
            (user_id, datetime.now())
        )
        conn.commit()
    
    conn.close()
    return user is not None


def get_user_session(user_id: str):
    """Get or create session for user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get last session
    cursor.execute(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY started_at DESC LIMIT 1",
        (user_id,)
    )
    session = cursor.fetchone()
    
    if session and not session['ended_at']:
        # Resume existing session
        conn.close()
        return dict(session)
    
    # Create new session
    cursor.execute(
        "INSERT INTO sessions (user_id, current_state) VALUES (?, ?)",
        (user_id, "PHQ4")
    )
    session_id = cursor.lastrowid
    
    # Create tracker for new session
    cursor.execute(
        """INSERT INTO trackers 
           (session_id, phq4_needed, phq4_progress, gad7_needed, gad7_progress, phq9_needed, phq9_progress)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, 1, 0, 0, 0, 0, 0)
    )
    
    conn.commit()
    
    cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    new_session = cursor.fetchone()
    conn.close()
    
    return dict(new_session)


if __name__ == "__main__":
    init_db()
