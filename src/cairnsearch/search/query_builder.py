"""Build SQLite FTS5 queries from parsed queries."""
from typing import Optional

from .query_parser import ParsedQuery


class QueryBuilder:
    """Build SQL queries from parsed search queries."""

    def build(self, parsed: ParsedQuery) -> tuple[str, list]:
        """
        Build SQL query from parsed query.
        
        Returns:
            Tuple of (SQL query string, parameters list)
        """
        params = []
        conditions = []
        
        # Base query - join documents with FTS
        base_sql = """
            SELECT 
                d.id,
                d.file_path,
                d.filename,
                d.file_type,
                d.content,
                d.doc_title,
                d.doc_author,
                d.doc_created,
                d.page_count,
                d.detected_dates,
                bm25(documents_fts) as score
            FROM documents d
            JOIN documents_fts fts ON d.id = fts.rowid
        """
        
        # FTS5 MATCH condition
        if parsed.has_fts_query:
            conditions.append("documents_fts MATCH ?")
            params.append(parsed.fts_query)
        
        # File type filter
        if parsed.file_type:
            conditions.append("d.file_type = ?")
            params.append(parsed.file_type)
        
        # Author filter
        if parsed.author:
            conditions.append("d.doc_author LIKE ?")
            params.append(f"%{parsed.author}%")
        
        # Date filters
        if parsed.after_date:
            conditions.append("(d.doc_created >= ? OR d.detected_dates LIKE ?)")
            params.append(parsed.after_date)
            params.append(f'%"{parsed.after_date[:4]}%')  # Match year in detected dates
        
        if parsed.before_date:
            conditions.append("(d.doc_created <= ? OR d.doc_created IS NULL)")
            params.append(parsed.before_date)
        
        if parsed.year:
            year_start = f"{parsed.year}-01-01"
            year_end = f"{parsed.year}-12-31"
            conditions.append("""
                (d.doc_created BETWEEN ? AND ? 
                 OR d.detected_dates LIKE ?)
            """)
            params.append(year_start)
            params.append(year_end)
            params.append(f'%"{parsed.year}%')
        
        # Build WHERE clause
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
        else:
            where_clause = ""
        
        # Order by relevance score (BM25 returns negative, more negative = better match)
        order_clause = " ORDER BY score ASC"
        
        sql = base_sql + where_clause + order_clause
        return sql, params

    def build_count(self, parsed: ParsedQuery) -> tuple[str, list]:
        """Build count query for pagination."""
        params = []
        conditions = []
        
        base_sql = """
            SELECT COUNT(*)
            FROM documents d
            JOIN documents_fts fts ON d.id = fts.rowid
        """
        
        if parsed.has_fts_query:
            conditions.append("documents_fts MATCH ?")
            params.append(parsed.fts_query)
        
        if parsed.file_type:
            conditions.append("d.file_type = ?")
            params.append(parsed.file_type)
        
        if parsed.author:
            conditions.append("d.doc_author LIKE ?")
            params.append(f"%{parsed.author}%")
        
        if parsed.after_date:
            conditions.append("(d.doc_created >= ? OR d.detected_dates LIKE ?)")
            params.append(parsed.after_date)
            params.append(f'%"{parsed.after_date[:4]}%')
        
        if parsed.before_date:
            conditions.append("(d.doc_created <= ? OR d.doc_created IS NULL)")
            params.append(parsed.before_date)
        
        if parsed.year:
            year_start = f"{parsed.year}-01-01"
            year_end = f"{parsed.year}-12-31"
            conditions.append("""
                (d.doc_created BETWEEN ? AND ? 
                 OR d.detected_dates LIKE ?)
            """)
            params.append(year_start)
            params.append(year_end)
            params.append(f'%"{parsed.year}%')
        
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
        else:
            where_clause = ""
        
        sql = base_sql + where_clause
        return sql, params
