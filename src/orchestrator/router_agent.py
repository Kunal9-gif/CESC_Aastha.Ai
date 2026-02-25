import boto3
import json
from typing import Literal
from ...state.state import AgentState
from dotenv import load_dotenv
load_dotenv()
import os
from utils.json_parser import extract_json_from_text

# ================= CONFIG =================
AWS_REGION = os.getenv("AWS_REGION")
BEDROCK_AGENT_ID = os.getenv("ORCHESTRATOR_AGENT_ID")
BEDROCK_AGENT_ALIAS_ID = os.getenv("ORCHESTRATOR_AGENT_ALIAS_ID")

bedrock_agent_runtime = boto3.client(
    service_name="bedrock-agent-runtime",
    region_name=AWS_REGION
)

# ==========================================================
# Bedrock Invocation
# ==========================================================
def invoke_bedrock_agent(session_id: str, input_text: str) -> str:
    try:
        response = bedrock_agent_runtime.invoke_agent(
            agentId=BEDROCK_AGENT_ID,
            agentAliasId=BEDROCK_AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=input_text
        )

        completion = ""
        for event in response.get("completion"):
            chunk = event["chunk"]
            if chunk:
                completion += chunk["bytes"].decode()

        print("Bedrock Agent Raw Response:\n", completion)
        return completion

    except Exception as e:
        print(f"Error invoking Bedrock Agent: {e}")
        return ""

