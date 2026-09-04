import os
import uuid
import json
import database as db
import research.papers as papers_mgmt
import ai.knowledge_agent as knowledge_agent
from app import app

def test_knowledge_graph_slice():
    print("=== Testing Phase 2, Slice 1: Knowledge & Concept Extraction Graph ===")
    
    uid = str(uuid.uuid4())[:8]
    email = f"ontologist_{uid}@lab.internal"
    pwd = "password123!"
    name = f"Ontology Researcher {uid}"
    
    # 1. Sign up user & create project
    signup_res = db.auth_sign_up(email, pwd, name)
    assert signup_res["success"], f"Signup failed: {signup_res}"
    user = signup_res["user"]
    user_id = user["id"]
    
    proj_res = db.create_project(
        title="Knowledge Graph Test Workspace",
        research_question="How do attention architectures compare across benchmark datasets?",
        domain="NLP & Machine Learning",
        description="Verifying entity and relationship extraction.",
        user_id=user_id
    )
    assert proj_res["success"], f"Project creation failed: {proj_res}"
    project_id = proj_res["project_id"]
    print(" [x] User and Project created successfully.")
    
    # 2. Check Zero-State
    kg_empty = db.get_project_knowledge_graph(project_id, user_id)
    assert len(kg_empty["nodes"]) == 0, f"Expected 0 nodes, got {len(kg_empty['nodes'])}"
    assert len(kg_empty["edges"]) == 0, f"Expected 0 edges, got {len(kg_empty['edges'])}"
    print(" [x] Verified zero-state: 0 nodes, 0 edges.")
    
    # 3. Save a sample paper
    paper_res = papers_mgmt.save_paper_to_project(project_id, {
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        "abstract": "We propose the Transformer, a model architecture eschewing recurrence and relying entirely on an attention mechanism to draw global dependencies between input and output. On WMT 2014 English-to-German translation task, the Transformer achieves 28.4 BLEU, outperforming existing models including ensembles.",
        "year": 2017,
        "venue": "NeurIPS",
        "arxiv_id": "1706.03762"
    }, user_id)
    assert paper_res["success"], f"Save paper failed: {paper_res}"
    paper_id = paper_res["paper_id"]
    print(" [x] Saved sample paper to project library.")
    
    # 4. Test Manual Node Creation and Edge Creation
    n1_res = db.add_or_update_knowledge_node(
        project_id=project_id,
        name="Transformer",
        category="method",
        description="Sequence model based purely on self-attention.",
        source_paper_id=paper_id
    )
    assert n1_res["success"], f"Add node 1 failed: {n1_res}"
    node1_id = n1_res["node_id"]
    
    n2_res = db.add_or_update_knowledge_node(
        project_id=project_id,
        name="WMT 2014 English-to-German",
        category="dataset",
        description="Standard machine translation evaluation benchmark.",
        source_paper_id=paper_id
    )
    assert n2_res["success"], f"Add node 2 failed: {n2_res}"
    node2_id = n2_res["node_id"]
    
    edge_res = db.add_knowledge_edge(
        project_id=project_id,
        source_node_id=node1_id,
        target_node_id=node2_id,
        relation_type="evaluates_on",
        evidence="On WMT 2014 English-to-German translation task, the Transformer achieves 28.4 BLEU.",
        source_paper_id=paper_id
    )
    assert edge_res["success"], f"Add edge failed: {edge_res}"
    print(" [x] Manual concept nodes and relationship link added.")
    
    # 5. Verify Graph Query
    kg = db.get_project_knowledge_graph(project_id, user_id)
    assert len(kg["nodes"]) >= 2, f"Expected at least 2 nodes, got {len(kg['nodes'])}"
    assert len(kg["edges"]) >= 1, f"Expected at least 1 edge, got {len(kg['edges'])}"
    assert any(n["name"] == "Transformer" for n in kg["nodes"])
    assert any(e["relation_type"] == "evaluates_on" for e in kg["edges"])
    print(" [x] Graph query verified with correct node metadata and edge receipts.")
    
    # 6. Test Automated Extraction Agent
    ext_res = knowledge_agent.extract_project_knowledge_graph(project_id, user_id, paper_id=paper_id)
    assert ext_res["success"], f"Extraction agent failed: {ext_res}"
    print(f" [x] Automated Knowledge Agent ran successfully. Total nodes in graph: {ext_res['nodes_count']}, edges: {ext_res['edges_count']}.")
    
    # 7. Test Flask Web Routes via Test Client
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = user
        sess["access_token"] = signup_res.get("access_token")
        
    # GET project view on knowledge tab
    view_resp = client.get(f"/projects/{project_id}?tab=knowledge")
    assert view_resp.status_code == 200, f"Project knowledge tab returned {view_resp.status_code}"
    assert b"Knowledge &amp; Concept Graph" in view_resp.data or b"Knowledge & Concept Graph" in view_resp.data
    assert b"Transformer" in view_resp.data
    
    # GET JSON API
    api_resp = client.get(f"/projects/{project_id}/knowledge/graph")
    assert api_resp.status_code == 200
    api_data = json.loads(api_resp.data)
    assert api_data["success"] is True
    assert len(api_data["graph"]["nodes"]) >= 2
    print(" [x] Flask routes GET /projects/<id>?tab=knowledge and API /knowledge/graph passed.")
    
    # POST new manual node via form
    post_node = client.post(f"/projects/{project_id}/knowledge/nodes/new", data={
        "name": "BLEU",
        "category": "metric",
        "description": "Bilingual Evaluation Understudy metric for text quality.",
        "source_paper_id": paper_id
    }, follow_redirects=True)
    assert post_node.status_code == 200
    assert b"BLEU" in post_node.data
    print(" [x] POST /projects/<id>/knowledge/nodes/new passed.")
    
    # POST clear knowledge graph
    clear_resp = client.post(f"/projects/{project_id}/knowledge/clear", follow_redirects=True)
    assert clear_resp.status_code == 200
    kg_after_clear = db.get_project_knowledge_graph(project_id, user_id)
    assert len(kg_after_clear["nodes"]) == 0
    assert len(kg_after_clear["edges"]) == 0
    print(" [x] POST /projects/<id>/knowledge/clear passed.")
    
    print("\n>>> ALL PHASE 2 SLICE 1 TESTS PASSED SUCCESSFULLY! <<<\n")

if __name__ == "__main__":
    test_knowledge_graph_slice()
