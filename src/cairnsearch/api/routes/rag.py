"""RAG API routes with conversation context support."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json

from cairnsearch.rag import RAGEngine, get_rag_config


router = APIRouter()


class Message(BaseModel):
    """A single message in conversation history."""
    role: str  # "user" or "assistant"
    content: str


class AskRequest(BaseModel):
    """Ask question request with optional conversation history."""
    question: str
    top_k: Optional[int] = None
    file_path: Optional[str] = None  # Filter to specific file
    stream: bool = False
    conversation_history: Optional[list[Message]] = None  # Previous messages for context


class AskResponse(BaseModel):
    """Ask question response."""
    answer: str
    sources: list[dict]
    query: str
    took_ms: float


class SummarizeRequest(BaseModel):
    """Summarize request."""
    query: str
    doc_ids: Optional[list[int]] = None


class IndexRequest(BaseModel):
    """Index document request."""
    doc_id: int
    file_path: str
    filename: str
    content: str


class ReindexDocRequest(BaseModel):
    """Reindex a specific document by ID."""
    doc_id: int


def _build_conversation_context(history: list[Message], current_question: str) -> str:
    """Build a contextualized query from conversation history.
    
    This helps the AI understand follow-up questions by including relevant
    conversation context in the retrieval query.
    """
    if not history or len(history) == 0:
        return current_question
    
    # Build context from recent history (last 3 exchanges max)
    recent_history = history[-6:] if len(history) > 6 else history
    
    context_parts = []
    for msg in recent_history:
        if msg.role == "user":
            context_parts.append(f"User asked: {msg.content}")
        else:
            # Include key points from assistant response (first 200 chars)
            summary = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            context_parts.append(f"Assistant answered: {summary}")
    
    context_parts.append(f"Current question: {current_question}")
    
    return "\n".join(context_parts)


def _create_contextual_prompt(history: list[Message], question: str, context: str) -> str:
    """Create a prompt that includes conversation history for better follow-up handling."""
    
    history_text = ""
    if history and len(history) > 0:
        history_parts = []
        for msg in history[-6:]:  # Last 3 exchanges
            if msg.role == "user":
                history_parts.append(f"User: {msg.content}")
            else:
                history_parts.append(f"Assistant: {msg.content}")
        history_text = "\n".join(history_parts)
    
    if history_text:
        return f"""Based on the following documents and our conversation history, answer the question.

CONVERSATION HISTORY:
{history_text}

RELEVANT DOCUMENTS:
{context}

CURRENT QUESTION: {question}

Instructions:
- Consider the conversation history when interpreting the current question
- If this appears to be a follow-up question, reference the previous context
- Answer based on the provided documents
- If you need to reference previous answers, do so naturally
- Cite the source documents when making claims

ANSWER:"""
    else:
        return f"""Based on the following documents, answer the question.

DOCUMENTS:
{context}

QUESTION: {question}

ANSWER:"""


@router.post("/rag/ask", response_model=None)
async def ask_question(request: AskRequest):
    """
    Ask a question and get an answer from indexed documents.
    
    Uses RAG (Retrieval-Augmented Generation):
    1. Retrieves relevant document chunks (using conversation context for follow-ups)
    2. Uses LLM to generate answer based on retrieved context and conversation history
    """
    engine = RAGEngine()
    
    if not engine.llm.is_available:
        raise HTTPException(
            status_code=503,
            detail="LLM not available. Configure Ollama or API key."
        )
    
    # Build enhanced query for retrieval if there's conversation history
    retrieval_query = request.question
    if request.conversation_history and len(request.conversation_history) > 0:
        # For follow-up questions, include context in the retrieval query
        # This helps find relevant chunks even when the follow-up is vague
        last_user_messages = [m.content for m in request.conversation_history if m.role == "user"][-2:]
        if last_user_messages:
            retrieval_query = f"{' '.join(last_user_messages)} {request.question}"
    
    if request.stream:
        # Streaming response with conversation context
        async def generate():
            import time
            start_time = time.perf_counter()
            
            # Retrieve with enhanced query
            chunks = engine.retriever.retrieve(
                retrieval_query,
                top_k=request.top_k or 10,  # Get more chunks for better context
                file_path_filter=request.file_path,
            )
            
            if not chunks:
                no_results_msg = "I couldn't find any relevant information in the indexed documents."
                yield f"data: {json.dumps({'token': no_results_msg})}\n\n"
                yield "data: [DONE]\n\n"
                return
            
            # Build context from chunks
            context = engine._build_context(chunks)
            
            # Create prompt with conversation history
            prompt = _create_contextual_prompt(
                request.conversation_history or [],
                request.question,
                context
            )
            
            system_prompt = """You are a helpful assistant that answers questions based on the provided documents.

