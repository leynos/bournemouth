# Conditional Testing for Optional Dependencies

This document explains how to make tests conditional on optional dependency groups being installed.

## Problem

The project has optional dependency groups (like `cli`) defined in `pyproject.toml`:

```toml
[dependency-groups]
cli = [
  "typer>=0.12",
  "textual>=0.51",
]
```

Tests for CLI functionality should only run when these dependencies are installed, but should be skipped gracefully when they're not available.

## Solution 1: Using pytest.importorskip (Recommended)

This is the cleanest approach for skipping entire test modules:

```python
from __future__ import annotations

import pytest

# Skip all tests in this module if CLI dependencies are not available
pytest.importorskip("typer", reason="CLI dependency group not installed")
pytest.importorskip("textual", reason="CLI dependency group not installed")

from bournemouth import cli

# Rest of your tests...
```

**Pros:**
- Clean and simple
- Skips the entire module if dependencies are missing
- Clear error messages
- Fails fast during test collection

**Cons:**
- All-or-nothing approach (entire module is skipped)

## Solution 2: Using pytest.mark.skipif with try/except

For more granular control over individual tests:

```python
from __future__ import annotations

import pytest

# Check if CLI dependencies are available
try:
    import typer
    import textual
    CLI_AVAILABLE = True
except ImportError:
    CLI_AVAILABLE = False

@pytest.mark.skipif(not CLI_AVAILABLE, reason="CLI dependencies not installed")
def test_cli_functionality():
    # Your CLI test here
    pass
```

**Pros:**
- Can skip individual tests or test classes
- More flexible than module-level skipping
- Can mix CLI and non-CLI tests in the same module

**Cons:**
- More verbose
- Need to remember to add the decorator to each test

## Solution 3: Using pytest fixtures

For complex dependency checking:

```python
import pytest

@pytest.fixture(scope="session")
def cli_dependencies():
    """Fixture that ensures CLI dependencies are available."""
    pytest.importorskip("typer")
    pytest.importorskip("textual")
    return True

def test_cli_functionality(cli_dependencies):
    # This test will be skipped if CLI dependencies are missing
    pass
```

## Solution 4: Custom pytest markers

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "cli: marks tests as requiring CLI dependencies",
]
```

Then in your test file:

```python
import pytest

@pytest.mark.cli
def test_cli_functionality():
    pytest.importorskip("typer")
    pytest.importorskip("textual")
    # Your test here
```

Run only CLI tests: `pytest -m cli`
Skip CLI tests: `pytest -m "not cli"`

## Running Tests

### With CLI dependencies:
```bash
uv run --group cli python -m pytest src/bournemouth/unittests/test_cli.py -v
```

### Without CLI dependencies:
```bash
uv run --no-group cli python -m pytest src/bournemouth/unittests/test_cli.py -v
```

### Skip CLI tests entirely:
```bash
uv run python -m pytest -m "not cli"
```

## Best Practices

1. **Use `pytest.importorskip`** for module-level skipping when the entire test file depends on optional dependencies
2. **Use `pytest.mark.skipif`** for individual test functions when you have mixed dependencies in one file
3. **Provide clear skip reasons** to help developers understand why tests were skipped
4. **Document the dependency groups** and how to install them
5. **Consider CI/CD implications** - you may want separate test jobs for different dependency combinations

## Example CI Configuration

```yaml
# .github/workflows/test.yml
jobs:
  test-core:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: uv sync
      - run: uv run pytest tests/ -m "not cli"
  
  test-cli:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: uv sync --group cli
      - run: uv run pytest tests/ -m cli
```

This ensures both core functionality and CLI functionality are tested, but in separate jobs with appropriate dependencies.
