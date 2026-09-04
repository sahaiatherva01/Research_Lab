import requests
import urllib.parse
import xml.etree.ElementTree as ET

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_URL = "http://export.arxiv.org/api/query"

def search_semantic_scholar(query, limit=10):
    """Search academic papers using Semantic Scholar Graph API."""
    params = {
        "query": query,
        "limit": limit,
        "fields": "paperId,title,abstract,authors,year,venue,citationCount,openAccessPdf,externalIds"
    }
    headers = {
        "User-Agent": "AIResearchLab/1.0 (academic-research-tool)"
    }
    
    try:
        response = requests.get(SEMANTIC_SCHOLAR_URL, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            papers = []
            for item in data.get("data", []):
                authors = [a.get("name") for a in item.get("authors", []) if a.get("name")]
                external_ids = item.get("externalIds") or {}
                oa_pdf = item.get("openAccessPdf") or {}
                pdf_url = oa_pdf.get("url") if isinstance(oa_pdf, dict) else None
                
                # If no direct OA pdf url from semantic scholar, check if arxiv external id exists
                arxiv_id = external_ids.get("ArXiv")
                if not pdf_url and arxiv_id:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                
                papers.append({
                    "id": item.get("paperId"),
                    "title": item.get("title") or "Untitled Paper",
                    "authors": authors,
                    "abstract": item.get("abstract") or "No abstract available.",
                    "year": item.get("year"),
                    "venue": item.get("venue") or "Academic Publication",
                    "citation_count": item.get("citationCount") or 0,
                    "doi": external_ids.get("DOI"),
                    "arxiv_id": arxiv_id,
                    "open_access_pdf_url": pdf_url,
                    "source": "Semantic Scholar"
                })
            return {"success": True, "papers": papers}
        else:
            return {"success": False, "error": f"Semantic Scholar API responded with status {response.status_code}"}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Search timed out. Please try again."}
    except Exception as e:
        return {"success": False, "error": f"Semantic Scholar search error: {str(e)}"}

def search_arxiv(query, limit=10):
    """Search preprints on arXiv API using Atom XML feed."""
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": "relevance",
        "sortOrder": "descending"
    }
    try:
        response = requests.get(ARXIV_URL, params=params, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            # Atom XML namespace
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            papers = []
            
            for entry in root.findall("atom:entry", ns):
                title_elem = entry.find("atom:title", ns)
                summary_elem = entry.find("atom:summary", ns)
                published_elem = entry.find("atom:published", ns)
                id_elem = entry.find("atom:id", ns)
                
                title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else "Untitled"
                abstract = summary_elem.text.strip().replace("\n", " ") if summary_elem is not None and summary_elem.text else "No abstract."
                published = published_elem.text[:4] if published_elem is not None and published_elem.text else None
                year = int(published) if published and published.isdigit() else None
                
                arxiv_url = id_elem.text.strip() if id_elem is not None and id_elem.text else ""
                arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else arxiv_url.split("/")[-1]
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else None
                
                authors = []
                for author_elem in entry.findall("atom:author", ns):
                    name_elem = author_elem.find("atom:name", ns)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())
                        
                papers.append({
                    "id": f"arxiv_{arxiv_id}",
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "year": year,
                    "venue": "arXiv Preprint",
                    "citation_count": 0,
                    "doi": None,
                    "arxiv_id": arxiv_id,
                    "open_access_pdf_url": pdf_url,
                    "source": "arXiv"
                })
            return {"success": True, "papers": papers}
        else:
            return {"success": False, "error": f"arXiv API error {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"arXiv search error: {str(e)}"}

def search_academic_papers(query, limit=10, source="all"):
    """Unified academic paper search."""
    query = query.strip()
    if not query:
        return {"success": True, "papers": []}
    
    # Try Semantic Scholar first
    res = search_semantic_scholar(query, limit=limit)
    if res.get("success") and res.get("papers"):
        return res
    
    # If Semantic Scholar had no results or error, try arXiv
    arxiv_res = search_arxiv(query, limit=limit)
    if arxiv_res.get("success") and arxiv_res.get("papers"):
        return arxiv_res
        
    return res if res.get("papers") is not None else arxiv_res
