"""
Minimaler YAML-Loader fuer ein einzelnes PVProject.

Bewusst KEIN Repository-Pattern in Phase 1 - das kommt gemaess Roadmap
erst, wenn mehrere Projekte + Persistenzwechsel (Datei -> Datenbank)
tatsaechlich anstehen. Diese Funktion ist der einzige Ort, der heute
Datei-IO macht; sie zu einem Repository auszubauen ist dann eine lokale
Aenderung.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import PVProject


def load_project_yaml(path: str | Path) -> PVProject:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return PVProject.model_validate(raw)
