import json
import logging
import requests
import re
import time
import boto3
import typing

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BASE_URL = "https://dice-uat.cesc.co.in"
COMP_SRC = "whatsapp"

TIMEOUT = 10
RETRIES = 2

bedrock = boto3.client("bedrock-runtime", region_name="ap-south-1")


# ---------------------------------------------------
# Bedrock Response Formatter
# ---------------------------------------------------
def bedrock_response(message, session=None):
    res =  {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": "SupplyOff",
            "function": "Supply-Off",
         
            "functionResponse": {

                "responseBody": {
                    "TEXT": {
                        "body": json.dumps(message)
                    }
                }
            },
               "sessionAttributes": session or {},
            "promptSessionAttributes": {},
        }
    }

    print(res)

    return res


# ---------------------------------------------------
# Safe API Call
# ---------------------------------------------------
def safe_api_call(method, url, headers=None, payload=None):


    print(f"The paylod for {url} is\n {payload} ")

    for _ in range(RETRIES):

        try:

            if method == "GET":
                r = requests.get(url, headers=headers, timeout=TIMEOUT)

            else:
                r = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)

            r.raise_for_status()

            x =  r.json()
            print(f"Response for {url} is \n {x}")
            return x

        except Exception as e:

            logger.error(f"API error: {e}")

            time.sleep(1)

    return {"error": True}


# ---------------------------------------------------
# JWT Token
# ---------------------------------------------------
def get_token():

    r = requests.get(f"{BASE_URL}/dicekey/botKeyStore.txt")

    initial_token = r.text.strip()

    payload = {"client_token_vl": initial_token}

    r = requests.post(f"{BASE_URL}/api/getSecretKey", json=payload)

    return r.json()["access_token"]


