"""
Mapping van dealerkolommen naar doelvelden: datamodel, JSON-schema voor een
afgedwongen Claude-antwoord, en de aanroep zelf. Alleen de kopregel-
kandidaten en een paar voorbeeldrijen gaan naar de API, nooit het hele bestand.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

from veldcatalogus import EENHEID_OPTIES

MODEL = "claude-opus-5"
MAX_TOKENS = 32000  # ruim: 150+ kolommen × ~40 tokens plus thinking
MAPPING_TIMEOUT_SECONDS = 180
ZEKERHEDEN = ["hoog", "middel", "laag"]

SYSTEEMPROMPT = """Je helpt een medewerker van Repair Care (fabrikant van houtreparatieproducten) om
invulbestanden van dealers automatisch te vullen met productdata.

Je krijgt de eerste rijen van een dealerbestand (Excel). Bepaal:
1. kopregel_index: de 0-gebaseerde index van de rij met kolomkoppen.
2. data_start_index: de 0-gebaseerde index van de eerste echte artikelrij of de
   eerste lege invulrij. Sla extra kopregels, technische veldcodes, eenheden en
   instructierijen onder de kolomkoppen over. Deze index ligt na kopregel_index.
   Bij een leeg sjabloon mag dit de rij direct na de laatste werkbladrij zijn.
3. Per kolom uit die kopregel: welk doelveld uit de catalogus de dealer vraagt.
   - Behoud de kolomkoppen exact en geef één item per kolom in de oorspronkelijke
     volgorde, ook bij dubbele labels. Gebruik andere kop- en instructierijen
     alleen als context; voeg hun tekst niet aan de gekozen kolomkop toe.
   - Kolommen die het artikel identificeren krijgen een sleutel_-veld
     (sleutel_artikelcode voor het Repair Care-artikelnummer / Hersteller-Artikelnummer /
     supplier item number; sleutel_ean voor EAN/GTIN; sleutel_omschrijving alleen als
     er geen ander sleutelveld is). Het eigen artikelnummer van de dealer is GEEN sleutel.
     Markeer élke kolom die het artikel identificeert als sleutel — artikelnummer én EAN
     (én omschrijving als beide ontbreken); meerdere sleutelkolommen zijn normaal.
     De tool probeert ze in volgorde artikelcode → EAN → omschrijving.
   - Kolommen die al door de dealer gevuld zijn of niet uit productdata af te leiden zijn
     krijgen 'geen'.
   - Kies bij gewichten en maten de eenheid die de dealer vraagt (uit de kop, de
     voorbeeldwaarden of de context). Onbekend: g voor gewicht, cm voor maten
     (gebruikelijk in dealer-/ERP-stamdata), en zekerheid 'middel'. Geen eenheid van
     toepassing: lege tekst "". De 'broneenheid' in de catalogus is de eenheid van onze
     data, niet wat de dealer vraagt.
   - Gebruik 'vast:...'-velden voor bedrijfsgegevens zoals land van oorsprong of Bundesland.
   - Gebruik 'ruw:...'-velden alleen als geen gewoon veld past.
   - Koppel geen tekstveld aan een kolom die alleen cijfers, een keuzevak of een x
     verwacht. Losse kenmerkopties (bijvoorbeeld MW-kolommen) krijgen 'geen' als
     de catalogus geen expliciete omzetting naar de gevraagde x-markering biedt.
4. zekerheid: hoog als kop en voorbeelden eenduidig zijn, middel bij een aanname
   (bijvoorbeeld de eenheid), laag als je gokt.
5. toelichting: één korte zin, alleen bij middel/laag of bij 'geen'.

Antwoord uitsluitend met JSON volgens het opgelegde schema.

