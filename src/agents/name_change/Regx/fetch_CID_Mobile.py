import requests

# ================= CONFIG =================
BASE_URL = "https://dice-uat.cesc.co.in"
COMP_SRC = "whatsapp"
MOBILE_NO = "9163361930"

INITIAL_TOKEN_URL = f"{BASE_URL}/dicekey/botKeyStore.txt"
JWT_URL = f"{BASE_URL}/api/getSecretKey"

CHK_CONSUMER_URL = f"{BASE_URL}/api/chkconsumer"
CONSUMER_DETAILS_URL = f"{BASE_URL}/api/consumerDetails"

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}


# ================= AUTH =================
def get_initial_token():
    r = requests.get(INITIAL_TOKEN_URL, headers={"User-Agent": "Mozilla/5.0"})
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
    return COMMON_HEADERS | {"Authorization": f"Bearer {jwt}"}


# ================= HELPERS =================
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

    return ", ".join(x.strip() for x in fields if x)


# ================= API CALLS =================
def fetch_customer_ids(jwt):

    payload = {
        "mobile": MOBILE_NO,
        "comp_src": COMP_SRC
    }

    r = requests.post(
        CHK_CONSUMER_URL,
        headers=auth_headers(jwt),
        json=payload
    )
    r.raise_for_status()

    data = r.json()

    return (
        data.get("data", {})
        .get("LT", {})
        .get("customer_id", [])
    )


def fetch_consumer_details(jwt, cid):

    payload = {
        "mobile": MOBILE_NO,
        "custid": cid,
        "comp_src": COMP_SRC
    }

    r = requests.post(
        CONSUMER_DETAILS_URL,
        headers=auth_headers(jwt),
        json=payload
    )
    r.raise_for_status()

    data = r.json()

    address = extract_address(data)
    return address


# ================= MAIN =================
if __name__ == "__main__":

    jwt = get_jwt_token(get_initial_token())
    cids = fetch_customer_ids(jwt)

    for i, cid in enumerate(cids, start=1):
        address = fetch_consumer_details(jwt, cid)
        print(f"{i}. CID {cid} — {address}")
