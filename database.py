import os
import sqlite3
import uuid
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Determine if Supabase is properly configured
IS_SUPABASE_CONFIGURED = bool(
    SUPABASE_URL and 
    SUPABASE_ANON_KEY and 
    not SUPABASE_URL.startswith("https://your-project") and
    not SUPABASE_ANON_KEY.startswith("your-supabase")
)

supabase_client = None
if IS_SUPABASE_CONFIGURED:
    try:
        from supabase import create_client, Client
        supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY)
        print("[AI Research Lab] Connected to live Supabase PostgreSQL & Auth.")
    except Exception as e:
        print(f"[AI Research Lab] Warning: Failed to initialize Supabase client ({e}). Falling back to local storage.")
        IS_SUPABASE_CONFIGURED = False
else:
    print("[AI Research Lab] Note: Live Supabase credentials not set. Running in Local Storage Mode.")

# ==============================================================================
# Local SQLite Storage Fallback (Implements exact Supabase Schema & Constraints)
# ==============================================================================
LOCAL_DB_PATH = os.path.join(os.path.dirname(__file__), "local_dev.db")

def _init_local_db():
    conn = sqlite3.connect(LOCAL_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        full_name TEXT,
        avatar_url TEXT,
        password_hash TEXT,
        created_at TEXT NOT NULL
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        research_question TEXT,
        domain TEXT,
        description TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (created_by) REFERENCES profiles(id) ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_members (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('owner', 'researcher', 'viewer')),
        joined_at TEXT NOT NULL,
        UNIQUE(project_id, user_id),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS papers (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        authors TEXT DEFAULT '[]',
        abstract TEXT,
        year INTEGER,
        venue TEXT,
        doi TEXT,
        arxiv_id TEXT,
        open_access_pdf_url TEXT,
        storage_path TEXT,
        added_by TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (added_by) REFERENCES profiles(id) ON DELETE SET NULL
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS research_notes (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_by TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (created_by) REFERENCES profiles(id) ON DELETE SET NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS paper_annotations (
        id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        selected_text TEXT NOT NULL,
        comment TEXT,
        color TEXT DEFAULT '#F59E0B',
        created_at TEXT NOT NULL,
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_nodes (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL CHECK (category IN ('method', 'dataset', 'task', 'metric', 'concept')),
        description TEXT,
        source_paper_ids TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        UNIQUE(project_id, name),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_edges (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        source_node_id TEXT NOT NULL,
        target_node_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        evidence TEXT,
        source_paper_id TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(project_id, source_node_id, target_node_id, relation_type),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (source_node_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
        FOREIGN KEY (target_node_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
        FOREIGN KEY (source_paper_id) REFERENCES papers(id) ON DELETE SET NULL
    );
    """)
    
    conn.commit()
    conn.close()




_init_local_db()

# ==============================================================================
# Unified Database & Auth Helper APIs
# ==============================================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# --- Authentication Helpers ---

def auth_sign_up(email, password, full_name=""):
    """Register a new user."""
    email = email.strip().lower()
    full_name = full_name.strip() or email.split("@")[0]
    
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            res = supabase_client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {"full_name": full_name}
                }
            })
            if res.user:
                return {"success": True, "user": {"id": res.user.id, "email": res.user.email, "full_name": full_name}}
            return {"success": False, "error": "Signup failed. Check verification email settings."}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        # Local development auth
        import hashlib
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        user_id = str(uuid.uuid4())
        created_at = now_iso()
        
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO profiles (id, email, full_name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, email, full_name, pwd_hash, created_at)
            )
            conn.commit()
            return {"success": True, "user": {"id": user_id, "email": email, "full_name": full_name}}
        except sqlite3.IntegrityError:
            return {"success": False, "error": "An account with this email already exists."}
        finally:
            conn.close()

def auth_sign_in(email, password):
    """Authenticate an existing user."""
    email = email.strip().lower()
    
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            res = supabase_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            if res.user and res.session:
                # Fetch profile info
                prof_res = supabase_client.table("profiles").select("*").eq("id", res.user.id).execute()
                profile = prof_res.data[0] if prof_res.data else {}
                full_name = profile.get("full_name") or email.split("@")[0]
                return {
                    "success": True, 
                    "user": {"id": res.user.id, "email": res.user.email, "full_name": full_name},
                    "access_token": res.session.access_token
                }
            return {"success": False, "error": "Invalid email or password."}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        # Local development auth
        import hashlib
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, full_name, password_hash FROM profiles WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[3] == pwd_hash:
            return {
                "success": True,
                "user": {"id": row[0], "email": row[1], "full_name": row[2]},
                "access_token": f"local_token_{row[0]}"
            }
        return {"success": False, "error": "Invalid email or password."}

def get_profile(user_id):
    """Get profile by user id."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            res = supabase_client.table("profiles").select("*").eq("id", user_id).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, full_name, avatar_url, created_at FROM profiles WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "email": row[1], "full_name": row[2], "avatar_url": row[3], "created_at": row[4]}
        return None

# --- Projects & Workspaces Helpers ---

def get_user_projects(user_id):
    """Retrieve all projects a user belongs to, including paper/note counts and their role."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            # Query project_members joined with projects
            members_res = supabase_client.table("project_members").select("role, project_id, projects(*)").eq("user_id", user_id).execute()
            projects = []
            for item in members_res.data:
                proj = item.get("projects")
                if proj:
                    pid = proj["id"]
                    # Get real counts
                    p_res = supabase_client.table("papers").select("id", count="exact").eq("project_id", pid).execute()
                    n_res = supabase_client.table("research_notes").select("id", count="exact").eq("project_id", pid).execute()
                    m_res = supabase_client.table("project_members").select("id", count="exact").eq("project_id", pid).execute()
                    
                    proj["role"] = item["role"]
                    proj["papers_count"] = p_res.count or 0
                    proj["notes_count"] = n_res.count or 0
                    proj["members_count"] = m_res.count or 1
                    projects.append(proj)
            return sorted(projects, key=lambda x: x.get("updated_at", ""), reverse=True)
        except Exception as e:
            print(f"Error fetching projects: {e}")
            return []
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        query = """
        SELECT 
            p.id, p.title, p.research_question, p.domain, p.description, 
            p.created_by, p.created_at, p.updated_at, pm.role,
            (SELECT COUNT(*) FROM papers WHERE project_id = p.id) as papers_count,
            (SELECT COUNT(*) FROM research_notes WHERE project_id = p.id) as notes_count,
            (SELECT COUNT(*) FROM project_members WHERE project_id = p.id) as members_count
        FROM projects p
        JOIN project_members pm ON p.id = pm.project_id
        WHERE pm.user_id = ?
        ORDER BY p.updated_at DESC
        """
        cursor.execute(query, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        projects = []
        for r in rows:
            projects.append({
                "id": r[0],
                "title": r[1],
                "research_question": r[2],
                "domain": r[3],
                "description": r[4],
                "created_by": r[5],
                "created_at": r[6],
                "updated_at": r[7],
                "role": r[8],
                "papers_count": r[9],
                "notes_count": r[10],
                "members_count": r[11]
            })
        return projects

def create_project(title, research_question, domain, description, user_id):
    """Create a new project and add the creator as owner."""
    project_id = str(uuid.uuid4())
    ts = now_iso()
    
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            # 1. Insert Project
            proj_data = {
                "id": project_id,
                "title": title.strip(),
                "research_question": research_question.strip(),
                "domain": domain.strip(),
                "description": description.strip(),
                "created_by": user_id,
                "created_at": ts,
                "updated_at": ts
            }
            supabase_client.table("projects").insert(proj_data).execute()
            
            # 2. Insert Membership (Owner)
            member_data = {
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "user_id": user_id,
                "role": "owner",
                "joined_at": ts
            }
            supabase_client.table("project_members").insert(member_data).execute()
            import research.git_tracker as git_tracker
            git_tracker.init_project_repo(project_id, title=title, research_question=research_question, description=description)
            return {"success": True, "project_id": project_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO projects (id, title, research_question, domain, description, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, title.strip(), research_question.strip(), domain.strip(), description.strip(), user_id, ts, ts)
            )
            member_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO project_members (id, project_id, user_id, role, joined_at) VALUES (?, ?, ?, ?, ?)",
                (member_id, project_id, user_id, "owner", ts)
            )
            conn.commit()
            import research.git_tracker as git_tracker
            git_tracker.init_project_repo(project_id, title=title, research_question=research_question, description=description)
            return {"success": True, "project_id": project_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

def get_project_details(project_id, user_id):
    """Retrieve detailed project information, validating user membership and role."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            # Check membership & role
            mem_res = supabase_client.table("project_members").select("role").eq("project_id", project_id).eq("user_id", user_id).execute()
            if not mem_res.data:
                return None  # Forbidden / Not found
            
            user_role = mem_res.data[0]["role"]
            
            # Fetch Project
            proj_res = supabase_client.table("projects").select("*").eq("id", project_id).execute()
            if not proj_res.data:
                return None
            project = proj_res.data[0]
            project["user_role"] = user_role
            
            # Fetch Members
            members_res = supabase_client.table("project_members").select("role, joined_at, profiles(id, email, full_name, avatar_url)").eq("project_id", project_id).execute()
            members = []
            for m in members_res.data:
                prof = m.get("profiles") or {}
                members.append({
                    "user_id": prof.get("id"),
                    "email": prof.get("email"),
                    "full_name": prof.get("full_name") or prof.get("email", "").split("@")[0],
                    "avatar_url": prof.get("avatar_url"),
                    "role": m["role"],
                    "joined_at": m["joined_at"]
                })
            project["members"] = members
            
            # Fetch real counts
            p_res = supabase_client.table("papers").select("id", count="exact").eq("project_id", project_id).execute()
            n_res = supabase_client.table("research_notes").select("id", count="exact").eq("project_id", project_id).execute()
            project["papers_count"] = p_res.count or 0
            project["notes_count"] = n_res.count or 0
            
            return project
        except Exception as e:
            print(f"Error getting project details: {e}")
            return None
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        
        # Check membership
        cursor.execute("SELECT role FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id))
        mem_row = cursor.fetchone()
        if not mem_row:
            conn.close()
            return None
        
        user_role = mem_row[0]
        
        cursor.execute("SELECT id, title, research_question, domain, description, created_by, created_at, updated_at FROM projects WHERE id = ?", (project_id,))
        proj_row = cursor.fetchone()
        if not proj_row:
            conn.close()
            return None
        
        project = {
            "id": proj_row[0],
            "title": proj_row[1],
            "research_question": proj_row[2],
            "domain": proj_row[3],
            "description": proj_row[4],
            "created_by": proj_row[5],
            "created_at": proj_row[6],
            "updated_at": proj_row[7],
            "user_role": user_role
        }
        
        # Members list
        cursor.execute("""
            SELECT pm.user_id, p.email, p.full_name, p.avatar_url, pm.role, pm.joined_at
            FROM project_members pm
            JOIN profiles p ON pm.user_id = p.id
            WHERE pm.project_id = ?
            ORDER BY pm.joined_at ASC
        """, (project_id,))
        members = []
        for mr in cursor.fetchall():
            members.append({
                "user_id": mr[0],
                "email": mr[1],
                "full_name": mr[2] or mr[1].split("@")[0],
                "avatar_url": mr[3],
                "role": mr[4],
                "joined_at": mr[5]
            })
        project["members"] = members
        
        # Counts
        cursor.execute("SELECT COUNT(*) FROM papers WHERE project_id = ?", (project_id,))
        project["papers_count"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM research_notes WHERE project_id = ?", (project_id,))
        project["notes_count"] = cursor.fetchone()[0]
        
        conn.close()
        return project

def invite_collaborator(project_id, email, role, inviter_user_id):
    """Invite/Add a collaborator to a project. Enforces that only owners can invite."""
    email = email.strip().lower()
    if role not in ('owner', 'researcher', 'viewer'):
        return {"success": False, "error": "Invalid role specified."}
    
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            # Check inviter is owner
            inv_res = supabase_client.table("project_members").select("role").eq("project_id", project_id).eq("user_id", inviter_user_id).execute()
            if not inv_res.data or inv_res.data[0]["role"] != "owner":
                return {"success": False, "error": "Only project owners can invite collaborators."}
            
            # Find profile by email
            prof_res = supabase_client.table("profiles").select("id").eq("email", email).execute()
            if not prof_res.data:
                return {"success": False, "error": f"User '{email}' not found. Ask them to register first."}
            
            target_user_id = prof_res.data[0]["id"]
            
            # Add to project_members
            supabase_client.table("project_members").insert({
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "user_id": target_user_id,
                "role": role,
                "joined_at": now_iso()
            }).execute()
            return {"success": True}
        except Exception as e:
            if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
                return {"success": False, "error": "User is already a member of this project."}
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        try:
            # Check inviter role
            cursor.execute("SELECT role FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, inviter_user_id))
            inv_row = cursor.fetchone()
            if not inv_row or inv_row[0] != "owner":
                return {"success": False, "error": "Only project owners can invite collaborators."}
            
            # Find user
            cursor.execute("SELECT id FROM profiles WHERE email = ?", (email,))
            user_row = cursor.fetchone()
            if not user_row:
                return {"success": False, "error": f"User '{email}' not registered yet. Please have them sign up first."}
            
            target_user_id = user_row[0]
            member_id = str(uuid.uuid4())
            ts = now_iso()
            cursor.execute(
                "INSERT INTO project_members (id, project_id, user_id, role, joined_at) VALUES (?, ?, ?, ?, ?)",
                (member_id, project_id, target_user_id, role, ts)
            )
            conn.commit()
            return {"success": True}
        except sqlite3.IntegrityError:
            return {"success": False, "error": "User is already a collaborator in this project."}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

# --- Paper Annotations Helpers ---

def add_paper_annotation(project_id, paper_id, user_id, page_number, selected_text, comment="", color="#F59E0B"):
    """Add a highlight annotation to a saved paper."""
    annotation_id = str(uuid.uuid4())
    ts = now_iso()
    
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            record = {
                "id": annotation_id,
                "paper_id": paper_id,
                "project_id": project_id,
                "user_id": user_id,
                "page_number": int(page_number),
                "selected_text": selected_text.strip(),
                "comment": comment.strip() if comment else "",
                "color": color,
                "created_at": ts
            }
            supabase_client.table("paper_annotations").insert(record).execute()
            return {"success": True, "annotation_id": annotation_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO paper_annotations (id, paper_id, project_id, user_id, page_number, selected_text, comment, color, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (annotation_id, paper_id, project_id, user_id, int(page_number), selected_text.strip(), comment.strip() if comment else "", color, ts))
            conn.commit()
            return {"success": True, "annotation_id": annotation_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

def get_paper_annotations(project_id, paper_id, user_id):
    """Fetch all highlights and annotations for a specific paper."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            res = supabase_client.table("paper_annotations").select("*, profiles(full_name, email)").eq("paper_id", paper_id).eq("project_id", project_id).order("page_number", desc=False).order("created_at", desc=False).execute()
            annotations = []
            for item in res.data:
                prof = item.get("profiles") or {}
                item["user_name"] = prof.get("full_name") or prof.get("email", "Lab Member")
                annotations.append(item)
            return annotations
        except Exception as e:
            print(f"Error getting annotations: {e}")
            return []
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT a.id, a.paper_id, a.project_id, a.user_id, a.page_number, a.selected_text, a.comment, a.color, a.created_at,
                   p.full_name, p.email
            FROM paper_annotations a
            LEFT JOIN profiles p ON a.user_id = p.id
            WHERE a.paper_id = ? AND a.project_id = ?
            ORDER BY a.page_number ASC, a.created_at ASC
        """, (paper_id, project_id))
        rows = c.fetchall()
        conn.close()
        
        annotations = []
        for r in rows:
            annotations.append({
                "id": r[0],
                "paper_id": r[1],
                "project_id": r[2],
                "user_id": r[3],
                "page_number": r[4],
                "selected_text": r[5],
                "comment": r[6],
                "color": r[7],
                "created_at": r[8],
                "user_name": r[9] or (r[10].split("@")[0] if r[10] else "Lab Member")
            })
        return annotations

def delete_paper_annotation(project_id, annotation_id, user_id):
    """Delete a highlight/annotation."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            supabase_client.table("paper_annotations").delete().eq("id", annotation_id).eq("project_id", project_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("DELETE FROM paper_annotations WHERE id = ? AND project_id = ?", (annotation_id, project_id))
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

# --- Research Notes Helpers ---

def create_research_note(project_id, title, content, user_id):
    """Create a timestamped research note."""
    note_id = str(uuid.uuid4())
    ts = now_iso()
    title = title.strip() or "Untitled Note"
    content = content.strip()
    
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            record = {
                "id": note_id,
                "project_id": project_id,
                "title": title,
                "content": content,
                "created_by": user_id,
                "created_at": ts,
                "updated_at": ts
            }
            supabase_client.table("research_notes").insert(record).execute()
            supabase_client.table("projects").update({"updated_at": ts}).eq("id", project_id).execute()
            return {"success": True, "note_id": note_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO research_notes (id, project_id, title, content, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (note_id, project_id, title, content, user_id, ts, ts))
            c.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, project_id))
            conn.commit()
            return {"success": True, "note_id": note_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

def get_project_notes(project_id, user_id):
    """Fetch all research notes for a project."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            # Check membership
            mem_res = supabase_client.table("project_members").select("role").eq("project_id", project_id).eq("user_id", user_id).execute()
            if not mem_res.data:
                return []
                
            res = supabase_client.table("research_notes").select("*, profiles(full_name, email)").eq("project_id", project_id).order("updated_at", desc=True).execute()
            notes = []
            for n in res.data:
                prof = n.get("profiles") or {}
                n["author_name"] = prof.get("full_name") or prof.get("email", "Researcher")
                notes.append(n)
            return notes
        except Exception as e:
            print(f"Error getting notes: {e}")
            return []
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT role FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id))
        if not c.fetchone():
            conn.close()
            return []
            
        c.execute("""
            SELECT n.id, n.project_id, n.title, n.content, n.created_by, n.created_at, n.updated_at,
                   p.full_name, p.email
            FROM research_notes n
            LEFT JOIN profiles p ON n.created_by = p.id
            WHERE n.project_id = ?
            ORDER BY n.updated_at DESC
        """, (project_id,))
        rows = c.fetchall()
        conn.close()
        
        notes = []
        for r in rows:
            notes.append({
                "id": r[0],
                "project_id": r[1],
                "title": r[2],
                "content": r[3],
                "created_by": r[4],
                "created_at": r[5],
                "updated_at": r[6],
                "author_name": r[7] or (r[8].split("@")[0] if r[8] else "Researcher")
            })
        return notes

def update_research_note(project_id, note_id, title, content, user_id):
    """Update an existing research note."""
    ts = now_iso()
    title = title.strip() or "Untitled Note"
    content = content.strip()
    
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            supabase_client.table("research_notes").update({
                "title": title,
                "content": content,
                "updated_at": ts
            }).eq("id", note_id).eq("project_id", project_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("""
                UPDATE research_notes 
                SET title = ?, content = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
            """, (title, content, ts, note_id, project_id))
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

def delete_research_note(project_id, note_id, user_id):
    """Delete a research note."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            supabase_client.table("research_notes").delete().eq("id", note_id).eq("project_id", project_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("DELETE FROM research_notes WHERE id = ? AND project_id = ?", (note_id, project_id))
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

# --- Knowledge Graph Helpers ---

def add_or_update_knowledge_node(project_id, name, category, description="", source_paper_id=None):
    """Add or update an extracted knowledge node."""
    name = name.strip()
    category = category.lower().strip()
    if category not in ('method', 'dataset', 'task', 'metric', 'concept'):
        category = 'concept'
        
    node_id = str(uuid.uuid4())
    ts = now_iso()
    source_papers = [source_paper_id] if source_paper_id else []
    
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            # Check existing node with same project_id and name
            existing = supabase_client.table("knowledge_nodes").select("*").eq("project_id", project_id).ilike("name", name).execute()
            if existing.data:
                node = existing.data[0]
                existing_papers = json.loads(node.get("source_paper_ids") or "[]") if isinstance(node.get("source_paper_ids"), str) else (node.get("source_paper_ids") or [])
                if source_paper_id and source_paper_id not in existing_papers:
                    existing_papers.append(source_paper_id)
                
                updated_desc = description.strip() if description.strip() else node.get("description", "")
                supabase_client.table("knowledge_nodes").update({
                    "description": updated_desc,
                    "source_paper_ids": json.dumps(existing_papers)
                }).eq("id", node["id"]).execute()
                return {"success": True, "node_id": node["id"], "is_new": False}
            else:
                supabase_client.table("knowledge_nodes").insert({
                    "id": node_id,
                    "project_id": project_id,
                    "name": name,
                    "category": category,
                    "description": description.strip(),
                    "source_paper_ids": json.dumps(source_papers),
                    "created_at": ts
                }).execute()
                return {"success": True, "node_id": node_id, "is_new": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("SELECT id, description, source_paper_ids FROM knowledge_nodes WHERE project_id = ? AND LOWER(name) = ?", (project_id, name.lower()))
            row = c.fetchone()
            if row:
                nid, curr_desc, curr_papers_raw = row
                try:
                    papers_list = json.loads(curr_papers_raw) if curr_papers_raw else []
                except Exception:
                    papers_list = []
                if source_paper_id and source_paper_id not in papers_list:
                    papers_list.append(source_paper_id)
                new_desc = description.strip() if description.strip() else (curr_desc or "")
                c.execute("UPDATE knowledge_nodes SET description = ?, source_paper_ids = ? WHERE id = ?", (new_desc, json.dumps(papers_list), nid))
                conn.commit()
                return {"success": True, "node_id": nid, "is_new": False}
            else:
                c.execute("""
                    INSERT INTO knowledge_nodes (id, project_id, name, category, description, source_paper_ids, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (node_id, project_id, name, category, description.strip(), json.dumps(source_papers), ts))
                conn.commit()
                return {"success": True, "node_id": node_id, "is_new": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

def add_knowledge_edge(project_id, source_node_id, target_node_id, relation_type, evidence="", source_paper_id=None):
    """Add or update a directed relationship edge between two concepts."""
    if source_node_id == target_node_id:
        return {"success": False, "error": "Self-loops are not permitted."}
    relation_type = relation_type.lower().strip()
    edge_id = str(uuid.uuid4())
    ts = now_iso()
    
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            supabase_client.table("knowledge_edges").upsert({
                "id": edge_id,
                "project_id": project_id,
                "source_node_id": source_node_id,
                "target_node_id": target_node_id,
                "relation_type": relation_type,
                "evidence": evidence.strip(),
                "source_paper_id": source_paper_id,
                "created_at": ts
            }, on_conflict="project_id, source_node_id, target_node_id, relation_type").execute()
            return {"success": True, "edge_id": edge_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO knowledge_edges (id, project_id, source_node_id, target_node_id, relation_type, evidence, source_paper_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, source_node_id, target_node_id, relation_type) 
                DO UPDATE SET evidence = excluded.evidence, source_paper_id = excluded.source_paper_id
            """, (edge_id, project_id, source_node_id, target_node_id, relation_type, evidence.strip(), source_paper_id, ts))
            conn.commit()
            return {"success": True, "edge_id": edge_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

def get_project_knowledge_graph(project_id, user_id):
    """Fetch complete knowledge graph (nodes + edges) for a project."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            mem_res = supabase_client.table("project_members").select("role").eq("project_id", project_id).eq("user_id", user_id).execute()
            if not mem_res.data:
                return {"nodes": [], "edges": []}
            
            nodes_res = supabase_client.table("knowledge_nodes").select("*").eq("project_id", project_id).execute()
            edges_res = supabase_client.table("knowledge_edges").select("*, papers(title)").eq("project_id", project_id).execute()
            
            nodes = []
            for n in nodes_res.data:
                p_ids = json.loads(n.get("source_paper_ids") or "[]") if isinstance(n.get("source_paper_ids"), str) else (n.get("source_paper_ids") or [])
                nodes.append({
                    "id": n["id"],
                    "name": n["name"],
                    "category": n["category"],
                    "description": n.get("description") or "",
                    "source_paper_ids": p_ids,
                    "created_at": n.get("created_at")
                })
                
            edges = []
            for e in edges_res.data:
                paper_info = e.get("papers") or {}
                edges.append({
                    "id": e["id"],
                    "source_node_id": e["source_node_id"],
                    "target_node_id": e["target_node_id"],
                    "relation_type": e["relation_type"],
                    "evidence": e.get("evidence") or "",
                    "source_paper_id": e.get("source_paper_id"),
                    "source_paper_title": paper_info.get("title") or "Saved Literature",
                    "created_at": e.get("created_at")
                })
                
            return {"nodes": nodes, "edges": edges}
        except Exception as e:
            print(f"Error getting knowledge graph: {e}")
            return {"nodes": [], "edges": []}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT role FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id))
        if not c.fetchone():
            conn.close()
            return {"nodes": [], "edges": []}
            
        c.execute("SELECT id, name, category, description, source_paper_ids, created_at FROM knowledge_nodes WHERE project_id = ? ORDER BY name ASC", (project_id,))
        nodes_rows = c.fetchall()
        
        nodes = []
        for r in nodes_rows:
            try:
                p_ids = json.loads(r[4]) if r[4] else []
            except Exception:
                p_ids = []
            nodes.append({
                "id": r[0],
                "name": r[1],
                "category": r[2],
                "description": r[3] or "",
                "source_paper_ids": p_ids,
                "created_at": r[5]
            })
            
        c.execute("""
            SELECT e.id, e.source_node_id, e.target_node_id, e.relation_type, e.evidence, e.source_paper_id, e.created_at, p.title
            FROM knowledge_edges e
            LEFT JOIN papers p ON e.source_paper_id = p.id
            WHERE e.project_id = ?
        """, (project_id,))
        edges_rows = c.fetchall()
        
        edges = []
        for r in edges_rows:
            edges.append({
                "id": r[0],
                "source_node_id": r[1],
                "target_node_id": r[2],
                "relation_type": r[3],
                "evidence": r[4] or "",
                "source_paper_id": r[5],
                "source_paper_title": r[7] or "Saved Literature",
                "created_at": r[6]
            })
        conn.close()
        return {"nodes": nodes, "edges": edges}

def delete_knowledge_node(project_id, node_id, user_id):
    """Delete a knowledge node and its connected edges."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            supabase_client.table("knowledge_edges").delete().eq("project_id", project_id).or_(f"source_node_id.eq.{node_id},target_node_id.eq.{node_id}").execute()
            supabase_client.table("knowledge_nodes").delete().eq("id", node_id).eq("project_id", project_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("DELETE FROM knowledge_edges WHERE project_id = ? AND (source_node_id = ? OR target_node_id = ?)", (project_id, node_id, node_id))
            c.execute("DELETE FROM knowledge_nodes WHERE id = ? AND project_id = ?", (node_id, project_id))
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

def clear_project_knowledge_graph(project_id, user_id):
    """Reset the knowledge graph for a project."""
    if IS_SUPABASE_CONFIGURED and supabase_client:
        try:
            supabase_client.table("knowledge_edges").delete().eq("project_id", project_id).execute()
            supabase_client.table("knowledge_nodes").delete().eq("project_id", project_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("DELETE FROM knowledge_edges WHERE project_id = ?", (project_id,))
            c.execute("DELETE FROM knowledge_nodes WHERE project_id = ?", (project_id,))
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()



