# AI Research Lab

> A collaborative Research IDE: VS Code + GitHub + Jupyter + Overleaf + an AI research assistant — built specifically for research.

---

## ⚡ Quickstart

### 1. Set Up Environment & Install Dependencies
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

*Note: If `SUPABASE_URL` and `SUPABASE_ANON_KEY` are not provided, AI Research Lab runs seamlessly in Local Development Storage Mode with full schema and role enforcement.*

### 3. Initialize Database (for Live Supabase)
Execute the SQL statements from `schema.sql` directly in your Supabase SQL Editor. This provisions the tables (`profiles`, `projects`, `project_members`, `papers`, `research_notes`) and enables Row-Level Security (RLS) policies.

### 4. Run Development Server
```bash
python app.py
```
Open [http://localhost:5001](http://localhost:5001) in your browser.

---

## 🔬 Architecture & Technology Stack

| Component | Choice | Rationale |
|---|---|---|
| **Frontend** | HTML5 + CSS3 + Vanilla JavaScript | No framework churn or complex build steps; clean and maintainable |
| **Backend** | Python + Flask | Unified language for routing, AI pipelines, and data manipulation |
| **Database** | Supabase (PostgreSQL) + RLS | Relational integrity and DB-level role security (`Owner`, `Researcher`, `Viewer`) |
| **Auth** | Supabase Auth (Email/Password + Google OAuth) | Secure, standards-compliant session management |
| **Literature Search** | Semantic Scholar + arXiv APIs | Live academic discovery with citations, DOIs, and open-access PDFs |
| **PDF Extraction & Reader** | PyMuPDF | In-browser reading, section/page parsing, and interactive annotations |
| **AI Layer** | Gemini API + FAISS + Sentence Transformers | Project-grounded RAG with explicit source citations |
| **Version Control** | Real Git (system subprocess) | True decentralized revision control and file tree inspection |

---

## 📚 Features Overview

- **Collaborative Workspaces:** Multi-user research projects with PostgreSQL RLS security (`Owner`, `Researcher`, `Viewer` roles).
- **Literature Discovery:** Live search across millions of papers via Semantic Scholar Graph & arXiv APIs.
- **Project Paper Library:** Save open-access literature, cache PDFs, and organize metadata with zero fabricated numbers.
- **In-App Reader & Annotations:** Read extracted papers in-browser, highlight passages with semantic tags, and collaborate on margin notes with team members.
- **Project-Scoped Research AI (RAG):** Local FAISS vector search powered by Sentence Transformers. Answers literature questions strictly grounded in saved papers with explicit `[Paper Title, p. X]` receipts.
- **Knowledge & Concept Graph:** Dynamic ontology extraction across literature (`methods`, `datasets`, `tasks`, `metrics`, `concepts`) with directed relationship links and passage quote receipts. Interactive canvas visualizer with physics force simulation, category filters, and concept matrix.
- **Research Notes & Journal:** Timestamped markdown notes capturing team observations, methodology logs, and direct AI synthesis captures.
- **Git Version Control & File Tree:** Auto-initialized local Git repository per project with real commit history, file browsing, and milestone tracking.






