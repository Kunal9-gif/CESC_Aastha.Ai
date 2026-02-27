import json
import urllib.request
import time
from typing import Dict, Any, Optional
from datetime import datetime
#Author : Devashree
# ---------------------------------------------------------------------------
# API Configuration — DICE UAT Server
# ---------------------------------------------------------------------------
BASE_URL                 = "https://dice-uat.cesc.co.in"
BOT_KEY_URL              = f"{BASE_URL}/dicekey/botKeyStore.txt"
SECRET_KEY_URL           = f"{BASE_URL}/api/getSecretKey"
GEN_DOCKET_URL           = f"{BASE_URL}/api/genSupplyCrmDkt"
STATUS_URL               = f"{BASE_URL}/api/getComplaintStatus"
GEN_EMERGENCY_DOCKET_URL = f"{BASE_URL}/api/genEmergencyCrmDkt"
SOURCE_NAME              = "whatsapp"

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
            return handle_business_rule_failure(api_message, reason, docket_no)

    except Exception as e:
        print(f"[ERROR] Exception in handle_supply_off_complaint: {str(e)}")
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "PROCESSING_ERROR",
            "error": str(e),
            "message": "An error occurred while processing your complaint"
        })


def handle_business_rule_failure(dkt_status: str, reason: str, docket_no: Optional[str]) -> Dict[str, Any]:
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