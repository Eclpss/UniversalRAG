import streamlit as st
import os
import sys
import pandas as pd
from neo4j import GraphDatabase
from streamlit_agraph import agraph, Node, Edge, Config

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ingestions.audio_pipeline import process_audio
from ingestions.video_pipeline import process_video_as_one_node
# --- NEO4J CONFIG ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"  # <--- CHANGE IF NEEDED

st.set_page_config(page_title="UniversalRAG", page_icon="🕸️", layout="wide")
st.title("🕸️ UniversalRAG OS")

tab_investigate, tab_ingest, tab_graph = st.tabs(["🕵️‍♂️ Investigation", "📁 Data Ingestion", "🕸️ Graph Explorer"])

# --- TAB 1: GLOBAL CONNECTION MATRIX ---
with tab_investigate:
    st.markdown("### 🧮 Cross-Reference Math Engine")
    st.write("Scan the entire database to find hidden mathematical connections and shared graph clues.")
    
    if st.button("Run Global Connection Matrix"):
        with st.spinner("Calculating cosine similarity and tracing shared entities..."):
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            
            matrix_query = """
            MATCH (a)
            WHERE (a:AudioTranscript OR a:DocumentChunk OR a:ImageChunk OR a:Video)
              AND a.embedding IS NOT NULL 
              AND a.file_name IS NOT NULL
            
            MATCH (b)
            WHERE (b:AudioTranscript OR b:DocumentChunk OR b:ImageChunk OR b:Video)
              AND b.embedding IS NOT NULL
              AND b.file_name IS NOT NULL
              AND elementId(a) < elementId(b)
              AND size(a.embedding) = size(b.embedding)
            
            WITH a, b, vector.similarity.cosine(a.embedding, b.embedding) AS math_score
            WHERE math_score > 0.40
            
            OPTIONAL MATCH (a)-[:MENTIONS]->(e:ExtractedEntity)<-[:MENTIONS]-(b)
            
            RETURN a.file_name AS Evidence_A,
                   b.file_name AS Evidence_B,
                   round(math_score * 100, 2) AS Match_Percentage,
                   collect(DISTINCT e.name) AS Shared_Entities
            ORDER BY Match_Percentage DESC
            LIMIT 100
            """
            
            with driver.session() as session:
                results = session.run(matrix_query)
                data = []
                for r in results:
                    shared = r["Shared_Entities"]
                    if shared:
                        reason = f"🔗 Shared Entities: {', '.join(shared)}"
                    elif r["Match_Percentage"] >= 75.0:
                        reason = "🎯 High Semantic Correlation"
                    else:
                        reason = "🧩 Moderate Topic Overlap"
                        
                    data.append({
                        "Evidence A": r["Evidence_A"], 
                        "Evidence B": r["Evidence_B"], 
                        "Similarity": r['Match_Percentage'], # Kept as float for sorting
                        "Explanation / Trace": reason
                    })
                        
            driver.close()
            
            # Save the data into Streamlit's memory so it doesn't vanish when we click other things
            st.session_state.matrix_data = data

    # --- RENDER THE UI IF WE HAVE DATA IN MEMORY ---
    if "matrix_data" in st.session_state and st.session_state.matrix_data:
        st.success("Analysis Complete! Here are the cross-modal connections:")
        
        # Display the main read-only table (formatting the float to a percentage string)
        display_df = pd.DataFrame(st.session_state.matrix_data)
        display_df["Similarity"] = display_df["Similarity"].astype(str) + "%"
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # --- HUMAN IN THE LOOP APPROVAL QUEUE ---
        high_matches = [d for d in st.session_state.matrix_data if d["Similarity"] >= 75.0]
        
        if high_matches:
            st.divider()
            st.markdown("#### 🛡️ Human-in-the-Loop: Pending Connections")
            st.info("The math engine flagged these files as highly related (>75%). Check the box to officially draw a `SIMILAR_TO` line between them in the database.")
            
            # Create a dataframe specifically for the editor
            df_pending = pd.DataFrame(high_matches)[["Evidence A", "Evidence B", "Similarity"]]
            df_pending["Similarity"] = df_pending["Similarity"].astype(str) + "%"
            
            # Insert a boolean column for the checkboxes at the very front
            df_pending.insert(0, "Approve Link", False) 
            
            # Render the interactive data editor
            edited_df = st.data_editor(df_pending, hide_index=True, use_container_width=True)
            
            if st.button("Confirm & Draw Approved Links"):
                approved_rows = edited_df[edited_df["Approve Link"] == True]
                
                if approved_rows.empty:
                    st.warning("No connections were checked for approval.")
                else:
                    with st.spinner("Burning connections into Neo4j..."):
                        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
                        
                        merge_query = """
                        MATCH (a), (b)
                        WHERE (a.file_name = $file_a OR a.name = $file_a) 
                          AND (b.file_name = $file_b OR b.name = $file_b)
                        MERGE (a)-[r:SIMILAR_TO]->(b)
                        SET r.score = $score
                        """
                        
                        with driver.session() as session:
                            for index, row in approved_rows.iterrows():
                                session.run(merge_query, 
                                            file_a=row["Evidence A"], 
                                            file_b=row["Evidence B"], 
                                            score=row["Similarity"])
                                            
                        driver.close()
                        st.success(f"Success! {len(approved_rows)} `SIMILAR_TO` lines have been drawn in the graph.")