# ==========================================================
# Router Agent
# ==========================================================
def router_agent(state: AgentState) -> dict:
    print("---ROUTER AGENT (BEDROCK)---")

    translated_text = state.get("translated_text", "")
    language = state.get("language", "")
    session_id = state.get("session_id", "session_123")

    active_journey = state.get("active_journey")
    journey_stack = state.get("journey_stack") or []
    pending_switch = state.get("pending_journey_switch")

    graph_to_route = {
        "name_change_graph": "NAME_CHANGE",
        "report_supply_off_graph": "REPORT_SUPPLY_OFF",
        "helpline_information_graph": "HELPLINE_INFORMATION"
    }

    route_to_graph = {v: k for k, v in graph_to_route.items()}

    # ==========================================================
    # 1️⃣ Handle Pending Journey Switch (CONFIRMATION STAGE)
    # ==========================================================
    if pending_switch:

        payload = {
            "mode": "JOURNEY_SWITCH_CONFIRMATION",
            "current_journey": active_journey,
            "requested_journey": pending_switch,
            "user_input": translated_text
        }

        agent_response = extract_json_from_text(
            invoke_bedrock_agent(session_id, json.dumps(payload))
        ) or {}

        action = agent_response.get("action", "").upper()

        if action == "CONFIRM_SWITCH":

            # Push current journey to stack
            if active_journey:
                journey_stack.append(active_journey)
                if len(journey_stack) > 2:
                    journey_stack.pop(0)

            return {
                "active_journey": pending_switch,
                "pending_journey_switch": None,
                "journey_stack": journey_stack,
                "route": graph_to_route.get(pending_switch),
                "current_node": "router_agent"
            }

        elif action == "DECLINE_SWITCH":
            return {
                "pending_journey_switch": None,
                "route": graph_to_route.get(active_journey),
                "active_journey": active_journey,
                "journey_stack": journey_stack,
                "current_node": "router_agent"
            }

        return {
            "route": "CLARIFICATION",
            "agent_question": "Please confirm whether you want to switch the current request.",
            "current_node": "router_agent"
        }

    # ==========================================================
    # 2️⃣ Resume Paused Journey
    # ==========================================================
    if not active_journey and journey_stack:

        top_journey = journey_stack[-1]

        payload = {
            "mode": "RESUME_CONFIRMATION",
            "paused_journey": top_journey,
            "user_input": translated_text
        }

        agent_response = extract_json_from_text(
            invoke_bedrock_agent(session_id, json.dumps(payload))
        ) or {}

        action = agent_response.get("action", "").upper()

        if action == "RESUME":
            return {
                "active_journey": top_journey,
                "journey_stack": journey_stack[:-1],
                "route": graph_to_route.get(top_journey),
                "current_node": "router_agent"
            }

        elif action == "IGNORE":
            return {
                "journey_stack": journey_stack[:-1],
                "route": "CLARIFICATION",
                "current_node": "router_agent"
            }

        return {
            "route": "CLARIFICATION",
            "agent_question": f"You have a pending {top_journey.replace('_graph','').replace('_',' ').title()} request. Would you like to continue it?",
            "current_node": "router_agent"
        }

    # ==========================================================
    # 3️⃣ Sticky Journey Mode (INSIDE ACTIVE JOURNEY)
    # ==========================================================
    if active_journey:

        payload = {
            "mode": "JOURNEY_SWITCH_CONFIRMATION",
            "current_journey": active_journey,
            "user_input": translated_text
        }

        agent_response = extract_json_from_text(
            invoke_bedrock_agent(session_id, json.dumps(payload))
        ) or {}

        action = agent_response.get("action", "").upper()

        if action == "CONFIRM_SWITCH":
            # Detect requested journey via normal classification
            normal_payload = {
                "user_input": translated_text,
                "language": language,
                "mobile_number": state.get("mobile_number", ""),
                "cid": state.get("cid", ""),
            }

            classification = extract_json_from_text(
                invoke_bedrock_agent(session_id, json.dumps(normal_payload))
            ) or {}

            new_route = classification.get("route", "").upper()
            new_graph = route_to_graph.get(new_route)

            if new_graph and new_graph != active_journey:
                return {
                    "pending_journey_switch": new_graph,
                    "route": "CLARIFICATION",
                    "agent_question": f"You are currently in {active_journey.replace('_graph','').replace('_',' ').title()}. Do you want to switch to {new_route.replace('_',' ').title()}?",
                    "current_node": "router_agent"
                }

        # No switch → return to active journey
        return {
            "route": graph_to_route.get(active_journey),
            "active_journey": active_journey,
            "journey_stack": journey_stack,
            "current_node": "router_agent"
        }

    # ==========================================================
    # 4️⃣ Normal Intent Classification (NO ACTIVE JOURNEY)
    # ==========================================================
    payload = {
        "user_input": translated_text,
        "language": language,
        "mobile_number": state.get("mobile_number", ""),
        "cid": state.get("cid", ""),
    }

    agent_response = extract_json_from_text(
        invoke_bedrock_agent(session_id, json.dumps(payload))
    ) or {}

    route = agent_response.get("route", "CLARIFICATION").upper()
    agent_question = agent_response.get("agent_question", "")
    mobile_number = agent_response.get("mobile_number", "")
    cid = agent_response.get("cid", "")

    new_journey = route_to_graph.get(route)

    # CID gating
    if route in ["NAME_CHANGE", "REPORT_SUPPLY_OFF"] and not cid:
        new_journey = None

    return {
        "route": route,
        "active_journey": new_journey,
        "agent_question": agent_question,
        "mobile_number": mobile_number,
        "cid": cid,
        "journey_stack": journey_stack,
        "current_node": "router_agent"
    }


# ==========================================================
# Route Decision
# ==========================================================
def route_decision(state: AgentState) -> Literal[
    "clarification_node",
    "name_change_graph",
    "report_supply_off_graph",
    "helpline_information_graph",
    "END"
]:

    route = state.get("route", "CLARIFICATION")

    if route == "NAME_CHANGE":
        return "name_change_graph"

    elif route in ["CLARIFYING", "CLARIFICATION"]:
        return "clarification_node"

    elif route == "HELPLINE_INFORMATION":
        return "helpline_information_graph"

    elif route == "REPORT_SUPPLY_OFF":
        return "report_supply_off_graph"

    return "clarification_node"