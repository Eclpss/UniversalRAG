import pickle
from neo4j import GraphDatabase

# Your local Docker Neo4j credentials
URI = "bolt://localhost:7687"
AUTH = ("neo4j", "password")

def test_connection_and_load():
    # 1. Test Neo4j Connection
    print("🔌 Connecting to Neo4j localhost...")
    try:
        driver = GraphDatabase.driver(URI, auth=AUTH)
        driver.verify_connectivity()
        print("✅ Neo4j Connection Successful!")
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j: {e}")
        return

    # 2. Load the embeddings you just cooked on the RTX 3060
    print("\n📂 Loading extracted features...")
    try:
        with open("eval/features/paragraph.pkl", "rb") as f:
            paragraphs = pickle.load(f)
            
        print(f"✅ Successfully loaded {len(paragraphs)} paragraph vectors into memory!")
    except FileNotFoundError:
        print("❌ Could not find paragraph.pkl. Make sure you are in the root directory!")
        
    # We will add the Cypher injection loop here next!
    driver.close()

if __name__ == "__main__":
    test_connection_and_load()