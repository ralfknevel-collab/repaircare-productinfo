# Dealer-Excel invuller — bouwplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een upload-tool in de bestaande Streamlit-app die willekeurig ingedeelde dealer-Excelbestanden automatisch invult met productdata uit het Repair Care Product Data Sheet.

**Architecture:** Het Product Data Sheet wordt eenmalig omgezet naar `artikeldata.json`. Een kernmodule zonder Streamlit-code leest het dealerbestand, laat Claude een kolom-mapping voorstellen (JSON-schema afgedwongen), matcht artikelen op artikelcode/EAN/omschrijving, rekent eenheden om en vult alleen lege cellen in, met een geel gemarkeerd gat waar data ontbreekt en een tabblad "Controle" met bron en rekenregel per cel. `app.py` krijgt een keuzeknop "Productinfo-chat | Dealer-Excel" en een dunne UI-laag (upload → mapping-tabel corrigeren → invullen → download).

**Tech Stack:** Python 3.9, openpyxl 3.1, anthropic SDK 0.109 (`claude-opus-5`, `output_config.format` json_schema), Streamlit 1.50, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-dealer-excel-invuller-design.md`

## Global Constraints

- Python 3.9-compatibel: `from __future__ import annotations` bovenaan elk module; geen `match`-statement; geen `X | Y` buiten annotaties.
- Geen nieuwe runtime-afhankelijkheden (openpyxl, anthropic, pydantic zijn aanwezig). Alleen `pytest` als dev-afhankelijkheid in `requirements-dev.txt`.
- Code, identifiers, commentaar en commit-berichten in het Nederlands, zoals de rest van de repo (`ingest_excel.py`, `app.py`).
- Tests draaien zonder API-key en zonder het echte Product Data Sheet; tests op het echte sheet worden overgeslagen als het bestand ontbreekt.
- Model voor de mapping: exact `claude-opus-5`.
- Alle commando's vanuit de projectmap met `./venv/bin/python` / `./venv/bin/pytest`.
- Alleen lege cellen invullen; bestaande waarden ongemoeid tenzij `overschrijven=True`.
- Elke commit eindigt met de trailers:
  ```
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b
  ```

## Bestandsstructuur

| Bestand | Verantwoordelijkheid |
|---|---|
| `veldcatalogus.py` | Vaste lijst doelvelden (`VELDEN`), eenheden en `converteer()`. Enige plek waar velden gedefinieerd zijn. |
| `ingest_artikeldata.py` | Product Data Sheet → `artikeldata.json`. Parse-helpers voor getallen, A:/B:-prefixen en maten. |
| `artikeldata.py` | Laden van `artikeldata.json` + `vaste_waarden.json`; artikel zoeken (code/EAN/omschrijving); waarde per doelveld met bron en rekenregel. |
| `mapping.py` | Mapping-datamodel, JSON-schema, prompt en Claude-aanroep; lege mapping als fallback. |
| `dealer_invuller.py` | Dealerbestand lezen (xlsx/csv), kopregel vinden, rijen matchen, invullen, tabblad Controle, CLI. |
| `app.py` | Keuzeknop + Dealer-Excel-weergave (dunne laag over de kern). |
| `vaste_waarden.json` | Bedrijfswaarden buiten het sheet. |
| `artikeldata.json` | Gegenereerd; committed. |
| `tests/conftest.py` | Fixture-bouwers voor een mini-Product-Data-Sheet en dealerbestanden. |
| `tests/test_*.py` | Eén testbestand per module. |

---

### Task 1: Testopzet en veldcatalogus

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py` (leeg)
- Create: `veldcatalogus.py`
- Test: `tests/test_veldcatalogus.py`

**Interfaces:**
- Produces:
  - `Veld` dataclass: `id: str, label: str, eenheid: str | None, soort: str, uitleg: str`
  - `VELDEN: list[Veld]`
  - `veld(veld_id: str) -> Veld | None` — herkent ook dynamische ids `ruw:<kolom>` en `vast:<sleutel>`
  - `EENHEDEN: dict[str, dict[str, float]]` — per dimensie factor naar basiseenheid
  - `converteer(waarde: float, van: str | None, naar: str | None) -> float`
  - `catalogus_voor_prompt(ruwe_kolommen: list[str], vaste_sleutels: dict[str, str]) -> list[dict]`
  - `EENHEID_OPTIES: list[str | None]`

- [ ] **Step 1: Testinfrastructuur aanmaken**

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.0
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
```

Installeer: `./venv/bin/pip install -r requirements-dev.txt`

- [ ] **Step 2: Schrijf de falende test**

`tests/test_veldcatalogus.py`:
```python
import pytest

from veldcatalogus import (
    EENHEID_OPTIES,
    VELDEN,
    catalogus_voor_prompt,
    converteer,
    veld,
)


def test_kernvelden_aanwezig():
    ids = {v.id for v in VELDEN}
    for verwacht in [
        "sleutel_artikelcode", "sleutel_ean", "sleutel_omschrijving",
        "gn_code", "netto_gewicht", "bruto_gewicht",
        "lengte", "breedte", "hoogte",
        "collo_lengte", "collo_breedte", "collo_hoogte",
        "ean", "omschrijving", "min_verkoophoeveelheid",
        "un_code", "klasse", "verpakkingsgroep", "adr_naam", "vlampunt",
        "ufi", "voc", "ghs", "geen",
    ]:
        assert verwacht in ids


def test_ids_uniek():
    ids = [v.id for v in VELDEN]
    assert len(ids) == len(set(ids))


def test_veld_opzoeken():
    assert veld("gn_code").label.startswith("Douanetariefnummer")
    assert veld("netto_gewicht").eenheid == "g"
    assert veld("lengte").eenheid == "mm"
    assert veld("onbekend") is None


def test_dynamische_velden():
    r = veld("ruw:UFI-code")
    assert r is not None and r.soort == "ruw" and r.label == "UFI-code"
    v = veld("vast:ursprungsland")
    assert v is not None and v.soort == "vast" and v.label == "ursprungsland"


@pytest.mark.parametrize("waarde, van, naar, verwacht", [
    (318, "g", "kg", 0.318),
    (0.5, "kg", "g", 500),
    (184, "mm", "cm", 18.4),
    (18.4, "cm", "mm", 184),
    (1200, "mm", "m", 1.2),
    (7, "g", "g", 7),
    (7, None, "g", 7),
    (7, "g", None, 7),
])
def test_converteer(waarde, van, naar, verwacht):
    assert converteer(waarde, van, naar) == pytest.approx(verwacht)


def test_converteer_verschillende_dimensies_faalt():
    with pytest.raises(ValueError):
        converteer(1, "g", "mm")


def test_catalogus_voor_prompt_bevat_ruw_en_vast():
    cat = catalogus_voor_prompt(["UFI-code", "VOC-content"], {"ursprungsland": "Land van oorsprong"})
    ids = [c["id"] for c in cat]
    assert "gn_code" in ids
    assert "ruw:UFI-code" in ids
    assert "vast:ursprungsland" in ids
    assert all(set(c) == {"id", "label", "eenheid", "uitleg"} for c in cat)


def test_eenheid_opties():
    assert None in EENHEID_OPTIES
    assert {"g", "kg", "mm", "cm", "m", "stuks"} <= set(o for o in EENHEID_OPTIES if o)
```

- [ ] **Step 3: Draai de test — moet falen**

Run: `./venv/bin/pytest tests/test_veldcatalogus.py -v`
Expected: FAIL met `ModuleNotFoundError: No module named 'veldcatalogus'`

- [ ] **Step 4: Implementeer `veldcatalogus.py`**

```python
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
```

- [ ] **Step 5: Draai de test — moet slagen**

Run: `./venv/bin/pytest tests/test_veldcatalogus.py -v`
Expected: alle tests PASS

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt pytest.ini tests/__init__.py tests/test_veldcatalogus.py veldcatalogus.py
git commit -q -m "Veldcatalogus en testopzet voor dealer-Excel invuller

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```

---

### Task 2: Parse-helpers voor het Product Data Sheet

**Files:**
- Create: `ingest_artikeldata.py` (alleen de helpers; `lees_artikelen`/`main` volgen in Task 3)
- Test: `tests/test_ingest_artikeldata.py`

**Interfaces:**
- Produces:
  - `parse_getal(tekst) -> float | None` — `"A: 222 "`→222.0, `"2,22"`→2.22, `"--"`/`"n.v.t."`/`None`→None, `3.8`→3.8
  - `split_prefix(tekst: str) -> tuple[str | None, str]` — `"A: 222"`→`("A","222")`, `"B : UN 2735…"`→`("B","UN 2735…")`, `"12"`→`(None,"12")`
  - `parse_maat(tekst) -> dict | None` — blok: `{"vorm":"blok","l":262,"b":290,"h":242}`; rond: `{"vorm":"rond","diameter":48,"hoogte":184,"l":48,"b":48,"h":184}`
  - `combineer_maat(maten: list[dict]) -> dict | None` — 0→None; 1→kopie zonder regel; ≥2→`{"vorm":"samengesteld","l":som l,"b":max b,"h":max h,"regel":"…"}`
  - `alleen_cijfers(tekst) -> str`
  - `normaliseer_kop(tekst) -> str` — whitespace samenvouwen

- [ ] **Step 1: Schrijf de falende tests**

`tests/test_ingest_artikeldata.py`:
```python
import pytest

from ingest_artikeldata import (
    alleen_cijfers,
    combineer_maat,
    normaliseer_kop,
    parse_getal,
    parse_maat,
    split_prefix,
)


@pytest.mark.parametrize("invoer, verwacht", [
    ("A: 222 ", 222.0),
    ("B: 052", 52.0),
    ("2,22", 2.22),
    ("A: 6,67", 6.67),
    (3.8, 3.8),
    (417, 417.0),
    ("537.6", 537.6),
    ("--", None),
    ("n.v.t.", None),
    ("", None),
    (None, None),
    ("set 10 stuks", 10.0),
])
def test_parse_getal(invoer, verwacht):
    assert parse_getal(invoer) == verwacht


@pytest.mark.parametrize("invoer, verwacht", [
    ("A: 222", ("A", "222")),
    ("B : UN 2735 AMINES", ("B", "UN 2735 AMINES")),
    ("A:                      Ø: 48   H: 184", ("A", "Ø: 48 H: 184")),
    ("12", (None, "12")),
    ("Actief", (None, "Actief")),
    ("ABC: 1", (None, "ABC: 1")),
])
def test_split_prefix(invoer, verwacht):
    assert split_prefix(invoer) == verwacht


def test_parse_maat_blok():
    assert parse_maat("262x290x242") == {"vorm": "blok", "l": 262.0, "b": 290.0, "h": 242.0}
    assert parse_maat("340x 240x250 ") == {"vorm": "blok", "l": 340.0, "b": 240.0, "h": 250.0}
    assert parse_maat("80 x 120 x 98") == {"vorm": "blok", "l": 80.0, "b": 120.0, "h": 98.0}


def test_parse_maat_rond():
    m = parse_maat("Ø:                      48                                        H: 184")
    assert m == {"vorm": "rond", "diameter": 48.0, "hoogte": 184.0, "l": 48.0, "b": 48.0, "h": 184.0}


@pytest.mark.parametrize("invoer", ["n.v.t.", "--", "-", "", None, "onzin"])
def test_parse_maat_geen(invoer):
    assert parse_maat(invoer) is None


def test_combineer_maat_leeg_en_enkel():
    assert combineer_maat([]) is None
    enkel = {"vorm": "rond", "diameter": 49, "hoogte": 230, "l": 49, "b": 49, "h": 230}
    uit = combineer_maat([enkel])
    assert uit == enkel
    assert uit is not enkel


def test_combineer_maat_twee_bussen():
    a = {"vorm": "rond", "diameter": 48, "hoogte": 184, "l": 48, "b": 48, "h": 184}
    b = {"vorm": "rond", "diameter": 41, "hoogte": 145, "l": 41, "b": 41, "h": 145}
    uit = combineer_maat([a, b])
    assert uit["vorm"] == "samengesteld"
    assert (uit["l"], uit["b"], uit["h"]) == (89, 48, 184)
    assert "naast elkaar" in uit["regel"]
    assert "48" in uit["regel"] and "41" in uit["regel"]


def test_alleen_cijfers():
    assert alleen_cijfers("87.14748.00436.8") == "8714748004368"
    assert alleen_cijfers("3214 10 10") == "32141010"
    assert alleen_cijfers(None) == ""


def test_normaliseer_kop():
    assert normaliseer_kop("Dimensions per piece    (mm) (LxBxH)") == "Dimensions per piece (mm) (LxBxH)"
    assert normaliseer_kop("  Artikelcode ") == "Artikelcode"
```

- [ ] **Step 2: Draai — moet falen**

Run: `./venv/bin/pytest tests/test_ingest_artikeldata.py -v`
Expected: FAIL met `ModuleNotFoundError: No module named 'ingest_artikeldata'`

- [ ] **Step 3: Implementeer de helpers**

