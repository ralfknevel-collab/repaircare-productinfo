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


from pathlib import Path

import openpyxl

from ingest_artikeldata import bouw_artikeldata, lees_artikelen

ECHT_SHEET = Path(__file__).resolve().parent.parent / "Product Data Sheet december 2024.xlsx"


def test_lees_artikelen_fixture(artikeldata_dict):
    art = artikeldata_dict["artikelen"]
    assert set(art) == {"2010005", "2511105", "4513032", "4570042", "4511003"}
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

    pistool = art["4511003"]
    assert pistool["componenten"] == []
    assert pistool["inhoud"] == "1 stuk"
    assert pistool["netto_g"] == 935 and "netto_regel" not in pistool
    assert pistool["maat_mm"] == {"vorm": "blok", "l": 350, "b": 60, "h": 180}


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
    assert {c["naam"] for a in art.values() for c in a["componenten"]} <= {"A", "B"}
    assert art["4511003"]["componenten"] == []
