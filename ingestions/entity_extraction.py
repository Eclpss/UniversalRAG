import os
import json
import requests
from neo4j import GraphDatabase

# --- CONFIGURATION ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
OLLAMA_URL = "http://localhost:11434"

# You can use any text model you have installed in Ollama
TEXT_MODEL = "llama3.1:8b" 

def extract_and_link_entities(file_path):
    # This automatically chops "../evidence_files/conver.mp4" down to "conver.mp4"
    file_name = os.path.basename(file_path)
    
    print(f"\n🕵️‍♂️ --- Starting Entity Extraction for: {file_name} ---")

    # --- 1. FETCH THE UNTOUCHED ORIGINAL TEXT ---
    print("📥 [1/3] Fetching the master transcript from Neo4j...")
    fetch_query = """
    MATCH (a:AudioTranscript {file_name: $file_name})
    RETURN a.text_transcript AS text
    """
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run(fetch_query, file_name=file_name)
        record = result.single()
        
        if not record or not record["text"]:
            print("❌ Could not find transcript in Neo4j. Did you run the audio pipeline first?")
            return
            
        raw_text = record["text"]

    # --- 2. ASK LLM TO EXTRACT NOUNS AS JSON ---
    print(f"🧠 [2/3] Asking '{TEXT_MODEL}' to extract People, Locations, and Hobbies...")
    
    prompt = f"""
    You are a data extraction AI. Read the following transcript and extract key entities.
    Categories to look for: Person, Location, Hobby, Language.
    
    Transcript: "{raw_text}"
    
    Return ONLY a valid JSON array of objects. Do not write any markdown, do not write explanations. 
    Format example:
    [
        {{"name": "John", "type": "Person"}},
        {{"name": "Japan", "type": "Location"}}
    ]
    """

    try:
       # Removed the strict format="json" flag so the model doesn't freeze
        res = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": TEXT_MODEL, "prompt": prompt, "stream": False}
        )
        res.raise_for_status()
        output = res.json().get("response", "[]")
        
        # --- THE MARKDOWN STRIPPER ---
        clean_output = output.strip()
        if clean_output.startswith("```json"):
            clean_output = clean_output[7:]
        elif clean_output.startswith("```"):
            clean_output = clean_output[3:]
        if clean_output.endswith("```"):
            clean_output = clean_output[:-3]
        clean_output = clean_output.strip()

        # Parse the cleaned string
        entities = json.loads(clean_output)
        print(f"✅ Extracted {len(entities)} entities: {entities}")
        
    except Exception as e:
        print(f"❌ Extraction failed. Error: {e}")
        print(f"👀 RAW AI OUTPUT WAS:\n{output}")
        return

    # --- 3. INJECT THE "TAGS" INTO NEO4J ---
    print("🔌 [3/3] Drawing the arrows and creating the tag nodes in Neo4j...")
    
    inject_query = """
    MATCH (a:AudioTranscript {file_name: $file_name})
    UNWIND $entities AS entity
    
    // Create the tag node (e.g., Person: "Sophia")
    MERGE (e:ExtractedEntity {name: entity.name})
    SET e.type = entity.type
    
    // Draw the arrow from the Transcript to the Tag without touching the original text
    MERGE (a)-[:MENTIONS]->(e)
    """
    
    try:
        with driver.session() as session:
            session.run(inject_query, file_name=file_name, entities=entities)
        print(f"✅ SUCCESS! Graph web perfectly built around '{file_name}'.")
    except Exception as e:
        print(f"❌ Neo4j injection failed: {e}")
    finally:
        driver.close()

if __name__ == "__main__":
    TARGET_FILE = "../evidence_files/conver.mp4"
    extract_and_link_entities(TARGET_FILE)