# NeuroRelate — AI-Native RDBMS for Enterprise RAG

NeuroRelate is an enterprise-grade AI-native Relational Database Management System (RDBMS) tailored for Retrieval-Augmented Generation (RAG). It combines relational ACID guarantees, normalized table hierarchies, and cascading foreign-key integrity with multi-stage hybrid semantic retrieval and grounded AI generation.

---

## 🌟 Key Highlights & Capabilities

- **Relational Data Architecture**: Normalized tables (`documents`, `document_chunks`, `query_history`) with cascading deletes (`ON DELETE CASCADE`) to prevent orphaned chunks.
- **Dual-Engine RDBMS Storage**:
  - Native **MySQL 8.0** connectivity with custom connection pooling.
  - Automatic, zero-configuration **SQLite** fallback (`neurorelate.db`) for instant local development and offline environments.
- **Hybrid Retrieval Engine**:
  - Multi-stage retrieval combining exact-phrase boost, BM25 / TF-IDF term coverage scoring, and length normalization.
  - Document-level scoped search or broad corpus search.
- **Grounded Enterprise AI Generation**:
  - Direct integration with **Google Gemini API** (`gemini-2.5-flash`).
  - Compatible with custom OpenAI / Ollama endpoints.
  - Zero-dependency built-in extractive synthesizer for offline environments.
  - Full provenance citations (`[Source: filename, Chunk #X]`) to guard against hallucinations.
- **Interactive Web Interface & SQL Console**:
  - Modern dark enterprise dashboard inspired by Tailwind CSS and Shadcn UI.
  - Ingestion Zone with drag-and-drop document upload and chunk inspector.
  - Interactive AI Chat with starter queries and cited sources.
  - Live SQL Query Console allowing real-time inspection of database tables.

---

## 🗄️ Relational Database Schema

```sql
-- Master documents table
CREATE TABLE documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    upload_date DATETIME NOT NULL,
    extracted_text LONGTEXT,
    file_size INT DEFAULT 0,
    chunk_count INT DEFAULT 0
);

-- Normalized semantic chunks with foreign key cascade
CREATE TABLE document_chunks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_number INT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- Query telemetry and provenance audit log
CREATE TABLE query_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source_document VARCHAR(255),
    created_at DATETIME NOT NULL
);
```

---

## 🚀 Quick Start Guide

### 1. Requirements
- Python 3.10+ (Python 3.14 recommended)
- (Optional) MySQL 8.0+ (If MySQL is not installed or running, SQLite is used automatically)

### 2. Install Dependencies
```bash
pip install -r neurorelate/requirements.txt
```

### 3. Environment Configuration
Edit `neurorelate/.env` with your settings:
```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=neurorelate_db
DB_PORT=3306

# Optional: Add your Gemini API key for full generative responses
GEMINI_API_KEY=your_gemini_api_key_here
```

### 4. Run the Platform
You can start the server directly using:
```bash
python run.py
```
Or from the `neurorelate` directory:
```bash
cd neurorelate
python app.py
```

Open your browser and navigate to:
👉 **`http://127.0.0.1:5000`**

---

## 📂 Project Structure

```
RDBMS project/
├── run.py                       # Root launcher script
├── README.md                    # Project documentation
├── fronted/                     # Reference designs & styling
│   ├── 1.html
│   └── 2.css
└── neurorelate/                 # Main Application Package
    ├── app.py                   # Flask server, routing, and REST API
    ├── database.py              # Dual MySQL / SQLite engine adapter
    ├── document_processor.py    # Text extraction & relational chunking
    ├── retrieval.py             # Hybrid BM25 & phrase search engine
    ├── ai_service.py            # Gemini LLM & grounded RAG generator
    ├── schema.sql               # Relational DDL definitions
    ├── requirements.txt         # Python package dependencies
    ├── .env                     # Environment configuration
    ├── static/
    │   ├── css/style.css        # Enterprise dark theme
    │   ├── js/main.js           # Client-side notifications & utilities
    │   └── uploads/             # Ingested file storage
    └── templates/
        ├── base.html            # Core layout & navigation
        ├── index.html           # Landing page
        ├── dashboard.html       # Analytics & telemetry
        ├── upload.html          # Drag-and-drop ingestion & chunk inspector
        ├── chat.html            # AI chat interface with citations
        ├── search.html          # Hybrid chunk search engine
        ├── database.html        # Interactive SQL query console
        └── about.html           # Architecture & API reference
```

---

## 📡 REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/documents/upload` | Ingests a file, extracts text, chunks, and commits to RDBMS |
| `GET` | `/api/documents` | Returns all indexed documents and metadata |
| `GET` | `/api/documents/<id>/chunks` | Returns all relational chunks for a document |
| `DELETE`| `/api/documents/<id>` | Cascading delete of document and associated chunks |
| `POST` | `/api/search` | Performs hybrid search across document chunks |
| `POST` | `/api/chat` | Executes RAG question answering with grounded citations |
| `POST` | `/api/database/query` | Executes safe read-only SQL queries in the SQL console |
| `GET` | `/api/stats` | Returns real-time database and query telemetry |

---

## 📄 License
MIT License. Created for RDBMS & AI Knowledge Management projects.
