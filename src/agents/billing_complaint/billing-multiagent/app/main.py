from app.graph import build_graph

def run_simulation():
    graph = build_graph()
    
    print("\n=======================================================")
    print("🤖 Billing Complaint Multi-Agent Simulator Started!")
    print("=======================================================")
    print("ℹ️ Type 'exit' or 'quit' to end the simulation.\n")
    
    # Keeping static tracking for the demo
    # We could theoretically carry this over multiple turns
    user_id = "user_1"
    cid = "CID123"
    
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