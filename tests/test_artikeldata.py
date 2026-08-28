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
