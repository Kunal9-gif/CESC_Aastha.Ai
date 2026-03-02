import re
import json

def extract_mobile(text):
    mobile = "not found"

    if not isinstance(text, str):
        return mobile

    temp_text = text

    # Normalize unicode dashes
    temp_text = temp_text.replace("–", "-").replace("—", "-")

    # Remove country code variants
    temp_text = re.sub(r'\+91', '', temp_text)
    temp_text = re.sub(r'\(0091\)', '', temp_text)
    temp_text = re.sub(r'\(91\)', '', temp_text)
    temp_text = re.sub(r'\b0091\b', '', temp_text)
    temp_text = re.sub(r'\b091\b', '', temp_text)
    temp_text = re.sub(r'\b91\b', '', temp_text)

    # Remove (0)
    temp_text = re.sub(r'\(0\)', '', temp_text)

    mobile_pattern = re.compile(r'((?:\d[\s\-\./()]*){10,11})')
    matches = mobile_pattern.findall(temp_text)

    for m in matches:
        clean = re.sub(r'\D', '', m)

        if len(clean) == 11 and clean.startswith("0"):
            clean = clean[1:]

        if len(clean) == 10 and clean[0] in "6789":
            mobile = clean
            break

    return mobile