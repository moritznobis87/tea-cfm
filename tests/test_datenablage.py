"""
Wie die Anwendung ihre Daten ablegt - und was sie dabei nicht zerstoert.

Anlass ist ein echter Schaden: Ein Testlauf hatte die Baseloadreihe des
meistgenutzten Marktpreisszenarios durch drei synthetische Werte ersetzt
(8,0 / 9,0 / 10,0 ct/kWh), und dieser Zustand ging mit dem naechsten
Commit ins Repository. Zwei Ursachen wirkten zusammen:

1. Die Tests schrieben in dieselbe Datei, aus der das Tool liest. Eine
   Sicherungsfixture schrieb sie zwar zurueck - aber nur bei geordnetem
   Ende. Ein harter Abbruch liess den Testzustand stehen.
2. `save_global_assumptions_yaml` kappte die Zieldatei vor dem Schreiben.
   Wer waehrenddessen las, sah eine halbe Datei.

Dieses Modul haelt beide Riegel fest. Der dritte Abschnitt prueft die
ausgelieferten Daten selbst - er haette den Schaden bemerkt.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.config import DATA_DIR, GLOBAL_ASSUMPTIONS_PATH, ROOT_DIR
from engine.io_yaml import load_global_assumptions_yaml, save_global_assumptions_yaml

#: Die ausgelieferten Daten IM REPOSITORY - bewusst nicht die Kopie, auf
#: der die Tests arbeiten. Geprueft wird hier, was committet wird.
_AUSGELIEFERT = ROOT_DIR / "data" / "global_assumptions.yaml"


@pytest.fixture(scope="module")
def ausgeliefert() -> dict:
    return yaml.safe_load(_AUSGELIEFERT.read_text(encoding="utf-8"))


class TestUmlenkung:
    """Kein Test darf die ausgelieferten Daten anfassen koennen."""

    def test_datenverzeichnis_liegt_ausserhalb_des_repositorys(self):
        assert DATA_DIR != ROOT_DIR / "data", (
            "Die Tests zeigen auf die ausgelieferten Daten - ein "
            "schreibender Test wuerde sie veraendern"
        )
        assert ROOT_DIR not in DATA_DIR.parents

    def test_die_kopie_ist_vollstaendig(self):
        """Eine halbe Kopie waere schlimmer als keine: Die Tests liefen
        dann gegen Daten, die es so nie gab."""
        original = {p.relative_to(ROOT_DIR / "data")
                    for p in (ROOT_DIR / "data").rglob("*") if p.is_file()}
        kopie = {p.relative_to(DATA_DIR) for p in DATA_DIR.rglob("*") if p.is_file()}
        assert original <= kopie

    def test_schreiben_laesst_die_ausgelieferte_datei_unberuehrt(self):
        vorher = _AUSGELIEFERT.read_bytes()
        ga = load_global_assumptions_yaml(GLOBAL_ASSUMPTIONS_PATH)
        ga.kosten_inflation_pct_pa = 0.99
        save_global_assumptions_yaml(ga, GLOBAL_ASSUMPTIONS_PATH)
        try:
            assert _AUSGELIEFERT.read_bytes() == vorher
            # ... und in der Kopie ist der Wert wirklich angekommen.
            assert load_global_assumptions_yaml(
                GLOBAL_ASSUMPTIONS_PATH
            ).kosten_inflation_pct_pa == pytest.approx(0.99)
        finally:
            GLOBAL_ASSUMPTIONS_PATH.write_bytes(vorher)


class TestAtomaresSchreiben:
    def test_fehler_beim_schreiben_laesst_die_alte_fassung_stehen(
        self, tmp_path, global_assumptions, monkeypatch
    ):
        """Der eigentliche Zweck: Ein Abbruch mittendrin darf keine
        halbe Datei hinterlassen."""
        ziel = tmp_path / "ga.yaml"
        save_global_assumptions_yaml(global_assumptions, ziel)
        alt = ziel.read_bytes()
        assert alt

        def platzt(daten, strom, **kwargs):
            strom.write("marktpreisszenarien:\n  - name: halb")
            raise OSError("Platte voll")

        monkeypatch.setattr("engine.io_yaml.yaml.safe_dump", platzt)
        with pytest.raises(OSError):
            save_global_assumptions_yaml(global_assumptions, ziel)

        assert ziel.read_bytes() == alt
        # Und die Datei ist weiterhin ladbar - nicht nur byteweise gleich.
        assert load_global_assumptions_yaml(ziel).gueltig_ab == "test"

    def test_kein_bruchstueck_bleibt_liegen(
        self, tmp_path, global_assumptions, monkeypatch
    ):
        """Die Zwischendatei muss verschwinden - sonst waechst neben den
        Daten mit jedem Fehlschlag ein Rest."""
        ziel = tmp_path / "ga.yaml"

        def platzt(daten, strom, **kwargs):
            raise OSError("Platte voll")

        monkeypatch.setattr("engine.io_yaml.yaml.safe_dump", platzt)
        with pytest.raises(OSError):
            save_global_assumptions_yaml(global_assumptions, ziel)
        assert list(tmp_path.iterdir()) == []

    def test_erfolg_hinterlaesst_nur_die_zieldatei(
        self, tmp_path, global_assumptions
    ):
        ziel = tmp_path / "ga.yaml"
        save_global_assumptions_yaml(global_assumptions, ziel)
        save_global_assumptions_yaml(global_assumptions, ziel)
        assert [p.name for p in tmp_path.iterdir()] == ["ga.yaml"]

    def test_projektdateien_werden_genauso_geschrieben(self, tmp_path, project):
        """Der Riegel gilt fuer beide Speicherwege - Projektdateien sind
        nicht weniger schuetzenswert."""
        from engine.io_yaml import load_project_yaml, save_project_yaml

        ziel = tmp_path / "p.yaml"
        save_project_yaml(project, ziel)
        alt = ziel.read_bytes()
        with pytest.MonkeyPatch.context() as mp:
            def platzt(daten, strom, **kwargs):
                raise OSError("Platte voll")

            mp.setattr("engine.io_yaml.yaml.safe_dump", platzt)
            with pytest.raises(OSError):
                save_project_yaml(project, ziel)
        assert ziel.read_bytes() == alt
        assert load_project_yaml(ziel).id == project.id
        assert [p.name for p in tmp_path.iterdir()] == ["p.yaml"]


class TestAusgelieferteMarktdaten:
    """Der Waechter, der beim Schaden gefehlt hat.

    Geprueft werden Eigenschaften, die aus der Herkunft der Daten folgen -
    nicht einzelne Zahlen. Einzelne Zahlen muessten bei jedem neuen
    Aurora-Jahrgang mitgepflegt werden und waeren nach dem zweiten Mal
    veraltet.
    """

    def _szenarien(self, daten) -> dict[str, dict]:
        return {s["name"]: s for s in daten["marktpreisszenarien"]}

    def test_jede_hinterlegte_baseloadreihe_deckt_die_laufzeit_ab(
        self, ausgeliefert
    ):
        """Eine Reihe mit drei Jahren ist kein Szenario, sondern ein
        Ueberbleibsel. Genau so sah der Schaden aus."""
        for name, szenario in self._szenarien(ausgeliefert).items():
            reihe = szenario.get("baseload_ct_kwh_je_kalenderjahr") or {}
            if not reihe:
                continue  # Aeltere Jahrgaenge fuehren keinen Baseload.
            assert len(reihe) >= 30, (
                f"{name}: nur {len(reihe)} Baseloadjahre - eine "
                f"vollstaendige Reihe hat gut 35"
            )

    def test_monatskurve_passt_zur_jahresreihe(self, ausgeliefert):
        """Die Monatskurve darf hinter der Jahresreihe zurueckbleiben -
        manche Jahrgaenge liefern das Randjahr nur als Jahreswert -, aber
        sie darf keine Jahre fuehren, die es nicht gibt, und nicht auf
        eine Handvoll zusammenschrumpfen.
        """
        for name, szenario in self._szenarien(ausgeliefert).items():
            jahre = szenario.get("baseload_ct_kwh_je_kalenderjahr") or {}
            monate = szenario.get("baseload_ct_kwh_je_monat") or {}
            if not jahre:
                continue
            assert set(monate) <= set(jahre), (
                f"{name}: Monatskurve fuehrt Jahre ohne Jahreswert "
                f"({sorted(set(monate) - set(jahre))})"
            )
            assert len(monate) >= len(jahre) - 1, (
                f"{name}: nur {len(monate)} Monatsjahre bei "
                f"{len(jahre)} Jahreswerten"
            )
            for jahr, werte in monate.items():
                assert len(werte) == 12, f"{name}/{jahr}: {len(werte)} Monate"

    def test_pult_und_tracker_tragen_denselben_baseload(self, ausgeliefert):
        """Der Grosshandelspreis ist eine Eigenschaft des Marktes, nicht
        der Modulaufstaenderung. Weichen die beiden Bauformen eines
        Jahrgangs voneinander ab, ist eine der Reihen beschaedigt.

        Diese Probe haette den Schaden gefunden: Sie ist der Grund, aus
        dem sich die wiederhergestellten Werte belegen liessen.
        """
        szenarien = self._szenarien(ausgeliefert)
        for name, szenario in szenarien.items():
            if "Pult" not in name:
                continue
            partner = szenarien.get(name.replace("Pult", "Tracker"))
            if partner is None:
                continue
            assert (
                szenario.get("baseload_ct_kwh_je_kalenderjahr")
                == partner.get("baseload_ct_kwh_je_kalenderjahr")
            ), f"{name}: Baseload weicht von der Trackervariante ab"
            assert (
                szenario.get("baseload_ct_kwh_je_monat")
                == partner.get("baseload_ct_kwh_je_monat")
            ), f"{name}: Monatskurve weicht von der Trackervariante ab"

    def test_keine_glatten_platzhalter_im_baseload(self, ausgeliefert):
        """Echte Marktdaten sind krumm. Eine Reihe aus lauter ganzen
        Zahlen kommt aus einer Testfixture, nicht aus einem Modell."""
        for name, szenario in self._szenarien(ausgeliefert).items():
            reihe = (szenario.get("baseload_ct_kwh_je_kalenderjahr") or {}).values()
            if len(reihe) < 3:
                continue
            assert not all(float(w).is_integer() for w in reihe), (
                f"{name}: lauter glatte Baseloadwerte - sieht nach "
                f"Testdaten aus"
            )

    def test_alle_projekte_verweisen_auf_ein_vorhandenes_szenario(self):
        """Haette der Schaden ein Szenario ganz entfernt statt es zu
        leeren, muesste das hier auffallen.

        Im Projekt steht der Name OHNE Bauform ("Aurora Q3/26 ·
        Central"); die Bauform waehlt daraus die Kurve. Aufgeloest wird
        deshalb mit derselben Funktion, die auch die Auswahlliste der
        Oberflaeche fuellt - eine eigene Namenszerlegung im Test waere
        eine zweite Wahrheit ueber das Namensschema.
        """
        from engine.io_aurora import szenario_auswahl

        ga = load_global_assumptions_yaml(_AUSGELIEFERT)
        waehlbar = set(szenario_auswahl(ga))
        for datei in sorted((ROOT_DIR / "data" / "projects").glob("*.yaml")):
            projekt = yaml.safe_load(datei.read_text(encoding="utf-8"))
            gewaehlt = projekt.get("marktpreisszenario")
            if not gewaehlt:
                continue
            assert gewaehlt in waehlbar, (
                f"{datei.name}: Szenario '{gewaehlt}' ist nicht waehlbar"
            )


def test_pfad_der_ausgelieferten_daten_stimmt():
    """Wenn die Datei umzieht, sollen die Waechter oben nicht still
    nichts mehr pruefen."""
    assert _AUSGELIEFERT.exists()
    assert isinstance(yaml.safe_load(_AUSGELIEFERT.read_text(encoding="utf-8")), dict)


def test_gedeckte_pfade_sind_wirklich_verschieden():
    """Damit die Waechter oben nicht versehentlich dieselbe Datei
    zweimal pruefen."""
    assert Path(_AUSGELIEFERT) != Path(GLOBAL_ASSUMPTIONS_PATH)