`ingest_artikeldata.py`:
```python
"""
Zet het Product Data Sheet (Excel) om naar artikeldata.json: gestructureerde
productdata per artikelcode, met componenten (A/B) apart én opgeteld.

Gebruik:
    python3 ingest_artikeldata.py

Gebruikt geen API. Opnieuw draaien overschrijft artikeldata.json.
"""

from __future__ import annotations

import re

LEEG = {"", "--", "-", "n.v.t.", "nvt", "inapplicable", "none"}

_GETAL = re.compile(r"-?\d+(?:[.,]\d+)?")
_PREFIX = re.compile(r"^([AB])\s*:\s*(.*)$", re.S)
_BLOK = re.compile(r"^(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)$")
_ROND = re.compile(r"Ø\s*:?\s*(\d+(?:[.,]\d+)?)\s*H\s*:?\s*(\d+(?:[.,]\d+)?)")


def normaliseer_kop(tekst) -> str:
    """Vouw alle whitespace samen tot één spatie en trim."""
    return " ".join(str(tekst).split()) if tekst is not None else ""


def alleen_cijfers(tekst) -> str:
    return re.sub(r"\D", "", str(tekst)) if tekst is not None else ""


def split_prefix(tekst: str) -> tuple[str | None, str]:
    """Haal een componentprefix 'A:'/'B:' van de tekst af."""
    schoon = normaliseer_kop(tekst)
    m = _PREFIX.match(schoon)
    if not m:
        return None, schoon
    return m.group(1), normaliseer_kop(m.group(2))


def parse_getal(tekst) -> float | None:
    """Eerste getal in de tekst als float; komma als decimaalteken toegestaan."""
    if tekst is None:
        return None
    if isinstance(tekst, (int, float)):
        return float(tekst)
    _, rest = split_prefix(str(tekst))
    if rest.lower() in LEEG:
        return None
    m = _GETAL.search(rest)
    if not m:
        return None
    return float(m.group(0).replace(",", "."))


def parse_maat(tekst) -> dict | None:
    """'262x290x242' -> blok; 'Ø: 48 H: 184' -> rond (l = b = diameter)."""
    if tekst is None:
        return None
    _, schoon = split_prefix(str(tekst))
    if schoon.lower() in LEEG:
        return None
    m = _BLOK.match(schoon)
    if m:
        l, b, h = (float(x.replace(",", ".")) for x in m.groups())
        return {"vorm": "blok", "l": l, "b": b, "h": h}
    m = _ROND.search(schoon)
    if m:
        d, h = (float(x.replace(",", ".")) for x in m.groups())
        return {"vorm": "rond", "diameter": d, "hoogte": h, "l": d, "b": d, "h": h}
    return None


def combineer_maat(maten: list[dict]) -> dict | None:
    """Maat van een verkoopeenheid uit componentmaten: naast elkaar gezet."""
    if not maten:
        return None
    if len(maten) == 1:
        return dict(maten[0])
    delen = " + ".join(f"{m['l']:g}" for m in maten)
    return {
        "vorm": "samengesteld",
        "l": sum(m["l"] for m in maten),
        "b": max(m["b"] for m in maten),
        "h": max(m["h"] for m in maten),
        "regel": f"componenten naast elkaar: L = {delen}, B en H = grootste component",
    }
```

- [ ] **Step 4: Draai — moet slagen**

Run: `./venv/bin/pytest tests/test_ingest_artikeldata.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ingest_artikeldata.py tests/test_ingest_artikeldata.py
git commit -q -m "Parse-helpers voor Product Data Sheet (getallen, prefixen, maten)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```

---

### Task 3: Ingest: sheet → artikeldata.json

**Files:**
- Create: `tests/conftest.py`
- Modify: `ingest_artikeldata.py` (toevoegen: `KOLOMMEN`, `VERPLICHT`, `COMPONENTVELDEN`, `lees_artikelen`, `bouw_artikeldata`, `main`)
- Modify: `tests/test_ingest_artikeldata.py` (tests toevoegen)
- Create (gegenereerd): `artikeldata.json`

**Interfaces:**
- Consumes: helpers uit Task 2.
- Produces:
  - `lees_artikelen(ws) -> tuple[dict[str, dict], list[str]]` — `(artikelen, ruwe_kolommen)`
  - `bouw_artikeldata(pad: Path) -> dict` met sleutels `bron`, `gemaakt_op`, `ruwe_kolommen`, `artikelen`
  - Artikelstructuur (alle sleutels optioneel behalve `artikelcode`, `omschrijving`, `componenten`, `ruw`):
    ```
    artikelcode: str, omschrijving: str, ean: str, status: str, productgroep: str,
    gn_code: str (alleen cijfers), min_verkoophoeveelheid: float,
    netto_g: float, netto_regel: str, bruto_g: float, bruto_regel: str,
    maat_mm: {vorm,l,b,h,[diameter,hoogte,regel]}, collo_mm: {...}, omdoos_cm: {...},
    inhoud, ufi, voc, klasse, un_code, verpakkingsgroep, transportcategorie,
    vlampunt, adr_naam, milieugevaarlijk: str, ghs: list[str],
    componenten: list[{naam: "A"|"B", <zelfde componentvelden>, ruw: dict}],
    ruw: {genormaliseerde kop: tekst}
    ```
  - Fixture `pds_bestand(tmp_path) -> Path` (conftest) met 4 artikelen: DRY FIX UNI (A+B rond), DRY SEAL MP (enkel rond), Spachtel (blok), Box (geen GN, geen maat). Fixture `artikeldata_dict(pds_bestand) -> dict`.

- [ ] **Step 1: Schrijf `tests/conftest.py`**

```python
"""Fixtures: mini-Product-Data-Sheet en dealerbestanden, gebouwd met openpyxl."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

# Exacte koppen zoals in het echte sheet (inclusief rare whitespace).
PDS_KOPPEN = [
    "Artikelcode", "Omschrijving", "Language version", "EAN-code", None, "Status",
    "Productgroup", "Minimale Verkoop- hoeveel-heid", "Assembled item", "Components",
    "Contentes", "Dimensions per piece    (mm) (LxBxH)", "Afmetingen collo     (mm) (LxBxH)",
    "Afmetingen omdoos (cm) (LxBXH)", "GHS07", "GHS05", "GHS09", "GHS08", "GHS02",
    "UFI-code", "VOC-content", "VOC-category", "Water- basis", "Klasse", "UN-code",
    "Verpakkings-categorie", "Transport-categorie ADR", "Dangerous for the environment",
    "Flashpoint", "Transport-naam ADR", "GN-code", "Tarief invoer-rechten",
    "Netto gewicht per stuk (gr)", "Bruto gewicht per stuk (gr)",
    "Netto gewicht per doos (kg)", "Bruto gewicht per doos (kg)",
]


def _rij(**waarden) -> list:
    """Bouw een rij op kopnaam; onbekende koppen geven een fout."""
    rij = [None] * len(PDS_KOPPEN)
    for kop, waarde in waarden.items():
        rij[PDS_KOPPEN.index(kop)] = waarde
    return rij


PDS_RIJEN = [
    _rij(**{"Artikelcode": 2010005, "Omschrijving": "DRY FIX UNI", "Language version": "NL/EN/GE/FR",
            "EAN-code": "87.14748.", "Status": "Actief", "Productgroup": "150, DRY FIX",
            "Minimale Verkoop- hoeveel-heid": 10, "Assembled item": "nee", "Components": "A",
            "Contentes": "A: 200 ml                ",
            "Dimensions per piece    (mm) (LxBxH)": "A:                      Ø: 48                                        H: 184                          ",
            "Afmetingen collo     (mm) (LxBxH)": "180x226x200", "Afmetingen omdoos (cm) (LxBXH)": "39x26x42",
            "GHS07": "x", "GHS05": "x", "GHS09": "x", "UFI-code": "A: EMM3-M8KP-4PK7-HVPV",
            "VOC-content": "A: 150 grams/liter   ", "Klasse": "A: 9   ", "UN-code": "A: 3082  ",
            "Verpakkings-categorie": "A: III ", "Transport-categorie ADR": "A: 3 ",
            "Dangerous for the environment": "A: yes", "Flashpoint": "A: >62°C",
            "Transport-naam ADR": "A: UN 3082 ENVIRONMENTALLY HAZARDOUS SUBSTANCE, LIQUID, N.O.S., 9, III",
            "GN-code": "3214 10 10", "Tarief invoer-rechten": 0.05,
            "Netto gewicht per stuk (gr)": "A: 222 ", "Bruto gewicht per stuk (gr)": "A: 243 ",
            "Netto gewicht per doos (kg)": "A: 2,22 ", "Bruto gewicht per doos (kg)": 3.8}),
    _rij(**{"Components": "B", "Contentes": "B: 100 ml",
            "Dimensions per piece    (mm) (LxBxH)": "B:                      Ø: 41                                        H: 145",
            "GHS07": "x", "GHS05": "x", "GHS09": "x", "GHS08": "x", "UFI-code": "B: 7WR3-X83H-EPKY-KXU3",
            "Klasse": "B: 8", "UN-code": "B: 2735", "Verpakkings-categorie": "B: III",
            "Flashpoint": "B: >62°C", "Transport-naam ADR": "B : UN 2735 AMINES, LIQUID, CORROSIVE, N.O.S., 8, III",
            "Netto gewicht per stuk (gr)": "B: 96", "Bruto gewicht per stuk (gr)": "B: 117"}),
    _rij(**{"Artikelcode": 2511105, "Omschrijving": "DRY SEAL MP wit 290 ml", "EAN-code": "87.14748.",
            "Status": "Actief", "Productgroup": "250, DRY SEAL", "Minimale Verkoop- hoeveel-heid": 12,
            "Dimensions per piece    (mm) (LxBxH)": "Ø: 49  H: 230", "Afmetingen collo     (mm) (LxBxH)": "310x215x240",
            "GHS07": "x", "GN-code": "3214 10 10", "Netto gewicht per stuk (gr)": 452,
            "Bruto gewicht per stuk (gr)": 480, "UN-code": "inapplicable"}),
    _rij(**{"Artikelcode": "4513032", "Omschrijving": "EASY Q Modelleerspatel metaal 50 mm",
            "EAN-code": "87.14748.", "Status": "Actief", "Productgroup": "450, EASY Q",
            "Minimale Verkoop- hoeveel-heid": 1, "Dimensions per piece    (mm) (LxBxH)": "25x50x222",
            "Afmetingen collo     (mm) (LxBxH)": "134x170x229", "GN-code": "8205 59 10",
            "Netto gewicht per stuk (gr)": 120, "Bruto gewicht per stuk (gr)": 130}),
    _rij(**{"Artikelcode": 4570042, "Omschrijving": "REPAIR CARE Box 5", "EAN-code": "87.14748.",
            "Status": "Actief", "Productgroup": "457, BOX", "Minimale Verkoop- hoeveel-heid": 1,
            "Afmetingen collo     (mm) (LxBxH)": "--", "Netto gewicht per stuk (gr)": 8710}),
]
# Tweede EAN-cel (kolom zonder kop) per hoofdrij.
_EAN2 = {0: "00436.8", 2: "00380.4", 3: "00332.3", 4: "00385.9"}
for _i, _e in _EAN2.items():
    PDS_RIJEN[_i][PDS_KOPPEN.index("EAN-code") + 1] = _e


@pytest.fixture
def pds_bestand(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Items"])
    ws.append([])
    ws.append(PDS_KOPPEN)
    for rij in PDS_RIJEN:
        ws.append(rij)
    pad = tmp_path / "pds.xlsx"
    wb.save(pad)
    return pad


@pytest.fixture
def artikeldata_dict(pds_bestand: Path) -> dict:
    from ingest_artikeldata import bouw_artikeldata
    return bouw_artikeldata(pds_bestand)


def maak_dealerbestand(pad: Path, koppen: list, rijen: list[list], tabblad: str = "Sheet1",
                       voorloop: list[list] | None = None) -> Path:
    """Schrijf een dealerbestand: optionele voorlooprijen, kopregel, datarijen."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tabblad
    for rij in voorloop or []:
        ws.append(rij)
    ws.append(koppen)
    for rij in rijen:
        ws.append(rij)
    wb.save(pad)
    return pad


SEEFELDER_KOPPEN = ["ArtNr", "Bundesland", "Ursprungsland", "Zolltarifnummer", "Nettogewicht",
                    "Länge", "Breite", "Höhe", "ArtBeschreibung", "Primärlieferant", "VKEinheit",
                    "HerstellerArtNr", "EAN13"]
SEEFELDER_RIJEN = [
    ["2010005", None, None, None, None, None, None, None, "REPAIR CARE DRY FIX UNI", 973184, "St.", "2010005", 8714748004368],
    ["2511105", None, None, None, None, None, None, None, "DRY SEAL MP WEIß 290 ML", 973184, "St.", "2511105", 8714748003804],
    ["4513032", None, None, "82055910", None, None, None, None, "EASY Q MODELLIERSPACHTEL METALL 50 mm", 973184, "St.", "4513032", 8714748003323],
    ["4530043", None, None, None, None, None, None, None, "EASY Q Wipes 120 Stück", 973184, "Pkt.", "0", 8714748004955],
    ["4570042", None, None, None, None, None, None, None, "REPAIR CARE Holzreparatur Box 5", 973184, "St.", "4570042", 8714748003859],
]


@pytest.fixture
def seefelder_bestand(tmp_path: Path) -> Path:
    return maak_dealerbestand(tmp_path / "Primärlieferant.xlsx", SEEFELDER_KOPPEN, SEEFELDER_RIJEN)
```

- [ ] **Step 2: Voeg ingest-tests toe aan `tests/test_ingest_artikeldata.py`**

