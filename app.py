import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from dotenv import load_dotenv

import database as db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "ai-research-lab-dev-secret-key-10928374")

# Decorator to require authenticated user session
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session or not session["user"].get("id"):
            flash("Please sign in to access your research workspace.", "info")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_global_context():
    return {
        "current_user": session.get("user"),
        "is_supabase_live": db.IS_SUPABASE_CONFIGURED,
        "app_env": os.getenv("APP_ENV", "development")
    }

# ==============================================================================
# Authentication Routes
# ==============================================================================

@app.route("/")
def index():
    if "user" in session and session["user"].get("id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session and session["user"].get("id"):
        return redirect(url_for("dashboard"))
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html", mode="login")
        
        result = db.auth_sign_in(email, password)
        if result["success"]:
            session["user"] = result["user"]
            session["access_token"] = result.get("access_token")
            flash(f"Welcome back, {result['user']['full_name']}!", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard"))
        else:
            flash(result["error"], "error")
            
    return render_template("login.html", mode="login")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user" in session and session["user"].get("id"):
        return redirect(url_for("dashboard"))
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        full_name = request.form.get("full_name", "").strip()
        
        if not email or not password:
            flash("Please provide both email and a secure password.", "error")
            return render_template("login.html", mode="signup")
        
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("login.html", mode="signup")
        
        result = db.auth_sign_up(email, password, full_name)
        if result["success"]:
            # Auto sign-in or prompt
            sign_in_res = db.auth_sign_in(email, password)
            if sign_in_res["success"]:
                session["user"] = sign_in_res["user"]
                session["access_token"] = sign_in_res.get("access_token")
                flash("Account created successfully! Welcome to AI Research Lab.", "success")
                return redirect(url_for("dashboard"))
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        else:
            flash(result["error"], "error")
            
    return render_template("login.html", mode="signup")

@app.route("/auth/google")
def auth_google():
    """Initiate Supabase Google OAuth or show status."""
    if db.IS_SUPABASE_CONFIGURED and db.supabase_client:
        try:
            redirect_to = url_for("auth_callback", _external=True)
            res = db.supabase_client.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {"redirect_to": redirect_to}
            })
            if res.url:
                return redirect(res.url)
        except Exception as e:
            flash(f"Google OAuth initialization failed: {e}", "error")
    else:
        flash("Google OAuth requires active Supabase credentials in .env. Use email sign in for local mode.", "info")
    return redirect(url_for("login"))

@app.route("/auth/callback")
def auth_callback():
    flash("Authenticated via OAuth.", "success")
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))

# ==============================================================================
# Dashboard & Projects Workspace Routes
# ==============================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user = session["user"]
    projects = db.get_user_projects(user["id"])
    return render_template("dashboard.html", projects=projects)

@app.route("/projects/new", methods=["POST"])
@login_required
def new_project():
    user = session["user"]
    title = request.form.get("title", "").strip()
    research_question = request.form.get("research_question", "").strip()
    domain = request.form.get("domain", "").strip()
    description = request.form.get("description", "").strip()
    
    if not title:
        flash("Project title is required.", "error")
        return redirect(url_for("dashboard"))
    
    res = db.create_project(title, research_question, domain, description, user["id"])
    if res["success"]:
        flash(f"Research project '{title}' created successfully!", "success")
        return redirect(url_for("project_view", project_id=res["project_id"]))
    else:
        flash(f"Failed to create project: {res.get('error')}", "error")
        return redirect(url_for("dashboard"))

import research.search as academic_search
import research.papers as papers_mgmt
from flask import send_file

import ai.research_agent as research_agent
import ai.knowledge_agent as knowledge_agent
import research.rag as rag
import research.git_tracker as git_tracker

