from app.graph import build_graph

def visualize():
    print("Building graph...")
    graph = build_graph()
    
    print("\n--- ASCII Graph Visualization ---\n")
    try:
        print(graph.get_graph().draw_ascii())
    except Exception as e:
        print("⚠️ Could not generate ASCII graph (You may need to `pip install grandalf`)")
    print("\n---------------------------------\n")
    
    # Save Mermaid PNG
    try:
        image_data = graph.get_graph().draw_mermaid_png()
        output_file = "graph_visualization.png"
        with open(output_file, "wb") as f:
            f.write(image_data)
        print(f"✅ Successfully saved Mermaid visualization to {output_file}")
    except Exception as e:
        print(f"⚠️ Could not generate PNG. (Note: Mermaid PNG generation requires internet connection to external API, or local installation)")
        print(f"Error: {e}")
        
    # Save Mermaid Text
    try:
        mermaid_text = graph.get_graph().draw_mermaid()
        output_file = "graph_visualization.md"
        with open(output_file, "w") as f:
            f.write(f"```mermaid\n{mermaid_text}\n```")
        print(f"✅ Successfully saved Mermaid Markdown to {output_file}")
    except Exception as e:
        print(f"⚠️ Could not generate Mermaid text.")
        print(f"Error: {e}")

if __name__ == "__main__":
    visualize()