Onderaan het bestand:
```python
from pathlib import Path

import openpyxl

from ingest_artikeldata import bouw_artikeldata, lees_artikelen

ECHT_SHEET = Path(__file__).resolve().parent.parent / "Product Data Sheet december 2024.xlsx"


def test_lees_artikelen_fixture(artikeldata_dict):
    art = artikeldata_dict["artikelen"]
    assert set(art) == {"2010005", "2511105", "4513032", "4570042"}
    assert "Dimensions per piece (mm) (LxBxH)" in artikeldata_dict["ruwe_kolommen"]

    dfu = art["2010005"]
    assert dfu["artikelcode"] == "2010005"
    assert dfu["ean"] == "8714748004368"
    assert dfu["gn_code"] == "32141010"
    assert dfu["min_verkoophoeveelheid"] == 10
    assert [c["naam"] for c in dfu["componenten"]] == ["A", "B"]
    assert dfu["componenten"][0]["netto_g"] == 222
    assert dfu["componenten"][1]["netto_g"] == 96
    assert dfu["netto_g"] == 318
    assert "222" in dfu["netto_regel"] and "96" in dfu["netto_regel"]
    assert dfu["bruto_g"] == 360
    assert dfu["maat_mm"]["vorm"] == "samengesteld"
    assert (dfu["maat_mm"]["l"], dfu["maat_mm"]["b"], dfu["maat_mm"]["h"]) == (89, 48, 184)
    assert dfu["collo_mm"] == {"vorm": "blok", "l": 180, "b": 226, "h": 200}
    assert dfu["omdoos_cm"] == {"vorm": "blok", "l": 39, "b": 26, "h": 42}
    assert dfu["componenten"][0]["un_code"] == "3082"
    assert dfu["componenten"][1]["un_code"] == "2735"
    assert dfu["componenten"][0]["ghs"] == ["GHS07", "GHS05", "GHS09"]
    assert dfu["componenten"][1]["ghs"] == ["GHS07", "GHS05", "GHS09", "GHS08"]
    assert dfu["componenten"][0]["ufi"] == "EMM3-M8KP-4PK7-HVPV"
    assert dfu["ruw"]["Bruto gewicht per doos (kg)"] == "3.8"
    assert "un_code" not in dfu  # alleen op componentniveau

    seal = art["2511105"]
    assert seal["componenten"] == []
    assert seal["netto_g"] == 452 and "netto_regel" not in seal
    assert seal["maat_mm"]["vorm"] == "rond" and seal["maat_mm"]["l"] == 49
    assert "un_code" not in seal  # 'inapplicable' telt als leeg

    spatel = art["4513032"]
    assert spatel["maat_mm"] == {"vorm": "blok", "l": 25, "b": 50, "h": 222}
    assert spatel["gn_code"] == "82055910"

    box = art["4570042"]
    assert "gn_code" not in box
    assert "maat_mm" not in box
    assert "collo_mm" not in box
    assert box["netto_g"] == 8710


def test_ontbrekende_kolom_geeft_duidelijke_fout(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Items"]); ws.append([]); ws.append(["Artikelcode", "Omschrijving"])
    ws.append([1, "x"])
    pad = tmp_path / "kapot.xlsx"
    wb.save(pad)
    with pytest.raises(ValueError) as e:
        bouw_artikeldata(pad)
    assert "GN-code" in str(e.value)


@pytest.mark.skipif(not ECHT_SHEET.exists(), reason="echt Product Data Sheet niet aanwezig")
def test_echt_sheet():
    data = bouw_artikeldata(ECHT_SHEET)
    art = data["artikelen"]
    assert len(art) == 167
    assert art["2010005"]["netto_g"] == 318
    assert art["2010005"]["gn_code"] == "32141010"
    assert art["2010005"]["maat_mm"]["l"] == 89
    assert art["2022003"]["omschrijving"] == "DRY FLEX 4 JP"   # string-artikelcode
    assert art["4012100"]["maat_mm"]["vorm"] == "rond"           # 'B: Ø: 50 H: 6' zonder componentrij
    assert art["4012100"]["netto_g"] == 7
```

- [ ] **Step 3: Draai — moet falen**

Run: `./venv/bin/pytest tests/test_ingest_artikeldata.py -v`
Expected: FAIL met `ImportError: cannot import name 'bouw_artikeldata'`

- [ ] **Step 4: Implementeer `lees_artikelen`, `bouw_artikeldata`, `main`**

Toevoegen aan `ingest_artikeldata.py` (imports bovenaan uitbreiden met `import json, sys`, `from datetime import date`, `from pathlib import Path`, `import openpyxl`):

```python
BASE_DIR = Path(__file__).resolve().parent
EXCEL_FILE = BASE_DIR / "Product Data Sheet december 2024.xlsx"
UITVOER = BASE_DIR / "artikeldata.json"
KOPREGEL = 2  # 0-based: rij 3 in Excel

# Genormaliseerde kop in het sheet -> interne sleutel.
KOLOMMEN = {
    "Artikelcode": "artikelcode",
    "Omschrijving": "omschrijving",
    "Language version": "taalversie",
    "EAN-code": "ean_1",
    "Status": "status",
    "Productgroup": "productgroep",
    "Minimale Verkoop- hoeveel-heid": "min_verkoophoeveelheid",
    "Assembled item": "samengesteld",
    "Components": "component",
    "Contentes": "inhoud",
    "Dimensions per piece (mm) (LxBxH)": "maat_stuk",
    "Afmetingen collo (mm) (LxBxH)": "maat_collo",
    "Afmetingen omdoos (cm) (LxBXH)": "maat_omdoos",
    "UFI-code": "ufi",
    "VOC-content": "voc",
    "VOC-category": "voc_categorie",
    "Klasse": "klasse",
    "UN-code": "un_code",
    "Verpakkings-categorie": "verpakkingsgroep",
    "Transport-categorie ADR": "transportcategorie",
    "Dangerous for the environment": "milieugevaarlijk",
    "Flashpoint": "vlampunt",
    "Transport-naam ADR": "adr_naam",
    "GN-code": "gn_code",
    "Tarief invoer-rechten": "invoerrechten",
    "Netto gewicht per stuk (gr)": "netto_g",
    "Bruto gewicht per stuk (gr)": "bruto_g",
}
VERPLICHT = ["Artikelcode", "Omschrijving", "EAN-code", "Components",
             "Dimensions per piece (mm) (LxBxH)", "GN-code",
             "Netto gewicht per stuk (gr)", "Bruto gewicht per stuk (gr)"]

# Velden die per component (A/B) kunnen voorkomen, herkenbaar aan een 'A:'/'B:'-prefix
# of doordat ze op een componentrij staan.
COMPONENTVELDEN = {"inhoud", "maat_stuk", "ufi", "voc", "voc_categorie", "klasse", "un_code",
                   "verpakkingsgroep", "transportcategorie", "milieugevaarlijk", "vlampunt",
                   "adr_naam", "netto_g", "bruto_g"}
GETALVELDEN = {"netto_g", "bruto_g", "min_verkoophoeveelheid", "invoerrechten"}
MAATVELDEN = {"maat_stuk": "maat_mm", "maat_collo": "collo_mm", "maat_omdoos": "omdoos_cm"}
TEKSTVELDEN = COMPONENTVELDEN - GETALVELDEN - {"maat_stuk"}


def _component(artikel: dict, naam: str) -> dict:
    for c in artikel["componenten"]:
        if c["naam"] == naam:
            return c
    c = {"naam": naam, "ruw": {}}
    artikel["componenten"].append(c)
    return c


def _zet(doel: dict, sleutel: str, tekst: str) -> None:
    """Zet een geparste waarde op artikel- of componentniveau."""
    if sleutel in GETALVELDEN:
        g = parse_getal(tekst)
        if g is not None:
            doel[sleutel] = g
    elif sleutel in MAATVELDEN:
        m = parse_maat(tekst)
        if m is not None:
            doel[MAATVELDEN[sleutel]] = m
    elif sleutel == "gn_code":
        cijfers = alleen_cijfers(tekst)
        if cijfers:
            doel[sleutel] = cijfers
    elif sleutel in TEKSTVELDEN or sleutel in ("status", "productgroep", "taalversie",
                                               "samengesteld", "omschrijving"):
        if tekst.lower() not in LEEG:
            doel[sleutel] = tekst


def _verwerk_rij(rij, index: dict[str, int], ghs_index: dict[str, int], kop_per_index: dict[int, str],
                 artikel: dict, standaard_component: str | None, hoofdrij: bool) -> None:
    """Eén sheetrij verwerken. Alle kolommen komen in 'ruw'; bekende kolommen ook geparst.

    Componentvelden met een A:/B:-prefix gaan naar dat component; zonder prefix naar het
    component van de rij (kolom Components) of, op de hoofdrij zonder component, naar het artikel.
    Overige kolommen horen op de hoofdrij bij het artikel en op een componentrij bij het component.
    """
    sleutel_per_index = {i: s for s, i in index.items()}
    ghs_kolommen = set(ghs_index.values())
    for i, kop in kop_per_index.items():
        sleutel = sleutel_per_index.get(i)
        if sleutel in ("artikelcode", "ean_1", "component") or i in ghs_kolommen:
            continue
        ruw = rij[i] if i < len(rij) else None
        if ruw is None:
            continue
        tekst = normaliseer_kop(ruw)
        if not tekst:
            continue
        if sleutel in COMPONENTVELDEN:
            prefix, rest = split_prefix(tekst)
            naam = prefix or standaard_component
            doel = _component(artikel, naam) if naam else artikel
            doel["ruw"][kop] = tekst
            _zet(doel, sleutel, rest)
        else:
            doel = artikel if hoofdrij or not standaard_component else _component(artikel, standaard_component)
            doel["ruw"][kop] = tekst
            if sleutel:
                _zet(artikel, sleutel, tekst)
    # GHS-markeringen ('x') horen bij het component van de rij, anders bij het artikel.
    ghs = [code for code, i in ghs_index.items()
           if i < len(rij) and rij[i] is not None and normaliseer_kop(rij[i])]
    if ghs:
        doel = _component(artikel, standaard_component) if standaard_component else artikel
        doel["ghs"] = ghs


def _rond_af(artikel: dict) -> None:
    """Artikelniveau afleiden uit componenten: gewichten optellen, maten combineren."""
    comps = artikel["componenten"]
    for veld, regel in (("netto_g", "netto_regel"), ("bruto_g", "bruto_regel")):
        if veld not in artikel and comps and all(veld in c for c in comps):
            artikel[veld] = sum(c[veld] for c in comps)
            artikel[regel] = "som van " + " + ".join(f"{c['naam']} {c[veld]:g} g" for c in comps)
    if "maat_mm" not in artikel:
        m = combineer_maat([c["maat_mm"] for c in comps if "maat_mm" in c])
        if m:
            artikel["maat_mm"] = m
    if "ghs" not in artikel and comps:
        gezien: list[str] = []
        for c in comps:
            for code in c.get("ghs", []):
                if code not in gezien:
                    gezien.append(code)
        if gezien:
            artikel["ghs"] = gezien


def lees_artikelen(ws) -> tuple[dict[str, dict], list[str]]:
    rijen = list(ws.iter_rows(values_only=True))
    koppen = [normaliseer_kop(k) if k is not None else None for k in rijen[KOPREGEL]]
    ontbreekt = [k for k in VERPLICHT if k not in koppen]
    if ontbreekt:
        raise ValueError(f"Verwachte kolommen ontbreken in het sheet: {', '.join(ontbreekt)}")
    index = {KOLOMMEN[k]: i for i, k in enumerate(koppen) if k in KOLOMMEN}
    ghs_index = {k: i for i, k in enumerate(koppen) if k and k.startswith("GHS")}
    kop_per_index = {i: k for i, k in enumerate(koppen) if k}
    ean_i = index["ean_1"]
    comp_i = index["component"]
    ruwe_kolommen = [k for k in koppen if k]

    artikelen: dict[str, dict] = {}
    huidig: dict | None = None
    for rij in rijen[KOPREGEL + 1:]:
        if not any(c is not None for c in rij):
            continue
        code = rij[index["artikelcode"]]
        if code is not None:
            code_str = normaliseer_kop(code)
            if isinstance(code, float) and code.is_integer():
                code_str = str(int(code))
            huidig = {"artikelcode": code_str, "omschrijving": "", "componenten": [], "ruw": {}}
            artikelen[code_str] = huidig
            ean = alleen_cijfers(rij[ean_i]) + alleen_cijfers(rij[ean_i + 1] if ean_i + 1 < len(rij) else None)
            if ean:
                huidig["ean"] = ean
            comp = normaliseer_kop(rij[comp_i]) if rij[comp_i] is not None else None
            _verwerk_rij(rij, index, ghs_index, kop_per_index, huidig, comp or None, hoofdrij=True)
        elif huidig is not None:
            comp = normaliseer_kop(rij[comp_i]) if rij[comp_i] is not None else None
            _verwerk_rij(rij, index, ghs_index, kop_per_index, huidig, comp or None, hoofdrij=False)
    for artikel in artikelen.values():
        _rond_af(artikel)
    return artikelen, ruwe_kolommen


def bouw_artikeldata(pad: Path) -> dict:
    wb = openpyxl.load_workbook(pad, data_only=True)
    ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb.worksheets[0]
    artikelen, ruwe_kolommen = lees_artikelen(ws)
    return {
        "bron": pad.name,
        "gemaakt_op": date.today().isoformat(),
        "ruwe_kolommen": ruwe_kolommen,
        "artikelen": artikelen,
    }


def main() -> int:
    if not EXCEL_FILE.exists():
        print(f"Excel niet gevonden: {EXCEL_FILE.name}")
        return 1
    data = bouw_artikeldata(EXCEL_FILE)
    UITVOER.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(data['artikelen'])} artikelen geschreven naar {UITVOER.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Let op in `_verwerk_rij`: `doel["ruw"]` bestaat altijd omdat zowel het artikel als elk component met `"ruw": {}` wordt aangemaakt. Kolommen zonder interne sleutel (bv. palletgegevens) komen alleen in `ruw`, en zijn later bereikbaar als doelveld `ruw:<kolom>`.

- [ ] **Step 5: Draai — moet slagen (inclusief de test op het echte sheet)**

Run: `./venv/bin/pytest tests/test_ingest_artikeldata.py -v`
Expected: PASS. Als `test_echt_sheet` faalt op een specifieke waarde: de fixture-test is leidend voor het parse-gedrag; onderzoek dan de echte rij met `./venv/bin/python -c "..."` en pas de assert alleen aan als het echte sheet écht een andere waarde bevat.

- [ ] **Step 6: Genereer `artikeldata.json` en controleer**

Run: `./venv/bin/python ingest_artikeldata.py`
Expected: `167 artikelen geschreven naar artikeldata.json`

Run: `./venv/bin/python -c "import json; d=json.load(open('artikeldata.json')); a=d['artikelen']; print(len(a), a['2010005']['netto_g'], a['2010005']['maat_mm'], a['4530043']['ean'])"`
Expected: `167 318.0 {...'l': 89.0...} 8714748004955`

- [ ] **Step 7: Commit**

```bash
git add ingest_artikeldata.py tests/conftest.py tests/test_ingest_artikeldata.py artikeldata.json
git commit -q -m "Ingest Product Data Sheet naar artikeldata.json

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```

---

### Task 4: Artikeldata laden, zoeken en waarden per doelveld

**Files:**
- Create: `artikeldata.py`
- Create: `vaste_waarden.json`
- Test: `tests/test_artikeldata.py`

**Interfaces:**
- Consumes: artikelstructuur uit Task 3; `veld()`/`converteer()` uit Task 1.
- Produces:
  - `normaliseer_code(x) -> str | None` — `2010005`→`"2010005"`, `2010005.0`→`"2010005"`, `" 2010005 "`→`"2010005"`, `0`/`"0"`/`None`/`""`→None
  - `normaliseer_ean(x) -> str | None` — alleen cijfers, 8 of 13 lang, anders None; `8714748004368.0`→`"8714748004368"`
  - `@dataclass Match(artikel: dict, via: str, score: float)` — `via` ∈ `artikelcode|ean|omschrijving`
  - `@dataclass Waarde(waarde: object, eenheid: str | None, bron: str, regel: str | None)`
  - `class Artikeldata`: `__init__(data: dict, vaste_waarden: dict | None = None)`, `laad(pad_json: Path, pad_vast: Path | None) -> Artikeldata` (classmethod), `zoek(artikelcode=None, ean=None, omschrijving=None) -> Match | None`, `waarde(artikel: dict, veld_id: str) -> Waarde | None`, `ruwe_kolommen: list[str]`, `vaste_sleutels: dict[str, str]` (sleutel → label)
  - `vaste_waarde(vaste: dict, sleutel: str, artikelcode: str) -> str | None`
  - `FUZZY_DREMPEL = 0.85`

- [ ] **Step 1: Schrijf `vaste_waarden.json`**

```json
{
  "ursprungsland": {
    "label": "Land van oorsprong (ISO-3, bv. NLD)",
    "standaard": null,
    "per_prefix": {},
    "per_artikel": {}
  },
  "bundesland": {
    "label": "Duits Bundesland (2 letters, alleen bij DEU)",
    "standaard": null,
    "per_prefix": {},
    "per_artikel": {}
  },
  "leverancier_naam": {
    "label": "Naam leverancier",
    "standaard": "Repair Care International B.V.",
    "per_prefix": {},
    "per_artikel": {}
  }
}
```

- [ ] **Step 2: Schrijf de falende tests**

`tests/test_artikeldata.py`:
```python
import json

