import requests

# =========================
# API URLs
# =========================
CONSUMER_DETAILS_URL = "https://smautomation.cesc.co.in/api/consumerDetails"
GET_CONSUMER_COUNT_URL = "https://smautomation.cesc.co.in/api/getConsumerCount"

COMP_SRC = "awsinfosys"   # as per your input


# =========================
# Functions
# =========================

def get_consumer_ids_from_mobile(mobile):
    """
    Calls getConsumerCount API and returns list of consumer IDs
    """
    payload = {
        "mob": mobile,
        "comp_src": COMP_SRC
    }

    print("\n📞 Calling getConsumerCount API with payload:", payload)

    response = requests.post(GET_CONSUMER_COUNT_URL, json=payload)

    print("Status Code:", response.status_code)
    print("Raw Response:", response.text)

    data = response.json()

    if data.get("status") == "success" and "data" in data:
        return data["data"]
    else:
        print("❌ Failed to fetch consumer IDs from mobile number")
        return []


def get_consumer_details(custid):
    """
    Calls consumerDetails API using custid
    """
    params = {
        "custid": custid,
        "comp_src": COMP_SRC
    }

    print("\n🔍 Calling consumerDetails API with params:", params)

    response = requests.get(CONSUMER_DETAILS_URL, params=params)

    print("Status Code:", response.status_code)
    print("Raw Response:", response.text)

    try:
        return response.json()
    except Exception as e:
        print("❌ Error parsing JSON:", e)
        return None


# =========================
# Main Flow
# =========================

def main():
    print("======================================")
    print("Select Input Type")
    print("1️⃣  Enter Mobile Number")
    print("2️⃣  Enter Customer ID (custid)")
    print("======================================")

    choice = input("Enter your choice (1 or 2): ").strip()

    if choice == "1":
        mobile = input("Enter Mobile Number: ").strip()

        consumer_ids = get_consumer_ids_from_mobile(mobile)

        if not consumer_ids:
            print("❌ No consumer IDs found for this mobile number")
            return

        print("\n✅ Consumer IDs found:", consumer_ids)

        # If multiple IDs, pick first (or you can loop over all)
        selected_custid = consumer_ids[0]
        print(f"\n➡ Using Customer ID: {selected_custid} to fetch consumer details")

        details = get_consumer_details(selected_custid)
        print("\n📄 Final Consumer Details Response:")
        print(details)

    elif choice == "2":
        custid = input("Enter Customer ID (custid): ").strip()

        details = get_consumer_details(custid)
        print("\n📄 Final Consumer Details Response:")
        print(details)

    else:
        print("❌ Invalid choice. Please select 1 or 2.")


# =========================
# Run
# =========================

if __name__ == "__main__":
    main()
