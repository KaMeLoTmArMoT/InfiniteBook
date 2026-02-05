from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Flux2KleinT2IParams:
    prompt: str
    negative: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg: float = 5.0
    seed: int = 0
    filename_prefix: str = "Flux2-Klein"


@dataclass(frozen=True)
class Flux2KleinT2IDistilledParams:
    prompt: str
    width: int = 1024
    height: int = 1024
    seed: int = 0
    filename_prefix: str = "Flux2-Klein"
    steps: int = 4
    cfg: float = 1.0


@dataclass(frozen=True)
class Flux2KleinT2IDistilledGGUFParams:
    prompt: str
    width: int = 768
    height: int = 1152
    seed: int = 0
    filename_prefix: str = "Flux2-Klein"
    steps: int = 4
    cfg: float = 1.0


def load_template(templates_dir: str, name: str) -> dict[str, Any]:
    p = Path(templates_dir) / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def build_flux2_klein_t2i(
    template: dict[str, Any], p: Flux2KleinT2IParams
) -> dict[str, Any]:
    g = json.loads(json.dumps(template))  # cheap deep copy

    g["76"]["inputs"]["value"] = p.prompt
    g["75:67"]["inputs"]["text"] = p.negative

    g["75:68"]["inputs"]["value"] = int(p.width)
    g["75:69"]["inputs"]["value"] = int(p.height)

    g["75:62"]["inputs"]["steps"] = int(p.steps)
    g["75:63"]["inputs"]["cfg"] = float(p.cfg)
    g["75:73"]["inputs"]["noise_seed"] = int(p.seed)

    g["9"]["inputs"]["filename_prefix"] = p.filename_prefix
    return g


def build_flux2_klein_t2i_distilled(
    template: dict[str, Any], p: Flux2KleinT2IDistilledParams
) -> dict[str, Any]:
    g = json.loads(json.dumps(template))

    g["76"]["inputs"]["value"] = p.prompt

    g["77:68"]["inputs"]["value"] = int(p.width)
    g["77:69"]["inputs"]["value"] = int(p.height)

    g["77:62"]["inputs"]["steps"] = int(p.steps)
    g["77:63"]["inputs"]["cfg"] = float(p.cfg)
    g["77:73"]["inputs"]["noise_seed"] = int(p.seed)

    g["78"]["inputs"]["filename_prefix"] = p.filename_prefix
    return g


def build_flux2_klein_t2i_distilled_gguf(
    template: dict[str, Any], p: Flux2KleinT2IDistilledGGUFParams
) -> dict[str, Any]:
    g = json.loads(json.dumps(template))

    g["76"]["inputs"]["value"] = p.prompt

    g["77:68"]["inputs"]["value"] = int(p.width)
    g["77:69"]["inputs"]["value"] = int(p.height)

    g["77:62"]["inputs"]["steps"] = int(p.steps)
    g["77:63"]["inputs"]["cfg"] = float(p.cfg)

    g["77:73"]["inputs"]["noise_seed"] = int(p.seed)

    g["78"]["inputs"]["filename_prefix"] = p.filename_prefix
    return g


DEFAULT_STYLE_PROMPT = (
    "Futuristic Berlin, cyberpunk noir thriller mood. Rainy night, neon reflections on wet asphalt, "
    "dirty alley + street-level view near a language school entrance, holographic ads in German, "
    "grime, cables, steam, puddles, cigarette smoke, synthetic drug vibe. High-contrast noir lighting, "
    "deep shadows, cyan/magenta neon glow, slight fog, flash-like highlights, early 2000s digital camera "
    "aesthetic, subtle noise and chromatic aberration. Cinematic composition, believable realism, "
    "documentary candid feel, not glossy, not clean."
)
DEFAULT_STYLE_ANCHOR = "Same visual style as the provided style reference image: cyberpunk noir, rainy neon Berlin, early 2000s digicam flash, slight noise, high contrast, cyan/magenta neon, gritty documentary realism."
DEFAULT_SCENE_BLOCK = "Full body shot, standing on a rainy urban street near a language school, wet pavement reflections, tense atmosphere, candid moment, looking over her shoulder."
DEFAULT_CHARACTER_ANCHOR = "Akusa Ivanova, Eastern European refugee woman, vibrant auburn hair tied in a high ponytail, small scar on the chin, slim athletic build, tired determined eyes. Wears a tactical emerald green techwear jumpsuit, heavy black combat boots. A thin silver chain necklace (she touches it when nervous)."


@dataclass(frozen=True)
class CharacterFromStyleParams:
    style_anchor: str = ""
    scene_block: str = ""
    character_anchor: str = ""
    style_image: str = ""  # filename in Comfy input/
    width: int = 768
    height: int = 1152
    steps: int = 4
    cfg: float = 1.0
    seed: int = 0
    filename_prefix: str = "HERO-BASE"


def build_flux2_klein_character_style_ref_gguf(
    template: dict[str, Any], p: CharacterFromStyleParams
) -> dict[str, Any]:
    g = json.loads(json.dumps(template))

    sa = (p.style_anchor or "").strip() or DEFAULT_STYLE_ANCHOR
    sb = (p.scene_block or "").strip() or DEFAULT_SCENE_BLOCK
    ca = (p.character_anchor or "").strip() or DEFAULT_CHARACTER_ANCHOR

    # text inputs
    g["1"]["inputs"]["value"] = sa
    g["6"]["inputs"]["value"] = sb
    g["3"]["inputs"]["value"] = ca

    # style image (must exist in Comfy input/)
    if p.style_image.strip():
        g["8"]["inputs"]["image"] = p.style_image.strip()

    # size
    g["9:89"]["inputs"]["value"] = int(p.width)
    g["9:90"]["inputs"]["value"] = int(p.height)

    # steps/cfg/seed
    g["9:62"]["inputs"]["steps"] = int(p.steps)
    g["9:63"]["inputs"]["cfg"] = float(p.cfg)
    g["9:73"]["inputs"]["noise_seed"] = int(p.seed)

    # prefix
    g["10"]["inputs"]["filename_prefix"] = p.filename_prefix

    return g
