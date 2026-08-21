"""
Stundenscharfer Speicher-Dispatch als lineares Programm.

Ein Betriebsjahr, 8.760 (bzw. 8.784) Stunden, ein LP. Geloest wird mit
HiGHS ueber `scipy.optimize.linprog` - HiGHS ist seit SciPy 1.9 der
eingebaute Solver, es kommt also KEINE neue Abhaengigkeit dazu.

Die Formulierung
----------------
Je Stunde sechs nichtnegative Variablen:

    pv_ins_netz      PV direkt ins Netz
    pv_in_speicher   PV in den Speicher
    netz_in_speicher Netzbezug in den Speicher (nur Graustrom)
    entladung        Speicher ins Netz
    abregelung       PV, die verworfen wird
    soc              Fuellstand am Ende der Stunde

und vier Restriktionen:

    PV-Bilanz     pv_ins_netz + pv_in_speicher + abregelung = pv[t]
    SOC-Kopplung  soc[t] - soc[t-1] = eta*laden - entladung/eta
    Exportgrenze  pv_ins_netz + entladung <= export_limit
    Leistung      pv_in_speicher + netz_in_speicher <= p_max,
                  entladung <= p_max

Laden und Entladen sind GETRENNTE Variablen mit Untergrenze 0, gekoppelt
allein ueber den SOC. Binaervariablen braucht es dafuer nicht: Solange
der Grenzerloes positiv ist, ist gleichzeitiges Laden und Entladen wegen
eta < 1 strikt dominiert, und das LP vermeidet es von selbst.

Der eine Fall, in dem das nicht gilt
------------------------------------
Bei NEGATIVEM Grenzerloes wird man fuer den Verbrauch bezahlt, und der
Roundtrip-Verlust wird zur Einnahme: Gleichzeitig laden und entladen
haelt den Fuellstand konstant und erloest p*(eta^2 - 1) > 0. Ein
konstruierter Fall (Speicher voll, -50 EUR/MWh, keine PV) erzeugt so
600 EUR aus dem Nichts.

Ueber ein vollstaendiges Jahr mit echten Preisen tritt das nicht auf -
solange der Speicher nicht voll ist, ist schlichtes Laden immer besser.
Deshalb wird NICHT vorsorglich gesperrt (das schnitte einen realen
Optimalpunkt ab), sondern GEPRUEFT: `_ueberlappung` misst nach jedem
Lauf, ob es vorkam. Nur dann wird fuer die betroffenen Stunden das
Entladen gesperrt und einmal nachgerechnet - mit Hinweis im Ergebnis.

Was dieses Modul NICHT tut
--------------------------
Es kennt weder Foerderung noch Steuern noch Finanzierung. Es bekommt je
Stunde einen GRENZERLOES (siehe economics.py) und maximiert damit. Die
Trennung ist der Grund, warum sich die Foerderlogik nicht verdoppelt.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, vstack

from .models import (
    BAHN_SPALTEN,
    BatteryConfig,
    SolverFehler,
    SpeicherModus,
    StorageDispatchResult,
)

#: Variablen je Stunde, in dieser Reihenfolge im Loesungsvektor.
_PV_NETZ, _PV_SPEICHER, _NETZ_SPEICHER, _ENTLADUNG, _ABREGELUNG, _SOC = range(6)
_N = 6

#: Ab welcher gleichzeitigen Lade- UND Entladeleistung eine Stunde als
#: ueberlappend gilt. Grosszuegig gegen Solver-Rauschen, aber weit
#: unterhalb jeder wirtschaftlich bedeutsamen Menge.
_UEBERLAPPUNG_TOLERANZ_MW = 1e-6

#: Winziger Vorzug der Einspeisung gegenueber der Abregelung, um
#: Gleichstaende bei einem Grenzerloes von exakt null aufzuloesen.
_GLEICHSTAND_BONUS_EUR_MWH = 1e-6


def _auswahl(spalte: int, T: int, faktor: float = 1.0) -> csr_matrix:
    """Matrix, die je Stunde genau eine Variable auswaehlt."""
    zeilen = np.arange(T)
    return csr_matrix(
        (np.full(T, faktor), (zeilen, zeilen * _N + spalte)),
        shape=(T, _N * T),
    )


def _soc_kopplung(T: int, eta_lade: float, eta_entlade: float) -> csr_matrix:
    """soc[t] - soc[t-1] - eta*laden + entladung/eta = 0.

    Die einzige Restriktion, die die Stunden miteinander verbindet - und
    damit der Grund, warum sich der Dispatch nicht Stunde fuer Stunde
    greedy loesen laesst.
    """
    zeilen: list[int] = []
    spalten: list[int] = []
    werte: list[float] = []
    for t in range(T):
        basis = t * _N
        zeilen += [t, t, t, t]
        spalten += [
            basis + _SOC,
            basis + _PV_SPEICHER,
            basis + _NETZ_SPEICHER,
            basis + _ENTLADUNG,
        ]
        werte += [1.0, -eta_lade, -eta_lade, 1.0 / eta_entlade]
        if t > 0:
            zeilen.append(t)
            spalten.append((t - 1) * _N + _SOC)
            werte.append(-1.0)
    return csr_matrix((werte, (zeilen, spalten)), shape=(T, _N * T))


def _loese(
    pv_mw: np.ndarray,
    grenzerloes_eur_mwh: np.ndarray,
    preis_eur_mwh: np.ndarray,
    batterie: BatteryConfig,
    export_limit_mw: float,
    entladung_gesperrt: np.ndarray | None = None,
) -> tuple[np.ndarray, float]:
    """Ein Jahr loesen; gibt die Stundenbahn und den Zielwert zurueck."""
    T = len(pv_mw)
    p_max = batterie.leistung_mw if batterie.wirksam else 0.0
    soc_min = batterie.kapazitaet_mwh * batterie.soc_min_pct
    soc_max = batterie.kapazitaet_mwh * batterie.soc_max_pct
    soc_start = batterie.kapazitaet_mwh * batterie.soc_start_pct
    soc_start = float(np.clip(soc_start, soc_min, soc_max))
    import_limit = (
        batterie.netzbezug_limit_mw
        if batterie.modus == SpeicherModus.GRAUSTROM and batterie.wirksam
        else 0.0
    )

    # --- Gleichungen -------------------------------------------------
    a_eq = [_auswahl(_PV_NETZ, T) + _auswahl(_PV_SPEICHER, T)
            + _auswahl(_ABREGELUNG, T)]
    b_eq = [pv_mw.astype(float)]

    kopplung = _soc_kopplung(T, batterie.eta_lade, batterie.eta_entlade)
    rechte_seite = np.zeros(T)
    rechte_seite[0] = soc_start
    a_eq.append(kopplung)
    b_eq.append(rechte_seite)

    # Zyklischer Abschluss: Der Fuellstand am Jahresende ist der zu
    # Jahresbeginn. Ohne ihn leerte der Optimierer den Speicher in der
    # letzten Stunde und buchte einen Erloes, der aus dem Anfangsbestand
    # stammt - ein Wert, den es kein zweites Mal gibt.
    a_eq.append(
        csr_matrix(([1.0], ([0], [(T - 1) * _N + _SOC])), shape=(1, _N * T))
    )
    b_eq.append(np.array([soc_start]))

    # --- Ungleichungen -----------------------------------------------
    a_ub = [
        _auswahl(_PV_NETZ, T) + _auswahl(_ENTLADUNG, T),
        _auswahl(_PV_SPEICHER, T) + _auswahl(_NETZ_SPEICHER, T),
        _auswahl(_ENTLADUNG, T),
        _auswahl(_NETZ_SPEICHER, T),
    ]
    b_ub = [
        np.full(T, export_limit_mw),
        np.full(T, p_max),
        np.full(T, p_max),
        np.full(T, import_limit),
    ]

    # --- Zielfunktion ------------------------------------------------
    # linprog MINIMIERT, deshalb negative Erloese.
    #
    # Einspeisung wird mit dem GRENZERLOES bewertet (Marktpreis plus
    # Foerderung, siehe economics.py), Netzbezug mit dem reinen
    # Marktpreis: Wer Strom kauft, zahlt den Marktpreis - eine
    # Einspeiseverguetung gibt es darauf nicht.
    c = np.zeros(_N * T)
    c[_PV_NETZ::_N] = -grenzerloes_eur_mwh
    c[_ENTLADUNG::_N] = -grenzerloes_eur_mwh
    c[_NETZ_SPEICHER::_N] = preis_eur_mwh
    # Verschleiss auf den Durchsatz: 0,5 x (Laden + Entladen), damit ein
    # voller Zyklus einmal zaehlt und nicht zweimal.
    halb = 0.5 * batterie.degradationskosten_eur_mwh
    c[_PV_SPEICHER::_N] += halb
    c[_NETZ_SPEICHER::_N] += halb
    c[_ENTLADUNG::_N] += halb
    # Gleichstand aufloesen: Bei einem Grenzerloes von exakt null bringt
    # Einspeisen genauso viel wie Abregeln, und der Solver greift
    # willkuerlich zu. Der Zielwert stimmt dann zwar, die ausgewiesene
    # Bahn aber nicht - in den Aurora-Reihen stehen tausende Stunden mit
    # glatt 0,00 EUR/MWh, und sie erschienen samt und sonders als
    # Abregelung.
    #
    # Ein winziger Bonus auf die Einspeisung entscheidet solche Faelle
    # zugunsten des Einspeisens. Er ist um acht Groessenordnungen
    # kleiner als ein Marktpreis; falsch entschieden wird damit nur im
    # Bereich |v| < 1e-6 EUR/MWh, und dort gibt es nichts zu entscheiden.
    c[_PV_NETZ::_N] -= _GLEICHSTAND_BONUS_EUR_MWH

    grenzen = np.zeros((_N * T, 2))
    grenzen[:, 1] = np.inf
    grenzen[_SOC::_N, 0] = soc_min
    grenzen[_SOC::_N, 1] = soc_max
    if entladung_gesperrt is not None:
        grenzen[_ENTLADUNG::_N, 1] = np.where(entladung_gesperrt, 0.0, np.inf)

    ergebnis = linprog(
        c,
        A_ub=vstack(a_ub, format="csr"), b_ub=np.concatenate(b_ub),
        A_eq=vstack(a_eq, format="csr"), b_eq=np.concatenate(b_eq),
        bounds=grenzen, method="highs",
    )
    if not ergebnis.success:
        raise SolverFehler(
            f"Der Dispatch liess sich nicht loesen: {ergebnis.message} "
            f"(Status {ergebnis.status})"
        )
    return ergebnis.x.reshape(T, _N), float(-ergebnis.fun)


#: Der Speicher, den es nicht gibt - Bezugspunkt jedes Wertbeitrags.
_KEIN_SPEICHER = BatteryConfig(aktiv=False, leistung_mw=0.0, kapazitaet_mwh=0.0)


def vergleichsfall(
    pv_mw: np.ndarray,
    preis_eur_mwh: np.ndarray,
    grenzerloes_eur_mwh: np.ndarray,
    export_limit_mw: float,
) -> tuple[float, float]:
    """Zielwert und Abregelung des Laufs OHNE Speicher.

    Gibt (zielwert_eur, abregelung_mwh) zurueck.

    Der Vergleichsfall haengt an KEINER Eigenschaft des Speichers. Mit
    `aktiv=False` ist die Leistungsgrenze null, der Fuellstand kann sich
    also nicht bewegen; Kapazitaet, Wirkungsgrad und Verschleiss
    multiplizieren dann ausschliesslich Variablen, die auf null
    festliegen. Genau deshalb steht diese Funktion hier: Ein Rasterlauf
    ueber fuenfzig Auslegungen rechnete den identischen Vergleichsfall
    sonst fuenfzigmal, und er ist so teuer wie ein Lauf MIT Speicher.
    """
    bahn, zielwert = _loese(
        pv_mw, grenzerloes_eur_mwh, preis_eur_mwh, _KEIN_SPEICHER,
        export_limit_mw,
    )
    return zielwert, float(bahn[:, _ABREGELUNG].sum())


def _ueberlappung(bahn: np.ndarray) -> np.ndarray:
    """Stunden, in denen gleichzeitig geladen UND entladen wird.

    Siehe Modulkopf: mathematisch moeglich bei negativem Grenzerloes,
    ueber ein echtes Jahr praktisch nie. Geprueft statt vorsorglich
    gesperrt.
    """
    laden = bahn[:, _PV_SPEICHER] + bahn[:, _NETZ_SPEICHER]
    entladen = bahn[:, _ENTLADUNG]
    return (laden > _UEBERLAPPUNG_TOLERANZ_MW) & (
        entladen > _UEBERLAPPUNG_TOLERANZ_MW
    )


def dispatch_jahr(
    pv_mw: np.ndarray,
    preis_eur_mwh: np.ndarray,
    grenzerloes_eur_mwh: np.ndarray,
    batterie: BatteryConfig,
    export_limit_mw: float,
    jahr: int = 1,
    kalenderjahr: int = 0,
    vergleich: tuple[float, float] | None = None,
) -> StorageDispatchResult:
    """Ein Betriebsjahr optimieren - mit und ohne Speicher.

    Der Vergleichsfall entsteht im SELBEN Verfahren mit einem
    unwirksamen Speicher: dieselben Preise, dieselbe Foerderlogik,
    dasselbe Exportlimit, nur ohne Batterie. Nur so ist die Differenz
    eine Aussage ueber den Speicher und nicht ueber zwei verschiedene
    Rechenwege.

    `vergleich` ist das Ergebnis von `vergleichsfall` fuer DIESE Stunden,
    falls es schon vorliegt. Der Rasterlauf der Auslegungssuche rechnet
    es einmal je Stuetzjahr und reicht es fuer jede Auslegung durch -
    ohne diesen Weg waere die Haelfte seiner Rechenzeit die immer gleiche
    Antwort auf die immer gleiche Frage.
    """
    for name, reihe in (("PV", pv_mw), ("Preis", preis_eur_mwh),
                        ("Grenzerloes", grenzerloes_eur_mwh)):
        if len(reihe) != len(pv_mw):
            raise ValueError(
                f"{name}-Reihe hat {len(reihe)} Werte, erwartet {len(pv_mw)}"
            )
    if export_limit_mw <= 0:
        raise ValueError("Das Exportlimit muss groesser als null sein")

    hinweise: list[str] = []
    bahn, zielwert = _loese(
        pv_mw, grenzerloes_eur_mwh, preis_eur_mwh, batterie, export_limit_mw
    )

    betroffen = _ueberlappung(bahn)
    if betroffen.any():
        # Nur jetzt sperren, und nur hier: Vorsorglich gesperrt haette
        # es einen realen Optimalpunkt abgeschnitten.
        hinweise.append(
            f"In {int(betroffen.sum())} Stunden mit negativem Grenzerloes "
            "wurde gleichzeitiges Laden und Entladen unterbunden; diese "
            "Stunden wurden ohne Entlademoeglichkeit nachgerechnet."
        )
        bahn, zielwert = _loese(
            pv_mw, grenzerloes_eur_mwh, preis_eur_mwh, batterie,
            export_limit_mw, entladung_gesperrt=betroffen,
        )

    # Der Vergleichsfall: dieselben Preise, dieselben Foerderregeln,
    # dasselbe Exportlimit - nur ohne Speicher. Ohne ihn gaebe es keinen
    # Massstab fuer den Wertbeitrag. Die Abregelung dieses Laufs ist der
    # Bezugspunkt der Rueckgewinnung und muss deshalb mit heraus.
    zielwert_ohne, abregelung_ohne = vergleich or vergleichsfall(
        pv_mw, preis_eur_mwh, grenzerloes_eur_mwh, export_limit_mw
    )

    vollstaendig = np.column_stack([
        pv_mw,
        bahn[:, _PV_NETZ],
        bahn[:, _PV_SPEICHER],
        bahn[:, _NETZ_SPEICHER],
        bahn[:, _ENTLADUNG],
        bahn[:, _ABREGELUNG],
        bahn[:, _SOC],
        preis_eur_mwh,
        grenzerloes_eur_mwh,
    ])
    assert vollstaendig.shape[1] == len(BAHN_SPALTEN)

    return StorageDispatchResult(
        jahr=jahr,
        kalenderjahr=kalenderjahr,
        bahn=vollstaendig,
        zielwert_eur=zielwert,
        zielwert_pv_only_eur=zielwert_ohne,
        abregelung_pv_only_mwh=abregelung_ohne,
        hinweise=hinweise,
    )