import pytest

from artikeldata import (
    FUZZY_DREMPEL,
    Artikeldata,
    normaliseer_code,
    normaliseer_ean,
    vaste_waarde,
)


@pytest.mark.parametrize("invoer, verwacht", [
    (2010005, "2010005"), (2010005.0, "2010005"), (" 2010005 ", "2010005"),
    ("2010005", "2010005"), (0, None), ("0", None), (None, None), ("", None), ("  ", None),
])
def test_normaliseer_code(invoer, verwacht):
    assert normaliseer_code(invoer) == verwacht


@pytest.mark.parametrize("invoer, verwacht", [
    (8714748004368, "8714748004368"), (8714748004368.0, "8714748004368"),
    ("87.14748.00436.8", "8714748004368"), ("8714748004368", "8714748004368"),
    ("12345678", "12345678"), ("123", None), (None, None), ("abc", None),
])
def test_normaliseer_ean(invoer, verwacht):
    assert normaliseer_ean(invoer) == verwacht


VASTE = {
    "ursprungsland": {"label": "Land", "standaard": None, "per_prefix": {"2": "NLD"},
                      "per_artikel": {"4530043": "CHN"}},
    "leverancier_naam": {"label": "Leverancier", "standaard": "Repair Care"},
}


def test_vaste_waarde_volgorde():
    assert vaste_waarde(VASTE, "ursprungsland", "4530043") == "CHN"
    assert vaste_waarde(VASTE, "ursprungsland", "2010005") == "NLD"
    assert vaste_waarde(VASTE, "ursprungsland", "4513032") is None
    assert vaste_waarde(VASTE, "leverancier_naam", "4513032") == "Repair Care"
    assert vaste_waarde(VASTE, "bestaat_niet", "4513032") is None


@pytest.fixture
def ad(artikeldata_dict) -> Artikeldata:
    return Artikeldata(artikeldata_dict, VASTE)


def test_laad_van_schijf(tmp_path, artikeldata_dict):
    pj = tmp_path / "artikeldata.json"
    pv = tmp_path / "vaste_waarden.json"
    pj.write_text(json.dumps(artikeldata_dict), encoding="utf-8")
    pv.write_text(json.dumps(VASTE), encoding="utf-8")
    ad = Artikeldata.laad(pj, pv)
    assert ad.zoek(artikelcode="2010005") is not None
    assert ad.vaste_sleutels == {"ursprungsland": "Land", "leverancier_naam": "Leverancier"}
    assert "GN-code" in ad.ruwe_kolommen


def test_zoek_op_code_en_ean(ad):
    m = ad.zoek(artikelcode=2010005)
    assert m.via == "artikelcode" and m.artikel["omschrijving"] == "DRY FIX UNI"
    m = ad.zoek(artikelcode="0", ean=8714748003804)
    assert m.via == "ean" and m.artikel["artikelcode"] == "2511105"
    assert ad.zoek(artikelcode="9999999", ean="1111111111111") is None


def test_zoek_op_omschrijving_fuzzy(ad):
    m = ad.zoek(omschrijving="EASY Q Modelleerspatel metaal 50mm")
    assert m is not None and m.via == "omschrijving" and m.score >= FUZZY_DREMPEL
    assert ad.zoek(omschrijving="Iets heel anders") is None


def test_zoek_volgorde_code_boven_ean(ad):
    # EAN hoort bij DRY SEAL, code bij DRY FIX UNI: code wint.
    m = ad.zoek(artikelcode="2010005", ean="8714748003804")
    assert m.via == "artikelcode" and m.artikel["artikelcode"] == "2010005"


def test_waarde_artikelvelden(ad):
    a = ad.zoek(artikelcode="2010005").artikel
    w = ad.waarde(a, "gn_code")
    assert w.waarde == "32141010" and w.eenheid is None
    w = ad.waarde(a, "netto_gewicht")
    assert w.waarde == 318 and w.eenheid == "g" and "222" in w.regel
    w = ad.waarde(a, "lengte")
    assert w.waarde == 89 and w.eenheid == "mm" and "naast elkaar" in w.regel
    assert ad.waarde(a, "breedte").waarde == 48
    assert ad.waarde(a, "hoogte").waarde == 184
    assert ad.waarde(a, "collo_lengte").waarde == 180
    assert ad.waarde(a, "ean").waarde == "8714748004368"
    assert ad.waarde(a, "omschrijving").waarde == "DRY FIX UNI"
    assert ad.waarde(a, "min_verkoophoeveelheid").waarde == 10


def test_waarde_componentvelden_vallen_terug_op_a(ad):
    a = ad.zoek(artikelcode="2010005").artikel
    w = ad.waarde(a, "un_code")
    assert w.waarde == "3082" and "component A" in w.bron
    w = ad.waarde(a, "ghs")
    assert w.waarde == "GHS07, GHS05, GHS09, GHS08"   # unie van A en B, op artikelniveau
    assert w.bron == "Product Data Sheet"
    seal = ad.zoek(artikelcode="2511105").artikel
    assert ad.waarde(seal, "un_code") is None
    assert ad.waarde(seal, "ghs").waarde == "GHS07"


def test_waarde_ruw_vast_geen(ad):
    a = ad.zoek(artikelcode="2010005").artikel
    assert ad.waarde(a, "ruw:Bruto gewicht per doos (kg)").waarde == "3.8"
    assert ad.waarde(a, "ruw:Bestaat niet") is None
    assert ad.waarde(a, "vast:ursprungsland").waarde == "NLD"
    assert ad.waarde(a, "vast:leverancier_naam").waarde == "Repair Care"
    spatel = ad.zoek(artikelcode="4513032").artikel
    assert ad.waarde(spatel, "vast:ursprungsland") is None
    assert ad.waarde(a, "geen") is None
    assert ad.waarde(a, "sleutel_artikelcode") is None
    assert ad.waarde(a, "onbekend_veld") is None


def test_waarde_ontbrekend(ad):
    box = ad.zoek(artikelcode="4570042").artikel
    assert ad.waarde(box, "gn_code") is None
    assert ad.waarde(box, "lengte") is None
    assert ad.waarde(box, "netto_gewicht").waarde == 8710
