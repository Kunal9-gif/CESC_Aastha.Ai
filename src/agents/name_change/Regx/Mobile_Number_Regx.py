import re

def extract_indian_mobile_numbers(text_list):
    pattern = re.compile(r'(?:\+91|91)?[\s\-]*((?:\d[\s\-]*){10})')

    for idx, text in enumerate(text_list, 1):
        matches = pattern.findall(text)

        print(f"\nTest Case {idx}:")
        print(f"Text: {text}")

        if matches:
            print("Extracted Mobile Numbers:")
            for m in matches:
                clean_number = re.sub(r'[\s\-]', '', m)
                print(f"  Raw Match   : '{m}'")
                print(f"  Clean Number: '{clean_number}'")
        else:
            print("No valid mobile number found.")


# =========================
# TEST CASES
# =========================
test_cases = [
    "+911234567890",
    "+91 1234567890",
    "911234567890",
    "91  1234567890",
    "91 - 1234567890",
    "+91-1234567890",
    "+91 12345 67 890",
    "Contact: +91 98 76 54 32 10 ASAP",
    "Invalid: 123456789 (9 digits)",
    "Text without number",
    "Multiple: +91 99999 88888 and 91-7777766666",
]

# =========================
# RUN
# =========================
extract_indian_mobile_numbers(test_cases)
