# AGI Screener

> The first agentic candidate evaluation system built using Next.js, FastAPI, and LangGraph — screen and grade technical hires autonomously using resume-grounded retrieval-augmented generation.

![Next.js](https://img.shields.io/badge/Next.js-v14.2.3-black?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-Active-blue?style=flat-square)
![LangGraph](https://img.shields.io/badge/LangGraph-Engine-purple?style=flat-square)
![MongoDB](https://img.shields.io/badge/MongoDB-Persisted-green?style=flat-square)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-orange?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-gray?style=flat-square)

---

Recruiting is slow. Ingesting resumes is manual. Standard tests are easily cheated by online models.

Until now.

AGI Screener is a complete candidate evaluation workspace that gives hiring managers the ability to autonomously configure, conduct, and grade conversational technical interviews. Questions are dynamically generated from the candidate's own resume using a full RAG pipeline — the resume is chunked, embedded, stored in a vector database, and retrieved to ground every question and evaluation in what the candidate actually claims to know.


## How It Works

```mermaid
sequenceDiagram
    participant C as Candidate
    participant F as Frontend (Next.js)
    participant B as Backend (FastAPI)
    participant V as ChromaDB (Vector Store)
    participant D as MongoDB

    C->>F: Upload Resume (PDF) & Select Role
    F->>B: POST /api/interview/start (form-data)
    B->>B: Parse PDF & Extract Raw Text + Skills
    B->>V: Chunk Resume → Embed → Store (per-session collection)
    B->>V: Retrieve relevant resume chunks per skill
    B->>B: Call Gemini (Generate 5 RAG-grounded questions)
    B->>D: Insert Session (Name, Email, Phone, Questions, Retrieved Context)
    B-->>F: Return session_id & Q1
    F-->>C: Display Q1 on screen
    
    C->>F: Submit Answer
    F->>B: POST /api/interview/submit (JSON)
    B->>D: Update MongoDB Log with Answer
    B->>B: Step < 5?
    B-->>F: Yes (Fetch Q_next from Pregenerated List)
    F-->>C: Display Q_next
    
    B-->>B: No (Final step answered)
    Note over F,B: Transition to Insights screen (displays pulsing skeleton dashboard)
    B->>V: For each answer → Retrieve matching resume chunks
    B->>B: Gemini evaluates (Resume Claims vs Actual Answers)
    B->>D: Mark Session COMPLETED & Save Evaluation Summary
    B->>V: Cleanup session collection
    B-->>F: Return completed status & evaluation_summary
    F-->>C: Fill Report Dashboard (scores, report, transcript tree)
```

---

## Architecture

```mermaid
graph TD
    subgraph Client Layer
        FL[Next.js Client Components]
        DZ[Drag-and-Drop Dropzone]
        CH[Chat Conversation Panel]
        EV[Insights Dashboard View]
    end

    subgraph FastAPI Application Layer
        RTR[Interview API Router]
        DB[Database Connection Dependency]
        RP[Resume Keyword Parser]
        CFG[Central Application Config]
    end

    subgraph RAG Pipeline
        ING[Resume Ingestion: Chunk + Embed]
        RET[Similarity Search Retrieval]
        CLN[Session Cleanup]
    end

    subgraph LangGraph Execution Engine
        SM[State Machine Router]
        GQ[Question Generation with RAG Context]
        FN[Evaluation with Resume vs Reality]
        CR[Conditional Edge Router]
    end

    subgraph Infrastructure Persistence Layer
        MDB[MongoDB Sessions Collection]
        CDB[ChromaDB Per-Session Vector Store]
        GEM[Google Gemini LLM Engine]
    end

    FL --> RTR
    DZ --> RP
    CH --> RTR
    EV --> RTR

    RTR --> DB
    RTR --> ING
    RTR --> SM
    
    ING --> CDB
    RET --> CDB
    CLN --> CDB

    SM --> GQ
    SM --> FN
    SM --> CR

    GQ --> RET
    GQ --> GEM
    FN --> RET
    FN --> GEM

    DB --> MDB
```

---

## RAG Pipeline

The RAG pipeline uses the **candidate's uploaded resume** as the knowledge base document. Each interview session gets its own isolated vector store collection.

### Flow

```mermaid
flowchart TD
    classDef process fill:#1e293b,stroke:#334155,color:#f8fafc;
    classDef storage fill:#1e293b,stroke:#10b981,color:#f8fafc;
    classDef decision fill:#1e293b,stroke:#f59e0b,color:#f8fafc;

    subgraph "1. Knowledge Ingestion (per session)"
        A1[Candidate Resume PDF]:::process --> A2[pypdf Text Extraction]:::process
        A2 --> A3["Recursive Splitting (600 chars / 60 overlap)"]:::process
        A3 --> A4["Google Gemini Embeddings (text-embedding-004)"]:::process
        A4 --> A5[("ChromaDB Collection: s_{session_id}")]:::storage
    end

    subgraph "2. Retrieval for Question Generation"
        B1[Skills + Role from Resume]:::process --> B2["Dynamic Query: '{skill} experience projects work {role}'"]:::process
        B2 --> B3[Query Vectorization]:::process
        B3 --> B4[Similarity Search Against Resume Chunks]:::process
        A5 -.-> B4
        B4 --> B5[Top-K Resume Chunks Retrieved]:::process
        B5 --> B6["Gemini Prompt: Retrieved Context + Resume → 5 Grounded Questions"]:::process
    end

    subgraph "3. Retrieval for Evaluation"
        C1[Candidate Answer Text]:::process --> C2[Similarity Search per Answer]:::process
        A5 -.-> C2
        C2 --> C3["Resume Claims Matched to Answer"]:::process
        C3 --> C4["Gemini Evaluates: Resume Claims vs Demonstrated Knowledge"]:::process
        C4 --> C5[Structured Report with 'Resume vs Reality' Section]:::process
    end

    subgraph "4. Cleanup"
        D1[Evaluation Complete]:::decision --> D2[Delete Session Collection from ChromaDB]:::process
    end
```

### Design Choices

| Parameter | Configuration | Rationale |
|---|---|---|
| Knowledge Source | Candidate's uploaded resume PDF | Questions probe what the candidate *claims* to know — the resume IS the knowledge base |
| Collection Scope | Per-session (`s_{session_uuid}`) | Isolates each candidate's data; enables parallel interviews |
| Split Strategy | `RecursiveCharacterTextSplitter` | Preserves semantic boundaries (paragraphs → sentences → words) |
| Chunk Size | 600 characters | Retains concise, contextual blocks covering resume sections |
| Chunk Overlap | 60 characters | Maintains context continuity across chunk boundaries |
| Embeddings Model | `models/text-embedding-004` | Google's latest high-accuracy embedding model |
| Vector Store | ChromaDB (local disk-persisted) | Zero-infrastructure vector search; persists across restarts |
| Retrieval (Questions) | Per-skill queries, top-3 per skill, deduplicated, max 10 chunks | Ensures questions cover multiple resume areas |
| Retrieval (Evaluation) | Per-answer similarity search, top-3 chunks | Cross-references what resume claims vs what candidate demonstrated |
| Cleanup Policy | Delete collection after evaluation | Keeps storage clean on deployment |

### Traceability (Context → Question → Answer → Storage)

Every question stored in MongoDB includes a `retrieved_context` field — an array of the exact resume chunks that were retrieved from ChromaDB and used to generate that question. This provides full traceability of the RAG pipeline:

```json
{
  "question": "You mentioned implementing a RAG pipeline with LangChain...",
  "answer": "I used RecursiveCharacterTextSplitter with...",
  "retrieved_context": [
    "Built an AI-powered document retrieval system using LangChain, ChromaDB...",
    "Implemented RAG pipeline for knowledge-grounded question answering..."
  ],
  "timestamp": "2026-07-07T12:30:00Z"
}
```

---

## API Reference

### Endpoints

| Endpoint | Method | Request Body | Description |
|---|---|---|---|
| `/api/interview/start` | POST | `multipart/form-data` (PDF + Role) | Parses resume, ingests into ChromaDB, generates 5 RAG-grounded questions, returns Q1 |
| `/api/interview/submit` | POST | `JSON` (Session ID + Answer) | Records answer, advances to next question or triggers RAG-verified evaluation |
| `/api/interview/summary/{id}`| GET | None | Retrieves complete Q/A transcript with retrieved context and evaluation report |

---

## Environment Variables

### Backend Configuration
Configure these settings inside `backend/.env`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | — | Google Gemini LLM API authorization key |
| `MONGODB_URL` | No | `mongodb://localhost:27017` | URI connection string for MongoDB instance |
| `MONGODB_DB_NAME` | No | `screener_db` | Collection database name inside MongoDB |
| `APP_TITLE` | No | `PG AGI Screener API` | Name identifier for FastAPI application |
| `MAX_INTERVIEW_QUESTIONS`| No | `5` | Turns limit before evaluation finalization |

### Frontend Configuration
Configure these settings inside `frontend/.env`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` | Backend API base URL for fetch requests |

---

## Local Setup

### System Pre-requisites
- Node.js version 18.0.0 or higher
- Python version 3.11.0 or higher
- Active local or cloud instance of MongoDB

### Backend Startup

Run these commands inside the `backend/` directory:

1. **Activate Python Virtual Environment**:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. **Install Package Dependencies**:
   ```bash
   uv pip install -r requirements.txt
   ```
   *(Or standard pip if uv is not configured: `pip install -r requirements.txt`)*
3. **Start FastAPI Application Server**:
   ```bash
   python -m uvicorn main:app --reload --port 8000
   ```

Verify route registration by visiting: `http://127.0.0.1:8000/docs`

---

### Frontend Startup

Run these commands inside the `frontend/` directory:

1. **Install Node Packages**:
   ```bash
   npm install
   ```
2. **Start Web Client Development Server**:
   ```bash
   npm run dev
   ```

Access the client application by visiting: `http://localhost:3000`

---

## Project Structure

```
pg-agi-screener/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── interview.py          # FastAPI routes (start, submit, summary)
│   │   ├── core/
│   │   │   ├── config.py             # Pydantic settings from .env
│   │   │   └── database.py           # Motor async MongoDB client
│   │   ├── rag/
│   │   │   └── ingest.py             # RAG pipeline: chunk, embed, store, retrieve, cleanup
│   │   ├── schemas/
│   │   │   └── interview.py          # Pydantic request/response/DB models
│   │   └── services/
│   │       ├── interview_graph.py    # LangGraph state machine + Gemini Q&A generation
│   │       └── resume_parser.py      # PDF text/skill extraction
│   ├── chroma_db/                    # ChromaDB persistent storage (auto-created)
│   ├── main.py                       # FastAPI app entry point
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx              # Main UI: Welcome → Chat → Insights
│       │   ├── layout.tsx            # Root layout
│       │   └── globals.css           # Global styles
│       ├── components/ui/            # Reusable UI components
│       └── lib/                      # Utilities
└── README.md
```

---

## Why LangGraph for Interviews

| Feature | LangGraph State Machine | Standard Linear Chain |
|---|---|---|
| Conversation Loop Routing | Non-linear routing based on step counters | Strictly linear pipeline execution |
| Memory Management | Persistent checkpointer (thread-scoped) | Stateless context payload builder |
| Yielding State Mid-Flow | Supported (pauses at END awaiting inputs) | Not supported (requires full run execution) |
| Non-Blocking REST Integration | Highly viable (stateless load-save logic) | Requires manually passing chat history |

---

## Key Features

- **Resume-as-Knowledge-Base RAG** — The candidate's resume is chunked, embedded, and stored in ChromaDB. Questions are generated from retrieved resume sections, not generic templates.
- **Resume vs Reality Evaluation** — During grading, each answer is similarity-searched against resume chunks to explicitly compare what the candidate claimed vs what they demonstrated.
- **Full Traceability** — Every question stores the exact resume chunks that influenced its generation (`retrieved_context` field in MongoDB).
- **Per-Session Vector Isolation** — Each candidate gets their own ChromaDB collection, deleted after evaluation.
- **Devil's Advocate Grading** — Strict evaluation with scores as low as 0.5/10 for placeholder answers.
- **Zero-Dependency PDF Parsing** — pypdf-based extraction with regex skill matching.
- **Skeleton Loading States** — Premium pulsing skeleton dashboard while evaluation generates.

---

## Tech Stack

- **Frontend**: Next.js 14, React 18, Tailwind CSS, TypeScript, Lucide Icons, Framer Motion
- **Backend**: FastAPI, Uvicorn, Python 3.11, Motor Async MongoDB Driver
- **AI/ML Engine**: LangGraph, LangChain, Google Gemini API, ChromaDB
- **Embeddings**: Google `text-embedding-004` via `langchain-google-genai`
- **Vector Store**: ChromaDB (local disk-persisted, per-session collections)
- **Persistence**: MongoDB (sessions, logs, evaluation reports)

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss options.

---

## License

MIT — see [LICENSE](./LICENSE)