```

- [ ] **Step 3: Draai — moet falen**

Run: `./venv/bin/pytest tests/test_artikeldata.py -v`
Expected: FAIL met `ModuleNotFoundError: No module named 'artikeldata'`

- [ ] **Step 4: Implementeer `artikeldata.py`**

```python
"""
Toegang tot artikeldata.json en vaste_waarden.json: artikel zoeken op
artikelcode, EAN of omschrijving, en per doelveld de waarde met bron en
rekenregel teruggeven.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from veldcatalogus import veld

FUZZY_DREMPEL = 0.85
BASE_DIR = Path(__file__).resolve().parent
ARTIKELDATA_FILE = BASE_DIR / "artikeldata.json"
VASTE_WAARDEN_FILE = BASE_DIR / "vaste_waarden.json"


@dataclass
class Match:
    artikel: dict
    via: str      # artikelcode | ean | omschrijving
    score: float  # 1.0 bij exacte match


@dataclass
class Waarde:
    waarde: object
    eenheid: str | None
    bron: str
    regel: str | None = None


def normaliseer_code(x) -> str | None:
    if x is None:
        return None
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    s = str(x).strip()
    if s == "" or s == "0":
        return None
    return s


def normaliseer_ean(x) -> str | None:
    if x is None:
        return None
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    cijfers = re.sub(r"\D", "", str(x))
    return cijfers if len(cijfers) in (8, 13) else None


def _normaliseer_tekst(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def vaste_waarde(vaste: dict, sleutel: str, artikelcode: str) -> str | None:
    regel = vaste.get(sleutel)
    if not regel:
        return None
    per_artikel = regel.get("per_artikel") or {}
    if artikelcode in per_artikel:
        return per_artikel[artikelcode]
    per_prefix = regel.get("per_prefix") or {}
    for prefix in sorted(per_prefix, key=len, reverse=True):
        if artikelcode.startswith(prefix):
            return per_prefix[prefix]
    return regel.get("standaard")


# veld-id -> (artikelsleutel, eenheid, regelsleutel)
_ARTIKELVELDEN = {
    "gn_code": ("gn_code", None, None),
    "netto_gewicht": ("netto_g", "g", "netto_regel"),
    "bruto_gewicht": ("bruto_g", "g", "bruto_regel"),
    "ean": ("ean", None, None),
    "omschrijving": ("omschrijving", None, None),
    "min_verkoophoeveelheid": ("min_verkoophoeveelheid", "stuks", None),
}
_MAATVELDEN = {
    "lengte": ("maat_mm", "l"), "breedte": ("maat_mm", "b"), "hoogte": ("maat_mm", "h"),
    "collo_lengte": ("collo_mm", "l"), "collo_breedte": ("collo_mm", "b"), "collo_hoogte": ("collo_mm", "h"),
}
_COMPONENTVELDEN = {"un_code", "klasse", "verpakkingsgroep", "adr_naam", "vlampunt", "ufi", "voc", "ghs"}


class Artikeldata:
    def __init__(self, data: dict, vaste_waarden: dict | None = None):
        self.artikelen: dict[str, dict] = data["artikelen"]
        self.ruwe_kolommen: list[str] = list(data.get("ruwe_kolommen", []))
        self.vaste: dict = vaste_waarden or {}
        self.vaste_sleutels: dict[str, str] = {k: v.get("label", k) for k, v in self.vaste.items()}
        self._op_ean = {a["ean"]: a for a in self.artikelen.values() if a.get("ean")}
        self._omschrijvingen = {_normaliseer_tekst(a["omschrijving"]): a
                                for a in self.artikelen.values() if a.get("omschrijving")}

    @classmethod
    def laad(cls, pad_json: Path | None = None, pad_vast: Path | None = None) -> "Artikeldata":
        # Defaults hier oplossen (niet in de signatuur) zodat tests de module-constanten kunnen vervangen.
        pad_json = pad_json or ARTIKELDATA_FILE
        pad_vast = pad_vast or VASTE_WAARDEN_FILE
        data = json.loads(Path(pad_json).read_text(encoding="utf-8"))
        vaste = None
        if Path(pad_vast).exists():
            vaste = json.loads(Path(pad_vast).read_text(encoding="utf-8"))
        return cls(data, vaste)

    def zoek(self, artikelcode=None, ean=None, omschrijving=None) -> Match | None:
        code = normaliseer_code(artikelcode)
        if code and code in self.artikelen:
            return Match(self.artikelen[code], "artikelcode", 1.0)
        e = normaliseer_ean(ean)
        if e and e in self._op_ean:
            return Match(self._op_ean[e], "ean", 1.0)
        if omschrijving:
            doel = _normaliseer_tekst(str(omschrijving))
            if doel:
                kandidaten = difflib.get_close_matches(doel, self._omschrijvingen.keys(), n=1, cutoff=FUZZY_DREMPEL)
                if kandidaten:
                    score = difflib.SequenceMatcher(None, doel, kandidaten[0]).ratio()
                    return Match(self._omschrijvingen[kandidaten[0]], "omschrijving", score)
        return None

    def waarde(self, artikel: dict, veld_id: str) -> Waarde | None:
        v = veld(veld_id)
        if v is None or v.soort in ("geen", "sleutel"):
            return None
        code = artikel.get("artikelcode", "")
        if v.soort == "ruw":
            w = artikel.get("ruw", {}).get(v.label)
            return Waarde(w, None, "Product Data Sheet, kolom " + v.label) if w is not None else None
        if v.soort == "vast":
            w = vaste_waarde(self.vaste, v.label, code)
            return Waarde(w, None, "vaste_waarden.json: " + v.label) if w is not None else None
        if veld_id in _ARTIKELVELDEN:
            sleutel, eenheid, regelsleutel = _ARTIKELVELDEN[veld_id]
            if sleutel not in artikel:
                return None
            return Waarde(artikel[sleutel], eenheid, "Product Data Sheet",
                          artikel.get(regelsleutel) if regelsleutel else None)
        if veld_id in _MAATVELDEN:
            maatsleutel, as_ = _MAATVELDEN[veld_id]
            maat = artikel.get(maatsleutel)
            if not maat or as_ not in maat:
                return None
            regel = maat.get("regel")
            if maat.get("vorm") == "rond" and as_ in ("l", "b"):
                regel = f"ronde verpakking: L = B = Ø {maat['diameter']:g} mm"
            return Waarde(maat[as_], "mm", "Product Data Sheet", regel)
        if veld_id in _COMPONENTVELDEN:
            bronnen = [(artikel, "Product Data Sheet")] + [
                (c, f"Product Data Sheet, component {c['naam']}") for c in artikel.get("componenten", [])]
            for houder, bron in bronnen:
                if veld_id in houder:
                    w = houder[veld_id]
                    if isinstance(w, list):
                        w = ", ".join(w)
                    return Waarde(w, None, bron)
            return None
        return None
```

- [ ] **Step 5: Draai — moet slagen**

Run: `./venv/bin/pytest tests/test_artikeldata.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add artikeldata.py vaste_waarden.json tests/test_artikeldata.py
git commit -q -m "Artikeldata: zoeken op code/EAN/omschrijving en waarde per doelveld

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```

---

### Task 5: Mapping-model, JSON-schema en Claude-aanroep

**Files:**
- Create: `mapping.py`
- Test: `tests/test_mapping.py`

**Interfaces:**
- Consumes: `catalogus_voor_prompt`, `EENHEID_OPTIES` uit Task 1.
- Produces:
  - `@dataclass KolomMapping(kolom: str, doelveld: str, eenheid: str | None, zekerheid: str, toelichting: str)`
  - `@dataclass Mapping(kopregel_index: int, kolommen: list[KolomMapping], opmerkingen: str = "")` met methodes `sleutels() -> list[KolomMapping]` (doelveld begint met `sleutel_`), `doelen() -> list[KolomMapping]` (overige, niet `geen`), `naar_dict()`, `uit_dict(d)` (staticmethod)
  - `mapping_schema(doelveld_ids: list[str]) -> dict` — JSON-schema (strict, `additionalProperties: False`)
  - `lege_mapping(kopregel_index: int, koppen: list[str]) -> Mapping` — alles op `geen`, zekerheid `laag`
  - `bouw_fragment(rijen: list[list], tabblad: str, totaal_rijen: int) -> str`
  - `SYSTEEMPROMPT: str`, `MODEL = "claude-opus-5"`
  - `vraag_mapping(client, rijen: list[list], tabblad: str, totaal_rijen: int, catalogus: list[dict]) -> Mapping`

- [ ] **Step 1: Schrijf de falende tests**

`tests/test_mapping.py`:
```python
import json
from types import SimpleNamespace

import pytest

from mapping import (
    MODEL,
    KolomMapping,
    Mapping,
    bouw_fragment,
    lege_mapping,
    mapping_schema,
    vraag_mapping,
)
from veldcatalogus import catalogus_voor_prompt


def test_mapping_sleutels_en_doelen():
    m = Mapping(0, [
        KolomMapping("HerstellerArtNr", "sleutel_artikelcode", None, "hoog", ""),
        KolomMapping("EAN13", "sleutel_ean", None, "hoog", ""),
        KolomMapping("Zolltarifnummer", "gn_code", None, "hoog", ""),
        KolomMapping("ArtBeschreibung", "geen", None, "hoog", "al gevuld"),
    ])
    assert [k.kolom for k in m.sleutels()] == ["HerstellerArtNr", "EAN13"]
    assert [k.kolom for k in m.doelen()] == ["Zolltarifnummer"]


def test_mapping_rondreis_dict():
    m = Mapping(2, [KolomMapping("Gewicht", "netto_gewicht", "kg", "middel", "eenheid gegokt")], "let op")
    d = m.naar_dict()
    assert json.loads(json.dumps(d)) == d
    assert Mapping.uit_dict(d) == m


def test_lege_mapping():
    m = lege_mapping(1, ["A", "B"])
    assert m.kopregel_index == 1
    assert all(k.doelveld == "geen" and k.zekerheid == "laag" for k in m.kolommen)
    assert [k.kolom for k in m.kolommen] == ["A", "B"]


def test_schema_is_strict_en_bevat_enums():
    s = mapping_schema(["gn_code", "geen", "sleutel_ean"])
    assert s["type"] == "object" and s["additionalProperties"] is False
    assert set(s["required"]) == {"kopregel_index", "kolommen", "opmerkingen"}
    kolom = s["properties"]["kolommen"]["items"]
    assert kolom["additionalProperties"] is False
    assert kolom["properties"]["doelveld"]["enum"] == ["gn_code", "geen", "sleutel_ean"]
    assert None in kolom["properties"]["eenheid"]["enum"]
    assert set(kolom["properties"]["zekerheid"]["enum"]) == {"hoog", "middel", "laag"}


def test_bouw_fragment():
    rijen = [["ArtNr", "Gewicht"], ["2010005", None], ["2511105", 452]]
    tekst = bouw_fragment(rijen, "Sheet1", 27)
    assert "Sheet1" in tekst and "27" in tekst
    assert "rij 0" in tekst and "ArtNr" in tekst and "2511105" in tekst


def _nep_client(antwoord: dict):
    """Minimale nep van anthropic.Anthropic: onthoudt de aanroep, geeft JSON-tekst terug."""
    aanroepen = []

    def create(**kwargs):
        aanroepen.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(antwoord))],
                               stop_reason="end_turn")

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return client, aanroepen


def test_vraag_mapping_gebruikt_schema_en_parset_antwoord():
    antwoord = {
        "kopregel_index": 0,
        "kolommen": [
            {"kolom": "HerstellerArtNr", "doelveld": "sleutel_artikelcode", "eenheid": None,
             "zekerheid": "hoog", "toelichting": ""},
            {"kolom": "Nettogewicht", "doelveld": "netto_gewicht", "eenheid": "g",
             "zekerheid": "middel", "toelichting": "gram volgens mail"},
        ],
        "opmerkingen": "ok",
    }
    client, aanroepen = _nep_client(antwoord)
    cat = catalogus_voor_prompt(["UFI-code"], {"ursprungsland": "Land"})
    m = vraag_mapping(client, [["HerstellerArtNr", "Nettogewicht"], ["2010005", None]], "Sheet1", 1, cat)

    assert isinstance(m, Mapping)
    assert m.kolommen[1].doelveld == "netto_gewicht" and m.kolommen[1].eenheid == "g"
    assert m.opmerkingen == "ok"

    kw = aanroepen[0]
    assert kw["model"] == MODEL
    assert kw["output_config"]["format"]["type"] == "json_schema"
    enum = kw["output_config"]["format"]["schema"]["properties"]["kolommen"]["items"]["properties"]["doelveld"]["enum"]
    assert "ruw:UFI-code" in enum and "vast:ursprungsland" in enum and "gn_code" in enum
    systeem = kw["system"]
    assert isinstance(systeem, list) and systeem[0]["cache_control"] == {"type": "ephemeral"}
    assert "ruw:UFI-code" in systeem[0]["text"]
    assert "HerstellerArtNr" in kw["messages"][0]["content"]


def test_vraag_mapping_onbekend_doelveld_faalt():
    antwoord = {"kopregel_index": 0, "kolommen": [
        {"kolom": "X", "doelveld": "bestaat_niet", "eenheid": None, "zekerheid": "hoog", "toelichting": ""}],
        "opmerkingen": ""}
    client, _ = _nep_client(antwoord)
    with pytest.raises(ValueError):
        vraag_mapping(client, [["X"]], "Sheet1", 0, catalogus_voor_prompt([], {}))
```

- [ ] **Step 2: Draai — moet falen**

Run: `./venv/bin/pytest tests/test_mapping.py -v`
Expected: FAIL met `ModuleNotFoundError: No module named 'mapping'`

- [ ] **Step 3: Implementeer `mapping.py`**

```python
"""
Mapping van dealerkolommen naar doelvelden: datamodel, JSON-schema voor een
afgedwongen Claude-antwoord, en de aanroep zelf. Alleen de kopregel-
kandidaten en een paar voorbeeldrijen gaan naar de API, nooit het hele bestand.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from veldcatalogus import EENHEID_OPTIES

MODEL = "claude-opus-5"
ZEKERHEDEN = ["hoog", "middel", "laag"]

SYSTEEMPROMPT = """Je helpt een medewerker van Repair Care (fabrikant van houtreparatieproducten) om
invulbestanden van dealers automatisch te vullen met productdata.

Je krijgt de eerste rijen van een dealerbestand (Excel). Bepaal:
1. kopregel_index: de 0-gebaseerde index van de rij met kolomkoppen.
2. Per kolom uit die kopregel: welk doelveld uit de catalogus de dealer vraagt.
   - Kolommen die het artikel identificeren krijgen een sleutel_-veld
     (sleutel_artikelcode voor het Repair Care-artikelnummer / Hersteller-Artikelnummer /
     supplier item number; sleutel_ean voor EAN/GTIN; sleutel_omschrijving alleen als
     er geen ander sleutelveld is). Het eigen artikelnummer van de dealer is GEEN sleutel.
   - Kolommen die al door de dealer gevuld zijn of niet uit productdata af te leiden zijn
     krijgen 'geen'.
   - Kies bij gewichten en maten de eenheid die de dealer vraagt (uit de kop, de
     voorbeeldwaarden of de context). Onbekend: g voor gewicht, mm voor maten, en
     zekerheid 'middel'.
   - Gebruik 'vast:...'-velden voor bedrijfsgegevens zoals land van oorsprong of Bundesland.
   - Gebruik 'ruw:...'-velden alleen als geen gewoon veld past.
3. zekerheid: hoog als kop en voorbeelden eenduidig zijn, middel bij een aanname
   (bijvoorbeeld de eenheid), laag als je gokt.
4. toelichting: één korte zin, alleen bij middel/laag of bij 'geen'.

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
            kolommen=[KolomMapping(k["kolom"], k["doelveld"], k.get("eenheid"),
                                   k.get("zekerheid", "laag"), k.get("toelichting", ""))
                      for k in d.get("kolommen", [])],
            opmerkingen=d.get("opmerkingen", "") or "",
        )


def mapping_schema(doelveld_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "kopregel_index": {"type": "integer"},
            "kolommen": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kolom": {"type": "string"},
                        "doelveld": {"type": "string", "enum": list(doelveld_ids)},
                        "eenheid": {"type": ["string", "null"], "enum": list(EENHEID_OPTIES)},
                        "zekerheid": {"type": "string", "enum": ZEKERHEDEN},
                        "toelichting": {"type": "string"},
                    },
                    "required": ["kolom", "doelveld", "eenheid", "zekerheid", "toelichting"],
                    "additionalProperties": False,
                },
            },
            "opmerkingen": {"type": "string"},
        },
        "required": ["kopregel_index", "kolommen", "opmerkingen"],
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
                  catalogus: list[dict]) -> Mapping:
    """Eén Claude-aanroep; antwoord is JSON volgens mapping_schema."""
    ids = [c["id"] for c in catalogus]
    systeem = [{
        "type": "text",
        "text": SYSTEEMPROMPT + json.dumps(catalogus, ensure_ascii=False, indent=1),
        "cache_control": {"type": "ephemeral"},
    }]
    antwoord = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=systeem,
        messages=[{"role": "user", "content": bouw_fragment(rijen, tabblad, totaal_rijen)}],
        output_config={"format": {"type": "json_schema", "schema": mapping_schema(ids)}},
    )
    tekst = next(b.text for b in antwoord.content if b.type == "text")
    data = json.loads(tekst)
    mapping = Mapping.uit_dict(data)
    onbekend = [k.doelveld for k in mapping.kolommen if k.doelveld not in ids]
    if onbekend:
        raise ValueError(f"Onbekende doelvelden in mapping: {onbekend}")
    return mapping
```

- [ ] **Step 4: Draai — moet slagen**

Run: `./venv/bin/pytest tests/test_mapping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mapping.py tests/test_mapping.py
git commit -q -m "Mapping-model, JSON-schema en Claude-aanroep voor kolomherkenning

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```

---

### Task 6: Dealerbestand lezen en kopregel vinden

**Files:**
- Create: `dealer_invuller.py` (eerste deel)
- Test: `tests/test_dealer_invuller.py`

**Interfaces:**
- Produces:
  - `laad_werkboek(inhoud: bytes, bestandsnaam: str) -> openpyxl.Workbook` — `.xlsx` via `BytesIO`; `.csv` (utf-8-sig, scheidingsteken gesnoven met `csv.Sniffer`, fallback `;`) naar nieuw werkboek met tabblad `"Sheet1"`; ander formaat → `ValueError("Alleen .xlsx of .csv…")`
  - `kies_tabblad(wb, naam: str | None) -> Worksheet` — gegeven naam, anders eerste tabblad met ≥1 niet-lege cel
  - `lees_rijen(ws, n: int = 10) -> list[list]` — eerste n rijen als lijsten (values)
  - `vind_kopregel(rijen: list[list]) -> int` — eerste rij met ≥3 cellen die niet-lege tekst zijn; `ValueError` als geen
  - `koppen(ws, kopregel_index: int) -> dict[str, int]` — kolomnaam (getrimd; lege kop → `"Kolom C"`, duplicaat → `"Naam (2)"`) → 0-based kolomindex
  - `SLEUTELTYPE_ARG = {"sleutel_artikelcode": "artikelcode", "sleutel_ean": "ean", "sleutel_omschrijving": "omschrijving"}`

- [ ] **Step 1: Schrijf de falende tests**

`tests/test_dealer_invuller.py`:
```python
from pathlib import Path

import openpyxl
import pytest

from dealer_invuller import (
    kies_tabblad,
    koppen,
    laad_werkboek,
    lees_rijen,
    vind_kopregel,
)
from tests.conftest import SEEFELDER_KOPPEN, SEEFELDER_RIJEN, maak_dealerbestand


def test_laad_xlsx(seefelder_bestand):
    wb = laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name)
    ws = kies_tabblad(wb, None)
    assert ws.title == "Sheet1"
    assert ws.cell(1, 1).value == "ArtNr"


def test_laad_csv():
    inhoud = "ArtNr;Gewicht\n2010005;\n".encode("utf-8-sig")
    wb = laad_werkboek(inhoud, "lijst.csv")
    ws = kies_tabblad(wb, None)
    assert [c.value for c in ws[1]] == ["ArtNr", "Gewicht"]
    assert ws.cell(2, 1).value == "2010005"


def test_laad_onbekend_formaat():
    with pytest.raises(ValueError) as e:
        laad_werkboek(b"x", "oud.xls")
    assert ".xlsx" in str(e.value)


def test_kies_tabblad_slaat_lege_over(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.title = "Leeg"
    ws2 = wb.create_sheet("Data")
    ws2.append(["ArtNr", "EAN", "Gewicht"])
    pad = tmp_path / "twee.xlsx"
    wb.save(pad)
    wb2 = laad_werkboek(pad.read_bytes(), pad.name)
    assert kies_tabblad(wb2, None).title == "Data"
    assert kies_tabblad(wb2, "Leeg").title == "Leeg"


def test_lees_rijen_en_kopregel_met_voorloop(tmp_path):
    pad = maak_dealerbestand(tmp_path / "v.xlsx", ["ArtNr", "EAN", "Gewicht (kg)"], [["1", "2", None]],
                             voorloop=[["Anfrage Stammdaten"], [], ["Bitte ausfüllen", None, None]])
    ws = kies_tabblad(laad_werkboek(pad.read_bytes(), pad.name), None)
    rijen = lees_rijen(ws, 10)
    assert rijen[0][0] == "Anfrage Stammdaten"
    assert vind_kopregel(rijen) == 3


def test_vind_kopregel_geen():
    with pytest.raises(ValueError):
        vind_kopregel([[1, 2, 3], ["a", None, None]])


def test_koppen_dedup_en_leeg(tmp_path):
    pad = maak_dealerbestand(tmp_path / "k.xlsx", ["ArtNr", " Gewicht ", None, "Gewicht", "EAN"], [[1, 2, 3, 4, 5]])
    ws = kies_tabblad(laad_werkboek(pad.read_bytes(), pad.name), None)
    k = koppen(ws, 0)
    assert k == {"ArtNr": 0, "Gewicht": 1, "Kolom C": 2, "Gewicht (2)": 3, "EAN": 4}
```

- [ ] **Step 2: Draai — moet falen**

Run: `./venv/bin/pytest tests/test_dealer_invuller.py -v`
Expected: FAIL met `ModuleNotFoundError: No module named 'dealer_invuller'`

- [ ] **Step 3: Implementeer het leesdeel van `dealer_invuller.py`**

```python
"""
Kern van de dealer-Excel invuller (geen Streamlit-code).

