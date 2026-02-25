import pandas as pd
import re

file_path = "C:\\Users\\DELL\\Downloads\\Mobile_CID_Test_Cases_Combined.xlsx"   # your input file
df = pd.read_excel(file_path)

# ================================
# REGEX PATTERNS
# ================================

cid_pattern = re.compile(r'((?:\d[\s\-]*){11})')


# ================================
# MOBILE EXTRACTION FUNCTION
# ================================

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

    # Remove (0) but keep leading 0 attached to number
    temp_text = re.sub(r'\(0\)', '', temp_text)

    # Pattern: 10 or 11 digits with separators
    mobile_pattern = re.compile(r'((?:\d[\s\-\./()]*){10,11})')
    matches = mobile_pattern.findall(temp_text)

    for m in matches:
        clean = re.sub(r'\D', '', m)

        # Handle leading zero case: 09876543210 → 9876543210
        if len(clean) == 11 and clean.startswith("0"):
            clean = clean[1:]

        if len(clean) == 10 and clean[0] in "6789":
            mobile = clean
            break

    return mobile


# ================================
# CID EXTRACTION FUNCTION
# ================================

def extract_cid(text):
    cid = "not found"

    if not isinstance(text, str):
        return cid

    temp_text = text

    # ---------------------------------------------
    # REMOVE ALL MOBILE BLOCKS VERY AGGRESSIVELY
    # ---------------------------------------------
    # This removes ANY sequence starting with +91, 91, 091, 0091 and followed by digits/separators
    temp_text = re.sub(
        r'(\+91|0091|091|91)[\s\-\./()]*[0-9][0-9\s\-\./()]{8,15}',
        '',
        temp_text
    )

    # Also remove standalone (91) and (0091) blocks
    temp_text = re.sub(
        r'\((91|0091)\)[\s\-\./()]*[0-9][0-9\s\-\./()]{8,15}',
        '',
        temp_text
    )

    # ---------------------------------------------
    # CID EXTRACTION (11 DIGITS)
    # ---------------------------------------------
    matches = cid_pattern.findall(temp_text)

    for item in matches:
        clean = re.sub(r'\D', '', item)

        if len(clean) == 11:
            cid = clean
            break

    return cid


# ================================
# PROCESS ROW BY ROW
# ================================

mobiles = []
cids = []

for _, row in df.iterrows():
    sentence = row.get("Test Case Sentence", "")

    mobile = extract_mobile(sentence)
    cid = extract_cid(sentence)

    mobiles.append(mobile)
    cids.append(cid)

df["Extracted Mobile Number"] = mobiles
df["Extracted CID"] = cids


# ================================
# SAVE OUTPUT
# ================================

output_path = "Mobile_CID_Extraction_Output.xlsx"
df.to_excel(output_path, index=False)

print("Extraction completed. Output saved to:", output_path)
