"""Document features API - summaries, similar documents, document chat."""
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["document-features"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SummarizeRequest(BaseModel):
    """Request to summarize a document."""
    doc_id: int
    summary_type: str = "executive"  # executive, key_points, detailed
    regenerate: bool = False


class SummaryResponse(BaseModel):
    """Document summary response."""
    doc_id: int
    filename: str
    summary_type: str
    summary: str
    key_points: List[str] = []
    generated_at: str


class SimilarRequest(BaseModel):
    """Request to find similar documents."""
    doc_id: int
    top_k: int = 10
    min_similarity: float = 0.5


class SimilarDocument(BaseModel):
    """A similar document result."""
    doc_id: int
    file_path: str
    filename: str
    file_type: str
    similarity_score: float
    snippet: str


class ChatMessage(BaseModel):
    """A message in document chat."""
    role: str  # user or assistant
    content: str


class DocumentChatRequest(BaseModel):
    """Request to chat with a specific document."""
    doc_id: int
    message: str
    conversation_history: List[ChatMessage] = []
    stream: bool = True


# ============================================================================
# Document Summaries
# ============================================================================

# Cache for generated summaries
_summary_cache: Dict[str, SummaryResponse] = {}


@router.post("/summarize", response_model=SummaryResponse)
async def summarize_document(request: SummarizeRequest):
    """
    Generate a summary for a document.
    
    Summary types:
    - executive: One paragraph overview
    - key_points: Bullet points of main ideas
    - detailed: Comprehensive summary with sections
    """
    from cairnsearch.db import Database
    from cairnsearch.rag import RAGEngine
    from datetime import datetime
    
    db = Database()
    
    # Get document
    rows = db.execute(
        "SELECT id, filename, content FROM documents WHERE id = ?",
        (request.doc_id,)
    )
    
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = rows[0]
    doc_id = doc["id"]
    filename = doc["filename"]
    content = doc["content"] or ""
    
    if not content.strip():
        raise HTTPException(status_code=400, detail="Document has no content to summarize")
    
    # Check cache
    cache_key = f"{doc_id}:{request.summary_type}"
    if cache_key in _summary_cache and not request.regenerate:
        return _summary_cache[cache_key]
    
    # Generate summary using LLM
    engine = RAGEngine()
    
    if not engine.llm.is_available:
        raise HTTPException(status_code=503, detail="LLM not available")
    
    # Truncate content if too long
    max_content = 15000  # ~4k tokens
    if len(content) > max_content:
        content = content[:max_content] + "\n\n[Content truncated...]"
    
    # Build prompt based on summary type
    if request.summary_type == "executive":
        prompt = f"""Summarize the following document in one clear, concise paragraph (3-5 sentences).
Focus on the main purpose and key takeaways.

DOCUMENT: {filename}
---
{content}
---

EXECUTIVE SUMMARY:"""
    
    elif request.summary_type == "key_points":
        prompt = f"""Extract the 5-7 most important points from this document as bullet points.
Each point should be one clear sentence.

DOCUMENT: {filename}
---
{content}
---

KEY POINTS:"""
    
    else:  # detailed
        prompt = f"""Provide a comprehensive summary of this document with the following structure:
1. Overview (2-3 sentences)
2. Main Topics Covered
3. Key Details
4. Conclusions/Takeaways

DOCUMENT: {filename}
---
{content}
---

DETAILED SUMMARY:"""
    
    system = "You are a helpful assistant that creates clear, accurate document summaries. Be concise and focus on the most important information."
    
    summary_text = engine.llm.generate(prompt, system=system)
    
    # Extract key points if applicable
    key_points = []
    if request.summary_type == "key_points":
        # Parse bullet points
        for line in summary_text.split('\n'):
            line = line.strip()
            if line and (line.startswith('-') or line.startswith('•') or line.startswith('*') or (len(line) > 2 and line[0].isdigit() and line[1] in '.)')):
                point = line.lstrip('-•*0123456789.) ').strip()
                if point:
                    key_points.append(point)
    
    response = SummaryResponse(
        doc_id=doc_id,
        filename=filename,
        summary_type=request.summary_type,
        summary=summary_text,
        key_points=key_points,
        generated_at=datetime.now().isoformat(),
    )
    
    # Cache the result
    _summary_cache[cache_key] = response
    
    return response


@router.get("/{doc_id}/summary")
async def get_document_summary(doc_id: int, summary_type: str = "executive"):
    """Get or generate summary for a document."""
    return await summarize_document(SummarizeRequest(
        doc_id=doc_id,
        summary_type=summary_type,
        regenerate=False,
    ))


# ============================================================================
# Similar Documents
# ============================================================================

@router.post("/similar", response_model=List[SimilarDocument])
async def find_similar_documents(request: SimilarRequest):
    """
    Find documents similar to a given document using embedding similarity.
    """
    from cairnsearch.db import Database
    from cairnsearch.rag import VectorStore
    import numpy as np
    
    db = Database()
    vector_store = VectorStore()
    
    # Get source document
    rows = db.execute(
        "SELECT id, filename, content FROM documents WHERE id = ?",
        (request.doc_id,)
    )
    
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    
    source_doc = rows[0]
    
    # Get embedding for source document (use average of chunk embeddings)
    source_embedding = vector_store.get_document_embedding(request.doc_id)
    
    if source_embedding is None:
        raise HTTPException(status_code=400, detail="Document has no embeddings. Try reindexing.")
    
    # Find similar documents
    similar_docs = vector_store.find_similar_documents(
        embedding=source_embedding,
        exclude_doc_id=request.doc_id,
        top_k=request.top_k,
        min_similarity=request.min_similarity,
    )
    
    # Enrich with document metadata
    results = []
    for doc_id, similarity in similar_docs:
        doc_rows = db.execute(
            "SELECT id, file_path, filename, file_type, content FROM documents WHERE id = ?",
            (doc_id,)
        )
        if doc_rows:
            doc = doc_rows[0]
            content = doc["content"] or ""
            snippet = content[:300] + "..." if len(content) > 300 else content
            
            results.append(SimilarDocument(
                doc_id=doc["id"],
                file_path=doc["file_path"],
                filename=doc["filename"],
                file_type=doc["file_type"],
                similarity_score=round(similarity, 3),
                snippet=snippet,
            ))
    
    return results


@router.get("/{doc_id}/similar")
async def get_similar_documents(doc_id: int, top_k: int = 10):
    """Get documents similar to the specified document."""
    return await find_similar_documents(SimilarRequest(
        doc_id=doc_id,
        top_k=top_k,
    ))


# ============================================================================
# Document Chat (Chat with specific document)
# ============================================================================

@router.post("/{doc_id}/chat")
async def chat_with_document(doc_id: int, request: DocumentChatRequest):
    """
    Chat with a specific document. All responses are grounded in that document only.
    """
    from cairnsearch.db import Database
    from cairnsearch.rag import RAGEngine
    
    db = Database()
    
    # Get document
    rows = db.execute(
        "SELECT id, filename, content FROM documents WHERE id = ?",
        (doc_id,)
    )
    
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = rows[0]
    filename = doc["filename"]
    content = doc["content"] or ""
    
    if not content.strip():
        raise HTTPException(status_code=400, detail="Document has no content")
    
    engine = RAGEngine()
    
    if not engine.llm.is_available:
        raise HTTPException(status_code=503, detail="LLM not available")
    
    # Build conversation context
    history_text = ""
    if request.conversation_history:
        history_parts = []
        for msg in request.conversation_history[-6:]:  # Last 3 exchanges
            if msg.role == "user":
                history_parts.append(f"User: {msg.content}")
            else:
                history_parts.append(f"Assistant: {msg.content}")
        history_text = "\n".join(history_parts)
    
    # Truncate document if too long
    max_content = 20000  # ~5k tokens
    if len(content) > max_content:
        # Try to get relevant chunks instead
        chunks = engine.retriever.retrieve(
            request.message,
            top_k=10,
            file_path_filter=doc["file_path"] if "file_path" in doc.keys() else None,
        )
        if chunks:
            content = "\n\n---\n\n".join([c.content for c in chunks])
        else:
            content = content[:max_content] + "\n\n[Content truncated...]"
    
    # Build prompt
    if history_text:
        prompt = f"""You are having a conversation about a specific document. Answer questions based ONLY on this document.

DOCUMENT: {filename}
---
{content}
---

CONVERSATION HISTORY:
{history_text}

CURRENT QUESTION: {request.message}

Instructions:
- Answer based ONLY on the document above
- If the answer isn't in the document, say so
- Reference specific parts of the document when relevant
- Consider the conversation history for context

ANSWER:"""
    else:
        prompt = f"""Answer the question based ONLY on the following document.

DOCUMENT: {filename}
---
{content}
---

QUESTION: {request.message}

Instructions:
- Answer based ONLY on the document above
- If the answer isn't in the document, say "I don't see that information in this document"
- Be specific and reference parts of the document when relevant

ANSWER:"""
    
    system = f"You are a helpful assistant discussing the document '{filename}'. Only use information from this document to answer questions."
    
    if request.stream:
        async def generate():
            for token in engine.llm.generate_stream(prompt, system=system):
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield f"data: {json.dumps({'done': True, 'filename': filename})}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
        )
    else:
        answer = engine.llm.generate(prompt, system=system)
        return {
            "answer": answer,
            "doc_id": doc_id,
            "filename": filename,
        }


