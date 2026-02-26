import boto3
import json


def classify_sarcasm_with_bedrock_llm(text):
    """
    Use: This function is used to predict if the given text is sarcastic or not
    --------------------------------------------------------------------------
    text: String
    --------------------------------------------------------------------------
    return "Yes" or "No"
    """

    try:
        bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name='ap-south-1'   # <-- IMPORTANT FIX
        )

        system_prompt = (
            "You have to understand Bengali and Hindi language as well but give output in English language only. "
            "Your output should not contain any explanation or process for detecting the category. "
            "All your output must be in English language only, and must be exactly one of these two options: "
            "'Sarcasm' or 'Not Sarcasm'."
        )

        prompt_prefix = "\n\nHuman: "

        prompt_instructions = (
            "CESC is a company that provides electricity to customers in Kolkata and its suburbs. "
            "Classify the following tweet as either 'Sarcasm' or 'Not Sarcasm' based on the descriptions below."
        )

        prompt_categories = """
Categories:
Sarcasm: Sarcasm is a form of verbal irony where someone says the opposite of what they truly mean, often in a mocking or critical manner. In the context of tweets about an electricity board like CESC, sarcasm might involve:
- Praising CESC for its "excellent" service when the service is actually poor
- Commending CESC's "fair" practices when the practices are actually monopolistic
- Thanking CESC for "memorable nights" when there are frequent power outages
- Expressing "gratitude" towards CESC for inconveniences caused by power cuts or voltage fluctuations

Not Sarcasm: Tweets which are not classified as Sarcasm. These tweets may include:
- Genuine complaints or criticism about CESC's services
- Factual statements or queries related to CESC
- Neutral or positive mentions of CESC without any irony or mockery
"""

        prompt_text = f"\nTweet: {text}"

        prompt_response_start = "\nAssistant: "

        prompt_example = """
Examples:
Tweet: Such a beautiful night, we are witnessing all twinkling stars because of you CESC, no electricity. Thank you CESC for such memorable nights.
Sarcasm
Tweet: Many thanks. This heat to keep the current off from tomorrow night until 4:30 a.m. Also, if you don't mind, thank you for showing the courtesy of continuing to play the Current Off game about 5 times after 4:30am and giving the current after your mind is full.
Sarcasm
Tweet: Situation getting worse with the rise in temperature, Fuckers CESC please give electricity as soon as possible
Not Sarcasm
Tweet: my power cut issue is resolved within 24hrs of the complaint.... Really appreciate it
Sarcasm
Tweet: Motherfucker! what else we expect from CESC than daily power cut of 2 hours in this regards they are way ahead of other electricity boards!
Not Sarcasm
"""

        prompt = (
            system_prompt
            + prompt_prefix
            + prompt_instructions
            + prompt_categories
            + prompt_text
            + prompt_example
            + prompt_response_start
        )

        prompt_config = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        body = json.dumps(prompt_config)

        modelId = "anthropic.claude-3-haiku-20240307-v1:0"
        accept = 'application/json'
        contentType = 'application/json'

        response = bedrock.invoke_model(
            body=body,
            modelId=modelId,
            accept=accept,
            contentType=contentType
        )

        response_body = json.loads(response.get('body').read())
        output = response_body.get('content', [])

        if output:
            output_text = output[0].get('text', '').strip()
            if output_text == "Sarcasm":
                return "Yes"
            elif output_text == "Not Sarcasm":
                return "No"
            else:
                print(f"⚠️ Unexpected output from model: {output_text}")
                return None
        else:
            print("⚠️ No output from the model.")
            return None

    except Exception as e:
        print(f"❌ Error while checking sarcasm tag of the message: {e}")
        return None


# ============================================
# MAIN FUNCTION
# ============================================
def main():
    test_sentences = [
        "Thank you CESC for another wonderful night without electricity, really enjoying the darkness.",
        "There is no power in my area since morning, please resolve it as soon as possible.",
        "Great job CESC, cutting power during peak summer, truly brilliant planning!",
        "My meter issue is resolved within 24 hours. Thanks for the quick support.",
        "No electricity for 3 hours now, very frustrating experience.",
        "Wow CESC, every day power cut, you guys are just amazing at this!"
    ]

    print("\n===== CESC Sarcasm Detection Test =====\n")

    for i, text in enumerate(test_sentences, start=1):
        print(f"Test {i}: {text}")
        result = classify_sarcasm_with_bedrock_llm(text)
        print(f"Prediction: {result}")
        print("-" * 60)


# ============================================
# ENTRY POINT
# ============================================
if __name__ == "__main__":
    main()
