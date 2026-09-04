# AGENTS.md — AI Research Lab

You are building **AI Research Lab**, a collaborative Research IDE.

> "VS Code + GitHub + Jupyter + Overleaf + an AI research assistant — built specifically for research."

Read this whole file before writing a single line of code. This is the only
guardrail document for this project. Don't create additional planning docs,
architecture docs, or "notes to self" files unless explicitly told to — one
source of truth beats ten stale ones.

---

## 0. Non-negotiable philosophy

1. **The human owns the research. AI accelerates it.** AI drafts, suggests,
   and flags — it never silently decides, deletes, publishes, or invents a
   result. Anything consequential goes through an explicit approve/reject
   step in the UI.
2. **Every number in a paper has a receipt.** A result on a page must trace
   back to `experiment_id → run → results.json`. If there's no run behind a
   number, the number does not go in the paper, full stop — not even as a
   "placeholder" or "illustrative" value.
3. **Algorithm ≠ Code.** An algorithm (pseudocode, math, complexity) is a
   first-class object, separate from its implementation, and the two are
   linked, not merged. The Methodology section is generated from the
   algorithm object, never from a code dump.
4. **No "generate whole paper" button.** Every section is human-drafted or
   human-edited with AI assistance alongside it (suggest / accept / edit /
   reject), never auto-populated in one shot.
5. **Build like a person, not a scaffold generator.** No dozens of empty
   `services/`, `interfaces/`, `utils/`, `helpers/` folders waiting to be
   filled, no speculative abstractions for problems that don't exist yet.
   Add a folder or a module only when the second real usage of it shows up.
   See §2.
6. **Keep the stack explainable in a viva/interview.** Every technology in
   this stack must be one you can defend line-by-line if asked "why did you
   use this and how does it work under the hood." That's a harder
   constraint than "what's most scalable," and it wins here.

---

## 1. Tech stack — deliberately simple, do not deviate

This is a **college-level flagship project**, not a startup's production
system. The goal is a stack a strong CS student fully understands and can
defend, that still produces a genuinely impressive, real, working product.

| Layer | Technology | Why |
|---|---|---|
| Frontend | **HTML5 + CSS3 + vanilla JavaScript** | You already know this well; no framework overhead, no build step to explain |
| Code editor | **CodeMirror** | Real in-browser code editor, far lighter and easier to reason about than Monaco |
| Backend | **Python + Flask** | Simple routing/APIs, one language across web + AI/ML/data tooling |
| Database | **Supabase (PostgreSQL)** | Proper relational DB with real relationships (User → Team → Project → Papers/Experiments/Datasets/Paper); needed once teams, roles, and permissions are in scope — SQLite would become a limitation fast |
| Auth | **Supabase Auth** | Email/password + Google OAuth, no custom auth to build or explain wrong |
| File storage | **Supabase Storage** | PDFs, datasets, graphs, exported packages |
| Row-level security | **Supabase RLS policies** | Real, DB-enforced permissions — never just hidden in the UI |
| AI | **Gemini API** | Matches your existing project stack |
| RAG | **FAISS + Sentence Transformers** | Simple, local, fully explainable vector search — no managed vector DB to abstract away |
| Academic search | **arXiv API + Semantic Scholar API + Crossref API** | Real paper discovery, no scraping |
| PDF processing | **PyMuPDF** | Extract and read research papers |
| Data / stats | **Pandas + NumPy** | Experiment data and statistical analysis |
| ML baselines | **scikit-learn** | Baseline models for experiments |
| Graphs | **Matplotlib** | Publication-style figures |
| Paper writing | **Markdown + LaTeX** | Simple, real academic writing workflow |
| PDF generation | **Pandoc / LaTeX (latexmk)** | Compile the paper to PDF, don't hand-roll this |
| Code execution | **Python `subprocess` with strict resource/time limits** | Enough isolation for a single-user college-scale sandbox; no Docker/Piston infra to stand up |
| Version control | **Real Git + GitHub** (shell out to system git per project repo) | Never reinvent version control |
| Deployment | **Render** (Flask app), **Supabase** (DB/Auth/Storage) | One deploy target, consistent with your other projects |

