import requests

# ================= CONFIG =================
BASE_URL = "https://dice-uat.cesc.co.in"

COMP_SRC = "whatsapp"
CUSTOMER_ID = "59000520629"

INITIAL_TOKEN_URL = f"{BASE_URL}/dicekey/botKeyStore.txt"
JWT_URL = f"{BASE_URL}/api/getSecretKey"
OLNT_ANX1_URL = f"{BASE_URL}/api/olntAnx1"

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}


# ================= AUTH =================
def get_initial_token():
    print("\nGetting initial token...")

    r = requests.get(
        INITIAL_TOKEN_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )

    r.raise_for_status()
    token = r.text.strip()

    print("Initial token received")
    return token


def get_jwt_token(initial_token):
    print("Getting JWT token...")

    payload = {
        "client_token_vl": initial_token
    }

    r = requests.post(
        JWT_URL,
        json=payload,
        headers=COMMON_HEADERS,
        timeout=30
    )

    r.raise_for_status()

    response = r.json()
    jwt = response.get("access_token")

    if not jwt:
        raise Exception("JWT token not found in response")

    print("JWT token received")
    return jwt


def auth_headers(jwt):
    headers = COMMON_HEADERS.copy()
    headers["Authorization"] = f"Bearer {jwt}"
    return headers


# ================= API CALL =================
def fetch_required_fields(jwt):

    print("\nCalling OLNT ANX1 API...")

    payload = {
        "customer_id": CUSTOMER_ID,
        "comp_src": COMP_SRC
    }

    r = requests.post(
        OLNT_ANX1_URL,
        headers=auth_headers(jwt),
        json=payload,
        timeout=30
    )

    r.raise_for_status()

    response = r.json()

    # ✅ FULL DEBUG OUTPUT
    print("\nFULL API RESPONSE:")
    print(response)

    # ================= SUCCESS CHECK =================
    api_status = response.get("status")

    # Handle BOTH formats:
    # 1) status = 200
    # 2) status = "success"
    is_success = (
        api_status == 200 or
        api_status == "success"
    )

    # ALSO ensure data exists (safest check)
    data = response.get("data")

    if not is_success or not data:
        print("\nAPI BUSINESS ERROR:")
        print(response.get("message"))
        return None, None

    # ================= SAFE DATA EXTRACTION =================
    olnc_slno = data.get("olncSlno")
    chksts = data.get("CHKSTS")

    return olnc_slno, chksts


# ================= MAIN =================
if __name__ == "__main__":

    try:
        initial_token = get_initial_token()
        jwt = get_jwt_token(initial_token)

        olnc_slno, chksts = fetch_required_fields(jwt)

        print("\n===== FINAL OUTPUT =====")

        if olnc_slno is None:
            print("No valid data returned from API.")
        else:
            print("olncSlno:", olnc_slno)
            print("CHKSTS:", chksts)

    except requests.exceptions.RequestException as e:
        print("\nHTTP ERROR:", str(e))

    except Exception as e:
        print("\nERROR:", str(e))