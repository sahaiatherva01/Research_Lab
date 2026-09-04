import os
import json
import numpy as np

_model = None

def get_embedding_model():
    """Lazy-load the SentenceTransformer embedding model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception as e:
            print(f"[RAG] Warning: sentence_transformers could not be loaded ({e}).")
            return None
    return _model

def get_project_index_paths(project_id):
    from research.papers import UPLOADS_DIR
    proj_dir = os.path.join(UPLOADS_DIR, project_id)
    os.makedirs(proj_dir, exist_ok=True)
    index_path = os.path.join(proj_dir, "index.faiss")
    meta_path = os.path.join(proj_dir, "metadata.json")
    return index_path, meta_path

def build_project_faiss_index(project_id, user_id):
    """
    Build a local FAISS index from all saved papers in this project.
    Extracts text chunks from PDFs and indexes them with metadata.
    """
    import faiss
    from research.papers import get_project_papers, UPLOADS_DIR
    from research.pdf_reader import extract_pdf_chunks
    
    papers = get_project_papers(project_id, user_id)
    if not papers:
        return {"success": False, "error": "No saved papers found in this project to index."}
        
    model = get_embedding_model()
    if model is None:
        return {"success": False, "error": "Sentence Transformer embedding model unavailable."}
        
    all_chunks = []
    
    for paper in papers:
        paper_id = paper["id"]
        paper_title = paper.get("title", "Untitled Paper")
        pdf_path = os.path.join(UPLOADS_DIR, project_id, f"{paper_id}.pdf")
        
        if os.path.exists(pdf_path):
            chunk_res = extract_pdf_chunks(pdf_path, chunk_size=350, overlap=40)
            if chunk_res.get("success") and chunk_res.get("chunks"):
                for c in chunk_res["chunks"]:
                    all_chunks.append({
                        "paper_id": paper_id,
                        "paper_title": paper_title,
                        "authors": paper.get("authors", []),
                        "page_number": c["page_number"],
                        "text": c["text"]
                    })
        else:
            # If PDF not cached locally, index abstract
            abstract = paper.get("abstract", "").strip()
            if abstract and abstract != "No abstract available.":
                all_chunks.append({
                    "paper_id": paper_id,
                    "paper_title": paper_title,
                    "authors": paper.get("authors", []),
                    "page_number": 1,
                    "text": f"Abstract: {abstract}"
                })
                
    if not all_chunks:
        return {"success": False, "error": "No extractable text found in saved papers."}
        
    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    
    # Normalize for cosine similarity
    faiss.normalize_L2(embeddings)
    
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    
    index_path, meta_path = get_project_index_paths(project_id)
    faiss.write_index(index, index_path)
    
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
        
    return {
        "success": True,
        "total_chunks": len(all_chunks),
        "total_papers": len(papers),
        "index_path": index_path
    }

def search_project_index(project_id, query, top_k=4):
    """Retrieve top-k relevant chunks from the project's FAISS index."""
    import faiss
    
    index_path, meta_path = get_project_index_paths(project_id)
    if not os.path.exists(index_path) or not os.path.exists(meta_path):
        return {"success": False, "error": "Project index not built yet. Click 'Re-Index Literature' first."}
        
    model = get_embedding_model()
    if model is None:
        return {"success": False, "error": "Embedding model unavailable."}
        
    try:
        index = faiss.read_index(index_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            
        q_emb = model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(q_emb)
        
        distances, indices = index.search(q_emb, min(top_k, len(metadata)))
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0 and idx < len(metadata):
                chunk = metadata[idx]
                results.append({
                    "score": float(dist),
                    "paper_id": chunk["paper_id"],
                    "paper_title": chunk["paper_title"],
                    "page_number": chunk["page_number"],
                    "text": chunk["text"],
                    "authors": chunk.get("authors", [])
                })
                
        return {"success": True, "results": results}
    except Exception as e:
        return {"success": False, "error": f"FAISS search failed: {str(e)}"}
