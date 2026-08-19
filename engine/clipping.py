"""
Einspeisebegrenzung: Wie viel Energie faellt der Kappung zum Opfer?

In Oesterreich darf am Netzverknuepfungspunkt hoechstens ein Anteil der
Modulspitzenleistung eingespeist werden - ueblich 70 %. Was darueber
liegt, geht verloren: Der Wechselrichter faehrt herunter, die Energie
wird nie erzeugt.

**Warum das eine Stundenreihe braucht.** Eine Monats- oder Jahresmenge
verraet nicht, in welchen Stunden die Leistung ueber der Grenze lag -
und genau darauf kommt es an. Die Kappung trifft ausschliesslich die
Mittagsstunden des Sommerhalbjahrs, und die sind zugleich die
preisschwaechsten des Jahres.

Die Rechenregel
---------------
Der Verlustanteil haengt an drei Groessen, und an keiner weiteren:

1. der FORM der Stundenreihe (normiert auf Summe 1),
2. dem Limit als Anteil der Modulspitzenleistung (0,70),
3. den Vollbenutzungsstunden des Projekts (kWh/kWp).

Die Nennleistung selbst kuerzt sich heraus. Denn mit

    Limit [kW]      = limit_pct * kWp
    Jahresmenge     = kWp * kwh_kwp

ist das Limit, ausgedrueckt als Anteil der Jahresmenge, schlicht

    limit_anteil = limit_pct / kwh_kwp

Der Verlust ist dann die Summe dessen, was je Stunde ueber diesem
Anteil liegt. Eine 10-MWp- und eine 100-MWp-Anlage mit gleicher Form
und gleichen Vollbenutzungsstunden verlieren denselben Prozentsatz.

Das ist mehr als eine Vereinfachung: Es macht die Analyse uebertragbar.
Ein einmal ermittelter Befund gilt fuer jedes Projekt mit aehnlichem
Profil und aehnlichen Vollbenutzungsstunden - die Grundlage des
Kappungskatalogs in den globalen Annahmen.

Grenzen der Aussage
-------------------
**Stundenmittel unterschaetzen die Kappung.** Innerhalb einer Stunde
schwankt die Leistung um ihren Mittelwert; was oberhalb der Grenze lag,
ist auch dann verloren, wenn das Stundenmittel darunter bleibt. Die
Zahlen hier sind deshalb eine UNTERGRENZE. Mit einer 15-Minuten-Reihe
faellt der Verlust groesser aus.

**Die Reihe muss die Einspeisung sein**, nicht die DC-Erzeugung: Das
Limit gilt am Netzverknuepfungspunkt, hinter dem Wechselrichter. Ist
die Reihe bereits AC-seitig gekappt (erkennbar an einem Plateau
identischer Hoechstwerte), rechnet dieses Modul eine Kappung ein
zweites Mal - `plateauverdacht()` prueft darauf.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import MONATE

#: Stunden je Monat im Normaljahr - dieselbe Aufteilung wie in
#: io_lastgang, hier bewusst noch einmal ausgeschrieben (waere sie dort
#: falsch, koennte ein Test, der sie von dort bezoege, das nicht
#: bemerken).
_STUNDEN_JE_MONAT = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
_STUNDEN_JE_MONAT_SCHALT = [744, 696, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]

#: Welcher Anteil der Stunden im Spitzenband GENAU auf dem Hoechstwert
#: liegen muss, damit die Reihe als bereits gekappt gilt.
#:
#: Zwei naheliegende Pruefungen taugen nicht. "Kommt der Hoechstwert oft
#: vor?" scheitert an der Rundung - die hinterlegten Reihen sind auf
#: 0,1 kW gerundet, bei 16,2 kW Spitze gibt es nur rund 160 moegliche
#: Werte, da haeuft sich jeder. "Ist er haeufiger als seine Nachbarn?"
#: scheitert daran, dass die Bandbreite eines gerundeten Werts selbst
#: von der Rundung abhaengt.
#:
#: Was Clipping wirklich auszeichnet: Die Anlage steht dann die ganze
#: Zeit am selben Wert - fast ALLES im Spitzenband liegt exakt auf dem
#: Maximum. Gemessen an den hinterlegten Reihen: Pult 5 %, Tracker 13 %
#: (beide ungekappt), kuenstlich gekappt ueber 90 %.
_PLATEAU_ANTEIL = 0.4

#: Unterkante des Spitzenbands, in dem gezaehlt wird.
_PLATEAU_BANDUNTERKANTE = 0.95


@dataclass(frozen=True)
class Kappung:
    """Was eine Einspeisegrenze dieses Projekt kostet."""

    #: Anteil der Jahreserzeugung, der verloren geht (0..1).
    verlust_pct: float
    #: Anteil je Kalendermonat, bezogen auf die Erzeugung DIESES Monats.
    #: Das ist die Groesse, die eine Monatsrechnung braucht - ein
    #: Jahreswert allein verteilte den Verlust auf Dezember mit, wo er
    #: nie entsteht.
    verlust_pct_je_monat: list[float]
    #: Anteil der Jahreserzeugung je Monat NACH der Kappung, Summe 1 -
    #: die Einspeisekurve der gekappten Anlage.
    kurve_nach_kappung_pct_je_monat: list[float]
    #: Hoechste Stundenleistung als Anteil der Modulspitzenleistung.
    #: Liegt sie unter dem Limit, kostet die Grenze nichts.
    spitze_pct_kwp: float
    #: Zahl der Stunden im Jahr, in denen gekappt wird.
    betroffene_stunden: int
    #: Verlorene Energie je Stunde, als Anteil der Jahreserzeugung -
    #: Grundlage der stundenscharfen Bewertung.
    verlust_anteil_je_stunde: list[float] = field(repr=False)
    hinweise: list[str] = field(default_factory=list)

    @property
    def greift(self) -> bool:
        return self.betroffene_stunden > 0


def plateauverdacht(reihe: list[float]) -> bool:
    """Sieht die Reihe aus, als waere sie bereits gekappt?

    Bei echtem Clipping steht die Anlage stundenlang exakt am Limit -
    der Hoechstwert kommt dann um ein Vielfaches haeufiger vor als die
    Werte knapp darunter. Bei einer freien Reihe ist das Maximum ein
    Ausreisser und eher seltener als seine Nachbarn.

    Verglichen wird deshalb, nicht gezaehlt: Absolute Haeufigkeiten
    haengen an der Rundung der Reihe, das Verhaeltnis nicht.
    """
    spitze = max(reihe, default=0.0)
    if spitze <= 0:
        return False
    im_band = [w for w in reihe if w >= spitze * _PLATEAU_BANDUNTERKANTE]
    if len(im_band) < 2:
        return False
    am_limit = sum(1 for w in im_band if w >= spitze * 0.9999)
    return am_limit / len(im_band) >= _PLATEAU_ANTEIL


def kappungsverlust(
    reihe: list[float],
    limit_pct: float,
    kwh_kwp: float,
) -> Kappung:
    """Verlust durch eine Einspeisegrenze.

    reihe:      Stundenwerte eines Jahres in beliebiger Einheit - nur
                ihre Form geht ein.
    limit_pct:  Grenze als Anteil der Modulspitzenleistung (0,70).
    kwh_kwp:    Vollbenutzungsstunden des Projekts.

    Die Nennleistung wird nicht gebraucht (siehe Modulkopf).
    """
    if limit_pct <= 0:
        raise ValueError("Ein Einspeiselimit von null oder weniger ergibt keinen Sinn.")
    if kwh_kwp <= 0:
        raise ValueError("Ohne Vollbenutzungsstunden laesst sich nicht kappen.")

    gesamt = sum(reihe)
    if gesamt <= 0:
        raise ValueError("Die Reihe summiert sich auf null.")

    anteile = [w / gesamt for w in reihe]
    # Das Limit als Anteil der JAHRESmenge - die Herleitung steht im
    # Modulkopf. Hier kuerzt sich die Nennleistung heraus.
    limit_anteil = limit_pct / kwh_kwp

    verlust_je_stunde = [max(0.0, a - limit_anteil) for a in anteile]
    verlust_gesamt = sum(verlust_je_stunde)

    laengen = (
        _STUNDEN_JE_MONAT_SCHALT
        if len(reihe) == sum(_STUNDEN_JE_MONAT_SCHALT)
        else _STUNDEN_JE_MONAT
    )

    je_monat: list[float] = []
    erzeugt_je_monat: list[float] = []
    start = 0
    for laenge in laengen:
        je_monat.append(sum(verlust_je_stunde[start:start + laenge]))
        erzeugt_je_monat.append(sum(anteile[start:start + laenge]))
        start += laenge

    # Zwei verschiedene Bezugsgroessen, und die Verwechslung waere
    # teuer: verlust_pct_je_monat misst am Ertrag DIESES Monats (fuer
    # den Mengenabzug einer Monatsrechnung), die Kurve danach am
    # Jahresertrag (als neue Einspeisekurve).
    verlust_pct_je_monat = [
        (v / e if e > 0 else 0.0)
        for v, e in zip(je_monat, erzeugt_je_monat, strict=True)
    ]
    rest = [e - v for e, v in zip(erzeugt_je_monat, je_monat, strict=True)]
    rest_summe = sum(rest)
    kurve_nach = (
        [r / rest_summe for r in rest] if rest_summe > 0 else [0.0] * MONATE
    )

    spitze_pct_kwp = max(anteile, default=0.0) * kwh_kwp

    hinweise: list[float] = []
    if plateauverdacht(reihe):
        hinweise.append(
            "Die Reihe zeigt ein Plateau identischer Höchstwerte – sie "
            "dürfte bereits gekappt sein. Eine zweite Kappung würde den "
            "Verlust doppelt zählen."
        )
    if any(w < 0 for w in reihe):
        hinweise.append(
            "Die Reihe enthält negative Werte (Bezug?). Sie gehen mit "
            "ihrem Vorzeichen in die Jahressumme ein."
        )

    return Kappung(
        verlust_pct=verlust_gesamt,
        verlust_pct_je_monat=verlust_pct_je_monat,
        kurve_nach_kappung_pct_je_monat=kurve_nach,
        spitze_pct_kwp=spitze_pct_kwp,
        betroffene_stunden=sum(1 for v in verlust_je_stunde if v > 0),
        verlust_anteil_je_stunde=verlust_je_stunde,
        hinweise=hinweise,
    )


def limit_ohne_verlust(reihe: list[float], kwh_kwp: float) -> float:
    """Kleinstes Limit (Anteil der kWp), bei dem nichts verloren geht.

    Das ist die Zahl, die eine Netzausbau-Diskussion braucht: Nicht
    "wie viel kostet 70 %", sondern "ab wo kostet es gar nichts mehr".
    Sie ist identisch mit der hoechsten Stundenleistung, gemessen an
    der Modulspitzenleistung.
    """
    gesamt = sum(reihe)
    if gesamt <= 0:
        raise ValueError("Die Reihe summiert sich auf null.")
    return max(w / gesamt for w in reihe) * kwh_kwp
