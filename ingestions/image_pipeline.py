import base64
import os
import requests
from neo4j import GraphDatabase

# --- CONFIGURATION ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

OLLAMA_URL = "http://localhost:11434"

# Utilizing the cosmic entities from your actual arsenal
VISION_MODEL = "qwen3-vl:8b" 
EMBEDDING_MODEL = "qwen3-embedding:0.6b"


def encode_image_to_base64(image_path):
    """Convert a local image file into a base64 string for Ollama."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def process_and_inject_image(image_path):
    if not os.path.exists(image_path):
        print(f"❌ Error: Image file '{image_path}' not found!")
        return

    file_name = os.path.basename(image_path)
    print(f"\n🖼️ [1/4] Processing image: '{file_name}'...")

    # --- STEP 1: Convert image to Base64 ---
    base64_image = encode_image_to_base64(image_path)

   # --- STEP 2: Ask Ollama Vision to describe the image (STREAMING ENABLED) ---
    print(f"👁️ [2/4] Asking '{VISION_MODEL}' to look at the image...")
    vision_prompt = (
        "Describe this image in extreme detail. List key objects, text, people, environment, "
        "and overall context. Keep it objective and dense with information so it can be searched later."
    )

    try:
        import json

        vision_res = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": VISION_MODEL,
                "prompt": vision_prompt,
                "images": [base64_image],
                "stream": True, # <--- Enable streaming mode
            },
            stream=True,
        )
        vision_res.raise_for_status()

        print("\n📝 Live Vision Streaming Output:\n" + "-" * 50)
        extracted_text = ""
        
        # Stream character-by-character / word-by-word directly to terminal
        for line in vision_res.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8"))
                token = chunk.get("response", "")
                extracted_text += token
                print(token, end="", flush=True) # <--- Prints words as they are generated!
                
        print("\n" + "-" * 50)
        extracted_text = extracted_text.strip()
        
    except Exception as e:
        print(f"\n❌ Vision step failed: {e}")
        return

    # --- STEP 3: Generate Real Vector Embedding ---
    print(f"\n⚙️ [3/4] Generating embedding via '{EMBEDDING_MODEL}'...")
    try:
        embed_res = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBEDDING_MODEL, "prompt": extracted_text},
        )
        embed_res.raise_for_status()
        vector = embed_res.json().get("embedding")
        print(f"✅ Generated {len(vector)}-dimensional real feature vector!")
    except Exception as e:
        print(f"❌ Embedding step failed: {e}")
        return

    # --- STEP 4: Push Real Node to Neo4j ---
    print("🔌 [4/4] Pushing real ImageChunk node to Neo4j...")
    cypher_query = """
    MERGE (i:ImageChunk {file_name: $file_name})
    SET i.text_description = $text,
        i.embedding = $embedding,
        i.modality = 'image',
        i.created_at = datetime()
    RETURN i
    """

    try:
        driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        with driver.session() as session:
            session.run(
                cypher_query,
                file_name=file_name,
                text=extracted_text,
                embedding=vector,
            )
        driver.close()
        print(
            f"🎉 SUCCESS! Node for '{file_name}' injected into Neo4j with real text and vector!"
        )

    except Exception as e:
        print(f"❌ Neo4j injection failed: {e}")


if __name__ == "__main__":
    # Point this to a real photo on your hard drive!
    TEST_IMAGE_PATH = "../evidence_files/sample.jpg" 

    process_and_inject_image(TEST_IMAGE_PATH)