import os
import re
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

import database
import research.papers as papers_mgmt
from research.papers import get_project_papers
from research.pdf_reader import extract_pdf_chunks

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def extract_knowledge_from_text_local(text, paper_title="Literature"):
    """
    High-precision local heuristic ontology extractor when LLM key is unavailable.
    Detects methods, datasets, tasks, metrics, concepts and relationships.
    """
    nodes = []
    edges = []
    
    # Common academic vocabulary filters
    known_methods = ["Transformer", "Attention Mechanism", "BERT", "GPT", "ResNet", "Diffusion Model", "LoRA", "RLHF", "Adam Optimizer", "CNN", "RNN", "LSTM", "Autoencoder", "Graph Neural Network", "Prompt Tuning", "FlashAttention", "Contrastive Learning"]
    known_datasets = ["ImageNet", "SQuAD", "GLUE", "SuperGLUE", "Common Crawl", "CIFAR-10", "CIFAR-100", "MNIST", "WMT", "HumanEval", "MMLU", "GSM8K", "CoNLL-2003"]
    known_tasks = ["Machine Translation", "Question Answering", "Object Detection", "Text Generation", "Sentiment Analysis", "Image Classification", "Code Generation", "Reasoning", "Named Entity Recognition"]
    known_metrics = ["BLEU", "ROUGE", "Accuracy", "F1 Score", "Perplexity", "Exact Match", "Top-1 Accuracy", "Loss", "Latency"]
    known_concepts = ["Self-Attention", "Overfitting", "Zero-Shot Learning", "Few-Shot Learning", "Generalization", "Transfer Learning", "In-Context Learning", "Quantization", "Positional Encoding"]

    found_nodes = {}

    def register_node(name, category, desc):
        norm = name.strip()
        if norm.lower() not in found_nodes:
            found_nodes[norm.lower()] = {
                "name": norm,
                "category": category,
                "description": desc
            }

    # Match predefined entities
    for m in known_methods:
        if re.search(r'\b' + re.escape(m) + r'\b', text, re.IGNORECASE):
            register_node(m, "method", f"Algorithmic method or model architecture referenced in {paper_title}.")
    for d in known_datasets:
        if re.search(r'\b' + re.escape(d) + r'\b', text, re.IGNORECASE):
            register_node(d, "dataset", f"Benchmark or evaluation dataset referenced in {paper_title}.")
    for t in known_tasks:
        if re.search(r'\b' + re.escape(t) + r'\b', text, re.IGNORECASE):
            register_node(t, "task", f"Downstream research task referenced in {paper_title}.")
    for met in known_metrics:
        if re.search(r'\b' + re.escape(met) + r'\b', text, re.IGNORECASE):
            register_node(met, "metric", f"Quantitative evaluation metric referenced in {paper_title}.")
    for c in known_concepts:
        if re.search(r'\b' + re.escape(c) + r'\b', text, re.IGNORECASE):
            register_node(c, "concept", f"Core theoretical concept referenced in {paper_title}.")

    # Dynamic Capitalized Entity Discovery (e.g., "X outperforms Y on Z")
    method_matches = re.findall(r'\b([A-Z][a-zA-Z0-9_\-]+(?:\s+[A-Z][a-zA-Z0-9_\-]+)?)\s+(?:model|architecture|framework|algorithm|network)\b', text)
    for m in method_matches[:8]:
        if len(m) > 3 and m.lower() not in ["the", "this", "our", "proposed", "novel"]:
            register_node(m, "method", f"Proposed or baseline method referenced in {paper_title}.")

    dataset_matches = re.findall(r'\b([A-Z][a-zA-Z0-9_\-]+)\s+(?:dataset|benchmark|corpus)\b', text)
    for d in dataset_matches[:5]:
        if len(d) > 2 and d.lower() not in ["the", "this", "a", "each"]:
            register_node(d, "dataset", f"Experimental dataset referenced in {paper_title}.")

    # Relationship Extraction
    sentences = re.split(r'[.\n]', text)
    node_keys = list(found_nodes.keys())

    for sent in sentences:
        sent_clean = sent.strip()
        if len(sent_clean) < 15:
            continue
        
        # Check pairs of detected entities present in the same sentence
        present = [k for k in node_keys if re.search(r'\b' + re.escape(k) + r'\b', sent_clean, re.IGNORECASE)]
        if len(present) >= 2:
            s_name = found_nodes[present[0]]["name"]
            t_name = found_nodes[present[1]]["name"]
            s_cat = found_nodes[present[0]]["category"]
            t_cat = found_nodes[present[1]]["category"]

            rel = "relates_to"
            if s_cat == "method" and t_cat == "dataset":
                rel = "evaluates_on"
            elif s_cat == "method" and t_cat == "task":
                rel = "applies_to"
            elif s_cat == "method" and t_cat == "metric":
                rel = "measures_with"
            elif s_cat == "method" and t_cat == "method":
                if any(w in sent_clean.lower() for w in ["outperform", "surpass", "better", "exceed", "higher"]):
                    rel = "outperforms"
                elif any(w in sent_clean.lower() for w in ["extend", "improve", "enhance", "build on"]):
                    rel = "improves"
                else:
                    rel = "uses"
            elif s_cat == "method" and t_cat == "concept":
                rel = "uses"

            edges.append({
                "source": s_name,
                "target": t_name,
                "relation": rel,
                "evidence": sent_clean[:280]
            })

    return list(found_nodes.values()), edges[:25]


