-- cairnsearch SQLite Schema
-- Enable WAL mode for concurrent reads during writes
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- File tracking for change detection
CREATE TABLE IF NOT EXISTS files_meta (
    path TEXT PRIMARY KEY,
    hash TEXT NOT NULL,              -- SHA-256 of file
    content_hash TEXT,               -- SHA-256 of extracted content
    size_bytes INTEGER NOT NULL,
    file_mtime REAL NOT NULL,        -- Unix timestamp
    indexed_at TEXT,                 -- ISO 8601
    status TEXT DEFAULT 'pending',   -- pending, indexed, failed, quarantined
    error_msg TEXT,
    needs_ocr BOOLEAN DEFAULT FALSE,
    version INTEGER DEFAULT 1,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TEXT
);

-- Extracted document content and metadata
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE REFERENCES files_meta(path) ON DELETE CASCADE,
    filename TEXT NOT NULL,          -- Just the filename for searching
    file_type TEXT NOT NULL,         -- pdf, docx, txt, etc.
    content TEXT,                    -- Full extracted text
    page_count INTEGER,
    doc_title TEXT,
    doc_author TEXT,
    doc_created TEXT,                -- From document metadata
    doc_modified TEXT,
    detected_dates TEXT,             -- JSON array of dates found in content
    extraction_method TEXT,          -- direct, ocr, hybrid
    extraction_metadata TEXT,        -- JSON: OCR confidence, tables, forms, etc.
    pii_detected BOOLEAN DEFAULT FALSE,
    pii_tags TEXT,                   -- JSON array of PII types found
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Page-level information for PDFs
CREATE TABLE IF NOT EXISTS document_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_num INTEGER NOT NULL,
    page_type TEXT,                  -- digital, scanned, mixed
    content TEXT,
    ocr_confidence REAL,
    ocr_data TEXT,                   -- JSON: word boxes, reading order
    has_tables BOOLEAN DEFAULT FALSE,
    has_forms BOOLEAN DEFAULT FALSE,
    tables_data TEXT,                -- JSON array of tables
    form_fields TEXT,                -- JSON array of form fields
    UNIQUE(doc_id, page_num)
);

-- FTS5 virtual table for full-text search with BM25 ranking
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    filename,
    content,
    content='documents',
    content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 1'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, filename, content)
    VALUES (new.id, new.filename, new.content);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, filename, content)
    VALUES ('delete', old.id, old.filename, old.content);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, filename, content)
    VALUES ('delete', old.id, old.filename, old.content);
    INSERT INTO documents_fts(rowid, filename, content)
    VALUES (new.id, new.filename, new.content);
END;

-- Job queue for async processing
CREATE TABLE IF NOT EXISTS job_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    job_type TEXT NOT NULL,          -- index, reindex, delete, ocr_only
    priority INTEGER DEFAULT 0,      -- Higher = more urgent
    status TEXT DEFAULT 'pending',   -- pending, processing, done, failed
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    error_msg TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT
);

-- Enhanced chunk storage with metadata
CREATE TABLE IF NOT EXISTS document_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT UNIQUE NOT NULL,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_type TEXT DEFAULT 'text',  -- text, table, form_field, ocr
    page_num INTEGER,
    section TEXT,
    ocr_confidence REAL,
    is_ocr BOOLEAN DEFAULT FALSE,
    table_id TEXT,
    sheet_name TEXT,
    row_numbers TEXT,                -- JSON array
    start_char INTEGER,
    end_char INTEGER,
    token_count INTEGER,
    metadata TEXT,                   -- JSON
    content_hash TEXT,               -- For deduplication
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_files_meta_status ON files_meta(status);
CREATE INDEX IF NOT EXISTS idx_files_meta_hash ON files_meta(hash);
CREATE INDEX IF NOT EXISTS idx_documents_file_type ON documents(file_type);
CREATE INDEX IF NOT EXISTS idx_documents_doc_created ON documents(doc_created);
CREATE INDEX IF NOT EXISTS idx_job_queue_status_priority ON job_queue(status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON document_chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_pages_doc_id ON document_pages(doc_id);