Leest een dealerbestand (.xlsx/.csv), vindt de kopregel, matcht artikelen via de
mapping, vult lege cellen met productdata en voegt een tabblad 'Controle' toe.
Ook bruikbaar als script:

    python3 dealer_invuller.py dealerbestand.xlsx [--mapping mapping.json] [--overschrijven]
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

from artikeldata import Artikeldata, Match, Waarde
from mapping import Mapping
from veldcatalogus import converteer, veld

SLEUTELTYPE_ARG = {
    "sleutel_artikelcode": "artikelcode",
    "sleutel_ean": "ean",
    "sleutel_omschrijving": "omschrijving",
}
GEEL = openpyxl.styles.PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
CONTROLE_TAB = "Controle"


def laad_werkboek(inhoud: bytes, bestandsnaam: str) -> openpyxl.Workbook:
    ext = Path(bestandsnaam).suffix.lower()
    if ext == ".xlsx":
        return openpyxl.load_workbook(io.BytesIO(inhoud))
    if ext == ".csv":
        tekst = inhoud.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(tekst[:2000], delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        for rij in csv.reader(io.StringIO(tekst), dialect):
            ws.append([c if c != "" else None for c in rij])
        return wb
    raise ValueError(f"Bestandsformaat {ext or '(geen)'} wordt niet ondersteund. Sla het bestand op als .xlsx of .csv.")


def kies_tabblad(wb: openpyxl.Workbook, naam: str | None):
    if naam:
        return wb[naam]
    for ws in wb.worksheets:
        for rij in ws.iter_rows(values_only=True):
            if any(c is not None for c in rij):
                return ws
    return wb.worksheets[0]


def lees_rijen(ws, n: int = 10) -> list[list]:
    uit = []
    for i, rij in enumerate(ws.iter_rows(values_only=True)):
        if i >= n:
            break
        uit.append(list(rij))
    return uit


def vind_kopregel(rijen: list[list]) -> int:
    for i, rij in enumerate(rijen):
        teksten = [c for c in rij if isinstance(c, str) and c.strip()]
        if len(teksten) >= 3:
            return i
    raise ValueError("Geen kopregel gevonden in de eerste rijen (verwacht een rij met minstens 3 tekstkoppen).")


def koppen(ws, kopregel_index: int) -> dict[str, int]:
    rij = next(ws.iter_rows(min_row=kopregel_index + 1, max_row=kopregel_index + 1, values_only=True))
    uit: dict[str, int] = {}
    for i, c in enumerate(rij):
        naam = str(c).strip() if c is not None and str(c).strip() else f"Kolom {get_column_letter(i + 1)}"
        basis, n = naam, 2
        while naam in uit:
            naam = f"{basis} ({n})"
            n += 1
        uit[naam] = i
    return uit
```

- [ ] **Step 4: Draai — moet slagen**

Run: `./venv/bin/pytest tests/test_dealer_invuller.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dealer_invuller.py tests/test_dealer_invuller.py
git commit -q -m "Dealerbestand lezen: xlsx/csv, tabblad, kopregel, koppen

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```

---

### Task 7: Matchen, invullen en tabblad Controle

**Files:**
- Modify: `dealer_invuller.py` (toevoegen)
- Modify: `tests/test_dealer_invuller.py` (tests toevoegen)

**Interfaces:**
- Consumes: Task 4 (`Artikeldata.zoek/waarde`, `Match`, `Waarde`), Task 5 (`Mapping`), Task 6.
- Produces:
  - `@dataclass VeldResultaat(kolom: str, veld_id: str, waarde: object, eenheid: str | None, bron: str, regel: str | None, status: str)` — status ∈ `ingevuld | leeg | bestaand | controleer`
  - `@dataclass RijResultaat(rij: int, sleutel: str, match: Match | None, velden: list[VeldResultaat])` — `rij` is 1-based Excel-rijnummer
  - `@dataclass Rapport(rijen: list[RijResultaat])` met `samenvatting() -> dict` (`totaal`, `gevonden`, `niet_gevonden`, `via` (dict), `ingevuld`, `gaten`, `gaten_per_kolom` (dict))
  - `match_rijen(ws, mapping: Mapping, artikeldata: Artikeldata) -> list[RijResultaat]` — alleen matchen, `velden` leeg
  - `vul_in(ws, mapping, artikeldata, overschrijven: bool = False) -> Rapport`
  - `schrijf_controle(wb, rapport: Rapport) -> None`
  - `werkboek_naar_bytes(wb) -> bytes`
  - `verwerk(inhoud: bytes, bestandsnaam: str, mapping: Mapping, artikeldata: Artikeldata, tabblad: str | None = None, overschrijven: bool = False) -> tuple[bytes, Rapport]`
  - `maak_waarde(w: Waarde, eenheid_doel: str | None) -> object` — omrekenen + afronden (3 decimalen), `float.is_integer()` → `int`

- [ ] **Step 1: Voeg tests toe aan `tests/test_dealer_invuller.py`**

```python
from artikeldata import Artikeldata
from dealer_invuller import (
    CONTROLE_TAB,
    Rapport,
    maak_waarde,
    match_rijen,
    schrijf_controle,
    verwerk,
    vul_in,
    werkboek_naar_bytes,
)
from artikeldata import Waarde
from mapping import KolomMapping, Mapping

SEEFELDER_MAPPING = Mapping(0, [
    KolomMapping("ArtNr", "geen", None, "hoog", "eigen nummer dealer"),
    KolomMapping("Bundesland", "vast:bundesland", None, "hoog", ""),
    KolomMapping("Ursprungsland", "vast:ursprungsland", None, "hoog", ""),
    KolomMapping("Zolltarifnummer", "gn_code", None, "hoog", ""),
    KolomMapping("Nettogewicht", "netto_gewicht", "g", "middel", ""),
    KolomMapping("Länge", "lengte", "cm", "middel", ""),
    KolomMapping("Breite", "breedte", "cm", "middel", ""),
    KolomMapping("Höhe", "hoogte", "cm", "middel", ""),
    KolomMapping("ArtBeschreibung", "geen", None, "hoog", ""),
    KolomMapping("Primärlieferant", "geen", None, "hoog", ""),
    KolomMapping("VKEinheit", "geen", None, "hoog", ""),
    KolomMapping("HerstellerArtNr", "sleutel_artikelcode", None, "hoog", ""),
    KolomMapping("EAN13", "sleutel_ean", None, "hoog", ""),
])

VASTE_TEST = {"ursprungsland": {"label": "Land", "standaard": None, "per_prefix": {"2": "NLD"}, "per_artikel": {}},
              "bundesland": {"label": "Bundesland", "standaard": None}}


@pytest.fixture
def ad(artikeldata_dict):
    return Artikeldata(artikeldata_dict, VASTE_TEST)


@pytest.mark.parametrize("w, doel, verwacht", [
    (Waarde(318.0, "g", "b"), "kg", 0.318),
    (Waarde(318.0, "g", "b"), "g", 318),
    (Waarde(184.0, "mm", "b"), "cm", 18.4),
    (Waarde(89.0, "mm", "b"), None, 89),
    (Waarde("32141010", None, "b"), None, "32141010"),
    (Waarde(0.3333333, "kg", "b"), "kg", 0.333),
])
def test_maak_waarde(w, doel, verwacht):
    assert maak_waarde(w, doel) == verwacht
    assert type(maak_waarde(w, doel)) is type(verwacht)


def test_match_rijen(seefelder_bestand, ad):
    ws = kies_tabblad(laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name), None)
    res = match_rijen(ws, SEEFELDER_MAPPING, ad)
    assert [r.rij for r in res] == [2, 3, 4, 5, 6]
    assert res[0].match.via == "artikelcode"
    assert res[3].sleutel == "0 / 8714748004955"
    assert res[3].match is None                 # Wipes zit niet in de fixture
    assert all(r.velden == [] for r in res)


def test_vul_in_seefelder(seefelder_bestand, ad):
    wb = laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name)
    ws = kies_tabblad(wb, None)
    rapport = vul_in(ws, SEEFELDER_MAPPING, ad)

    # Rij 2 = DRY FIX UNI: gn, gewicht, maten in cm, land NLD via prefix, Bundesland leeg+geel.
    assert ws["D2"].value == "32141010"
    assert ws["E2"].value == 318
    assert (ws["F2"].value, ws["G2"].value, ws["H2"].value) == (8.9, 4.8, 18.4)
    assert ws["C2"].value == "NLD"
    assert ws["B2"].value is None and ws["B2"].fill.start_color.rgb.endswith("FFFF00")
    # Rij 4 = spatel: bestaande GN-code blijft staan, land leeg (prefix 4 niet geconfigureerd).
    assert ws["D4"].value == "82055910"
    assert ws["C4"].value is None
    # Rij 5 = Wipes: niet gevonden -> alle doelcellen geel, leeg.
    assert ws["D5"].value is None and ws["D5"].fill.start_color.rgb.endswith("FFFF00")
    # Rij 6 = Box: geen GN, geen maat -> geel; gewicht wel.
    assert ws["D6"].value is None and ws["E6"].value == 8710
    # 'geen'-kolommen ongemoeid.
    assert ws["I2"].value == "REPAIR CARE DRY FIX UNI"

    s = rapport.samenvatting()
    assert s["totaal"] == 5 and s["gevonden"] == 4 and s["niet_gevonden"] == 1
    assert s["via"] == {"artikelcode": 4}
    assert s["gaten_per_kolom"]["Bundesland"] == 5
    assert s["gaten_per_kolom"]["Zolltarifnummer"] == 2   # Wipes + Box
    statussen = {(v.kolom, v.status) for v in rapport.rijen[2].velden}
    assert ("Zolltarifnummer", "bestaand") in statussen


def test_vul_in_overschrijven(seefelder_bestand, ad):
    wb = laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name)
    ws = kies_tabblad(wb, None)
    vul_in(ws, SEEFELDER_MAPPING, ad, overschrijven=True)
    assert ws["D4"].value == "82055910"  # zelfde waarde uit de data, nu wél geschreven


def test_vul_in_zonder_sleutel_faalt(seefelder_bestand, ad):
    ws = kies_tabblad(laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name), None)
    m = Mapping(0, [KolomMapping("Zolltarifnummer", "gn_code", None, "hoog", "")])
    with pytest.raises(ValueError):
        vul_in(ws, m, ad)


def test_controle_tab(seefelder_bestand, ad):
    wb = laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name)
    ws = kies_tabblad(wb, None)
    rapport = vul_in(ws, SEEFELDER_MAPPING, ad)
    schrijf_controle(wb, rapport)
    schrijf_controle(wb, rapport)  # tweede keer: vervangen, niet dupliceren
    assert wb.sheetnames.count(CONTROLE_TAB) == 1
    ct = wb[CONTROLE_TAB]
    tekst = "\n".join(" ".join(str(c) for c in rij if c is not None) for rij in ct.iter_rows(values_only=True))
    assert "2010005" in tekst and "artikelcode" in tekst
    assert "222" in tekst and "96" in tekst          # rekenregel gewicht
    assert "naast elkaar" in tekst                     # rekenregel maat
    assert "niet gevonden" in tekst.lower()
    assert "Gevonden: 4" in tekst


def test_verwerk_rondreis(seefelder_bestand, ad):
    uit, rapport = verwerk(seefelder_bestand.read_bytes(), seefelder_bestand.name, SEEFELDER_MAPPING, ad)
    wb = openpyxl.load_workbook(io.BytesIO(uit))
    assert CONTROLE_TAB in wb.sheetnames
    assert wb["Sheet1"]["E2"].value == 318
    assert rapport.samenvatting()["gevonden"] == 4


def test_verwerk_csv_met_kg_en_cm(tmp_path, ad):
    inhoud = "Item no.;Net weight (kg);Height (cm)\n2010005;;\n".encode("utf-8")
    m = Mapping(0, [KolomMapping("Item no.", "sleutel_artikelcode", None, "hoog", ""),
                    KolomMapping("Net weight (kg)", "netto_gewicht", "kg", "hoog", ""),
                    KolomMapping("Height (cm)", "hoogte", "cm", "hoog", "")])
    uit, _ = verwerk(inhoud, "lijst.csv", m, ad)
    ws = openpyxl.load_workbook(io.BytesIO(uit))["Sheet1"]
    assert ws["B2"].value == 0.318 and ws["C2"].value == 18.4
