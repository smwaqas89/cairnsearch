# cairnsearch - Troubleshooting Guide

## Database Location

```
~/.local/share/cairnsearch/cairnsearch.db      # Main SQLite database (documents, FTS)
~/.local/share/cairnsearch/vectors/vectors.db # Vector store (embeddings)
```

## Quick Diagnostic Queries

### Check Document Count
```bash
sqlite3 ~/.local/share/cairnsearch/cairnsearch.db "SELECT COUNT(*) as total FROM documents;"
```

### Check Chunks Count (RAG)
```bash
sqlite3 ~/.local/share/cairnsearch/vectors/vectors.db "SELECT COUNT(*) as total_chunks FROM chunks;"
```

### List All Indexed Documents
```bash
sqlite3 -header -column ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT id, filename, file_type, page_count, extraction_method, created_at 
 FROM documents ORDER BY created_at DESC LIMIT 20;"
```

### Check Indexing Status by File Type
```bash
sqlite3 -header -column ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT file_type, COUNT(*) as count FROM documents GROUP BY file_type;"
```

### List Failed Files
```bash
sqlite3 -header -column ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT path, status, error_msg, indexed_at 
 FROM files_meta WHERE status = 'failed';"
```

### List Pending Files
```bash
sqlite3 -header -column ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT path, status, indexed_at 
 FROM files_meta WHERE status = 'pending';"
```

### Check Document Content (first 200 chars)
```bash
sqlite3 ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT filename, substr(content, 1, 200) as preview 
 FROM documents WHERE id = 1;"
```

### Search Documents by Filename
```bash
sqlite3 -header -column ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT id, filename, file_type FROM documents WHERE filename LIKE '%passport%';"
```

### Full-Text Search Test
```bash
sqlite3 -header -column ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT id, filename, snippet(documents, 3, '<mark>', '</mark>', '...', 20) 
 FROM documents WHERE documents MATCH 'education' LIMIT 5;"
```

### Check Vector Store Stats
```bash
sqlite3 -header -column ~/.local/share/cairnsearch/vectors/vectors.db \
"SELECT doc_id, filename, COUNT(*) as chunks 
 FROM chunks GROUP BY doc_id ORDER BY chunks DESC LIMIT 10;"
```

### Documents Without Chunks (RAG won't work for these)
```bash
sqlite3 ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT d.id, d.filename FROM documents d 
 WHERE d.id NOT IN (SELECT DISTINCT doc_id FROM chunks);" 
```
Note: Run this against vectors.db for the subquery.

### Check Content Length
```bash
sqlite3 -header -column ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT filename, length(content) as chars 
 FROM documents ORDER BY chars ASC LIMIT 10;"
```

## API Health Checks

### Server Status
```bash
curl http://localhost:8080/api/status | python -m json.tool
```

### RAG Status
```bash
curl http://localhost:8080/api/rag/status | python -m json.tool
```

### Ollama Status
```bash
curl http://localhost:11434/api/tags | python -m json.tool
```

### Test Search API
```bash
curl "http://localhost:8080/api/search?q=test" | python -m json.tool
```

### Test RAG API
```bash
curl -X POST http://localhost:8080/api/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What documents do you have?"}' | python -m json.tool
```

## Common Issues

### Issue: "No chunks created for document X"

**Cause**: Document has no extractable text or text is too short.

**Diagnose**:
```bash
# Check if document has content
sqlite3 ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT id, filename, length(content) as chars FROM documents WHERE id = X;"
```

**Solutions**:
1. If `chars = 0`: Document is likely scanned/image-based. Install Tesseract:
   ```bash
   brew install tesseract
   ```
2. If `chars < 20`: Content too short, chunker skips it (this is expected).

### Issue: "Extraction failed" for PDFs

**Diagnose**:
```bash
# Check the error
sqlite3 ~/.local/share/cairnsearch/cairnsearch.db \
"SELECT path, error_msg FROM files_meta WHERE path LIKE '%.pdf' AND status = 'failed';"
```

**Solutions**:
1. Corrupted PDF: Try opening in Preview/Adobe
2. Password protected: Remove password protection
3. Scanned PDF: Install Tesseract OCR

### Issue: "sentence-transformers not available"

**Cause**: Using Ollama embeddings instead (this is fine if intentional).

**Fix** (if you want local embeddings):
```bash
pip install sentence-transformers
```

### Issue: Segmentation Fault

**Cause**: Library conflicts (usually torch/sentence-transformers with macOS).

**Solution**: Use pure Ollama setup:
```bash
pip uninstall sentence-transformers torch -y
# Configure to use Ollama for embeddings (default in latest version)
```

### Issue: Port 8080 Already in Use

```bash
# Find process
lsof -i :8080

# Kill it
kill -9 $(lsof -t -i:8080)

# Or use different port
./run.sh serve --port 8081
```

### Issue: Ollama Not Responding

```bash
# Check if running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# Pull required models
ollama pull nomic-embed-text
ollama pull llama3.1:8b
```

### Issue: Clear Index Not Working

**Diagnose**:
```bash
# Check document count after clear
sqlite3 ~/.local/share/cairnsearch/cairnsearch.db "SELECT COUNT(*) FROM documents;"

# If still > 0, manually clear
sqlite3 ~/.local/share/cairnsearch/cairnsearch.db "DELETE FROM documents; DELETE FROM files_meta;"
sqlite3 ~/.local/share/cairnsearch/vectors/vectors.db "DELETE FROM chunks;"
```

**Nuclear option** - delete everything:
```bash
rm -rf ~/.local/share/cairnsearch
```

## Log Locations

- Server logs: Terminal where `./run.sh serve` is running
- Enable debug logs: Add `log_level = "DEBUG"` to config.toml

## Configuration File

Create `~/.config/cairnsearch/config.toml`:
```toml
[general]
data_dir = "~/.local/share/cairnsearch"
log_level = "INFO"

[indexer]
workers = 3
max_file_size_mb = 500

[rag]
enabled = true
embedding_provider = "ollama"
reranker_enabled = true
ollama_base_url = "http://localhost:11434"
ollama_model = "llama3.1:8b"
```

## Reset Everything

```bash
# Stop server (Ctrl+C)

# Delete all data
rm -rf ~/.local/share/cairnsearch

# Restart
./run.sh serve
```

## Performance Tips

1. **Slow indexing**: Reduce `workers` in config if CPU is overloaded
2. **Slow RAG**: Use smaller Ollama model (`llama3.2:3b` instead of `llama3.1:8b`)
3. **High memory**: Reduce `max_file_size_mb` to skip large files
4. **Slow search**: The FTS5 index should be fast; if slow, check if SQLite is on SSD
