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

    response = requests.get(CONSUMER_DETAILS_URL, params=params)

    try:
        return response.json()
    except Exception as e:
        print(f"❌ Error parsing JSON for custid {custid}: {e}")
        return None


def extract_address(details_response):
    """
    Extract address from CESC consumerDetails response using exact known keys.
    """
    try:
        data = details_response.get("DATA")

        if not data or not isinstance(data, dict):
            return "Address not available"

        address_fields = [
            data.get("ACC_ADDR", ""),
            data.get("ADDR_TWO", ""),
            data.get("ADDR_THREE", ""),
            data.get("ADDR_FOUR", ""),
            data.get("ADDR_FIVE", ""),
            data.get("ADDR_SIX", "")
        ]

        # Remove empty values and strip spaces
        address_parts = [part.strip() for part in address_fields if part and part.strip()]

        if address_parts:
            return ", ".join(address_parts)

        return "Address not available"

    except Exception as e:
        print("❌ Error extracting address:", e)
        return "Address not available"


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
# Helper: Select CustID with Address
# =========================

def select_customer_with_address(custid_list):
    customer_map = []

    print("\n🔍 Fetching address for each Customer ID...\n")

    for custid in custid_list:
        details = get_consumer_details(custid)
        address = extract_address(details) if details else "Address not available"
        customer_map.append({
            "custid": custid,
            "address": address
        })

    print("🔢 Multiple connections found. Please select one:\n")

    for idx, item in enumerate(customer_map, start=1):
        print(f"{idx}. {item['custid']}  –  {item['address']}")

    while True:
        choice = input("\nEnter option number: ").strip()

        if choice.isdigit():
            choice = int(choice)
            if 1 <= choice <= len(customer_map):
                return customer_map[choice - 1]

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

        # Select with address
        if len(consumer_ids) == 1:
            details = get_consumer_details(consumer_ids[0])
            address = extract_address(details)
            selected = {
                "custid": consumer_ids[0],
                "address": address
            }
            print(f"\n➡ Only one connection found: {selected['custid']} – {selected['address']}")
        else:
            selected = select_customer_with_address(consumer_ids)

        print(f"\n✅ Selected Customer ID: {selected['custid']}")
        print(f"🏠 Address: {selected['address']}")

        # Generate Supply CRM Docket
        result = gen_supply_crm_dkt(selected["custid"], mobile)

        print("\n📄 Final genSupplyCrmDkt Response:")
        print(result)

    elif choice == "2":
        custid = input("Enter Customer ID (custid): ").strip()
        mobile = input("Enter Mobile Number: ").strip()

        details = get_consumer_details(custid)
        address = extract_address(details)

        print(f"\n🏠 Address: {address}")

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