```

Voeg bovenaan het testbestand `import io` toe.

- [ ] **Step 2: Draai — moet falen**

Run: `./venv/bin/pytest tests/test_dealer_invuller.py -v`
Expected: FAIL met `ImportError: cannot import name 'Rapport'`

- [ ] **Step 3: Implementeer matchen, invullen, Controle**

Toevoegen aan `dealer_invuller.py`:

```python
@dataclass
class VeldResultaat:
    kolom: str
    veld_id: str
    waarde: object
    eenheid: str | None
    bron: str
    regel: str | None
    status: str  # ingevuld | leeg | bestaand | controleer


@dataclass
class RijResultaat:
    rij: int                     # 1-based Excel-rijnummer
    sleutel: str
    match: Match | None
    velden: list[VeldResultaat] = field(default_factory=list)


@dataclass
class Rapport:
    rijen: list[RijResultaat]

    def samenvatting(self) -> dict:
        via: dict[str, int] = {}
        gaten_per_kolom: dict[str, int] = {}
        ingevuld = gaten = 0
        for r in self.rijen:
            if r.match:
                via[r.match.via] = via.get(r.match.via, 0) + 1
            for v in r.velden:
                if v.status == "ingevuld":
                    ingevuld += 1
                elif v.status == "leeg":
                    gaten += 1
                    gaten_per_kolom[v.kolom] = gaten_per_kolom.get(v.kolom, 0) + 1
        gevonden = sum(1 for r in self.rijen if r.match)
        return {
            "totaal": len(self.rijen), "gevonden": gevonden, "niet_gevonden": len(self.rijen) - gevonden,
            "via": via, "ingevuld": ingevuld, "gaten": gaten, "gaten_per_kolom": gaten_per_kolom,
        }


def maak_waarde(w: Waarde, eenheid_doel: str | None):
    """Bronwaarde omrekenen naar de gevraagde eenheid; getallen netjes afronden."""
    if isinstance(w.waarde, bool) or not isinstance(w.waarde, (int, float)):
        return w.waarde
    getal = float(w.waarde)
    if w.eenheid and eenheid_doel:
        getal = converteer(getal, w.eenheid, eenheid_doel)
    getal = round(getal, 3)
    return int(getal) if getal.is_integer() else getal


def _is_leeg(cel) -> bool:
    return cel.value is None or (isinstance(cel.value, str) and not cel.value.strip())


def _datarijen(ws, kopregel_index: int):
    for rijnr in range(kopregel_index + 2, ws.max_row + 1):
        cellen = ws[rijnr]
        if any(not _is_leeg(c) for c in cellen):
            yield rijnr, cellen


def _zoek_match(cellen, mapping: Mapping, kolomindex: dict[str, int], artikeldata: Artikeldata):
    argumenten: dict[str, object] = {}
    delen = []
    for k in mapping.sleutels():
        i = kolomindex.get(k.kolom)
        if i is None:
            continue
        waarde = cellen[i].value
        argumenten[SLEUTELTYPE_ARG[k.doelveld]] = waarde
        delen.append("" if waarde is None else str(waarde))
    return artikeldata.zoek(**argumenten), " / ".join(delen)


def match_rijen(ws, mapping: Mapping, artikeldata: Artikeldata) -> list[RijResultaat]:
    if not mapping.sleutels():
        raise ValueError("Geen sleutelkolom gekozen (artikelnummer, EAN of omschrijving).")
    kolomindex = koppen(ws, mapping.kopregel_index)
    uit = []
    for rijnr, cellen in _datarijen(ws, mapping.kopregel_index):
        match, sleutel = _zoek_match(cellen, mapping, kolomindex, artikeldata)
        uit.append(RijResultaat(rijnr, sleutel, match))
    return uit


def vul_in(ws, mapping: Mapping, artikeldata: Artikeldata, overschrijven: bool = False) -> Rapport:
    rijen = match_rijen(ws, mapping, artikeldata)
    kolomindex = koppen(ws, mapping.kopregel_index)
    doelen = [(k, kolomindex[k.kolom]) for k in mapping.doelen() if k.kolom in kolomindex]
    for r in rijen:
        for k, i in doelen:
            cel = ws.cell(row=r.rij, column=i + 1)
            w = artikeldata.waarde(r.match.artikel, k.doelveld) if r.match else None
            if not _is_leeg(cel) and not overschrijven:
                r.velden.append(VeldResultaat(k.kolom, k.doelveld, cel.value, k.eenheid,
                                              "dealer (bestaande waarde)", None, "bestaand"))
                continue
            if w is None or w.waarde is None or w.waarde == "":
                cel.fill = GEEL
                bron = "artikel niet gevonden" if r.match is None else "geen waarde in productdata"
                r.velden.append(VeldResultaat(k.kolom, k.doelveld, None, k.eenheid, bron, None, "leeg"))
                continue
            cel.value = maak_waarde(w, k.eenheid)
            status = "controleer" if r.match.via == "omschrijving" else "ingevuld"
            r.velden.append(VeldResultaat(k.kolom, k.doelveld, cel.value, k.eenheid, w.bron, w.regel, status))
    return Rapport(rijen)


def schrijf_controle(wb, rapport: Rapport) -> None:
    if CONTROLE_TAB in wb.sheetnames:
        del wb[CONTROLE_TAB]
    ct = wb.create_sheet(CONTROLE_TAB)
    s = rapport.samenvatting()
    ct.append(["Samenvatting"])
    ct.append([f"Rijen: {s['totaal']}", f"Gevonden: {s['gevonden']}", f"Niet gevonden: {s['niet_gevonden']}",
               f"Ingevuld: {s['ingevuld']}", f"Gaten: {s['gaten']}"])
    ct.append(["Gevonden via: " + ", ".join(f"{k} {v}" for k, v in s["via"].items())])
    ct.append(["Gaten per kolom: " + ", ".join(f"{k} {v}" for k, v in s["gaten_per_kolom"].items())])
    ct.append([])
    ct.append(["Rij", "Sleutel", "Artikelcode", "Gevonden via", "Kolom", "Doelveld", "Waarde", "Eenheid",
               "Status", "Bron", "Rekenregel"])
    for r in rapport.rijen:
        if r.match is None:
            ct.append([r.rij, r.sleutel, None, "niet gevonden"])
            continue
        code = r.match.artikel.get("artikelcode")
        via = r.match.via if r.match.score >= 1.0 else f"{r.match.via} ({r.match.score:.2f})"
        for v in r.velden:
            ct.append([r.rij, r.sleutel, code, via, v.kolom, v.veld_id, v.waarde, v.eenheid,
                       v.status, v.bron, v.regel])
    for kol, breedte in zip("ABCDEFGHIJK", (6, 26, 12, 14, 20, 22, 16, 8, 11, 34, 50)):
        ct.column_dimensions[kol].width = breedte


