import json
import urllib.request
import time
import boto3
from typing import Dict, Any, Optional, List
from datetime import datetime

# ---------------------------------------------------------------------------
# API Configuration — DICE UAT Server
# ---------------------------------------------------------------------------
BASE_URL                 = "https://dice-uat.cesc.co.in"
BOT_KEY_URL              = f"{BASE_URL}/dicekey/botKeyStore.txt"
SECRET_KEY_URL           = f"{BASE_URL}/api/getSecretKey"
GEN_DOCKET_URL           = f"{BASE_URL}/api/genSupplyCrmDkt"
STATUS_URL               = f"{BASE_URL}/api/getComplaintStatus"
GEN_EMERGENCY_DOCKET_URL = f"{BASE_URL}/api/genEmergencyCrmDkt"
CONSUMER_DETAILS_URL     = f"{BASE_URL}/api/consumerDetails"        # NEW
BURNT_METER_DETAILS_URL  = f"{BASE_URL}/api/BurntMeterDetails"      # NEW
CHK_CONSUMER_URL         = f"{BASE_URL}/api/chkconsumer"             # NEW — mobile-to-CID lookup
GEN_HT_DOCKET_URL        = f"{BASE_URL}/api/genHtSupplyCrmDkt"       # NEW — HT supply off docket
HT_DOCKET_STATUS_URL         = f"{BASE_URL}/api/getHTComplaintStatus"     # NEW — HT docket status
POWER_THEFT_MAJOR_AREA_URL   = f"{BASE_URL}/api/powerTheftMajorArea"          # NEW — theft area list
POWER_THEFT_POLICE_LIST_URL  = f"{BASE_URL}/api/powerTheftPoliceStationList"  # NEW — police station list
POWER_THEFT_DOCKET_DTLS_URL  = f"{BASE_URL}/api/powerTheftDocketDetails"      # NEW — theft docket details
SAVE_POWER_THEFT_URL         = f"{BASE_URL}/api/savePowerTheft"               # NEW — save theft complaint (multipart)
GET_COMPLAINT_OP_URL         = f"{BASE_URL}/api/getComplaintOp"             # complaint nature list (opt=2 for supply)
INSERT_COMPLAINT_URL         = f"{BASE_URL}/api/insertComplaintData"        # raise docket for all 8 supply complaint types

# S3 bucket used for image downloads during Bedrock console testing.
# In production this bucket also receives WhatsApp media uploaded by the webhook.
S3_IMAGE_BUCKET = "cesc-whatsapp-media"    # CHANGE to your actual bucket name
SOURCE_NAME              = "whatsapp"

# ---------------------------------------------------------------------------
# Amazon Bedrock — Intent Classification
# ---------------------------------------------------------------------------
BEDROCK_REGION            = "ap-south-1"                                 # Mumbai — change if needed
INTENT_MODEL_ID           = "anthropic.claude-3-sonnet-20240229-v1:0"   # Claude 3 Sonnet
INTENT_MAX_TOKENS         = 512                                           # small — only returns JSON
_bedrock_client           = None                                          # module-level cache

# All 8 complaint types from the flow diagram (step 4)
COMPLAINT_TYPES = {
    "TYPE_1":  {
        "label":       "Pending repair after temporary restoration",
        "description": "User had power restored temporarily but the permanent fix is pending",
        "keywords":    ["temporary restoration", "temp restore", "not permanently fixed",
                        "still pending", "temporary supply", "sাময়িক সংযোগ"]
    },
    "TYPE_2":  {
        "label":       "Faulty equipment supply issue",
        "description": "Transformer, cable, or other equipment is faulty causing supply issues",
        "keywords":    ["transformer", "cable fault", "equipment", "faulty", "ট্রান্সফর্মার"]
    },
    "TYPE_3":  {
        "label":       "Electricity theft",
        "description": "User is reporting someone stealing electricity, illegal connection, meter tampering, or hooking",
        "keywords":    ["theft", "steal", "illegal connection", "hook", "bypass meter",
                        "tamper", "চুরি", "বিদ্যুৎ চুরি", "অবৈধ সংযোগ", "হুক", "মিটার টেম্পার"]
    },
    "TYPE_4":  {
        "label":       "Meter board renovation",
        "description": "Meter board needs repair, replacement, or renovation",
        "keywords":    ["meter board", "board renovation", "meterboard", "মিটার বোর্ড"]
    },
    "TYPE_5":  {
        "label":       "Live wires in reachable distance",
        "description": "Dangerous live/exposed wires hanging low or within reach of people",
        "keywords":    ["live wire", "exposed wire", "hanging wire", "low wire", "wire touching",
                        "তার ঝুলছে", "ঝুলন্ত তার", "বিপজ্জনক তার"]
    },
    "TYPE_6":  {
        "label":       "Damaged pole near premises",
        "description": "Electric pole near the user premises is damaged, leaning, or broken",
        "keywords":    ["damaged pole", "broken pole", "leaning pole", "pole fell",
                        "খুঁটি ভাঙা", "খুঁটি হেলে", "পোল ক্ষতিগ্রস্ত"]
    },
    "TYPE_7":  {
        "label":       "Street lighting complaint",
        "description": "Street light is not working, damaged, or always on",
        "keywords":    ["street light", "streetlight", "road light", "lamp post",
                        "street lamp", "পথ বাতি", "রাস্তার বাতি", "স্ট্রিট লাইট"]
    },
    "TYPE_8":  {
        "label":       "Other supply related issue",
        "description": "Any other electricity supply related complaint not covered above",
        "keywords":    ["supply issue", "no power", "power cut", "outage", "load shedding",
                        "বিদ্যুৎ নেই", "কারেন্ট নেই", "লোডশেডিং"]
    },
    "UNKNOWN": {
        "label":       "Unable to determine complaint type",
        "description": "The message does not clearly indicate a supply complaint type",
        "keywords":    []
    }
}

# ---------------------------------------------------------------------------
# Consumer type detection helpers
# ---------------------------------------------------------------------------
HT_CONSUMER_PREFIX = "010"   # All HT Consumer Numbers start with 010

# Module-level JWT cache — reused across warm Lambda invocations.
# JWT expires in 1800s (30 min); we refresh 60s early to be safe.
_cached_token: Optional[str] = None
_token_expiry: float = 0.0

# Emergency complaint codes and descriptions
EMERGENCY_COMPLAINT_CODES = {
    "6":  {"desc": "Meter Burnt",                   "urgency": "Emergency"},
    "7":  {"desc": "Fire / Smoke / Spark",           "urgency": "Emergency"},
    "8":  {"desc": "Electrical Accident",            "urgency": "Extreme Emergency"},
    "9":  {"desc": "Public Disturbance",             "urgency": "Emergency"},
    "11": {"desc": "Pillar Box Open",                "urgency": "Extreme Emergency"},
    "12": {"desc": "Danger Of Electrical Accident",  "urgency": "Extreme Emergency"},
    "16": {"desc": "Pole Corroded & may Fall",       "urgency": "Emergency"},
    "18": {"desc": "Call from Exam Center",          "urgency": "Extreme Emergency"},
}

# ---------------------------------------------------------------------------
# JWT Authentication
# ---------------------------------------------------------------------------

def get_jwt_token() -> str:
    """
    Two-step auth flow with module-level caching:
      1. Return cached token if still valid (reuses warm Lambda container).
      2. Fetch fresh bot token from botKeyStore.txt (plain text GET).
      3. POST it to /api/getSecretKey to receive a Bearer JWT (valid 30 min).
    """
    global _cached_token, _token_expiry

    # Return cached token if it won't expire in the next 60 seconds
    if _cached_token and time.time() < (_token_expiry - 60):
        print("[INFO] Using cached JWT token")
        return _cached_token

    # Step 1: fetch initial bot token (plain text, short timeout)
    req = urllib.request.Request(BOT_KEY_URL, method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        client_token = resp.read().decode("utf-8").strip()

    if not client_token:
        raise Exception("Failed to retrieve bot token from botKeyStore.txt")

    print(f"[INFO] Fetched client token: {client_token[:10]}...")

    # Step 2: exchange for JWT (short timeout)
    payload = json.dumps({"client_token_vl": client_token}).encode("utf-8")
    req = urllib.request.Request(
        SECRET_KEY_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    access_token = data.get("access_token")
    expires_in   = data.get("expires_in", 1800)  # default 30 min per spec

    if not access_token:
        raise Exception(f"No access_token in getSecretKey response: {data}")

    # Cache the token
    _cached_token = access_token
    _token_expiry = time.time() + expires_in

    print("[INFO] JWT token acquired and cached successfully")
    return access_token


# ---------------------------------------------------------------------------
# HTTP utilities
# ---------------------------------------------------------------------------

def bedrock_wrap(action_group: str, function_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Wraps response in Bedrock-compatible format"""
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "function": function_name,
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": json.dumps(payload)
                    }
                }
            }
        }
    }

def http_post(url: str, payload: Dict[str, Any], token: str, timeout: int = 20) -> Dict[str, Any]:
    """Makes authenticated HTTP POST request with error handling"""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        raise Exception(f"HTTP Error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"URL Error: {str(e.reason)}")
    except json.JSONDecodeError as e:
        raise Exception(f"JSON Decode Error: {str(e)}")
    except Exception as e:
        raise Exception(f"Request failed: {str(e)}")


# ---------------------------------------------------------------------------
# Main Lambda Handler
# ---------------------------------------------------------------------------

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Supply Off and SOS Emergency complaint flows.
    Routes to the appropriate handler based on the invoked function.
    """
    try:
        # Obtain a fresh JWT for this invocation
        try:
            jwt_token = get_jwt_token()
        except Exception as e:
            print(f"[ERROR] Failed to obtain JWT token: {str(e)}")
            return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
                "case_type": "AUTH_ERROR",
                "message": "Authentication failed. Please try again later.",
                "technical_error": str(e)
            })

        # Extract function and parameters
        function   = event.get('function')
        parameters = event.get('parameters', [])

        # Convert parameters to dictionary
        param_dict = {param['name'].lower(): str(param['value']) for param in parameters}

        print(f"[INFO] Function: {function}")
        print(f"[INFO] Parameters: {param_dict}")

        # Route to appropriate handler
        if function == 'SupplyOffComplaint':
            return handle_supply_off_complaint(param_dict, jwt_token)
        elif function == 'SOSEmergencyComplaint':
            return handle_sos_emergency_complaint(param_dict, jwt_token)
        elif function == 'LookupCustomerByMobile':
            return handle_lookup_customer_by_mobile(param_dict, jwt_token)
        elif function == 'HTSupplyOffComplaint':
            return handle_ht_supply_off_complaint(param_dict, jwt_token)
        elif function == 'DetectConsumerType':
            return handle_detect_consumer_type(param_dict)
        elif function == 'GetPowerTheftReferenceData':
            return handle_get_power_theft_reference_data(param_dict, jwt_token)
        elif function == 'SavePowerTheftComplaint':
            return handle_save_power_theft_complaint(param_dict, jwt_token)
        elif function == 'GetPowerTheftDocketDetails':
            return handle_get_power_theft_docket_details(param_dict, jwt_token)
        elif function == 'ResolveTheftDetails':
            return handle_resolve_theft_details(param_dict, jwt_token)
        elif function == 'GetComplaintOptions':
            return handle_get_complaint_options(param_dict, jwt_token)
        elif function == 'InsertComplaintData':
            return handle_insert_complaint_data(param_dict, jwt_token)
        elif function == 'GetConsumerDetails':
            return handle_get_consumer_details(param_dict, jwt_token)
        elif function == 'ValidateCustomerID':
            return handle_validate_customer_id(param_dict, jwt_token)
        elif function == 'DetectComplaintIntent':
            return handle_detect_complaint_intent(param_dict)
        else:
            return bedrock_wrap("SupplyOff", function, {
                "case_type": "INVALID_FUNCTION",
                "message": f"Unknown function: {function}"
            })

    except Exception as e:
        print(f"[ERROR] Lambda handler exception: {str(e)}")
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "SYSTEM_ERROR",
            "error": str(e),
            "message": "An unexpected error occurred in the system"
        })


# ---------------------------------------------------------------------------
# Complaint Intent Detection via Amazon Bedrock Claude 3 Sonnet  (Step 2-4)
# ---------------------------------------------------------------------------

def _get_bedrock_client():
    """Returns a cached boto3 Bedrock Runtime client."""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
        print(f"[INFO] Bedrock client initialised in region {BEDROCK_REGION}")
    return _bedrock_client


def _build_intent_prompt(user_message: str) -> str:
    """
    Builds a strict JSON-only classification prompt for Claude 3 Sonnet.
    Supports English, Bengali, and Hindi inputs from Kolkata consumers.
    """
    type_descriptions = "\n".join([
        f'  "{k}": "{v["label"]} — {v["description"]}"'
        for k, v in COMPLAINT_TYPES.items()
        if k != "UNKNOWN"
    ])

    prompt = (
        "You are an intent classifier for CESC (Calcutta Electric Supply Corporation) WhatsApp bot.\n"
        "A consumer has sent a message reporting an electricity-related issue.\n"
        "Your job is to classify the message into exactly ONE of the complaint types below.\n\n"
        "COMPLAINT TYPES:\n"
        + type_descriptions +
        "\n\nRULES:\n"
        "- If the message mentions someone ELSE stealing electricity, illegal wiring, meter bypass, hooking, or tampering -> always classify as TYPE_3\n"
        "- If the message is about the user's OWN power being off or fluctuating -> TYPE_8 unless more specific\n"
        "- The user may write in English, Bengali, or Hindi - understand all three\n"
        "- Return ONLY a valid JSON object, no explanation, no markdown, no extra text\n"
        "- confidence must be a float between 0.0 and 1.0\n"
        "- If confidence < 0.5, set complaint_type to UNKNOWN\n"
        "- extracted_entities should capture any names, locations, addresses, or meter numbers mentioned\n\n"
        "RESPONSE FORMAT (strict JSON only):\n"
        "{\n"
        "  \"complaint_type\": \"<TYPE_1|TYPE_2|TYPE_3|TYPE_4|TYPE_5|TYPE_6|TYPE_7|TYPE_8|UNKNOWN>\",\n"
        "  \"confidence\": <0.0-1.0>,\n"
        "  \"is_power_theft\": <true|false>,\n"
        "  \"reasoning\": \"<one sentence explaining why>\",\n"
        "  \"extracted_entities\": {\n"
        "    \"offender_name\": \"<name if mentioned or null>\",\n"
        "    \"offender_address\": \"<address/location if mentioned or null>\",\n"
        "    \"meter_no\": \"<meter number if mentioned or null>\",\n"
        "    \"area\": \"<area/locality if mentioned or null>\",\n"
        "    \"police_station\": \"<police station if mentioned or null>\",\n"
        "    \"landmark\": \"<any landmark mentioned or null>\"\n"
        "  },\n"
        "  \"follow_up_needed\": <true|false>,\n"
        "  \"follow_up_question\": \"<question to ask user if more info needed, or null>\"\n"
        "}\n\n"
        "USER MESSAGE:\n"
        + user_message +
        "\n\nRespond with JSON only:"
    )
    return prompt