@app.route("/projects/<project_id>")
@login_required
def project_view(project_id):
    user = session["user"]
    project = db.get_project_details(project_id, user["id"])
    if not project:
        flash("Project not found or access denied.", "error")
        return redirect(url_for("dashboard"))
    
    active_tab = request.args.get("tab", "overview")
    search_query = request.args.get("q", "").strip()
    
    saved_papers = []
    search_results = []
    search_error = None
    notes = []
    index_status = {"indexed": False, "total_chunks": 0}
    knowledge_graph = {"nodes": [], "edges": []}
    
    if active_tab in ("literature", "ai", "knowledge"):
        saved_papers = papers_mgmt.get_project_papers(project_id, user["id"])
        
    if active_tab == "literature" and search_query:
        search_res = academic_search.search_academic_papers(search_query)
        if search_res.get("success"):
            search_results = search_res.get("papers", [])
        else:
            search_error = search_res.get("error")
            
    if active_tab == "notes":
        notes = db.get_project_notes(project_id, user["id"])

    if active_tab == "knowledge":
        knowledge_graph = db.get_project_knowledge_graph(project_id, user["id"])
            
    if active_tab == "ai":
        index_path, meta_path = rag.get_project_index_paths(project_id)
        if os.path.exists(index_path) and os.path.exists(meta_path):
            try:
                import json
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    index_status = {"indexed": True, "total_chunks": len(meta)}
            except Exception:
                index_status = {"indexed": True, "total_chunks": 0}

    selected_file_path = request.args.get("file", "").strip()
    file_content = None
    file_tree = []
    commits = []
    
    if active_tab == "git":
        commits = git_tracker.get_commit_history(project_id)
        file_tree = git_tracker.get_project_file_tree(project_id)
        if selected_file_path:
            f_res = git_tracker.get_file_content(project_id, selected_file_path)
            if f_res.get("success"):
                file_content = f_res.get("content")
        elif file_tree:
            # Default to README.md
            readme = next((f for f in file_tree if f["name"] == "README.md"), None)
            if readme:
                selected_file_path = "README.md"
                f_res = git_tracker.get_file_content(project_id, "README.md")
                if f_res.get("success"):
                    file_content = f_res.get("content")

                
    return render_template(
        "project.html", 
        project=project, 
        active_tab=active_tab,
        saved_papers=saved_papers,
        search_query=search_query,
        search_results=search_results,
        search_error=search_error,
        index_status=index_status,
        notes=notes,
        knowledge_graph=knowledge_graph,
        commits=commits,
        file_tree=file_tree,
        selected_file_path=selected_file_path,
        file_content=file_content
    )

@app.route("/projects/<project_id>/git/commit", methods=["POST"])
@login_required
def project_git_commit(project_id):
    user = session["user"]
    file_path = request.form.get("file_path", "").strip()
    content = request.form.get("content", "")
    message = request.form.get("message", "").strip()
    
    if not file_path or not message:
        flash("File path and commit message are required.", "error")
        return redirect(url_for("project_view", project_id=project_id, tab="git"))
        
    res = git_tracker.save_and_commit_file(
        project_id=project_id,
        relative_path=file_path,
        content=content,
        message=message,
        author_name=user.get("full_name", "Lab Researcher"),
        author_email=user.get("email", "researcher@lab.local")
    )
    if res.get("success"):
        flash(f"Git commit created: '{message}'", "success")
    else:
        flash(f"Commit failed: {res.get('output')}", "error")
        
    return redirect(url_for("project_view", project_id=project_id, tab="git", file=file_path))


@app.route("/projects/<project_id>/notes/new", methods=["POST"])
@login_required
def new_note(project_id):
    user = session["user"]
    title = request.form.get("title", "").strip() or "Untitled Research Note"
    content = request.form.get("content", "").strip()
    
    if not content:
        flash("Note content cannot be empty.", "error")
        return redirect(url_for("project_view", project_id=project_id, tab="notes"))
        
    res = db.create_research_note(project_id, title, content, user["id"])
    if res["success"]:
        flash(f"Research note '{title}' created.", "success")
    else:
        flash(f"Could not create note: {res.get('error')}", "error")
        
    return redirect(url_for("project_view", project_id=project_id, tab="notes"))

@app.route("/projects/<project_id>/notes/<note_id>/update", methods=["POST"])
@login_required
def update_note(project_id, note_id):
    user = session["user"]
    title = request.form.get("title", "").strip() or "Untitled Note"
    content = request.form.get("content", "").strip()
    
    res = db.update_research_note(project_id, note_id, title, content, user["id"])
    if res["success"]:
        flash("Note updated.", "success")
    else:
        flash(f"Could not update note: {res.get('error')}", "error")
        
    return redirect(url_for("project_view", project_id=project_id, tab="notes"))