Instructions:
- Answer based ONLY on the provided context and conversation history
- If the context doesn't contain enough information, say so
- Cite the source documents when making claims
- Be concise and direct
- For follow-up questions, use the conversation history to understand context
- If asked about something not in the context, say "I don't have information about that in the provided documents"
"""
            
            for token in engine.llm.generate_stream(prompt, system=system_prompt):
                yield f"data: {json.dumps({'token': token})}\n\n"
            
            # Send sources at the end
            sources = [
                {
                    "chunk_id": s.chunk_id,
                    "doc_id": s.doc_id,
                    "file_path": s.file_path,
                    "filename": s.filename,
                    "content": s.content[:300] + "..." if len(s.content) > 300 else s.content,
                    "score": s.score,
                }
                for s in chunks[:5]  # Top 5 sources
            ]
            yield f"data: {json.dumps({'sources': sources})}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
        )
    
    # Non-streaming response with conversation context
    import time
    start_time = time.perf_counter()
    
    # Retrieve with enhanced query
    chunks = engine.retriever.retrieve(
        retrieval_query,
        top_k=request.top_k or 10,
        file_path_filter=request.file_path,
    )
    
    if not chunks:
        return AskResponse(
            answer="I couldn't find any relevant information in the indexed documents.",
            sources=[],
            query=request.question,
            took_ms=round((time.perf_counter() - start_time) * 1000, 2),
        )
    
    # Build context and create prompt with conversation history
    context = engine._build_context(chunks)
    prompt = _create_contextual_prompt(
        request.conversation_history or [],
        request.question,
        context
    )
    
    system_prompt = """You are a helpful assistant that answers questions based on the provided documents.