# --- TAB 2: UNIVERSAL UPLOAD ---
with tab_ingest:
    st.markdown("### Upload New Evidence")
    
    uploaded_file = st.file_uploader("Drop a file to instantly vectorize and graph it", type=["txt", "pdf", "mp4", "jpg", "png"])
    
    if uploaded_file is not None:
        ext = uploaded_file.name.split('.')[-1].lower()
        
        # 🎛️ DYNAMIC UI: Only show video options if it's an MP4
        video_mode = None
        if ext == 'mp4':
            st.markdown("#### 🎬 Video Processing Options")
            video_mode = st.radio(
                "How do you want the AI to analyze this video?",
                ["Transcribe Audio (Speech to Text)", 
                 "Describe Visuals (Frame Analysis)", 
                 "Full Multimodal (Transcribe Audio + Describe Visuals)"]
            )
            
        if st.button("Process & Inject to Neo4j"):
            with st.spinner(f"Processing {uploaded_file.name}..."):
                
                # 1. Save the file locally
                save_dir = "staging_uploads"
                os.makedirs(save_dir, exist_ok=True)
                file_path = os.path.join(save_dir, uploaded_file.name)
                
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                st.success(f"✅ File staged at: `{file_path}`")
                
                # 2. Route to the correct extraction pipeline
                st.info("Initiating extraction protocols...")
                
                try:
                    if ext == 'mp4':
                        if "Transcribe" in video_mode or "Multimodal" in video_mode:
                            st.write("🎙️ Ripping audio and running Whisper transcription...")
                            process_audio(file_path)
                            st.write("✅ Speech transcribed, embedded, and injected into Neo4j!")
                            
                        if "Visuals" in video_mode or "Multimodal" in video_mode:
                            st.write("👁️ Extracting keyframes and analyzing visual context...")
                            output_frames_dir = os.path.join("staging_uploads", "video_frames")
                            process_video_as_one_node(file_path, output_frames_dir)
                            st.write("✅ Visual frames analyzed, embedded, and injected into Neo4j!")
                            
                    elif ext in ['jpg', 'png']:
                        st.write("🖼️ Analyzing image context with Qwen Vision and generating embeddings...")
                        process_and_inject_image(file_path)
                        st.write("✅ Image processed, embedded, and injected into Neo4j as an ImageChunk!")
                        
                    elif ext in ['pdf', 'txt']:
                        st.info("📄 Document chunking pipeline pending connection.")
                    
                    st.success(f"🎉 **{uploaded_file.name}** successfully processed and injected into the graph!")
                    
                except Exception as e:
                    st.error(f"Ingestion failed: {e}")