def werkboek_naar_bytes(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def verwerk(inhoud: bytes, bestandsnaam: str, mapping: Mapping, artikeldata: Artikeldata,
            tabblad: str | None = None, overschrijven: bool = False) -> tuple[bytes, Rapport]:
    wb = laad_werkboek(inhoud, bestandsnaam)
    ws = kies_tabblad(wb, tabblad)
    rapport = vul_in(ws, mapping, artikeldata, overschrijven)
    schrijf_controle(wb, rapport)
    return werkboek_naar_bytes(wb), rapport
```

- [ ] **Step 4: Draai — moet slagen**

Run: `./venv/bin/pytest tests/test_dealer_invuller.py -v`
Expected: PASS. Let op bij `test_maak_waarde`: `type(...) is type(verwacht)` eist dat `318.0` als `int` 318 terugkomt en `0.318` als `float`.

- [ ] **Step 5: Draai de hele testset**

Run: `./venv/bin/pytest -q`
Expected: alles PASS

- [ ] **Step 6: Commit**

```bash
git add dealer_invuller.py tests/test_dealer_invuller.py
git commit -q -m "Invullen van dealerbestand met rapport en tabblad Controle

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```

---

### Task 8: Commandoregel-script en rooktest op het Seefelder-bestand

**Files:**
- Modify: `dealer_invuller.py` (toevoegen `bepaal_mapping`, `main`)
- Modify: `tests/test_dealer_invuller.py` (test voor `main` met `--mapping`)

**Interfaces:**
- Consumes: alles hierboven; `vraag_mapping`, `lege_mapping` uit Task 5; `catalogus_voor_prompt` uit Task 1.
- Produces:
  - `bepaal_mapping(client, ws, artikeldata: Artikeldata) -> Mapping` — leest 10 rijen, vindt kopregel, roept Claude aan; bij `anthropic.APIError` of `ValueError` → `lege_mapping` met `opmerkingen` = foutmelding
  - `main(argv: list[str] | None = None) -> int` — argumenten: `bestand`, `--mapping pad.json` (overslaat Claude), `--schrijf-mapping pad.json` (slaat de gebruikte mapping op), `--overschrijven`, `--tabblad naam`, `--uit pad.xlsx` (standaard `<naam>_ingevuld.xlsx`)

- [ ] **Step 1: Voeg de test toe**

```python
import json

from dealer_invuller import main as cli_main


def test_cli_met_mapping_bestand(seefelder_bestand, tmp_path, artikeldata_dict, monkeypatch):
    pj = tmp_path / "artikeldata.json"
    pj.write_text(json.dumps(artikeldata_dict), encoding="utf-8")
    pv = tmp_path / "vaste.json"
    pv.write_text(json.dumps(VASTE_TEST), encoding="utf-8")
    import artikeldata as ad_mod
    monkeypatch.setattr(ad_mod, "ARTIKELDATA_FILE", pj)
    monkeypatch.setattr(ad_mod, "VASTE_WAARDEN_FILE", pv)

    pm = tmp_path / "mapping.json"
    pm.write_text(json.dumps(SEEFELDER_MAPPING.naar_dict()), encoding="utf-8")
    uit = tmp_path / "uit.xlsx"
    code = cli_main([str(seefelder_bestand), "--mapping", str(pm), "--uit", str(uit)])
    assert code == 0
    wb = openpyxl.load_workbook(uit)
    assert wb["Sheet1"]["E2"].value == 318
    assert CONTROLE_TAB in wb.sheetnames
```

- [ ] **Step 2: Draai — moet falen**

Run: `./venv/bin/pytest tests/test_dealer_invuller.py::test_cli_met_mapping_bestand -v`
Expected: FAIL met `ImportError: cannot import name 'main'`

- [ ] **Step 3: Implementeer `bepaal_mapping` en `main`**

Toevoegen aan `dealer_invuller.py` (imports uitbreiden met `import argparse, json, os, sys`, `import anthropic`, `from mapping import Mapping, lege_mapping, vraag_mapping`, `from veldcatalogus import catalogus_voor_prompt, converteer, veld`; de bestaande `from mapping import Mapping` vervangen):

```python
def bepaal_mapping(client, ws, artikeldata: Artikeldata) -> Mapping:
    """Kopregel zoeken en Claude om een mapping vragen; bij een fout een lege mapping."""
    rijen = lees_rijen(ws, 10)
    try:
        kopregel = vind_kopregel(rijen)
    except ValueError as e:
        return Mapping(0, [], opmerkingen=str(e))
    namen = list(koppen(ws, kopregel).keys())
    if client is None:
        m = lege_mapping(kopregel, namen)
        m.opmerkingen = "Geen API-client: mapping handmatig kiezen."
        return m
    catalogus = catalogus_voor_prompt(artikeldata.ruwe_kolommen, artikeldata.vaste_sleutels)
    try:
        m = vraag_mapping(client, rijen, ws.title, ws.max_row - kopregel - 1, catalogus)
    except (anthropic.APIError, ValueError, StopIteration, json.JSONDecodeError) as e:
        m = lege_mapping(kopregel, namen)
        m.opmerkingen = f"Mapping door Claude mislukt ({e}). Kies de velden handmatig."
        return m
    # Kolommen die Claude niet noemde toevoegen als 'geen', zodat de UI compleet is.
    genoemd = {k.kolom for k in m.kolommen}
    for naam in namen:
        if naam not in genoemd:
            m.kolommen.append(lege_mapping(kopregel, [naam]).kolommen[0])
    return m


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Vul een dealer-Excelbestand met Repair Care-productdata.")
    p.add_argument("bestand")
    p.add_argument("--mapping", help="mapping.json gebruiken in plaats van Claude")
    p.add_argument("--schrijf-mapping", help="gebruikte mapping opslaan als JSON")
    p.add_argument("--overschrijven", action="store_true")
    p.add_argument("--tabblad")
    p.add_argument("--uit")
    args = p.parse_args(argv)

    pad = Path(args.bestand)
    inhoud = pad.read_bytes()
    artikeldata = Artikeldata.laad()
    wb = laad_werkboek(inhoud, pad.name)
    ws = kies_tabblad(wb, args.tabblad)

    if args.mapping:
        mapping = Mapping.uit_dict(json.loads(Path(args.mapping).read_text(encoding="utf-8")))
    else:
        client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
        mapping = bepaal_mapping(client, ws, artikeldata)
        if mapping.opmerkingen:
            print("Opmerking:", mapping.opmerkingen)
    if args.schrijf_mapping:
        Path(args.schrijf_mapping).write_text(json.dumps(mapping.naar_dict(), ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    for k in mapping.kolommen:
        print(f"  {k.kolom:30} -> {k.doelveld:24} {k.eenheid or '':4} [{k.zekerheid}] {k.toelichting}")

    uit_bytes, rapport = verwerk(inhoud, pad.name, mapping, artikeldata, ws.title, args.overschrijven)
    uit = Path(args.uit) if args.uit else pad.with_name(pad.stem + "_ingevuld.xlsx")
    uit.write_bytes(uit_bytes)
    s = rapport.samenvatting()
    print(f"Geschreven: {uit}")
    print(f"Rijen {s['totaal']}, gevonden {s['gevonden']}, niet gevonden {s['niet_gevonden']}, "
          f"ingevuld {s['ingevuld']}, gaten {s['gaten']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Draai — moet slagen**

Run: `./venv/bin/pytest -q`
Expected: alles PASS

- [ ] **Step 5: Rooktest op het echte Seefelder-bestand met een handmatige mapping (zonder API)**

Schrijf `docs/superpowers/mapping-seefelder.json` met exact de inhoud van `SEEFELDER_MAPPING.naar_dict()` uit de test (kopregel_index 0, dezelfde 13 kolommen). Daarna:

Run: `./venv/bin/python dealer_invuller.py "Primärlieferant_973184.xlsx" --mapping docs/superpowers/mapping-seefelder.json --uit /private/tmp/claude-501/-Users-ralfknevel-Desktop-Productinfo-intern-tool/c94d70a3-3243-4200-8ea1-a2ff4aa590d9/scratchpad/seefelder_ingevuld.xlsx`
Expected: `Rijen 27, gevonden 27, niet gevonden 0`, gaten = 27 (Bundesland) + 27 (Ursprungsland, want vaste_waarden.json heeft nog `null`) + 1 (GN Box 5) + 3 (L/B/H Wipes) = 58.

Controleer steekproef: `./venv/bin/python -c "import openpyxl; ws=openpyxl.load_workbook('<scratchpad>/seefelder_ingevuld.xlsx')['Sheet1']; print([c.value for c in ws[2]][:8]); print([c.value for c in ws[13]][:8])"`
Expected rij 2: `['2010005', None, None, '32141010', 318, 8.9, 4.8, 18.4]`; rij 13 (DRY SEAL MP wit): GN `32141010`, gewicht 452, maten `4.9, 4.9, 23`.

- [ ] **Step 6: Rooktest mét Claude (handmatig, alleen als `ANTHROPIC_API_KEY` gezet is)**

Run: `./venv/bin/python dealer_invuller.py "Primärlieferant_973184.xlsx" --schrijf-mapping <scratchpad>/mapping-claude.json --uit <scratchpad>/seefelder_claude.xlsx`
Expected: mapping-uitdraai waarin `HerstellerArtNr -> sleutel_artikelcode`, `EAN13 -> sleutel_ean`, `Zolltarifnummer -> gn_code`, `Nettogewicht -> netto_gewicht g`, `Länge/Breite/Höhe -> lengte/breedte/hoogte cm`, `Ursprungsland -> vast:ursprungsland`, `Bundesland -> vast:bundesland`, overige `geen`. Wijkt Claude af (bijvoorbeeld mm in plaats van cm), noteer dat in de commit-boodschap; de prompt in `mapping.py` mag dan worden aangescherpt met één extra regel, gevolgd door `./venv/bin/pytest -q`.

Zonder API-key: deze stap overslaan en dat melden.

- [ ] **Step 7: Commit**

```bash
git add dealer_invuller.py tests/test_dealer_invuller.py docs/superpowers/mapping-seefelder.json
git commit -q -m "CLI voor dealer-Excel invuller met mapping via Claude of JSON

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```

---

### Task 9: Streamlit-integratie

**Files:**
- Modify: `app.py:297-356` (`main()`), nieuwe functies `toon_chat()` en `toon_dealer_excel()`
- Test: geen unit-test (UI); handmatige controle via `streamlit run app.py`

**Interfaces:**
- Consumes: `Artikeldata.laad()`, `laad_werkboek`, `kies_tabblad`, `bepaal_mapping`, `match_rijen`, `verwerk`, `Mapping`, `KolomMapping`, `catalogus_voor_prompt`, `EENHEID_OPTIES`.

- [ ] **Step 1: Splits `main()` in navigatie + `toon_chat()`**

Vervang in `app.py` het deel van `main()` vanaf de regel `if "kennisbank_tekst" not in st.session_state:` tot en met `st.rerun()` aan het einde door:

```python
    if "client" not in st.session_state:
        st.session_state.client = anthropic.Anthropic(api_key=api_key)

    keuze = st.segmented_control(
        "Onderdeel", ["Productinfo-chat", "Dealer-Excel"],
        default="Productinfo-chat", label_visibility="collapsed",
    )
    if keuze == "Dealer-Excel":
        toon_dealer_excel()
    else:
        toon_chat(documenten)


def toon_chat(documenten: list[dict]) -> None:
    if "kennisbank_tekst" not in st.session_state:
        st.session_state.kennisbank_tekst = bouw_kennisbank_tekst(documenten)
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Knop om het gesprek te wissen (rechtsboven, alleen tijdens een gesprek).
    if st.session_state.messages:
        _, rechts = st.columns([4, 1])
        if rechts.button("Wissen", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # Welkomstscherm met voorbeeldvragen zolang er nog niets gevraagd is.
    gekozen_voorbeeld = None
    if not st.session_state.messages:
        st.markdown(
            f"<p style='color:{BODYGRIJS}; margin-bottom:6px;'>"
            "Waar kan ik je mee helpen? Probeer bijvoorbeeld:</p>",
            unsafe_allow_html=True,
        )
        kolommen = st.columns(2)
        for i, v in enumerate(VOORBEELDVRAGEN):
            if kolommen_klik(kolommen=kolommen, index=i, vraag=v):
                gekozen_voorbeeld = v

    # Eerdere berichten tonen.
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    getypt = st.chat_input("Stel je vraag over een product...")
    vraag = getypt or gekozen_voorbeeld
    if vraag:
        beantwoord(vraag)
        st.rerun()
```

De kennisbank-controle (`documenten` leeg → waarschuwing + `st.stop()`) blijft vóór de keuzeknop staan, zoals nu.

- [ ] **Step 2: Voeg `toon_dealer_excel()` toe**

Imports bovenaan `app.py` uitbreiden:
```python
import hashlib
import io

import pandas as pd

from artikeldata import Artikeldata
from dealer_invuller import (
    bepaal_mapping, kies_tabblad, koppen, laad_werkboek, lees_rijen, match_rijen, verwerk,
)
from mapping import KolomMapping, Mapping, lege_mapping
from veldcatalogus import EENHEID_OPTIES, catalogus_voor_prompt
```
(`pandas` wordt door Streamlit meegeleverd; niet apart in requirements.)

Functie:
```python
def toon_dealer_excel() -> None:
    st.markdown(
        f"<p style='color:{BODYGRIJS};'>Upload een invulbestand van een dealer. De tool herkent de "
        "kolommen, jij controleert de mapping, daarna worden de lege cellen ingevuld.</p>",
        unsafe_allow_html=True,
    )
    try:
        artikeldata = Artikeldata.laad()
    except FileNotFoundError:
        st.error("artikeldata.json ontbreekt. Draai eerst:  python3 ingest_artikeldata.py")
        return

    bestand = st.file_uploader("Dealerbestand", type=["xlsx", "csv"], label_visibility="collapsed")
    if bestand is None:
        st.session_state.pop("dealer", None)
        return
    inhoud = bestand.getvalue()
    sleutel = hashlib.sha256(inhoud).hexdigest()

    try:
        wb = laad_werkboek(inhoud, bestand.name)
    except ValueError as e:
        st.error(str(e))
        return
    tabblad = None
    if len(wb.sheetnames) > 1:
        tabblad = st.selectbox("Tabblad", wb.sheetnames, index=wb.sheetnames.index(kies_tabblad(wb, None).title))
    ws = kies_tabblad(wb, tabblad)

    staat = st.session_state.get("dealer")
    if not staat or staat["sleutel"] != (sleutel, ws.title):
        with st.spinner("Kolommen herkennen…"):
            mapping = bepaal_mapping(st.session_state.client, ws, artikeldata)
        staat = {"sleutel": (sleutel, ws.title), "mapping": mapping}
        st.session_state.dealer = staat
    mapping: Mapping = staat["mapping"]
    if mapping.opmerkingen:
        st.info(mapping.opmerkingen)
    if not mapping.kolommen:
        # Geen kopregel herkend: gebruiker wijst de rij aan.
        rijen = lees_rijen(ws, 10)
        opties = [f"rij {i + 1}: " + " | ".join(str(c) for c in r if c is not None)[:80]
                  for i, r in enumerate(rijen)]
        gekozen = st.selectbox("Kopregel niet herkend — kies de rij met de kolomkoppen",
                               list(range(len(opties))), format_func=lambda i: opties[i])
        mapping = lege_mapping(gekozen, list(koppen(ws, gekozen).keys()))
        staat["mapping"] = mapping

    catalogus = catalogus_voor_prompt(artikeldata.ruwe_kolommen, artikeldata.vaste_sleutels)
    labels = {c["id"]: f"{c['label']}  [{c['id']}]" for c in catalogus}
    ids_per_label = {v: k for k, v in labels.items()}
    voorbeeld = {}
    kolomindex = koppen(ws, mapping.kopregel_index)
    for rij in ws.iter_rows(min_row=mapping.kopregel_index + 2, max_row=mapping.kopregel_index + 4, values_only=True):
        for naam, i in kolomindex.items():
            if naam not in voorbeeld and i < len(rij) and rij[i] is not None:
                voorbeeld[naam] = str(rij[i])

    st.markdown("**Mapping** — pas aan waar nodig, dan *Invullen*.")
    tabel = pd.DataFrame([{
        "Kolom": k.kolom,
        "Voorbeeld": voorbeeld.get(k.kolom, ""),
        "Doelveld": labels.get(k.doelveld, labels["geen"]),
        "Eenheid": k.eenheid or "",
        "Zekerheid": k.zekerheid,
        "Toelichting": k.toelichting,
    } for k in mapping.kolommen])
    bewerkt = st.data_editor(
        tabel, hide_index=True, use_container_width=True, key=f"mapping_{sleutel}_{ws.title}",
        disabled=["Kolom", "Voorbeeld", "Zekerheid", "Toelichting"],
        column_config={
            "Doelveld": st.column_config.SelectboxColumn(options=list(labels.values()), required=True),
            "Eenheid": st.column_config.SelectboxColumn(options=[o or "" for o in EENHEID_OPTIES]),
        },
    )
    mapping = Mapping(mapping.kopregel_index, [
        KolomMapping(r["Kolom"], ids_per_label[r["Doelveld"]], r["Eenheid"] or None, r["Zekerheid"], r["Toelichting"])
        for _, r in bewerkt.iterrows()
    ], mapping.opmerkingen)

    try:
        res = match_rijen(ws, mapping, artikeldata)
    except ValueError as e:
        st.warning(str(e))
        return
    gevonden = [r for r in res if r.match]
    niet = [r.sleutel for r in res if not r.match]
    st.markdown(f"**{len(gevonden)} van {len(res)} artikelen gevonden.**"
                + (f" Niet gevonden: {', '.join(niet[:10])}{'…' if len(niet) > 10 else ''}" if niet else ""))
    if res and not gevonden:
        st.warning("Geen enkel artikel gevonden. Controleer de sleutelkolom (artikelnummer of EAN).")

    overschrijven = st.checkbox("Ook gevulde cellen overschrijven", value=False)
    if st.button("Invullen", type="primary"):
        uit, rapport = verwerk(inhoud, bestand.name, mapping, artikeldata, ws.title, overschrijven)
        s = rapport.samenvatting()
        st.success(f"Ingevuld: {s['ingevuld']} cellen. Gaten (geel): {s['gaten']}. "
                   f"Zie tabblad 'Controle' in het bestand.")
        naam = bestand.name.rsplit(".", 1)[0] + "_ingevuld.xlsx"
        st.download_button("Download ingevuld bestand", data=uit, file_name=naam,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
```

- [ ] **Step 3: Syntax- en importcontrole**

Run: `./venv/bin/python -m py_compile app.py && ./venv/bin/python -c "import ast,sys; ast.parse(open('app.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Handmatige controle in de browser**

Run (achtergrond): `./venv/bin/streamlit run app.py --server.headless true --server.port 8501`
Controleer met Playwright of handmatig:
1. Keuzeknop zichtbaar; chat werkt nog (voorbeeldvraag klikken geeft antwoord).
2. Dealer-Excel: upload `Primärlieferant_973184.xlsx` → mapping-tabel verschijnt (met API-key: Claude-voorstel; zonder: alles `geen` + info-melding).
3. Doelveld wijzigen in de tabel → matchregel ("27 van 27 artikelen gevonden") verschijnt zodra een sleutel gekozen is.
4. Invullen → downloadknop; gedownload bestand heeft tabblad Controle en gele cellen.
Stop daarna: `pkill -f "streamlit run app.py"`.

- [ ] **Step 5: Draai de tests en commit**

Run: `./venv/bin/pytest -q`
Expected: PASS

```bash
git add app.py
git commit -q -m "Dealer-Excel tabblad in de Streamlit-app

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```

---

### Task 10: README en afronding

**Files:**
- Modify: `README.md`
- Modify: `.gitignore` (regel `skill-observations/` toevoegen — sessielog, hoort niet in de repo)

- [ ] **Step 1: README aanvullen**

Na de sectie "Stap 1b — Excel-artikeloverzicht toevoegen" een sectie toevoegen:

```markdown
### Stap 1c — Artikeldata voor de dealer-Excel invuller

`ingest_artikeldata.py` zet het Product Data Sheet om naar `artikeldata.json`
(gestructureerd, per artikelcode). Draai dit opnieuw bij een nieuwe versie van
het sheet en commit het resultaat:

```bash
python3 ingest_artikeldata.py
```

## Dealer-Excel invullen

Dealers sturen invulbestanden in allerlei indelingen. In de app kies je bovenin
**Dealer-Excel**, uploadt het bestand, controleert de voorgestelde mapping
(welke kolom → welk gegeven, in welke eenheid) en klikt op *Invullen*. Je krijgt
hetzelfde bestand terug met alleen de lege cellen gevuld. Cellen waarvoor geen
data is, zijn geel; het tabblad *Controle* laat per cel de bron en rekenregel zien.

- Artikelen worden gezocht op Repair Care-artikelnummer, daarna EAN, daarna
  omschrijving (die laatste krijgt status "controleer").
- Tweecomponentproducten: gewicht = A + B; afmeting = bussen naast elkaar.
- Gegevens die niet in het sheet staan (land van oorsprong, Bundesland) komen
  uit `vaste_waarden.json`. Vul daar `standaard`, `per_prefix` (bv. `"2": "NLD"`)
  of `per_artikel` in.

Zonder browser:

```bash
python3 dealer_invuller.py dealerbestand.xlsx            # mapping via Claude
python3 dealer_invuller.py dealerbestand.xlsx --mapping mapping.json
```

Tests: `pip install -r requirements-dev.txt && pytest`
```

- [ ] **Step 2: `.gitignore` aanvullen en committen**

```bash
printf '\n# Sessielog van de task-observer skill\nskill-observations/\n' >> .gitignore
./venv/bin/pytest -q
git add README.md .gitignore
git commit -q -m "README: dealer-Excel invuller en artikeldata-ingest

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Jg9tNczyy39LL8Rh3xiB3b"
```
