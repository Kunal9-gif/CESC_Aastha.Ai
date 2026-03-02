from app.graph import build_graph
from app.mocks.mock_crm import MOCK_PROFILES

def run_simulation():
    graph = build_graph()
    
    print("\n=======================================================")
    print("🤖 Billing Complaint Multi-Agent Simulator Started!")
    print("=======================================================")
    print("ℹ️ Type 'exit' or 'quit' to end the simulation.\n")
    
    print("--- [SIMULATOR CONFIGURATION] ---")
    print("Select a Mock CRM Profile to simulate:")
    for key, profile in MOCK_PROFILES.items():
        print(f"  [{key}] {profile['name']} (CID: {profile['cid']} | Mobile: {profile['mobile']})")
    
    choice = input("\nEnter profile number [default: 1]: ").strip()
    if choice not in MOCK_PROFILES:
        choice = "1"
        
    selected_profile = MOCK_PROFILES[choice]
    
    user_id = selected_profile.get("user_id", f"user_{choice}")
    cid = selected_profile["cid"]
    mobile = selected_profile["mobile"]
    
    print(f"\n✅ Loaded Profile: {selected_profile['name']}")
    print("---------------------------------\n")
    
    while True:
        try:
            user_input = input(f"👤 [{user_id}]: ")
            if user_input.lower().strip() in ['exit', 'quit']:
                print("\nExiting simulation. Goodbye!")
                break
            
            if not user_input.strip():
                continue
                
            print("⏳ Please wait while we process your request...")
            
            # Rebuilding a fresh initial state for every input for simplicity in this demo.
            initial_state = {
                "user_id": user_id,
                "normalized_message": user_input,
                "intent": "",
                "confidence": 0.0,
                "clarification_needed": False,
                "CID": cid,
                "registered_mobile_no": mobile,
                "OTP_verification_status": "NOT_VERIFIED",
                "tool_invoked": "",
                "next_agent": ""
            }
            
            result = graph.invoke(initial_state)
            
            print("\n✅ FINAL STATE: ")
            print("-----------------")
            for key, value in result.items():
                if key == "OTP_verification_status" and value == "NOT_VERIFIED":
                    pass # Hide default noise maybe? We will print all for debugging purposes
                print(f"  {key}: {value}")
            print("\n-------------------------------------------------------\n")
            
        except (KeyboardInterrupt, EOFError):
            print("\nExiting simulation. Goodbye!")
            break

if __name__ == "__main__":
    run_simulation()