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
EMERGENCY_URL = f"{BASE_URL}/api/genEmergencyCrmDkt"

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}

# =========================
# HELPERS
# =========================

# def get_param(event, name):
#     for param in event.get("parameters", []):
#         if param.get("name") == name:
#             return param.get("value")
#     return None


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
# API CALLS
# =========================

def raise_emergency_complaint(jwt, mobile, comp_code, address, remark):

    payload = {"custid": "",
                "mobile": mobile,
                "comp": comp_code,    
                "comp_src": "whatsapp",
                "add": address,
                "remark": remark
            }

    r = requests.post(
        EMERGENCY_URL,
        headers=auth_headers(jwt),
        json=payload,
        timeout=10
    )
    r.raise_for_status()

    data = safe_json(r)
    
    print(data)

    return data


# =========================
# LAMBDA HANDLER
# =========================

def lambda_handler(event, context):

    logger.info("EVENT RECEIVED: %s", json.dumps(event))

    body_text = ""

    try:
        action_group = event.get('actionGroup', 'defaultActionGrp')
        function = event.get('function', 'default')
        message_version = event.get('messageVersion',1)
        parameters = event.get('parameters', [])

        # Execute your business logic here. For more information, 
        # refer to: https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html

        param_dict = {param['name'].lower(): str(param['value']) for param in parameters}
        print(f"Param Dict : {param_dict}")
        print(function)

        # Get the values from the event stack from agent.
        mobile = param_dict.get('mobile', '')
        comp_code = param_dict.get('comp_code', '')
        address = param_dict.get('address', '')
        remark = param_dict.get('remark', "Please respond ASAP.")
        
        print(mobile, comp_code, address, remark)

        # Performing regex in mobile number.
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

            # 📡 Register the emergency response.
            response = raise_emergency_complaint(jwt, mobile, comp_code, address, remark)

            if (response.get('status') == 'success'):
                body_text = "Your Emergency Complain has been registered with us, we will send field support immediately."
            
            else:
                body_text = "Emergency complain generation failed."

           
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
