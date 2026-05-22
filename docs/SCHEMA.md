# cairnsearch — Data Schema and Extraction Mapping

This document describes the internal data schema cairnsearch uses for chunks
and how raw extraction output (including OCR bounding boxes and table
structure) is mapped into the searchable index. It is provided for
transparency and reproducibility, so that reviewers and users can verify that
relationships between entities — particularly inside complex tables — are
preserved rather than lost during chunking.

## 1. Chunk schema

Every indexed unit is a *typed chunk* with the following metadata
(`ChunkMetadata`, see `src/cairnsearch/core/models.py`). Serialised to JSON:

```json
{
  "chunk_id": "doc42_p3_c7",
  "doc_id": 42,
  "file_path": "/Users/vics/Contracts/Acme_MSA_2023.pdf",
  "filename": "Acme_MSA_2023.pdf",
  "page_num": 3,
  "section": "Payment Terms",
  "chunk_type": "table",
  "ocr_confidence": 0.97,
  "is_ocr": false,
  "table_id": "doc42_p3_t1",
  "row_numbers": [4, 5, 6],
  "sheet_name": null,
  "bounding_box": {
    "page": 3,
    "x0": 72.0, "y0": 540.5, "x1": 523.4, "y1": 612.8,
    "unit": "pdf_points"
  },
  "start_char": 1840,
  "end_char": 2304,
  "token_count": 118
}
```

Field semantics:

| Field | Meaning |
|---|---|
| `chunk_id` | Stable identifier `doc{id}_p{page}_c{index}` |
| `doc_id` | Foreign key to the `documents` table |
| `chunk_type` | One of `text`, `table`, `form_field`, `ocr`, `heading`, `list`, `code` |
| `is_ocr` / `ocr_confidence` | Whether the text came from OCR and its mean per-word confidence (0–1) |
| `table_id` | Groups all chunks that belong to the same source table |
| `row_numbers` / `sheet_name` | Spreadsheet provenance (Excel) |
| `bounding_box` | Region on the source page (PDF points, origin bottom-left) |
| `start_char` / `end_char` | Character offsets into the document's normalised text |
| `token_count` | Tokens in the chunk (used for context budgeting) |

## 2. OCR bounding-box → chunk mapping

For scanned pages, the Tesseract-backed extractor records, for every
recognised word, a bounding box and a confidence score:

```json
{
  "word": "net-30",
  "conf": 0.94,
  "bbox": {"x0": 210, "y0": 548, "x1": 268, "y1": 564}
}
```

The mapping into chunks proceeds as follows:

1. **Reading-order grouping.** Words are grouped into lines and blocks using
   Tesseract's layout output (block/paragraph/line indices), then ordered
   top-to-bottom, left-to-right.
2. **Chunk assignment.** Consecutive blocks are concatenated until the chunk
   reaches `chunk_size` tokens (default 500, with `chunk_overlap` 50). A chunk
   never crosses a detected table boundary (see below).
3. **Bounding-box union.** Each chunk's `bounding_box` is the union (min x0/y0,
   max x1/y1) of the boxes of the words it contains, so a chunk can be located
   on the page for citation highlighting.
4. **Confidence propagation.** `ocr_confidence` is the mean of the per-word
   confidences in the chunk. Downstream code can filter or down-weight
   low-confidence chunks (`OCRConfidence` thresholds: HIGH > 0.85,
   MEDIUM 0.60–0.85, LOW < 0.60).

## 3. Table structure preservation

To avoid losing row/column relationships when a table is split into chunks:

1. **Detection.** Tables are detected during extraction and assigned a
   `table_id`.
2. **Flattening.** Each table is serialised to a `header — separator — row`
   text layout, e.g.:

   ```
   Vendor | Term | Late Fee
   ------ | ---- | --------
   Acme   | net-30 | 1.5%/mo
   BetaCorp | net-45 | 1.5%/mo
   ```

   This keeps column headers adjacent to their values, so lexical (FTS5) search
   can match `Late Fee` against `1.5%`.
3. **Atomic chunking.** A table is chunked on row boundaries only; a single row
   is never split across two chunks. `row_numbers` records which source rows a
   chunk covers, so the original table region is recoverable.
4. **Linkage.** All chunks sharing a `table_id` can be re-assembled to
   reconstruct the full table.

## 4. Index targets

Each chunk is written to three stores (see the paper's Figure 1):

- **SQLite FTS5** — `content` + `filename` for BM25 lexical search.
- **Vector store (NumPy)** — a 768-d embedding of `content`
  (`nomic-embed-text` via Ollama by default).
- **SQLite metadata** — the full `ChunkMetadata` row above, enabling field
  filters (`type:`, `author:`, `after:`) and citation back to page/region.

## 5. Deduplication

Before indexing, a content-hash (SHA-256 over normalised chunk text) is used to
drop near-duplicate chunks such as repeated page headers, footers, and
boilerplate. This is exact/near-exact dedup; paraphrased duplicates are not
detected (a known limitation, noted in the paper).
