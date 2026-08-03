"""
Zahlen- und Wertformatierung im deutschen Format (Dezimalkomma,
Tausenderpunkt) - die EINZIGE Stelle der App, die Zahlen in Strings
verwandelt.

Warum kein `locale.setlocale`: Das ist prozessglobal, nicht threadsafe
und auf Streamlit Cloud nicht zuverlaessig verfuegbar (fehlende
de_AT/de_DE-Locales). Die Umstellung per String-Swap ist trivial,
deterministisch und ueberall gleich.
"""

from __future__ import annotations


def _de(zahl_str: str) -> str:
    """Wandelt US-Formatierung (1,234.56) in deutsche (1.234,56) um."""
    return zahl_str.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fmt_number(value: float | int | None, digits: int = 0, *,
               mit_vorzeichen: bool = False) -> str:
    """Zahl mit Tausenderpunkt und Dezimalkomma, z.B. 1.234.567,89.

    mit_vorzeichen setzt auch bei positiven Werten ein "+" - fuer
    Abweichungen, bei denen die Richtung die eigentliche Aussage ist.
    """
    if value is None:
        return "n/a"
    format_ = f"{value:+,.{digits}f}" if mit_vorzeichen else f"{value:,.{digits}f}"
    return _de(format_)


def fmt_eur(value: float | None, digits: int = 0) -> str:
    """Euro-Betrag, z.B. '1.234.567 €'."""
    if value is None:
        return "n/a"
    return f"{fmt_number(value, digits)} €"


def fmt_eur_kompakt(value: float | None) -> str:
    """Gerundeter Euro-Betrag fuer Kennzahlkacheln, z.B. '1,24 Mio €'.

    Die ausgeschriebene Form ('1.243.117 €') ist der eigentliche Grund,
    warum Kachelwerte frueher abgeschnitten wurden: Sie ist breiter als
    jede vertretbare Kachel und traegt eine Genauigkeit, die beim
    Ueberfliegen niemand braucht. Der genaue Betrag steht im Tooltip der
    Kachel (siehe app/components/kpi.py).
    """
    if value is None:
        return "n/a"
    betrag = abs(value)
    if betrag >= 1_000_000:
        return f"{fmt_number(value / 1_000_000, 2)} Mio €"
    if betrag >= 10_000:
        return f"{fmt_number(value / 1_000, 0)} Tsd €"
    return fmt_eur(value)


def fmt_pct(value: float | None, digits: int = 2) -> str:
    """Prozentwert aus einem Anteil (0.0743 -> '7,43 %')."""
    if value is None:
        return "n/a"
    return f"{fmt_number(value * 100, digits)} %"


def fmt_ct_kwh(value: float | None, digits: int = 2) -> str:
    """ct/kWh-Wert, z.B. '7,20 ct/kWh'."""
    if value is None:
        return "n/a"
    return f"{fmt_number(value, digits)} ct/kWh"


def fmt_kwp(value: float | None) -> str:
    """Anlagenleistung, z.B. '3.800 kWp'."""
    if value is None:
        return "n/a"
    return f"{fmt_number(value, 0)} kWp"


def fmt_dscr(value: float | None) -> str:
    """DSCR als Deckungsfaktor, z.B. '1,25x'."""
    if value is None:
        return "n/a"
    return f"{fmt_number(value, 2)}x"
