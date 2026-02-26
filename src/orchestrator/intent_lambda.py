# Lambda Name : intentDetectionTool

import json
import boto3

ENDPOINT_NAME = "nli-deberta-intent-router-v5"

runtime = boto3.client("sagemaker-runtime")

INTENT_HYPOTHESES = {
    "Helpline Information":
        "The user is asking for customer support or helpline contact information for electricity services.",

    "Name Change":
        "The user is requesting a change or correction of the consumer name or ownership on an electricity account.",

    "Green Tariff":
        "The user is asking about enrolling in or understanding a green or renewable energy tariff plan.",

    "New Connection":
        "The user is asking about applying for or tracking a new electricity supply connection.",

    "Maintenance Outages":
        "The user is asking about planned maintenance outages or restoration timelines for electricity supply.",

    "Report Supply Off":
        "The user is reporting an unplanned power outage or loss of electricity supply at their location.",

    "Bill payment":
        "The user is asking about paying their electricity bill or issues related to bill payments.",

    "Complaints":
        "The user is raising or following up on a complaint about electricity services."
}


def predict_intent(query: str):
    """
    Sends query to SageMaker endpoint and returns best intent + score
    """

    payload = {
        "query": query,
        "hypotheses": INTENT_HYPOTHESES
    }

    response = runtime.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Body=json.dumps(payload),
    )

    result = json.loads(response["Body"].read())
    scores = result["scores"]

    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]

    return best_intent, round(best_score, 4)



def response_composer(message_version, action_group, function, message):
    response = {
        'messageVersion': message_version,
        'response': {
            'actionGroup': action_group,
            'function': function,
            'functionResponse': {
                    'responseBody': {
                            'TEXT': {
                                'body': message
                            }
                    }
            }     
        }
    }

    return response



def lambda_handler(event, context):
    # TODO implement

    print(event)

    try:
        print(event)
        action_group = event['actionGroup']
        function = event['function']
        message_version = event.get('messageVersion',1)
        parameters = event.get('parameters', [])

        param_dict = {param['name'].lower(): str(param['value']) for param in parameters}
        print(f"Param Dict : {param_dict}")
        print(function)

        query = param_dict.get('user_input', 'hi agent')
        intent, score = predict_intent(query)       

        response = response_composer(message_version, action_group, json.dumps({'intent': intent, 'confidence_score': score}))
        print(response)

        return response
    
    except Exception as e:
    
        response = {
            'statusCode': "404",
            'body': f'Error: {str(e)}'
        }

        print(response)
        return response