# ============================================================================
# Document Preview / Content
# ============================================================================

@router.get("/{doc_id}/content")
async def get_document_content(
    doc_id: int,
    page: Optional[int] = None,
    highlight: Optional[str] = None,
):
    """
    Get document content for preview.
    
    Args:
        doc_id: Document ID
        page: Specific page number (for PDFs)
        highlight: Search term to highlight
    """
    from cairnsearch.db import Database
    import re
    
    db = Database()
    
    rows = db.execute(
        "SELECT id, file_path, filename, file_type, content, page_count FROM documents WHERE id = ?",
        (doc_id,)
    )
    
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = rows[0]
    content = doc["content"] or ""
    
    # Apply highlighting if requested
    highlighted_content = content
    highlight_positions = []
    
    if highlight and highlight.strip():
        terms = highlight.lower().split()
        for term in terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            for match in pattern.finditer(content):
                highlight_positions.append({
                    "start": match.start(),
                    "end": match.end(),
                    "term": term,
                })
            # Wrap matches in highlight tags
            highlighted_content = pattern.sub(
                lambda m: f"<mark>{m.group()}</mark>",
                highlighted_content
            )
    
    return {
        "doc_id": doc["id"],
        "file_path": doc["file_path"],
        "filename": doc["filename"],
        "file_type": doc["file_type"],
        "page_count": doc["page_count"],
        "content": content,
        "highlighted_content": highlighted_content if highlight else None,
        "highlight_positions": highlight_positions if highlight else [],
        "content_length": len(content),
    }