def extract_knowledge_with_gemini(text, paper_title="Literature"):
    """
    Extract structured concept nodes and relationships using Gemini LLM.
    """
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = f"""
You are an expert Research Ontologist & Knowledge Graph Agent in AI Research Lab.
Extract structured research entities and directed relationships from the research paper text below.

PAPER TITLE: {paper_title}

PAPER TEXT:
{text[:12000]}

OUTPUT FORMAT:
Respond ONLY with a valid, clean JSON object (no markdown quotes, no explanation):
{{
  "nodes": [
    {{
      "name": "Transformer",
      "category": "method", // one of: "method", "dataset", "task", "metric", "concept"
      "description": "Sequence transduction model based entirely on attention mechanisms."
    }}
  ],
  "edges": [
    {{
      "source": "Transformer",
      "target": "WMT 2014 English-to-German",
      "relation": "evaluates_on", // one of: "uses", "evaluates_on", "improves", "outperforms", "contradicts", "applies_to"
      "evidence": "On the WMT 2014 English-to-German translation task, the big transformer model achieves 28.4 BLEU."
    }}
  ]
}}
"""
    response = model.generate_content(prompt)
    raw_text = response.text.strip()
    # Clean json formatting
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
        
    data = json.loads(raw_text.strip())
    return data.get("nodes", []), data.get("edges", [])


def extract_project_knowledge_graph(project_id, user_id, paper_id=None):
    """
    Extract and populate knowledge graph for a project's saved literature.
    Can run for all saved papers or a specific target paper.
    """
    papers = get_project_papers(project_id, user_id)
    if not papers:
        return {"success": False, "error": "No saved papers found in this project workspace."}

    target_papers = [p for p in papers if p["id"] == paper_id] if paper_id else papers
    if not target_papers:
        return {"success": False, "error": "Target paper not found in project library."}

    total_nodes_added = 0
    total_edges_added = 0
    errors = []

    for paper in target_papers:
        p_id = paper["id"]
        title = paper.get("title", "Literature")
        abstract = paper.get("abstract", "") or ""

        # Collect text from PDF chunks or abstract
        pdf_path = os.path.join(papers_mgmt.UPLOADS_DIR, project_id, f"{p_id}.pdf")
        pdf_chunks_res = extract_pdf_chunks(pdf_path) if os.path.exists(pdf_path) else {}
        pdf_chunks = pdf_chunks_res.get("chunks", []) if pdf_chunks_res.get("success") else []
        
        combined_text = f"Title: {title}\n\nAbstract: {abstract}\n\n"
        if pdf_chunks:
            # Take representative chunk text
            chunk_texts = [c.get("text", "") for c in pdf_chunks[:12]]
            combined_text += "\n\n".join(chunk_texts)
        else:
            combined_text += abstract

        if len(combined_text.strip()) < 50:
            continue

        raw_nodes = []
        raw_edges = []

        # Try Gemini if API key is valid
        if GEMINI_API_KEY and not GEMINI_API_KEY.startswith("your-gemini"):
            try:
                raw_nodes, raw_edges = extract_knowledge_with_gemini(combined_text, title)
            except Exception as e:
                print(f"[KnowledgeAgent] Gemini error: {e}. Falling back to local extractor.")
                raw_nodes, raw_edges = extract_knowledge_from_text_local(combined_text, title)
        else:
            raw_nodes, raw_edges = extract_knowledge_from_text_local(combined_text, title)

        # Store Nodes
        node_id_map = {} # name.lower() -> node_id
        for n in raw_nodes:
            n_name = n.get("name", "").strip()
            n_cat = n.get("category", "concept")
            n_desc = n.get("description", "")
            if not n_name:
                continue
            
            res = database.add_or_update_knowledge_node(
                project_id=project_id,
                name=n_name,
                category=n_cat,
                description=n_desc,
                source_paper_id=p_id
            )
            if res.get("success"):
                node_id_map[n_name.lower()] = res.get("node_id")
                if res.get("is_new"):
                    total_nodes_added += 1

        # Store Edges
        for e in raw_edges:
            s_name = e.get("source", "").strip().lower()
            t_name = e.get("target", "").strip().lower()
            rel = e.get("relation", "relates_to").strip().lower()
            evidence = e.get("evidence", "")

            s_id = node_id_map.get(s_name)
            t_id = node_id_map.get(t_name)

            if s_id and t_id and s_id != t_id:
                edge_res = database.add_knowledge_edge(
                    project_id=project_id,
                    source_node_id=s_id,
                    target_node_id=t_id,
                    relation_type=rel,
                    evidence=evidence,
                    source_paper_id=p_id
                )
                if edge_res.get("success"):
                    total_edges_added += 1

    graph_data = database.get_project_knowledge_graph(project_id, user_id)

    return {
        "success": True,
        "nodes_count": len(graph_data.get("nodes", [])),
        "edges_count": len(graph_data.get("edges", [])),
        "new_nodes_added": total_nodes_added,
        "new_edges_added": total_edges_added,
        "graph": graph_data
    }
