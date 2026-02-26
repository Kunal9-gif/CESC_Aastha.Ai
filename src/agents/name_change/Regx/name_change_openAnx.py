import requests
import json

# ================= CONFIG =================
BASE_URL = "https://dice-uat.cesc.co.in"

COMP_SRC = "whatsapp"
APPLN_REF_NO = "10211"

INITIAL_TOKEN_URL = f"{BASE_URL}/dicekey/botKeyStore.txt"
JWT_URL = f"{BASE_URL}/api/getSecretKey"
OPEN_ANX_URL = f"{BASE_URL}/api/openAnx"

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
    return COMMON_HEADERS | {
        "Authorization": f"Bearer {jwt}"
    }


# ================= API CALL =================
def fetch_open_anx(jwt):

    payload = {
        "applnRefNo": APPLN_REF_NO,
        "comp_src": COMP_SRC
    }

    r = requests.post(
        OPEN_ANX_URL,
        headers=auth_headers(jwt),
        json=payload
    )

    r.raise_for_status()
    return r.json()


# ================= MAIN =================
if __name__ == "__main__":

    try:
        # Step 1 — Authentication
        initial_token = get_initial_token()
        jwt = get_jwt_token(initial_token)

        # Step 2 — API Call
        full_response = fetch_open_anx(jwt)

        # ✅ PRINT COMPLETE JSON RESPONSE
        print(json.dumps(full_response, indent=2))

    except Exception as e:
        print("ERROR:", str(e))