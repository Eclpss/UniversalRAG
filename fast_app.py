import requests
import re
from flask import Flask, request, jsonify
from neo4j import GraphDatabase

app = Flask(__name__)

# --- NEO4J CONNECTION ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password" # <--- CHANGE THIS IF NEEDED!

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

@app.route('/ask_neo4j', methods=['POST'])
def ask_neo4j():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "") or data.get("query", "") or data.get("text", "")
    
    if not question:
        question = request.data.decode("utf-8")
        if not question or len(question) < 2:
            return jsonify({ "text": "n8n failed to send a valid question payload." }), 400

    print(f"\n🤖 [NEO4J AGENT] Incoming Question: {question}", flush=True)
    
    q_lower = question.lower()
    clean_cypher = None

    # =========================================================================
    # ⚡ FAST LANE: PYTHON INTENT ROUTER
    # =========================================================================
    mention_match = re.search(r'mentions? of [\'"]?([a-zA-Z0-9_]+)[\'"]?', q_lower)
    
    if mention_match:
        target_word = mention_match.group(1)
        print(f"⚡ [FAST LANE] Python intercepted mention search for: '{target_word}'", flush=True)
        
        clean_cypher = f"""
        MATCH (n)
        WHERE any(key IN keys(n) WHERE toLower(key) = toLower('{target_word}'))
        RETURN count(n) AS Total_Nodes
        """.strip()

    # =========================================================================
    # 🧠 SLOW LANE: LLM ROUTING
    # =========================================================================
    if not clean_cypher:
        with driver.session() as session:
            try:
                path_result = session.run("MATCH (a)-[r]->(b) RETURN DISTINCT labels(a)[0] AS From, type(r) AS Rel, labels(b)[0] AS To LIMIT 200")
                valid_paths = [f"({r['From']})-[:{r['Rel']}]->({r['To']})" for r in path_result if r['From'] and r['To']]
                
                prop_result = session.run("""
                    CALL db.schema.nodeTypeProperties() 
                    YIELD nodeLabels, propertyName 
                    RETURN nodeLabels[0] AS label, collect(DISTINCT propertyName) AS props
                """)
                node_props = [f"Node '{r['label']}' contains properties: {r['props']}" for r in prop_result if r['label']]
            except Exception as e:
                print(f"❌ [ERROR] Database scan failed: {e}", flush=True)
                return jsonify({ "text": f"Database scan failed: {e}" }), 500

        prompt = f"""
        You are an expert Neo4j Database Query writer.
        Translate the user's question into a single, valid Cypher query.
        
        === DYNAMIC GRAPH TOPOLOGY MAP ===
        Valid Node-to-Node Relationships:
        {valid_paths}
        Exact Properties mapped to Nodes:
        {node_props}
        ==================================

        CRITICAL RULES:
        1. Always append `LIMIT 25` to the very end of your query.
        
        2. 🕸️ UNIVERSAL DETECTIVE WEB RULE: When finding connections between entities.
            MATCH (target:ExtractedEntity)<-[:MENTIONS]-(doc)-[:MENTIONS]->(other:ExtractedEntity)
            WHERE toLower(target.name) CONTAINS toLower('the_word') OR toLower(doc.text) CONTAINS toLower('the_word')
            RETURN doc.file_name AS Source_File, labels(doc)[0] AS File_Type, coalesce(doc.text_transcript, doc.text, doc.description, doc.content, 'No text available') AS Content, collect(DISTINCT other.name) AS Connected_Clues
            
     3. 📁 CONTENT & FILE SEARCH RULE: If the user asks what is "inside" a file, asks for a "conversation", "transcript", or mentions a file name, search across all nodes holding a file_name:
            MATCH (doc)
            WHERE toLower(doc.file_name) CONTAINS toLower('the_filename_or_word')
            RETURN doc.file_name AS Source_File, labels(doc)[0] AS File_Type, coalesce(doc.text_transcript, doc.text, doc.description, doc.content, 'No text available') AS Content
            
        4. NEVER RETURN `doc.text AS Source_File`. YOU MUST RETURN `doc.file_name AS Source_File`.
        5. Return ONLY the raw Cypher code. No markdown formatting.
        
        User Question: "{question}"
        """
        
        print(f"🧠 [SLOW LANE] Asking AI Coder to translate to Cypher...", flush=True)
        try:
            response = requests.post("http://localhost:11434/api/generate", json={
                "model": "qwen2.5-coder:7b", # <-- Try 7b if 14b keeps crashing!
                "prompt": prompt,
                "stream": False
            })
            
            # Catch Ollama 404 errors if the model isn't pulled properly
            if response.status_code != 200:
                error_msg = response.json().get("error", "Unknown Ollama Error")
                raise Exception(f"Ollama returned {response.status_code}: {error_msg}")
                
            raw_cypher = response.json().get("response", "")
            clean_cypher = raw_cypher.replace("```cypher", "").replace("```", "").strip().split("\n\n")[0]
            
           # 🛡️ Safety net: Ensure Source_File is always file_name
            clean_cypher = clean_cypher.replace("doc.text AS Source_File", "doc.file_name AS Source_File")

           # 🛡️ Universal Guardrail: Strip brittle label assumptions & force bracket syntax into a WHERE clause
            clean_cypher = re.sub(
                r'\((\w+)(?::\w+)?\s*\{\s*file_name\s*:\s*([\'"][^\'"]+[\'"])\s*\}\)',
                r'(\1)\nWHERE toLower(\1.file_name) CONTAINS toLower(\2)',
                clean_cypher
            )

            # 🛡️ Fix invalid 'OR' label syntax inside node patterns: (doc:A OR doc:B) -> (doc:A|B)
                
        except Exception as e:
            print(f"❌ [ERROR] AI Request Failed: {e}", flush=True)
            return jsonify({ "text": f"Failed to contact local AI: {e}" }), 500

    # =========================================================================
    # ⚙️ EXECUTION ENGINE
    # =========================================================================
    print(f"📐 [NEO4J AGENT] Cypher Code Executed:\n{clean_cypher}", flush=True)
    
    with driver.session() as session:
        try:
            result = session.run(clean_cypher)
            records = [record.data() for record in result]
            
            if not records:
                final_answer = "I searched the Knowledge Graph, but could not find any exact data matching your question."
            else:
                final_answer = "Data found in Neo4j Knowledge Graph:\n\n"
                for r in records:
                    if 'Total_Nodes' in r:
                        final_answer += f"- Found {r['Total_Nodes']} nodes with that property key.\n"
                    else:
                        clues = r.get('Connected_Clues', [])
                        clues_text = ', '.join(clues) if clues else "No connected clues"
                        final_answer += f"- Found in {r.get('Source_File', 'Unknown Document')}. Connected clues: {clues_text}\n"
                        
                        # 📝 NEW: Hand the actual text payload back to AnythingLLM
                        content = r.get('Content')
                        if content and content != 'No text available':
                            final_answer += f"  📄 Transcript/Content:\n  {content}\n\n"
            
            print("✅ [NEO4J AGENT] Query successful! Handing data back to UI.", flush=True)
            return jsonify({ "text": final_answer }), 200

        except Exception as e:
            print(f"❌ [ERROR] Cypher Execution failed: {e}", flush=True)
            return jsonify({ "text": f"The Cypher query failed: {clean_cypher}\n\nError: {e}" }), 500

if __name__ == '__main__':
    print("🚀 FAST ROUTER Agent listening on port 5001...")
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)