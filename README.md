<div align="center">
  <h3 align="center">Infinite Book Architect</h3>

  <p align="center">
    A local-first, single-page app that turns an idea into a full chapter-by-chapter novel.
    <br />
    Idea → Plot → Characters → Chapter Beats → Beat Prose, with local Ollama or cloud OpenRouter models.
    <br /><br />
    <a href="#"><strong>View Demo »</strong></a>
    ·
    <a href="../../issues">Report Bug</a>
    ·
    <a href="../../issues">Request Feature</a>
  </p>
</div>

## About The Project

Infinite Book Architect is a FastAPI + vanilla JS app for generating a complete story pipeline: pick an idea, generate a plot outline, build a cast, plan beats per chapter, and write beat prose.  
It supports multiple LLM providers behind a small gateway (local Ollama by default, OpenRouter for free cloud models).

<p align="center">
  <img src="assets/main.png" width="720" alt="Main UI">
</p>

### Key Features

- End-to-end writing pipeline (Idea → Plot → Characters → Beats → Prose).
- Chapter navigation (plan and write per chapter).
- Beat-level writing controls: write, rewrite, clear, clear-from, generate-all.
- Multi-provider LLM routing (local Ollama + cloud OpenRouter).
- Strict JSON structured outputs (schema validation + retries).
- Live system monitor widget (providers, Ollama status, GPU, VRAM, RAM).

### Built With

- Python + FastAPI
- Vanilla JavaScript + HTML + CSS
- Ollama (local LLM runtime)
- OpenRouter (cloud LLM gateway)

## Getting Started

### Prerequisites

- Python 3.11+ (recommended)
- Ollama installed and running (for local mode)
- Optional: OpenRouter API key (for cloud mode)

### Installation

1. Clone the repo:
   ```bash
   git clone https://github.com/<YOU>/<YOUR_REPO>.git
   cd <YOUR_REPO>
   ```

2. Create venv + install deps:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```

3. Run:
   ```bash
   python main.py
   ```

4. Open:
   - http://127.0.0.1:8000/

### Configuration (.env)

Create `.env` in the project root:

```env
# Provider selection
IB_LLM_PROVIDER=openrouter          # or "ollama"

# Ollama (local)
IB_MODEL_NAME=gemma3:12b

# OpenRouter (cloud)
IB_OPENROUTER_API=https://openrouter.ai
IB_OPENROUTER_API_KEY=XXX
IB_OPENROUTER_PRIMARY_MODEL=meta-llama/llama-3.3-70b-instruct:free
IB_OPENROUTER_FALLBACK_MODEL=openai/gpt-oss-120b:free
```

Notes:
- Free models can be blocked by OpenRouter privacy/data-policy settings; if you get a “No endpoints found matching your data policy” error, check your OpenRouter privacy settings.

## Usage

1. Step 1: Enter genre/idea and refine variations.
2. Step 2: Generate the plot (chapter outline).
3. Step 3: Generate characters.
4. Step 4: Generate beats for the current chapter (use Prev/Next Chapter).
5. Step 5: Write beat prose (Write Next / Generate All).

<p align="center">
  <img src="assets/beats.png" width="720" alt="Chapter Beats + Write UI">
</p>

## Roadmap

- Image generation for chapter/beat thumbnails (consistent character + style refs).
- TTS narration (short-form “TikTok friendly” outputs).
- Better memory/continuity tools (per-chapter capsule, global timeline).
- Export formats (Markdown/EPUB/PDF).

See the [open issues](https://github.com/KaMeLoTmArMoT/InfiniteBook/issues).

## Contributing

Contributions are welcome:
1. Fork the repo
2. Create a feature branch
3. Open a PR

For bug reports, please include:
- OS + GPU
- Provider (Ollama/OpenRouter) + model name
- Steps to reproduce
- Relevant logs

## License

This project is licensed under the MIT License — see [`LICENSE`](https://github.com/KaMeLoTmArMoT/InfiniteBook/blob/main/LICENSE).

## Acknowledgments

- README structure inspired by Best-README-Template.
- Built with assistance from generative AI tools for ideation and code suggestions; all changes were reviewed and tested by the author.