# --- TAB 3: VISUAL GRAPH EXPLORER ---
with tab_graph:
    st.markdown("### Live Database Topology")
    
    # Visual color legend for nodes
    st.markdown("""
    <div style='background-color: #1E1E1E; padding: 10px; border-radius: 5px; margin-bottom: 15px;'>
        <b>Node Legend:</b> &nbsp;&nbsp;
        <span style='color:#4B8BBE;'>⬤ Document</span> &nbsp;&nbsp;|&nbsp;&nbsp; 
        <span style='color:#F5A623;'>⬤ Audio</span> &nbsp;&nbsp;|&nbsp;&nbsp; 
        <span style='color:#9013FE;'>⬤ Video</span> &nbsp;&nbsp;|&nbsp;&nbsp; 
        <span style='color:#50E3C2;'>⬤ Image</span> &nbsp;&nbsp;|&nbsp;&nbsp; 
        <span style='color:#F7A7A6;'>⬤ Extracted Entity</span>
    </div>
    """, unsafe_allow_html=True)
    
    if "graph_loaded" not in st.session_state:
        st.session_state.graph_loaded = False

    col1, col2 = st.columns([2, 8])
    with col1:
        if st.button("🔄 Refresh Graph"):
            st.session_state.graph_loaded = True

    COLOR_MAP = {
        "DocumentChunk": "#4B8BBE",
        "AudioTranscript": "#F5A623",
        "Video": "#9013FE",
        "ImageChunk": "#50E3C2",
        "ExtractedEntity": "#F7A7A6"
    }

    if st.session_state.graph_loaded:
        with st.spinner("Traversing active graph nodes..."):
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            
            # ⚡ UPGRADED QUERY: Fetches both Entities AND Similar_To connections
            query = """
            MATCH (file)
            WHERE (file:AudioTranscript OR file:ImageChunk OR file:Video 
                   OR (file:DocumentChunk AND (file.file_name IS NOT NULL OR file.name IS NOT NULL)))
                   
            OPTIONAL MATCH (file)-[r:MENTIONS|SIMILAR_TO]->(target)
            
            RETURN elementId(file) AS source_uid,
                   COALESCE(file.file_name, file.name, labels(file)[0]) AS source_name, 
                   labels(file)[0] AS source_label, 
                   elementId(target) AS target_uid,
                   COALESCE(target.name, target.file_name, labels(target)[0]) AS target_name, 
                   labels(target)[0] AS target_label,
                   type(r) AS rel_type
            LIMIT 200
            """
            
            nodes = []
            edges = []
            added_nodes = set()
            
            with driver.session() as session:
                results = session.run(query)
                for record in results:
                    src_uid = record["source_uid"]
                    src_name = record["source_name"]
                    src_label = record["source_label"] or "DocumentChunk"
                    tgt_uid = record["target_uid"]
                    tgt_name = record["target_name"]
                    tgt_label = record["target_label"]
                    
                    # 1. Draw the main file node
                    if src_uid not in added_nodes:
                        color = COLOR_MAP.get(src_label, "#4B8BBE")
                        nodes.append(Node(id=src_uid, label=src_name, size=25, color=color))
                        added_nodes.add(src_uid)

                    # 2. Draw the connected node (can be an Entity OR another File)
                    if tgt_uid and tgt_name:
                        if tgt_uid not in added_nodes:
                            tgt_size = 15 if tgt_label == "ExtractedEntity" else 25
                            tgt_color = COLOR_MAP.get(tgt_label, COLOR_MAP["ExtractedEntity"])
                            nodes.append(Node(id=tgt_uid, label=tgt_name, size=tgt_size, color=tgt_color))
                            added_nodes.add(tgt_uid)
                        
                        # 3. Draw the line (Green for SIMILAR_TO, Default for MENTIONS)
                        rel_type = record["rel_type"]
                        edge_color = "#50E3C2" if rel_type == "SIMILAR_TO" else "#F7A7A6"
                        edges.append(Edge(source=src_uid, target=tgt_uid, label=rel_type, color=edge_color))
            
            driver.close()
            
            config = Config(
                height=650,
                width=1000,
                nodeHighlightBehavior=True,
                highlightColor="#FFFF00",
                directed=True,
                collapsible=False,
                physics=True,
                gravity=-180,
                linkDistance=140,
                node={'labelProperty': 'label', 'renderLabel': True}
            )
            
            agraph(nodes=nodes, edges=edges, config=config)