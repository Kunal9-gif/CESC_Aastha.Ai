import os
import json
import logging
import requests
from regex_code import extract_mobile 

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# =========================
# ENV VARIABLES
# =========================
BASE_URL = os.environ.get("BASE_URL")
COMP_SRC = os.environ.get("COMP_SRC")

if not BASE_URL:
    raise Exception("BASE_URL environment variable not set")

INITIAL_TOKEN_URL = f"{BASE_URL}/dicekey/botKeyStore.txt"
JWT_URL = f"{BASE_URL}/api/getSecretKey"
CHK_CONSUMER_URL = f"{BASE_URL}/api/chkconsumer"
CONSUMER_DETAILS_URL = f"{BASE_URL}/api/consumerDetails"

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}

# =========================
# HELPERS
# =========================

def get_param(event, name):
    for param in event.get("parameters", []):
        if param.get("name") == name:
            return param.get("value")
    return None


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        logger.error(f"Invalid JSON: {resp.text}")
        return {}


# =========================
# AUTHENTICATION
# =========================

def get_initial_token():
    r = requests.get(INITIAL_TOKEN_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    r.raise_for_status()
    return r.text.strip()


def get_jwt_token(initial_token):
    r = requests.post(
        JWT_URL,
        json={"client_token_vl": initial_token},
        headers=COMMON_HEADERS,
        timeout=10
    )
    r.raise_for_status()
    return r.json().get("access_token")


def auth_headers(jwt):
    return COMMON_HEADERS | {"Authorization": f"Bearer {jwt}"}


# =========================
# ADDRESS EXTRACTION
# =========================

def extract_address(data):
    d = data.get("data", {})

    fields = [
        d.get("ACC_ADDR", ""),
        d.get("ADDR_TWO", ""),
        d.get("ADDR_THREE", ""),
        d.get("ADDR_FOUR", ""),
        d.get("ADDR_FIVE", ""),
        d.get("ADDR_SIX", "")
    ]

    return ", ".join(x.strip() for x in fields if x and isinstance(x, str))


# =========================
# API CALLS
# =========================

def fetch_customer_ids(jwt, mobile):

    payload = {
        "mobile": mobile,
        "comp_src": COMP_SRC
    }

    r = requests.post(
        CHK_CONSUMER_URL,
        headers=auth_headers(jwt),
        json=payload,
        timeout=10
    )
    r.raise_for_status()

    data = safe_json(r)

    return (
        data.get("data", {})
        .get("LT", {})
        .get("customer_id", [])
    )


def fetch_consumer_details(jwt, mobile, cid):

    payload = {
        "mobile": mobile,
        "custid": cid,
        "comp_src": COMP_SRC
    }

    r = requests.post(
        CONSUMER_DETAILS_URL,
        headers=auth_headers(jwt),
        json=payload,
        timeout=10
    )
    r.raise_for_status()

    data = safe_json(r)
    return extract_address(data)


# =========================
# LAMBDA HANDLER
# =========================

def lambda_handler(event, context):

    logger.info("EVENT RECEIVED: %s", json.dumps(event))

    body_text = ""

    try:
        action_group = event['actionGroup']
        function = event['function']
        message_version = event.get('messageVersion',1)

        mobile = get_param(event, "Mobile")
        print(mobile)
        mobile = extract_mobile(mobile)
        print(mobile)

        if (mobile == 'not found'):
            body_text = "Mobile number is required."
        else:
            # 🔐 AUTH
            initial_token = get_initial_token()
            jwt = get_jwt_token(initial_token)

            if not jwt:
                raise Exception("JWT token not received")

            # 📡 FETCH CIDs
            cids = fetch_customer_ids(jwt, mobile)

            if not cids:
                body_text = "No Consumer ID found for this mobile number."
            else:
                lines = []

                for i, cid in enumerate(cids, start=1):
                    address = fetch_consumer_details(jwt, mobile, cid)
                    lines.append(f"{i}. CID {cid} — {address}")

                body_text = "\n".join(lines)

    except Exception as e:
        logger.exception("ERROR")
        body_text = "Internal system error occurred. Please try again later."

    # ✅ BEDROCK REQUIRED RESPONSE FORMAT
    response = {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "function": function,
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": body_text
                    }
                }
            }
        }
    }

    print(response)
    return response