Instructions:
- Answer based ONLY on the provided context and conversation history
- If the context doesn't contain enough information, say so
- Cite the source documents when making claims
- Be concise and direct
- For follow-up questions, use the conversation history to understand context
- If asked about something not in the context, say "I don't have information about that in the provided documents"
"""
    
    answer = engine.llm.generate(prompt, system=system_prompt)
    
    took_ms = round((time.perf_counter() - start_time) * 1000, 2)
    
    return AskResponse(
        answer=answer,
        sources=[
            {
                "chunk_id": s.chunk_id,
                "doc_id": s.doc_id,
                "file_path": s.file_path,
                "filename": s.filename,
                "content": s.content[:300] + "..." if len(s.content) > 300 else s.content,
                "score": s.score,
                "page": getattr(s, 'page', None),
                "chunk_index": getattr(s, 'chunk_index', None),
            }
            for s in chunks
        ],
        query=request.question,
        took_ms=took_ms,
    )


@router.post("/rag/summarize")
async def summarize_search(request: SummarizeRequest) -> dict:
    """
    Summarize search results using LLM.
    """
    engine = RAGEngine()
    
    if not engine.llm.is_available:
        raise HTTPException(
            status_code=503,
            detail="LLM not available. Configure Ollama or API key."
        )
    
    # Get relevant chunks
    chunks = engine.retriever.retrieve(request.query, top_k=10)
    
    if not chunks:
        return {"summary": "No relevant documents found.", "sources": []}
    
    # Generate summary
    summary = engine.summarize_results(request.query, chunks)
    
    return {
        "summary": summary,
        "query": request.query,
        "sources": [
            {"filename": c.filename, "file_path": c.file_path}
            for c in chunks
        ],
    }


@router.post("/rag/index")
async def index_document(request: IndexRequest) -> dict:
    """
    Index a document for RAG.
    
    This chunks the document, generates embeddings, and stores in vector DB.
    """
    engine = RAGEngine()
    
    chunks_added = engine.index_document(
        doc_id=request.doc_id,
        file_path=request.file_path,
        filename=request.filename,
        content=request.content,
    )
    
    return {
        "doc_id": request.doc_id,
        "chunks_indexed": chunks_added,
    }


@router.post("/rag/reindex-document")
async def reindex_document_by_id(request: ReindexDocRequest) -> dict:
    """
    Re-index a specific document by ID.
    
    Fetches the document from the database and re-indexes it.
    """
    from cairnsearch.db import Database
    from cairnsearch.indexer import IndexManager
    from pathlib import Path
    
    db = Database()
    engine = RAGEngine()
    
    # Get document info from database
    with db.connection() as conn:
        row = conn.execute(
            "SELECT id, file_path, filename, content FROM documents WHERE id = ?",
            (request.doc_id,)
        ).fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc_id, file_path, filename, content = row
    
    # Check if file still exists
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File no longer exists on disk")
    
    # Re-extract content if needed
    if not content:
        index_manager = IndexManager()
        try:
            from cairnsearch.extractors import ExtractorRegistry
            registry = ExtractorRegistry()
            extractor = registry.get_extractor(path)
            if extractor:
                result = extractor.extract(path)
                content = result.text
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to extract content: {str(e)}")
    
    # Re-index in vector store
    chunks_added = engine.index_document(
        doc_id=doc_id,
        file_path=file_path,
        filename=filename,
        content=content or "",
    )
    
    return {
        "doc_id": doc_id,
        "filename": filename,
        "chunks_indexed": chunks_added,
        "message": f"Successfully re-indexed {filename}"
    }


@router.delete("/rag/index/{doc_id}")
async def delete_document(doc_id: int) -> dict:
    """Delete document from RAG index."""
    engine = RAGEngine()
    deleted = engine.delete_document(doc_id)
    
    return {
        "doc_id": doc_id,
        "chunks_deleted": deleted,
    }


@router.get("/rag/status")
async def rag_status() -> dict:
    """Get RAG system status."""
    engine = RAGEngine()
    stats = engine.get_stats()
    
    config = get_rag_config()
    
    # Check embeddings availability
    embeddings_available = False
    embeddings_error = None
    try:
        from cairnsearch.rag.embeddings import get_embedder
        embedder = get_embedder()
        # Try a simple test embedding
        test_result = embedder.embed("test")
        if test_result and len(test_result) > 0:
            embeddings_available = True
    except Exception as e:
        embeddings_error = str(e)
    
    return {
        "enabled": config.enabled,
        "llm": {
            "provider": config.llm_provider.value,
            "model": config.ollama_model if config.llm_provider.value == "ollama" else config.anthropic_model,
            "available": engine.llm.is_available,
        },
        "embeddings": {
            "provider": config.embedding_provider.value,
            "model": config.embedding_model,
            "available": embeddings_available,
            "error": embeddings_error,
        },
        "vector_store": stats["vector_store"],
        "settings": {
            "chunk_size": config.chunk_size,
            "top_k": config.top_k,
            "hybrid_search": config.hybrid_search,
        },
    }


class TestConnectionRequest(BaseModel):
    """Test connection request."""
    provider: str = "ollama"
    model: str = "llama3.1:8b"


@router.post("/rag/test-connection")
async def test_connection(request: TestConnectionRequest) -> dict:
    """
    Test connection to a specific LLM provider.
    
    This endpoint actually validates the connection rather than
    just checking if credentials exist.
    """
    import os
    
    llm_available = False
    llm_error = None
    embeddings_available = False
    embeddings_error = None
    
    # Test LLM connection based on selected provider
    if request.provider == "ollama":
        try:
            import httpx
            # Check if Ollama is running
            response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
            if response.status_code == 200:
                # Check if the specific model is available
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if any(request.model in name or name in request.model for name in model_names):
                    llm_available = True
                else:
                    llm_error = f"Model '{request.model}' not found. Available: {', '.join(model_names[:5])}"
            else:
                llm_error = "Ollama not responding"
        except Exception as e:
            llm_error = f"Cannot connect to Ollama: {str(e)}"
    
    elif request.provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            llm_error = "OPENAI_API_KEY environment variable not set"
        else:
            try:
                import httpx
                response = httpx.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0
                )
                if response.status_code == 200:
                    llm_available = True
                elif response.status_code == 401:
                    llm_error = "Invalid OpenAI API key"
                else:
                    llm_error = f"OpenAI API error: {response.status_code}"
            except Exception as e:
                llm_error = f"Cannot connect to OpenAI: {str(e)}"
    
    elif request.provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            llm_error = "ANTHROPIC_API_KEY environment variable not set"
        else:
            try:
                import httpx
                # Test with a minimal request
                response = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}]
                    },
                    timeout=10.0
                )
                if response.status_code == 200:
                    llm_available = True
                elif response.status_code == 401:
                    llm_error = "Invalid Anthropic API key"
                else:
                    error_detail = response.json().get("error", {}).get("message", str(response.status_code))
                    llm_error = f"Anthropic API error: {error_detail}"
            except Exception as e:
                llm_error = f"Cannot connect to Anthropic: {str(e)}"
    
    # Test embeddings
    try:
        from cairnsearch.rag.embeddings import get_embedder
        embedder = get_embedder()
        test_result = embedder.embed("test")
        if test_result and len(test_result) > 0:
            embeddings_available = True
    except Exception as e:
        embeddings_error = str(e)
    
    return {
        "llm": {
            "provider": request.provider,
            "model": request.model,
            "available": llm_available,
            "error": llm_error,
        },
        "embeddings": {
            "available": embeddings_available,
            "error": embeddings_error,
        }
    }


@router.get("/rag/chunks/{doc_id}")
async def get_document_chunks(doc_id: int) -> dict:
    """Get all chunks for a specific document."""
    from cairnsearch.rag import VectorStore
    import sqlite3
    
    vector_store = VectorStore()
    
    conn = sqlite3.connect(vector_store.db_path)
    cursor = conn.execute(
        "SELECT chunk_id, chunk_index, content FROM chunks WHERE doc_id = ? ORDER BY chunk_index",
        (doc_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    chunks = [
        {
            "chunk_id": row[0],
            "chunk_index": row[1],
            "content": row[2][:500] + "..." if len(row[2]) > 500 else row[2],
        }
        for row in rows
    ]
    
    return {
        "doc_id": doc_id,
        "total_chunks": len(chunks),
        "chunks": chunks,
    }


class RAGConfigRequest(BaseModel):
    """RAG configuration update request."""
    reranker_enabled: Optional[bool] = None
    top_k: Optional[int] = None
    chunk_size: Optional[int] = None
    hybrid_search: Optional[bool] = None
    llm_provider: Optional[str] = None  # "ollama", "anthropic", "openai"
    ollama_model: Optional[str] = None
    openai_model: Optional[str] = None
    anthropic_model: Optional[str] = None
    embedding_provider: Optional[str] = None  # "ollama", "openai", "local"
    openai_embedding_model: Optional[str] = None


@router.post("/rag/config")
async def update_rag_config(request: RAGConfigRequest) -> dict:
    """
    Update RAG configuration settings.
    
    These settings affect how documents are retrieved and reranked.
    """
    from cairnsearch.rag.config import get_rag_config, set_rag_config, LLMProvider, EmbeddingProvider
    
    config = get_rag_config()
    
    # Update only provided fields
    if request.reranker_enabled is not None:
        config.reranker_enabled = request.reranker_enabled
    if request.top_k is not None:
        config.top_k = request.top_k
    if request.chunk_size is not None:
        config.chunk_size = request.chunk_size
    if request.hybrid_search is not None:
        config.hybrid_search = request.hybrid_search
    if request.llm_provider is not None:
        # Map string to enum
        provider_map = {
            "ollama": LLMProvider.OLLAMA,
            "anthropic": LLMProvider.ANTHROPIC,
            "openai": LLMProvider.OPENAI,
            "none": LLMProvider.NONE,
        }
        config.llm_provider = provider_map.get(request.llm_provider.lower(), LLMProvider.OLLAMA)
    if request.ollama_model is not None:
        config.ollama_model = request.ollama_model
    if request.openai_model is not None:
        config.openai_model = request.openai_model
    if request.anthropic_model is not None:
        config.anthropic_model = request.anthropic_model
    if request.embedding_provider is not None:
        # Map string to enum
        embedding_map = {
            "ollama": EmbeddingProvider.OLLAMA,
            "openai": EmbeddingProvider.OPENAI,
            "local": EmbeddingProvider.LOCAL,
        }
        config.embedding_provider = embedding_map.get(request.embedding_provider.lower(), EmbeddingProvider.OLLAMA)
    if request.openai_embedding_model is not None:
        config.openai_embedding_model = request.openai_embedding_model
    
    set_rag_config(config)
    
    return {
        "message": "RAG configuration updated",
        "config": {
            "reranker_enabled": config.reranker_enabled,
            "top_k": config.top_k,
            "chunk_size": config.chunk_size,
            "hybrid_search": config.hybrid_search,
            "llm_provider": config.llm_provider.value,
            "ollama_model": config.ollama_model,
            "openai_model": config.openai_model,
            "anthropic_model": config.anthropic_model,
            "embedding_provider": config.embedding_provider.value,
            "openai_embedding_model": config.openai_embedding_model,
        }
    }


@router.get("/rag/config")
async def get_current_rag_config() -> dict:
    """Get current RAG configuration."""
    config = get_rag_config()
    
    return {
        "reranker_enabled": config.reranker_enabled,
        "top_k": config.top_k,
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "hybrid_search": config.hybrid_search,
        "bm25_weight": config.bm25_weight,
        "vector_weight": config.vector_weight,
        "llm_provider": config.llm_provider.value,
        "ollama_model": config.ollama_model,
        "anthropic_model": config.anthropic_model,
    }
