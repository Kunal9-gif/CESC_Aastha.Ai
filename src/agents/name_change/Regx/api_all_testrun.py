import requests
import csv
import time
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
MOBILE_NO = "9163361930"

# LT
CUST_ID = "05001190061"
LT_DOCKET_NO = "11250316"

# HT
HT_CONS_NO = "01060001001"
HT_DOCKET_NO = "901265"

# Green Tariff
TARIFF_CATEGORY = "X"

# Chat History
CHAT_HISTORY_TEXT = "TEST CHAT HISTORY"
CALL_TIME = "2026-01-28 13:12:01"
# =================================


# ---------- CSV LOGGER ----------
def log_to_csv(api_name, endpoint, status_code, success, exec_time_ms, response_text):
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
                "execution_time_ms",
                "api_response"
            ])

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            api_name,
            endpoint,
            status_code,
            success,
            exec_time_ms,
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
    resp = requests.post(
        JWT_TOKEN_URL,
        json={"client_token_vl": initial_token},
        headers=COMMON_HEADERS,
        timeout=10
    )
    print("JWT Status Code:", resp.status_code)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ---------- GENERIC API CALL ----------
def call_api(api_name, endpoint, payload, jwt_token):
    url = f"{BASE_URL}{endpoint}"
    headers = COMMON_HEADERS | {"Authorization": f"Bearer {jwt_token}"}

    print("\n==============================")
    print("API:", api_name)
    print("Endpoint:", endpoint)

    start_time = time.perf_counter()

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        exec_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        success = "YES" if resp.status_code == 200 else "NO"

        print("Status:", resp.status_code)
        print("Time Taken (ms):", exec_time_ms)

        log_to_csv(api_name, endpoint, resp.status_code, success, exec_time_ms, resp.text)

    except Exception as e:
        exec_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        log_to_csv(api_name, endpoint, "ERROR", "NO", exec_time_ms, str(e))

    print("==============================\n")


# ---------- ALL 10 API TEST CASES ----------
API_TEST_CASES = [
    # 1
    {
        "name": "Mapped Customer ID by Mobile",
        "endpoint": "/api/chkconsumer",
        "payload": {"mobile": MOBILE_NO, "comp_src": SOURCE_NAME}
    },
    # 2
    {
        "name": "LT Consumer Details",
        "endpoint": "/api/consumerDetails",
        "payload": {"mobile": MOBILE_NO, "custid": CUST_ID, "comp_src": SOURCE_NAME}
    },
    # 3
    {
        "name": "LT Supply Off – Generate Docket",
        "endpoint": "/api/genSupplyCrmDkt",
        "payload": {
            "custid": CUST_ID,
            "mobile": MOBILE_NO,
            "comp": "1",
            "comp_src": SOURCE_NAME,
            "dtl": "Test complaint details MK-6"
        }
    },
    # 4
    {
        "name": "LT Emergency – Generate Docket",
        "endpoint": "/api/genEmergencyCrmDkt",
        "payload": {
            "custid": "",
            "mobile": MOBILE_NO,
            "comp": "7",
            "comp_src": SOURCE_NAME,
            "add": "Emergency test address",
            "remark": "test emergency"
        }
    },
    # 5
    {
        "name": "LT Complaint Status",
        "endpoint": "/api/getComplaintStatus",
        "payload": {"docket": LT_DOCKET_NO, "mobile": MOBILE_NO, "comp_src": SOURCE_NAME}
    },
    # 6
    {
        "name": "Green Tariff Consumer Details",
        "endpoint": "/api/greenEnergyConsumerDetails",
        "payload": {
            "mobile": MOBILE_NO,
            "custid": CUST_ID,
            "consumer_type": "LT",
            "comp_src": SOURCE_NAME
        }
    },
    # 7
    {
        "name": "Green Tariff Apply",
        "endpoint": "/api/greenEnergyApply",
        "payload": {
            "mobile": MOBILE_NO,
            "custid": CUST_ID,
            "consumer_type": "LT",
            "tariff_category": TARIFF_CATEGORY,
            "intend_to_have": "25",
            "frequency": "Monthly",
            "email": "test@gmail.com",
            "cons_name": "TEST CONSUMER",
            "cons_address": "TEST ADDRESS",
            "comp_src": SOURCE_NAME
        }
    },
    # 8
    {
        "name": "HT Supply Off – Generate Docket",
        "endpoint": "/api/genHtSupplyCrmDkt",
        "payload": {
            "consno": HT_CONS_NO,
            "mobile": MOBILE_NO,
            "comp": "1",
            "comp_src": SOURCE_NAME,
            "dtl": "Test HT supply off complaint"
        }
    },
    # 9
    {
        "name": "HT Docket Status",
        "endpoint": "/api/getHTComplaintStatus",
        "payload": {"mobile": MOBILE_NO, "docket": HT_DOCKET_NO, "comp_src": SOURCE_NAME}
    },
    # 10
    {
        "name": "Save Chat History",
        "endpoint": "/api/saveChatHistory",
        "payload": {
            "custid": CUST_ID,
            "chat_history": CHAT_HISTORY_TEXT,
            "call_time": CALL_TIME,
            "comp_src": SOURCE_NAME
        }
    }
]


# ---------- MAIN ----------
if __name__ == "__main__":
    print("🚀 Starting FULL API test run (10 APIs)...\n")

    try:
        jwt_token = get_jwt_token(get_initial_token())

        for api in API_TEST_CASES:
            call_api(api["name"], api["endpoint"], api["payload"], jwt_token)

        print("✅ ALL 10 APIs tested exactly once.")
        print(f"📄 Results saved to: {CSV_FILE}")

    except Exception as e:
        print("❌ Execution failed:", e)
