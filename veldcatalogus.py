"""
Veldcatalogus: de enige plek waar doelvelden voor de dealer-Excel invuller
zijn gedefinieerd. Wordt gebruikt door de ingest (welke waarden bewaren),
de mapping (keuzemenu voor Claude en de gebruiker) en het invullen.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Veld:
    id: str
    label: str
    eenheid: str | None   # standaardeenheid van de bronwaarde
    soort: str            # sleutel | artikel | component | vast | ruw | geen
    uitleg: str


VELDEN: list[Veld] = [
    Veld("sleutel_artikelcode", "Repair Care-artikelnummer (sleutel)", None, "sleutel",
         "Kolom met het Repair Care-artikelnummer, bv. 2010005. Gebruikt om het artikel op te zoeken."),
    Veld("sleutel_ean", "EAN-13 (sleutel)", None, "sleutel",
         "Kolom met de EAN-code van het artikel. Gebruikt om het artikel op te zoeken."),
    Veld("sleutel_omschrijving", "Omschrijving (sleutel, fuzzy)", None, "sleutel",
         "Kolom met de productnaam. Alleen als sleutel gebruiken als er geen artikelnummer of EAN is."),
    Veld("gn_code", "Douanetariefnummer (GN/HS-code)", None, "artikel",
         "Gecombineerde nomenclatuur / HS-code / Zolltarifnummer / tariff code, 8 of 10 cijfers."),
    Veld("netto_gewicht", "Nettogewicht per stuk", "g", "artikel",
         "Netto gewicht van één verkoopeenheid. Bij tweecomponentproducten de som van A en B."),
    Veld("bruto_gewicht", "Brutogewicht per stuk", "g", "artikel",
         "Bruto gewicht van één verkoopeenheid inclusief verpakking."),
    Veld("lengte", "Lengte per stuk", "mm", "artikel", "Lengte van één verkoopeenheid."),
    Veld("breedte", "Breedte per stuk", "mm", "artikel", "Breedte van één verkoopeenheid."),
    Veld("hoogte", "Hoogte per stuk", "mm", "artikel", "Hoogte van één verkoopeenheid."),
    Veld("collo_lengte", "Lengte verpakkingseenheid (collo)", "mm", "artikel", "Lengte van de doos/collo."),
    Veld("collo_breedte", "Breedte verpakkingseenheid (collo)", "mm", "artikel", "Breedte van de doos/collo."),
    Veld("collo_hoogte", "Hoogte verpakkingseenheid (collo)", "mm", "artikel", "Hoogte van de doos/collo."),
    Veld("ean", "EAN-13", None, "artikel", "EAN-code van het artikel (invullen, geen sleutel)."),
    Veld("omschrijving", "Omschrijving", None, "artikel", "Productnaam volgens Repair Care."),
    Veld("min_verkoophoeveelheid", "Minimale afname", "stuks", "artikel", "Minimale verkoophoeveelheid."),
    Veld("un_code", "UN-nummer", None, "component", "UN-nummer voor gevaarlijke stoffen (ADR)."),
    Veld("klasse", "Gevarenklasse (ADR)", None, "component", "ADR-klasse, bv. 9 of 8."),
    Veld("verpakkingsgroep", "Verpakkingsgroep", None, "component", "ADR-verpakkingsgroep, bv. III."),
    Veld("adr_naam", "Transportnaam (ADR)", None, "component", "Officiële vervoersnaam."),
    Veld("vlampunt", "Vlampunt", None, "component", "Vlampunt, bv. >62°C."),
    Veld("ufi", "UFI-code", None, "component", "Unique Formula Identifier."),
    Veld("voc", "VOC-gehalte", None, "component", "Vluchtige organische stoffen."),
    Veld("ghs", "GHS-pictogrammen", None, "component", "Lijst GHS-codes, bv. GHS07, GHS05."),
    Veld("geen", "Niet invullen", None, "geen",
         "Kolom overslaan: al gevuld door de dealer, of niet uit de productdata af te leiden."),
]

_VELD_INDEX = {v.id: v for v in VELDEN}

# Eenheden per dimensie, factor naar de basiseenheid (g resp. mm).
EENHEDEN: dict[str, dict[str, float]] = {
    "massa": {"g": 1.0, "kg": 1000.0},
    "lengte": {"mm": 1.0, "cm": 10.0, "m": 1000.0},
    "aantal": {"stuks": 1.0},
}

EENHEID_OPTIES: list[str | None] = [None, "g", "kg", "mm", "cm", "m", "stuks"]


def veld(veld_id: str) -> Veld | None:
    """Zoek een veld op id. Kent ook 'ruw:<kolom>' en 'vast:<sleutel>'."""
    if veld_id in _VELD_INDEX:
        return _VELD_INDEX[veld_id]
    if veld_id.startswith("ruw:") and len(veld_id) > 4:
        naam = veld_id[4:]
        return Veld(veld_id, naam, None, "ruw", f"Originele kolom '{naam}' uit het Product Data Sheet.")
    if veld_id.startswith("vast:") and len(veld_id) > 5:
        naam = veld_id[5:]
        return Veld(veld_id, naam, None, "vast", f"Vaste bedrijfswaarde '{naam}' uit vaste_waarden.json.")
    return None


def _dimensie(eenheid: str) -> str:
    for dim, tabel in EENHEDEN.items():
        if eenheid in tabel:
            return dim
    raise ValueError(f"Onbekende eenheid: {eenheid!r}")


def converteer(waarde: float, van: str | None, naar: str | None) -> float:
    """Reken een getal om tussen eenheden van dezelfde dimensie (g/kg, mm/cm/m)."""
    if van is None or naar is None or van == naar:
        return waarde
    dim_van, dim_naar = _dimensie(van), _dimensie(naar)
    if dim_van != dim_naar:
        raise ValueError(f"Kan {van!r} niet omrekenen naar {naar!r}")
    tabel = EENHEDEN[dim_van]
    return waarde * tabel[van] / tabel[naar]


def catalogus_voor_prompt(ruwe_kolommen: list[str], vaste_sleutels: dict[str, str]) -> list[dict]:
    """Volledige keuzelijst (vaste velden + ruw:* + vast:*) als platte dicts voor prompt en UI."""
    uit = [{"id": v.id, "label": v.label, "eenheid": v.eenheid, "uitleg": v.uitleg} for v in VELDEN]
    for kolom in ruwe_kolommen:
        v = veld(f"ruw:{kolom}")
        uit.append({"id": v.id, "label": v.label, "eenheid": None, "uitleg": v.uitleg})
    for sleutel, label in vaste_sleutels.items():
        uit.append({"id": f"vast:{sleutel}", "label": label, "eenheid": None,
                    "uitleg": f"Vaste bedrijfswaarde: {label}. Kan leeg zijn (dan wordt de cel gemarkeerd)."})
    return uit
