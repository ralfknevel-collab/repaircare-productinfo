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
