"""Abweichungen eines Projekts von den globalen Annahmen.

Grundregel des ganzen Mechanismus: **None heisst "folgt der Vorgabe"**.
Ein Projekt speichert nicht den globalen Wert, sondern nur, dass es ihm
folgt - sonst erreichte eine spaetere Aenderung der Vorgabe kein
einziges Projekt mehr.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from engine.models import (
    AnlagenTyp,
    CapexBreakdown,
    GlobalAssumptions,
    Projektannahmen,
    PVProject,
    TaxModus,
    TilgungsArt,
    ZinsMethode,
)
from engine.pipeline import resolve_assumptions

_ROOT = Path(__file__).resolve().parent.parent


def _projekt(**kw) -> PVProject:
    felder = dict(
        id="p", name="P", anlagentyp=AnlagenTyp.AGRI_PV,
        # Ohne Investition gibt es kein Darlehen und nichts zu tilgen.
        capex=CapexBreakdown(epc_eur=2_600_000.0),
        nennleistung_kwp=5000.0, vollbenutzungsstunden_kwh_kwp=1050.0,
        pacht_eur_kwp_jahr=4.0, fremdkapitalzins_pct=0.042,
        eigenkapitalquote_pct=0.2, eag_zuschlagswert_ct_kwh=6.5,
    )
    felder.update(kw)
    return PVProject(**felder)


def _ga(**kw) -> GlobalAssumptions:
    felder = dict(afa_nutzungsdauer_jahre=20)
    felder.update(kw)
    return GlobalAssumptions(**felder)


class TestVorgabeUndAbweichung:
    def test_ohne_abweichung_gilt_die_vorgabe(self):
        ga = _ga(kreditlaufzeit_jahre=18, tilgungsart=TilgungsArt.LINEAR)
        ea = resolve_assumptions(_projekt(), ga)
        assert ea.kreditlaufzeit_jahre == 18
        assert ea.tilgungsart == TilgungsArt.LINEAR

    def test_abweichung_hat_vorrang(self):
        ga = _ga(kreditlaufzeit_jahre=18)
        projekt = _projekt(annahmen=Projektannahmen(kreditlaufzeit_jahre=12))
        assert resolve_assumptions(projekt, ga).kreditlaufzeit_jahre == 12

    def test_projekt_zieht_mit_wenn_es_der_vorgabe_folgt(self):
        """Der eigentliche Zweck: Die globalen Annahmen bleiben
        Vorgaben. Wer nicht abweicht, uebernimmt eine spaetere
        Aenderung."""
        projekt = _projekt()
        assert resolve_assumptions(projekt, _ga(steuersatz_pct=0.25)) \
            .steuersatz_pct == 0.25
        assert resolve_assumptions(projekt, _ga(steuersatz_pct=0.30)) \
            .steuersatz_pct == 0.30

    def test_abweichung_bleibt_stehen_wenn_die_vorgabe_wechselt(self):
        projekt = _projekt(annahmen=Projektannahmen(steuersatz_pct=0.40))
        for vorgabe in (0.25, 0.30):
            assert resolve_assumptions(projekt, _ga(steuersatz_pct=vorgabe)) \
                .steuersatz_pct == 0.40

    @pytest.mark.parametrize("wert", [False, 0.0, 0])
    def test_falsy_abweichungen_wirken(self, wert):
        """`if eigen:` waere hier falsch: Ein abweichendes 0 % oder
        False ist eine Eingabe, keine fehlende Angabe."""
        ga = _ga(tilgungsfreies_anlaufjahr=True, sicherheitsabschlag_pct=0.05)
        projekt = _projekt(annahmen=Projektannahmen(
            tilgungsfreies_anlaufjahr=False, sicherheitsabschlag_pct=0.0,
        ))
        ea = resolve_assumptions(projekt, ga)
        assert ea.tilgungsfreies_anlaufjahr is False
        assert ea.sicherheitsabschlag_pct == 0.0

    def test_negativstunden_regel_waehlt_die_richtige_zeitreihe(self):
        """Die Regel bestimmt nicht nur eine Kennzahl, sondern WELCHE
        der beiden Negativmengen-Reihen des Szenarios gerechnet wird.
        Bliebe dort die globale Regel stehen, waere die Abweichung nur
        halb wirksam."""
        from engine.models import MarktpreisSzenario, NegativeStundenRegel

        szenario = MarktpreisSzenario(
            name="S",
            marktwert_solar_ct_kwh_je_kalenderjahr={j: 6.0 for j in range(2027, 2060)},
            erzeugungsmenge_negativ_6h_pct_je_kalenderjahr={
                j: 0.01 for j in range(2027, 2060)
            },
            erzeugungsmenge_negativ_1h_pct_je_kalenderjahr={
                j: 0.09 for j in range(2027, 2060)
            },
        )
        ga = _ga(
            marktpreisszenarien=[szenario],
            negative_stunden_regel=NegativeStundenRegel.SECHS_STUNDEN,
        )
        projekt = _projekt(marktpreisszenario="S")
        ea = resolve_assumptions(projekt, ga)
        assert set(ea.anteil_negativer_stunden_pct_je_kalenderjahr.values()) == {0.01}

        projekt.annahmen.negative_stunden_regel = NegativeStundenRegel.EINE_STUNDE
        ea = resolve_assumptions(projekt, ga)
        assert set(ea.anteil_negativer_stunden_pct_je_kalenderjahr.values()) == {0.09}


class TestGesetzteFelder:
    def test_leerer_block_zaehlt_nichts(self):
        assert Projektannahmen().gesetzte_felder == []

    def test_nennt_nur_die_gesetzten(self):
        block = Projektannahmen(steuersatz_pct=0.3, tilgungsart=TilgungsArt.LINEAR)
        assert set(block.gesetzte_felder) == {"steuersatz_pct", "tilgungsart"}

    def test_betriebskosten_zaehlen_als_ein_feld(self):
        block = Projektannahmen(opex_standard_eur_kwp={"Versicherungen": 1.4})
        assert block.gesetzte_felder == ["opex_standard_eur_kwp"]


class TestSpeicherform:
    def test_yaml_traegt_nur_gesetzte_abweichungen(self, tmp_path):
        """Ungefiltert stuenden rund dreissig `null`-Zeilen in jeder
        Datei und verdeckten die wenigen, auf die es ankommt."""
        import yaml

        from engine.io_yaml import load_project_yaml, save_project_yaml

        projekt = _projekt(annahmen=Projektannahmen(kreditlaufzeit_jahre=15))
        pfad = tmp_path / "p.yaml"
        save_project_yaml(projekt, pfad)

        roh = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        assert roh["annahmen"] == {"kreditlaufzeit_jahre": 15}
        assert load_project_yaml(pfad).annahmen.kreditlaufzeit_jahre == 15

    def test_altbestand_ohne_block_laedt(self, tmp_path):
        """Projektdateien vor v5.17 kennen den Abschnitt nicht - sie
        folgen in allem der Vorgabe."""
        import yaml

        from engine.io_yaml import load_project_yaml, save_project_yaml

        pfad = tmp_path / "p.yaml"
        save_project_yaml(_projekt(), pfad)
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        del daten["annahmen"]
        pfad.write_text(yaml.safe_dump(daten, allow_unicode=True), encoding="utf-8")

        assert load_project_yaml(pfad).annahmen.gesetzte_felder == []


class TestWirkungAufDasErgebnis:
    def test_tilgungsfreies_anlaufjahr_wirkt_je_projekt(self):
        """Der vom Nutzer genannte Fall: Bisher liess sich nur global
        entscheiden, ob ALLE Projekte ein tilgungsfreies Anlaufjahr
        haben."""
        from engine import run_valuation

        ga = _ga(tilgungsfreies_anlaufjahr=False)
        ohne = run_valuation(_projekt(), ga)
        mit = run_valuation(
            _projekt(annahmen=Projektannahmen(tilgungsfreies_anlaufjahr=True)), ga
        )
        # Zeile 0 ist das Investitionsjahr - getilgt wird ab Jahr 1.
        def tilgung_jahr1(ergebnis):
            df = ergebnis.cashflow.data
            return float(df.loc[df["jahr"] == 1, "tilgung_eur"].iloc[0])

        assert tilgung_jahr1(mit) == 0.0
        assert tilgung_jahr1(ohne) > 0.0

    def test_zwei_projekte_rechnen_verschiedene_laender(self):
        """Zinsmethode und Steuermodell nebeneinander in einem
        Portfolio - der Fall, der ohne Abweichungen unmoeglich war."""
        ga = _ga(
            zinsmethode=ZinsMethode.OESTERREICH,
            tax_modus=TaxModus.AFA_KOERPERSCHAFTSTEUER,
        )
        deutsch = _projekt(annahmen=Projektannahmen(
            zinsmethode=ZinsMethode.DEUTSCH, tax_modus=TaxModus.GEWERBESTEUER_DE,
        ))
        assert resolve_assumptions(_projekt(), ga).zinsmethode == ZinsMethode.OESTERREICH
        ea = resolve_assumptions(deutsch, ga)
        assert ea.zinsmethode == ZinsMethode.DEUTSCH
        assert ea.tax_modus == TaxModus.GEWERBESTEUER_DE


class TestParameterspalte:
    """Die Bedienung: ein Widget je Parameter, leer = Vorgabe."""

    @pytest.fixture
    def spalte(self):
        at = AppTest.from_file(str(_ROOT / "streamlit_app.py"), default_timeout=90)
        at.run()
        knoepfe = [b.key for b in at.button if b.key and b.key.startswith("open_")]
        [b for b in at.button if b.key == knoepfe[0]][0].click()
        at.run()
        return at, f"param_{knoepfe[0].removeprefix('open_')}"

    def test_jedes_erbfeld_hat_genau_ein_bedienelement(self, spalte):
        """Der Grund, warum die Spalte nicht explodiert: kein zweiter
        "Abweichen?"-Schalter neben jedem Wert.

        Geprueft wird gegen die Feldliste der Maske, nicht gegen eine
        feste Zahl - sonst muesste der Test bei jedem neuen Feld
        nachgezogen werden, statt einen Fehler zu melden.
        """
        from app.components.project_form import _ABWEICHUNG_LABEL

        at, form_key = spalte
        schluessel = [
            w.key
            for art in ("number_input", "selectbox", "radio")
            for w in at.get(art)
            if w.key and w.key.startswith(f"{form_key}_abw_")
        ]
        assert len(schluessel) == len(set(schluessel))
        assert {s.removeprefix(f"{form_key}_abw_") for s in schluessel} == set(
            _ABWEICHUNG_LABEL
        )

    def test_alle_abweichungsfelder_sind_erreichbar(self):
        """Regressionsschutz: Ein spaeter ergaenztes Abweichungsfeld darf
        nicht still unerreichbar bleiben."""
        from app.components.project_form import _ABWEICHUNG_LABEL

        offen = (
            set(Projektannahmen.model_fields)
            - set(_ABWEICHUNG_LABEL)
            # Die Betriebskosten stehen als Tabelle in der Maske, nicht
            # als Einzelfeld - sie haben deshalb keine Beschriftung hier.
            - {"opex_standard_eur_kwp"}
        )
        assert offen == set()

    def test_ohne_abweichung_steht_nach_vorgabe(self, spalte):
        at, _ = spalte
        assert sum(c.value == "nach Vorgabe" for c in at.caption) >= 2

    def test_eingabe_wird_zur_abweichung(self, spalte):
        at, form_key = spalte
        feld = [n for n in at.get("number_input")
                if n.key == f"{form_key}_abw_kreditlaufzeit_jahre"][0]
        feld.set_value(12)
        at.run()
        assert not at.exception
        assert any("Kreditlaufzeit" in c.value for c in at.caption)

    def test_leeren_fuehrt_zur_vorgabe_zurueck(self, spalte):
        at, form_key = spalte
        schluessel = f"{form_key}_abw_kreditlaufzeit_jahre"
        [n for n in at.get("number_input") if n.key == schluessel][0].set_value(12)
        at.run()
        [n for n in at.get("number_input") if n.key == schluessel][0].set_value(None)
        at.run()
        assert not at.exception
        assert not any("Kreditlaufzeit" in c.value for c in at.caption)

    def test_land_setzt_das_paket(self, spalte):
        """Ein Klick statt vier Feldern in drei Popovern."""
        at, form_key = spalte
        [b for b in at.button
         if b.key == f"{form_key}_land_Deutschland"][0].click()
        at.run()
        assert not at.exception
        gewaehlt = {
            s.key.removeprefix(f"{form_key}_abw_"): s.value
            for s in at.get("selectbox") if s.key and "_abw_" in s.key
        }
        assert gewaehlt["zinsmethode"] == "Deutschland (30/360)"
        assert gewaehlt["tax_modus"] == "Gewerbesteuer (DE)"

    def test_erbfelder_haengen_am_entwurf(self, spalte):
        """`verwirf_entwurf` loescht alle Schluessel mit dem Praefix der
        Spalte. Truege ein Erbfeld einen anderen Schluessel, bliebe die
        Abweichung nach dem Verwerfen stehen - der stille Fehler, den
        zwei getrennte Eingabeflaechen erzeugt haetten.
        """
        at, form_key = spalte
        schluessel = f"{form_key}_abw_kreditlaufzeit_jahre"
        [n for n in at.get("number_input") if n.key == schluessel][0].set_value(12)
        at.run()
        assert at.session_state[schluessel] == 12
        assert schluessel.startswith(f"{form_key}_")

        # Und der Knopf raeumt tatsaechlich auf: Das Feld steht danach
        # wieder leer, das Projekt folgt also wieder der Vorgabe. (Der
        # Schluessel selbst existiert weiter - das Widget wird im
        # selben Durchlauf neu aufgebaut.)
        verwerfen = [b for b in at.button if b.key == f"{form_key}__verwerfen"]
        assert verwerfen, "Verwerfen-Knopf fehlt"
        verwerfen[0].click()
        at.run()
        assert not at.exception
        assert at.session_state[schluessel] is None
        assert not any("Kreditlaufzeit" in c.value for c in at.caption)
