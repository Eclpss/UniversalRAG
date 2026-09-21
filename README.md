# 🌐 UniversalRAG

---

## 🧪 Quick Test: Ingestion via Dashboard

To test ingestion without running massive dataset batch jobs:

1. Launch the dashboard:
   ```bash
   streamlit run dashboard.py
   ```
2. Drag and drop any `.mp4`, `.mp3`, `.pdf`, `.txt`, or image directly into the drop zone.
3. The pipeline will automatically extract entities, generate embeddings, and map the relationships into your graph.
4. Open the [Neo4j Browser](http://localhost:7474) to inspect the newly formed nodes and relationships.

> 📘 **Database Setup:** For complete Neo4j installation, Bolt configuration, and APOC plugin setup, see [Module 6: Neo4j Installation & Setup Guide](#https://docs.google.com/document/d/1zNhamFbTweRsDvzDcp3bW7FS5M5n9f0D8rbZ7fkSyuE/edit?usp=sharing) below.

---

## 🛠️ Architecture & Windows (Git Bash) Port

The original research codebase relied on Linux system utilities (`parallel`, `curl -C -`, `tar -xf`, and native Unix directory commands). Running this on Windows requires **Git Bash** to emulate a Unix shell for dataset scripts like `get_infoseek.sh`, `get_hybridqa.sh`, and `get_nq.sh`.

```
UniversalRAG/
├── dataset/                  # Benchmark datasets & parquet pipelines
│   ├── HybridQA/             # Tabular + text extraction
│   ├── infoseek/             # Multi-shard image/text extraction
│   ├── query/                # Benchmark JSON evaluation sets
│   ├── merge_datasets.py     # Unifies parquet shards into single collections
│   └── *.parquet             # Extracted multimodal features
├── ingestions/               # Real-time processing engines
│   ├── audio_pipeline.py     # Whisper transcription & chunking
│   ├── video_pipeline.py     # Keyframe extraction & OCR
│   ├── image_pipeline.py     # Visual embedding extraction
│   └── entity_extraction.py  # Spacy/LLM graph entity extraction
├── fast_app.py               # Flask Fast Router with LLM guardrails
└── dashboard.py              # Streamlit interactive UI
```

---

## 💻 Full Installation & Setup

### 1. Environment Initialization (Git Bash)

Open Git Bash in your working directory:

```bash
# Clone the repository
git clone https://github.com/Eclpss/UniversalRAG.git
cd UniversalRAG

# Initialize and activate Python virtual environment
python -m venv .venv
source .venv/Scripts/activate

# Install core system dependencies
pip install --upgrade pip
pip install flask requests neo4j streamlit python-dotenv
```

### 2. Multimodal & Ingestion Dependencies

To run the video, audio, and visual pipelines:

```bash
# PyTorch with CUDA support (adjust version based on your GPU)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Audio & Vision extraction tools
pip install openai-whisper opencv-python pillow sentence-transformers
```

### 3. Running Benchmark Extraction Scripts

For large batch extraction (e.g., InfoSeek, HybridQA), execute the adapted bash scripts inside Git Bash:

```bash
cd dataset/infoseek
bash get_infoseek.sh
```

> ⚠️ **Note:** Ensure your GPU has sufficient VRAM when running `merge_datasets.py` and processing high-volume parquets — pipeline embedding extraction will push GPU utilization near 100%.

---

## 🧠 Running the Backend Query Engine

The system uses a two-tier routing engine (`fast_app.py`) to handle natural language questions without hardcoded paths:

- **Fast Lane:** Intercepts known patterns (e.g., mention counts) using regex.
- **Slow Lane:** Scans dynamic database schema (`CALL db.schema.nodeTypeProperties()`) and translates natural language into universal Cypher queries via local LLMs.

### 1. Ensure Ollama is running and load the coder model:

```bash
ollama run qwen2.5-coder:7b
# Or for larger setups:
# ollama run qwen2.5-coder:14b
```

### 2. Start the Fast Router:

```bash
python fast_app.py
```

The router listens on `http://127.0.0.1:5001/ask_neo4j`.
