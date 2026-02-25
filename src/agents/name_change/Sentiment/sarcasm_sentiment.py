import boto3
import json

from senti_sar_prompt import (
    SARCASM_SYSTEM_PROMPT,
    SARCASM_PROMPT_INSTRUCTIONS,
    SARCASM_PROMPT_EXAMPLES,
    SARCASM_PROMPT_FORMAT,
    SENTIMENT_SYSTEM_PROMPT,
    SENTIMENT_PROMPT_INSTRUCTIONS,
    SENTIMENT_PROMPT_EXAMPLES,
    SENTIMENT_PROMPT_FORMAT
)


def get_bedrock_client():
    return boto3.client(
        service_name="bedrock-runtime",
        region_name="ap-south-1"
    )


# ============================================
# SARCASM CLASSIFIER
# ============================================

def classify_sarcasm(text):
    try:
        bedrock = get_bedrock_client()

        prompt = (
            SARCASM_SYSTEM_PROMPT + "\n\n"
            + SARCASM_PROMPT_INSTRUCTIONS + "\n\n"
            + SARCASM_PROMPT_EXAMPLES + "\n"
            + SARCASM_PROMPT_FORMAT.format(user_text=text)
        )

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 50,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        })

        response = bedrock.invoke_model(
            body=body,
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            accept="application/json",
            contentType="application/json"
        )

        response_body = json.loads(response["body"].read())
        output = response_body.get("content", [])

        if not output:
            return None

        result = output[0].get("text", "").strip()
        return result

    except Exception as e:
        print(f"❌ Sarcasm detection error: {e}")
        return None


# ============================================
# SENTIMENT CLASSIFIER
# ============================================

def classify_sentiment(text):
    try:
        bedrock = get_bedrock_client()

        prompt = (
            SENTIMENT_SYSTEM_PROMPT + "\n\n"
            + SENTIMENT_PROMPT_INSTRUCTIONS + "\n"
            + SENTIMENT_PROMPT_EXAMPLES + "\n"
            + SENTIMENT_PROMPT_FORMAT.format(user_text=text)
        )

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 50,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        })

        response = bedrock.invoke_model(
            body=body,
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            accept="application/json",
            contentType="application/json"
        )

        response_body = json.loads(response["body"].read())
        output = response_body.get("content", [])

        if not output:
            return None

        result = output[0].get("text", "").strip()
        return result

    except Exception as e:
        print(f"❌ Sentiment detection error: {e}")
        return None


# ============================================
# PIPELINE FUNCTION
# ============================================

def process_message(text):
    sarcasm_result = classify_sarcasm(text)

    if sarcasm_result == "Sarcasm":
        # Business rule: sarcasm always treated as negative
        sentiment_result = "Negative"
    elif sarcasm_result == "Not Sarcasm":
        sentiment_result = classify_sentiment(text)
    else:
        sentiment_result = None

    return {
        "input_text": text,
        "sarcasm": sarcasm_result,
        "sentiment": sentiment_result
    }


# ============================================
# MAIN FUNCTION
# ============================================

def main():
    print("\n===== CESC Sarcasm + Sentiment Detector =====")
    print("Type your sentence and press Enter.")
    print("Type 'exit' to quit.")
    print("===========================================\n")

    while True:
        user_input = input("Enter sentence: ").strip()

        if user_input.lower() == "exit":
            print("\n👋 Exiting. Goodbye!")
            break

        if not user_input:
            print("⚠️ Please enter a valid sentence.\n")
            continue

        result = process_message(user_input)

        print("\nResult:")
        print(f"  Sarcasm  : {result['sarcasm']}")
        print(f"  Sentiment: {result['sentiment']}")
        print("-" * 60)


# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":
    main()
