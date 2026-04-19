# Contributing to cairnsearch

Thank you for your interest in contributing to cairnsearch! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites

- Python 3.11+
- Tesseract OCR (optional, for image/scanned PDF support)
- Ollama (optional, for local AI features)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/smwaqas89/cairnsearch.git
cd cairnsearch

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Initialize database
cairnsearch init
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=cairnsearch

# Run specific test file
pytest tests/test_search.py
```

### Code Style

We use `ruff` for linting and formatting:

```bash
# Format code
ruff format src/

# Check for issues
ruff check src/

# Fix auto-fixable issues
ruff check --fix src/
```

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/smwaqas89/cairnsearch/issues)
2. If not, create a new issue with:
   - Clear, descriptive title
   - Steps to reproduce
   - Expected vs actual behavior
   - System info (OS, Python version, etc.)
   - Error messages/logs if applicable

### Suggesting Features

1. Check existing issues and discussions
2. Create a new issue with:
   - Clear description of the feature
   - Use case / motivation
   - Proposed implementation (optional)

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Add tests if applicable
5. Run linting: `ruff check src/`
6. Run tests: `pytest`
7. Commit with clear message: `git commit -m "Add feature: description"`
8. Push to your fork: `git push origin feature/my-feature`
9. Open a Pull Request

### Commit Messages

Follow conventional commits:

- `feat: add new feature`
- `fix: resolve bug`
- `docs: update documentation`
- `refactor: improve code structure`
- `test: add tests`
- `chore: maintenance tasks`

## Project Structure

```
cairnsearch/
├── src/cairnsearch/
│   ├── api/           # FastAPI routes
│   ├── cli/           # Command-line interface
│   ├── db/            # Database models and connection
│   ├── extractors/    # File content extractors
│   ├── indexer/       # Document indexing
│   ├── queue/         # Job queue for async processing
│   ├── rag/           # AI/RAG components
│   ├── search/        # Search engine
│   └── watcher/       # Folder watching
└── ui/                # Web interface
```

## Areas for Contribution

- **Extractors**: Add support for new file types
- **Search**: Improve query parsing, ranking algorithms
- **RAG**: Enhance AI responses, add new features
- **UI**: Improve web interface
- **Documentation**: Fix typos, add examples, improve clarity
- **Tests**: Increase test coverage
- **Performance**: Optimize indexing, search speed

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Keep discussions on-topic

## Questions?

Feel free to open an issue or discussion for any questions!
