import requests

from config import (
    GET_COMPLAINT_STATUS_URL,
    COMP_SRC
)
# =========================
# Function
# =========================

def get_complaint_status(docket_no):
    """
    Calls getComplaintStatus API using docket number
    """
    payload = {
        "docket": docket_no,
        "comp_src": COMP_SRC
    }

    print("\n🔍 Calling getComplaintStatus API with payload:", payload)

    response = requests.post(GET_COMPLAINT_STATUS_URL, json=payload)

    print("Status Code:", response.status_code)
    print("Raw Response:", response.text)

    try:
        return response.json()
    except Exception as e:
        print("❌ Error parsing JSON:", e)
        return None


# =========================
# Main (Test Runner)
# =========================

def main():
    docket_no = input("Enter Docket Number: ").strip()

    result = get_complaint_status(docket_no)

    print("\n📄 Final getComplaintStatus Response:")
    print(result)


# =========================
# Run
# =========================

if __name__ == "__main__":
    main()
