"""
Monatsaufloesung, Praemienmodelle und hybride Vermarktung (v5.4).

Drei Erweiterungen der Erloesrechnung, die unabhaengig voneinander
wirken sollen - und genau das wird hier geprueft:

1. Zeitaufloesung: Die Jahresmenge wird ueber die Einspeisekurve auf
   Monate verteilt und trifft dort auf Monatsmarktwerte.
2. Praemienmodell: einseitiger CfD (bisher), zweiseitiger CfD und der
   oesterreichische Weg mit Toleranzband (§ 10 EAG).
3. PPA: ein Teil der Menge geht zum Vertragspreis weg, der Rest an den
   Markt - die Foerderung bemisst sich unveraendert am Referenzmarktwert.

Die Fixtures rechnen mit 1.000 kWp x 1.000 kWh/kWp = 1 GWh/Jahr, 4 ct
Marktwert und 7 ct Zuschlagswert; damit sind alle Erwartungswerte von
Hand nachvollziehbar.
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.energy import calculate_energy_production
from engine.models import (
    EINSPEISEKURVE_STANDARD_PCT,
    MarktpreisSzenario,
    NegativeStundenModus,
    PraemienModell,
    Zeitaufloesung,
)
from engine.pipeline import resolve_assumptions
from engine.revenue import calculate_revenue
from engine.timeline import build_timeline


def _revenue(project, ga, jahre: int = 25):
    assumptions = resolve_assumptions(project, ga)
    timeline = build_timeline(
        date(project.inbetriebnahme_jahr, project.inbetriebnahme_monat, 1), jahre
    )
    energy = calculate_energy_production(timeline, assumptions)
    return calculate_revenue(timeline, energy, assumptions)


def _energie(project, ga, jahre: int = 25):
    assumptions = resolve_assumptions(project, ga)
    timeline = build_timeline(
        date(project.inbetriebnahme_jahr, project.inbetriebnahme_monat, 1), jahre
    )
    return calculate_energy_production(timeline, assumptions)


class TestZeitaufloesung:
    """Die Monatsebene ist eine Unterebene der Erloesrechnung - der
    Cashflow bleibt jaehrlich."""

    def test_ohne_monatsdaten_aendert_sich_nichts(self, project, global_assumptions):
        """Ein Szenario ohne Monatsreihen faellt auf seinen Jahreswert
        zurueck. Sonst wuerde die Umschaltung Projekte veraendern, fuer
        die noch gar keine Monatsdaten vorliegen."""
        jahr = _revenue(project, global_assumptions)
        global_assumptions.zeitaufloesung = Zeitaufloesung.MONAT
        monat = _revenue(project, global_assumptions)
        assert monat["erloes_eur"].sum() == pytest.approx(
            jahr["erloes_eur"].sum(), rel=1e-9
        )

    def test_jahresmenge_bleibt_die_jahresmenge(self, project, global_assumptions):
        """Die Einspeisekurve verteilt, sie erzeugt und vernichtet nicht."""
        global_assumptions.zeitaufloesung = Zeitaufloesung.MONAT
        energie = _energie(project, global_assumptions)
        assert float(energie.loc[energie["jahr"] == 2, "produktion_kwh"].iloc[0]) == (
            pytest.approx(1_000_000.0)
        )

    def test_kurve_wird_normiert(self, project, global_assumptions):
        """Eine Kurve, die sich auf 99 % summiert, darf die Jahresmenge
        nicht um 1 % kuerzen - sie ist eine Verteilung, keine Menge."""
        global_assumptions.zeitaufloesung = Zeitaufloesung.MONAT
        global_assumptions.einspeisekurve_pct_je_monat = [
            w * 0.99 for w in EINSPEISEKURVE_STANDARD_PCT
        ]
        energie = _energie(project, global_assumptions)
        assert float(energie.loc[energie["jahr"] == 2, "produktion_kwh"].iloc[0]) == (
            pytest.approx(1_000_000.0)
        )

    def test_anlaufjahr_folgt_der_erzeugung_statt_dem_kalender(
        self, project, global_assumptions
    ):
        """Eine Anlage, die im Juli startet, erzeugt im Anlaufjahr mehr
        als das halbe Jahr - die ertragreichen Monate liegen im Sommer.
        Die Jahresrechnung mit ihrem Tagesanteil kann das nicht wissen.
        """
        project.inbetriebnahme_monat = 7
        global_assumptions.zeitaufloesung = Zeitaufloesung.MONAT
        energie = _energie(project, global_assumptions)
        anteil = (
            float(energie.loc[energie["jahr"] == 1, "produktion_kwh"].iloc[0])
            / float(energie.loc[energie["jahr"] == 2, "produktion_kwh"].iloc[0])
        )
        erwartet = sum(EINSPEISEKURVE_STANDARD_PCT[6:]) / sum(
            EINSPEISEKURVE_STANDARD_PCT
        )
        assert anteil == pytest.approx(erwartet)

    def test_monatswerte_schlagen_den_jahreswert(self, project, global_assumptions):
        """Liegt eine Monatsreihe vor, gilt sie - und der ausgewiesene
        Jahresmarktwert ist ihr erzeugungsgewichtetes Mittel, nicht ihr
        einfacher Durchschnitt. Fuer PV sind das zwei verschiedene
        Zahlen, und nur die erste beschreibt, was die Anlage erloest."""
        # Sommer 2 ct, Winter 6 ct: einfacher Mittelwert 4 ct, mit der
        # Sommerlastigkeit der PV-Erzeugung aber deutlich weniger.
        monate = [6.0] * 3 + [2.0] * 6 + [6.0] * 3
        szenario = global_assumptions.marktpreisszenarien[0]
        global_assumptions.marktpreisszenarien = [
            MarktpreisSzenario(
                name=szenario.name,
                marktwert_solar_ct_kwh_je_kalenderjahr=(
                    szenario.marktwert_solar_ct_kwh_je_kalenderjahr
                ),
                erzeugungsmenge_negativ_6h_pct_je_kalenderjahr=(
                    szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr
                ),
                marktwert_solar_ct_kwh_je_monat={
                    j: list(monate)
                    for j in szenario.marktwert_solar_ct_kwh_je_kalenderjahr
                },
            )
        ]
        global_assumptions.zeitaufloesung = Zeitaufloesung.MONAT
        revenue = _revenue(project, global_assumptions)
        gewichtet = float(
            revenue.loc[revenue["jahr"] == 2, "marktwert_nominal_ct_kwh"].iloc[0]
        )
        sommeranteil = sum(EINSPEISEKURVE_STANDARD_PCT[3:9])
        assert gewichtet == pytest.approx(
            6.0 - 4.0 * sommeranteil / sum(EINSPEISEKURVE_STANDARD_PCT), rel=1e-6
        )
        assert gewichtet < 4.0

    def test_monatsreihe_braucht_zwoelf_werte(self):
        """Elf Werte waeren eine stillschweigend verschobene Reihe."""
        with pytest.raises(ValueError, match="12"):
            MarktpreisSzenario(
                name="kaputt",
                marktwert_solar_ct_kwh_je_monat={2030: [4.0] * 11},
            )


class TestPraemienmodelle:
    """Was geschieht oberhalb des anzulegenden Werts? Unterhalb zahlen
    alle drei Modelle auf."""

    @pytest.fixture
    def teures_szenario(self, global_assumptions):
        """Marktwert 12 ct - deutlich ueber dem Zuschlagswert von 7 ct
        und ueber dem Toleranzband (7 x 1,4 = 9,8 ct)."""
        global_assumptions.marktpreisszenarien = [
            MarktpreisSzenario(
                name="Testszenario",
                marktwert_solar_ct_kwh_je_kalenderjahr={
                    j: 12.0 for j in range(2025, 2061)
                },
                erzeugungsmenge_negativ_6h_pct_je_kalenderjahr={
                    j: 0.0 for j in range(2025, 2061)
                },
            )
        ]
        return global_assumptions

    def test_einseitig_behaelt_den_uebergewinn(self, project, teures_szenario):
        teures_szenario.praemien_modell = PraemienModell.EINSEITIG_CFD
        revenue = _revenue(project, teures_szenario)
        zeile = revenue[revenue["jahr"] == 2].iloc[0]
        assert zeile["verguetungssatz_ct_kwh"] == pytest.approx(12.0)
        assert zeile["rueckzahlung_eur"] == 0.0

    def test_zweiseitig_zahlt_den_uebergewinn_vollstaendig_zurueck(
        self, project, teures_szenario
    ):
        teures_szenario.praemien_modell = PraemienModell.ZWEISEITIG_CFD
        revenue = _revenue(project, teures_szenario)
        zeile = revenue[revenue["jahr"] == 2].iloc[0]
        # 12 ct Marktwert minus 5 ct Rueckzahlung = 7 ct anzulegender Wert.
        assert zeile["verguetungssatz_ct_kwh"] == pytest.approx(7.0)
        assert zeile["rueckzahlung_eur"] == pytest.approx(1_000_000 * 0.05)

    def test_toleranzband_schoepft_nur_oberhalb_des_bandes_ab(
        self, project, teures_szenario
    ):
        """§ 10 EAG: 66 % des Betrags oberhalb von 140 % des anzulegenden
        Werts. 12 - 9,8 = 2,2 ct; davon 66 % = 1,452 ct."""
        teures_szenario.praemien_modell = PraemienModell.EAG_TOLERANZBAND
        project.nennleistung_kwp = 6000.0  # ueber der 5-MW-Schwelle
        revenue = _revenue(project, teures_szenario)
        zeile = revenue[revenue["jahr"] == 2].iloc[0]
        assert zeile["verguetungssatz_ct_kwh"] == pytest.approx(12.0 - 1.452)

    def test_toleranzband_greift_erst_ab_der_schwellenleistung(
        self, project, teures_szenario
    ):
        """Unter 5 MW behaelt die Anlage ihren Uebergewinn vollstaendig -
        derselbe Marktwert, ein anderes Ergebnis."""
        teures_szenario.praemien_modell = PraemienModell.EAG_TOLERANZBAND
        project.nennleistung_kwp = 4000.0
        revenue = _revenue(project, teures_szenario)
        assert revenue["rueckzahlung_eur"].sum() == 0.0

    def test_kein_modell_wirkt_nach_der_foerderdauer(
        self, project, teures_szenario
    ):
        """Nach dem Foerderende gibt es weder Praemie noch Rueckzahlung -
        der Vertrag ist ausgelaufen."""
        teures_szenario.praemien_modell = PraemienModell.ZWEISEITIG_CFD
        revenue = _revenue(project, teures_szenario)
        danach = revenue[revenue["jahr"] > 20]
        assert danach["rueckzahlung_eur"].sum() == 0.0
        assert danach["verguetungssatz_ct_kwh"].eq(12.0).all()

    def test_unterhalb_des_zuschlags_sind_alle_modelle_gleich(
        self, project, global_assumptions
    ):
        """Marktwert 4 ct < Zuschlag 7 ct: Es gibt keinen Uebergewinn, es
        gibt nichts abzuschoepfen."""
        ergebnisse = []
        for modell in PraemienModell:
            global_assumptions.praemien_modell = modell
            ergebnisse.append(_revenue(project, global_assumptions)["erloes_eur"].sum())
        assert ergebnisse[1] == pytest.approx(ergebnisse[0])
        assert ergebnisse[2] == pytest.approx(ergebnisse[0])


class TestHybridesPPA:
    """Ein PPA verschiebt die Erloesverteilung, nicht den
    Foerderanspruch."""

    def test_ohne_ppa_bleibt_alles_merchant(self, project, global_assumptions):
        revenue = _revenue(project, global_assumptions)
        assert revenue["erloes_ppa_eur"].sum() == 0.0
        assert revenue["erloes_merchant_eur"].sum() == pytest.approx(
            revenue["erloes_markt_eur"].sum()
        )

    def test_anteil_teilt_die_menge(self, project, global_assumptions):
        """50 % der Menge zu 80 EUR/MWh (= 8 ct/kWh), der Rest zum
        Marktwert von 4 ct."""
        project.ppa_anteil_pct = 0.5
        project.ppa_preis_eur_mwh = 80.0
        project.ppa_laufzeit_jahre = 10
        revenue = _revenue(project, global_assumptions)
        zeile = revenue[revenue["jahr"] == 2].iloc[0]
        assert zeile["erloes_ppa_eur"] == pytest.approx(500_000 * 0.08)
        assert zeile["erloes_merchant_eur"] == pytest.approx(500_000 * 0.04)

    def test_praemie_bemisst_sich_weiter_am_marktwert(
        self, project, global_assumptions
    ):
        """Der Vermarktungsweg aendert die Foerderung nicht: Die
        gleitende Marktpraemie bemisst sich am Referenzmarktwert, nicht
        am tatsaechlich erzielten Preis."""
        ohne = _revenue(project, global_assumptions)
        project.ppa_anteil_pct = 0.6
        project.ppa_preis_eur_mwh = 90.0
        project.ppa_laufzeit_jahre = 25
        mit = _revenue(project, global_assumptions)
        assert mit["erloes_praemie_eur"].sum() == pytest.approx(
            ohne["erloes_praemie_eur"].sum()
        )

    def test_laufzeit_und_startjahr_begrenzen_den_vertrag(
        self, project, global_assumptions
    ):
        project.ppa_anteil_pct = 1.0
        project.ppa_preis_eur_mwh = 80.0
        project.ppa_start_jahr = 3
        project.ppa_laufzeit_jahre = 2
        revenue = _revenue(project, global_assumptions)
        mit_ppa = revenue.loc[revenue["erloes_ppa_eur"] > 0, "jahr"].tolist()
        assert mit_ppa == [3, 4]

    def test_indexierung_startet_im_ersten_vertragsjahr(
        self, project, global_assumptions
    ):
        """Ein Vertrag, der erst in Jahr 3 beginnt, startet mit seinem
        vereinbarten Preis - nicht mit einem bereits zweimal indexierten.
        """
        project.ppa_anteil_pct = 1.0
        project.ppa_preis_eur_mwh = 80.0
        project.ppa_start_jahr = 3
        project.ppa_laufzeit_jahre = 3
        project.ppa_indexierung_pct_pa = 0.10
        revenue = _revenue(project, global_assumptions)
        erstes = float(revenue.loc[revenue["jahr"] == 3, "erloes_ppa_eur"].iloc[0])
        zweites = float(revenue.loc[revenue["jahr"] == 4, "erloes_ppa_eur"].iloc[0])
        assert erstes == pytest.approx(1_000_000 * 0.08)
        assert zweites == pytest.approx(erstes * 1.10)

    def test_negative_stunden_kuerzen_auch_die_ppa_menge(
        self, project, global_assumptions
    ):
        """Im Modus ABREGELUNG steht die Anlage still - dann gibt es auch
        nichts zu liefern. Ein PPA aendert daran nichts; die Mengenfrage
        ist der Vermarktung vorgelagert."""
        global_assumptions.negative_stunden_modus = NegativeStundenModus.ABREGELUNG
        szenario = global_assumptions.marktpreisszenarien[0]
        global_assumptions.marktpreisszenarien = [
            MarktpreisSzenario(
                name=szenario.name,
                marktwert_solar_ct_kwh_je_kalenderjahr=(
                    szenario.marktwert_solar_ct_kwh_je_kalenderjahr
                ),
                erzeugungsmenge_negativ_6h_pct_je_kalenderjahr={
                    j: 0.10 for j in szenario.marktwert_solar_ct_kwh_je_kalenderjahr
                },
            )
        ]
        project.ppa_anteil_pct = 1.0
        project.ppa_preis_eur_mwh = 80.0
        project.ppa_laufzeit_jahre = 25
        revenue = _revenue(project, global_assumptions)
        zeile = revenue[revenue["jahr"] == 2].iloc[0]
        assert zeile["erloes_ppa_eur"] == pytest.approx(900_000 * 0.08)


class TestExcelRundlauf:
    """Die Monatsdaten kommen aus einer Studie, nicht aus der Maske -
    der Excel-Weg ist deshalb der eigentliche Eingabekanal."""

    def _mit_monatsdaten(self, global_assumptions):
        szenario = global_assumptions.marktpreisszenarien[0]
        global_assumptions.marktpreisszenarien = [
            MarktpreisSzenario(
                name=szenario.name,
                marktwert_solar_ct_kwh_je_kalenderjahr=(
                    szenario.marktwert_solar_ct_kwh_je_kalenderjahr
                ),
                marktwert_solar_ct_kwh_je_monat={
                    2030: [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 5.5, 5.0, 4.5, 4.0, 3.5]
                },
                erzeugungsmenge_negativ_6h_pct_je_monat={
                    2030: [0.01 * m for m in range(1, 13)]
                },
            )
        ]
        return global_assumptions

    def test_monatsreihen_ueberstehen_den_rundlauf(self, global_assumptions):
        from engine.io_excel import (
            excel_to_global_assumptions,
            global_assumptions_to_excel,
        )

        ga = self._mit_monatsdaten(global_assumptions)
        ga.zeitaufloesung = Zeitaufloesung.MONAT
        ga.praemien_modell = PraemienModell.EAG_TOLERANZBAND
        ga.einspeisekurve_pct_je_monat = [w * 1.0 for w in EINSPEISEKURVE_STANDARD_PCT]

        gelesen = excel_to_global_assumptions(global_assumptions_to_excel(ga))
        szenario = gelesen.marktpreisszenarien[0]
        assert szenario.marktwert_solar_ct_kwh_je_monat[2030] == pytest.approx(
            ga.marktpreisszenarien[0].marktwert_solar_ct_kwh_je_monat[2030]
        )
        assert szenario.erzeugungsmenge_negativ_6h_pct_je_monat[2030] == pytest.approx(
            ga.marktpreisszenarien[0].erzeugungsmenge_negativ_6h_pct_je_monat[2030]
        )
        assert gelesen.zeitaufloesung == Zeitaufloesung.MONAT
        assert gelesen.praemien_modell == PraemienModell.EAG_TOLERANZBAND
        assert gelesen.einspeisekurve_pct_je_monat == pytest.approx(
            ga.einspeisekurve_pct_je_monat
        )

    def test_datei_ohne_monatsblaetter_bleibt_lesbar(self, global_assumptions):
        """Abwaertskompatibilitaet: Eine frueher gesicherte Mappe kennt
        die beiden neuen Blaetter nicht."""
        import io as _io

        import pandas as pd

        from engine.io_excel import (
            excel_to_global_assumptions,
            global_assumptions_to_excel,
        )

        blaetter = pd.read_excel(
            _io.BytesIO(global_assumptions_to_excel(global_assumptions)),
            sheet_name=None, engine="openpyxl",
        )
        puffer = _io.BytesIO()
        with pd.ExcelWriter(puffer, engine="openpyxl") as writer:
            for name, blatt in blaetter.items():
                if name in ("Preiskurven Monate", "Einspeisekurve"):
                    continue
                blatt.to_excel(writer, sheet_name=name, index=False)

        gelesen = excel_to_global_assumptions(puffer.getvalue())
        assert gelesen.zeitaufloesung == Zeitaufloesung.JAHR
        assert gelesen.einspeisekurve_pct_je_monat == pytest.approx(
            EINSPEISEKURVE_STANDARD_PCT
        )

    def test_ppa_felder_ueberstehen_den_projekt_rundlauf(self, project):
        from engine.io_excel import excel_to_projects, projects_to_excel

        project.ppa_anteil_pct = 0.35
        project.ppa_preis_eur_mwh = 72.5
        project.ppa_start_jahr = 2
        project.ppa_laufzeit_jahre = 12
        project.ppa_indexierung_pct_pa = 0.015

        gelesen = excel_to_projects(projects_to_excel([project]))[0]
        assert gelesen.ppa_anteil_pct == pytest.approx(0.35)
        assert gelesen.ppa_preis_eur_mwh == pytest.approx(72.5)
        assert gelesen.ppa_start_jahr == 2
        assert gelesen.ppa_laufzeit_jahre == 12
        assert gelesen.ppa_indexierung_pct_pa == pytest.approx(0.015)
