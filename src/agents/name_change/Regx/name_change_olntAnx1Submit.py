import requests
import json

BASE_URL = "https://dice-uat.cesc.co.in"

INITIAL_TOKEN_URL = f"{BASE_URL}/dicekey/botKeyStore.txt"
JWT_URL = f"{BASE_URL}/api/getSecretKey"
SUBMIT_URL = f"{BASE_URL}/api/olntAnx1Submit"

FILE_PATH = "aadhaar.pdf"

# ---- VALUES FROM olntAnx1 API ----
CUST_ID = "59000520629"
CONS_ID = "5900052062"
APPLNREFNO = "10211"


def get_initial_token():
    r = requests.get(INITIAL_TOKEN_URL,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text.strip()


def get_jwt(token):
    r = requests.post(
        JWT_URL,
        json={"client_token_vl": token},
        headers={"Content-Type": "application/json"}
    )
    r.raise_for_status()
    return r.json()["access_token"]


def submit(jwt):

    headers = {
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    # EXACT multipart payload
    data = [
        ("cust_id", CUST_ID),
        ("consid", CONS_ID),
        ("applnrefno", APPLNREFNO),
        ("name", "TEST Name"),
        ("flat_no", "f1"),
        ("floor_no", "fl1"),
        ("block_no", "bl"),
        ("street", "street"),
        ("city", "city"),
        ("pincode", "711106"),
        ("mail", "eamiOfNew@gmail.com"),
        ("mobile", "9999999999"),
        ("dob", "1201"),
        ("transfer_sts", "A"),
        ("prop_sd_amt", "1000"),
        ("a1app_uid_type", "ADHAR"),
        ("anx_wt1_name", "a1w1n1"),
        ("anx_wt1_add", "a1w1add1"),
        ("anx_wt2_name", "a1w1n2"),
        ("anx_wt2_add", "a1w1add2"),
        ("comp_src", "whatsapp"),
    ]

    with open(FILE_PATH, "rb") as f:
        files = [
            ("a1app_uid_file", ("aadhaar.pdf", f, "application/pdf"))
        ]

        r = requests.post(
            SUBMIT_URL,
            headers=headers,
            data=data,
            files=files
        )

    print("\nHTTP:", r.status_code)
    print(r.text)


if __name__ == "__main__":
    jwt = get_jwt(get_initial_token())
    submit(jwt)