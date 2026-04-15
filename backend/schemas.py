from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ChatRequest(BaseModel):
    user_id: str
    message: str


class GeminiParseResult(BaseModel):
    confidence: str  # high, medium, low
    option: Optional[str] = None  # a, b, c, d
    reason: str
    ask_confirm: Optional[bool] = False
    action: Optional[str] = None  # clarify, redirect


class ResponseSave(BaseModel):
    session_id: int
    questionnaire: str
    question_no: int
    score: int
    raw_response: str
    gemini_confidence: str


class ScoreSave(BaseModel):
    session_id: int
    questionnaire: str
    total_score: int
    severity_level: str


class RiskFlag(BaseModel):
    session_id: int
    risk_type: str
    flag_details: str


class ChatResponse(BaseModel):
    session_id: int
    current_state: str
    next_question: str
    question_number: int
    total_questions: int
    progress_message: str
    clarification_needed: Optional[bool] = False
    clarification_prompt: Optional[str] = None


class SessionInfo(BaseModel):
    session_id: int
    user_id: str
    current_state: str
    phq4_progress: int
    gad7_progress: int
    phq9_progress: int
    can_resume: bool


class ResultsSummary(BaseModel):
    session_id: int
    phq4_score: Optional[int] = None
    phq4_severity: Optional[str] = None
    gad7_score: Optional[int] = None
    gad7_severity: Optional[str] = None
    phq9_score: Optional[int] = None
    phq9_severity: Optional[str] = None
    risk_flags: List[str] = []
    recommendations: List[str] = []
