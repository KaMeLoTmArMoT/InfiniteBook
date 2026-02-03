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


def build_flux2_klein_t2i(template: dict[str, Any], p: Flux2KleinT2IParams) -> dict[str, Any]:
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


def build_flux2_klein_t2i_distilled(template: dict[str, Any], p: Flux2KleinT2IDistilledParams) -> dict[str, Any]:
    g = json.loads(json.dumps(template))

    g["76"]["inputs"]["value"] = p.prompt

    g["77:68"]["inputs"]["value"] = int(p.width)
    g["77:69"]["inputs"]["value"] = int(p.height)

    g["77:62"]["inputs"]["steps"] = int(p.steps)
    g["77:63"]["inputs"]["cfg"] = float(p.cfg)
    g["77:73"]["inputs"]["noise_seed"] = int(p.seed)

    g["78"]["inputs"]["filename_prefix"] = p.filename_prefix
    return g


def build_flux2_klein_t2i_distilled_gguf(template: dict[str, Any], p: Flux2KleinT2IDistilledGGUFParams) -> dict[
    str, Any]:
    g = json.loads(json.dumps(template))

    g["76"]["inputs"]["value"] = p.prompt

    g["77:68"]["inputs"]["value"] = int(p.width)
    g["77:69"]["inputs"]["value"] = int(p.height)

    g["77:62"]["inputs"]["steps"] = int(p.steps)
    g["77:63"]["inputs"]["cfg"] = float(p.cfg)

    g["77:73"]["inputs"]["noise_seed"] = int(p.seed)

    g["78"]["inputs"]["filename_prefix"] = p.filename_prefix
    return g