def handle_detect_complaint_intent(params: Dict[str, str]) -> Dict[str, Any]:
    """
    Classifies the user's free-text message into one of the 8 complaint types
    using Claude 3 Sonnet via Amazon Bedrock Runtime.

    Required params:
        user_message  — the raw text/voice-note transcript from the user

    Optional params:
        session_id    — for logging/tracing
        language_hint — 'en', 'bn', 'hi' (informational, model handles all)

    Returns:
        complaint_type   — TYPE_1 to TYPE_8 or UNKNOWN
        is_power_theft   — boolean shortcut for the calling agent
        confidence       — 0.0–1.0
        reasoning        — one-sentence explanation
        extracted_entities — any offender/location data already in the message
        follow_up_needed — whether the agent should ask for more detail
        follow_up_question — the exact question to ask if follow_up_needed=true
        next_action      — tells the Bedrock agent exactly which Lambda function to call next
        complaint_meta   — label + description for the matched type
    """
    user_message = params.get("user_message", "").strip()

    if not user_message:
        return bedrock_wrap("IntentDetection", "DetectComplaintIntent", {
            "case_type": "VALIDATION_ERROR",
            "message":   "user_message parameter is required for intent detection."
        })

    print(f"[INFO] DetectComplaintIntent: message='{user_message[:80]}...' "
          f"session={params.get('session_id', 'N/A')}")

    # ------------------------------------------------------------------
    # Call Claude 3 Sonnet via Bedrock Runtime
    # ------------------------------------------------------------------
    try:
        client = _get_bedrock_client()
        prompt = _build_intent_prompt(user_message)

        bedrock_payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens":        INTENT_MAX_TOKENS,
            "temperature":       0.0,    # deterministic for classification
            "top_p":             1.0,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        response = client.invoke_model(
            modelId        = INTENT_MODEL_ID,
            contentType    = "application/json",
            accept         = "application/json",
            body           = json.dumps(bedrock_payload)
        )

        response_body = json.loads(response["body"].read().decode("utf-8"))
        raw_text      = response_body["content"][0]["text"].strip()

        print(f"[INFO] Bedrock raw response: {raw_text[:200]}")

    except Exception as e:
        print(f"[ERROR] Bedrock invocation failed: {e}")
        return bedrock_wrap("IntentDetection", "DetectComplaintIntent", {
            "case_type":      "BEDROCK_ERROR",
            "message":        "Intent classification service is temporarily unavailable.",
            "technical_error": str(e),
            # Graceful fallback — ask the user to describe their issue
            "follow_up_needed":   True,
            "follow_up_question": (
                "Could you please describe your issue in more detail? "
                "For example: no power, damaged pole, street light issue, "
                "meter problem, or electricity theft?"
            )
        })

    # ------------------------------------------------------------------
    # Parse the JSON response from Claude
    # ------------------------------------------------------------------
    try:
        # Strip any accidental markdown fences Claude might add
        clean = raw_text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.lower().startswith("json"):
                clean = clean[4:]
        classification = json.loads(clean.strip())

    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON parse failed on Bedrock response: {e} Raw: {raw_text[:200]}")
        return bedrock_wrap("IntentDetection", "DetectComplaintIntent", {
            "case_type":      "PARSE_ERROR",
            "message":        "Could not interpret the classification response.",
            "raw_response":   raw_text[:500],
            "follow_up_needed":   True,
            "follow_up_question": (
                "Could you tell me more about the issue? "
                "Is this about no power supply, a damaged pole, street light, "
                "meter issue, or electricity theft?"
            )
        })

    # ------------------------------------------------------------------
    # Enrich response with next-action routing instructions
    # ------------------------------------------------------------------
    complaint_type = classification.get("complaint_type", "UNKNOWN")
    confidence     = float(classification.get("confidence", 0.0))
    is_theft       = classification.get("is_power_theft", False)
    follow_up      = classification.get("follow_up_needed", False)

    # Map each complaint type to the next Lambda function the agent should call
    next_action_map = {
        "TYPE_1": {
            "function":    "SupplyOffComplaint",
            "instruction": "Collect previous temporary restoration docket, then raise supply docket with complaint_type=1"
        },
        "TYPE_2": {
            "function":    "SupplyOffComplaint",
            "instruction": "Ask user for 1-line description and optional photo, then raise supply docket with complaint_type=1"
        },
        "TYPE_3": {
            "function":    "GetPowerTheftReferenceData",
            "instruction": (
                "This is a POWER THEFT report. "
                "First call GetPowerTheftReferenceData to load area + police station lists. "
                "Then collect mandatory offender details (name, premises no, road/locality, area, police station). "
                "Caller details are optional. Image upload is optional. "
                "Finally call SavePowerTheftComplaint."
            )
        },
        "TYPE_4": {
            "function":    "SupplyOffComplaint",
            "instruction": "Ask for number of meters on board, board details and optional photo, then raise docket"
        },
        "TYPE_5": {
            "function":    "SupplyOffComplaint",
            "instruction": "Ask for 1-line description and optional photo of the live wire issue, then raise docket"
        },
        "TYPE_6": {
            "function":    "SupplyOffComplaint",
            "instruction": "Ask for 1-line description and optional photo of the damaged pole, then raise docket"
        },
        "TYPE_7": {
            "function":    "SupplyOffComplaint",
            "instruction": "Ask for lamp post number (optional), 1-line description, optional photo, then raise docket"
        },
        "TYPE_8": {
            "function":    "SupplyOffComplaint",
            "instruction": "Ask for 1-line description and optional photo, then raise supply docket"
        },
        "UNKNOWN": {
            "function":    None,
            "instruction": "Ask the user to clarify their complaint type before proceeding"
        }
    }

    next_action  = next_action_map.get(complaint_type, next_action_map["UNKNOWN"])
    complaint_meta = {
        "type_code":   complaint_type,
        "label":       COMPLAINT_TYPES.get(complaint_type, {}).get("label", "Unknown"),
        "description": COMPLAINT_TYPES.get(complaint_type, {}).get("description", "")
    }

    # If confidence is low, override next action to ask for clarification
    if confidence < 0.5:
        complaint_type = "UNKNOWN"
        follow_up      = True
        classification["follow_up_question"] = (
            classification.get("follow_up_question") or
            "Could you please describe your issue in a bit more detail? "
            "For example: is this about no power supply, electricity theft by someone, "
            "a damaged pole, street light not working, or a meter issue?"
        )

    print(f"[INFO] Intent classified: type={complaint_type}, "
          f"confidence={confidence:.2f}, is_theft={is_theft}")

    return bedrock_wrap("IntentDetection", "DetectComplaintIntent", {
        "case_type":          "INTENT_CLASSIFIED",
        "complaint_type":     complaint_type,
        "complaint_meta":     complaint_meta,
        "confidence":         confidence,
        "is_power_theft":     is_theft,
        "reasoning":          classification.get("reasoning", ""),
        "extracted_entities": classification.get("extracted_entities", {}),
        "follow_up_needed":   follow_up,
        "follow_up_question": classification.get("follow_up_question"),
        "next_action":        next_action,
        "session_id":         params.get("session_id", ""),
        "original_message":   user_message,
        "model_used":         INTENT_MODEL_ID
    })


# ---------------------------------------------------------------------------
# Consumer Type Detection  (no mobile — user gave CID or Consumer No directly)
# ---------------------------------------------------------------------------

def handle_detect_consumer_type(params: Dict[str, str]) -> Dict[str, Any]:
    """
    Determines whether a user-supplied identifier is an HT Consumer Number
    or an LT Customer ID WITHOUT making any API call.

    Rules:
      - HT Consumer Number : starts with "010"  (e.g. 01060001001)
      - LT Customer ID     : anything else       (e.g. 58000076133)

    Required params: identifier  (the raw value the user typed)
    Optional params: mobile      (if user also provided it)
    """
    identifier = params.get("identifier", "").strip()

    if not identifier:
        return bedrock_wrap("SupplyOff", "DetectConsumerType", {
            "case_type": "VALIDATION_ERROR",
            "message":   "No Customer ID or Consumer Number was provided. Please share your CID or Consumer Number."
        })

    consumer_type = _detect_consumer_type(identifier)

    print(f"[INFO] DetectConsumerType: identifier={identifier}, type={consumer_type}")

    return bedrock_wrap("SupplyOff", "DetectConsumerType", {
        "case_type":     "CONSUMER_TYPE_DETECTED",
        "identifier":    identifier,
        "consumer_type": consumer_type,
        "custid":        identifier if consumer_type == "LT" else None,
        "consumer_no":   identifier if consumer_type == "HT" else None,
        "mobile":        params.get("mobile", ""),
        "message": (
            f"Identified as {'HT Consumer Number' if consumer_type == 'HT' else 'LT Customer ID'}. "
            f"Proceeding with {'genHtSupplyCrmDkt' if consumer_type == 'HT' else 'genSupplyCrmDkt'} flow."
        ),
        "action": (
            "Call HTSupplyOffComplaint with consumer_no" if consumer_type == "HT"
            else "Call SupplyOffComplaint with custid"
        )
    })


def _detect_consumer_type(identifier: str) -> str:
    """
    Returns 'HT' if identifier starts with HT_CONSUMER_PREFIX ('010'),
    otherwise returns 'LT'.
    """
    if identifier.startswith(HT_CONSUMER_PREFIX):
        return "HT"
    return "LT"


# ---------------------------------------------------------------------------
# HT Supply Off Complaint Handler  (genHtSupplyCrmDkt + getHTComplaintStatus)
# ---------------------------------------------------------------------------

