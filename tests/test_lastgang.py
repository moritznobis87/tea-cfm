"""
Einspeisekurven je Bauform: ihre Ableitung aus Stundenreihen
(engine/io_lastgang.py) und die im Modell hinterlegten Kurven.

Die Ableitung laeuft nicht zur Laufzeit - sie ist einmal gelaufen und
hat die zwoelf Monatsanteile fuer "Pult" und "Tracker" erzeugt
(engine/models.EINSPEISEKURVEN_JE_BAUFORM). Genau deshalb wird sie hier
geprueft: Aus den Rohreihen unter data/lastgang muessen wieder dieselben
Zahlen entstehen, sonst stuende im Modell eine Kurve, die zu keiner
Messung mehr gehoert.

Dazu die Bausteine: das Lesen (deutsches Dezimalkomma, Kopfzeilen, CSV,
Excel) und das Auswerten (Pflichtlaenge 8.760/8.784, Monatszuordnung,
Normierung). Die Pflichtlaenge ist der wichtigste Fall - eine um Stunden
verschobene Reihe ergaebe eine still verschobene Kurve, und der Fehler
faende sich erst in der Rendite wieder.

Am Ende steht das Praemienmodell des Laenderschalters: Oesterreich
rechnet mit dem Toleranzband des EAG, Deutschland mit dem einseitigen
CfD des EEG.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import pandas as pd
import pytest

from engine.io_lastgang import (
    STUNDEN_NORMALJAHR,
    STUNDEN_SCHALTJAHR,
    LastgangFehler,
    einspeisekurve_aus_stundenreihe,
    kurve_aus_datei,
    lies_stundenreihe,
)

_ROOT = Path(__file__).resolve().parent.parent
_GA_PFAD = _ROOT / "data" / "global_assumptions.yaml"

#: Stunden je Monat im Normaljahr - dieselbe Aufteilung wie im Modul,
#: hier bewusst noch einmal ausgeschrieben: Waere sie im Modul falsch,
#: koennte ein Test, der sie von dort bezoege, das nicht bemerken.
_STUNDEN = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]


def _sonnenreihe(stunden: int = STUNDEN_NORMALJAHR) -> list[float]:
    """Eine PV-aehnliche Reihe: Tagesgang mal Jahresgang, nachts null."""
    werte = []
    for i in range(stunden):
        tagesstunde = i % 24
        tag = i // 24
        tages = max(0.0, math.sin(math.pi * (tagesstunde - 6) / 12))
        jahres = 0.55 + 0.45 * math.cos(2 * math.pi * (tag - 172) / 365)
        werte.append(tages * jahres)
    return werte


class TestLesen:
    def test_eine_zahl_je_zeile(self):
        assert lies_stundenreihe("1\n2\n3\n") == [1.0, 2.0, 3.0]

    def test_deutsches_dezimalkomma(self):
        assert lies_stundenreihe("0,5\n1,25\n") == [0.5, 1.25]

    def test_tausenderpunkt_bei_dezimalkomma(self):
        assert lies_stundenreihe("1.234,5\n") == [1234.5]

    def test_englische_schreibweise(self):
        assert lies_stundenreihe("0.5\n1.25\n") == [0.5, 1.25]

    def test_kopfzeile_wird_uebergangen(self):
        assert lies_stundenreihe("Erzeugung kW\n1\n2\n") == [1.0, 2.0]

    def test_csv_mit_semikolon(self):
        assert lies_stundenreihe("1;2;3") == [1.0, 2.0, 3.0]

    def test_leere_zeilen_zaehlen_nicht(self):
        assert lies_stundenreihe("1\n\n\n2\n") == [1.0, 2.0]

    def test_excel_spalte(self):
        puffer = io.BytesIO()
        pd.DataFrame({"kW": [0.0, 1.5, 3.0]}).to_excel(
            puffer, index=False, header=True
        )
        werte = lies_stundenreihe(puffer.getvalue(), "lastgang.xlsx")
        assert werte == [0.0, 1.5, 3.0]

    def test_bytes_mit_bom(self):
        assert lies_stundenreihe("1\n2\n".encode("utf-8-sig"), "reihe.csv") == [
            1.0,
            2.0,
        ]


class TestAuswertung:
    def test_falsche_laenge_wird_abgewiesen(self):
        with pytest.raises(LastgangFehler, match="8.760"):
            einspeisekurve_aus_stundenreihe([1.0] * 8759)

    def test_leere_reihe_wird_abgewiesen(self):
        with pytest.raises(LastgangFehler):
            einspeisekurve_aus_stundenreihe([])

    def test_konstante_reihe_ergibt_stundenanteile(self):
        """Bei konstanter Leistung ist die Kurve die Laenge der Monate."""
        auswertung = einspeisekurve_aus_stundenreihe([1.0] * STUNDEN_NORMALJAHR)
        erwartet = [s / STUNDEN_NORMALJAHR for s in _STUNDEN]
        assert auswertung.kurve_pct_je_monat == pytest.approx(erwartet)
        assert sum(auswertung.kurve_pct_je_monat) == pytest.approx(1.0)
        assert auswertung.schaltjahr is False
        assert auswertung.stunden == STUNDEN_NORMALJAHR

    def test_schaltjahr_erlaubt_und_erkannt(self):
        auswertung = einspeisekurve_aus_stundenreihe([1.0] * STUNDEN_SCHALTJAHR)
        assert auswertung.schaltjahr is True
        # Der Februar traegt im Schaltjahr 696 statt 672 Stunden.
        assert auswertung.kurve_pct_je_monat[1] == pytest.approx(
            696 / STUNDEN_SCHALTJAHR
        )

    def test_monatszuordnung_trennt_scharf(self):
        """Nur der Januar traegt Werte - dann ist die Kurve (1, 0, ...)."""
        werte = [1.0] * 744 + [0.0] * (STUNDEN_NORMALJAHR - 744)
        kurve = einspeisekurve_aus_stundenreihe(werte).kurve_pct_je_monat
        assert kurve[0] == pytest.approx(1.0)
        assert sum(kurve[1:]) == pytest.approx(0.0)

    def test_massstab_ist_gleichgueltig(self):
        """kW oder MW - die Kurve ist dieselbe, nur die Form zaehlt."""
        reihe = _sonnenreihe()
        a = einspeisekurve_aus_stundenreihe(reihe).kurve_pct_je_monat
        b = einspeisekurve_aus_stundenreihe([w * 1000 for w in reihe])
        assert b.kurve_pct_je_monat == pytest.approx(a)

    def test_sommer_traegt_mehr_als_winter(self):
        kurve = einspeisekurve_aus_stundenreihe(_sonnenreihe()).kurve_pct_je_monat
        assert kurve[5] + kurve[6] > kurve[0] + kurve[11]

    def test_gegenproben(self):
        reihe = _sonnenreihe()
        auswertung = einspeisekurve_aus_stundenreihe(reihe)
        assert auswertung.summe == pytest.approx(sum(reihe))
        assert auswertung.spitze == pytest.approx(max(reihe))
        assert auswertung.vollbenutzungsstunden == pytest.approx(
            sum(reihe) / max(reihe)
        )

    def test_nullreihe_wird_abgewiesen(self):
        with pytest.raises(LastgangFehler, match="null"):
            einspeisekurve_aus_stundenreihe([0.0] * STUNDEN_NORMALJAHR)

    def test_negative_werte_ergeben_hinweis(self):
        werte = [1.0] * STUNDEN_NORMALJAHR
        werte[0] = -0.5
        auswertung = einspeisekurve_aus_stundenreihe(werte)
        assert any("negativ" in h.lower() for h in auswertung.hinweise)

    def test_leerer_monat_ergibt_hinweis(self):
        werte = [1.0] * STUNDEN_NORMALJAHR
        werte[:744] = [0.0] * 744
        auswertung = einspeisekurve_aus_stundenreihe(werte)
        assert any("Monate ohne Erzeugung" in h for h in auswertung.hinweise)


class TestKurveAusDatei:
    def test_text_ohne_zahlen(self):
        with pytest.raises(LastgangFehler, match="keine Zahlen"):
            kurve_aus_datei("Kopfzeile\nnur Text\n")

    def test_csv_datei(self):
        text = "kW\n" + "\n".join(
            f"{w:.4f}".replace(".", ",") for w in _sonnenreihe()
        )
        auswertung = kurve_aus_datei(text.encode("utf-8"), "pult.csv")
        assert sum(auswertung.kurve_pct_je_monat) == pytest.approx(1.0)

    def test_excel_datei(self):
        puffer = io.BytesIO()
        pd.DataFrame({"kW": _sonnenreihe()}).to_excel(puffer, index=False)
        auswertung = kurve_aus_datei(puffer.getvalue(), "tracker.xlsx")
        assert auswertung.stunden == STUNDEN_NORMALJAHR


class TestHinterlegteKurven:
    """Die beiden Kurven im Modell sind kein Handwerk, sondern das
    Ergebnis der Ableitung - und genau das wird hier nachgerechnet:
    aus den Rohreihen unter data/lastgang muessen wieder die Zahlen aus
    EINSPEISEKURVEN_JE_BAUFORM entstehen."""

    @pytest.mark.parametrize("bauform", ["Pult", "Tracker"])
    def test_kurve_stimmt_mit_rohreihe_ueberein(self, bauform):
        from engine.models import EINSPEISEKURVEN_JE_BAUFORM

        pfad = _ROOT / "data" / "lastgang" / f"{bauform.lower()}.csv"
        auswertung = kurve_aus_datei(pfad.read_bytes(), pfad.name)
        assert auswertung.stunden == STUNDEN_NORMALJAHR
        # Hinterlegt sind sechs Nachkommastellen.
        assert auswertung.kurve_pct_je_monat == pytest.approx(
            EINSPEISEKURVEN_JE_BAUFORM[bauform], abs=5e-7
        )

    @pytest.mark.parametrize("bauform", ["Pult", "Tracker"])
    def test_kurve_summiert_sich_auf_eins(self, bauform):
        from engine.models import EINSPEISEKURVEN_JE_BAUFORM

        kurve = EINSPEISEKURVEN_JE_BAUFORM[bauform]
        assert len(kurve) == 12
        assert sum(kurve) == pytest.approx(1.0, abs=1e-5)
        assert all(w > 0 for w in kurve)

    def test_standard_ist_die_pult_kurve(self):
        from engine.models import (
            EINSPEISEKURVE_STANDARD_BAUFORM,
            EINSPEISEKURVE_STANDARD_PCT,
            EINSPEISEKURVEN_JE_BAUFORM,
        )

        assert EINSPEISEKURVE_STANDARD_BAUFORM == "Pult"
        assert EINSPEISEKURVE_STANDARD_PCT == EINSPEISEKURVEN_JE_BAUFORM["Pult"]

    def test_globale_annahmen_bringen_beide_kurven_mit(self):
        from engine.models import EINSPEISEKURVEN_JE_BAUFORM, GlobalAssumptions

        ga = GlobalAssumptions.model_construct()
        vorgabe = GlobalAssumptions.model_fields[
            "einspeisekurven_je_bauform"
        ].default_factory()
        assert set(vorgabe) == set(EINSPEISEKURVEN_JE_BAUFORM)
        # Eigene Kopien - ein Projekt darf die Vorlage nicht veraendern.
        vorgabe["Pult"][0] = 0.99
        assert EINSPEISEKURVEN_JE_BAUFORM["Pult"][0] != 0.99
        del ga

    def test_ausgelieferte_annahmen_nutzen_die_pult_kurve(self):
        from engine.io_yaml import load_global_assumptions_yaml
        from engine.models import EINSPEISEKURVEN_JE_BAUFORM

        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.einspeisekurve_bauform == "Pult"
        assert set(ga.einspeisekurven_je_bauform) == set(EINSPEISEKURVEN_JE_BAUFORM)
        assert ga.einspeisekurve_pct_je_monat == pytest.approx(
            EINSPEISEKURVEN_JE_BAUFORM["Pult"], abs=5e-7
        )

    def test_tracker_hebt_die_uebergangszeit_an(self):
        """Nachgefuehrte Module verschieben Erzeugung aus dem Hochsommer
        in die flachen Monate - sonst waere die Unterscheidung der
        Bauformen fuer die Monatsrechnung ohne Wirkung."""
        from engine.models import EINSPEISEKURVEN_JE_BAUFORM

        pult = EINSPEISEKURVEN_JE_BAUFORM["Pult"]
        tracker = EINSPEISEKURVEN_JE_BAUFORM["Tracker"]
        assert tracker != pult
        # Mai bis Juli: Tracker traegt mehr, April/August weniger.
        assert sum(tracker[4:7]) > sum(pult[4:7])


class TestModellfelder:
    def test_kurven_je_bauform_werden_gespeichert(self, tmp_path, global_assumptions):
        from engine.io_yaml import load_global_assumptions_yaml, save_global_assumptions_yaml

        kurve = einspeisekurve_aus_stundenreihe(_sonnenreihe()).kurve_pct_je_monat
        ga = global_assumptions
        ga.einspeisekurven_je_bauform["Pult"] = kurve
        ga.einspeisekurve_bauform = "Pult"
        ga.einspeisekurve_pct_je_monat = list(kurve)

        pfad = tmp_path / "ga.yaml"
        save_global_assumptions_yaml(ga, pfad)
        gelesen = load_global_assumptions_yaml(pfad)
        assert gelesen.einspeisekurve_bauform == "Pult"
        assert gelesen.einspeisekurven_je_bauform["Pult"] == pytest.approx(kurve)


@pytest.fixture()
def _ga_datei_gesichert():
    """Wie in test_markt_system.py: Der Import speichert sofort."""
    sicherung = _GA_PFAD.read_bytes()
    try:
        yield
    finally:
        _GA_PFAD.write_bytes(sicherung)
        from app import services

        services._load_global_assumptions_cached.clear()


def _app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(_ROOT / "streamlit_app.py"), default_timeout=300)
    at.run()
    assert not at.exception, at.exception
    return at


def _navigiere(at, key: str):
    [b for b in at.button if b.key == key][0].click()
    at.run()
    return at


class TestMarktsystemSetztPraemienmodell:
    """Oesterreich rechnet mit dem Toleranzband des EAG, Deutschland mit
    dem einseitigen CfD des EEG - der Laenderschalter stellt das mit um."""

    def test_deutschland_setzt_einseitigen_cfd(self, _ga_datei_gesichert):
        from engine.io_yaml import load_global_assumptions_yaml
        from engine.models import PraemienModell

        at = _app()
        _navigiere(at, "nav_annahmen")
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        assert not at.exception, at.exception
        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.praemien_modell == PraemienModell.EINSEITIG_CFD

    def test_oesterreich_setzt_toleranzband(self, _ga_datei_gesichert):
        from engine.io_yaml import load_global_assumptions_yaml
        from engine.models import PraemienModell

        at = _app()
        _navigiere(at, "nav_annahmen")
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        [b for b in at.button if b.key == "marktsystem_at"][0].click()
        at.run()
        assert not at.exception, at.exception
        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.praemien_modell == PraemienModell.EAG_TOLERANZBAND

    def test_standard_der_globalen_annahmen_ist_oesterreichisch(self):
        from engine.models import GlobalAssumptions, MarktSystem, PraemienModell

        felder = GlobalAssumptions.model_fields
        assert felder["markt_system"].default == MarktSystem.OESTERREICH
        assert felder["praemien_modell"].default == PraemienModell.EAG_TOLERANZBAND
