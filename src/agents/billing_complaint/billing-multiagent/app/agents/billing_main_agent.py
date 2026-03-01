import os
import re
import json
from typing import Dict, Any
import boto3
from dotenv import load_dotenv

from app.policies.otp_policy import INTENT_OTP_POLICY
from app.mocks.mock_otp import trigger_mock_otp

load_dotenv()

CONFIDENCE_THRESHOLD = 0.90
MOCK_OTP = os.getenv("MOCK_OTP", "true").lower() == "true"


class BillingComplaintMainAgent:

    def __init__(self):
        self.bedrock = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION")
        )

        self.model_id = os.getenv("BEDROCK_MODEL_ID")
        self.guardrail_id = os.getenv("BEDROCK_GUARDRAIL_ID")

        self.lambda_client = boto3.client(
            "lambda",
            region_name=os.getenv("AWS_REGION")
        )

        self.tools = self._define_tools()

    # ------------------------------------------------
    # TOOL DEFINITION FOR BEDROCK FUNCTION CALLING
    # ------------------------------------------------

    def _define_tools(self):
        return [
            {
                "name": "trigger_otp_verification",
                "description": "Trigger OTP verification if required by policy.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "cid": {"type": "string"}
                        },
                        "required": ["cid"]
                    }
                }
            }
        ]

    # ------------------------------------------------
    # INTENT CLASSIFICATION
    # ------------------------------------------------

    def classify_intent(self, state: Dict[str, Any]):

        valid_intents = list(INTENT_OTP_POLICY.keys())
        system_prompts = [{"text": f"""
You are a Billing Intent Classifier.

You MUST choose the intent from the following list of valid intents:
{valid_intents}

Return strict JSON:
{{
  "intent": "<CHOSEN_INTENT>",
  "confidence": 0.95
}}
"""}]

        response = self.bedrock.converse(
            modelId=self.model_id,
            messages=[
                {"role": "user", "content": [{"text": state["normalized_message"]}]}
            ],
            system=system_prompts,
            guardrailConfig={
                "guardrailIdentifier": self.guardrail_id,
                "guardrailVersion": "DRAFT" # Using DRAFT as placeholder, update if needed
            } if self.guardrail_id else None
        )

        text_content = response['output']['message']['content'][0]['text']
        
        # Robustly extract JSON block
        json_str = None
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Fallback to finding first { and last }
            start_idx = text_content.find('{')
            end_idx = text_content.rfind('}')
            if start_idx != -1 and end_idx != -1:
                json_str = text_content[start_idx:end_idx+1]

        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
                
        # If all parsing fails, return a default clarification intent
        return {"intent": "CLARIFICATION", "confidence": 1.0}

    # ------------------------------------------------
    # REQUEST OTP VIA TOOL CALL
    # ------------------------------------------------

    def request_otp_tool_call(self, state: Dict[str, Any]):

        system_prompts = [{"text": """
OTP is required for this intent.
You MUST call trigger_otp_verification tool.
Do not return JSON.
"""}]

        response = self.bedrock.converse(
            modelId=self.model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": f"Intent: {state['intent']} | CID: {state['CID']}"}]
                }
            ],
            system=system_prompts,
            toolConfig={
                "tools": [{"toolSpec": tool} for tool in self.tools]
            }
        )

        tool_calls = [
            content_block['toolUse']
            for content_block in response['output']['message']['content']
            if 'toolUse' in content_block
        ]
        
        return tool_calls[0] if tool_calls else None

    # ------------------------------------------------
    # MAIN PROCESS
    # ------------------------------------------------

    def process(self, state: Dict[str, Any]):

        # Step 1: Classify
        if not state.get("intent"):
            result = self.classify_intent(state)
            state["intent"] = result["intent"]
            state["confidence"] = result["confidence"]

        # Step 2: Confidence check or explicit Clarification
        if state["confidence"] < CONFIDENCE_THRESHOLD or state["intent"] == "CLARIFICATION":
            state["clarification_needed"] = True
            state["next_agent"] = "CLARIFICATION_NODE"
            return state

        # Step 3: Check OTP policy
        otp_required = INTENT_OTP_POLICY.get(state["intent"], False)

        if not otp_required:
            state["next_agent"] = f"{state['intent']}_JOURNEY_AGENT"
            return state

        # Step 4: OTP required
        if state["OTP_verification_status"] == "VERIFIED":
            state["next_agent"] = f"{state['intent']}_JOURNEY_AGENT"
            return state

        # Step 5: Ask LLM to call tool
        tool_call = self.request_otp_tool_call(state)

        # Step 6: MOCK ONLY OTP EXECUTION
        if MOCK_OTP:
            trigger_mock_otp(tool_call["input"]["cid"])
        else:
            self.lambda_client.invoke(
                FunctionName=os.getenv("OTP_LAMBDA_NAME"),
                InvocationType="RequestResponse",
                Payload=json.dumps(tool_call["input"])
            )

        state["tool_invoked"] = tool_call["name"]
        state["next_agent"] = "OTP_VERIFICATION_NODE"

        return state