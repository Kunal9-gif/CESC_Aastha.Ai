from langgraph.graph import StateGraph, END
from app.state import AgentState
from app.agents.billing_main_agent import BillingComplaintMainAgent
from app.agents.clarification_agent import ClarificationAgent

def billing_node(state: AgentState):
    agent = BillingComplaintMainAgent()
    return agent.process(state)

def clarification_node(state: AgentState):
    agent = ClarificationAgent()
    return agent.process(state)

def route_from_billing(state: AgentState):
    # Route to clarification node if we don't have enough confidence or if parsing failed
    if state.get("next_agent") == "CLARIFICATION_NODE":
        return "clarification"
    # Otherwise, end the turn (the simulation loop will pick it up)
    return END

def build_graph():
    workflow = StateGraph(AgentState)
    
    # 1. Add nodes
    workflow.add_node("billing_main", billing_node)
    workflow.add_node("clarification", clarification_node)
    
    # 2. Set Entry
    workflow.set_entry_point("billing_main")
    
    # 3. Add Edges and Routing
    workflow.add_conditional_edges(
        "billing_main",
        route_from_billing,
        {
            "clarification": "clarification",
            END: END
        }
    )
    
    workflow.add_edge("clarification", END)
    
    return workflow.compile()