**Explicitly excluded** — do not introduce any of these unless a specific
Phase 3+ requirement genuinely can't be met without one, and even then, flag
it and ask first: Next.js, TypeScript, React, React Query, Zustand, Monaco,
Docker/Piston as external services, Redis, Celery, Kubernetes, microservices.

### Why Postgres over SQLite here specifically
The moment teams, roles, permissions, and a knowledge/claim-evidence graph
enter the picture (Phase 1 and Phase 2), you need real relational integrity
and row-level security enforced by the database — not the app layer. That's
the one upgrade worth making from day one; everything else in the stack
stays intentionally minimal.

---

## 2. What "looks human-made" actually means here

This is the part most AI-driven builds get wrong. Follow these rules:

- **Grow the folder structure with the features, not ahead of them.** Phase
  1 should have a small, flat structure. Don't create `algorithm_lab/`,
  `paper_lab/`, `knowledge_graph/` modules in week one because they appear
  in the roadmap — create them in the phase that builds them.
- **Commit like a person working through a plan**, not like a single giant
  generated diff: small, scoped commits, present-tense messages
  (`add paper library table + RLS policy`, not `Implemented Feature #7`),
  and a commit per logical unit of work (schema, then route, then template),
  not one commit per file.
- **No boilerplate comments.** No `# TODO: implement this later` scattered
  everywhere, no file-header comment blocks restating the filename, no
  comments explaining what a self-explanatory line does.
- **Real error handling, not decorative try/except.** If Gemini is down, the
  UI shows "AI assistant unavailable, try again" — never a silently empty
  result styled to look intentional.
- **Don't over-name things.** `research/rag.py`, not
  `research/infrastructure/retrieval/VectorSearchOrchestrator.py`. A
  student building this solo would not build an enterprise Java-style layer
  cake.
- **One README, kept current, not a docs/ folder with ten stale files.**
  If you need design notes for yourself mid-build, put them at the bottom
  of the relevant commit message, not in a permanent file.

Target repo shape after Phase 1 (grow organically from here — do not
pre-create folders below that Phase 1 doesn't need yet):

```
research_lab/
├── app.py
├── database.py              # Supabase client + query helpers
├── requirements.txt
├── .env
├── README.md
├── AGENTS.md                 # this file
│
├── ai/
│   └── research_agent.py     # RAG-grounded Q&A over saved papers
│
├── research/
│   ├── search.py              # arXiv / Semantic Scholar / Crossref
│   ├── papers.py               # save/list papers for a project
│   ├── pdf_reader.py            # PyMuPDF extraction
│   └── rag.py                    # FAISS + Sentence Transformers
│
├── templates/
│   ├── login.html
│   ├── dashboard.html
│   ├── project.html
│   └── papers.html
│
├── static/
│   ├── css/
│   └── js/
│
└── uploads/                    # saved PDFs (mirrored to Supabase Storage)
```

`ai/writing_agent.py`, `ai/coding_agent.py`, `ai/review_agent.py`,
`experiments/`, `paper/`, and the rest of `templates/` get added in the
phases that actually build them — not before.

---

## 3. Working mode

Work the way you would with a careful human collaborator, not a one-shot
generator:

1. **Restate the scope** of whatever slice you're about to build before
   writing code (one paragraph).
2. **One vertical slice at a time** — schema → route → template → test, for
   one feature, fully working end to end, before moving to the next. Never
   half-build five features in parallel.
3. **Flag before adding**: any new dependency, any new Supabase table, any
   new external API call gets called out explicitly before you add it.
4. **State what's real vs stubbed** at the end of each slice: e.g. "Paper
   search hits Semantic Scholar for real; PDF annotation UI is a static
   mock, not wired up yet."
5. **Never fabricate data.** Empty state = empty state (0 papers, 0
   experiments) — never seeded fake numbers in anything that looks like a
   production view. Seed/demo data, if ever needed for a demo, lives behind
   an explicit `APP_ENV=development` flag and is visually marked as demo
   data.
6. **Ask before touching AI-authored user content.** Never silently
   "improve" a paragraph a user wrote in the Paper Lab — AI edits appear
   as a diff/suggestion the human accepts or rejects.

---

## 4. Phase 1 scope — build this first, build it completely

Do not start Phase 2 until every item below is real and working end to end.

**Auth & workspace**
- Supabase email/password + Google OAuth
- Create a Research Project (title, research question, domain, description)
- Team workspace: invite a collaborator by email, roles = Owner / Researcher
  / Viewer, enforced via **Supabase RLS policies** — not just hidden in the
  Flask routes or the templates
- Research dashboard: shows the project's current state (papers saved,
  notes count, last activity) — real counts from Postgres, zero-state when
  empty

