import requests
import json

# ============================================
# CONFIGURATION
# ============================================

# URLs
INITIAL_TOKEN_URL = "https://dice-uat.cesc.co.in/dicekey/botKeyStore.txt"
JWT_TOKEN_URL = "https://dice-uat.cesc.co.in/api/getSecretKey"
PAYMENT_API_URL = "https://extsrv.cesc.co.in/kb81siB3e/h6Hfy27GGy/dev_uat.php"

# ============================================
# STEP 1: Get Initial Token
# ============================================

def get_initial_token():
    response = requests.get(INITIAL_TOKEN_URL)
    response.raise_for_status()
    return response.text.strip()


# ============================================
# STEP 2: Get JWT Access Token
# ============================================

def get_jwt_token(client_token):
    payload = {
        "client_token_vl": client_token
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(JWT_TOKEN_URL, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()["access_token"]


# ============================================
# STEP 3: Call Payment API
# ============================================

def call_payment_api(access_token):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Example: Monthly Bill
    payload = {
        "param_1": "11001202551",   # Customer ID (11 digit)
        "param_2": "200",              # Not required for Monthly
        "param_3": "3",             # Bill Type = 1 (Monthly)
        "param_4": "10.50.81.31",   # External platform IP
        "param_5": "9163361930",    # Mobile number
        "param_6": "3",             # Source = 3 (WhatsApp)
        "param_7": "",
        "param_8": "",
        "param_9": ""
    }

    response = requests.post(PAYMENT_API_URL, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()


# ============================================
# MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    try:
        print("Fetching initial token...")
        client_token = get_initial_token()
        print("Initial Token:", client_token)

        print("\nGenerating JWT token...")
        access_token = get_jwt_token(client_token)
        print("Access Token:", access_token)

        print("\nCalling Payment API...")
        api_response = call_payment_api(access_token)

        print("\nAPI Response:")
        print(json.dumps(api_response, indent=4))

    except Exception as e:
        print("Error occurred:", str(e))
