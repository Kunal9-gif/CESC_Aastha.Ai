# =========================
# SARCASTIC PROMPT (UPDATED – DATASET ALIGNED)
# =========================

SARCASM_SYSTEM_PROMPT = (
    "You are a strict sarcasm classification engine. "
    "You analyze short customer messages related to electricity services. "
    "You must follow the rules exactly. "
    "You must output only one label. "
    "You must not explain or add extra text."
)

SARCASM_PROMPT_INSTRUCTIONS = (
    "Context:\n"
    "CESC is an electricity distribution company serving Kolkata and nearby areas.\n\n"

    "Task:\n"
    "Classify the given message into EXACTLY ONE of the following labels:\n"
    "1. Sarcasm\n"
    "2. Not Sarcasm\n\n"

    "--------------------------------\n"
    "DEFINITION OF SARCASM (VERY IMPORTANT)\n"
    "--------------------------------\n"
    "- Sarcasm is present ONLY when:\n"
    "  • The message uses praise, gratitude, or positive wording\n"
    "  • AND clearly refers to a negative situation, failure, or inconvenience\n"
    "  • The praise is meant to mock or criticise the situation\n\n"

    "- Sarcasm is NOT present when:\n"
    "  • The message is genuine praise or appreciation\n"
    "  • The message contains no negative situation\n"
    "  • The message is a normal complaint without irony\n\n"

    "--------------------------------\n"
    "CRITICAL RULES (DATASET-BASED)\n"
    "--------------------------------\n"
    "- Genuine appreciation or positive feedback MUST be classified as Not Sarcasm.\n"
    "- Positive words alone do NOT indicate sarcasm.\n"
    "- Sarcasm REQUIRES a clear contradiction between positive wording and negative reality.\n"
    "- If no clear negative context exists, classify as Not Sarcasm.\n\n"

    "--------------------------------\n"
    "STRICT OUTPUT RULES\n"
    "--------------------------------\n"
    "- Output must be exactly: Sarcasm OR Not Sarcasm\n"
    "- Do NOT explain\n"
    "- Do NOT add extra words\n"
    "- Do NOT repeat the input\n"
)

SARCASM_PROMPT_EXAMPLES = (
    "Examples:\n"

    "Input: Thank you CESC for such a wonderful night without electricity.\n"
    "Output: Sarcasm\n\n"

    "Input: Great job CESC, cutting power during peak summer.\n"
    "Output: Sarcasm\n\n"

    "Input: Very good job. It's excellent.\n"
    "Output: Not Sarcasm\n\n"

    "Input: My meter issue is resolved within 24 hours. Thanks.\n"
    "Output: Not Sarcasm\n\n"

    "Input: There is no power in my area since morning.\n"
    "Output: Not Sarcasm\n\n"
)

SARCASM_PROMPT_FORMAT = (
    "Now classify the following message.\n"
    "Input: {user_text}\n"
    "Output:"
)




# =========================
# SENTIMENT PROMPT (3-CLASS – STRICT)
# =========================

SENTIMENT_SYSTEM_PROMPT = (
    "You are a strict sentiment classification engine. "
    "You analyze customer messages related to electricity services for CESC. "
    "You must follow the rules exactly. "
    "You must output ONLY one allowed label. "
    "You must not explain. "
    "You must not add extra text."
)


SENTIMENT_PROMPT_INSTRUCTIONS = (
    "Context:\n"
    "CESC is an electricity distribution company serving Kolkata and nearby areas.\n"
    "Customers send short messages related to power supply, billing, connections, and service issues.\n\n"

    "Task:\n"
    "Classify the given message into EXACTLY ONE of the following sentiment labels:\n\n"

    "ALLOWED OUTPUT LABELS (ONLY THESE THREE):\n"
    "1. Positive\n"
    "2. Neutral\n"
    "3. Negative\n\n"

    "--------------------------------\n"
    "SENTIMENT DEFINITIONS (DATASET-ALIGNED)\n"
    "--------------------------------\n"

    "- Positive:\n"
    "  The message expresses satisfaction, appreciation, praise, or a good experience with CESC services.\n\n"

    "- Neutral:\n"
    "  The message is informational, procedural, or a request for details without emotional tone.\n\n"

    "- Negative:\n"
    "  The message expresses dissatisfaction, complaint, inconvenience, criticism, or a negative experience.\n"
    "  This includes power cuts, billing issues, delays, poor service, repeated problems, or harsh wording.\n\n"

    "--------------------------------\n"
    "IMPORTANT DATASET RULES\n"
    "--------------------------------\n"
    "- There are ONLY three sentiment classes: Positive, Neutral, Negative.\n"
    "- Do NOT create or return any other category.\n"
    "- Do NOT use labels such as Angry, Urgent, Frustrated, Critical, etc.\n"
    "- Strong complaints or frustration MUST still be classified as Negative.\n\n"

    "--------------------------------\n"
    "STRICT OUTPUT RULES (NO EXCEPTIONS)\n"
    "--------------------------------\n"
    "- Output MUST be exactly one of the three labels listed above.\n"
    "- Output MUST match spelling exactly.\n"
    "- Output MUST contain no explanation.\n"
    "- Output MUST contain no additional words, symbols, or punctuation.\n"
    "- If unsure, choose the closest matching label from the allowed list.\n"
)


SENTIMENT_PROMPT_EXAMPLES = (
    "Examples:\n"

    "Input: Jobs activated very smoothly.\n"
    "Output: Positive\n\n"

    "Input: Very good job.\n"
    "Output: Positive\n\n"

    "Input: Increase communication.\n"
    "Output: Neutral\n\n"

    "Input: Please inform customer ID or consumer number.\n"
    "Output: Neutral\n\n"

    "Input: Power cut again today, very disappointing service.\n"
    "Output: Negative\n\n"

    "Input: My electricity bill is wrong and no one is responding.\n"
    "Output: Negative\n\n"
)


SENTIMENT_PROMPT_FORMAT = (
    "Now classify the sentiment of the following message.\n"
    "Input: {user_text}\n"
    "Output:"
)
