import requests

# =========================
# API URLs
# =========================
GET_CONSUMER_COUNT_URL = "https://smautomation.cesc.co.in/api/getConsumerCount"
CONSUMER_DETAILS_URL = "https://smautomation.cesc.co.in/api/consumerDetails"
GEN_SUPPLY_CRM_DKT_URL = "https://smautomation.cesc.co.in/api/genSupplyCrmDkt"

COMP_SRC = "awsinfosys"
COMP = "1"


# =========================
# Functions
# =========================

def get_consumer_ids_from_mobile(mobile):
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


def gen_supply_crm_dkt(custid, mobile):
    payload = {
        "custid": custid,
        "mob": mobile,
        "comp": COMP,
        "comp_src": COMP_SRC
    }

    print("\n📝 Calling genSupplyCrmDkt API with payload:", payload)

    response = requests.post(GEN_SUPPLY_CRM_DKT_URL, json=payload)
    print("Status Code:", response.status_code)
    print("Raw Response:", response.text)

    try:
        return response.json()
    except Exception as e:
        print("❌ Error parsing JSON:", e)
        return None


# =========================
# Helper: Select CustID
# =========================

def select_customer_id(consumer_ids):
    print("\n🔢 Multiple Customer IDs found. Please select one:\n")

    for idx, cid in enumerate(consumer_ids, start=1):
        print(f"{idx}. {cid}")

    while True:
        choice = input("\nEnter option number: ").strip()

        if choice.isdigit():
            choice = int(choice)
            if 1 <= choice <= len(consumer_ids):
                return consumer_ids[choice - 1]

        print("❌ Invalid selection. Please try again.")


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

        print("\n✅ Consumer IDs fetched:", consumer_ids)

        # Select custid
        if len(consumer_ids) == 1:
            selected_custid = consumer_ids[0]
            print(f"\n➡ Only one Customer ID found: {selected_custid}")
        else:
            selected_custid = select_customer_id(consumer_ids)
            print(f"\n➡ Selected Customer ID: {selected_custid}")

        # Fetch Consumer Details
        details = get_consumer_details(selected_custid)
        print("\n📄 Consumer Details Response:")
        print(details)

        # Generate Supply CRM Docket
        result = gen_supply_crm_dkt(selected_custid, mobile)
        print("\n📄 Final genSupplyCrmDkt Response:")
        print(result)

    elif choice == "2":
        custid = input("Enter Customer ID (custid): ").strip()
        mobile = input("Enter Mobile Number: ").strip()

        # Fetch Consumer Details
        details = get_consumer_details(custid)
        print("\n📄 Consumer Details Response:")
        print(details)

        # Generate Supply CRM Docket
        result = gen_supply_crm_dkt(custid, mobile)
        print("\n📄 Final genSupplyCrmDkt Response:")
        print(result)

    else:
        print("❌ Invalid choice. Please select 1 or 2.")


# =========================
# Run
# =========================

if __name__ == "__main__":
    main()
