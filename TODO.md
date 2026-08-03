# Technical TODO & Refactoring Roadmap

## Priority Technical Refactorings & Fixes

### 1. Remove Wildcard Star Imports (`from module import *`)
- [ ] Refactor [api/routes_projects.py](file:///g:/programming/infinite_reader/api/routes_projects.py), [api/routes_speech.py](file:///g:/programming/infinite_reader/api/routes_speech.py), and [api/routes_imggen.py](file:///g:/programming/infinite_reader/api/routes_imggen.py) to explicitly import required symbols instead of `from utils.utils import *` and `from utils.pydantic_models import *`.
- **Benefit:** Prevents accidental namespace pollution, eliminates `F403`/`F405` linter suppressions, improves IDE autocompletion and static analysis.

### 2. Remove Hardcoded Environment Paths
- [ ] Replace hardcoded Windows paths (e.g. `C:\Users\andrii\AppData\Local\ffmpeg\bin` in [main.py](file:///g:/programming/infinite_reader/main.py)) with environment variable reads (`FFMPEG_PATH`) or automatic `PATH` detection.
- **Benefit:** Enhances cross-platform portability across Windows, Linux, and macOS.

### 3. Object-Oriented Architecture (OOP) & Base Interfaces
- [ ] Abstract LLM providers ([utils/models.py](file:///g:/programming/infinite_reader/utils/models.py)) behind an explicit Abstract Base Class (`BaseLLMProvider` / `BaseTTSProvider`) with standard methods (`generate_json`, `generate_text`).
- [ ] Replace duck-typing with formal protocols or abstract base classes (`abc.ABC`).
- **Benefit:** Guarantees strict API contract enforcement across `OllamaModel`, `OpenRouterModel`, `GeminiModel`, and new model integrations.

### 4. Code Quality & DRY (Don't Repeat Yourself) Cleanups
- [ ] **Unified Context Building:** Deduplicate prompt context preparation functions (`_build_write_context` vs beat prompt builders) into a dedicated `ContextBuilder` domain class.
- [ ] **Unified Async State Locking:** Wrap project state reads/writes in `MemoryStore` with explicit file-locking or async mutex locks to prevent race conditions during rapid background requests.
- [ ] **Proper Type Annotations:** Replace raw `dict` payload parameters in API endpoints with strongly typed Pydantic request body models.

### 5. Asynchronous Job & Worker Queues
- [ ] Refactor long-running CPU/GPU blocking calls (TTS generation, Stable Diffusion image rendering) from generic `asyncio.to_thread` calls into a dedicated background worker queue (e.g., `asyncio.Queue` worker).
- **Benefit:** Prevents thread-pool exhaustion and allows task cancellation and progress reporting.
