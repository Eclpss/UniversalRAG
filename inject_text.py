import pandas as pd
from neo4j import GraphDatabase

# Your local Docker Neo4j credentials
URI = "bolt://localhost:7687"
AUTH = ("neo4j", "password")

def attach_text_to_nodes():
    print("📂 Loading original text from parquet file...")
    df = pd.read_parquet("dataset/paragraph.parquet", engine="fastparquet")
    
    # FIX: Grab the psg_id directly from the Index instead of the columns
    records = []
    for psg_id, row in df.iterrows():
        records.append({
            "psg_id": str(psg_id), 
            "text": str(row['text'])
        })
        
    print(f"✅ Loaded {len(records)} text snippets!")

    print("🔌 Connecting to Neo4j...")
    driver = GraphDatabase.driver(URI, auth=AUTH)
    batch_size = 1000

    def update_batch(tx, batch):
        query = """
        UNWIND $batch AS record
        MATCH (d:DocumentChunk {psg_id: record.psg_id})
        SET d.text = record.text
        """
        tx.run(query, batch=batch)

    print("⚡ Gluing human-readable text to your graph nodes...")
    with driver.session() as session:
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            session.execute_write(update_batch, batch)
            print(f"   -> Updated batch {i} to {i + len(batch)}...")

    print("\n🎉 DONE! Your vectors now have actual text attached!")
    driver.close()

if __name__ == "__main__":
    attach_text_to_nodes()