@app.route("/projects/<project_id>/notes/<note_id>/delete", methods=["POST"])
@login_required
def delete_note(project_id, note_id):
    user = session["user"]
    res = db.delete_research_note(project_id, note_id, user["id"])
    if res["success"]:
        flash("Note deleted.", "info")
    else:
        flash(f"Failed to delete note: {res.get('error')}", "error")
        
    return redirect(url_for("project_view", project_id=project_id, tab="notes"))


@app.route("/projects/<project_id>/ai/ask", methods=["POST"])
@login_required
def ai_ask_question(project_id):
    user = session["user"]
    # Check access
    proj = db.get_project_details(project_id, user["id"])
    if not proj:
        return jsonify({"success": False, "error": "Access denied."}), 403
        
    data = request.get_json(silent=True) or request.form
    question = data.get("question", "").strip()
    
    if not question:
        return jsonify({"success": False, "error": "Question cannot be empty."}), 400
        
    res = research_agent.ask_research_agent(project_id, user["id"], question)
    return jsonify(res)

@app.route("/projects/<project_id>/ai/reindex", methods=["POST"])
@login_required
def ai_reindex_project(project_id):
    user = session["user"]
    res = rag.build_project_faiss_index(project_id, user["id"])
    if res.get("success"):
        flash(f"Literature vector index rebuilt ({res.get('total_chunks')} chunks from {res.get('total_papers')} papers).", "success")
    else:
        flash(f"Indexing notice: {res.get('error')}", "info")
    return redirect(url_for("project_view", project_id=project_id, tab="ai"))


@app.route("/projects/<project_id>/literature/search", methods=["GET"])
@login_required
def api_search_papers(project_id):
    user = session["user"]
    # Check access
    proj = db.get_project_details(project_id, user["id"])
    if not proj:
        return jsonify({"success": False, "error": "Access denied."}), 403
    
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"success": True, "papers": []})
    
    res = academic_search.search_academic_papers(query)
    return jsonify(res)

@app.route("/projects/<project_id>/literature/save", methods=["POST"])
@login_required
def save_paper(project_id):
    user = session["user"]
    title = request.form.get("title", "").strip()
    authors_raw = request.form.get("authors", "[]")
    abstract = request.form.get("abstract", "").strip()
    year = request.form.get("year")
    venue = request.form.get("venue", "").strip()
    doi = request.form.get("doi", "").strip() or None
    arxiv_id = request.form.get("arxiv_id", "").strip() or None
    oa_pdf_url = request.form.get("open_access_pdf_url", "").strip() or None
    
    import json
    try:
        authors = json.loads(authors_raw) if isinstance(authors_raw, str) and authors_raw.startswith("[") else [authors_raw]
    except Exception:
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
        
    year_int = int(year) if year and year.isdigit() else None
    
    paper_data = {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "year": year_int,
        "venue": venue,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "open_access_pdf_url": oa_pdf_url
    }
    
    res = papers_mgmt.save_paper_to_project(project_id, paper_data, user["id"])
    if res["success"]:
        flash(f"Paper '{title[:60]}...' saved to project library.", "success")
    else:
        flash(f"Could not save paper: {res.get('error')}", "error")
        
    return redirect(url_for("project_view", project_id=project_id, tab="literature"))

@app.route("/projects/<project_id>/literature/<paper_id>/delete", methods=["POST"])
@login_required
def delete_paper(project_id):
    user = session["user"]
    res = papers_mgmt.delete_project_paper(project_id, paper_id, user["id"])
    if res["success"]:
        flash("Paper removed from library.", "info")
    else:
        flash(f"Failed to remove paper: {res.get('error')}", "error")
    return redirect(url_for("project_view", project_id=project_id, tab="literature"))

import research.pdf_reader as pdf_reader

