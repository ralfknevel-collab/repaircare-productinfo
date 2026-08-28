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
