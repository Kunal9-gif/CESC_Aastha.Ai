import json
import re
from datetime import datetime
from typing import Optional, Dict


class WhatsAppEventNormalizer:
    def __init__(self, channel_type: str = "WHATSAPP"):
        self.channel_type = channel_type

    def normalize_text(self, text: str) -> str:
        """
        Normalize user input text:
        - Lowercase
        - Remove special characters
        - Remove extra spaces
        """
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Replace special characters with space
        text = re.sub(r"[^a-z0-9\s]", " ", text)

        # Remove extra spaces
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def build_event_envelope(
        self,
        source_user_id: str,
        raw_text: str,
        media: Optional[Dict] = None
    ) -> Dict:
        """
        Build the standardized event envelope
        """

        normalized_text = self.normalize_text(raw_text)

        event_envelope = {
            "channelType": self.channel_type,
            "sourceUserId": source_user_id,
            "messagePayload": {
                "rawText": raw_text,
                "normalizedText": normalized_text,
                "language": "en",
                "messageType": "TEXT"
            },
            "media": media,  # None if no media
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        return event_envelope


# =========================
# Example Usage
# =========================
if __name__ == "__main__":
    normalizer = WhatsAppEventNormalizer()

    user_inputs = [
        "My power is out—who should I call?",
        "I need to talk to someone about this outage.",
        "Is there a number for reporting outages?",
        "How do I contact CESC for urgent help?"
    ]

    source_user_id = "whatsapp:+919876543210"

    for text in user_inputs:
        envelope = normalizer.build_event_envelope(
            source_user_id=source_user_id,
            raw_text=text
        )

        print(json.dumps(envelope, indent=4))
        print("-" * 80)
