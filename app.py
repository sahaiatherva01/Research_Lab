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

@app.route("/projects/<project_id>")
@login_required
def project_view(project_id):
    user = session["user"]
    project = db.get_project_details(project_id, user["id"])
    if not project:
        flash("Project not found or access denied.", "error")
        return redirect(url_for("dashboard"))
    
    active_tab = request.args.get("tab", "overview")
    return render_template("project.html", project=project, active_tab=active_tab)

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

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1")
    app.run(host="0.0.0.0", port=port, debug=debug)
