import os
from typing import Dict, Any
import boto3

class ClarificationAgent:
    def __init__(self):
        self.bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION"))
        self.model_id = os.getenv("BEDROCK_MODEL_ID")

    def process(self, state: Dict[str, Any]):
        system_prompts = [{"text": """
You are a helpful customer support assistant for an electricity billing company.
The user's message was not clear enough to map to a specific billing or account issue workflow.
Only reply in English "Thanks for reaching out to CESE Helpline. Could you please provide a bit more details about the issue you're facing with your electricity bill or account? That would help me better understand how I can assist you." 
Do NOT use markdown code blocks.
"""}]

        response = self.bedrock.converse(
            modelId=self.model_id,
            messages=[
                {"role": "user", "content": [{"text": state["normalized_message"]}]}
            ],
            system=system_prompts
        )

        clarification_message = response['output']['message']['content'][0]['text']
        
        # In a real app we would output this via websocket, but for console simulaton we print:
        print(f"\nAastha: {clarification_message}")
        
        # Reset state parameters since we've now clarified/greeted
        state["intent"] = "WAITING_ON_USER"
        state["confidence"] = 0.0
        state["clarification_needed"] = False
        state["next_agent"] = "USER_INPUT_NODE"
        
        return state
