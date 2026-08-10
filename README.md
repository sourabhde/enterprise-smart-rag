# 🧠 Enterprise Smart RAG Workspace

A production-grade Retrieval-Augmented Generation (RAG) platform designed with industry-standard architecture, semantic vector chunking, hybrid retrieval, and real-time observability.

## 🏗️ Architecture & Core Pipeline

1. **Multi-Format Ingestion:** Parses text, documents, and PDFs into clean structural blocks.
2. **True Semantic Chunking:** Analyzes embedding shifts between consecutive sentences using cosine distance thresholds.
3. **Embedding Generation:** Uses local embeddings (all-MiniLM-L6-v2) via HuggingFace sentence-transformers.
4. **Vector Database & Similarity:** In-memory vector index calculating exact cosine similarity scores.
5. **Hybrid Retrieval:** Combines semantic vector distance with keyword scoring.
6. **Context Re-Ranking & Filtering:** Filters out noise and prioritizes highest-scoring context segments.
7. **LLM Generation Engine:** Powered by Llama-3.3-70b-versatile via Groq.
8. **Observability & Guardrails:** Real-time telemetry monitoring latency and factual evaluation scores.

## 🚀 Key Features

* **Contextual Vector Inspector:** Open an interactive dialog from any AI response to inspect evaluated chunks, active status indicators, and cosine similarities.
* **Dynamic Execution Modes:** Toggle seamlessly between Auto, Private, and General modes.

## 🛠️ Tech Stack

* **Frontend / UI:** Streamlit
* **Orchestration:** Python, NumPy, Scikit-Learn
* **Embeddings:** Sentence-Transformers (all-MiniLM-L6-v2)
* **LLM Provider:** Groq API (Llama-3.3-70b-versatile)
* **Document Parsing:** PyPDF


## ⚙️ Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/sourabhde/enterprise-smart-rag.git
cd enterprise-smart-rag
```

### 2. Install Dependencies
```bash
pip install streamlit pandas python-dotenv groq pypdf numpy scikit-learn sentence-transformers
```

### 3. Set Up Environment Variables
Create a .env file in the root directory and add your Groq API key:
```env
GROQ_API_KEY=your_actual_groq_api_key_here
```

### 4. Run the Application
```bash
streamlit run app.py
```