# ---------------------------------------------------
# Claude Sonnet Intent Detection
# ---------------------------------------------------
def detect_intent_llm(text):

    prompt = f"""
Classify electricity complaint.

Possible intents:
SUPPLY_OFF
VOLTAGE_FLUCTUATION
CHECK_STATUS
OTHER

User message:
{text}

Return only intent name.
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 20,
        "messages": [{"role": "user", "content": prompt}]
    }

    response = bedrock.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        body=json.dumps(body)
    )

    result = json.loads(response["body"].read())

    return result["content"][0]["text"].strip()


# ---------------------------------------------------
# Fast Intent Detection
# ---------------------------------------------------
def detect_intent(text):

    t = text.lower()

    if "status" in t or "docket" in t:
        return "CHECK_STATUS"

    if "voltage" in t:
        return "VOLTAGE_FLUCTUATION"

    if "power" in t or "light" in t or "supply" in t:
        return "SUPPLY_OFF"

    return detect_intent_llm(text)


# ---------------------------------------------------
# Complaint code mapping
# ---------------------------------------------------
def get_complaint_code(intent):

    if intent == "SUPPLY_OFF":
        return "1"

    if intent == "VOLTAGE_FLUCTUATION":
        return "14"

    return "1"


# ---------------------------------------------------
# Extract mobile
# ---------------------------------------------------
def extract_mobile(text):

    m = re.search(r"\b\d{10}\b", text)

    return m.group() if m else None


# ---------------------------------------------------
# Extract docket
# ---------------------------------------------------
def extract_docket(text):

    m = re.search(r"\b\d{6,}\b", text)

    return m.group() if m else None


#-----------------------------------------------------
# Checking  consumer
# ----------------------------------------------------
def check_consumer(token, mobile):
     headers = {"Authorization": f"Bearer {token}"}
     payload = 	{ "mobile": "9874463684", "comp_src": "whatsapp"} 
     return safe_api_call(
        "POST",
        f"{BASE_URL}/api/chkconsumer",
        headers,
        payload
     )



# ---------------------------------------------------
# Restriction checks
"""
Creating Codes
to be compared later on
"""
# ---------------------------------------------------
def check_restrictions(data) -> int:

    if data.get("LCC", {}).get("LockedStat") == "Y":
        return 2
        # return "Your connection is LCC disconnected."
   
    if len(data.get("BURNT_METER",[])) >0:
        return 5
        
        # return "A burnt meter complaint already exists."
  
      
    if data.get("COMMERCIAL_DISC", {}).get("DISC") == "YES":
        return 3
        # return "Your connection is commercially disconnected."

    if data.get("Outage") == "Y":
        return 4
        # return "There is a known outage in your area."

   

    if data.get("Incomplete_2hr_more") == "Y":
        return 6
        # return "A complaint was already registered within the last 2 hours."

    if data.get("NearbyComplaint") == "Y":
        return 7
        # return "A nearby complaint already exists nearby."

    if data.get("ExistingDkt"):
        return 1

        # return f"Complaint already exists. Docket number: {data.get('ExistingDkt')}"


    return 0
    # return None


# ---------------------------------------------------
# Get Burnt Meter Details
# ---------------------------------------------------
def get_burnt_meter_details(token, docket_no, custid):
    headers = { 
        "Authorization": f"Bearer {token}"
    }

    payload = 	{ 
    "custid": custid, 
    "docket_no": docket_no, 
    "comp_src": "whatsapp" 
    } 

    return safe_api_call(
        "POST",
        f"{BASE_URL}/api/BurntMeterDetails",
        headers,
        payload
    )




# ---------------------------------------------------
# Complaint Status
# ---------------------------------------------------
def get_complaint_status(token, docket, mobile = None):

    headers = {"Authorization": f"Bearer {token}"}

    if  mobile:
        payload = {"docket": docket,"mobile": mobile,"comp_src": COMP_SRC}
    else:
        payload = {"docket": docket,"comp_src": COMP_SRC}




    return safe_api_call(
        "POST",
        f"{BASE_URL}/api/getComplaintStatus",
        headers,
        payload
    )


# ---------------------------------------------------
# Parse event
# ---------------------------------------------------
def parse_event(event):

    params = {}

    for p in event.get("parameters", []):
        params[p["name"]] = p["value"]

    session = event.get("sessionAttributes", {})

    text = event.get("inputText", "")

    mobile = params.get("mobile") or session.get("mobile")

    custid = params.get("custid")

    docket_no = params.get("docket_no")

    complaint_status = params.get("complaint_type")

    if not complaint_status:
        complaint_status = "SUPPLY_OFF"

    if params.get("mobile"):
        session["mobile"] = params["mobile"]

    return text, mobile, custid, session, docket_no, complaint_status


# ---------------------------------------------------
# Lambda handler
# ---------------------------------------------------
def lambda_handler(event, context):

    logger.info(event)

    try:

        user_text, mobile, custid, session, docket_no, complaint_status = parse_event(event)

        intent = detect_intent(user_text)
        
        complaint_code = get_complaint_code(intent)

        token = get_token()

        headers = {"Authorization": f"Bearer {token}"}

        if docket_no:
            status = get_complaint_status(token, docket_no)
            if status.get("error"):
                return bedrock_response(
                    "Error fetching your docket details",
                    session
                )
            data = status.get("data")
            msg = data.get("docket_status_msg")
            return bedrock_response(f"Your docket status is as follows\n{msg}")

        if not mobile:
            details = safe_api_call(
            "POST",
            f"{BASE_URL}/api/consumerDetails",
            headers,
            {
                "custid": custid,
                "comp_src": COMP_SRC
            }
        )
            if details.get("error"):
                return bedrock_response(
                    "We are unable to find your mobile no ",
                    session
                )
            data = details.get("data")
            mobile = data.get("MOB_NO")
            if not mobile:
                return bedrock_response(
                    "We are unable to find your mobile no ",
                    session
                )
            # mobile = extract_mobile(user_text)

      

        # ------------------------------------------------
        # Complaint status flow
        # ------------------------------------------------

        if intent == "CHECK_STATUS":

            docket = extract_docket(user_text)

            if not docket:

                return bedrock_response(
                    "Please provide your docket number to check complaint status.",
                    session
                )

            resp = get_complaint_status(token, docket, mobile)

            if resp.get("error"):

                return bedrock_response(
                    "Unable to fetch complaint status currently.",
                    session
                )

            data = resp.get("data")

            if (not data )or data==[]:
                return generate_docket(session,headers,user_text, mobile, custid, complaint_code, consumer_no=None)
               
            status = data.get("status")

            if status == "I":
                msg = f"Complaint {docket} is currently in progress."

            elif status == "C":
                msg = f"Complaint {docket} has been resolved."

            else:
                msg = f"Complaint {docket} status: {status}"

            return bedrock_response(msg, session)

        # ------------------------------------------------
        # Ask for mobile
        # ------------------------------------------------

        if not mobile and not custid:

            return bedrock_response(
                "Please provide your registered mobile number or customer ID.",
                session
            )

        # ------------------------------------------------
        # Consumer mapping
        # ------------------------------------------------

        if not custid:

            chk = safe_api_call(
                "POST",
                f"{BASE_URL}/api/chkconsumer",
                headers,
                {"mobile": mobile, "comp_src": COMP_SRC}
            )

            consumers = chk.get("data", {}).get("LT", {}).get("customer_id", [])
            consumers_lt = chk.get("data",{}).get("HT", {}).get("consumer_no", [])

            if not consumers and not consumers_lt:

                return bedrock_response(
                    "No consumer mapping found for this mobile number.",
                    session
                )

            if len(consumers) + len (consumers_lt) >5:
                return bedrock_response(
                    "Since the user has more the 5 consumers/customers Please ask the user politely to enter the CID/ Consumer No"
                )    

            if len(consumers) > 1 or len(consumers_lt) >1:

                msg = "Multiple consumers are linked to this mobile number:\n\n"

                for i, cid in enumerate(consumers, start=1):

                    details = safe_api_call(
                        "POST",
                        f"{BASE_URL}/api/consumerDetails",
                        headers,
                        {
                            "mobile": mobile,
                            "custid": cid,
                            "comp_src": COMP_SRC
                        }
                    )

                    addr = ""

                    if not details.get("error"):
                        d = details.get("data", {})
                        addr = f"{d.get('ADDR_TWO','')} {d.get('ADDR_THREE','')}"

                    msg += f"{i}. CID {cid} - {addr}\n"

                for i, cid in enumerate(consumers_lt, start=1):

                    details = safe_api_call(
                        "POST",
                        f"{BASE_URL}/api/consumerDetails",
                        headers,
                        {
                            "mobile": mobile,
                            "custid": cid,
                            "comp_src": COMP_SRC
                        }
                    )

                    addr = ""

                    if not details.get("error"):
                        d = details.get("data", {})
                        addr = f"{d.get('ADDR_TWO','')} {d.get('ADDR_THREE','')}"

                    msg += f"{i}. CID {cid} - {addr}\n"


                msg += "Ask the user to select any one of the following CIDs"

                return bedrock_response(msg, session)

            custid = consumers[0]

        
        # Till here we have both custId and mobile number
        #--------------------------------------------
        #Classifying user as LT or HT
        #--------------------------------------------

        customer_type = ""

        resp = check_consumer(token, mobile)
        if resp.get("error"):

            return bedrock_response(
                "We are unable to detect your customer type.Please come again later",
                session
            )

        data = resp.get("data",{})
        custIds = data.get("LT").get("customer_id")
        consumIds = data.get("HT").get("consumer_no")

        if custid in custIds:
            customer_type = "LT"
        else:
            customer_type = "HT"


        # ------------------------------------------------
        # Consumer details - Till here we have both mobile and custid
        # ------------------------------------------------

        details = safe_api_call(
            "POST",
            f"{BASE_URL}/api/consumerDetails",
            headers,
            {
                "mobile": mobile,
                "custid": custid,
                "comp_src": COMP_SRC
            }
        )

        if details.get("error"):

            return bedrock_response(
                "Unable to retrieve consumer details.",
                session
            )

        data = details.get("data", {})
        print(f"The data I got is {data}")


        

        restriction: int = check_restrictions(data)


        if restriction == 1:  # If docket exists
            docket_no = data.get('ExistingDkt')



            # To be done for LT users
            complaint_status = get_complaint_status(token , docket_no, mobile)
            if (complaint_status.get("error")):
                return bedrock_response(
                    f"Your docket no exists as {docket_no} but error fetching docket details",
                    session
                )

            """
                    "data": { 
                "docket": "11250339", 
                "status": "I", 
                "con_add": "9/1/B RAM MOHAN BERA LANE KOLKATA 700046", 
                "site_latitude": "22.5456005", 
                "site_longitude": "88.3762846", 
                "vehicle_location": { 
                    "vno": "WB04H9758", 
                    "record_time": "2026-01-29 10:01:12", 
                    "latitude": 22.565946, 
                    "longitude": 88.358127 
                } 
            }, 
            """
            data = complaint_status.get("data", {})
            
            return bedrock_response(
                f"Let user know his docket number already exists by specifically specifing his docket no exists with following data {data}",
                session
            )
    

        if restriction == 2:
            rgn_cd = data.get("RGN_CD", "")

            if rgn_cd in ["CRO", "NRO", "NSRO", ""]:
                data_str = "Districts: CCD, CND, ND & NSD | Office: EASTERN BUILDING, 3rd Floor, 15/1 Chowringhee Square, Kol-69 | Landmark: Near Aaykar Bhavan & Peerless Building | Contact: 2228-8041 / 42"

            elif rgn_cd == "HRO":
                data_str = "Districts: HD & SERD | Office: EASTERN BUILDING, 4th Floor, 15/1 Chowringhee Square, Kol-69 | Landmark: Near Aaykar Bhavan & Peerless Building | Contact: 2228-8041 / 42"

            elif rgn_cd in ["SRO", "SWRO"]:
                data_str ="Districts: CSD, SD, SWD & WSD | Office: ROLLS PRINT UNIT, 1 Taratalla Road, Kolkata-700088 | Landmark: Opp. Modern Bakery | Contact: 2401-0001 / 0017"

            else:
                data_str = "Your LCC is locked but your region details couldn't be found please contact a human operator"

            return bedrock_response(
                f"Please go to the regional office mentioned with following details\n{data_str}",
                session
            )

        if restriction == 3:
            bill_details = data.get("BILLINFO")
            if not bill_details:
                return bedrock_response(
                f"You have a commercial disconnection.We are having trouble fetching your bill details",
                session
            )


            return bedrock_response(
                f"We have a commerical disconnection for you .The bill details are {bill_details}",
                session
            )
            
        if restriction == 4: #outage
            return bedrock_response(
                f"There is an outage in your area as of now",
                session
            )
        if restriction == 5: # ExistingBurntMeterDkt

            docketNo = data.get("BURNT_METER",[])[0].get("DKT_NUM","")


            if docketNo == "":
                return bedrock_response(
                    f"You have a burnt meter but your docket no cannot be identified.Please contact a human operator",
                    session
                )
            

            meter_details = get_burnt_meter_details(
                token, docketNo, custid
            )

            if meter_details.get("error"):
                return bedrock_response(
                    f"You have a burnt meter but your docket details cannot be found.Please contact a human operator",
                    session
                )

            burn_meter_details = meter_details.get("data", {})
            pdf_url = meter_details.get("url","")
            if data == {}:
                return bedrock_response(
                    f"You have a burnt meter but your docket details cannot be found.Please contact a human operator",
                    session
                )
            return bedrock_response(
                f"""
                Your burnmeter details are as follows\n{burn_meter_details} 
                with pdf url={pdf_url if pdf_url !=""  else "Not found"}
                """
            )

        # Not checking for restriction 6 or 7 since there reasons will be provided by docket_generation only


        consumer_no = data.get("CONS_NUM")


        return generate_docket(session,headers,user_text, mobile, custid, complaint_code)

    
    except Exception as e:

        logger.error(e)

        return bedrock_response(
            "Unexpected system error occurred while processing your request."
        )


def generate_docket(session,headers,user_text, mobile, custid, complaint_code, consumer_no=None):

    # ------------------------------------------------
    # Create complaint
    # ------------------------------------------------

    


    docket = safe_api_call(
        "POST",
        f"{BASE_URL}/api/genSupplyCrmDkt",
        headers,
        {
            "custid": custid,
            "consumer_no": consumer_no,
            "mobile": mobile,
            "comp": complaint_code,
            "comp_src": COMP_SRC,
            "dtl": user_text
        }
    )

    if "error" in docket:
        return bedrock_response(
            f"Failure to register your docket complaint .Please contact the human operator"
        )



    return bedrock_response(
        f"The api respnse is this.Provide user with reason in a simple format {docket}",
        session
    )