@app.route("/projects/<project_id>/literature/<paper_id>/reader")
@login_required
def paper_reader(project_id, paper_id):
    user = session["user"]
    proj = db.get_project_details(project_id, user["id"])
    if not proj:
        flash("Access denied.", "error")
        return redirect(url_for("dashboard"))
    
    # Get paper info
    saved_papers = papers_mgmt.get_project_papers(project_id, user["id"])
    target_paper = next((p for p in saved_papers if p["id"] == paper_id), None)
    if not target_paper:
        flash("Paper not found in project library.", "error")
        return redirect(url_for("project_view", project_id=project_id, tab="literature"))
    
    pdf_path = os.path.join(papers_mgmt.UPLOADS_DIR, project_id, f"{paper_id}.pdf")
    pages_data = []
    extraction_error = None
    
    if os.path.exists(pdf_path):
        ext_res = pdf_reader.extract_pdf_pages(pdf_path)
        if ext_res.get("success"):
            pages_data = ext_res.get("pages", [])
        else:
            extraction_error = ext_res.get("error")
    else:
        extraction_error = "PDF has not been downloaded to local cache."
        
    annotations = db.get_paper_annotations(project_id, paper_id, user["id"])
    
    return render_template(
        "pdf_viewer.html",
        project=proj,
        paper=target_paper,
        pages=pages_data,
        annotations=annotations,
        extraction_error=extraction_error,
        has_cached_pdf=os.path.exists(pdf_path)
    )

@app.route("/projects/<project_id>/literature/<paper_id>/pdf")
@login_required
def get_paper_pdf(project_id, paper_id):
    user = session["user"]
    proj = db.get_project_details(project_id, user["id"])
    if not proj:
        flash("Access denied.", "error")
        return redirect(url_for("dashboard"))
    
    pdf_path = os.path.join(papers_mgmt.UPLOADS_DIR, project_id, f"{paper_id}.pdf")
    if os.path.exists(pdf_path):
        return send_file(pdf_path, mimetype="application/pdf")
    
    flash("PDF is not cached locally or open access copy is unavailable.", "info")
    return redirect(url_for("project_view", project_id=project_id, tab="literature"))

@app.route("/projects/<project_id>/literature/<paper_id>/annotations", methods=["POST"])
@login_required
def add_annotation(project_id, paper_id):
    user = session["user"]
    page_number = request.form.get("page_number", 1)
    selected_text = request.form.get("selected_text", "").strip()
    comment = request.form.get("comment", "").strip()
    color = request.form.get("color", "#F59E0B")
    
    if not selected_text:
        flash("Highlighted text cannot be empty.", "error")
        return redirect(url_for("paper_reader", project_id=project_id, paper_id=paper_id))
    
    res = db.add_paper_annotation(project_id, paper_id, user["id"], page_number, selected_text, comment, color)
    if res["success"]:
        flash("Annotation and highlight saved.", "success")
    else:
        flash(f"Could not save annotation: {res.get('error')}", "error")
        
    return redirect(url_for("paper_reader", project_id=project_id, paper_id=paper_id))

@app.route("/projects/<project_id>/literature/<paper_id>/annotations/<annotation_id>/delete", methods=["POST"])
@login_required
def delete_annotation(project_id, paper_id, annotation_id):
    user = session["user"]
    res = db.delete_paper_annotation(project_id, annotation_id, user["id"])
    if res["success"]:
        flash("Highlight removed.", "info")
    else:
        flash(f"Failed to remove highlight: {res.get('error')}", "error")
    return redirect(url_for("paper_reader", project_id=project_id, paper_id=paper_id))


@app.route("/projects/<project_id>/invite", methods=["POST"])
@login_required
def invite_member(project_id):
    user = session["user"]
    email = request.form.get("email", "").strip()
    role = request.form.get("role", "researcher").strip()
    
    if not email:
        flash("Collaborator email is required.", "error")
        return redirect(url_for("project_view", project_id=project_id, tab="team"))
    
    res = db.invite_collaborator(project_id, email, role, user["id"])
    if res["success"]:
        flash(f"Collaborator '{email}' added with '{role.capitalize()}' role.", "success")
    else:
        flash(res["error"], "error")
        
    return redirect(url_for("project_view", project_id=project_id, tab="team"))

