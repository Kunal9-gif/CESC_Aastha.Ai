import re

def extract_11_digit_numbers(text_list):
    pattern = re.compile(r'(?:\d\s*){11}')

    for idx, text in enumerate(text_list, 1):
        matches = pattern.findall(text)

        print(f"\nTest Case {idx}:")
        print(f"Text: {text}")

        if matches:
            print("Matched 11-digit numbers:")
            for m in matches:
                # Clean spaces for final output
                clean_number = re.sub(r"\s+", "", m)
                print(f"  Raw Match   : '{m}'")
                print(f"  Clean Number: '{clean_number}'")
        else:
            print("No 11-digit number found.")


# =========================
# TEST CASES
# =========================
test_cases = [
    "My number is 12345678901 and it is valid",
    "Call me at 123 456 78901 tomorrow",
    "The code is 1 2 3 4 5 6 7 8 9 0 1 for access",
    "Wrong number 1234567890 (only 10 digits)",
    "Another format 12 345 678 901 is also valid",
    "Multiple numbers here: 12345678901 and 109 876 54321",
    "No number here just text",
    "Edge case: 1 23 4567 8901 mixed spacing",
]

test_case1 =[
    "My number is 12345  678901 and it is valid"
]

# =========================
# RUN
# =========================
extract_11_digit_numbers(test_case1)
