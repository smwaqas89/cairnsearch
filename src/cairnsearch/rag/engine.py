"""Main RAG engine - orchestrates retrieval and generation."""
from dataclasses import dataclass
from typing import Optional, Generator
import logging
import time

from cairnsearch.db import Database
from .config import get_rag_config
from .chunker import DocumentChunker, Chunk
from .embeddings import get_embedder
from .vector_store import VectorStore
from .retriever import HybridRetriever, RetrievalResult
from .llm import get_llm


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided documents.

Instructions:
- Answer based ONLY on the provided context
- If the context doesn't contain enough information, say so
- Cite the source documents when making claims
- Be concise and direct
- If asked about something not in the context, say "I don't have information about that in the provided documents"
"""

QA_PROMPT_TEMPLATE = """Based on the following documents, answer the question.

DOCUMENTS:
{context}

QUESTION: {question}

ANSWER:"""

SUMMARY_PROMPT_TEMPLATE = """Summarize the key information from the following search results.

SEARCH RESULTS:
{context}

Provide a concise summary of the main findings:"""


@dataclass
class RAGResponse:
    """Response from RAG system."""
    answer: str
    sources: list[RetrievalResult]
    query: str
    took_ms: float


class RAGEngine:
    """Main RAG engine combining retrieval and generation."""
    
    def __init__(
        self,
        db: Optional[Database] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        self.config = get_rag_config()
        self.db = db or Database()
        self.vector_store = vector_store or VectorStore()
        self.chunker = DocumentChunker()
        self.embedder = get_embedder()
        self.retriever = HybridRetriever(self.db, self.vector_store)
        self.llm = get_llm()
    
    def index_document(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """Index a document for RAG."""
        self.vector_store.delete_by_doc_id(doc_id)
        
        chunks = self.chunker.chunk_document(
            doc_id=doc_id,
            file_path=file_path,
            filename=filename,
            content=content,
            metadata=metadata,
        )
        
        if not chunks:
            logger.warning(f"No chunks created for document {doc_id}")
            return 0
        
        texts = [chunk.content for chunk in chunks]
        embeddings = self.embedder.embed_batch(texts)
        added = self.vector_store.add_chunks(chunks, embeddings)
        
        logger.info(f"Indexed {added} chunks for document {doc_id}")
        return added
    
    def delete_document(self, doc_id: int) -> int:
        """Delete document chunks from vector store."""
        return self.vector_store.delete_by_doc_id(doc_id)
    
    def ask(
        self,
        question: str,
        top_k: Optional[int] = None,
        file_path_filter: Optional[str] = None,
    ) -> RAGResponse:
        """Ask a question and get an answer from documents."""
        start_time = time.perf_counter()
        
        chunks = self.retriever.retrieve(question, top_k=top_k, file_path_filter=file_path_filter)
        
        if not chunks:
            return RAGResponse(
                answer="I couldn't find any relevant information in the indexed documents.",
                sources=[],
                query=question,
                took_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
        
        context = self._build_context(chunks)
        prompt = QA_PROMPT_TEMPLATE.format(context=context, question=question)
        answer = self.llm.generate(prompt, system=SYSTEM_PROMPT)
        
        took_ms = round((time.perf_counter() - start_time) * 1000, 2)
        
        return RAGResponse(answer=answer, sources=chunks, query=question, took_ms=took_ms)
    
    def ask_stream(
        self,
        question: str,
        top_k: Optional[int] = None,
        file_path_filter: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Ask a question and stream the answer."""
        chunks = self.retriever.retrieve(question, top_k=top_k, file_path_filter=file_path_filter)
        
        if not chunks:
            yield "I couldn't find any relevant information in the indexed documents."
            return
        
        context = self._build_context(chunks)
        prompt = QA_PROMPT_TEMPLATE.format(context=context, question=question)
        
        for token in self.llm.generate_stream(prompt, system=SYSTEM_PROMPT):
            yield token
    
    def summarize_results(self, query: str, results: list[RetrievalResult]) -> str:
        """Summarize search results."""
        if not results:
            return "No results to summarize."
        
        context = self._build_context(results)
        prompt = SUMMARY_PROMPT_TEMPLATE.format(context=context)
        return self.llm.generate(prompt, system=SYSTEM_PROMPT)
    
    def _build_context(self, chunks: list[RetrievalResult], max_tokens: Optional[int] = None) -> str:
        """Build context string from chunks."""
        max_tokens = max_tokens or self.config.max_context_tokens
        
        context_parts = []
        total_tokens = 0
        
        for chunk in chunks:
            chunk_text = f"[Document: {chunk.filename}]\n{chunk.content}\n"
            chunk_tokens = len(chunk_text) // 4
            
            if total_tokens + chunk_tokens > max_tokens:
                break
            
            context_parts.append(chunk_text)
            total_tokens += chunk_tokens
        
        return "\n---\n".join(context_parts)
    
    def get_stats(self) -> dict:
        """Get RAG system statistics."""
        vector_stats = self.vector_store.get_stats()
        
        return {
            "vector_store": vector_stats,
            "llm_provider": self.config.llm_provider.value,
            "llm_available": self.llm.is_available,
            "embedding_provider": self.config.embedding_provider.value,
            "chunk_size": self.config.chunk_size,
            "hybrid_search": self.config.hybrid_search,
        }


def create_rag_engine() -> RAGEngine:
    """Create a new RAG engine instance."""
    return RAGEngine()
