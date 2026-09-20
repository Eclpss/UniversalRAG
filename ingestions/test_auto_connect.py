import json
import requests
from neo4j import GraphDatabase

# --- CONFIGURATION ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
OLLAMA_URL = "http://localhost:11434"

TEXT_MODEL = "llama3.1:8b" 
EMBEDDING_MODEL = "qwen3-embedding:0.6b"

def run_auto_connect_test():
    print("\n🕵️‍♂️ --- Starting Automatic Connection Test ---")
    
    # 1. The New Evidence (We are skipping a physical text file for speed)
    new_document_name = "surveillance_report_01.txt"
    document_text = "Suspect goes by the name Sophia. She is currently operating out of Malaysia and was observed teaching English online."
    
    # 2. Get Vector Embedding
    print(f"⚙️ [1/3] Getting math vector using {EMBEDDING_MODEL}...")
    embed_res = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": document_text},
    )
    vector = embed_res.json().get("embedding")

    # 3. Extract Entities via Llama 3
    print(f"🧠 [2/3] Asking {TEXT_MODEL} to extract entities...")
    prompt = f"""
    Extract key entities from this text: "{document_text}"
    Categories: Person, Location, Language, Hobby.
    Return ONLY a JSON array of objects. Do not say "Here is the JSON".
    Example: [{{"name": "John", "type": "Person"}}]
    """
    
    output = ""
    try:
        res = requests.post(
            f"{OLLAMA_URL}/api/generate", 
            json={"model": TEXT_MODEL, "prompt": prompt, "stream": False, "format": "json"}
        )
        res.raise_for_status()
        output = res.json().get("response", "[]")
        
        # Clean JSON and Parse it safely INSIDE the try block
        clean_output = output.strip()
        if clean_output.startswith("```json"): clean_output = clean_output[7:]
        elif clean_output.startswith("```"): clean_output = clean_output[3:]
        if clean_output.endswith("```"): clean_output = clean_output[:-3]
        
        entities = json.loads(clean_output.strip())
        print(f"✅ Extracted: {entities}")
        
    except Exception as e:
        print(f"❌ Failed to read JSON. Error: {e}")
        print(f"👀 RAW AI OUTPUT WAS:\n{output}")
        return

    # 4. Push to Graph without hardcoding the audio file!
    print("🔌 [3/3] Pushing to Neo4j to see if it auto-connects...")
    cypher_query = """
    // A. Save the new document
    MERGE (d:DocumentChunk {file_name: $file_name})
    SET d.text = $text, d.embedding = $embedding
    
    // B. Draw arrows to entities (MERGE prevents duplicates)
    WITH d, $entities AS entities
    UNWIND entities AS entity
    MERGE (e:ExtractedEntity {name: entity.name})
    SET e.type = entity.type
    MERGE (d)-[:MENTIONS]->(e)
    """
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        session.run(cypher_query, file_name=new_document_name, text=document_text, embedding=vector, entities=entities)
    driver.close()
    print("🎉 SUCCESS! New document injected.")

if __name__ == "__main__":
    run_auto_connect_test()