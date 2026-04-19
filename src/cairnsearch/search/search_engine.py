"""Main search engine combining all search components."""
import time
from typing import Optional
import logging

from cairnsearch.config import get_config
from cairnsearch.db import Database, SearchResult, SearchResponse
from .query_parser import parse_query, ParsedQuery
from .query_builder import QueryBuilder
from .snippets import SnippetGenerator, extract_query_terms


logger = logging.getLogger(__name__)


class SearchEngine:
    """Full-text search engine using SQLite FTS5."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.config = get_config()
        self.query_builder = QueryBuilder()
        self.snippet_generator = SnippetGenerator()

    def search(
        self,
        query: str,
        page: int = 1,
        page_size: Optional[int] = None,
    ) -> SearchResponse:
        """
        Search indexed documents.
        
        Args:
            query: Search query string
            page: Page number (1-indexed)
            page_size: Results per page
            
        Returns:
            SearchResponse with results and metadata
        """
        start_time = time.perf_counter()
        
        # Validate pagination
        if page_size is None:
            page_size = self.config.search.default_page_size
        page_size = min(page_size, self.config.search.max_page_size)
        page = max(1, page)
        offset = (page - 1) * page_size
        
        # Parse query
        parsed = parse_query(query)
        
        # Handle empty query
        if not parsed.has_fts_query and not parsed.file_type and not parsed.author:
            return self._empty_response(query, page, page_size, start_time)
        
        # Get total count
        total = self._get_count(parsed)
        
        # Get results
        results = self._get_results(parsed, query, offset, page_size)
        
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        return SearchResponse(
            query=query,
            total=total,
            page=page,
            page_size=page_size,
            took_ms=round(elapsed_ms, 2),
            results=results,
        )

    def _get_count(self, parsed: ParsedQuery) -> int:
        """Get total result count."""
        sql, params = self.query_builder.build_count(parsed)
        try:
            rows = self.db.execute(sql, tuple(params))
            return rows[0][0] if rows else 0
        except Exception as e:
            logger.error(f"Count query failed: {e}")
            return 0

    def _get_results(
        self,
        parsed: ParsedQuery,
        original_query: str,
        offset: int,
        limit: int,
    ) -> list[SearchResult]:
        """Get search results with snippets."""
        sql, params = self.query_builder.build(parsed)
        sql += f" LIMIT {limit} OFFSET {offset}"
        
        try:
            rows = self.db.execute(sql, tuple(params))
        except Exception as e:
            logger.error(f"Search query failed: {e}")
            return []
        
        # Extract query terms for highlighting
        query_terms = extract_query_terms(original_query)
        
        results = []
        for row in rows:
            # Generate snippets
            content = row["content"] or ""
            snippets = self.snippet_generator.generate(content, query_terms)
            
            result = SearchResult(
                id=row["id"],
                file_path=row["file_path"],
                filename=row["filename"],
                file_type=row["file_type"],
                score=abs(row["score"]),  # BM25 returns negative scores
                snippets=snippets,
                doc_title=row["doc_title"],
                doc_author=row["doc_author"],
                doc_created=row["doc_created"],
                page_count=row["page_count"],
            )
            results.append(result)
        
        return results

    def _empty_response(
        self,
        query: str,
        page: int,
        page_size: int,
        start_time: float,
    ) -> SearchResponse:
        """Return empty response for invalid queries."""
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return SearchResponse(
            query=query,
            total=0,
            page=page,
            page_size=page_size,
            took_ms=round(elapsed_ms, 2),
            results=[],
        )

    def get_document(self, doc_id: int) -> Optional[dict]:
        """Get full document by ID."""
        rows = self.db.execute(
            "SELECT * FROM documents WHERE id = ?",
            (doc_id,)
        )
        if not rows:
            return None
        
        row = rows[0]
        return {
            "id": row["id"],
            "file_path": row["file_path"],
            "filename": row["filename"],
            "file_type": row["file_type"],
            "content": row["content"],
            "page_count": row["page_count"],
            "doc_title": row["doc_title"],
            "doc_author": row["doc_author"],
            "doc_created": row["doc_created"],
            "doc_modified": row["doc_modified"],
            "detected_dates": row["detected_dates"],
            "extraction_method": row["extraction_method"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def suggest(self, prefix: str, limit: int = 10) -> list[str]:
        """Get search suggestions based on prefix."""
        # Simple prefix search on filenames
        rows = self.db.execute(
            """SELECT DISTINCT filename FROM documents 
               WHERE filename LIKE ? 
               ORDER BY filename 
               LIMIT ?""",
            (f"{prefix}%", limit)
        )
        return [row["filename"] for row in rows]