def handle_ht_supply_off_complaint(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Handles HT Supply Off complaint flow.

    genHtSupplyCrmDkt API:
      Input  : consno (HT Consumer Number), mobile, comp, comp_src, [dtl]
      Output : status="success", message="new"|"existing"|<block>,
               data.docket = docket number

    HT Consumer Numbers always start with '010'.
    Required params: consumer_no (or consno), mobile, complaint_type (comp)
    """
    try:
        # Accept both param name styles from the agent
        consumer_no = (
            params.get("consumer_no")
            or params.get("consno")
            or params.get("custid")   # fallback if agent passes custid for HT
            or ""
        ).strip()

        mobile         = params.get("mobile", "").strip()
        complaint_type = params.get("complaint_type", "").strip()

        missing = []
        if not consumer_no:
            missing.append("consumer_no")
        if not complaint_type:
            missing.append("complaint_type")

        if missing:
            return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
                "case_type": "VALIDATION_ERROR",
                "message":   f"Missing required parameters: {', '.join(missing)}"
            })

        # Confirm this is actually an HT number before calling the HT API
        if not consumer_no.startswith(HT_CONSUMER_PREFIX):
            return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
                "case_type": "INVALID_HT_CONSUMER_NO",
                "consumer_no": consumer_no,
                "message": (
                    f"Consumer Number '{consumer_no}' does not appear to be an HT Consumer Number "
                    f"(expected prefix '{HT_CONSUMER_PREFIX}'). "
                    "Please verify the number or use SupplyOffComplaint for LT consumers."
                )
            })

        print(f"[INFO] HT Supply Off: consumer_no={consumer_no}, comp={complaint_type}")

        ht_docket_payload = {
            "consno":   consumer_no,
            "mobile":   mobile,
            "comp":     complaint_type,
            "comp_src": SOURCE_NAME
        }

        if "dtl" in params:
            ht_docket_payload["dtl"] = params["dtl"]

        # Call genHtSupplyCrmDkt API
        try:
            ht_response = http_post(GEN_HT_DOCKET_URL, ht_docket_payload, token)
        except Exception as e:
            print(f"[ERROR] genHtSupplyCrmDkt API failed: {str(e)}")
            return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
                "case_type":      "SYSTEM_DOWN",
                "message":        "HT docket system is currently unavailable. Please try again later.",
                "technical_error": str(e)
            })

        if not ht_response or not isinstance(ht_response, dict):
            return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
                "case_type": "SYSTEM_DOWN",
                "message":   "Invalid response from HT docket system"
            })

        api_status = ht_response.get("status")

        if api_status != "success":
            error_msg = ht_response.get("message", "Unknown error")
            errors    = ht_response.get("errors", [])
            return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
                "case_type": "API_ERROR",
                "message":   f"HT docket generation failed: {error_msg}",
                "errors":    errors
            })

        # Same message convention as LT: "new" | "existing" | <block reason>
        api_message = ht_response.get("message", "").strip().lower()
        data        = ht_response.get("data", {})
        docket_no   = data.get("docket") or data.get("dtl")
        reason      = data.get("msg") or data.get("dtl_msg", "")

        print(f"[INFO] HT API message: {api_message}, Docket: {docket_no}, Reason: {reason}")

        if api_message == "new":
            return _handle_ht_new_docket(docket_no, consumer_no, mobile, complaint_type)

        elif api_message == "existing":
            return _handle_ht_existing_docket(docket_no, mobile, token)

        else:
            # Business rule block — reuse LT handler (same case_type taxonomy)
            return handle_business_rule_failure(api_message, reason, docket_no)

    except Exception as e:
        print(f"[ERROR] Exception in handle_ht_supply_off_complaint: {str(e)}")
        return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
            "case_type": "PROCESSING_ERROR",
            "error":     str(e),
            "message":   "An error occurred while processing your HT complaint"
        })


def _handle_ht_new_docket(docket_no: Optional[str], consumer_no: str, mobile: str, complaint_type: str) -> Dict[str, Any]:
    """Handles successful HT new docket creation."""
    if not docket_no:
        return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
            "case_type": "DOCKET_CREATION_ERROR",
            "message":   "HT docket creation reported success but docket number is missing"
        })

    print(f"[INFO] New HT docket created: {docket_no}")

    return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
        "case_type": "NEW_HT_DOCKET_CREATED",
        "docket_no": docket_no,
        "message":   f"Your HT supply off complaint has been registered. Docket number: {docket_no}",
        "details": {
            "consumer_no":    consumer_no,
            "mobile":         mobile,
            "complaint_type": complaint_type,
            "source":         SOURCE_NAME,
            "timestamp":      datetime.utcnow().isoformat() + "Z"
        },
        "next_steps": [
            "You will receive SMS confirmation shortly",
            "Field staff will be assigned to your complaint",
            "You can track the status using your docket number"
        ],
        "acknowledgment": "Thank you for reporting. We are working on restoring your HT supply."
    })


def _handle_ht_existing_docket(docket_no: Optional[str], mobile: str, token: str) -> Dict[str, Any]:
    """
    Fetches HT docket status via getHTComplaintStatus.

    API input  : { "mobile": "...", "docket": "...", "comp_src": "..." }
    API output : data.docket, data.status ("C" = complete), data.con_add
    """
    if not docket_no:
        return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
            "case_type": "INVALID_DOCKET",
            "message":   "Existing HT docket found but docket number is missing"
        })

    print(f"[INFO] Fetching HT docket status for: {docket_no}")

    try:
        status_payload = {
            "mobile":   mobile,
            "docket":   docket_no,
            "comp_src": SOURCE_NAME
        }
        status_response = http_post(HT_DOCKET_STATUS_URL, status_payload, token)
    except Exception as e:
        print(f"[ERROR] getHTComplaintStatus API failed: {str(e)}")
        return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
            "case_type": "EXISTING_HT_DOCKET_STATUS_UNAVAILABLE",
            "docket_no": docket_no,
            "message":   f"Existing HT docket {docket_no} found, but status could not be retrieved.",
            "error":     str(e)
        })

    if not status_response or status_response.get("status") != "success":
        return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", {
            "case_type": "EXISTING_HT_DOCKET_STATUS_ERROR",
            "docket_no": docket_no,
            "message":   f"Existing HT docket {docket_no} found, but status retrieval failed.",
            "api_response": status_response
        })

    status_data      = status_response.get("data", {})
    complaint_status = status_data.get("status", "Unknown")   # "C" = Completed
    con_add          = status_data.get("con_add", "")

    is_complete   = complaint_status in ["C", "COMPLETE", "COMPLETED", "CLOSED"]
    is_incomplete = complaint_status in ["I", "INCOMPLETE", "PENDING", "IN_PROGRESS"]

    result = {
        "case_type":      "EXISTING_HT_DOCKET",
        "docket_no":      docket_no,
        "status":         complaint_status,
        "consumer_address": con_add,
        "message":        f"An existing HT docket {docket_no} was found for your complaint.",
        "status_details": status_data
    }

    if is_complete:
        result["message"] = (
            f"Your previous HT docket {docket_no} has been completed. "
            f"Consumer address on record: {con_add}"
        )
    elif is_incomplete:
        result["message"] = (
            f"Your HT docket {docket_no} is currently in progress. "
            f"Consumer address on record: {con_add}"
        )

    return bedrock_wrap("SupplyOff", "HTSupplyOffComplaint", result)


# ---------------------------------------------------------------------------
# Mobile-to-CID Lookup Handler  (chkconsumer API)
# ---------------------------------------------------------------------------

def handle_lookup_customer_by_mobile(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Resolves Customer ID(s) from a mobile number via the /chkconsumer API.

    API message values:
      "single"   — exactly one mapping found (LT or HT); proceed automatically.
      "multiple" — more than one CID mapped; ask user to select.
      "nomap"    — mobile not registered; ask user to provide CID directly.

    Required params: mobile
    """
    mobile = params.get("mobile", "").strip()

    if not mobile or not mobile.isdigit() or len(mobile) != 10:
        return bedrock_wrap("SupplyOff", "LookupCustomerByMobile", {
            "case_type": "VALIDATION_ERROR",
            "message": "A valid 10-digit mobile number is required to look up your Customer ID."
        })

    print(f"[INFO] LookupCustomerByMobile: mobile={mobile}")

    try:
        chk_payload = {
            "mobile":   mobile,
            "comp_src": SOURCE_NAME
        }
        chk_response = http_post(CHK_CONSUMER_URL, chk_payload, token)
    except Exception as e:
        print(f"[ERROR] chkconsumer API failed: {str(e)}")
        return bedrock_wrap("SupplyOff", "LookupCustomerByMobile", {
            "case_type": "SYSTEM_DOWN",
            "message": "Unable to look up your Customer ID at this time. Please provide your CID directly.",
            "technical_error": str(e)
        })

    if not chk_response or chk_response.get("status") != "success":
        return bedrock_wrap("SupplyOff", "LookupCustomerByMobile", {
            "case_type": "API_ERROR",
            "message": "Customer lookup failed. Please provide your Customer ID directly.",
            "api_response": chk_response
        })

    api_message = chk_response.get("message", "").strip().lower()
    data        = chk_response.get("data", {})

    print(f"[INFO] chkconsumer response message: {api_message}")

    if api_message == "single":
        return _handle_single_cid_mapping(data, mobile)

    elif api_message == "multiple":
        return _handle_multiple_cid_mapping(data, mobile)

    elif api_message == "nomap":
        return bedrock_wrap("SupplyOff", "LookupCustomerByMobile", {
            "case_type": "NO_MAPPING_FOUND",
            "mobile":    mobile,
            "message": (
                "Your mobile number is not registered with any Customer ID in our system. "
                "Please provide your Customer ID (CID) directly to proceed."
            ),
            "action": "Ask user to provide their CID manually"
        })

    else:
        # Unexpected message value — surface raw data and ask user for CID
        print(f"[WARN] chkconsumer unexpected message value: {api_message}")
        return bedrock_wrap("SupplyOff", "LookupCustomerByMobile", {
            "case_type": "UNKNOWN_MAPPING_RESPONSE",
            "mobile":    mobile,
            "message": (
                "We could not automatically determine your Customer ID. "
                "Please provide your Customer ID (CID) directly to proceed."
            ),
            "raw_message": api_message
        })


def _handle_single_cid_mapping(data: Dict[str, Any], mobile: str) -> Dict[str, Any]:
    """
    Exactly one CID found. Determine whether it is an LT or HT consumer
    and return the resolved CID so the agent can proceed without asking the user.
    """
    lt_ids = data.get("LT", {}).get("customer_id", [])
    ht_ids = data.get("HT", {}).get("consumer_no", [])

    if lt_ids:
        custid       = lt_ids[0]
        consumer_type = "LT"
    elif ht_ids:
        custid       = ht_ids[0]
        consumer_type = "HT"
    else:
        # API said "single" but data is empty — treat as no-map
        return bedrock_wrap("SupplyOff", "LookupCustomerByMobile", {
            "case_type": "NO_MAPPING_FOUND",
            "mobile":    mobile,
            "message": (
                "Your mobile number is not linked to any Customer ID. "
                "Please provide your Customer ID (CID) directly."
            )
        })

    print(f"[INFO] Single mapping resolved: custid={custid}, type={consumer_type}")

    return bedrock_wrap("SupplyOff", "LookupCustomerByMobile", {
        "case_type":     "SINGLE_CID_FOUND",
        "mobile":        mobile,
        "custid":        custid,
        "consumer_type": consumer_type,
        "message": (
            f"Your Customer ID has been identified as {custid} ({consumer_type} consumer). "
            "Proceeding with your complaint."
        ),
        "action": "Proceed automatically with the resolved custid — do NOT ask the user to confirm"
    })


def _handle_multiple_cid_mapping(data: Dict[str, Any], mobile: str) -> Dict[str, Any]:
    """
    More than one CID found. Build a combined list of LT + HT IDs and
    return them so the agent can present a numbered choice to the user.
    The list is built ONCE here — the agent must use this exact list and
    must NOT call chkconsumer again for the same mobile.
    """
    lt_ids = data.get("LT", {}).get("customer_id", [])
    ht_ids = data.get("HT", {}).get("consumer_no", [])

    # Build a deduplicated, labelled options list
    options = []
    for cid in lt_ids:
        options.append({"custid": cid, "consumer_type": "LT"})
    for cno in ht_ids:
        options.append({"custid": cno, "consumer_type": "HT"})

    if not options:
        return bedrock_wrap("SupplyOff", "LookupCustomerByMobile", {
            "case_type": "NO_MAPPING_FOUND",
            "mobile":    mobile,
            "message": (
                "No Customer IDs could be retrieved. "
                "Please provide your Customer ID (CID) directly."
            )
        })

    print(f"[INFO] Multiple mappings found: {options}")

    return bedrock_wrap("SupplyOff", "LookupCustomerByMobile", {
        "case_type":      "MULTIPLE_CIDS_FOUND",
        "mobile":         mobile,
        "cid_options":    options,
        "total_found":    len(options),
        "message": (
            f"We found {len(options)} Customer IDs linked to your mobile number. "
            "Please select the correct one to proceed."
        ),
        "action": (
            "Present the cid_options list to the user as a numbered selection. "
            "Wait for the user's choice. Do NOT call chkconsumer again — use this cached result."
        )
    })


# ---------------------------------------------------------------------------
# Supply Off Complaint Handler
# ---------------------------------------------------------------------------

def handle_supply_off_complaint(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Handles Supply Off complaint flow starting from Step 6

    Steps covered:
    6. Previous HT Call w.r.t Consumer No. within 2 hours
    7. Same Service Incomplete Call exists within 2 hours
    8. Already existing complaint requested customer's LP no is overhead supply network area
    Then proceeds to create docket or handle existing scenarios
    """
    try:
        # Validate required parameters
        required_params = ['custid', 'mobile', 'complaint_type']
        missing_params  = [p for p in required_params if p not in params]

        if missing_params:
            return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
                "case_type": "VALIDATION_ERROR",
                "message": f"Missing required parameters: {', '.join(missing_params)}"
            })

        print(f"[INFO] Generating docket for customer: {params['custid']}")

        docket_payload = {
            "custid":   params['custid'],
            "mobile":   params["mobile"],
            "comp":     params["complaint_type"],
            "comp_src": SOURCE_NAME
        }

        if 'dtl' in params:
            docket_payload['dtl'] = params['dtl']

        # Call genSupplyCrmDkt API
        try:
            docket_response = http_post(GEN_DOCKET_URL, docket_payload, token)
        except Exception as e:
            print(f"[ERROR] API call failed: {str(e)}")
            return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
                "case_type": "SYSTEM_DOWN",
                "message": "Supply docket system is currently unavailable. Please try again later.",
                "technical_error": str(e)
            })

        if not docket_response or not isinstance(docket_response, dict):
            return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
                "case_type": "SYSTEM_DOWN",
                "message": "Invalid response from docket system"
            })

        api_status = docket_response.get("status")

        if api_status != "success":
            error_msg = docket_response.get("message", "Unknown error")
            errors    = docket_response.get("errors", [])
            return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
                "case_type": "API_ERROR",
                "message": f"Docket generation failed: {error_msg}",
                "errors": errors
            })

        # Extract data per actual API response shape:
        #   root "message": "new" | "existing" | other = business rule block
        #   data.docket = docket number
        #   data.msg    = reason text (populated on block scenarios)
        api_message = docket_response.get("message", "").strip().lower()
        data        = docket_response.get("data", {})
        docket_no   = data.get("docket") or data.get("dtl")
        reason      = data.get("msg") or data.get("dtl_msg", "")

        print(f"[INFO] API message: {api_message}, Docket: {docket_no}, Reason: {reason}")

        if api_message == "new":
            return handle_new_docket(docket_no, params)

        elif api_message == "existing":
            return handle_existing_docket(docket_no, params, token)

        else:
            # Any other message value = business rule block
            # Use the message itself as dkt_status for rule matching
            return handle_business_rule_failure(api_message, reason, docket_no, params, token)

    except Exception as e:
        print(f"[ERROR] Exception in handle_supply_off_complaint: {str(e)}")
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "PROCESSING_ERROR",
            "error": str(e),
            "message": "An error occurred while processing your complaint"
        })


def handle_business_rule_failure(dkt_status: str, reason: str, docket_no: Optional[str], params: Dict[str, str] = None, token: str = None) -> Dict[str, Any]:
    """
    Handles all 8 business rule failure scenarios (Steps 7.2.1.1 to 7.2.1.8)
    """
    print(f"[INFO] Business rule failure: {dkt_status}, Reason: {reason}")

    if dkt_status == "DUPLICATE" or "already" in reason.lower() or "exist" in reason.lower():
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "DUPLICATE_DOCKET",
            "message": "A docket already exists for the same issue",
            "reason": reason,
            "existing_docket_no": docket_no,
            "action": "User feedback will be taken with a thumbs up and thumbs down"
        })

    elif dkt_status == "LCC_DISCONNECTED" or "lcc" in reason.lower():
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "LCC_DISCONNECTED",
            "message": "Your connection is currently disconnected due to unpaid bills (LCC)",
            "reason": reason,
            "action": "Please clear outstanding dues. User is treated by making the payment if interested, redirected to human agent to share info"
        })

    elif dkt_status == "COMMERCIAL_DISCONNECTED" or "commercial" in reason.lower():
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "COMMERCIAL_DISCONNECTED",
            "message": "Your connection is commercially disconnected",
            "reason": reason,
            "action": "User is provided with commercial disconnected bill amount with link and due date of the payment"
        })

    elif dkt_status == "DTR_OUTAGE" or "dtr" in reason.lower() or "outage" in reason.lower():
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "DTR_OUTAGE",
            "message": "There is an ongoing area-wide outage affecting your connection",
            "reason": reason,
            "action": "User will be provided with the result of outage"
        })

    elif dkt_status == "BURNT_METER_PENDING" or "burnt" in reason.lower() or "meter" in reason.lower():
        # -------------------------------------------------------------------
        # Steps 7.2.1.5 → 7.2.1.5.1 → 7.2.1.5.2
        # 1. Call consumerDetails to confirm METER_BURNT flag (only for LT cases)
        # 2. If confirmed, call BurntMeterDetails to get one of 3 docket stages
        # 3. Return details + thumbs up/down feedback action
        # -------------------------------------------------------------------
        if params and token:
            return handle_burnt_meter_pending(docket_no, reason, params, token)

        # Fallback if params/token not forwarded (should not happen in normal flow)
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "BURNT_METER_PENDING",
            "message": "There is already a pending burnt meter docket for your connection",
            "reason": reason,
            "existing_docket_no": docket_no,
            "action": "Docket number and Burnt meter docket details will be shared with a thumbs up and thumbs down. User feedback will be taken for further proceedings. Allocation for preference. We request your choice for further process - any preferences"
        })

    elif dkt_status == "HT_CALL_RECENT" or "ht call" in reason.lower() or "2 hour" in reason.lower():
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "RECENT_HT_CALL",
            "message": "A recent HT call was made for your consumer number within the last 2 hours",
            "reason": reason,
            "action": "User feedback will be taken with a thumbs up and thumbs down"
        })

    elif dkt_status == "INCOMPLETE_CALL_RECENT" or "incomplete" in reason.lower() or "service" in reason.lower():
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "INCOMPLETE_RECENT_CALL",
            "message": "An incomplete call for the same service exists within the last 2 hours",
            "reason": reason,
            "action": "Reference docket number/Ref ID status will be shared and the user"
        })

    elif dkt_status == "OVERHEAD_NETWORK" or "overhead" in reason.lower() or "network area" in reason.lower():
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "OVERHEAD_NETWORK_AREA",
            "message": "Your connection is in an overhead supply network area with existing complaints",
            "reason": reason,
            "action": "Reference docket number/Ref ID and its status will be shared and the user"
        })

    else:
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "CANNOT_RAISE_DOCKET",
            "message": "Unable to raise a new docket at this time",
            "reason": reason,
            "docket_status": dkt_status
        })


# ---------------------------------------------------------------------------
# Burnt Meter Pending — Steps 7.2.1.5 → 7.2.1.5.1 → 7.2.1.5.2  (NEW)
# ---------------------------------------------------------------------------

def handle_burnt_meter_pending(docket_no: Optional[str], reason: str, params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Step 7.2.1.5: Already have pending Burnt Meter docket (only for LT cases).

    Flow:
      7.2.1.5   — Confirm METER_BURNT flag via consumerDetails API.
      7.2.1.5.1 — Using burnt meter docket, get one of 3 stages via
                  BurntMeterDetails API and share with user.
      7.2.1.5.2 — User feedback will be taken with a thumbs up and thumbs down.
    """
    custid = params.get("custid", "")
    mobile = params.get("mobile", "")

    # ------------------------------------------------------------------
    # Step 7.2.1.5 — Call consumerDetails to verify METER_BURNT status
    # ------------------------------------------------------------------
    print(f"[INFO] Burnt Meter: fetching consumerDetails for custid={custid}")

    try:
        consumer_payload = {
            "custid":   custid,
            "mobile":   mobile,
            "comp_src": SOURCE_NAME
        }
        consumer_response = http_post(CONSUMER_DETAILS_URL, consumer_payload, token)
    except Exception as e:
        print(f"[ERROR] consumerDetails API failed: {str(e)}")
        # Graceful fallback — still surface the pending burnt meter info
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "BURNT_METER_PENDING",
            "message": "There is already a pending burnt meter docket for your connection",
            "reason": reason,
            "existing_docket_no": docket_no,
            "action": "Docket number and Burnt meter docket details will be shared with a thumbs up and thumbs down. User feedback will be taken for further proceedings.",
            "consumer_details_error": str(e)
        })

    if not consumer_response or consumer_response.get("status") != "success":
        print(f"[WARN] consumerDetails returned non-success: {consumer_response}")
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "BURNT_METER_PENDING",
            "message": "There is already a pending burnt meter docket for your connection",
            "reason": reason,
            "existing_docket_no": docket_no,
            "action": "Docket number and Burnt meter docket details will be shared with a thumbs up and thumbs down. User feedback will be taken for further proceedings."
        })

    consumer_data = consumer_response.get("data", {})
    meter_burnt   = consumer_data.get("METER_BURNT", {})
    mb_status     = meter_burnt.get("status", "").lower()

    print(f"[INFO] METER_BURNT status from consumerDetails: {mb_status}")

    # If METER_BURNT flag is NOT set / not an LT burnt meter case, fall through gracefully
    if mb_status != "ok" and mb_status != "yes" and mb_status != "true":
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "BURNT_METER_PENDING",
            "message": "There is already a pending burnt meter docket for your connection",
            "reason": reason,
            "existing_docket_no": docket_no,
            "meter_burnt_status": mb_status,
            "action": "Docket number and Burnt meter docket details will be shared with a thumbs up and thumbs down. User feedback will be taken for further proceedings."
        })

    # Prefer the docket_no surfaced from consumerDetails (bill_link / reason fields)
    # if the upstream genSupplyCrmDkt call did not return one.
    burnt_docket_no = docket_no or meter_burnt.get("reason", "") or ""

    # ------------------------------------------------------------------
    # Step 7.2.1.5.1 — Call BurntMeterDetails to get one of 3 docket stages
    # ------------------------------------------------------------------
    print(f"[INFO] Burnt Meter: fetching BurntMeterDetails for docket={burnt_docket_no}")

    try:
        burnt_meter_payload = {
            "custid":     custid,
            "docket_no":  burnt_docket_no,
            "comp_src":   SOURCE_NAME
        }
        burnt_meter_response = http_post(BURNT_METER_DETAILS_URL, burnt_meter_payload, token)
    except Exception as e:
        print(f"[ERROR] BurntMeterDetails API failed: {str(e)}")
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "BURNT_METER_PENDING",
            "message": "There is already a pending burnt meter docket for your connection",
            "reason": reason,
            "existing_docket_no": burnt_docket_no,
            "meter_burnt_status": mb_status,
            "action": "Docket number and Burnt meter docket details will be shared with a thumbs up and thumbs down. User feedback will be taken for further proceedings.",
            "burnt_meter_details_error": str(e)
        })

    if not burnt_meter_response or burnt_meter_response.get("status") != "success":
        print(f"[WARN] BurntMeterDetails returned non-success: {burnt_meter_response}")
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "BURNT_METER_PENDING",
            "message": "There is already a pending burnt meter docket for your connection",
            "reason": reason,
            "existing_docket_no": burnt_docket_no,
            "meter_burnt_status": mb_status,
            "action": "Docket number and Burnt meter docket details will be shared with a thumbs up and thumbs down. User feedback will be taken for further proceedings."
        })

    bm_data        = burnt_meter_response.get("data", {})
    bm_message     = bm_data.get("message", "")   # e.g. "Rs. 1235 (OS AMT: Rs. 0 ...)"
    bm_url         = bm_data.get("url", "")        # PDF bill link
    bm_reff_id     = burnt_meter_response.get("reffid", "") or bm_data.get("reff_id", "")

    # Determine which of the 3 stages this docket is in based on available data
    burnt_meter_stage = _resolve_burnt_meter_stage(bm_data)

    print(f"[INFO] BurntMeterDetails stage={burnt_meter_stage}, reff_id={bm_reff_id}")

    # ------------------------------------------------------------------
    # Step 7.2.1.5.2 — Return details; user feedback via thumbs up/down
    # ------------------------------------------------------------------
    return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
        "case_type":           "BURNT_METER_PENDING",
        "existing_docket_no":  burnt_docket_no,
        "reff_id":             bm_reff_id,
        "meter_burnt_status":  mb_status,
        "burnt_meter_stage":   burnt_meter_stage,
        "burnt_meter_message": bm_message,
        "burnt_meter_bill_url": bm_url,
        "reason":              reason,
        "message": (
            f"There is already a pending burnt meter docket ({burnt_docket_no}) for your connection. "
            f"Stage: {burnt_meter_stage}. {bm_message}"
        ),
        "action": (
            "Docket number and Burnt meter docket details have been shared. "
            "User feedback will be taken with a thumbs up and thumbs down. "
            "We request your choice for further process - any preferences."
        )
    })


