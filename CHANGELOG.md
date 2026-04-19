# Changelog

All notable changes to cairnsearch will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-19

First public release. This is the version described in the accompanying SoftwareX
paper.

### Search
- Full-text search backed by SQLite FTS5 with BM25 ranking
- Boolean queries (`AND`, `OR`, `NOT`) and parenthesised groups
- Phrase search (`"exact phrase match"`)
- Field search: `filename:`, `type:`, `author:`, `after:`, `before:`, `year:`
- Query sanitisation that tolerates the special characters users typically type

### Retrieval-augmented generation (RAG)
- Local embeddings via Ollama (default model: `nomic-embed-text`, 768 dimensions)
- NumPy-backed vector store with cosine similarity
- Hybrid retrieval combining BM25 and dense scores via weighted max-normalised
  fusion (default weights 0.7 dense / 0.3 lexical)
- Optional cross-encoder reranker for the top candidates
- Local LLM generation via Ollama (default model: `llama3.1:8b`)
- Grounded prompting with explicit document delimiters and citation-ready source
  chunks returned alongside each answer

### Document extraction
- PDF extraction via PyMuPDF, with per-page classification of digital / scanned /
  mixed pages
- OCR for scanned pages via Tesseract, with per-word bounding boxes and
  confidence propagated to chunks
- DOCX via python-docx; XLSX, XLS, CSV, TSV via openpyxl and stdlib
- HTML via BeautifulSoup, plain text and Markdown, images with OCR

### Processing pipeline
- Semantic chunker producing typed chunks (text, table, form field, OCR,
  heading, list, code)
- Text normalisation, table and form-field extraction
- Content-hash deduplication to drop near-identical boilerplate
- Async job queue decoupling ingestion from the user-facing path
- Filesystem watcher for incremental reindexing
- Atomic database commits and resumable progress for crash recovery
- Subprocess isolation for native extractors (PDF, OCR, images) so one
  document failure never takes down the system
- Quarantine system for failed documents with structured failure manifests
- Configurable guardrails on file size, page count, row count, chunk count,
  and token budgets

### Interfaces
- FastAPI REST service (`/api/search`, `/api/rag/ask`, `/api/status`, `/api/index`, …)
- Single-page web UI
- Typer-based command-line interface suitable for scripting
- OpenAPI documentation served automatically by FastAPI

### Privacy and safeguards
- 100% local: extraction, embeddings, retrieval, and generation all run on the
  host machine or against a local Ollama instance; no document content or
  queries leave the machine
- PII detector covering 12 classes (SSN, credit card, email, phone, address,
  date of birth, passport, driver's licence, bank account, IP, name, medical
  record) using regex and heuristics
- Optional AES-256 encryption at rest
- Audit logging of all document operations
- Structured JSON logs with `doc_id`, filename, stage, duration

### Observability
- Per-document metrics: time, chunks, tokens, errors
- System-health metrics: queue status, error rates, estimated costs
- Automatic alerting on repeated failures or chunk explosions

## [Unreleased]

### Planned
- Evaluation harness built on BEIR-style benchmarks plus a curated
  private-document benchmark
- PDF in-browser preview
- Document comparison
- Learned (rather than fixed) hybrid-fusion weights
- Additional AI features (summarisation, fact extraction)