**Literature**
- Paper search against real APIs (start with Semantic Scholar — free, no
  key friction) with relevance ranking
- Save a paper to the project's Paper Library (metadata in Postgres, PDF in
  Supabase Storage)
- In-app PDF reader for saved papers (only for legally open-access PDFs —
  surface the open-access link the API provides; never scrape paywalled
  content)
- Basic highlight/annotation on a PDF

**Research AI (scoped, not the whole roadmap)**
- RAG over the papers saved in *this* project only (FAISS index built from
  Sentence Transformer embeddings of the saved PDFs), so "summarize this
  paper" / "what does the literature say about X" is grounded in papers the
  researcher actually added — every AI answer here shows which saved
  paper(s) it drew from
- Every AI-generated claim in this phase carries a visible source link;
  no source, no claim

**Notes & version control**
- Free-text research notes per project, timestamped
- Git integration: each project maps to a real git repo (init on project
  creation); a minimal file browser + commit history view is enough for
  Phase 1 — the full CodeMirror code editor comes in Phase 3

Acceptance bar for "Phase 1 done": a real researcher can create a project,
invite a labmate, search and save five real papers, ask the AI a grounded
question about those papers and get a cited answer, write notes, and see
all of it persist and show correctly to the invited collaborator with the
right permissions. No feature in this list is "done" if it only works for
the happy path — test the empty state, the error state (API down), and the
permission-denied state for each one.

---

## 5. Guardrails to enforce in code, not just in this doc

- Supabase RLS policies on every table that holds team-scoped data — never
  rely on the Flask route or the frontend to hide data the database would
  still return to a direct query.
- Every AI call has a timeout + explicit failure UI — no infinite spinners.
- Every "AI suggests" surface has a visible accept/edit/reject control;
  there is no code path where AI output lands in a document without one.
- Any code execution (Phase 3+) runs via `subprocess` with an enforced CPU
  time limit, memory limit, and no network access — never `eval`/`exec` on
  raw user or AI-generated code in the Flask process itself.
- Log AI provenance (model, prompt version, timestamp, source docs) on
  every AI-generated artifact stored in the DB, so a later "why did it say
  this" question is answerable.

---

## 6. Roadmap after Phase 1 (context only — do not build ahead of it)

Phase 2 — Research Intelligence (knowledge graph, claim-evidence graph,
gap/contradiction detection, hypothesis generation) → Phase 3 — Experiment
Lab (CodeMirror editor, subprocess-sandboxed execution, Algorithm Lab with
pseudocode-to-code linking, experiment/dataset managers, baseline
comparisons, ablations, Matplotlib graphs, Pandas/NumPy/scikit-learn-backed
stats) → Phase 4 — Paper Lab (section-by-section editor with AI assist,
citation/results/figure integration, LaTeX + Pandoc export) → Phase 5 —
Advanced (peer-review agent, publication readiness, research journal,
decision log).

Keep the AI agent roster small and purposeful rather than one agent per
feature — 7–8 is enough: Research Manager, Literature Agent, Evidence
Agent, Gap Agent, Hypothesis Agent, Experiment Agent, Writing Agent, Review
Agent. Everything else (graphs, stats, PDF processing, Git, experiment
execution, file management) is deterministic Python, not an "agent."

Full feature-level breakdown and status tracking lives in
`AI_Research_Lab_Tracker.xlsx` (Phase Roadmap + Full Feature Catalog
sheets) — treat that as the backlog, not this file.

---

## 7. First message to send Antigravity

> Read AGENTS.md fully. Restate the Phase 1 scope back to me in your own
> words, propose the first vertical slice you'll build (Supabase schema →
> Flask route → template), and wait for my go-ahead before writing code.