def _resolve_burnt_meter_stage(bm_data: Dict[str, Any]) -> str:
    """
    Determines which of the 3 burnt meter docket stages applies
    based on the BurntMeterDetails API response payload.

    Stage 1 — Bill raised, pending payment  : message present, url present
    Stage 2 — Payment done, meter not replaced yet : message present, url empty/absent
    Stage 3 — Meter replaced / work completed : no message, no url (or explicit completion flag)
    """
    bm_message = bm_data.get("message", "").strip()
    bm_url     = bm_data.get("url", "").strip()

    if bm_message and bm_url:
        return "Stage 1 - Bill raised, pending payment"
    elif bm_message and not bm_url:
        return "Stage 2 - Payment received, meter replacement pending"
    else:
        return "Stage 3 - Meter replaced / work completed"


def handle_existing_docket(docket_no: str, params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Handles existing docket scenario (Step 7.2.1.3.1).
    Fetches status and provides details to user.

    New API input:  { "docket": "<no>", "mobile": "...", "comp_src": "..." }
    New API output: data.docket, data.status, data.vehicle_location { vno, record_time, latitude, longitude }
    """
    if not docket_no:
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "INVALID_DOCKET",
            "message": "Existing docket found but docket number is missing"
        })

    print(f"[INFO] Fetching status for existing docket: {docket_no}")

    try:
        status_payload = {
            "docket":   docket_no,          # field name per new API spec
            "mobile":   params.get("mobile", ""),
            "comp_src": SOURCE_NAME
        }
        status_response = http_post(STATUS_URL, status_payload, token)

    except Exception as e:
        print(f"[ERROR] Failed to fetch docket status: {str(e)}")
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "EXISTING_DOCKET_STATUS_UNAVAILABLE",
            "docket_no": docket_no,
            "message": f"An existing docket {docket_no} was found, but status could not be retrieved",
            "error": str(e)
        })

    if not status_response or status_response.get("status") != "success":
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "EXISTING_DOCKET_STATUS_ERROR",
            "docket_no": docket_no,
            "message": f"Existing docket {docket_no} found, but status retrieval failed",
            "api_response": status_response
        })

    status_data      = status_response.get("data", {})
    complaint_status = status_data.get("status", "Unknown")
    vehicle_location = status_data.get("vehicle_location")

    is_incomplete = complaint_status in ["I", "INCOMPLETE", "PENDING", "IN_PROGRESS"]
    is_complete   = complaint_status in ["C", "COMPLETE", "COMPLETED", "CLOSED"]

    result = {
        "case_type":      "EXISTING_DOCKET",
        "docket_no":      docket_no,
        "status":         complaint_status,
        "message":        f"A docket already exists for your complaint: {docket_no}",
        "status_details": status_data
    }

    if is_incomplete and vehicle_location:
        result["vehicle_info"] = {
            "vehicle_no":   vehicle_location.get("vno"),
            "last_updated": vehicle_location.get("record_time"),
            "latitude":     vehicle_location.get("latitude"),
            "longitude":    vehicle_location.get("longitude")
        }
        result["message"] = f"Your docket {docket_no} is in progress. Field staff have been assigned."

    elif is_complete:
        result["message"] = f"Your previous docket {docket_no} has been completed."

    return bedrock_wrap("SupplyOff", "SupplyOffComplaint", result)


def handle_new_docket(docket_no: str, params: Dict[str, str]) -> Dict[str, Any]:
    """Handles new docket creation success (Step 7.1.4)"""
    if not docket_no:
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "DOCKET_CREATION_ERROR",
            "message": "Docket creation reported success but docket number is missing"
        })

    print(f"[INFO] New docket created successfully: {docket_no}")

    result = {
        "case_type": "NEW_DOCKET_CREATED",
        "docket_no": docket_no,
        "message":   f"Your complaint has been registered successfully. Docket number: {docket_no}",
        "details": {
            "customer_id":    params.get("custid"),
            "mobile":         params.get("mobile"),
            "complaint_type": params.get("complaint_type"),
            "source":         SOURCE_NAME,
            "timestamp":      datetime.utcnow().isoformat() + "Z"
        },
        "next_steps": [
            "You will receive SMS and email confirmation shortly",
            "Field staff will be assigned to your complaint",
            "You can track the status using your docket number"
        ],
        "acknowledgment": "Thank you for reporting. We are working on restoring your power supply.",
        "contact_info": {
            "whatsapp_available": True,
            "message": "For any queries, please contact us on WhatsApp"
        }
    }

    return bedrock_wrap("SupplyOff", "SupplyOffComplaint", result)


# ---------------------------------------------------------------------------
# SOS Emergency Complaint Handler
# ---------------------------------------------------------------------------

def handle_sos_emergency_complaint(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Handles SOS Emergency complaint flow via genEmergencyCrmDkt API.

    Supported complaint codes (comp):
        6  - Meter Burnt                     (Emergency)
        7  - Fire / Smoke / Spark            (Emergency)
        8  - Electrical Accident             (Extreme Emergency)
        9  - Public Disturbance              (Emergency)
        11 - Pillar Box Open                 (Extreme Emergency)
        12 - Danger Of Electrical Accident   (Extreme Emergency)
        16 - Pole Corroded & may Fall        (Emergency)
        18 - Call from Exam Center           (Extreme Emergency)

    Required params: custid, mobile, comp
    Optional params: add (address), remark
    """
    try:
        required_params = ['custid', 'mobile', 'comp']
        missing_params  = [p for p in required_params if p not in params]

        if missing_params:
            return bedrock_wrap("SOS", "SOSEmergencyComplaint", {
                "case_type": "VALIDATION_ERROR",
                "message": f"Missing required parameters: {', '.join(missing_params)}"
            })

        comp_code = params['comp']
        if comp_code not in EMERGENCY_COMPLAINT_CODES:
            return bedrock_wrap("SOS", "SOSEmergencyComplaint", {
                "case_type": "INVALID_COMPLAINT_CODE",
                "message": f"Complaint code '{comp_code}' is not a valid SOS emergency complaint code.",
                "valid_codes": EMERGENCY_COMPLAINT_CODES
            })

        comp_info = EMERGENCY_COMPLAINT_CODES[comp_code]
        print(f"[INFO] SOS Emergency - Customer: {params['custid']}, "
              f"Complaint: {comp_info['desc']} ({comp_info['urgency']})")

        emergency_payload = {
            "custid":   params['custid'],
            "mobile":   params['mobile'],
            "comp":     comp_code,
            "comp_src": SOURCE_NAME
        }

        if 'add' in params:
            emergency_payload['add'] = params['add']
        if 'remark' in params:
            emergency_payload['remark'] = params['remark']

        # Call genEmergencyCrmDkt API
        try:
            emergency_response = http_post(GEN_EMERGENCY_DOCKET_URL, emergency_payload, token)
        except Exception as e:
            print(f"[ERROR] SOS API call failed: {str(e)}")
            return bedrock_wrap("SOS", "SOSEmergencyComplaint", {
                "case_type": "SYSTEM_DOWN",
                "message": "Emergency docket system is currently unavailable. Please call emergency services directly.",
                "technical_error": str(e)
            })

        if not emergency_response or not isinstance(emergency_response, dict):
            return bedrock_wrap("SOS", "SOSEmergencyComplaint", {
                "case_type": "SYSTEM_DOWN",
                "message": "Invalid response from emergency docket system"
            })

        api_status = emergency_response.get("status")

        if api_status != "success":
            error_msg = emergency_response.get("message", "Unknown error")
            errors    = emergency_response.get("errors", [])
            return bedrock_wrap("SOS", "SOSEmergencyComplaint", {
                "case_type": "API_ERROR",
                "message": f"Emergency docket generation failed: {error_msg}",
                "errors": errors
            })

        # New API returns reff_id inside data{} and also reffid at root level
        data    = emergency_response.get("data", {})
        reff_id = data.get("reff_id") or emergency_response.get("reffid")

        print(f"[INFO] SOS Emergency docket created - reff_id: {reff_id}")

        return handle_new_emergency_docket(reff_id, comp_info, params)

    except Exception as e:
        print(f"[ERROR] Exception in handle_sos_emergency_complaint: {str(e)}")
        return bedrock_wrap("SOS", "SOSEmergencyComplaint", {
            "case_type": "PROCESSING_ERROR",
            "error": str(e),
            "message": "An error occurred while processing your emergency complaint"
        })


def handle_new_emergency_docket(reff_id: Optional[str], comp_info: Dict[str, str], params: Dict[str, str]) -> Dict[str, Any]:
    """Handles successful SOS emergency docket creation."""
    if not reff_id:
        return bedrock_wrap("SOS", "SOSEmergencyComplaint", {
            "case_type": "EMERGENCY_DOCKET_CREATION_ERROR",
            "message": "Emergency docket creation reported success but reference ID is missing"
        })

    print(f"[INFO] New SOS emergency docket created successfully: {reff_id}")

    result = {
        "case_type":             "EMERGENCY_DOCKET_CREATED",
        "reff_id":               reff_id,
        "urgency":               comp_info["urgency"],
        "complaint_description": comp_info["desc"],
        "message": (
            f"Your SOS emergency complaint has been registered. "
            f"Reference ID: {reff_id}. "
            f"Urgency level: {comp_info['urgency']}."
        ),
        "details": {
            "customer_id":    params.get("custid"),
            "mobile":         params.get("mobile"),
            "complaint_code": params.get("comp"),
            "address":        params.get("add", ""),
            "remark":         params.get("remark", ""),
            "source":         SOURCE_NAME,
            "timestamp":      datetime.utcnow().isoformat() + "Z"
        },
        "next_steps": [
            "Emergency response team has been notified",
            "You will receive an SMS confirmation shortly",
            "Please keep the area clear until help arrives",
            "You can track the status using your reference ID"
        ],
        "acknowledgment": (
            "Thank you for alerting us. Our emergency team is being dispatched immediately. "
            "Please stay safe."
        ),
        "contact_info": {
            "whatsapp_available": True,
            "message": "For urgent follow-up, please contact us on WhatsApp with your Reference ID"
        }
    }

    return bedrock_wrap("SOS", "SOSEmergencyComplaint", result)


# ---------------------------------------------------------------------------
# Power Theft — Reference Data  (Steps 5 → 5.1 → 5.2 → 5.3 from flow diagram)
# ---------------------------------------------------------------------------

def handle_get_power_theft_reference_data(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Fetches both the Theft Major Area list and Police Station list in one call
    so the Bedrock agent can present them to the user for selection and then
    fuzzy-match free-text input from the user's message against real API values.

    Steps covered:
      5.1  — Collect offender details from user.
      API  — powerTheftMajorArea   : returns [{area_id, theft_area}, ...]
      API  — powerTheftPoliceStationList : returns [{stncd, stndesc}, ...]

    No required params — both APIs only need comp_src.
    """
    print("[INFO] Fetching power theft reference data (areas + police stations)")

    areas_result   = _fetch_theft_major_areas(token)
    police_result  = _fetch_theft_police_stations(token)

    areas_ok   = areas_result.get("status") == "success"
    police_ok  = police_result.get("status") == "success"

    return bedrock_wrap("PowerTheft", "GetPowerTheftReferenceData", {
        "case_type":       "REFERENCE_DATA_FETCHED",
        "major_areas":     areas_result.get("data", [])   if areas_ok  else [],
        "police_stations": police_result.get("data", [])  if police_ok else [],
        "areas_error":     areas_result.get("error")      if not areas_ok  else None,
        "police_error":    police_result.get("error")     if not police_ok else None,
        "message": (
            "Reference data loaded. Use major_areas to match the theft area and "
            "police_stations to match the police station from the user's free text. "
            "Match case-insensitively using partial/fuzzy matching. "
            "If no match found, ask the user to select from the list."
        ),
        "matching_instruction": (
            "To resolve area_id: compare user text against theft_area values. "
            "To resolve police stncd: compare user text against stndesc values. "
            "Always confirm the matched value with the user before calling SavePowerTheftComplaint."
        )
    })


def _fetch_theft_major_areas(token: str) -> Dict[str, Any]:
    """Calls powerTheftMajorArea and returns normalised result."""
    try:
        resp = http_post(POWER_THEFT_MAJOR_AREA_URL, {"comp_src": SOURCE_NAME}, token)
        if resp and resp.get("status") == "success":
            return {"status": "success", "data": resp.get("data", [])}
        return {"status": "error", "error": resp.get("message", "Unknown error"), "data": []}
    except Exception as e:
        print(f"[ERROR] powerTheftMajorArea failed: {e}")
        return {"status": "error", "error": str(e), "data": []}


def _fetch_theft_police_stations(token: str) -> Dict[str, Any]:
    """Calls powerTheftPoliceStationList and returns normalised result."""
    try:
        resp = http_post(POWER_THEFT_POLICE_LIST_URL, {"comp_src": SOURCE_NAME}, token)
        if resp and resp.get("status") == "success":
            return {"status": "success", "data": resp.get("data", [])}
        return {"status": "error", "error": resp.get("message", "Unknown error"), "data": []}
    except Exception as e:
        print(f"[ERROR] powerTheftPoliceStationList failed: {e}")
        return {"status": "error", "error": str(e), "data": []}


def fuzzy_match_area(user_text: str, areas: list) -> Optional[Dict[str, Any]]:
    """
    Case-insensitive substring match of user_text against theft_area values.
    Returns the best matching area dict {area_id, theft_area} or None.
    """
    user_lower = user_text.lower().strip()
    for area in areas:
        if user_lower in area.get("theft_area", "").lower():
            return area
    # Try reverse — area name substring in user text
    for area in areas:
        if area.get("theft_area", "").lower() in user_lower:
            return area
    return None


def fuzzy_match_police_station(user_text: str, stations: list) -> Optional[Dict[str, Any]]:
    """
    Case-insensitive substring match of user_text against stndesc values.
    Returns the best matching station dict {stncd, stndesc} or None.
    """
    user_lower = user_text.lower().strip()
    for stn in stations:
        if user_lower in stn.get("stndesc", "").lower():
            return stn
    for stn in stations:
        if stn.get("stndesc", "").lower() in user_lower:
            return stn
    return None


# ---------------------------------------------------------------------------
# CID Validation — /api/consumerDetails (step 7.2 in flow diagram)
# Format check first, then API call to confirm CID exists in CESC database
# ---------------------------------------------------------------------------

def handle_validate_customer_id(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Validates a Customer ID (LT) or Consumer Number (HT) via consumerDetails API.
    Called at step 7.2 — before entering any complaint flow.

    Validation is two-stage:
      Stage 1 — Format check (no API call):
        LT CID       : 11 digits, numeric
        HT Cons No.  : starts with "010", numeric

      Stage 2 — API call to consumerDetails:
        Passes custid (mobile is optional/not required for validation).
        success + data present → VALID
        error or empty data   → INVALID

    Retry tracking:
        Pass attempt_number (1, 2, 3) so the agent knows when to escalate.
        On attempt 3 failure → case_type = ESCALATE_TO_HUMAN

    Required params:
        custid         — CID or Consumer Number provided by user

    Optional params:
        mobile         — mobile number if available (not required for validation)
        attempt_number — current attempt count (1, 2, or 3). Default 1.
    """
    custid         = params.get("custid", "").strip()
    mobile         = params.get("mobile", "").strip()
    attempt_number = int(params.get("attempt_number", "1").strip() or "1")

    # Clamp attempt between 1 and 3
    attempt_number = max(1, min(3, attempt_number))

    # ------------------------------------------------------------------
    # Stage 1 — Format validation (no API call needed)
    # ------------------------------------------------------------------
    if not custid:
        return bedrock_wrap("Validation", "ValidateCustomerID", {
            "case_type":      "FORMAT_INVALID",
            "valid":          False,
            "custid":         custid,
            "attempt_number": attempt_number,
            "attempts_left":  3 - attempt_number,
            "message":        "No Customer ID provided. Please ask the user for their 11-digit Customer ID or Consumer Number.",
            "retry_prompt":   "Could you please provide your 11-digit Customer ID or Consumer Number?"
        })

    # Remove spaces/dashes if user typed them
    custid_clean = custid.replace(" ", "").replace("-", "")

    # Check numeric
    if not custid_clean.isdigit():
        return _invalid_cid_response(custid, attempt_number,
            "Customer ID must contain digits only. Please ask the user to re-enter.")

    # Any 11-digit number is a valid LT Customer ID
    # HT Consumer Numbers specifically start with 010
    # Both are exactly 11 digits
    is_ht = custid_clean.startswith("010")

    if len(custid_clean) != 11:
        return _invalid_cid_response(custid, attempt_number,
            f"Customer ID and Consumer Number must be exactly 11 digits. Received {len(custid_clean)} digits.")

    print(f"[INFO] ValidateCustomerID: custid={custid_clean}, "
          f"type={'HT' if is_ht else 'LT'}, attempt={attempt_number}")

    # ------------------------------------------------------------------
    # Stage 2 — API validation via consumerDetails
    # ------------------------------------------------------------------
    try:
        payload = {"custid": custid_clean, "comp_src": SOURCE_NAME}
        if mobile:
            payload["mobile"] = mobile

        response = http_post(CONSUMER_DETAILS_URL, payload, token)
    except Exception as e:
        print(f"[ERROR] consumerDetails API failed during CID validation: {e}")
        # On API failure, don't count as a user mistake — return system error
        return bedrock_wrap("Validation", "ValidateCustomerID", {
            "case_type":      "SYSTEM_DOWN",
            "valid":          False,
            "custid":         custid_clean,
            "attempt_number": attempt_number,
            "message":        "Validation service is temporarily unavailable. Please try again in a moment.",
            "technical_error": str(e)
        })

    # ------------------------------------------------------------------
    # Parse response
    # ------------------------------------------------------------------
    api_status = response.get("status") if response else None
    data       = response.get("data", {}) if response else {}

    # Invalid CID — API returns error or empty data
    if api_status != "success" or not data or not data.get("CONS_NAME"):
        return _invalid_cid_response(custid_clean, attempt_number,
            response.get("message", "Customer ID not found in CESC records.") if response else "No response from validation service.")

    # ------------------------------------------------------------------
    # Valid CID — extract key consumer info for the agent to use directly
    # (avoids needing a separate GetConsumerDetails call in most flows)
    # ------------------------------------------------------------------
    consumer_type = "HT" if is_ht else "LT"

    addr_parts  = [data.get(f"ADDR_{s}", "") for s in ["TWO","THREE","FOUR","FIVE","SIX"]]
    full_address = ", ".join(p for p in addr_parts if p.strip())

    print(f"[INFO] CID validated: custid={custid_clean}, "
          f"name={data.get('CONS_NAME')}, type={consumer_type}")

    return bedrock_wrap("Validation", "ValidateCustomerID", {
        "case_type":       "CID_VALID",
        "valid":           True,
        "custid":          custid_clean,
        "consumer_type":   consumer_type,
        "consumer_name":   data.get("CONS_NAME", ""),
        "address":         full_address,
        "mobile":          data.get("MOB_NO", ""),
        "email":           data.get("MAIL_ID", ""),
        "attempt_number":  attempt_number,
        "message": (
            f"Customer ID {custid_clean} is valid. "
            f"Consumer: {data.get('CONS_NAME', '')} — {full_address}. "
            f"Type: {consumer_type}. "
            "Please confirm this CID with the user before proceeding."
        ),
        "confirm_prompt": (
            f"I found your account: {data.get('CONS_NAME', '')} at {full_address}. "
            "Is this correct?"
        )
    })


def _invalid_cid_response(custid: str, attempt_number: int, reason: str) -> Dict[str, Any]:
    """
    Builds a consistent INVALID or ESCALATE response based on attempt count.
    On 3rd failed attempt → ESCALATE_TO_HUMAN.
    """
    attempts_left = 3 - attempt_number

    if attempt_number >= 3:
        print(f"[INFO] CID validation failed 3 times for custid={custid} — escalating")
        return bedrock_wrap("Validation", "ValidateCustomerID", {
            "case_type":      "ESCALATE_TO_HUMAN",
            "valid":          False,
            "custid":         custid,
            "attempt_number": attempt_number,
            "attempts_left":  0,
            "message":        "Customer ID could not be validated after 3 attempts. Transfer to human agent.",
            "escalation_message": (
                "I'm sorry, I was unable to verify your Customer ID. "
                "Let me connect you with our support team who can help you further."
            )
        })

    return bedrock_wrap("Validation", "ValidateCustomerID", {
        "case_type":      "CID_INVALID",
        "valid":          False,
        "custid":         custid,
        "attempt_number": attempt_number,
        "attempts_left":  attempts_left,
        "reason":         reason,
        "message":        f"Invalid Customer ID (attempt {attempt_number}/3). {reason}",
        "retry_prompt": (
            f"I couldn't find that Customer ID in our records. "
            f"Could you please double-check and re-enter? "
            f"({attempts_left} attempt{'s' if attempts_left > 1 else ''} remaining)"
        )
    })


# ---------------------------------------------------------------------------
# Consumer Details — /api/consumerDetails
# Surfaces PRV_TEMPORARY_DKT, consumer info, meter list, billing info
# Called for TYPE 1 (Pending repair after temporary restoration)
# ---------------------------------------------------------------------------

def handle_get_consumer_details(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Calls /api/consumerDetails and returns a clean summary including
    PRV_TEMPORARY_DKT for use in TYPE 1 complaint flow.

    PRV_TEMPORARY_DKT from the API can be:
      - An object: {"docket": "1024011084", "con_add": "...", "at": "...", "complaint": "...", "comp_detail": "..."}
      - An empty list [] when no previous temporary docket exists

    Required params:
        custid  — 11-digit Customer ID
        mobile  — registered mobile number

    Returns:
        has_prv_temporary_dkt  — true/false
        prv_temporary_dkt      — docket details object or null
        consumer_name          — CONS_NAME
        address                — full formatted address
        mobile                 — MOB_NO
        email                  — MAIL_ID
        meter_list             — list of meters
        bill_info              — BILLINFO summary
        payment_info           — PAYMENTINFO summary
        meter_burnt            — BURNT_METER status
        lcc_locked             — LCC locked status (Y/N)
        commercial_disc        — commercial disconnection status
    """
    custid = params.get("custid", "").strip()
    mobile = params.get("mobile", "").strip()

    if not custid:
        return bedrock_wrap("ConsumerDetails", "GetConsumerDetails", {
            "case_type": "VALIDATION_ERROR",
            "message":   "custid is required."
        })

    print(f"[INFO] GetConsumerDetails: custid={custid}")

    try:
        payload  = {"custid": custid, "mobile": mobile, "comp_src": SOURCE_NAME}
        response = http_post(CONSUMER_DETAILS_URL, payload, token)
    except Exception as e:
        print(f"[ERROR] consumerDetails failed: {e}")
        return bedrock_wrap("ConsumerDetails", "GetConsumerDetails", {
            "case_type":       "SYSTEM_DOWN",
            "message":         "Unable to fetch consumer details. Please try again.",
            "technical_error": str(e)
        })

    if not response or response.get("status") != "success":
        return bedrock_wrap("ConsumerDetails", "GetConsumerDetails", {
            "case_type": "API_ERROR",
            "message":   f"Failed to fetch consumer details: {response.get('message', 'Unknown error') if response else 'No response'}"
        })

    data = response.get("data", {})

    # ------------------------------------------------------------------
    # Parse PRV_TEMPORARY_DKT safely — can be {} object OR [] empty list
    # ------------------------------------------------------------------
    prv_temp_raw = data.get("PRV_TEMPORARY_DKT")
    has_prv_temporary_dkt = False
    prv_temporary_dkt     = None

    if isinstance(prv_temp_raw, dict) and prv_temp_raw.get("docket"):
        # Valid docket object
        has_prv_temporary_dkt = True
        prv_temporary_dkt = {
            "docket":       prv_temp_raw.get("docket", ""),
            "address":      prv_temp_raw.get("con_add", ""),
            "raised_at":    prv_temp_raw.get("at", ""),
            "complaint":    prv_temp_raw.get("complaint", ""),
            "comp_detail":  prv_temp_raw.get("comp_detail", ""),
            "status":       prv_temp_raw.get("status", ""),        # "C" = Completed, "O" = Open
            "status_dtl":   prv_temp_raw.get("status_dtl", ""),   # e.g. "Complaint resolved"
            "completed_at": prv_temp_raw.get("completed_at", ""), # e.g. "03/10/2024 11:42"
        }
    elif isinstance(prv_temp_raw, list) and len(prv_temp_raw) > 0:
        # Non-empty list — take first item if it has a docket
        first = prv_temp_raw[0]
        if isinstance(first, dict) and first.get("docket"):
            has_prv_temporary_dkt = True
            prv_temporary_dkt = {
                "docket":       first.get("docket", ""),
                "address":      first.get("con_add", ""),
                "raised_at":    first.get("at", ""),
                "complaint":    first.get("complaint", ""),
                "comp_detail":  first.get("comp_detail", ""),
                "status":       first.get("status", ""),
                "status_dtl":   first.get("status_dtl", ""),
                "completed_at": first.get("completed_at", ""),
            }
    # else: empty list [] or None → has_prv_temporary_dkt stays False

    # ------------------------------------------------------------------
    # Parse PRV_SUPPLY_DKT (previous supply/no-power docket)
    # ------------------------------------------------------------------
    prv_supply_raw = data.get("PRV_SUPPLY_DKT")
    prv_supply_dkt = None
    if isinstance(prv_supply_raw, dict) and prv_supply_raw.get("docket"):
        prv_supply_dkt = {
            "docket":     prv_supply_raw.get("docket", ""),
            "address":    prv_supply_raw.get("con_add", ""),
            "raised_at":  prv_supply_raw.get("at", ""),
            "complaint":  prv_supply_raw.get("complaint", ""),
            "status":     prv_supply_raw.get("status", ""),
            "status_dtl": prv_supply_raw.get("status_dtl", ""),
        }

    # ------------------------------------------------------------------
    # Build full address from address fields
    # ------------------------------------------------------------------
    addr_parts = [
        data.get("ADDR_TWO", ""),
        data.get("ADDR_THREE", ""),
        data.get("ADDR_FOUR", ""),
        data.get("ADDR_FIVE", ""),
        data.get("ADDR_SIX", ""),
    ]
    full_address = ", ".join(p for p in addr_parts if p.strip())

    # ------------------------------------------------------------------
    # LCC + Commercial + Burnt Meter status
    # ------------------------------------------------------------------
    lcc_locked   = data.get("LCC", {}).get("LockedStat", "N")
    comm_disc    = data.get("COMMERCIAL_DISC", {})
    burnt_meter  = data.get("BURNT_METER", [])
    has_burnt_meter = isinstance(burnt_meter, dict) and bool(burnt_meter)

    print(f"[INFO] GetConsumerDetails: name={data.get('CONS_NAME')}, "
          f"has_prv_temp_dkt={has_prv_temporary_dkt}, lcc={lcc_locked}")

    return bedrock_wrap("ConsumerDetails", "GetConsumerDetails", {
        "case_type":            "CONSUMER_DETAILS_FETCHED",
        "customer_id":          data.get("CUSTOMER_ID", custid),
        "consumer_name":        data.get("CONS_NAME", ""),
        "address":              full_address,
        "mobile":               data.get("MOB_NO", ""),
        "email":                data.get("MAIL_ID", ""),
        "meter_list":           data.get("MTR_LIST", []),
        "bill_info":            data.get("BILLINFO", {}),
        "payment_info":         data.get("PAYMENTINFO", {}),
        "lcc_locked":           lcc_locked,
        "commercial_disc":      comm_disc,
        "has_burnt_meter":      has_burnt_meter,
        # Previous dockets
        "has_prv_temporary_dkt": has_prv_temporary_dkt,
        "prv_temporary_dkt":     prv_temporary_dkt,
        "prv_supply_dkt":        prv_supply_dkt,
        # Instruction for agent
        "message": (
            "Consumer details fetched successfully. "
            + (
                f"Previous temporary restoration docket found: {prv_temporary_dkt['docket']}. "
                "Use prv_temporary_dkt.docket as prev_docket in InsertComplaintData for TYPE 1 complaints."
                if has_prv_temporary_dkt
                else
                "No previous temporary restoration docket found (PRV_TEMPORARY_DKT is empty). "
                "For TYPE 1 complaints, inform user that no temporary restoration docket was found "
                "and ask them to confirm whether they want to proceed with a fresh complaint."
            )
        )
    })


# ---------------------------------------------------------------------------
# Complaint Options — getComplaintOp  (opt=2 for supply nature list)
# ---------------------------------------------------------------------------

def handle_get_complaint_options(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Calls getComplaintOp API and returns the supply complaint type list.

    API response structure:
        data.complaint = [{opt_name, opt_code}, ...]

    opt=2  → Supply related complaints (all 8 types) — USE THIS for supply flows
    opt=1  → Commercial/Billing only — NOT used in current supply flows

    The returned opt_code is passed as complaint_code in InsertComplaintData.

    Required params:
        opt — always pass "2" for supply complaints
    """
    opt = params.get("opt", "2").strip()

    if opt not in ("1", "2"):
        return bedrock_wrap("ComplaintOptions", "GetComplaintOptions", {
            "case_type": "VALIDATION_ERROR",
            "message":   "opt must be '2' for supply complaints."
        })

    print(f"[INFO] GetComplaintOptions: opt={opt}")

    try:
        payload  = {"opt": opt, "comp_src": SOURCE_NAME}
        response = http_post(GET_COMPLAINT_OP_URL, payload, token)
    except Exception as e:
        print(f"[ERROR] getComplaintOp failed: {e}")
        return bedrock_wrap("ComplaintOptions", "GetComplaintOptions", {
            "case_type":       "SYSTEM_DOWN",
            "message":         "Complaint options service is currently unavailable. Please try again.",
            "technical_error": str(e)
        })

    if not response or response.get("status") != "success":
        return bedrock_wrap("ComplaintOptions", "GetComplaintOptions", {
            "case_type": "API_ERROR",
            "message":   f"Failed to fetch complaint options: {response.get('message', 'Unknown error') if response else 'No response'}"
        })

    # Correct response structure: data.complaint = [{opt_name, opt_code}, ...]
    data     = response.get("data", {})
    options  = data.get("complaint", [])

    # Build numbered display list for agent to present to user
    display_list = [
        f"{i+1}. {item.get('opt_name', '')}"
        for i, item in enumerate(options)
    ]

    print(f"[INFO] GetComplaintOptions: returned {len(options)} options for opt={opt}")

    return bedrock_wrap("ComplaintOptions", "GetComplaintOptions", {
        "case_type":    "OPTIONS_FETCHED",
        "opt":          opt,
        "options":      options,       # [{opt_name, opt_code}, ...]
        "display_list": display_list,  # numbered strings — present these to user
        "total":        len(options),
        "message":      (
            "Complaint options fetched. Present display_list to user. "
            "After user selects, find the matching opt_code from options list. "
            "Pass opt_code as complaint_code in InsertComplaintData."
        ),
        "instruction": (
            "Map user selection (number or text) to opt_code. "
            "Example: user says '7' or 'temporary restoration' → find matching item → use its opt_code (e.g. '60'). "
            "Store opt_code and opt_name for use in InsertComplaintData."
        )
    })


# ---------------------------------------------------------------------------
# Insert Complaint Data — raises docket for all 8 supply complaint types
# ---------------------------------------------------------------------------

def handle_insert_complaint_data(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Raises a complaint docket via insertComplaintData API.
    Used for ALL 8 supply complaint types (TYPE 1-2, TYPE 4-8).
    Uses multipart/form-data to support optional image/file upload.

    MANDATORY fields:
        custid           — 11-digit Customer ID (reporter's own CID)
        complaint_code   — opt_code from GetComplaintOptions (e.g. "60", "64", "86")
        complaint_detail — description of the complaint (max 200 chars)
        complaint_category — always "2" for supply related
        cons_type        — "e" for existing consumer (always for supply complaints)

    OPTIONAL fields:
        phone            — reporter's mobile number
        email            — reporter's email
        no_of_meter      — number of meters (TYPE 4 Meter Board only, 2 digit numeric)
        image_s3_url     — S3 URL of uploaded image/photo
        image_base64     — base64 image fallback (small images only)
        image_mime_type  — default image/jpeg
        image_filename   — default complaint_photo.jpg

    INTENDING CONSUMER ONLY (when user has no CID — cons_type=n):
        dist             — 2 digit numeric
        refno            — numeric reference
        yr               — 2 digit numeric year

    test_mode=true skips mandatory validation for testing.
    """
    try:
        test_mode = params.get("test_mode", "").strip().lower() in ("true", "1", "yes")

        if test_mode:
            print("[INFO] InsertComplaintData: TEST MODE — skipping mandatory validation")

        # ------------------------------------------------------------------
        # Mandatory validation
        # ------------------------------------------------------------------
        if not test_mode:
            mandatory = ["custid", "complaint_code", "complaint_detail", "complaint_category", "cons_type"]
            missing   = [f for f in mandatory if not params.get(f, "").strip()]
            if missing:
                return bedrock_wrap("ComplaintData", "InsertComplaintData", {
                    "case_type":      "VALIDATION_ERROR",
                    "missing_fields": missing,
                    "message":        f"Missing required fields: {', '.join(missing)}",
                    "field_guide": {
                        "custid":             "Reporter 11-digit Customer ID",
                        "complaint_code":     "opt_code from GetComplaintOptions e.g. '60'",
                        "complaint_detail":   "Description of complaint (max 200 chars)",
                        "complaint_category": "Always '2' for supply related",
                        "cons_type":          "Always 'e' for existing consumer"
                    }
                })

        cons_type = params.get("cons_type", "e").strip()

        print(f"[INFO] InsertComplaintData: custid={params.get('custid','N/A')}, "
              f"code={params.get('complaint_code','N/A')}, cons_type={cons_type}, "
              f"test_mode={test_mode}")

        # ------------------------------------------------------------------
        # Resolve image if provided
        # ------------------------------------------------------------------
        image_bytes    = None
        image_mime     = params.get("image_mime_type", "image/jpeg").strip()
        image_filename = params.get("image_filename", "complaint_photo.jpg").strip()
        image_source   = "none"

        image_s3_url = params.get("image_s3_url", "").strip()
        image_base64 = params.get("image_base64", "").strip()

        if image_s3_url:
            try:
                image_bytes, image_mime, image_filename = _download_image_from_s3(image_s3_url)
                image_source = "s3"
                print(f"[INFO] Image from S3: {len(image_bytes)} bytes")
            except Exception as s3_err:
                print(f"[WARN] S3 image download failed: {s3_err} — submitting without image")
        elif image_base64:
            import base64 as b64mod
            try:
                image_bytes  = b64mod.b64decode(image_base64)
                image_source = "base64"
                print(f"[INFO] Image from base64: {len(image_bytes)} bytes")
            except Exception as b64_err:
                print(f"[WARN] base64 decode failed: {b64_err} — submitting without image")

        # ------------------------------------------------------------------
        # Build form fields
        # ------------------------------------------------------------------
        complaint_detail = params.get("complaint_detail", "")
        if len(complaint_detail) > 200:
            complaint_detail = complaint_detail[:200]

        form_fields = {
            # Mandatory
            "custid":             params.get("custid", ""),
            "complaint_code":     params.get("complaint_code", ""),
            "complaint_detail":   complaint_detail,
            "complaint_category": params.get("complaint_category", "2"),
            "cons_type":          cons_type,
            "comp_src":           SOURCE_NAME,
            # Optional standard
            "phone":              params.get("phone", ""),
            "email":              params.get("email", ""),
            "name":               params.get("name", ""),
            "no_of_meter":        params.get("no_of_meter", ""),
            # Intending consumer only (cons_type=n)
            "dist":               params.get("dist", "") if cons_type == "n" else "",
            "refno":              params.get("refno", "") if cons_type == "n" else "",
            "yr":                 params.get("yr", "")   if cons_type == "n" else "",
        }

        # ------------------------------------------------------------------
        # Build multipart/form-data body
        # ------------------------------------------------------------------
        CRLF     = "\r\n"
        boundary = "----BotComplaintBoundary" + datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        body_parts = []

        for field_name, field_value in form_fields.items():
            if str(field_value).strip():
                part = (
                    "--" + boundary + CRLF +
                    'Content-Disposition: form-data; name="' + field_name + '"' + CRLF + CRLF +
                    str(field_value)
                )
                body_parts.append(part)

        if image_bytes:
            text_body  = (CRLF.join(body_parts) + CRLF).encode("utf-8")
            img_header = (
                "--" + boundary + CRLF +
                'Content-Disposition: form-data; name="complaint_file"; filename="' + image_filename + '"' + CRLF +
                "Content-Type: " + image_mime + CRLF + CRLF
            ).encode("utf-8")
            img_footer       = (CRLF + "--" + boundary + "--" + CRLF).encode("utf-8")
            multipart_body   = text_body + img_header + image_bytes + img_footer
        else:
            multipart_body = (CRLF.join(body_parts) + CRLF + "--" + boundary + "--" + CRLF).encode("utf-8")

        # ------------------------------------------------------------------
        # POST to insertComplaintData
        # ------------------------------------------------------------------
        try:
            req = urllib.request.Request(
                INSERT_COMPLAINT_URL,
                data=multipart_body,
                headers={
                    "Content-Type":  "multipart/form-data; boundary=" + boundary,
                    "Authorization": "Bearer " + token
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                insert_response = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else str(e)
            print(f"[ERROR] insertComplaintData HTTP {e.code}: {err_body}")
            return bedrock_wrap("ComplaintData", "InsertComplaintData", {
                "case_type":       "SYSTEM_DOWN",
                "message":         "Complaint registration system is currently unavailable. Please try again.",
                "technical_error": f"HTTP {e.code}: {err_body}"
            })
        except Exception as e:
            print(f"[ERROR] insertComplaintData failed: {e}")
            return bedrock_wrap("ComplaintData", "InsertComplaintData", {
                "case_type":       "SYSTEM_DOWN",
                "message":         "Complaint registration system is currently unavailable. Please try again.",
                "technical_error": str(e)
            })

        # ------------------------------------------------------------------
        # Handle response
        # ------------------------------------------------------------------
        if not insert_response:
            return bedrock_wrap("ComplaintData", "InsertComplaintData", {
                "case_type": "API_ERROR",
                "message":   "No response received from complaint system."
            })

        api_status = insert_response.get("status", "")

        # Validation error from API (e.g. invalid Customer ID)
        if api_status == "error":
            errors = insert_response.get("errors", [])
            return bedrock_wrap("ComplaintData", "InsertComplaintData", {
                "case_type": "VALIDATION_ERROR",
                "message":   f"Complaint could not be registered: {insert_response.get('message', 'Validation failed')}",
                "errors":    errors,
                "reff_id":   insert_response.get("reffid", "")
            })

        if api_status != "success":
            return bedrock_wrap("ComplaintData", "InsertComplaintData", {
                "case_type": "API_ERROR",
                "message":   f"Unexpected response: {insert_response.get('message', 'Unknown error')}"
            })

        data      = insert_response.get("data", {})
        docket_no = data.get("DOCKET_NO", "")
        reff_id   = insert_response.get("reffid", "")

        print(f"[INFO] InsertComplaintData: docket={docket_no}, reff_id={reff_id}, "
              f"image_source={image_source}")

        return bedrock_wrap("ComplaintData", "InsertComplaintData", {
            "case_type":      "DOCKET_CREATED",
            "docket_no":      docket_no,
            "reff_id":        reff_id,
            "image_attached": image_bytes is not None,
            "image_source":   image_source,
            "complaint_code": params.get("complaint_code", ""),
            "message":        f"We are looking into the matter. Your docket number is {docket_no}.",
            "next_step":      "Ask user for feedback (thumbs up/down) and proceed to post-docket flow."
        })

    except Exception as e:
        print(f"[ERROR] Exception in handle_insert_complaint_data: {e}")
        return bedrock_wrap("ComplaintData", "InsertComplaintData", {
            "case_type": "PROCESSING_ERROR",
            "error":     str(e),
            "message":   "An error occurred while registering your complaint."
        })


# ---------------------------------------------------------------------------
# Power Theft — Resolve area_id and stncd from user-provided names
# ---------------------------------------------------------------------------

def handle_resolve_theft_details(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Takes the user-selected area name and police station name and resolves
    them to the actual area_id and stncd codes needed by SavePowerTheftComplaint.

    This is called AFTER GetPowerTheftReferenceData and AFTER user has selected
    their area and police station by name or number.

    Required params:
        area_name         — what the user said/selected e.g. "Jadavpur" or "2"
        police_name       — what the user said/selected e.g. "Bhawanipur" or "P015"

    Returns:
        resolved_area_id   — numeric area_id to pass to SavePowerTheftComplaint
        resolved_stncd     — stncd code to pass as off_police
        resolved_area_name — confirmed display name
        resolved_police_name — confirmed display name
        ready_to_submit    — true if both resolved successfully
        unresolved         — list of fields that could not be matched
    """
    area_input   = params.get("area_name", "").strip()
    police_input = params.get("police_name", "").strip()

    if not area_input and not police_input:
        return bedrock_wrap("PowerTheft", "ResolveTheftDetails", {
            "case_type": "VALIDATION_ERROR",
            "message":   "Provide at least area_name or police_name to resolve."
        })

    # Fetch reference data
    areas_result  = _fetch_theft_major_areas(token)
    police_result = _fetch_theft_police_stations(token)

    areas    = areas_result.get("data", [])
    stations = police_result.get("data", [])

    resolved_area_id    = None
    resolved_area_name  = None
    resolved_stncd      = None
    resolved_police_name = None
    unresolved = []

    # ---- Resolve area ----
    if area_input:
        # Try exact numeric match first (user typed the area_id directly)
        if area_input.isdigit():
            for a in areas:
                if str(a.get("area_id", "")) == area_input:
                    resolved_area_id   = str(a["area_id"])
                    resolved_area_name = a["theft_area"]
                    break
        # Try name match
        if not resolved_area_id:
            match = fuzzy_match_area(area_input, areas)
            if match:
                resolved_area_id   = str(match["area_id"])
                resolved_area_name = match["theft_area"]
        if not resolved_area_id:
            unresolved.append("area_name")

    # ---- Resolve police station ----
    if police_input:
        # Try exact stncd match first (e.g. "P015")
        for s in stations:
            if s.get("stncd", "").upper() == police_input.upper():
                resolved_stncd        = s["stncd"]
                resolved_police_name  = s["stndesc"]
                break
        # Try name match
        if not resolved_stncd:
            match = fuzzy_match_police_station(police_input, stations)
            if match:
                resolved_stncd        = match["stncd"]
                resolved_police_name  = match["stndesc"]
        if not resolved_stncd:
            unresolved.append("police_name")

    ready = len(unresolved) == 0 and bool(resolved_area_id) and bool(resolved_stncd)

    print(f"[INFO] ResolveTheftDetails: area_id={resolved_area_id}, "
          f"stncd={resolved_stncd}, unresolved={unresolved}")

    result = {
        "case_type":             "THEFT_DETAILS_RESOLVED" if ready else "PARTIAL_RESOLVE",
        "resolved_area_id":      resolved_area_id,
        "resolved_area_name":    resolved_area_name,
        "resolved_stncd":        resolved_stncd,
        "resolved_police_name":  resolved_police_name,
        "ready_to_submit":       ready,
        "unresolved":            unresolved,
    }

    if ready:
        result["message"] = (
            f"Successfully resolved: Area='{resolved_area_name}' (area_id={resolved_area_id}), "
            f"Police='{resolved_police_name}' (stncd={resolved_stncd}). "
            f"Now call SavePowerTheftComplaint using area_id={resolved_area_id} "
            f"and off_police={resolved_stncd}."
        )
        result["next_action"] = (
            f"Call SavePowerTheftComplaint with area_id={resolved_area_id} "
            f"and off_police={resolved_stncd}"
        )
    else:
        # Build user-facing list for unresolvable names
        suggestion = {}
        if "area_name" in unresolved:
            suggestion["available_areas"] = [
                f"{a['area_id']}: {a['theft_area']}" for a in areas
            ]
        if "police_name" in unresolved:
            suggestion["available_stations"] = [
                f"{s['stncd']}: {s['stndesc']}" for s in stations[:20]
            ]
        result["message"] = (
            f"Could not resolve: {', '.join(unresolved)}. "
            "Please ask the user to select from the available options."
        )
        result["suggestions"] = suggestion

    return bedrock_wrap("PowerTheft", "ResolveTheftDetails", result)


# ---------------------------------------------------------------------------
# Power Theft — Save Complaint  (Step 5.1 → 5.2 → 5.3)
# savePowerTheft uses multipart/form-data because images can be attached.
# ---------------------------------------------------------------------------

def _download_image_from_s3(s3_url: str) -> tuple:
    """
    Downloads image bytes from an S3 URL or s3://bucket/key URI.

    Accepts two formats:
      1. s3://bucket-name/path/to/image.jpg   — parsed directly
      2. https://bucket.s3.region.amazonaws.com/path/to/image.jpg — parsed from URL

    Returns (image_bytes, mime_type, filename) or raises Exception on failure.
    """
    import base64

    s3_url = s3_url.strip()

    # Parse s3:// URI
    if s3_url.startswith("s3://"):
        # s3://bucket/key
        without_prefix = s3_url[5:]
        slash_idx = without_prefix.find("/")
        if slash_idx == -1:
            raise Exception(f"Invalid s3:// URI — no key found: {s3_url}")
        bucket = without_prefix[:slash_idx]
        key    = without_prefix[slash_idx + 1:]

    # Parse HTTPS S3 URL:  https://bucket.s3.region.amazonaws.com/key
    #                   or https://s3.region.amazonaws.com/bucket/key
    elif s3_url.startswith("https://") and "amazonaws.com" in s3_url:
        from urllib.parse import urlparse
        parsed = urlparse(s3_url)
        host   = parsed.netloc  # e.g. mybucket.s3.ap-south-1.amazonaws.com

        if host.endswith(".amazonaws.com") and ".s3." in host:
            # Virtual-hosted style: bucket.s3.region.amazonaws.com/key
            bucket = host.split(".s3.")[0]
            key    = parsed.path.lstrip("/")
        else:
            # Path style: s3.region.amazonaws.com/bucket/key
            parts  = parsed.path.lstrip("/").split("/", 1)
            if len(parts) < 2:
                raise Exception(f"Could not parse S3 bucket/key from URL: {s3_url}")
            bucket, key = parts[0], parts[1]
    else:
        raise Exception(
            f"Unsupported image URL format: '{s3_url}'. "
            "Expected s3://bucket/key or https://bucket.s3.region.amazonaws.com/key"
        )

    print(f"[INFO] Downloading image from S3: bucket={bucket}, key={key}")

    s3_client  = boto3.client("s3")
    s3_obj     = s3_client.get_object(Bucket=bucket, Key=key)
    img_bytes  = s3_obj["Body"].read()
    content_type = s3_obj.get("ContentType", "image/jpeg")
    filename   = key.split("/")[-1] or "theft_photo.jpg"

    print(f"[INFO] S3 image downloaded: {len(img_bytes)} bytes, type={content_type}")
    return img_bytes, content_type, filename


def handle_save_power_theft_complaint(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Saves a power theft complaint via the savePowerTheft API (multipart/form-data).

    IMAGE HANDLING — two modes:
      Production / Bedrock testing with S3:
        Pass  image_s3_url  as either:
          - s3://bucket-name/path/to/image.jpg
          - https://bucket.s3.region.amazonaws.com/path/to/image.jpg
        Lambda downloads bytes from S3 using boto3 and attaches to multipart.

      Legacy / fallback:
        Pass  image_base64  — raw base64 string (small images only, <20KB).

    TEST MODE:
        Pass  test_mode=true  to skip mandatory field validation entirely.
        Useful for testing the S3 image pipeline or API connectivity
        without having all offender details yet.

    MANDATORY offender fields (collected at step 5.1):
        off_cust_id          — Offender Customer ID
        off_name             — Offender name
        off_prno             — Premises number
        off_rd_locality      — Road / Lane / Locality
        area_id              — Resolved from powerTheftMajorArea
        off_police           — Resolved stncd from powerTheftPoliceStationList

    OPTIONAL offender fields:
        meter_no, offender_father_name, offender_address,
        offender_flat_no, offender_floor, offender_building,
        offender_pincode, off_lnno (landmark), off_con_no,
        uses_ac (yes/no, default no)

    OPTIONAL caller details (not mandatory per spec):
        caller_name, caller_mobile, caller_email, caller_address
    """
    try:
        # ------------------------------------------------------------------
        # Test mode — skip mandatory validation for Bedrock console testing
        # ------------------------------------------------------------------
        test_mode = params.get("test_mode", "").strip().lower() in ("true", "1", "yes")

        if test_mode:
            print("[INFO] SavePowerTheft: TEST MODE enabled — skipping mandatory validation")

        # ------------------------------------------------------------------
        # Mandatory field validation (skipped in test_mode)
        # ------------------------------------------------------------------
        if not test_mode:
            # off_cust_id is optional — user may not know the offender's CID
            # off_police must be the stncd code (e.g. "P015"), not the station name
            # area_id must be the numeric area_id from GetPowerTheftReferenceData
            mandatory = ['off_name', 'off_prno', 'off_rd_locality', 'area_id', 'off_police']
            missing = [f for f in mandatory if not params.get(f, "").strip()]

            if missing:
                return bedrock_wrap("PowerTheft", "SavePowerTheftComplaint", {
                    "case_type":      "VALIDATION_ERROR",
                    "missing_fields": missing,
                    "message": (
                        f"The following mandatory offender details are still required: "
                        f"{', '.join(missing)}. Please collect these from the user."
                    ),
                    "mandatory_fields_guide": {
                        "off_name":        "Offender name",
                        "off_prno":        "Premises number",
                        "off_rd_locality": "Road / Lane / Locality",
                        "area_id":         "Numeric area_id from GetPowerTheftReferenceData major_areas list",
                        "off_police":      "stncd code from GetPowerTheftReferenceData police_stations list (e.g. P015)"
                    },
                    "note": "off_cust_id is optional — pass empty string if user does not know it.",
                    "tip": "Pass test_mode=true to skip validation during Bedrock console testing."
                })

        print(f"[INFO] SavePowerTheft: off_cust_id={params.get('off_cust_id', 'N/A')}, "
              f"area_id={params.get('area_id', 'N/A')}, police={params.get('off_police', 'N/A')}, "
              f"test_mode={test_mode}")

        # ------------------------------------------------------------------
        # Resolve image — S3 URL takes priority over base64
        # ------------------------------------------------------------------
        image_bytes    = None
        image_mime     = params.get("image_mime_type", "image/jpeg").strip()
        image_filename = params.get("image_filename", "theft_photo.jpg").strip()
        image_source   = "none"

        image_s3_url  = params.get("image_s3_url", "").strip()
        image_base64  = params.get("image_base64", "").strip()

        if image_s3_url:
            # ------ Path A: Download from S3 ------
            try:
                image_bytes, image_mime, image_filename = _download_image_from_s3(image_s3_url)
                image_source = "s3"
                print(f"[INFO] Image source: S3 ({len(image_bytes)} bytes)")
            except Exception as s3_err:
                print(f"[WARN] S3 image download failed: {s3_err}")
                return bedrock_wrap("PowerTheft", "SavePowerTheftComplaint", {
                    "case_type":      "IMAGE_DOWNLOAD_ERROR",
                    "message":        "Could not download the image from S3. Please check the S3 URL and bucket permissions.",
                    "s3_url":         image_s3_url,
                    "technical_error": str(s3_err),
                    "tip": (
                        "Ensure the Lambda execution role has s3:GetObject permission on the bucket. "
                        "S3 URL format: s3://bucket-name/path/to/image.jpg "
                        "or https://bucket.s3.region.amazonaws.com/path/to/image.jpg"
                    )
                })

        elif image_base64:
            # ------ Path B: Decode base64 (small images / fallback) ------
            import base64 as b64mod
            try:
                image_bytes  = b64mod.b64decode(image_base64)
                image_source = "base64"
                print(f"[INFO] Image source: base64 ({len(image_bytes)} bytes)")
            except Exception as b64_err:
                print(f"[WARN] base64 image decode failed: {b64_err} — submitting without image")
                image_bytes = None

        # ------------------------------------------------------------------
        # Build form fields dict
        # ------------------------------------------------------------------
        form_fields = {
            # Mandatory (may be empty in test_mode)
            "off_cust_id":          params.get("off_cust_id", ""),
            "off_name":             params.get("off_name", ""),
            "off_prno":             params.get("off_prno", ""),
            "off_rd_locality":      params.get("off_rd_locality", ""),
            "area_id":              params.get("area_id", ""),
            "off_police":           params.get("off_police", ""),
            "comp_src":             SOURCE_NAME,
            # Optional offender
            "meter_no":             params.get("meter_no", ""),
            "offender_father_name": params.get("offender_father_name", ""),
            "offender_address":     params.get("offender_address", ""),
            "offender_flat_no":     params.get("offender_flat_no", ""),
            "offender_floor":       params.get("offender_floor", ""),
            "offender_building":    params.get("offender_building", ""),
            "offender_pincode":     params.get("offender_pincode", ""),
            "off_lnno":             params.get("off_lnno", ""),
            "off_con_no":           params.get("off_con_no", ""),
            "uses_ac":              params.get("uses_ac", "no"),
            # Optional caller details
            "caller_name":          params.get("caller_name", ""),
            "caller_mobile":        params.get("caller_mobile", ""),
            "caller_email":         params.get("caller_email", ""),
            "caller_address":       params.get("caller_address", ""),
            # Reporter CID
            "custid":               params.get("custid", ""),
        }

        # ------------------------------------------------------------------
        # Build multipart/form-data body
        # ------------------------------------------------------------------
        CRLF     = "\r\n"
        boundary = "----BotTheftBoundary" + datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        body_parts = []

        for field_name, field_value in form_fields.items():
            if field_value:    # skip empty optional fields
                part = (
                    "--" + boundary + CRLF +
                    'Content-Disposition: form-data; name="' + field_name + '"' + CRLF + CRLF +
                    str(field_value)
                )
                body_parts.append(part)

        # Attach image bytes if successfully resolved
        if image_bytes:
            text_body  = (CRLF.join(body_parts) + CRLF).encode("utf-8")
            img_header = (
                "--" + boundary + CRLF +
                'Content-Disposition: form-data; name="theft_image"; filename="' + image_filename + '"' + CRLF +
                "Content-Type: " + image_mime + CRLF + CRLF
            ).encode("utf-8")
            img_footer = (CRLF + "--" + boundary + "--" + CRLF).encode("utf-8")
            multipart_body = text_body + img_header + image_bytes + img_footer
        else:
            multipart_body = (CRLF.join(body_parts) + CRLF + "--" + boundary + "--" + CRLF).encode("utf-8")

        # ------------------------------------------------------------------
        # POST multipart to savePowerTheft
        # ------------------------------------------------------------------
        try:
            req = urllib.request.Request(
                SAVE_POWER_THEFT_URL,
                data=multipart_body,
                headers={
                    "Content-Type":  "multipart/form-data; boundary=" + boundary,
                    "Authorization": "Bearer " + token
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                save_response = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else str(e)
            print(f"[ERROR] savePowerTheft HTTP error {e.code}: {err_body}")
            return bedrock_wrap("PowerTheft", "SavePowerTheftComplaint", {
                "case_type":       "SYSTEM_DOWN",
                "message":         "Power theft reporting system is currently unavailable. Please try again later.",
                "technical_error": f"HTTP {e.code}: {err_body}"
            })
        except Exception as e:
            print(f"[ERROR] savePowerTheft request failed: {e}")
            return bedrock_wrap("PowerTheft", "SavePowerTheftComplaint", {
                "case_type":       "SYSTEM_DOWN",
                "message":         "Power theft reporting system is currently unavailable. Please try again later.",
                "technical_error": str(e)
            })

        if not save_response or save_response.get("status") != "success":
            return bedrock_wrap("PowerTheft", "SavePowerTheftComplaint", {
                "case_type": "API_ERROR",
                "message":   f"Failed to save power theft complaint: {save_response.get('message', 'Unknown error')}",
                "errors":    save_response.get("errors", [])
            })

        data        = save_response.get("data", {})
        docket      = data.get("docket", "")
        docket_type = data.get("docket_type", "")
        reff_id     = save_response.get("reffid", "")

        print(f"[INFO] Power theft saved: docket={docket}, type={docket_type}, "
              f"reff_id={reff_id}, image_source={image_source}")

        return bedrock_wrap("PowerTheft", "SavePowerTheftComplaint", {
            "case_type":      "POWER_THEFT_REPORTED",
            "docket":         docket,
            "docket_type":    docket_type,
            "reff_id":        reff_id,
            "image_attached": image_bytes is not None,
            "image_source":   image_source,
            "test_mode":      test_mode,
            "message": (
                f"Your power theft complaint has been registered successfully. "
                f"Docket number: {docket} (Type: {docket_type})."
            ),
            "next_steps": [
                "Our vigilance team has been notified",
                "You will receive an SMS confirmation shortly",
                "You can check docket details using GetPowerTheftDocketDetails"
            ],
            "acknowledgment": (
                "Thank you for reporting electricity theft. "
                "This helps us serve all consumers better."
            )
        })

    except Exception as e:
        print(f"[ERROR] Exception in handle_save_power_theft_complaint: {e}")
        return bedrock_wrap("PowerTheft", "SavePowerTheftComplaint", {
            "case_type": "PROCESSING_ERROR",
            "error":     str(e),
            "message":   "An error occurred while saving the power theft complaint"
        })


# ---------------------------------------------------------------------------
# Power Theft — Docket Details  (powerTheftDocketDetails)
# ---------------------------------------------------------------------------

def handle_get_power_theft_docket_details(params: Dict[str, str], token: str) -> Dict[str, Any]:
    """
    Retrieves full details of an existing power theft docket.

    Required params: theft_docket
    Optional params: custid
    """
    theft_docket = params.get("theft_docket", "").strip()

    if not theft_docket:
        return bedrock_wrap("PowerTheft", "GetPowerTheftDocketDetails", {
            "case_type": "VALIDATION_ERROR",
            "message":   "A theft docket number is required to fetch details."
        })

    print(f"[INFO] GetPowerTheftDocketDetails: docket={theft_docket}")

    try:
        payload = {
            "custid":       params.get("custid", ""),
            "theft_docket": theft_docket,
            "comp_src":     SOURCE_NAME
        }
        resp = http_post(POWER_THEFT_DOCKET_DTLS_URL, payload, token)
    except Exception as e:
        print(f"[ERROR] powerTheftDocketDetails failed: {e}")
        return bedrock_wrap("PowerTheft", "GetPowerTheftDocketDetails", {
            "case_type":      "SYSTEM_DOWN",
            "message":        "Unable to retrieve theft docket details. Please try again later.",
            "technical_error": str(e)
        })

    if not resp or resp.get("status") != "success":
        return bedrock_wrap("PowerTheft", "GetPowerTheftDocketDetails", {
            "case_type": "API_ERROR",
            "message":   f"Failed to fetch docket details: {resp.get('message', 'Unknown error') if resp else 'No response'}"
        })

    data = resp.get("data", {})

    # Build a clean, readable summary for the agent to present to the user
    offender_summary = {
        "theft_docket":    data.get("theft_docket"),
        "off_cust_id":     data.get("off_cust_id"),
        "off_con_no":      data.get("off_con_no"),
        "off_name":        data.get("off_name"),
        "off_father_name": data.get("off_father_name"),
        "off_address":     data.get("off_address"),
        "off_flatno":      data.get("off_flatno"),
        "off_floor":       data.get("off_floor"),
        "off_bldg_name":   data.get("off_bldg_name"),
        "off_prno":        data.get("off_prno"),
        "off_rd_locality": data.get("off_rd_locality"),
        "off_police":      data.get("off_police"),
        "off_pin":         data.get("off_pin"),
        "off_mtrno":       data.get("off_mtrno"),
    }

    return bedrock_wrap("PowerTheft", "GetPowerTheftDocketDetails", {
        "case_type":        "THEFT_DOCKET_DETAILS",
        "theft_docket":     theft_docket,
        "offender_details": offender_summary,
        "raw_data":         data,
        "reff_id":          resp.get("reffid", ""),
        "message":          f"Details for theft docket {theft_docket} retrieved successfully."
    })


# ---------------------------------------------------------------------------
# Additional utility functions for edge cases
# ---------------------------------------------------------------------------

def validate_customer_id(custid: str) -> bool:
    """Validates customer ID format"""
    if not custid or len(custid) < 5:
        return False
    return True

def validate_mobile_number(mobile: str) -> bool:
    """Validates mobile number format"""
    if not mobile or len(mobile) != 10:
        return False
    if not mobile.isdigit():
        return False
    return True

def validate_complaint_type(comp_type: str) -> bool:
    """Validates Supply Off complaint type. '1': No Power, '14': Voltage Complaint"""
    valid_types = ["1", "14"]
    return comp_type in valid_types

def validate_emergency_complaint_code(comp_code: str) -> bool:
    """Validates SOS emergency complaint code against supported codes"""
    return comp_code in EMERGENCY_COMPLAINT_CODES


# ---------------------------------------------------------------------------
# Error recovery and retry logic
# ---------------------------------------------------------------------------

def retry_api_call(url: str, payload: Dict[str, Any], token: str, max_retries: int = 3) -> Dict[str, Any]:
    """Retries API call with exponential backoff"""
    import time

    for attempt in range(max_retries):
        try:
            return http_post(url, payload, token, timeout=20)
        except Exception as e:
            print(f"[WARN] API call attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                time.sleep(wait_time)
            else:
                raise


# ---------------------------------------------------------------------------
# Logging and monitoring helpers
# ---------------------------------------------------------------------------

def log_event(event_type: str, details: Dict[str, Any]) -> None:
    """Logs events for monitoring and debugging"""
    log_entry = {
        "timestamp":  datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        "details":    details
    }
    print(f"[EVENT] {json.dumps(log_entry)}")

def sanitize_error_message(error: Exception) -> str:
    """Sanitizes error messages for user-facing output"""
    error_str = str(error)
    return error_str[:200]  # Limit length