=== VELDCATALOGUS ===
"""


@dataclass
class KolomMapping:
    kolom: str
    doelveld: str
    eenheid: str | None
    zekerheid: str
    toelichting: str


@dataclass
class Mapping:
    kopregel_index: int
    kolommen: list[KolomMapping] = field(default_factory=list)
    opmerkingen: str = ""
    data_start_index: int | None = None

    def sleutels(self) -> list[KolomMapping]:
        return [k for k in self.kolommen if k.doelveld.startswith("sleutel_")]

    def doelen(self) -> list[KolomMapping]:
        return [k for k in self.kolommen if not k.doelveld.startswith("sleutel_") and k.doelveld != "geen"]

    def naar_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def uit_dict(d: dict) -> "Mapping":
        return Mapping(
            kopregel_index=int(d["kopregel_index"]),
            kolommen=[KolomMapping(k["kolom"], k["doelveld"], (k.get("eenheid") or None),
                                   k.get("zekerheid", "laag"), k.get("toelichting", ""))
                      for k in d.get("kolommen", [])],
            opmerkingen=d.get("opmerkingen", "") or "",
            data_start_index=(int(d["data_start_index"])
                              if d.get("data_start_index") is not None else None),
        )


def mapping_schema(doelveld_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "kopregel_index": {"type": "integer"},
            "data_start_index": {"type": "integer"},
            "kolommen": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kolom": {"type": "string"},
                        "doelveld": {"type": "string", "enum": list(doelveld_ids)},
                        "eenheid": {"type": "string", "enum": [o or "" for o in EENHEID_OPTIES]},
                        "zekerheid": {"type": "string", "enum": ZEKERHEDEN},
                        "toelichting": {"type": "string"},
                    },
                    "required": ["kolom", "doelveld", "eenheid", "zekerheid", "toelichting"],
                    "additionalProperties": False,
                },
            },
            "opmerkingen": {"type": "string"},
        },
        "required": ["kopregel_index", "data_start_index", "kolommen", "opmerkingen"],
        "additionalProperties": False,
    }


def lege_mapping(kopregel_index: int, koppen: list[str]) -> Mapping:
    return Mapping(kopregel_index, [KolomMapping(k, "geen", None, "laag", "") for k in koppen])


def bouw_fragment(rijen: list[list], tabblad: str, totaal_rijen: int) -> str:
    regels = [f"Tabblad: {tabblad}. Totaal {totaal_rijen} rijen. Eerste rijen (index: cellen):"]
    for i, rij in enumerate(rijen):
        cellen = [("" if c is None else str(c)) for c in rij]
        regels.append(f"rij {i}: " + " | ".join(cellen))
    return "\n".join(regels)


def vraag_mapping(client, rijen: list[list], tabblad: str, totaal_rijen: int,
                  catalogus: list[dict], voortgang: Callable[[str], None] | None = None) -> Mapping:
    """Eén begrensde Claude-aanroep; de meegegeven AsyncAnthropic-client wordt gesloten."""
    ids = [c["id"] for c in catalogus]
    systeem = [{
        "type": "text",
        "text": SYSTEEMPROMPT + json.dumps(catalogus, ensure_ascii=False, indent=1),
        "cache_control": {"type": "ephemeral"},
    }]
    async def ontvang_antwoord():
        # Sluit de verbinding binnen dezelfde eventloop, ook bij annulering.
        async with client.with_options(timeout=30.0, max_retries=0) as begrensde_client:
            if voortgang:
                voortgang("Verbinding maken voor automatische kolomherkenning...")
            laatste_update, tekens = time.monotonic(), 0
            async with begrensde_client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=systeem,
                messages=[{"role": "user", "content": bouw_fragment(rijen, tabblad, totaal_rijen)}],
                output_config={"format": {"type": "json_schema", "schema": mapping_schema(ids)}},
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        tekens += len(event.text)
                    nu = time.monotonic()
                    if voortgang and nu - laatste_update >= 1:
                        voortgang(f"Kolomherkenning bezig: {tekens:,} tekens ontvangen.")
                        laatste_update = nu
                return await stream.get_final_message()

    async def begrensd_antwoord():
        # Ook actieve ping-/tekststreams stoppen bij deze totale wachttijd.
        return await asyncio.wait_for(ontvang_antwoord(), timeout=MAPPING_TIMEOUT_SECONDS)

    antwoord = asyncio.run(begrensd_antwoord())
    stop = getattr(antwoord, "stop_reason", None)
    if stop in ("refusal", "max_tokens"):
        raise ValueError(f"Claude gaf geen bruikbare mapping (stop_reason={stop}).")
    tekst = next((b.text for b in antwoord.content if b.type == "text"), None)
    if tekst is None:
        raise ValueError("Claude-antwoord bevat geen tekstblok met JSON.")
    try:
        data = json.loads(tekst)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude-antwoord is geen geldige JSON: {e}") from e
    kopregel = data.get("kopregel_index") if isinstance(data, dict) else None
    if type(kopregel) is not int or not 0 <= kopregel < min(len(rijen), totaal_rijen):
        raise ValueError("Ongeldige kopregel_index: kies een bestaande rij uit het aangeleverde fragment.")
    beginrij = data.get("data_start_index")
    # Oude mappings beginnen direct na de kop; totaal_rijen is ook de eerste
    # invoegpositie na het werkblad wanneer een sjabloon nog geen artikelen bevat.
    if beginrij is None:
        beginrij = kopregel + 1
    if type(beginrij) is not int or not kopregel < beginrij <= totaal_rijen:
        raise ValueError("Ongeldige data_start_index: kies een rij na de kop, uiterlijk direct na het werkblad.")
    mapping = Mapping.uit_dict(data)
    onbekend = [k.doelveld for k in mapping.kolommen if k.doelveld not in ids]
    if onbekend:
        raise ValueError(f"Onbekende doelvelden in mapping: {onbekend}")
    return mapping
