import requests

BASE_URL = "https://dice-uat.cesc.co.in"

INITIAL_TOKEN_URL = f"{BASE_URL}/dicekey/botKeyStore.txt"
JWT_TOKEN_URL = f"{BASE_URL}/api/getSecretKey"
TARGET_API_URL = f"{BASE_URL}/api/olntAnx1"

SOURCE_NAME = "whatsapp"
CUSTOMER_ID = "11001867601"


def get_initial_token():
    resp = requests.get(
        INITIAL_TOKEN_URL,
        timeout=10,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )
    resp.raise_for_status()

    token = resp.text.strip().replace("\ufeff", "")
    print("Initial Token:", token)
    return token


def get_jwt_token(initial_token):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    payload = {
        "client_token_vl": initial_token
    }

    resp = requests.post(
        JWT_TOKEN_URL,
        json=payload,
        headers=headers,
        timeout=10
    )

    # 🔥 Print raw response for debugging
    print("JWT Status Code:", resp.status_code)
    print("JWT Raw Response:", resp.text)

    resp.raise_for_status()

    return resp.json()["access_token"]


def call_target_api(jwt_token):
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    payload = {
        "olnt_src": SOURCE_NAME,
        "customer_id": CUSTOMER_ID
    }

    resp = requests.post(
        TARGET_API_URL,
        json=payload,
        headers=headers,
        timeout=10
    )

    print("Final API Status:", resp.status_code)
    print("Final API Response:", resp.text)


if __name__ == "__main__":
    try:
        token = get_initial_token()
        jwt = get_jwt_token(token)
        call_target_api(jwt)

    except requests.exceptions.RequestException as e:
        print("API call failed:", e)
