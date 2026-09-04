import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def ask_research_agent(project_id, user_id, question, top_k=4):
    """
    RAG-grounded Research Agent over project saved papers.
    Strictly cites retrieved passages [Paper Title, p. X].
    """
    from research.rag import search_project_index, build_project_faiss_index, get_project_index_paths
    
    question = question.strip()
    if not question:
        return {"success": False, "error": "Question cannot be empty."}
        
    index_path, meta_path = get_project_index_paths(project_id)
    if not os.path.exists(index_path):
        # Auto-build index on first query
        build_res = build_project_faiss_index(project_id, user_id)
        if not build_res.get("success"):
            return {
                "success": False, 
                "error": f"Could not index project literature: {build_res.get('error')}. Please save papers to your library first."
            }
            
    # Search vector index
    search_res = search_project_index(project_id, question, top_k=top_k)
    if not search_res.get("success"):
        return search_res
        
    chunks = search_res.get("results", [])
    if not chunks:
        return {
            "success": True,
            "answer": "No relevant passages were found in your saved papers for this question.",
            "sources": [],
            "provenance": {"model": "local-rag", "timestamp": now_iso()}
        }
        
    # Format context passages
    context_blocks = []
    sources = []
    for i, c in enumerate(chunks, 1):
        context_blocks.append(f"Passage [{i}] (From '{c['paper_title']}', Page {c['page_number']}):\n{c['text']}")
        sources.append({
            "index": i,
            "paper_id": c["paper_id"],
            "paper_title": c["paper_title"],
            "page_number": c["page_number"],
            "score": round(c["score"], 3),
            "snippet": c["text"][:220] + "..." if len(c["text"]) > 220 else c["text"]
        })
        
    context_text = "\n\n".join(context_blocks)
    
    system_prompt = (
        "You are an AI Research Assistant inside AI Research Lab. "
        "Your task is to answer the researcher's inquiry strictly grounded in the provided project literature passages.\n\n"
        "PHILOSOPHY & GUARDRAILS:\n"
        "1. Every factual statement or claim MUST carry a visible citation citing the source passage or paper title and page number, e.g. [Title, p. X] or [Passage 1].\n"
        "2. If the provided literature does not contain the answer, state explicitly: 'The saved project literature does not contain sufficient evidence to answer this question.'\n"
        "3. NEVER fabricate citations, numbers, or conclusions. Research integrity is paramount."
    )
    
    user_prompt = (
        f"Research Question: {question}\n\n"
        f"Retrieved Literature Passages from Project Library:\n{context_text}\n\n"
        f"Provide a rigorous, cited synthesis:"
    )
    
    # Try Gemini API if key provided
    if GEMINI_API_KEY and not GEMINI_API_KEY.startswith("your-gemini"):
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = model.generate_content(full_prompt)
            
            return {
                "success": True,
                "answer": response.text,
                "sources": sources,
                "provenance": {
                    "model": "gemini-1.5-flash",
                    "sources_count": len(sources),
                    "timestamp": now_iso()
                }
            }
        except Exception as e:
            print(f"[Research AI] Gemini API error ({e}). Falling back to extractive synthesis.")
            
    # Local extractive synthesis fallback
    synthesis_lines = [
        f"**Literature Grounding on:** *\"{question}\"*\n",
        "Based on the saved papers in this project workspace, the following relevant evidence was identified:\n"
    ]
    for s in sources:
        synthesis_lines.append(f"- **[{s['paper_title']}, p. {s['page_number']}]**: \"{s['snippet']}\"\n")
    synthesis_lines.append("\n*(Note: Configure `GEMINI_API_KEY` in `.env` for generative LLM synthesis. Raw citations above reflect direct vector-matched passages.)*")
    
    return {
        "success": True,
        "answer": "\n".join(synthesis_lines),
        "sources": sources,
        "provenance": {
            "model": "extractive-rag-local",
            "sources_count": len(sources),
            "timestamp": now_iso()
        }
    }