# ==============================================================================
# Knowledge Graph Endpoints
# ==============================================================================

@app.route("/projects/<project_id>/knowledge/extract", methods=["POST"])
@login_required
def extract_knowledge(project_id):
    user = session["user"]
    proj = db.get_project_details(project_id, user["id"])
    if not proj:
        return jsonify({"success": False, "error": "Access denied."}), 403
        
    paper_id = request.form.get("paper_id") or (request.get_json(silent=True) or {}).get("paper_id")
    if paper_id:
        paper_id = paper_id.strip() or None

    res = knowledge_agent.extract_project_knowledge_graph(project_id, user["id"], paper_id=paper_id)
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(res)
        
    if res.get("success"):
        flash(f"Extracted {res.get('new_nodes_added', 0)} concepts and {res.get('new_edges_added', 0)} relationships into the Knowledge Graph.", "success")
    else:
        flash(f"Extraction notice: {res.get('error')}", "error")
        
    return redirect(url_for("project_view", project_id=project_id, tab="knowledge"))

@app.route("/projects/<project_id>/knowledge/graph", methods=["GET"])
@login_required
def get_knowledge_graph_api(project_id):
    user = session["user"]
    graph = db.get_project_knowledge_graph(project_id, user["id"])
    return jsonify({"success": True, "graph": graph})

@app.route("/projects/<project_id>/knowledge/nodes/new", methods=["POST"])
@login_required
def add_knowledge_node_manual(project_id):
    user = session["user"]
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "concept").strip()
    description = request.form.get("description", "").strip()
    source_paper_id = request.form.get("source_paper_id", "").strip() or None
    
    if not name:
        flash("Concept name cannot be empty.", "error")
        return redirect(url_for("project_view", project_id=project_id, tab="knowledge"))
        
    res = db.add_or_update_knowledge_node(project_id, name, category, description, source_paper_id)
    if res["success"]:
        flash(f"Concept '{name}' added to Knowledge Graph.", "success")
    else:
        flash(f"Could not add concept: {res.get('error')}", "error")
    return redirect(url_for("project_view", project_id=project_id, tab="knowledge"))

@app.route("/projects/<project_id>/knowledge/nodes/<node_id>/delete", methods=["POST"])
@login_required
def delete_knowledge_node_route(project_id, node_id):
    user = session["user"]
    res = db.delete_knowledge_node(project_id, node_id, user["id"])
    if res["success"]:
        flash("Concept node deleted from graph.", "info")
    else:
        flash(f"Could not delete node: {res.get('error')}", "error")
    return redirect(url_for("project_view", project_id=project_id, tab="knowledge"))

@app.route("/projects/<project_id>/knowledge/edges/new", methods=["POST"])
@login_required
def add_knowledge_edge_manual(project_id):
    user = session["user"]
    source_id = request.form.get("source_node_id", "").strip()
    target_id = request.form.get("target_node_id", "").strip()
    relation_type = request.form.get("relation_type", "relates_to").strip()
    evidence = request.form.get("evidence", "").strip()
    source_paper_id = request.form.get("source_paper_id", "").strip() or None
    
    if not source_id or not target_id:
        flash("Source and target concepts must be selected.", "error")
        return redirect(url_for("project_view", project_id=project_id, tab="knowledge"))
        
    res = db.add_knowledge_edge(project_id, source_id, target_id, relation_type, evidence, source_paper_id)
    if res["success"]:
        flash("Relationship link added to graph.", "success")
    else:
        flash(f"Could not add relationship: {res.get('error')}", "error")
    return redirect(url_for("project_view", project_id=project_id, tab="knowledge"))

@app.route("/projects/<project_id>/knowledge/clear", methods=["POST"])
@login_required
def clear_knowledge_graph_route(project_id):
    user = session["user"]
    res = db.clear_project_knowledge_graph(project_id, user["id"])
    if res["success"]:
        flash("Knowledge Graph reset.", "info")
    else:
        flash(f"Could not reset graph: {res.get('error')}", "error")
    return redirect(url_for("project_view", project_id=project_id, tab="knowledge"))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1")
    app.run(host="0.0.0.0", port=port, debug=debug)

