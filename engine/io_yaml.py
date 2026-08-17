"""
Minimale YAML-Loader/-Writer fuer PVProject und GlobalAssumptions.

Bewusst KEIN Repository-Pattern - das kommt, wenn ein Wechsel auf eine
Datenbank tatsaechlich ansteht. Dies ist der einzige Ort, der Datei-IO
macht.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import GlobalAssumptions, PVProject


def load_project_yaml(path: str | Path) -> PVProject:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return PVProject.model_validate(raw)


def save_project_yaml(project: PVProject, path: str | Path) -> None:
    daten = project.model_dump(mode="json")
    # Abweichungen: nur schreiben, was gesetzt ist. Ungefiltert stuenden
    # rund dreissig `null`-Zeilen in jeder Datei und verdeckten die
    # wenigen, auf die es ankommt - und `null` liesse sich beim Lesen
    # nicht von einer bewussten Eingabe unterscheiden (siehe
    # engine/models.py::Projektannahmen).
    daten["annahmen"] = {
        feld: wert for feld, wert in daten.get("annahmen", {}).items()
        if wert is not None and wert != {}
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(daten, f, allow_unicode=True, sort_keys=False)


def load_global_assumptions_yaml(path: str | Path) -> GlobalAssumptions:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return GlobalAssumptions.model_validate(raw)


def save_global_assumptions_yaml(
    assumptions: GlobalAssumptions, path: str | Path
) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            assumptions.model_dump(mode="json"),
            f,
            allow_unicode=True,
            sort_keys=False,
        )
