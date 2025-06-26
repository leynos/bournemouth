.PHONY: help all clean build release lint fmt check-fmt markdownlint \
	tools nixie test

MDLINT ?= markdownlint
NIXIE ?= nixie

all: release ## Build the release artifact

build release: ## Build artefacts (sdist & wheel)
	python -m build --sdist --wheel

clean: ## Remove build artifacts
	rm -rf build dist *.egg-info \
	.mypy_cache .pytest_cache .coverage coverage.* htmlcov \
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

lint: ## Run linters
	ruff check
	ty check

markdownlint: ## Lint Markdown files
	$(call ensure_tool,$(MDLINT))
	find . -type f -name '*.md' -not -path './target/*' -print0 | xargs -0 $(MDLINT)

nixie: ## Validate Mermaid diagrams
	$(call ensure_tool,$(NIXIE))
	find . -type f -name '*.md' -not -path './target/*' -print0 | xargs -0 $(NIXIE)

test: tools ## Run tests
	uv run pytest -v

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
