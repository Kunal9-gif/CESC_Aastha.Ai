import json
import urllib.request

GEN_DOCKET_URL = "https://smautomation.cesc.co.in/api/genSupplyCrmDkt"
STATUS_URL = "https://smautomation.cesc.co.in/api/getComplaintStatus"
SOURCE_NAME = "awsinfosys"

def bedrock_wrap(action_group, function_name, payload):
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

def http_post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def lambda_handler(event, context):
    try:
        payload = {
            "custid": event["custid"],
            "mob": event["mobile"],        # mapping
            "comp": event["complaint_type"],  # mapping
            "comp_src": SOURCE_NAME
        }

        resp = http_post(GEN_DOCKET_URL, payload)

        if resp.get("status") != "success":
            return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
                "case_type": "SYSTEM_DOWN",
                "message": "Supply docket system is down"
            })

        data = resp["data"]
        dkt_status = data.get("dkt_status")
        dkt_type = data.get("dkt_type")
        docket_no = data.get("dtl")
        reason = data.get("dtl_msg", "")

        # 8 business rule fail
        if dkt_status != "ok":
            return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
                "case_type": "CANNOT_RAISE_DOCKET",
                "reason": reason
            })

        # Existing docket → fetch status
        if dkt_type == "EXISTING":
            status_resp = http_post(STATUS_URL, {
                "docket": docket_no,
                "comp_src": SOURCE_NAME
            })

            return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
                "case_type": "EXISTING_DOCKET",
                "docket_no": docket_no,
                "status_details": status_resp["data"]
            })

        # New docket created
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "NEW_DOCKET_CREATED",
            "docket_no": docket_no
        })

    except Exception as e:
        return bedrock_wrap("SupplyOff", "SupplyOffComplaint", {
            "case_type": "SYSTEM_DOWN",
            "error": str(e)
        })
