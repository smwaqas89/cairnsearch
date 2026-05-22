# Response to Reviewer Comments — cairnsearch v1.1.0

The paper *"cairnsearch: A privacy-first hybrid search and local RAG system for
personal document collections"* was accepted for publication in SoftwareX
(DOI: 10.1016/j.softx.2026.102742). The reviewer comments were advisory
improvements to the software. The published paper is unchanged; the following
changes were made to the **repository** and released as **v1.1.0**.

This document records, point by point, how each comment was addressed.

---

## Reviewer #1

### 1. Metadata specification & extraction mapping
> *Display a data schema (JSON) and the mapping from raw extraction (OCR
> bounding boxes) into the index, to prove relationships in complex tables are
> not lost.*

**Addressed.** Added [`docs/SCHEMA.md`](docs/SCHEMA.md), which documents:
- the full chunk JSON schema (`ChunkMetadata`), with a worked example;
- the OCR bounding-box → chunk mapping (reading-order grouping, chunk
  assignment, bounding-box union, confidence propagation);
- table-structure preservation (detection, header–separator–row flattening,
  row-atomic chunking, `table_id` linkage so tables can be reassembled);
- the three index targets (FTS5, vector store, metadata) and the dedup step.

### 2. Installation accessibility for non-IT users
> *A single pip install is too technical for lawyers/clinicians/journalists;
> provide a standalone executable (e.g. PyInstaller) or a one-click installer
> that automates setup and launches Ollama in the background.*

**Addressed.** Added one-click installers `install.sh` (macOS/Linux) and
`install.bat` (Windows). Each one:
- checks for Python 3.11+ and creates an isolated virtual environment;
- installs cairnsearch and its dependencies;
- detects Ollama and, if it is not already running, **launches `ollama serve`
  in the background** (detached), waits for the API to come up, then pulls the
  default models (`llama3.1:8b`, `nomic-embed-text`);
- offers to start the cairnsearch server and **opens the web UI in the default
  browser automatically**, so the user finishes on a working application
  without typing further commands.

The README lists this as the easiest install path.

**On the standalone executable (PyInstaller):** we deliberately chose the
one-click script over a bundled binary. cairnsearch depends on native libraries
(Tesseract for OCR, PyMuPDF for PDF parsing) that are awkward and
platform-specific to bundle, and — more importantly — it relies on a separate
Ollama installation (a multi-GB local LLM server) that cannot be packaged into a
PyInstaller executable. A single binary would therefore still require a separate
Ollama install and could not deliver a genuinely self-contained experience. The
background-launching installer achieves the reviewer's actual goal — removing
command-line friction for non-technical users — more reliably and on every
platform.

### 3. Interface visibility & user journey
> *Add a user-journey map and UI screenshots showing the LLM answer side by
> side with citation highlighting.*

**Partially addressed.** The README install/quick-start flow documents the
end-to-end user journey (install → index a folder → search → ask). UI
screenshots are recommended for the repository README and can be added without
a code change; this is noted as a follow-up. (The published paper's figure
budget is fixed.)

### Additional — Resource fallback (OOM handling)
> *Informative error handling if the local LLM runs out of memory, rather than
> a silent crash.*

**Addressed.** The Ollama provider now detects out-of-memory, model-not-found,
connection, and timeout conditions and raises clear, actionable errors
(`LLMResourceError`, `LLMUnavailableError`, `LLMTimeoutError`), e.g.
"the model ran out of memory — try a smaller model such as llama3.2:1b."

### Additional — Security isolation (sandboxing)
> *Add an extractor sandboxing layer to limit the impact of malicious
> PDF/Office documents.*

**Addressed.** The extractor subprocess runner now applies POSIX resource
limits (`RLIMIT_AS` memory cap, `RLIMIT_CPU` CPU-time cap, `RLIMIT_CORE` 0) and
runs with a stripped environment that withholds API keys and other secrets,
in addition to the existing crash isolation.

---

## Reviewer #2

### Abstract should mention limitations
**Not changed (paper is published/frozen).** The published Limitations section
already covers the qualitative-only evaluation and static fusion weights; this
is noted for any future extended version.

### Explicit objective sentence in §1
**Not changed (paper frozen).** Noted for a future revision.

### Fusion weights described informally ("I had tested…")
**Not changed in paper (frozen).** The repository documents that the 0.7/0.3
weights are heuristic defaults from informal tuning and exposes them as
configuration so users can run their own evaluation without editing code.

### Chunk-size default logic not explained
**Addressed (repo).** README now explains the 500-token / 50-token-overlap
default (granularity vs. coherence trade-off) and that tables are chunked on
row boundaries; full detail in `docs/SCHEMA.md`.

### PII detection precision/recall not discussed
**Addressed (repo).** README now states the PII detector is a recall-oriented
safety net (regex + heuristics), not a high-precision classifier, with explicit
caveats about false positives/negatives and unsuitability as a sole compliance
control.

### Std devs missing for indexing rows; single-hardware eval; no CIs
**Not changed in paper (frozen).** The paper's Table 2 caption already notes
indexing phases are single cold-start runs, and the Limitations section flags
the qualitative, single-machine nature of the benchmark. Noted for future work
(the planned BEIR-style evaluation harness).

### No retrieval-quality evaluation (P@k, NDCG)
**Acknowledged.** Already stated as the primary planned next step (BEIR-style
harness plus a curated private-document benchmark) in the published Limitations.

### Cross-encoder reranker model not named/cited
**Addressed (repo).** Clarified honestly that the default reranker is a **local
LLM-based (listwise) reranker** (it prompts the Ollama model to score
relevance), not a separate cross-encoder model — which is why no cross-encoder
model is downloaded or cited. Documented how to substitute a true cross-encoder
(e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`) via `BaseReranker`. See
`src/cairnsearch/rag/reranker.py` and the README "Reranking" note.

---

## Beyond the reviews — research-integrity alignment

The paper states the system makes **no external network calls** and that
"nothing leaves the machine." A `strict_local` mode (default **on**) was added
to guarantee this at runtime: cloud providers are refused before any request is
sent, across the LLM factory, embedder factory, `/api/rag/test-connection`, and
`/api/rag/config`. Users can opt in to cloud providers by setting
`strict_local = false`. This ensures the released code matches the published
privacy claim by default.

A startup `RuntimeWarning` (double-import of `cli.main`) was also fixed.

---

## Summary of repository changes (v1.0.0 → v1.1.0)

| Area | Change |
|---|---|
| Privacy | `strict_local` mode, default on; cloud providers blocked unless opted in |
| Reliability | Actionable OOM/connection/timeout errors for the local LLM |
| Security | Subprocess resource limits + stripped environment for extractors |
| Docs | `docs/SCHEMA.md`; README notes on privacy, reranker, chunking, PII |
| UX | `install.sh` / `install.bat` one-click installers |
| Fix | CLI double-import `RuntimeWarning` resolved |

No breaking changes. All changes are backward compatible with v1.0.0
configurations (the new `strict_local` flag defaults to the safe, paper-aligned
behaviour).
