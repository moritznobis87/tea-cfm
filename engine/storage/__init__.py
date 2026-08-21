"""Co-Location-Bewertung: PV plus Batteriespeicher.

Drei Bausteine, streng getrennt:

    models     - was eingestellt wird und was herauskommt
    dispatch   - die stundenscharfe Optimierung (LP ueber HiGHS)
    economics  - der Grenzerloes aus der Foerderlogik und die Auswertung
    kosten     - was die Auslegung kostet
    valuation  - vom Stundendispatch zum Cashflow
    auslegung  - welche Groesse sich lohnt (Rasterlauf)

Der Dispatch kennt weder Foerderung noch Steuern noch Finanzierung: Er
bekommt je Stunde einen Grenzerloes und maximiert damit. Genau deshalb
verdoppelt sich die Foerderlogik nicht.
"""

from .auslegung import (
    DAUERN_STANDARD,
    DAUERN_STUNDEN,
    LEISTUNGSSCHRITT_MW,
    NACH_BARWERT,
    NACH_RENDITE,
    STUETZJAHRE_STANDARD,
    Kandidat,
    Rasterergebnis,
    Rasterpunkt,
    Stuetze,
    Stuetzjahr,
    leistungen_standard,
    leistungsstufen,
    raster,
    rasterlauf,
    stuetzen_vorbereiten,
)
from .dispatch import dispatch_jahr, vergleichsfall
from .economics import (
    Wertzerlegung,
    grenzerloes_je_stunde,
    jahreswert,
    negativstunden_maske,
    vollzyklen,
    zerlegung,
)
from .kosten import capex_eur, opex_jahr_eur
from .models import (
    BAHN_SPALTEN,
    BatteryConfig,
    SolverFehler,
    SpeicherModus,
    StorageDispatchResult,
    StorageJahreswert,
)
from .optimum import StetigesOptimum, optimum_stetig
from .valuation import (
    Jahreseingabe,
    SpeicherBeitrag,
    dispatch_mehrjahr,
    jahreseingabe,
)

__all__ = [
    "BAHN_SPALTEN",
    "DAUERN_STANDARD",
    "DAUERN_STUNDEN",
    "LEISTUNGSSCHRITT_MW",
    "NACH_BARWERT",
    "NACH_RENDITE",
    "STUETZJAHRE_STANDARD",
    "BatteryConfig",
    "Jahreseingabe",
    "Kandidat",
    "Rasterergebnis",
    "Rasterpunkt",
    "SolverFehler",
    "SpeicherModus",
    "StorageDispatchResult",
    "SpeicherBeitrag",
    "StorageJahreswert",
    "StetigesOptimum",
    "Stuetze",
    "Stuetzjahr",
    "Wertzerlegung",
    "capex_eur",
    "dispatch_jahr",
    "dispatch_mehrjahr",
    "jahreseingabe",
    "opex_jahr_eur",
    "optimum_stetig",
    "grenzerloes_je_stunde",
    "jahreswert",
    "negativstunden_maske",
    "leistungen_standard",
    "leistungsstufen",
    "raster",
    "stuetzen_vorbereiten",
    "rasterlauf",
    "vergleichsfall",
    "vollzyklen",
    "zerlegung",
]
