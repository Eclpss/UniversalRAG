import requests
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"

def run_hybrid_search(question):
    # 1. Embed Question
    embed_res = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": question},
    )
    if embed_res.status_code != 200:
        return []
        
    question_vector = embed_res.json().get("embedding")

    # 2. Cosine Math + Graph Traversal
    hybrid_query = """
    WITH $question_vector AS q_vec
    MATCH (node)
    WHERE (node:AudioTranscript OR node:DocumentChunk OR node:ImageChunk OR node:Video) 
      AND node.embedding IS NOT NULL
      AND size(node.embedding) = size(q_vec)
    
    WITH node, vector.similarity.cosine(node.embedding, q_vec) AS math_score
    WHERE math_score > 0.35
    
    OPTIONAL MATCH (node)-[:MENTIONS]->(e:ExtractedEntity)
    
    RETURN labels(node)[0] AS File_Type,
           node.file_name AS File, 
           COALESCE(node.text, node.text_transcript, node.text_description) AS Text, 
           math_score, 
           collect(DISTINCT e.name) AS Clues
    ORDER BY math_score DESC
    LIMIT 3
    """
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    records = []
    
    with driver.session() as session:
        results = session.run(hybrid_query, question_vector=question_vector)
        for r in results:
            records.append({
                "type": r["File_Type"],
                "file": r["File"],
                "score": round(r["math_score"] * 100, 2),
                "clues": r["Clues"],
                "text": r["Text"]
            })
            
    driver.close()
    return records # <--- This is the magic part! It hands the data back to Streamlit.