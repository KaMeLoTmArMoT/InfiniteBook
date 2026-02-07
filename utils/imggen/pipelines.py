# utils/imggen/pipelines.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.prompts import (
    DEFAULT_CHARACTER_ANCHOR,
    DEFAULT_SCENE_BLOCK,
    DEFAULT_STYLE_ANCHOR,
)
from utils.pydantic_models import (
    CharacterFromStyleParams,
    Flux2KleinT2IDistilledGGUFParams,
    Flux2KleinT2IDistilledParams,
    Flux2KleinT2IParams,
    SceneFromStyleAndCharParams,
)


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


def build_flux2_klein_scene_dual_ref_gguf(
    template: dict[str, Any], p: SceneFromStyleAndCharParams
) -> dict[str, Any]:
    g = json.loads(json.dumps(template))

    sa = (p.style_anchor or "").strip() or DEFAULT_STYLE_ANCHOR
    sb = (p.scene_block or "").strip() or DEFAULT_SCENE_BLOCK
    ca = (p.character_anchor or "").strip() or DEFAULT_CHARACTER_ANCHOR

    # Text inputs
    # 1: STYLE_ANCHOR
    # 6: SCENE_BLOCK
    # 3: CHARACTER_ANCHOR
    g["1"]["inputs"]["value"] = sa
    g["6"]["inputs"]["value"] = sb
    g["3"]["inputs"]["value"] = ca

    # Style Image (Node 8 у твоєму прикладі)
    if p.style_image.strip():
        g["8"]["inputs"]["image"] = p.style_image.strip()

    # Character Image (Node 12 у твоєму прикладі)
    if p.char_image.strip():
        g["12"]["inputs"]["image"] = p.char_image.strip()

    # Size (Node 9:89, 9:90)
    g["9:89"]["inputs"]["value"] = int(p.width)
    g["9:90"]["inputs"]["value"] = int(p.height)

    # Steps/CFG/Seed (Node 9:62, 9:63, 9:73)
    g["9:62"]["inputs"]["steps"] = int(p.steps)
    g["9:63"]["inputs"]["cfg"] = float(p.cfg)
    g["9:73"]["inputs"]["noise_seed"] = int(p.seed)

    # Prefix (Node 10)
    g["10"]["inputs"]["filename_prefix"] = p.filename_prefix

    return g
