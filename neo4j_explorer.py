import streamlit as st
import pandas as pd
from neo4j import GraphDatabase

# Configure the Streamlit page
st.set_page_config(page_title="Neo4j RAG Explorer", layout="wide")
st.title("🔍 Multi-Graph RAG: Neo4j Explorer")

# Sidebar Connection
st.sidebar.header("Database Connection")
URI = st.sidebar.text_input("URI", "bolt://localhost:7687")
USER = st.sidebar.text_input("User", "neo4j")
PASSWORD = st.sidebar.text_input("Password", "password", type="password")

@st.cache_resource
def get_driver(uri, user, password):
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver
    except Exception as e:
        st.sidebar.error(f"Connection failed: {e}")
        return None

driver = get_driver(URI, USER, PASSWORD)

if driver:
    st.sidebar.success("✅ Connected to Neo4j!")
    
    def run_query(query):
        with driver.session() as session:
            result = session.run(query)
            return [record.data() for record in result]

    # --- 1. DYNAMICALLY FETCH ALL NODE LABELS ---
    labels_result = run_query("CALL db.labels()")
    all_labels = [record['label'] for record in labels_result]
    
    if not all_labels:
        st.warning("No data found in Neo4j yet!")
    else:
        # --- 2. DROPDOWN SELECTOR ---
        st.subheader("🗂️ Select Database Collection")
        selected_label = st.selectbox("Choose a category (Node Label) to inspect:", all_labels)
        
        # --- 3. DYNAMIC DASHBOARD METRICS ---
        st.subheader(f"📊 Health Metrics for '{selected_label}'")
        col1, col2 = st.columns(2)
        
        # Calculate totals dynamically
        total_nodes = run_query(f"MATCH (n:{selected_label}) RETURN count(n) AS count")[0]['count']
        
        # Calculate valid text
        text_query = f"MATCH (n:{selected_label}) WHERE n.text IS NOT NULL AND n.text <> 'None' AND n.text <> '' RETURN count(n) AS count"
        text_nodes = run_query(text_query)[0]['count']
        
        col1.metric("Total Nodes in Collection", total_nodes)
        col2.metric("Nodes with Valid Text", text_nodes)

        st.divider()

        # --- 4. DYNAMIC DATA EXPLORER (UI PREVIEW) ---
        st.subheader(f"👁️ Preview '{selected_label}' Data")
        st.info("Showing a limited preview to prevent browser crashes. Use the download section below for the full dataset.")
        limit = st.slider("Number of nodes to preview:", 5, 200, 10)
        
        if st.button(f"Fetch Preview for {selected_label}"):
            data = run_query(f"MATCH (n:{selected_label}) RETURN properties(n) AS Data LIMIT {limit}")
            
            if data:
                flat_data = [d['Data'] for d in data]
                df = pd.DataFrame(flat_data)
                
                if 'text' in df.columns:
                    cols = ['text'] + [c for c in df.columns if c != 'text']
                    df = df[cols]
                    
                st.dataframe(df, use_container_width=True)
            else:
                st.warning(f"No valid data found for {selected_label}.")

        st.divider()

       # --- 5. CSV EXPORT ENGINE (FAST FETCH + PROGRESS BAR) ---
        st.subheader(f"📥 Export Full Database")
        st.write(f"Download all **{total_nodes:,}** nodes from `{selected_label}` as a complete `.csv` file.")
        
        if st.button(f"Generate CSV for all {total_nodes:,} nodes"):
            try:
                # 1. Dynamically get all property keys
                keys_query = f"MATCH (n:{selected_label}) WITH keys(n) AS keys UNWIND keys AS key RETURN DISTINCT key"
                keys_result = run_query(keys_query)
                
                # 2. Exclude massive 'embedding' arrays
                safe_keys = [k['key'] for k in keys_result if k['key'] not in ['embedding', 'vector']]
                
                if not safe_keys:
                    st.warning("No exportable text data found.")
                else:
                    return_clause = ", ".join([f"n.{k} AS {k}" for k in safe_keys])
                    all_data_query = f"MATCH (n:{selected_label}) RETURN {return_clause}"
                    
                    # --- PROGRESS BAR SETUP ---
                    st.info("📡 Initiating data stream from Neo4j...")
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    all_data = []
                    
                    # 3. Stream data with an open session so we can track progress
                    with driver.session() as session:
                        result = session.run(all_data_query)
                        
                        for i, record in enumerate(result):
                            all_data.append(record.data())
                            
                            # Update UI every 1,000 rows to prevent lagging
                            if i % 1000 == 0 and total_nodes > 0:
                                percent_complete = min(i / total_nodes, 1.0)
                                progress_bar.progress(percent_complete)
                                status_text.text(f"Streaming Data: {i:,} / {total_nodes:,} records fetched...")
                    
                    # Max out progress bar when done fetching
                    progress_bar.progress(1.0)
                    status_text.text(f"✅ Fetched all {total_nodes:,} records! Structuring data...")
                    
                    if all_data:
                        # 4. Build DataFrame and format
                        df_all = pd.DataFrame(all_data)
                        if 'text' in df_all.columns:
                            cols = ['text'] + [c for c in df_all.columns if c != 'text']
                            df_all = df_all[cols]
                        
                        status_text.text(f"✅ Data structured! Encoding to CSV...")
                        
                        # 5. Convert to CSV
                        csv_data = df_all.to_csv(index=False).encode('utf-8')
                        
                        status_text.text(f"🎉 Export complete! Your file is ready.")
                        
                        st.download_button(
                            label="⬇️ Download .csv File",
                            data=csv_data,
                            file_name=f"Neo4j_{selected_label}_Optimized_Export.csv",
                            mime="text/csv"
                        )
                    else:
                        st.warning("No data found to export.")
            except Exception as e:
                st.error(f"Failed to generate CSV file: {e}")

        st.divider()
    # --- CUSTOM QUERY ENGINE ---
    st.subheader("⚡ Custom Cypher Query")
    user_query = st.text_area("Write your Cypher query here:", "MATCH (n) RETURN n LIMIT 5")
    if st.button("Run Query"):
        try:
            results = run_query(user_query)
            st.write(results)
        except Exception as e:
            st.error(f"Error executing query: {e}")