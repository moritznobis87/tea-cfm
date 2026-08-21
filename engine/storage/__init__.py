"""Co-Location-Bewertung: PV plus Batteriespeicher.

Drei Bausteine, streng getrennt:

    models     - was eingestellt wird und was herauskommt
    dispatch   - die stundenscharfe Optimierung (LP ueber HiGHS)
    economics  - der Grenzerloes aus der Foerderlogik und die Auswertung

Der Dispatch kennt weder Foerderung noch Steuern noch Finanzierung: Er
bekommt je Stunde einen Grenzerloes und maximiert damit. Genau deshalb
verdoppelt sich die Foerderlogik nicht.
"""

from .dispatch import dispatch_jahr
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
from .valuation import (
    Jahreseingabe,
    SpeicherBeitrag,
    dispatch_mehrjahr,
    jahreseingabe,
)

__all__ = [
    "BAHN_SPALTEN",
    "BatteryConfig",
    "Jahreseingabe",
    "SolverFehler",
    "SpeicherModus",
    "StorageDispatchResult",
    "SpeicherBeitrag",
    "StorageJahreswert",
    "Wertzerlegung",
    "capex_eur",
    "dispatch_jahr",
    "dispatch_mehrjahr",
    "jahreseingabe",
    "opex_jahr_eur",
    "grenzerloes_je_stunde",
    "jahreswert",
    "negativstunden_maske",
    "vollzyklen",
    "zerlegung",
]