@router.get("/{doc_id}/metadata")
async def get_document_metadata(doc_id: int):
    """Get document metadata without full content."""
    from cairnsearch.db import Database
    import os
    
    db = Database()
    
    rows = db.execute(
        """SELECT d.*, f.hash, f.size_bytes, f.file_mtime, f.status
           FROM documents d
           LEFT JOIN files_meta f ON d.file_path = f.path
           WHERE d.id = ?""",
        (doc_id,)
    )
    
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = rows[0]
    
    # Get chunk count
    try:
        from cairnsearch.rag import VectorStore
        vs = VectorStore()
        chunk_count = vs.get_chunk_count(doc_id)
    except:
        chunk_count = 0
    
    return {
        "doc_id": doc["id"],
        "file_path": doc["file_path"],
        "filename": doc["filename"],
        "file_type": doc["file_type"],
        "page_count": doc["page_count"],
        "title": doc["doc_title"],
        "author": doc["doc_author"],
        "created": doc["doc_created"],
        "modified": doc["doc_modified"],
        "extraction_method": doc["extraction_method"],
        "indexed_at": doc["created_at"],
        "updated_at": doc["updated_at"],
        "file_hash": doc["hash"] if "hash" in doc.keys() else None,
        "file_size_bytes": doc["size_bytes"] if "size_bytes" in doc.keys() else None,
        "content_length": len(doc["content"]) if doc["content"] else 0,
        "chunk_count": chunk_count,
        "status": doc["status"] if "status" in doc.keys() else "indexed",
    }
