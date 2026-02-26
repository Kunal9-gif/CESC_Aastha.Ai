import requests
import csv
import json
from datetime import datetime

# ================= CONFIG =================
BASE_URL = "https://dice-uat.cesc.co.in"

INITIAL_TOKEN_URL = f"{BASE_URL}/dicekey/botKeyStore.txt"
JWT_TOKEN_URL = f"{BASE_URL}/api/getSecretKey"

CSV_FILE = "api_test_results.csv"

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}

# -------- STATIC TEST DATA --------
SOURCE_NAME = "whatsapp"
MOBILE_NO = "9836384460"
CUST_ID = "50000004766"
DOCKET_NO = "11250316"
# =================================


# ---------- CSV LOGGER ----------
def log_to_csv(api_name, endpoint, status_code, success, response_text):
    file_exists = False
    try:
        with open(CSV_FILE, "r", encoding="utf-8"):
            file_exists = True
    except FileNotFoundError:
        pass

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "timestamp",
                "api_name",
                "endpoint",
                "http_status",
                "success",
                "api_response"
            ])

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            api_name,
            endpoint,
            status_code,
            success,
            response_text
        ])


# ---------- AUTH ----------
def get_initial_token():
    resp = requests.get(
        INITIAL_TOKEN_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10
    )
    resp.raise_for_status()
    token = resp.text.strip().replace("\ufeff", "")
    print("Initial Token:", token)
    return token


def get_jwt_token(initial_token):
    payload = {"client_token_vl": initial_token}

    resp = requests.post(
        JWT_TOKEN_URL,
        json=payload,
        headers=COMMON_HEADERS,
        timeout=10
    )

    print("JWT Status Code:", resp.status_code)
    print("JWT Raw Response:", resp.text)

    resp.raise_for_status()
    return resp.json()["access_token"]


# ---------- GENERIC API CALL ----------
def call_api(api_name, endpoint, payload, jwt_token):
    url = f"{BASE_URL}{endpoint}"

    headers = COMMON_HEADERS.copy()
    headers["Authorization"] = f"Bearer {jwt_token}"

    print("\n==============================")
    print("API:", api_name)
    print("Endpoint:", endpoint)
    print("Payload:", payload)

    try:
        resp = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=15
        )

        success = "YES" if resp.status_code == 200 else "NO"

        print("Status:", resp.status_code)
        print("Response:")
        print(resp.text)

        log_to_csv(
            api_name=api_name,
            endpoint=endpoint,
            status_code=resp.status_code,
            success=success,
            response_text=resp.text
        )

    except Exception as e:
        print("API FAILED:", str(e))
        log_to_csv(
            api_name=api_name,
            endpoint=endpoint,
            status_code="ERROR",
            success="NO",
            response_text=str(e)
        )

    print("==============================\n")


# ---------- API OPTIONS ----------
def run_api(option, jwt_token):

    if option == "1":
        call_api(
            "Mapped Customer ID by Mobile",
            "/api/chkconsumer",
            {
                "mobile": MOBILE_NO,
                "comp_src": SOURCE_NAME
            },
            jwt_token
        )

    elif option == "2":
        call_api(
            "LT Consumer Details",
            "/api/consumerDetails",
            {
                "mobile": MOBILE_NO,
                "custid": CUST_ID,
                "comp_src": SOURCE_NAME
            },
            jwt_token
        )

    elif option == "3":
        call_api(
            "LT No Power – Generate Docket",
            "/api/genSupplyCrmDk",
            {
                "custid": CUST_ID,
                "mobile": MOBILE_NO,
                "comp": "1",
                "comp_src": SOURCE_NAME,
                "dtl": "Test complaint details"
            },
            jwt_token
        )

    elif option == "4":
        call_api(
            "SOS Emergency – Generate Docket",
            "/api/genEmergencyCrmDkt",
            {
                "custid": "",
                "mobile": MOBILE_NO,
                "comp": "7",
                "comp_src": SOURCE_NAME,
                "add": "Test address",
                "remark": "test remarks"
            },
            jwt_token
        )

    elif option == "5":
        call_api(
            "Complaint Status by Docket",
            "/api/getComplaintStatus",
            {
                "docket": DOCKET_NO,
                "mobile": MOBILE_NO,
                "comp_src": SOURCE_NAME
            },
            jwt_token
        )

    elif option == "6":
        call_api(
            "Green Tariff Consumer Details",
            "/api/greenEnergyConsumerDetails",
            {
                "mobile": MOBILE_NO,
                "custid": CUST_ID,
                "consumer_type": "LT",
                "comp_src": SOURCE_NAME
            },
            jwt_token
        )

    elif option == "7":
        call_api(
            "Green Tariff Apply",
            "/api/greenEnergyApply",
            {
                "mobile": MOBILE_NO,
                "custid": CUST_ID,
                "consumer_type": "LT",
                "tariff_category": "X",
                "intend_to_have": "25",
                "frequency": "Monthly",
                "email": "test@gmail.com",
                "cons_name": "TEST CONSUMER",
                "cons_address": "TEST ADDRESS",
                "comp_src": SOURCE_NAME
            },
            jwt_token
        )

    else:
        print("❌ Invalid option selected")


# ---------- MAIN ----------
if __name__ == "__main__":
    try:
        initial_token = get_initial_token()
        jwt_token = get_jwt_token(initial_token)

        print("""
Choose API to test:
1 - Mapped Customer ID by Mobile
2 - LT Consumer Details
3 - LT No Power (Generate Docket)
4 - SOS Emergency (Generate Docket)
5 - Complaint Status by Docket
6 - Green Tariff Consumer Details
7 - Green Tariff Apply
""")

        option = input("Enter option number: ").strip()
        run_api(option, jwt_token)

        print(f"✅ Result saved to {CSV_FILE}")

    except requests.exceptions.RequestException as e:
        print("API call failed:", e)
