import requests
import json

# ================= CONFIG =================
BASE_URL = "https://dice-uat.cesc.co.in"

COMP_SRC = "whatsapp"
APPLN_REF_NO = "20880226"

INITIAL_TOKEN_URL = f"{BASE_URL}/dicekey/botKeyStore.txt"
JWT_URL = f"{BASE_URL}/api/getSecretKey"
CHECK_STATUS_URL = f"{BASE_URL}/api/showCheckStatus"

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}

# ================= AUTH =================
def get_initial_token():
    r = requests.get(
        INITIAL_TOKEN_URL,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    r.raise_for_status()
    return r.text.strip()


def get_jwt_token(initial_token):
    r = requests.post(
        JWT_URL,
        json={"client_token_vl": initial_token},
        headers=COMMON_HEADERS
    )
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(jwt):
    headers = COMMON_HEADERS.copy()
    headers["Authorization"] = f"Bearer {jwt}"
    return headers


# ================= API CALL =================
def fetch_check_status(jwt):

    payload = {
        "applnRefNo": APPLN_REF_NO,
        "comp_src": COMP_SRC
    }

    r = requests.post(
        CHECK_STATUS_URL,
        headers=auth_headers(jwt),
        json=payload
    )

    r.raise_for_status()
    return r.json()


# ================= MAIN =================
if __name__ == "__main__":

    try:
        print("Authenticating...")
        token = get_initial_token()
        jwt = get_jwt_token(token)

        print("Calling showCheckStatus API...")
        response = fetch_check_status(jwt)

        print("\nFULL RESPONSE:")
        print(json.dumps(response, indent=2))

    except Exception as e:
        print("ERROR:", str(e))