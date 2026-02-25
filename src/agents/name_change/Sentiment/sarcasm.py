import boto3
import json

from prompts import (
    SYSTEM_PROMPT,
    PROMPT_INSTRUCTIONS,
    PROMPT_EXAMPLES,
    PROMPT_FORMAT
)


def classify_sarcasm_with_bedrock_llm(text):
    """
    Predict if the given text is sarcastic or not.
    Returns: "Sarcasm" or "Not Sarcasm"
    """

    try:
        bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name='ap-south-1'
        )

        prompt = (
            SYSTEM_PROMPT + "\n\n"
            + PROMPT_INSTRUCTIONS + "\n\n"
            + PROMPT_EXAMPLES + "\n"
            + PROMPT_FORMAT.format(user_text=text)
        )

        prompt_config = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 50,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        body = json.dumps(prompt_config)

        model_id = "anthropic.claude-3-haiku-20240307-v1:0"

        response = bedrock.invoke_model(
            body=body,
            modelId=model_id,
            accept="application/json",
            contentType="application/json"
        )

        response_body = json.loads(response.get("body").read())
        output = response_body.get("content", [])

        if not output:
            print("⚠️ No output from model")
            return None

        output_text = output[0].get("text", "").strip()

        if output_text == "Sarcasm":
            return "Sarcasm"
        elif output_text == "Not Sarcasm":
            return "Not Sarcasm"
        else:
            print(f"⚠️ Unexpected output from model: {output_text}")
            return None

    except Exception as e:
        print(f"❌ Error while checking sarcasm tag: {e}")
        return None


# ============================================
# MAIN FUNCTION (USER INPUT)
# ============================================

def main():
    print("\n===== CESC Sarcasm Detection =====")
    print("Type your sentence and press Enter.")
    print("Type 'exit' to quit.")
    print("=================================\n")

    while True:
        user_input = input("Enter sentence: ").strip()

        if user_input.lower() == "exit":
            print("\n👋 Exiting Sarcasm Detector. Goodbye!")
            break

        if not user_input:
            print("⚠️ Please enter a valid sentence.\n")
            continue

        result = classify_sarcasm_with_bedrock_llm(user_input)

        print(f"Prediction: {result}")
        print("-" * 60)


# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":
    main()
