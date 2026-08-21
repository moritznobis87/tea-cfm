#!/usr/bin/env python3
"""
Den aktuellen Stand in die Nebenrepositories spiegeln.

Derselbe Quellcode liegt in mehreren Repositories, aber NICHT dieselben
Projektdaten:

    tea-cfm         alles - das Produktivrepository. Dorthin wird normal
                    gepusht, dieses Skript fasst es nicht an.
    valyze          nur die Vorlagen. Testrepository; echte Projektdaten
                    haben dort nichts verloren.
    trendscouting   die Vorlagen und die oesterreichischen Projekte.

Ein blosser Push naehme ueberallhin alles mit. Dieses Skript baut
deshalb je Ziel einen eigenen Commit obendrauf, in dem die dort nicht
gewuenschten Dateien fehlen, und schiebt DEN.

Warum nach dem Inhalt und nicht nach dem Dateinamen
---------------------------------------------------
Der Dateiname ist die Projekt-ID, und die wird EINMAL bei der Anlage
vergeben und bleibt danach stehen - auch wenn das Projekt umbenannt wird
(siehe app/services.py::make_project_id). Der Dateiname sagt damit
nichts darueber, was in der Datei steht.

Im Bestand war das kein Sonderfall, sondern der Regelfall:

    template-agri-kopie.yaml            enthaelt  OÖ_Buchkirchen_Silber
    template-konventionell-kopie.yaml   enthaelt  NÖ_Ternitz_LivingBricx
    ooe-buchkirchen-silber-kopie.yaml   enthaelt  STMK_Lödersdorf_Wagner

Ein Filter ueber die Dateinamen haette zwei echte Projekte unter
vorlagenaehnlichen Namen nach valyze durchgelassen.

Die Richtung des Zweifels
-------------------------
Aufgenommen wird nur, was ausdruecklich passt; alles Uebrige faellt weg.
Eine Vorlage, die der Regel nicht folgt, verschwindet damit aus dem
Testrepository und laesst dort Tests scheitern - laut und behebbar. Ein
echtes Projekt dagegen kann nicht versehentlich mitwandern. Von den
beiden moeglichen Fehlern ist das der harmlose.

Aufruf
------
    python scripts/spiegeln.py                  # zeigt nur, was passieren wuerde
    python scripts/spiegeln.py --push           # spiegelt in alle Ziele
    python scripts/spiegeln.py --push valyze    # nur in eines

Was dieses Skript NICHT tut: Es raeumt die VERGANGENHEIT nicht auf.
Frueher gespiegelte Staende enthalten die damals mitgeschobenen Dateien
weiterhin, und ein `git log` foerdert sie zutage. Wer sie dort auch
historisch los sein will, braucht eine neu geschriebene Historie - ein
eigener, zerstoerender Schritt, der bewusst nicht hier steht.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


def _streamlit_leise() -> None:
    """Streamlit zum Schweigen bringen, BEVOR die App-Module laden.

    Die Laenderpruefung greift auf die Maske zu und zieht damit
    Streamlit herein. Ausserhalb eines laufenden Servers schreibt es je
    Cache-Dekorator eine Warnung - ein Dutzend Zeilen, die den Bericht
    dieses Skripts zerreissen. Die Reihenfolge ist der Kniff: Streamlit
    richtet seine Logger beim Import ein, ein vorher gesetzter Pegel
    waere wieder ueberschrieben.
    """
    from streamlit import logger as st_logger

    # Ueber Streamlits eigene Schnittstelle und nicht ueber
    # logging.getLogger("streamlit"): Streamlit legt seine Logger erst
    # bei der ersten Benutzung an und traegt dabei den bei IHM
    # hinterlegten Pegel ein - ein von aussen gesetzter waere gleich
    # wieder ueberschrieben.
    st_logger.set_log_level("error")


WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

PROJEKTE = WURZEL / "data" / "projects"

#: Ein Projekt gilt als Vorlage, wenn sein NAME so beginnt.
VORLAGENPRAEFIX = "Template"

#: Zielzweig in den Nebenrepositories.
ZIELZWEIG = "main"
#: Zwischenzweig fuer den Spiegel-Commit. Er lebt nur waehrend des Laufs.
ARBEITSZWEIG = "spiegel-arbeit"


def _git(*args: str, pruefen: bool = True) -> str:
    fertig = subprocess.run(
        ["git", "-C", str(WURZEL), *args],
        capture_output=True, text=True, check=pruefen,
    )
    return fertig.stdout.strip()


def _laden(pfad: Path) -> dict:
    try:
        return yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def ist_vorlage(daten: dict) -> bool:
    return str(daten.get("name", "")).startswith(VORLAGENPRAEFIX)


def land(daten: dict) -> str | None:
    """Das Laenderpaket, das dieses Projekt tatsaechlich rechnet.

    Ausgewertet wird mit derselben Funktion, die auch der Laenderschalter
    der Maske benutzt: Abweichung, wo sie gesetzt ist, sonst die globale
    Vorgabe. Eine zweite Herleitung waere eine zweite Wahrheit - und
    ausgerechnet hier entscheidet sie darueber, welche Daten ein
    Repository verlassen.

    Rueckgabe "Österreich", "Deutschland" oder None fuer eine gemischte
    Zusammenstellung (die vier Felder bleiben einzeln aenderbar).
    """
    _streamlit_leise()
    from app.components.project_form import _geltendes_land
    from engine.io_yaml import load_global_assumptions_yaml
    from engine.models import Projektannahmen

    global_assumptions = load_global_assumptions_yaml(
        WURZEL / "data" / "global_assumptions.yaml"
    )
    annahmen = Projektannahmen.model_validate(daten.get("annahmen") or {})
    return _geltendes_land(global_assumptions, annahmen.model_dump())


def nur_vorlagen(daten: dict) -> bool:
    return ist_vorlage(daten)


def vorlagen_und_oesterreich(daten: dict) -> bool:
    """Vorlagen bleiben mit drin.

    Sie sind keine Kundendaten, sondern Teil der Anwendung - und die
    Testsuite braucht sie: Ein gutes Dutzend Tests oeffnet
    `template-agri`. Ohne sie waere das Repository zwar sauber, aber
    seine Suite rot.
    """
    return ist_vorlage(daten) or land(daten) == "Österreich"


#: Repository -> (Beschreibung, Aufnahmeregel).
ZIELE: dict[str, tuple[str, object]] = {
    "valyze": ("nur die Vorlagen", nur_vorlagen),
    "trendscouting": (
        "Vorlagen und oesterreichische Projekte", vorlagen_und_oesterreich
    ),
}


def einteilen(regel) -> tuple[list[Path], list[Path]]:
    """(aufnehmen, weglassen) - beide nach Dateinamen sortiert."""
    drin, raus = [], []
    for pfad in sorted(PROJEKTE.glob("*.yaml")):
        (drin if regel(_laden(pfad)) else raus).append(pfad)
    return drin, raus


def bericht(ziel: str, drin: list[Path], raus: list[Path]) -> None:
    beschreibung = ZIELE[ziel][0]
    print(f"\n=== {ziel} ({beschreibung}) ===")
    print(f"  aufnehmen: {len(drin)}")
    for pfad in drin:
        daten = _laden(pfad)
        print(f"    + {pfad.name:52} {daten.get('name', '?')}")
    print(f"  weglassen: {len(raus)}")
    for pfad in raus:
        daten = _laden(pfad)
        herkunft = "Vorlage" if ist_vorlage(daten) else (land(daten) or "gemischt")
        print(f"    - {pfad.name:52} {daten.get('name', '?')}  [{herkunft}]")


def spiegeln(ziel: str, raus: list[Path]) -> None:
    """Baut den Spiegel-Commit und schiebt ihn ins Zielrepository."""
    zweig = _git("rev-parse", "--abbrev-ref", "HEAD")
    _git("checkout", "-B", ARBEITSZWEIG)
    try:
        if raus:
            _git("rm", "--quiet", *[str(p.relative_to(WURZEL)) for p in raus])
            _git(
                "commit", "--quiet", "-m",
                f"Projektdaten fuer {ziel} filtern\n\n"
                f"Automatisch erzeugt von scripts/spiegeln.py: "
                f"{ZIELE[ziel][0]}.\n"
                f"{len(raus)} Projektdateien sind hier nicht enthalten; sie "
                f"fuehrt\nausschliesslich tea-cfm.",
            )
        _git("push", ziel, f"{ARBEITSZWEIG}:{ZIELZWEIG}", "--force")
        print(f"  -> nach {ziel}/{ZIELZWEIG} gespiegelt "
              f"({len(raus)} Dateien nicht enthalten).")
    finally:
        # Der Arbeitszweig darf nicht stehenbleiben: Sein Commit gehoert
        # nicht in die Entwicklungslinie, und ein spaeterer Merge zoege
        # die Loeschung nach tea-cfm.
        _git("checkout", "--quiet", zweig)
        _git("branch", "-D", ARBEITSZWEIG, pruefen=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--push", action="store_true",
                        help="wirklich spiegeln (sonst nur Bericht)")
    parser.add_argument("ziele", nargs="*", choices=[*ZIELE, []],
                        help="einzelne Ziele; ohne Angabe alle")
    args = parser.parse_args()
    ziele = args.ziele or list(ZIELE)

    if args.push and _git("status", "--porcelain"):
        sys.exit("Arbeitsverzeichnis ist nicht sauber - erst committen.")

    plan = {}
    for ziel in ziele:
        drin, raus = einteilen(ZIELE[ziel][1])
        bericht(ziel, drin, raus)
        if not drin:
            sys.exit(
                f"\n{ziel} bekaeme kein einziges Projekt - seine Tests "
                f"scheiterten. Abbruch."
            )
        plan[ziel] = raus

    if not args.push:
        print("\nNur Bericht. Mit --push wird tatsaechlich gespiegelt.")
        return
    print()
    for ziel, raus in plan.items():
        spiegeln(ziel, raus)


if __name__ == "__main__":
    main()
