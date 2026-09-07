"""De adviesprijslijst lezen zonder prijzen of artikelidentiteiten te raden."""

from __future__ import annotations

import csv
import io
import json

import pytest

from prijslijst import lees_prijslijst


def _bestand(tmp_path, artikelen=None, *, encoding="utf-8", titel=None,
             prijzen=None, geldigheid=None, extra=None):
    regels = [
        [""],
        [titel or "Verkoopadviesprijzen per 01-01-2026"],
        [""],
        ["Artikel", "Omschrijving", "EAN code", "VE", "Eenheid", " VK/St € ", "", ""],
        ["DRY FLEX®"],
    ]
    regels.extend(artikelen if artikelen is not None else [
        ["2023005", "DRY FLEX® 1", "87.14748.00474.0", "20", "st", "€ 74.58"],
        ["2040005", "Universele Kleurpigmenten™", "8714748005112", "4", "set", "€ 22.99"],
    ])
    regels.extend([
        ["Condities"],
        ["Prijzen", prijzen or "In euro's excl. BTW, per stuk resp. per set"],
        ["Geldigheid", geldigheid or "voor leveringen tussen 01-01-2026 en 31-12-2026, tot nader order\n"],
    ])
    regels.extend(extra or [])
    inhoud = io.StringIO(newline="")
    csv.writer(inhoud).writerows(regels)
    pad = tmp_path / "adviesprijzen.csv"
    pad.write_bytes(inhoud.getvalue().encode(encoding))
    return pad


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1252"])
def test_leest_bron_prijsbasis_datums_en_unicode(tmp_path, encoding):
    gegevens = lees_prijslijst(_bestand(tmp_path, encoding=encoding))

    assert gegevens["bron"] == "adviesprijzen.csv"
    assert gegevens["geldig_vanaf"] == "2026-01-01"
    assert gegevens["geldig_tot"] == "2026-12-31"
    assert gegevens["valuta"] == "EUR"
    assert gegevens["btw"] == "exclusief"
    assert gegevens["artikelen"]["2023005"] == {
        "omschrijving": "DRY FLEX® 1", "ean": "8714748004740",
        "ve_aantal": 20, "eenheid": "st", "adviesprijs_cent": 7458,
        "bronregel": 6,
    }
    assert gegevens["artikelen"]["2040005"]["omschrijving"] == "Universele Kleurpigmenten™"
    assert gegevens["artikelen"]["2040005"]["eenheid"] == "set"
    assert gegevens["meldingen"] == []
    json.dumps(gegevens, allow_nan=False)


def test_opleiding_neemt_echte_prijskolom_en_geen_getal_uit_ean_opmerking(tmp_path):
    pad = _bestand(tmp_path, [[
        "9001411", "Niveau 1 opleiding: op locatie dealer",
        "doorberekenen aan deelnemer € 199,00", "1", "st", "€ 1,039.00",
    ]])
    gegevens = lees_prijslijst(pad)

    assert gegevens["artikelen"]["9001411"]["adviesprijs_cent"] == 103900
    assert gegevens["artikelen"]["9001411"]["ean"] is None
    assert any("9001411" in melding and "EAN" in melding for melding in gegevens["meldingen"])


def test_ontbrekende_ean_behoudt_gecontroleerde_code_en_prijs(tmp_path):
    gegevens = lees_prijslijst(_bestand(tmp_path, [[
        "2040005", "Universele Kleurpigmenten", "", "4", "set", "€ 22.99",
    ]]))

    assert gegevens["artikelen"]["2040005"]["ean"] is None
    assert gegevens["artikelen"]["2040005"]["adviesprijs_cent"] == 2299
    assert any("EAN" in melding for melding in gegevens["meldingen"])


@pytest.mark.parametrize("prijs,centen", [("€ 0.00", 0), ("€ 0.29", 29), ("€ 10.01", 1001)])
def test_centbedragen_blijven_exact(tmp_path, prijs, centen):
    gegevens = lees_prijslijst(_bestand(tmp_path, [[
        "2040005", "Universele Kleurpigmenten", "8714748005112", "4", "set", prijs,
    ]]))

    assert gegevens["artikelen"]["2040005"]["adviesprijs_cent"] == centen


