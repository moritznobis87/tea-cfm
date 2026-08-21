"""
Die Auslegung als Teil der Optimierung - Leistung und Kapazitaet als
Variablen desselben linearen Programms.

Der Dispatch in dispatch.py bekommt eine feste Auslegung vorgesetzt und
optimiert die Fahrweise. Hier faellt beides zusammen: `p` (Leistung) und
`E` (Kapazitaet) sind zwei zusaetzliche Spalten, und der Solver waehlt
sie mit. Das Ergebnis ist ein EXAKTES, stetiges Optimum - kein Raster,
keine Diskretisierung, kein Suchverfahren.

Dass das geht, liegt daran, dass beide Groessen ueberall LINEAR
auftreten:

    Ladeleistung   pv_in_speicher + netz_in_speicher - p     <= 0
    Entladung      entladung - p                             <= 0
    Fuellstand     soc - soc_max_pct * E                     <= 0
                   soc_min_pct * E - soc                     <= 0
    Anfangsstand   soc[0] - soc_start_pct * E - ...           = 0
    Kosten         a * p + b * E                          (linear)

Damit bleibt das Modell ein LP. Waeren die Fuellstandsgrenzen wie im
Dispatch als Variablengrenzen formuliert, ginge das nicht - eine
Variablengrenze kann keine andere Variable enthalten. Sie wandern hier
deshalb in die Restriktionsmatrix; das ist der Preis der Mitoptimierung
und der Grund, warum dieses LP rund doppelt so viele Zeilen hat.

Mehrere Jahre in EINEM Modell
-----------------------------
Die Stuetzjahre werden nicht nacheinander geloest, sondern gemeinsam:
Jedes bringt seinen eigenen Stundenblock mit, alle teilen sich `p` und
`E`. Nur so entsteht die Auslegung, die ueber die Laufzeit die beste ist
- getrennt geloest bekaeme jedes Jahr seine eigene, und aus vier
Antworten liesse sich keine machen.

Was dieses Modell NICHT kann - und warum es das Raster nicht ersetzt
--------------------------------------------------------------------
Es maximiert den BARWERT DES SPEICHERS: abgezinste Deckungsbeitraege
abzueglich Investition, mit einem pauschalen Steuersatz und der linearen
Abschreibung. Das ist eine saubere, aber vereinfachte Groesse.

Die Kennzahl, an der die Anwendung sonst alles misst - die EK-Rendite -
ist KEINE lineare Funktion der Auslegung. Sie haengt an Verlustvortrag,
Freibetrag, Gewerbesteuer, Tilgungsprofil und Fremdkapitalanteil, und
eine interne Verzinsung ist ohnehin nicht linearisierbar. Kein LP und
kein DP kann sie direkt maximieren.

Deshalb gibt es beides: Dieses Modell sagt exakt, WO das Optimum der
Dispatch-Oekonomie liegt. Das Raster (auslegung.py) sagt, was eine
gebaute Auslegung im vollen Cashflow wirklich einbringt. Die beiden
Antworten fallen regelmaessig auseinander - und dass sie es tun, ist
eine Auskunft und kein Fehler: Steuer und Fremdkapital verschieben das
Optimum zu kleineren Speichern, weil der Erloes besteuert wird, waehrend
die Investition voll zu bezahlen ist.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, vstack

from ..models import BatteryConfig, EffectiveAssumptions, SpeicherModus

# Die Spaltenindizes kommen aus dispatch.py und nicht aus einer zweiten
# Aufzaehlung: Beide Modelle beschreiben dieselbe Stundenbahn, und zwei
# Reihenfolgen davon waeren eine zu viel.
from .dispatch import (
    _ABREGELUNG,
    _ENTLADUNG,
    _N,
    _NETZ_SPEICHER,
    _PV_NETZ,
    _PV_SPEICHER,
    _SOC,
    vergleichsfall,
)
from .models import SolverFehler
from .valuation import Jahreseingabe

#: kW je MW und kWh je MWh.
_JE_EINHEIT = 1000.0


@dataclass(frozen=True)
class StetigesOptimum:
    """Was der Mitoptimierer herausrechnet."""

    leistung_mw: float
    kapazitaet_mwh: float
    #: Barwert des Speichers: abgezinste Deckungsbeitraege nach Steuer,
    #: abzueglich Investition und zuzueglich Abschreibungsschild.
    barwert_eur: float
    #: Investition bei dieser Auslegung.
    capex_eur: float
    #: Auf welchen Jahren gerechnet wurde.
    kalenderjahre: tuple[int, ...]
    #: Der abgezinste Wert OHNE Speicher - der Nullpunkt, gegen den der
    #: Barwert oben gemessen ist.
    vergleichswert_eur: float
    #: Der gesetzte Leistungsdeckel, falls einer galt.
    leistung_deckel_mw: float | None = None
    #: War die Leistung vorgegeben und nur die Kapazitaet gesucht?
    leistung_fest: bool = False

    @property
    def dauer_h(self) -> float:
        if self.leistung_mw <= 0:
            return 0.0
        return self.kapazitaet_mwh / self.leistung_mw

    @property
    def am_deckel(self) -> bool:
        """Stoesst die Leistung an die Einspeisegrenze?

        Dann ist der Punkt kein inneres Optimum, sondern der Rand: Der
        Speicher wuerde mehr Leistung nehmen, wenn der Anschluss sie
        hergaebe. Das ist eine Auskunft ueber den NETZANSCHLUSS und
        gehoert deshalb gesagt.
        """
        if self.leistung_deckel_mw is None:
            return False
        return self.leistung_mw >= self.leistung_deckel_mw - 1e-6

    @property
    def wirksam(self) -> bool:
        """Lohnt ueberhaupt einer? Ein Optimum bei null ist eine Antwort."""
        return self.leistung_mw > 1e-6 and self.kapazitaet_mwh > 1e-6


def _spaltenwahl(
    spalte: int, T: int, versatz: int, breite: int, faktor: float = 1.0
) -> csr_matrix:
    """Je Stunde genau eine Variable des Blocks bei `versatz`."""
    zeilen = np.arange(T)
    return csr_matrix(
        (np.full(T, faktor), (zeilen, versatz + zeilen * _N + spalte)),
        shape=(T, breite),
    )


def _festspalte(wert: float, T: int, spalte: int, breite: int) -> csr_matrix:
    """Dieselbe Spalte in jeder Zeile - fuer p und E."""
    zeilen = np.arange(T)
    return csr_matrix(
        (np.full(T, wert), (zeilen, np.full(T, spalte))), shape=(T, breite)
    )


def _barwertfaktoren(
    assumptions: EffectiveAssumptions, jahre: int, satz: float
) -> tuple[float, float]:
    """(Barwertfaktor der Betriebskosten, Steuerschild je Euro Investition).

    Das Steuerschild ist der Barwert der Abschreibung mal Steuersatz. Es
    macht die Investition guenstiger, als sie auf dem Papier ist - ohne
    ihn faende der Optimierer durchweg zu kleine Speicher.
    """
    steuer = assumptions.steuersatz_pct
    barwert_opex = sum(
        (1.0 - steuer) / (1.0 + satz) ** (i + 1) for i in range(jahre)
    )
    nutzungsdauer = assumptions.afa_nutzungsdauer_jahre or jahre
    schild = steuer * sum(
        (1.0 / nutzungsdauer) / (1.0 + satz) ** (i + 1)
        for i in range(int(nutzungsdauer))
    )
    return barwert_opex, schild


def optimum_stetig(
    assumptions: EffectiveAssumptions,
    vorlage: BatteryConfig,
    eingaben: Sequence[Jahreseingabe],
    gewichte: Sequence[tuple[float, float]],
    *,
    betriebsjahre: int,
    diskontsatz: float = 0.08,
    leistung_hoechstens_mw: float | None = None,
    leistung_fest_mw: float | None = None,
    vergleiche: Sequence[float] | None = None,
) -> StetigesOptimum:
    """Loest Fahrweise UND Auslegung in einem Zug.

    `gewichte` ist je Stuetzjahr das Paar (Erloesgewicht,
    Verschleissgewicht) - die abgezinste Zahl der Jahre, fuer die es
    steht, einmal mit und einmal ohne Preisniveau (siehe
    auslegung.hochrechnen; dieselbe Zerlegung, damit beide Verfahren
    dieselbe Laufzeit abbilden).

    `leistung_hoechstens_mw` deckelt die Speicherleistung. Ohne Deckel
    kann das Optimum weit ueber der PV-Anlage liegen: Ein Speicher, der
    nur aus PV laedt, ist zwar durch die Erzeugung begrenzt, seine
    ENTLADEleistung aber nur durch das Exportlimit - und das schoepft er
    aus, wenn die Preisspreizung es hergibt.

    `leistung_fest_mw` NAGELT die Leistung fest und laesst nur die
    Kapazitaet frei. Damit wird aus dem zweidimensionalen Problem ein
    eindimensionales: Gesucht ist nur noch die Speicherdauer. Der Fall
    ist der Graustromspeicher mit vereinbarter Netzbezugsleistung - dort
    ist die Leistung durch den Netzanschlussvertrag gegeben und keine
    Entwurfsgroesse mehr. Ist beides gesetzt, gewinnt der feste Wert.
    """
    steuer = assumptions.steuersatz_pct
    eta = np.sqrt(vorlage.roundtrip_wirkungsgrad)
    import_limit = (
        vorlage.netzbezug_limit_mw
        if vorlage.modus == SpeicherModus.GRAUSTROM else 0.0
    )

    laengen = [len(e.pv_mw) for e in eingaben]
    breite = sum(_N * T for T in laengen) + 2
    p_spalte, e_spalte = breite - 2, breite - 1

    a_eq: list[csr_matrix] = []
    b_eq: list[np.ndarray] = []
    a_ub: list[csr_matrix] = []
    b_ub: list[np.ndarray] = []
    c = np.zeros(breite)

    versatz = 0
    for eingabe, (w_erloes, w_verschleiss), T in zip(
        eingaben, gewichte, laengen, strict=True
    ):
        wahl = lambda s, f=1.0, v=versatz, t=T: _spaltenwahl(  # noqa: E731
            s, t, v, breite, f
        )

        # --- PV-Bilanz -----------------------------------------------
        a_eq.append(wahl(_PV_NETZ) + wahl(_PV_SPEICHER) + wahl(_ABREGELUNG))
        b_eq.append(eingabe.pv_mw.astype(float))

        # --- Fuellstandskopplung -------------------------------------
        # soc[t] - soc[t-1] - eta*laden + entladen/eta = 0, und in der
        # ersten Stunde steht statt soc[-1] der Anfangsstand - der jetzt
        # selbst eine Variable ist (soc_start_pct * E).
        zeilen: list[int] = []
        spalten: list[int] = []
        werte: list[float] = []
        for t in range(T):
            basis = versatz + t * _N
            zeilen += [t, t, t, t]
            spalten += [basis + _SOC, basis + _PV_SPEICHER,
                        basis + _NETZ_SPEICHER, basis + _ENTLADUNG]
            werte += [1.0, -eta, -eta, 1.0 / eta]
            if t > 0:
                zeilen.append(t)
                spalten.append(basis - _N + _SOC)
                werte.append(-1.0)
        zeilen.append(0)
        spalten.append(e_spalte)
        werte.append(-vorlage.soc_start_pct)
        a_eq.append(csr_matrix((werte, (zeilen, spalten)), shape=(T, breite)))
        b_eq.append(np.zeros(T))

        # Zyklischer Abschluss - Endstand gleich Anfangsstand.
        a_eq.append(csr_matrix(
            ([1.0, -vorlage.soc_start_pct],
             ([0, 0], [versatz + (T - 1) * _N + _SOC, e_spalte])),
            shape=(1, breite),
        ))
        b_eq.append(np.zeros(1))

        # --- Ungleichungen -------------------------------------------
        a_ub.append(wahl(_PV_NETZ) + wahl(_ENTLADUNG))
        b_ub.append(np.full(T, eingabe.export_limit_mw))

        gegen_p = _festspalte(-1.0, T, p_spalte, breite)
        a_ub.append(wahl(_PV_SPEICHER) + wahl(_NETZ_SPEICHER) + gegen_p)
        b_ub.append(np.zeros(T))
        a_ub.append(wahl(_ENTLADUNG) + gegen_p)
        b_ub.append(np.zeros(T))

        a_ub.append(wahl(_NETZ_SPEICHER))
        b_ub.append(np.full(T, import_limit))

        a_ub.append(wahl(_SOC) + _festspalte(
            -vorlage.soc_max_pct, T, e_spalte, breite
        ))
        b_ub.append(np.zeros(T))
        a_ub.append(wahl(_SOC, -1.0) + _festspalte(
            vorlage.soc_min_pct, T, e_spalte, breite
        ))
        b_ub.append(np.zeros(T))

        # --- Zielfunktion --------------------------------------------
        # linprog MINIMIERT, deshalb negative Erloese. Alles ist nach
        # Steuer und abgezinst - nur so ist es mit der Investition
        # vergleichbar, die in Jahr 0 voll zu zahlen ist.
        nach_steuer = (1.0 - steuer) * w_erloes
        c[versatz + _PV_NETZ:versatz + _N * T:_N] = (
            -nach_steuer * eingabe.grenzerloes_eur_mwh
        )
        c[versatz + _ENTLADUNG:versatz + _N * T:_N] = (
            -nach_steuer * eingabe.grenzerloes_eur_mwh
        )
        c[versatz + _NETZ_SPEICHER:versatz + _N * T:_N] = (
            nach_steuer * eingabe.preise_eur_mwh
        )
        halb = 0.5 * vorlage.degradationskosten_eur_mwh * (
            1.0 - steuer
        ) * w_verschleiss
        c[versatz + _PV_SPEICHER:versatz + _N * T:_N] += halb
        c[versatz + _NETZ_SPEICHER:versatz + _N * T:_N] += halb
        c[versatz + _ENTLADUNG:versatz + _N * T:_N] += halb

        versatz += _N * T

    # --- Kosten der Auslegung ----------------------------------------
    barwert_opex, schild = _barwertfaktoren(
        assumptions, betriebsjahre, diskontsatz
    )
    c[p_spalte] = _JE_EINHEIT * (
        assumptions.speicher_capex_leistung_eur_kw * (1.0 - schild)
        + assumptions.speicher_opex_eur_kw_jahr * barwert_opex
    )
    c[e_spalte] = _JE_EINHEIT * (
        assumptions.speicher_capex_energie_eur_kwh * (1.0 - schild)
    )

    grenzen = np.zeros((breite, 2))
    grenzen[:, 1] = np.inf
    if leistung_fest_mw is not None:
        # Untergrenze GLEICH Obergrenze: Die Leistung steht fest, gesucht
        # ist allein die Kapazitaet. Das ist keine Vereinfachung, sondern
        # der Fall eines Graustromspeichers mit vereinbarter
        # Netzbezugsleistung - dort ist die Leistung ein Vertrag und
        # keine Entwurfsgroesse.
        grenzen[p_spalte, :] = float(leistung_fest_mw)
    elif leistung_hoechstens_mw is not None:
        grenzen[p_spalte, 1] = float(leistung_hoechstens_mw)

    ergebnis = linprog(
        c,
        A_ub=vstack(a_ub, format="csr"), b_ub=np.concatenate(b_ub),
        A_eq=vstack(a_eq, format="csr"), b_eq=np.concatenate(b_eq),
        bounds=grenzen, method="highs",
    )
    if not ergebnis.success:
        raise SolverFehler(
            "Die Mitoptimierung der Auslegung liess sich nicht loesen: "
            f"{ergebnis.message} (Status {ergebnis.status})"
        )

    leistung = float(ergebnis.x[p_spalte])
    kapazitaet = float(ergebnis.x[e_spalte])

    # Der Zielwert enthaelt auch den Erloes der PV-Anlage selbst. Er
    # haengt nicht an p und E und verschiebt das Optimum deshalb nicht -
    # ausweisen darf man ihn aber nicht: Als "Barwert des Speichers"
    # waere er um ein Vielfaches zu gross. Abgezogen wird derselbe
    # Vergleichsfall, den auch das Raster benutzt.
    if vergleiche is None:
        vergleiche = [
            vergleichsfall(
                e.pv_mw, e.preise_eur_mwh, e.grenzerloes_eur_mwh,
                e.export_limit_mw,
            )[0]
            for e in eingaben
        ]
    vergleich = sum(
        (1.0 - steuer) * w_erloes * ziel_ohne
        for (w_erloes, _), ziel_ohne in zip(gewichte, vergleiche, strict=True)
    )

    return StetigesOptimum(
        leistung_mw=leistung,
        kapazitaet_mwh=kapazitaet,
        barwert_eur=float(-ergebnis.fun) - vergleich,
        capex_eur=_JE_EINHEIT * (
            leistung * assumptions.speicher_capex_leistung_eur_kw
            + kapazitaet * assumptions.speicher_capex_energie_eur_kwh
        ),
        kalenderjahre=tuple(e.kalenderjahr for e in eingaben),
        vergleichswert_eur=vergleich,
        # Eine FESTE Leistung ist kein Deckel: Sie kann nicht binden,
        # weil es nichts zu binden gibt. Ein Hinweis "die Leistung steht
        # am Deckel" waere dort schlicht falsch.
        leistung_deckel_mw=(
            None if leistung_fest_mw is not None
            else (
                float(leistung_hoechstens_mw)
                if leistung_hoechstens_mw is not None else None
            )
        ),
        leistung_fest=leistung_fest_mw is not None,
    )
