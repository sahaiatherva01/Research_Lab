import os
import pymupdf as fitz


def extract_pdf_pages(pdf_path):
    """Extract page-by-page text and metadata from a PDF file using PyMuPDF."""
    if not os.path.exists(pdf_path):
        return {"success": False, "error": f"PDF file not found at {pdf_path}"}
    
    try:
        doc = fitz.open(pdf_path)
        pages_data = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            pages_data.append({
                "page_number": page_num + 1,
                "text": text.strip(),
                "char_count": len(text)
            })
            
        metadata = {
            "page_count": len(doc),
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "subject": doc.metadata.get("subject", ""),
            "keywords": doc.metadata.get("keywords", "")
        }
        
        doc.close()
        return {
            "success": True,
            "metadata": metadata,
            "pages": pages_data
        }
    except Exception as e:
        return {"success": False, "error": f"PyMuPDF extraction failed: {str(e)}"}

def extract_pdf_chunks(pdf_path, chunk_size=400, overlap=50):
    """
    Extract overlapping text chunks from PDF with page numbers and section context.
    Essential for local FAISS vector index grounding.
    """
    res = extract_pdf_pages(pdf_path)
    if not res.get("success"):
        return res
    
    chunks = []
    for page in res.get("pages", []):
        text = page["text"]
        page_num = page["page_number"]
        words = text.split()
        
        if not words:
            continue
            
        i = 0
        while i < len(words):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            if len(chunk_text.strip()) > 30:  # Skip tiny noise fragments
                chunks.append({
                    "page_number": page_num,
                    "text": chunk_text,
                    "word_count": len(chunk_words)
                })
            i += (chunk_size - overlap)
            
    return {
        "success": True,
        "metadata": res["metadata"],
        "total_chunks": len(chunks),
        "chunks": chunks
    }
