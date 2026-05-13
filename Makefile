.PHONY: install test clean

install:
	uv sync --dev

test:
	uv run pytest

clean:
	rm -rf __pycache__ .pytest_cache
	find . -depth -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
