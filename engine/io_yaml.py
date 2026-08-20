"""
Minimale YAML-Loader/-Writer fuer PVProject und GlobalAssumptions.

Bewusst KEIN Repository-Pattern - das kommt, wenn ein Wechsel auf eine
Datenbank tatsaechlich ansteht. Dies ist der einzige Ort, der Datei-IO
macht.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .models import GlobalAssumptions, PVProject


def _schreibe_yaml(daten: Any, path: str | Path) -> None:
    """YAML schreiben, ohne die alte Fassung preiszugeben.

    Ein `open(path, "w")` kappt die Datei sofort auf null Byte und fuellt
    sie erst danach. In dieser Spanne - bei den globalen Annahmen rund
    500 kB, also keine Mikrosekunde - sieht jeder Leser eine leere oder
    halbe Datei. Bricht der Schreibvorgang darin ab, bleibt sie so.

    Das ist kein theoretischer Fall: Waehrend eines Testlaufs las ein
    parallel laufender Streamlit-Server genau diesen Zwischenzustand.

    Geschrieben wird deshalb in eine Nachbardatei und dann umbenannt.
    `os.replace` ist auf einem Dateisystem atomar: Ein Leser sieht
    entweder vollstaendig die alte oder vollstaendig die neue Fassung,
    nie etwas dazwischen. Das Verzeichnis muss dasselbe sein - ueber
    Dateisystemgrenzen hinweg waere es ein Kopieren und damit wieder
    nicht atomar.

    Das `fsync` davor stellt sicher, dass der Inhalt auf Platte steht,
    bevor der Name auf ihn zeigt - sonst koennte ein Stromausfall einen
    gueltigen Namen mit leerem Inhalt hinterlassen.
    """
    ziel = Path(path)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, vorlaeufig = tempfile.mkstemp(
        dir=ziel.parent, prefix=f".{ziel.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(daten, f, allow_unicode=True, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(vorlaeufig, ziel)
    except BaseException:
        Path(vorlaeufig).unlink(missing_ok=True)
        raise


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
    # Aus demselben Grund fallen leere Optionalfelder ganz weg: Ein
    # `lastgang_datei: null` in siebzehn Dateien sagt nichts, verlaengert
    # aber jeden Diff. Was fehlt, ist nicht gesetzt - das Modell setzt
    # beim Laden denselben Standard.
    for feld in ("annahmen", "lastgang_datei"):
        if not daten.get(feld):
            daten.pop(feld, None)
    _schreibe_yaml(daten, path)


def load_global_assumptions_yaml(path: str | Path) -> GlobalAssumptions:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return GlobalAssumptions.model_validate(raw)


def save_global_assumptions_yaml(
    assumptions: GlobalAssumptions, path: str | Path
) -> None:
    _schreibe_yaml(assumptions.model_dump(mode="json"), path)
