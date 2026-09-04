import os
import json
import uuid
import requests
from datetime import datetime, timezone
import database as db

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def download_open_access_pdf(project_id, paper_id, pdf_url):
    """Download open-access PDF to project uploads directory and mirror to storage."""
    if not pdf_url:
        return None
        
    proj_dir = os.path.join(UPLOADS_DIR, project_id)
    os.makedirs(proj_dir, exist_ok=True)
    
    local_pdf_path = os.path.join(proj_dir, f"{paper_id}.pdf")
    rel_storage_path = f"uploads/{project_id}/{paper_id}.pdf"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AIResearchLab/1.0"
    }
    
    try:
        response = requests.get(pdf_url, headers=headers, timeout=15, stream=True)
        if response.status_code == 200:
            with open(local_pdf_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # If live Supabase storage is configured, upload to 'papers' bucket
            if db.IS_SUPABASE_CONFIGURED and db.supabase_client:
                try:
                    bucket_name = "papers"
                    storage_dest = f"{project_id}/{paper_id}.pdf"
                    with open(local_pdf_path, "rb") as f:
                        db.supabase_client.storage.from_(bucket_name).upload(
                            file=f,
                            path=storage_dest,
                            file_options={"content-type": "application/pdf", "upsert": "true"}
                        )
                except Exception as st_err:
                    print(f"Notice: Supabase storage upload skipped ({st_err}). Local copy retained.")
            
            return rel_storage_path
    except Exception as e:
        print(f"Could not download open-access PDF from {pdf_url}: {e}")
    return None

def save_paper_to_project(project_id, paper_data, user_id):
    """Save an academic paper to the project's Paper Library."""
    # Verify user has owner or researcher permissions
    role = None
    if db.IS_SUPABASE_CONFIGURED and db.supabase_client:
        mem_res = db.supabase_client.table("project_members").select("role").eq("project_id", project_id).eq("user_id", user_id).execute()
        if mem_res.data:
            role = mem_res.data[0]["role"]
    else:
        import sqlite3
        conn = sqlite3.connect(db.LOCAL_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT role FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id))
        row = c.fetchone()
        conn.close()
        if row:
            role = row[0]
            
    if role not in ('owner', 'researcher'):
        return {"success": False, "error": "Only Owners and Researchers can save papers to the library."}
        
    paper_id = str(uuid.uuid4())
    title = paper_data.get("title", "").strip() or "Untitled Paper"
    authors = paper_data.get("authors", [])
    abstract = paper_data.get("abstract", "").strip()
    year = paper_data.get("year")
    venue = paper_data.get("venue", "").strip()
    doi = paper_data.get("doi")
    arxiv_id = paper_data.get("arxiv_id")
    oa_pdf_url = paper_data.get("open_access_pdf_url")
    ts = now_iso()
    
    # Download open access PDF if available
    storage_path = download_open_access_pdf(project_id, paper_id, oa_pdf_url)
    
    authors_json = json.dumps(authors)
    
    if db.IS_SUPABASE_CONFIGURED and db.supabase_client:
        try:
            record = {
                "id": paper_id,
                "project_id": project_id,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "year": year,
                "venue": venue,
                "doi": doi,
                "arxiv_id": arxiv_id,
                "open_access_pdf_url": oa_pdf_url,
                "storage_path": storage_path,
                "added_by": user_id,
                "created_at": ts
            }
            db.supabase_client.table("papers").insert(record).execute()
            # Update project timestamp
            db.supabase_client.table("projects").update({"updated_at": ts}).eq("id", project_id).execute()
            return {"success": True, "paper_id": paper_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        import sqlite3
        conn = sqlite3.connect(db.LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO papers (id, project_id, title, authors, abstract, year, venue, doi, arxiv_id, open_access_pdf_url, storage_path, added_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (paper_id, project_id, title, authors_json, abstract, year, venue, doi, arxiv_id, oa_pdf_url, storage_path, user_id, ts))
            c.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, project_id))
            conn.commit()
            return {"success": True, "paper_id": paper_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

def get_project_papers(project_id, user_id):
    """Fetch all saved papers for a given project."""
    if db.IS_SUPABASE_CONFIGURED and db.supabase_client:
        try:
            # Check membership
            mem_res = db.supabase_client.table("project_members").select("role").eq("project_id", project_id).eq("user_id", user_id).execute()
            if not mem_res.data:
                return []
            
            papers_res = db.supabase_client.table("papers").select("*, profiles(full_name, email)").eq("project_id", project_id).order("created_at", desc=True).execute()
            papers = []
            for p in papers_res.data:
                prof = p.get("profiles") or {}
                p["added_by_name"] = prof.get("full_name") or prof.get("email", "Lab Member")
                papers.append(p)
            return papers
        except Exception as e:
            print(f"Error getting project papers: {e}")
            return []
    else:
        import sqlite3
        conn = sqlite3.connect(db.LOCAL_DB_PATH)
        c = conn.cursor()
        # Verify access
        c.execute("SELECT role FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id))
        if not c.fetchone():
            conn.close()
            return []
        
        c.execute("""
            SELECT p.id, p.project_id, p.title, p.authors, p.abstract, p.year, p.venue, 
                   p.doi, p.arxiv_id, p.open_access_pdf_url, p.storage_path, p.added_by, p.created_at,
                   prof.full_name, prof.email
            FROM papers p
            LEFT JOIN profiles prof ON p.added_by = prof.id
            WHERE p.project_id = ?
            ORDER BY p.created_at DESC
        """, (project_id,))
        rows = c.fetchall()
        conn.close()
        
        papers = []
        for r in rows:
            authors = []
            try:
                authors = json.loads(r[3]) if r[3] else []
            except Exception:
                authors = [r[3]] if r[3] else []
            
            papers.append({
                "id": r[0],
                "project_id": r[1],
                "title": r[2],
                "authors": authors,
                "abstract": r[4],
                "year": r[5],
                "venue": r[6],
                "doi": r[7],
                "arxiv_id": r[8],
                "open_access_pdf_url": r[9],
                "storage_path": r[10],
                "added_by": r[11],
                "created_at": r[12],
                "added_by_name": r[13] or (r[14].split("@")[0] if r[14] else "Lab Member")
            })
        return papers

def delete_project_paper(project_id, paper_id, user_id):
    """Delete a saved paper from the project library."""
    role = None
    if db.IS_SUPABASE_CONFIGURED and db.supabase_client:
        mem_res = db.supabase_client.table("project_members").select("role").eq("project_id", project_id).eq("user_id", user_id).execute()
        if mem_res.data:
            role = mem_res.data[0]["role"]
    else:
        import sqlite3
        conn = sqlite3.connect(db.LOCAL_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT role FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id))
        row = c.fetchone()
        conn.close()
        if row:
            role = row[0]
            
    if role not in ('owner', 'researcher'):
        return {"success": False, "error": "Only Owners and Researchers can remove papers."}
        
    if db.IS_SUPABASE_CONFIGURED and db.supabase_client:
        try:
            db.supabase_client.table("papers").delete().eq("id", paper_id).eq("project_id", project_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        import sqlite3
        conn = sqlite3.connect(db.LOCAL_DB_PATH)
        c = conn.cursor()
        try:
            c.execute("DELETE FROM papers WHERE id = ? AND project_id = ?", (paper_id, project_id))
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()
