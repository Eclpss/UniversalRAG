import base64
import json
import os
import cv2
from neo4j import GraphDatabase
import requests

# --- CONFIGURATION ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
OLLAMA_URL = "http://localhost:11434"

VISION_MODEL = "qwen3-vl:8b"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"


def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def process_video_as_one_node(video_path, output_folder):
    if not os.path.exists(video_path):
        print(f"❌ Error: Video '{video_path}' not found!")
        return

    os.makedirs(output_folder, exist_ok=True)
    file_name = os.path.basename(video_path)
    print(f"\n🎬 --- Processing Entire Video: {file_name} ---")

    # --- 1. EXTRACT 3 KEYFRAMES (Beginning, Middle, End) ---
    print("✂️ [1/4] Extracting 3 master keyframes from the video...")
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Grab frames at 10%, 50%, and 90% of the video length
    target_frames = [
        int(total_frames * 0.1),
        int(total_frames * 0.5),
        int(total_frames * 0.9)
    ]
    
    saved_images = []
    for tf in target_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, tf)
        ret, frame = cap.read()
        if ret:
            img_path = os.path.join(output_folder, f"keyframe_{tf}.jpg")
            cv2.imwrite(img_path, frame)
            saved_images.append(img_path)
    cap.release()

    # --- 2. GENERATE MASTER SUMMARY ---
    print(f"👁️ [2/4] Asking '{VISION_MODEL}' to write a master summary of the whole event...")
    # We pass all 3 images to the AI at once so it understands the timeline
    base64_images = [encode_image_to_base64(img) for img in saved_images]
    
    # The prompt is tailored to find rogue/suspicious behavior for the case
    vision_prompt = (
        "You are a forensic investigator. Look at these sequential frames from an office video. "
        "Write ONE concise, factual paragraph summarizing the entire event. Focus on identifying "
        "people, meetings, documents, and any potentially unauthorized or suspicious business activity. "
        "Do not describe the camera angles; focus only on the events happening in the room."
    )

    extracted_text = ""
    try:
        vision_res = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": VISION_MODEL,
                "prompt": vision_prompt,
                "images": base64_images,
                "stream": True,
            },
            stream=True,
        )
        vision_res.raise_for_status()

        print("\n📝 Master Video Summary:")
        print("-" * 50)
        for line in vision_res.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8"))
                token = chunk.get("response", "")
                extracted_text += token
                print(token, end="", flush=True)

        extracted_text = extracted_text.strip()
        print("\n" + "-" * 50)
    except Exception as e:
        print(f"❌ Vision step failed: {e}")
        return

    # --- 3. VECTOR EMBEDDING ---
    print(f"\n⚙️ [3/4] Generating embedding for the master summary via '{EMBEDDING_MODEL}'...")
    try:
        embed_res = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBEDDING_MODEL, "prompt": extracted_text},
        )
        embed_res.raise_for_status()
        vector = embed_res.json().get("embedding")
    except Exception as e:
        print(f"❌ Embedding step failed: {e}")
        return

    # --- 4. INJECT ONE SINGLE NODE INTO NEO4J ---
    print("🔌 [4/4] Pushing SINGLE Master :Video node to Neo4j...")
    cypher_query = """
    MERGE (v:Video {file_name: $file_name})
    SET v.text_description = $text,
        v.embedding = $embedding,
        v.modality = 'video',
        v.investigation_status = 'Evidence Logged',
        v.created_at = datetime()
    RETURN v
    """
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            session.run(
                cypher_query,
                file_name=file_name,
                text=extracted_text,
                embedding=vector,
            )
        driver.close()
        print(f"✅ SUCCESS! One clean node for '{file_name}' secured in the Graph. No clutter!")
    except Exception as e:
        print(f"❌ Neo4j injection failed: {e}")


if __name__ == "__main__":
    VIDEO_FILE = "../evidence_files/stockvid.mp4"
    OUTPUT_DIRECTORY = "video_frames"

    process_video_as_one_node(VIDEO_FILE, OUTPUT_DIRECTORY)