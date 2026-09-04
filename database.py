import os
import sqlite3
import uuid
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
