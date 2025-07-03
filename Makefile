.PHONY: help default all clean build build-release lint fmt check-fmt \
	markdownlint tools nixie test

MDLINT ?= markdownlint
NIXIE ?= nixie

all: build check-fmt test typecheck

default: build

build: tools ## Build for test/typecheck
	uv venv
	uv sync --group dev

build-release: ## Build artefacts (sdist & wheel)
	python -m build --sdist --wheel

clean: ## Remove build artifacts
	rm -rf build dist *.egg-info \
	  .mypy_cache .pytest_cache .coverage coverage.* lcov.info htmlcov \
	  .venv
	find . -type d -name '__pycache__' -exec rm -rf '{}' +

define ensure_tool
$(if $(shell command -v $(1) >/dev/null 2>&1 && echo y),,\
$(error $(1) is required but not installed))
endef


tools: ## Verify required CLI tools
	$(foreach t,mdformat-all ruff ty $(MDLINT) $(NIXIE) pytest uv,$(call ensure_tool,$t))
	@:

fmt: tools ## Format sources
	ruff format
	mdformat-all

check-fmt: ## Verify formatting
	ruff format --check
	mdformat-all --check

lint: tools ## Run linters
	ruff check

typecheck: build ## Run typechecking
	ty check

markdownlint: tools ## Lint Markdown files
	find . -type f -name '*.md' -not -path './target/*' -print0 | xargs -0 $(MDLINT)

nixie: tools ## Validate Mermaid diagrams
	find . -type f -name '*.md' -not -path './target/*' -print0 | xargs -0 $(NIXIE)

test: build ## Run tests
	uv run pytest -v

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
