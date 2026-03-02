from typing import TypedDict

class AgentState(TypedDict):
    user_id: str
    normalized_message: str
    intent: str
    confidence: float
    clarification_needed: bool
    CID: str
    registered_mobile_no: str
    OTP_verification_status: str
    tool_invoked: str
    next_agent: str