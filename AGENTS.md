# Agent Guidelines & Project Overview

## Project Architecture
- **Application:** Infinite Book Architect (FastAPI backend + Vanilla JS/HTML/CSS frontend).
- **Python Version:** 3.13 (`requires-python = ">=3.13,<3.14"` in `pyproject.toml`).
- **Package & Environment Tooling:** `uv` (use `uv sync`, `uv add`, `uv run`).
- **Code Quality:** `ruff` (pinned to `0.16.1`, configured in `pyproject.toml`).

## Development Workflow
- **Dependencies:** Add or update dependencies using `uv add` or `uv add --dev`.
- **Linting & Formatting (Python):**
  - Run lint check & fix: `uv run ruff check --fix`
  - Run formatting: `uv run ruff format`
- **Linting & Formatting (Frontend templates):**
  - Run lint & format check: `npx @biomejs/biome@2.5.14 check templates/`
  - Run format in-place: `npx @biomejs/biome@2.5.14 format --write templates/`
- **Testing:**
  - Run test suite: `uv run pytest`
- **Running Locally:** `uv run python main.py`