@pytest.mark.parametrize("prijs", [
    "€ -1.00", "€ NaN", "€ Infinity", "€ 1,03", "€ 10,39.00", "€ 74.580",
    "74.58", "=74.58", "€ 7e2", "€ 74.58 incl. BTW", "",
])
def test_ongeldige_of_dubbelzinnige_prijs_wordt_niet_gebruikt(tmp_path, prijs):
    pad = _bestand(tmp_path, [["2023005", "DRY FLEX", "8714748004740", "20", "st", prijs]])
    gegevens = lees_prijslijst(pad)

    assert gegevens["artikelen"] == {}
    assert any("2023005" in melding for melding in gegevens["meldingen"])


@pytest.mark.parametrize("kolom,waarde", [
    (2, "8714748004741"), (2, "871474800474"), (2, "EAN 8714748004740"),
    (2, "=8714748004740"), (3, "0"), (3, "2.5"), (3, "-1"),
    (4, "doos"), (4, ""), (1, "=HYPERLINK(\"https://example.invalid\")"),
])
def test_ongeldige_identiteit_ve_eenheid_of_formule_slaat_artikel_over(tmp_path, kolom, waarde):
    rij = ["2023005", "DRY FLEX", "8714748004740", "20", "st", "€ 74.58"]
    rij[kolom] = waarde
    gegevens = lees_prijslijst(_bestand(tmp_path, [rij]))

    assert gegevens["artikelen"] == {}
    assert gegevens["meldingen"]


@pytest.mark.parametrize("rij2", [
    ["2023005", "Ander artikel", "8714748005112", "4", "set", "€ 22.99"],
    ["2023005", "Zelfde artikel", "8714748004740", "20", "st", "€ 74.58"],
    ["2040005", "Ander artikel", "8714748004740", "4", "set", "€ 22.99"],
    ["2023005", "Foutieve dubbele regel", "8714748005112", "4", "set", "€ NaN"],
    ["2040005", "Foutieve prijs maar gedeelde EAN", "8714748004740", "4", "set", "€ NaN"],
])
def test_dubbele_artikelcode_of_gedeelde_ean_geeft_geen_winnaar(tmp_path, rij2):
    rij1 = ["2023005", "DRY FLEX", "8714748004740", "20", "st", "€ 74.58"]
    gegevens = lees_prijslijst(_bestand(tmp_path, [rij1, rij2]))

    assert gegevens["artikelen"] == {}
    assert any("dubbel" in melding.lower() or "meerdere" in melding.lower()
               for melding in gegevens["meldingen"])


@pytest.mark.parametrize("wijziging", [
    {"titel": "Verkoopadviesprijzen per 01-01-2025"},
    {"titel": "Prijslijst 2026"},
    {"prijzen": "In euro's incl. BTW, per stuk resp. per set"},
    {"prijzen": "In dollars excl. BTW, per stuk resp. per set"},
    {"prijzen": "In euro's excl. BTW, per doos"},
    {"geldigheid": "voor leveringen tussen 31-02-2026 en 31-12-2026, tot nader order"},
    {"geldigheid": "voor leveringen tussen 01-01-2026 en 31-12-2025, tot nader order"},
    {"geldigheid": "in 2026"},
    {"extra": [["Prijzen", "In euro's excl. BTW, per stuk resp. per set"]]},
    {"extra": [["Geldigheid", "voor leveringen tussen 01-01-2027 en 31-12-2027, tot nader order"]]},
])
def test_onzekere_prijsmetadata_stopt_hele_import(tmp_path, wijziging):
    with pytest.raises(ValueError):
        lees_prijslijst(_bestand(tmp_path, **wijziging))


def test_ontbrekende_kop_of_footer_stopt_import(tmp_path):
    pad = tmp_path / "onvolledig.csv"
    pad.write_text("Artikel,Omschrijving,EAN code,VE,Eenheid, VK/St €\n", encoding="utf-8")

    with pytest.raises(ValueError):
        lees_prijslijst(pad)


def test_parser_bewaart_verlopen_periode_zonder_zelf_prijzen_toe_te_staan(tmp_path):
    gegevens = lees_prijslijst(_bestand(
        tmp_path, titel="Verkoopadviesprijzen per 01-01-2025",
        geldigheid="voor leveringen tussen 01-01-2025 en 31-12-2025, tot nader order",
    ))

    assert gegevens["geldig_vanaf"] == "2025-01-01"
    assert gegevens["geldig_tot"] == "2025-12-31"
    assert len(gegevens["artikelen"]) == 2


def test_leesfout_wordt_niet_als_lege_prijslijst_verstopt(tmp_path):
    with pytest.raises(OSError):
        lees_prijslijst(tmp_path / "bestaat-niet.csv")
