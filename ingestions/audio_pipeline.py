import os
import requests
import whisper
from moviepy import VideoFileClip  # UPDATED FOR MOVIEPY 2.X
from neo4j import GraphDatabase

# --- CONFIGURATION ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
OLLAMA_URL = "http://localhost:11434"

EMBEDDING_MODEL = "qwen3-embedding:0.6b"

def process_audio(video_path):
    if not os.path.exists(video_path):
        print(f"❌ Error: Video '{video_path}' not found!")
        return

    file_name = os.path.basename(video_path)
    temp_audio_path = "temp_audio.wav"
    
    print(f"\n🎙️ --- Processing Audio for: {file_name} ---")

    # --- 1. RIP AUDIO FROM VIDEO ---
    print("✂️ [1/4] Ripping audio track from the video file...")
    try:
        video = VideoFileClip(video_path)
        # Extract audio and save to a temporary wav file
        video.audio.write_audiofile(temp_audio_path)
        video.close()
    except Exception as e:
        print(f"❌ Failed to extract audio. (If this is an ffmpeg error, let me know!): {e}")
        return

    # --- 2. TRANSCRIBE WITH WHISPER ---
    print("🧠 [2/4] Loading local Whisper AI to transcribe audio...")
    try:
        # "base" model is fast and takes very little VRAM. 
        model = whisper.load_model("base")
        print("🗣️ Transcribing... (this might take a few seconds)")
        result = model.transcribe(temp_audio_path)
        extracted_text = result["text"].strip()
        
        if not extracted_text:
            extracted_text = "[No audible speech detected in this video segment.]"
            
        print("\n📝 Master Audio Transcript:")
        print("-" * 50)
        print(extracted_text)
        print("-" * 50 + "\n")
    except Exception as e:
        print(f"❌ Whisper transcription failed: {e}")
        return
    finally:
        # Clean up the temporary audio file
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

    # --- 3. VECTOR EMBEDDING ---
    print(f"⚙️ [3/4] Generating embedding via '{EMBEDDING_MODEL}'...")
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

    # --- 4. INJECT INTO NEO4J ---
    print("🔌 [4/4] Pushing :AudioTranscript node to Neo4j...")
    cypher_query = """
    MERGE (a:AudioTranscript {file_name: $file_name})
    SET a.text_transcript = $text,
        a.embedding = $embedding,
        a.modality = 'audio',
        a.investigation_status = 'Evidence Logged',
        a.created_at = datetime()
    RETURN a
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
        print(f"✅ SUCCESS! Audio transcript for '{file_name}' secured in the Graph.")
    except Exception as e:
        print(f"❌ Neo4j injection failed: {e}")

if __name__ == "__main__":
    # Point this to the exact same video we just processed visually
    VIDEO_FILE = "../evidence_files/conver.mp4" 
    process_audio(VIDEO_FILE)