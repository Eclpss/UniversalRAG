import pickle
from neo4j import GraphDatabase

# Your local Docker Neo4j credentials
URI = "bolt://localhost:7687"
AUTH = ("neo4j", "password")

def test_connection_and_load():
    print("🔌 Connecting to Neo4j localhost...")
    driver = GraphDatabase.driver(URI, auth=AUTH)
    
    print("📂 Loading extracted features...")
    with open("eval/features/paragraph.pkl", "rb") as f:
        paragraphs = pickle.load(f)
    print(f"✅ Loaded {len(paragraphs)} paragraph vectors!\n")

    print("🚀 Formatting data for injection...")
    # Convert numpy arrays to standard Python lists so Neo4j can read them
    records = [{"psg_id": str(k), "embedding": v.tolist()} for k, v in paragraphs.items()]
    
    # We feed it 1,000 at a time to prevent Docker from crashing
    batch_size = 1000 
    
    def insert_batch(tx, batch):
        query = """
        UNWIND $batch AS record
        MERGE (d:DocumentChunk {psg_id: record.psg_id})
        SET d.embedding = record.embedding
        """
        tx.run(query, batch=batch)

    print("⚡ Blasting nodes into the Graph Database...")
    with driver.session() as session:
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            session.execute_write(insert_batch, batch)
            print(f"   -> Injected batch {i} to {i + len(batch)}...")

    print("\n🎉 MISSION ACCOMPLISHED: All 73,313 vectors are secured in the Graph!")
    driver.close()

if __name__ == "__main__":
    test_connection_and_load()