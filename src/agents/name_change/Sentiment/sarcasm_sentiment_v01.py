import boto3
import json
import pandas as pd

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


# ============================================
# BEDROCK CLIENT
# ============================================

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
            "max_tokens": 30,
            "messages": [{"role": "user", "content": prompt}]
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
            return "No"

        result = output[0].get("text", "").strip()
        return "Yes" if result == "Sarcasm" else "No"

    except Exception as e:
        print(f"❌ Sarcasm detection error: {e}")
        return "No"


# ============================================
# SENTIMENT CLASSIFIER (3-CLASS ONLY)
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
            "max_tokens": 30,
            "messages": [{"role": "user", "content": prompt}]
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

        return output[0].get("text", "").strip()

    except Exception as e:
        print(f"❌ Sentiment detection error: {e}")
        return None


# ============================================
# PIPELINE FUNCTION
# ============================================

def process_message(text):
    sarcasm = classify_sarcasm(text)

    if sarcasm == "Yes":
        sentiment = "Negative"
    else:
        sentiment = classify_sentiment(text)

    return {
        "text": text,
        "sarcasm": sarcasm,
        "sentiment": sentiment
    }


# ============================================
# EXCEL PROCESSING (WITH ROW COUNT)
# ============================================

def process_excel(input_excel_path, output_excel_path):
    df = pd.read_excel(input_excel_path)

    total_rows = len(df)
    print(f"\n📄 Total rows to process: {total_rows}\n")

    llm_results = []
    sarcasm_results = []
    status_results = []

    for idx, row in df.iterrows():
        current_row = idx + 1
        print(f"🔄 Processing row {current_row} / {total_rows}")

        text = str(row["Post"]).strip()
        excel_sentiment = str(row["Sentiment"]).strip().capitalize()

        result = process_message(text)

        llm_sentiment = result["sentiment"]
        sarcasm_value = result["sarcasm"]

        status = "Matched" if llm_sentiment == excel_sentiment else "Not Matched"

        llm_results.append(llm_sentiment)
        sarcasm_results.append(sarcasm_value)
        status_results.append(status)

    df["llm_result"] = llm_results
    df["sarcasm"] = sarcasm_results
    df["status"] = status_results

    df.to_excel(output_excel_path, index=False)

    print("\n✅ Excel processing completed successfully")
    print(f"📁 Output file: {output_excel_path}")


# ============================================
# MAIN
# ============================================

def main():
    input_excel = "EVOC  analysis- Posts-Sentiment analysis repository.xlsx"
    output_excel = "EVOC_analysis_with_llm_results.xlsx"

    print("\n===== CESC SENTIMENT + SARCASM VALIDATION =====")
    process_excel(input_excel, output_excel)
    print("==============================================\n")


# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":
    main()
