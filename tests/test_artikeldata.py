import json
from copy import deepcopy
from datetime import date

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


@pytest.fixture
def prijsbron():
    return {
        "bron": "verkoopadviesprijzen_2026.csv", "geldig_vanaf": "2026-01-01",
        "geldig_tot": "2026-12-31", "valuta": "EUR", "btw": "exclusief",
        "artikelen": {
            "2010005": {"omschrijving": "DRY FIX® UNI", "ean": "8714748004368",
                        "ve_aantal": 10, "eenheid": "st", "adviesprijs_cent": 7656, "bronregel": 19},
            "2040005": {"omschrijving": "Universele Kleurpigmenten", "ean": "8714748005112",
                        "ve_aantal": 4, "eenheid": "set", "adviesprijs_cent": 2299, "bronregel": 17},
            "9001411": {"omschrijving": "Niveau 1 opleiding: op locatie dealer", "ean": None,
                        "ve_aantal": 1, "eenheid": "st", "adviesprijs_cent": 103900, "bronregel": 70},
        }, "meldingen": [],
    }


@pytest.fixture
def datum_in_prijsjaar(monkeypatch):
    class VasteDatum(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 7)

    monkeypatch.setattr("artikeldata.date", VasteDatum, raising=False)


def test_prijslijst_verrijkt_zonder_technische_bron_te_veranderen(artikeldata_dict, prijsbron, datum_in_prijsjaar):
    origineel = deepcopy(artikeldata_dict)
    prijsorigineel = deepcopy(prijsbron)
    ad = Artikeldata(artikeldata_dict, VASTE, prijslijst=prijsbron)
    artikel = ad.zoek(artikelcode="2010005").artikel
    technische_bron = {k: v for k, v in origineel["artikelen"]["2010005"].items() if k != "omschrijving"}
    assert {k: artikel[k] for k in technische_bron} == technische_bron
    assert ad.waarde(artikel, "omschrijving").waarde == "DRY FIX® UNI"
    assert ad.waarde(artikel, "omschrijving").bron == "verkoopadviesprijzen_2026.csv, rij 19"
    assert ad.waarde(artikel, "prijslijst_omschrijving").waarde == "DRY FIX® UNI"
    assert ad.waarde(artikel, "netto_gewicht").waarde == 318
    assert ad.waarde(artikel, "min_verkoophoeveelheid").waarde == 10
    assert artikeldata_dict == origineel and prijsbron == prijsorigineel
    assert not any("omschrijving verschilt" in melding.lower() for melding in ad.bron_meldingen)
    zonder_prijs = ad.zoek(artikelcode="4513032").artikel
    assert ad.waarde(zonder_prijs, "omschrijving").waarde == "EASY Q Modelleerspatel metaal 50 mm"
    assert ad.waarde(zonder_prijs, "omschrijving").bron == "Product Data Sheet"
    assert not artikel.get("bron_conflicten")
    json.dumps(ad.artikelen)
    json.dumps(ad.prijslijst_info)


def test_prijslijst_voegt_artikel_en_opleiding_toe_zonder_maten_te_verzinnen(artikeldata_dict, prijsbron, datum_in_prijsjaar):
    ad = Artikeldata(artikeldata_dict, prijslijst=prijsbron)
    kleur = ad.zoek(artikelcode="2040005").artikel
    assert ad.zoek(ean="8714748005112").artikel is kleur
    assert ad.waarde(kleur, "omschrijving").waarde == "Universele Kleurpigmenten"
    assert "verkoopadviesprijzen_2026.csv" in ad.waarde(kleur, "omschrijving").bron
    assert "rij 17" in ad.waarde(kleur, "ean").bron
    assert ad.waarde(kleur, "ean").waarde == "8714748005112"
    for doel in ("netto_gewicht", "bruto_gewicht", "lengte", "collo_netto_gewicht", "min_verkoophoeveelheid"):
        assert ad.waarde(kleur, doel) is None
    training = ad.zoek(artikelcode="9001411").artikel
    assert training.get("ean") is None
    assert ad.waarde(training, "adviesprijs").waarde == 1039
    assert ad.waarde(training, "ean") is None


def test_adviesprijs_houdt_btw_valuta_eenheid_ve_en_bron_apart(artikeldata_dict, prijsbron, datum_in_prijsjaar):
    ad = Artikeldata(artikeldata_dict, prijslijst=prijsbron)
    artikel = ad.zoek(artikelcode="2040005").artikel
    prijs = ad.waarde(artikel, "adviesprijs")
    assert prijs.waarde == 22.99 and prijs.eenheid == "EUR" and prijs.eenduidig
    assert "verkoopadviesprijzen_2026.csv" in prijs.bron and "rij 17" in prijs.bron
    for stukje in ("EUR", "exclusief btw", "per set", "2026-01-01", "2026-12-31"):
        assert stukje in prijs.regel
    assert ad.waarde(artikel, "adviesprijs_eenheid").waarde == "set"
    assert ad.waarde(artikel, "ve_aantal").waarde == 4
    assert ad.waarde(artikel, "ve_aantal").eenheid is None
    assert "geen doosinhoud" in ad.waarde(artikel, "ve_aantal").regel
    assert ad.waarde(artikel, "dealerinkoopprijs") is None


def test_verschillende_bron_eans_blijven_zichtbaar_en_onbruikbaar_als_prijsmatch(artikeldata_dict, prijsbron, datum_in_prijsjaar):
    artikeldata_dict["artikelen"]["2023999"] = {
        "artikelcode": "2023999", "omschrijving": "DRY FLEX 1", "ean": "8714748002616", "netto_g": 340,
    }
    prijsbron["artikelen"]["2023999"] = {
        "omschrijving": "DRY FLEX® 1", "ean": "8714748004740", "ve_aantal": 20,
        "eenheid": "st", "adviesprijs_cent": 7458, "bronregel": 6,
    }
    ad = Artikeldata(artikeldata_dict, prijslijst=prijsbron)
    artikel = ad.zoek(artikelcode="2023999").artikel
    assert artikel["ean"] == "8714748002616"
    assert artikel["prijslijst"]["ean"] == "8714748004740"
    assert ad.zoek(ean="8714748004740") is None
    assert ad.zoek(ean="8714748002616").artikel is artikel
    assert all(tekst in " ".join(artikel["bron_conflicten"]) for tekst in ("2023999", "8714748002616", "8714748004740"))
    prijs = ad.waarde(artikel, "adviesprijs")
    assert prijs.waarde is None and not prijs.eenduidig and "EAN" in prijs.onzeker_reden
    assert any("2023999" in melding and "EAN" in melding for melding in ad.bron_meldingen)


def test_nieuwe_code_met_ean_van_andere_pds_code_markeert_beide(artikeldata_dict, prijsbron, datum_in_prijsjaar):
    prijsbron["artikelen"]["2040005"]["ean"] = "8714748004368"
    del prijsbron["artikelen"]["2010005"]
    ad = Artikeldata(artikeldata_dict, prijslijst=prijsbron)
    bestaand = ad.zoek(artikelcode="2010005").artikel
    nieuw = ad.zoek(artikelcode="2040005").artikel
    assert bestaand["bron_conflicten"] and nieuw["bron_conflicten"]
    assert ad.zoek(ean="8714748004368").artikel is bestaand
    assert ad.waarde(nieuw, "adviesprijs").waarde is None
    assert bestaand["omschrijving"] == "DRY FIX UNI"


@pytest.mark.parametrize("vandaag,verwacht", [
    ((2025, 12, 31), None), ((2026, 1, 1), 22.99), ((2026, 12, 31), 22.99), ((2027, 1, 1), None),
])
def test_prijzen_worden_alleen_binnen_geldigheidsperiode_ingevuld(artikeldata_dict, prijsbron, monkeypatch, vandaag, verwacht):
    class VasteDatum(date):
        @classmethod
        def today(cls):
            return cls(*vandaag)

    monkeypatch.setattr("artikeldata.date", VasteDatum, raising=False)
    ad = Artikeldata(artikeldata_dict, prijslijst=prijsbron)
    artikel = ad.zoek(artikelcode="2040005").artikel
    waarde = ad.waarde(artikel, "adviesprijs")
    assert waarde.waarde == verwacht
    assert waarde.eenduidig == (verwacht is not None)
    assert ad.waarde(artikel, "omschrijving").waarde == "Universele Kleurpigmenten"
    assert ad.waarde(artikel, "ve_aantal").waarde == 4
    if verwacht is None:
        assert waarde.onzeker_reden and ad.bron_meldingen


def test_explicitiete_json_zonder_prijsbron_blijft_geisoleerd(tmp_path, artikeldata_dict, monkeypatch):
    pad = tmp_path / "artikelen.json"
    pad.write_text(json.dumps(artikeldata_dict), encoding="utf-8")
    monkeypatch.setattr("artikeldata.PRIJSLIJST_FILE", tmp_path / "ontbreekt.csv", raising=False)
    ad = Artikeldata.laad(pad_json=pad)
    assert ad.zoek(artikelcode="2040005") is None
    assert ad.prijslijst_info == {} and ad.bron_meldingen == []


@pytest.mark.parametrize("inhoud", [None, "dit is geen prijslijst\n"])
def test_onbruikbare_prijsbron_meldt_fout_en_behoudt_pds(tmp_path, artikeldata_dict, inhoud):
    pad = tmp_path / "artikelen.json"
    pad.write_text(json.dumps(artikeldata_dict), encoding="utf-8")
    prijs = tmp_path / "prijslijst.csv"
    if inhoud is not None:
        prijs.write_text(inhoud, encoding="utf-8")
    ad = Artikeldata.laad(pad_json=pad, pad_prijslijst=prijs)
    assert ad.zoek(artikelcode="2010005") is not None
    assert ad.prijslijst_info == {}
    assert any("prijslijst.csv" in melding for melding in ad.bron_meldingen)


def test_default_laad_koppelt_prijslijst_maar_schrijft_geen_bronnen(tmp_path, artikeldata_dict, monkeypatch, datum_in_prijsjaar):
    pad = tmp_path / "artikelen.json"
    tekst = json.dumps(artikeldata_dict)
    pad.write_text(tekst, encoding="utf-8")
    prijs = tmp_path / "prijslijst.csv"
    csv = (
        "Verkoopadviesprijzen per 01-01-2026,,,,,\n"
        "Artikel,Omschrijving,EAN code,VE,Eenheid,VK/St €\n"
        "2040005,Universele Kleurpigmenten,87.14748.00511.2,4,set,€ 22.99\n"
        "Condities,,,,,\n"
        "Prijzen,\"In euro's excl. BTW, per stuk resp. per set\",,,,\n"
        "Geldigheid,\"voor leveringen tussen 01-01-2026 en 31-12-2026, tot nader order\",,,,\n"
    )
    prijs.write_text(csv, encoding="utf-8")
    monkeypatch.setattr("artikeldata.ARTIKELDATA_FILE", pad)
    monkeypatch.setattr("artikeldata.PRIJSLIJST_FILE", prijs, raising=False)
    ad = Artikeldata.laad()
    artikel = ad.zoek(artikelcode="2040005").artikel
    assert ad.waarde(artikel, "adviesprijs").waarde == 22.99
    assert ad.prijslijst_info["bron"] == "prijslijst.csv"
    assert pad.read_text(encoding="utf-8") == tekst and prijs.read_text(encoding="utf-8") == csv


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
    assert w.waarde.waarden == (("A", 48), ("B", 41)) and w.eenheid == "mm"
    assert ad.waarde(a, "breedte").waarde.waarden == (("A", 48), ("B", 41))
    assert ad.waarde(a, "hoogte").waarde.waarden == (("A", 184), ("B", 145))
    assert ad.waarde(a, "collo_lengte").waarde == 180
    assert ad.waarde(a, "ean").waarde == "8714748004368"
    assert ad.waarde(a, "omschrijving").waarde == "DRY FIX UNI"
    assert ad.waarde(a, "min_verkoophoeveelheid").waarde == 10


@pytest.mark.parametrize("doel, verwacht", [
    ("lengte", (("A", 48), ("B", 41))),
    ("breedte", (("A", 48), ("B", 41))),
    ("hoogte", (("A", 184), ("B", 145))),
])
def test_componentmaten_vervangen_berekende_setopstelling(ad, doel, verwacht):
    artikel = ad.zoek(artikelcode="2010005").artikel
    # De naam bepaalt de volgorde, niet de plaats in de bronlijst.
    artikel["componenten"].reverse()
    waarde = ad.waarde(artikel, doel)
    assert waarde.waarde.waarden == verwacht
    assert waarde.eenduidig and waarde.onzeker_reden is None
    assert "componenten A en B" in waarde.bron
    assert "geen totale setmaat" in waarde.regel
    assert "naast elkaar" not in waarde.regel
    # De doosmaat en het gesommeerde nettogewicht hebben een eigen bronbetekenis.
    assert ad.waarde(artikel, "collo_lengte").eenduidig
    assert ad.waarde(artikel, "netto_gewicht").eenduidig


@pytest.mark.parametrize("componenten", [
    [],
    [{"naam": "A", "maat_mm": {"l": 48}}],
    [{"naam": "A", "maat_mm": {"l": 48}}, {"naam": "B", "maat_mm": {"h": 145}}],
    [{"naam": "A", "maat_mm": {"l": 48}}, {"maat_mm": {"l": 41}}],
    [{"naam": "A", "maat_mm": {"l": 48}}, {"naam": "A", "maat_mm": {"l": 41}}],
    [{"naam": "A", "maat_mm": {"l": 48}}, {"naam": "B", "maat_mm": {"l": None}}],
    [{"naam": "A", "maat_mm": {"l": 48}}, {"naam": "B", "maat_mm": {"l": float("nan")}}],
    [{"naam": "A", "maat_mm": {"l": 48}}, {"naam": "B", "maat_mm": {"l": True}}],
    [{"naam": "A", "maat_mm": {"l": 48}}, {"naam": "B", "maat_mm": {"l": -41}}],
])
def test_onvolledige_componentbron_wordt_nooit_een_opgetelde_maat(ad, componenten):
    artikel = ad.zoek(artikelcode="2010005").artikel
    artikel["componenten"] = componenten
    waarde = ad.waarde(artikel, "lengte")
    assert waarde.waarde is None
    assert not waarde.eenduidig and "component" in waarde.onzeker_reden.lower()


def test_componentmaten_zijn_onafhankelijk_per_as(ad):
    artikel = ad.zoek(artikelcode="2010005").artikel
    del artikel["componenten"][1]["maat_mm"]["h"]
    assert ad.waarde(artikel, "lengte").waarde.waarden == (("A", 48), ("B", 41))
    assert ad.waarde(artikel, "hoogte").waarde is None


def test_gelijke_componentmaten_behouden_beide_bronnamen(ad):
    artikel = ad.zoek(artikelcode="2010005").artikel
    artikel["componenten"][1]["maat_mm"]["l"] = 48
    assert ad.waarde(artikel, "lengte").waarde.waarden == (("A", 48), ("B", 48))


def test_directe_2_in_1_maat_heeft_voorrang_op_componenten(ad):
    artikel = ad.zoek(artikelcode="2010005").artikel
    artikel["maat_mm"] = {"vorm": "blok", "l": 50, "b": 50, "h": 240}
    assert [ad.waarde(artikel, doel).waarde for doel in ("lengte", "breedte", "hoogte")] == [50, 50, 240]


@pytest.mark.parametrize("code,verwacht", [("2511105", (49, 49, 230)), ("4513032", (25, 50, 222))])
def test_rechtstreekse_productmaten_blijven_bruikbaar(ad, code, verwacht):
    artikel = ad.zoek(artikelcode=code).artikel
    waarden = [ad.waarde(artikel, doel) for doel in ("lengte", "breedte", "hoogte")]
    assert tuple(w.waarde for w in waarden) == verwacht
    assert all(w.eenduidig and w.eenheid == "mm" for w in waarden)


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


def test_waarde_componentveld_meldt_afwijkend_component(ad):
    a = ad.zoek(artikelcode="2010005").artikel
    w = ad.waarde(a, "un_code")
    assert w.regel == "ook B: 2735"
    assert w.bron == "Product Data Sheet, component A (B wijkt af)"
    assert ad.waarde(a, "klasse").regel == "ook B: 8"
    # Vlampunt is gelijk in A en B: geen melding.
    assert ad.waarde(a, "vlampunt").regel is None
    # GHS staat als unie op artikelniveau: geen componentmelding.
    assert ad.waarde(a, "ghs").regel is None


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


def test_componentverschil_is_gestructureerd_onzeker(ad):
    artikel = ad.zoek(artikelcode="2010005").artikel
    assert ad.waarde(artikel, "un_code").eenduidig is False
    assert ad.waarde(artikel, "vlampunt").eenduidig is True
    assert ad.waarde(artikel, "ghs").eenduidig is True
    assert ad.waarde(artikel, "netto_gewicht").eenduidig is True


@pytest.fixture
def doosartikel():
    return {
        "artikelcode": "2023205", "netto_g": 172, "bruto_g": 269.5,
        "min_verkoophoeveelheid": 10,
        "ruw": {"Netto gewicht per doos (kg)": "A: 1,11",
                "Bruto gewicht per doos (kg)": "2.87", "Inhoud (om)doos": "1 x 10"},
        "componenten": [
            {"naam": "A", "netto_g": 111, "ruw": {}},
            {"naam": "B", "netto_g": 61, "ruw": {"Netto gewicht per doos (kg)": "B: 0,61"}},
        ],
    }


def test_doosgewichten_tellen_componenten_eenmaal_en_rekenen_kg_om(ad, doosartikel):
    doosartikel["componenten"].reverse()
    netto = ad.waarde(doosartikel, "collo_netto_gewicht")
    bruto = ad.waarde(doosartikel, "collo_bruto_gewicht")
    assert netto is not None and bruto is not None
    assert netto.waarde == 1720 and netto.eenheid == "g" and netto.eenduidig
    assert "1.11" in netto.regel and "0.61" in netto.regel and "kg" in netto.regel
    assert "Netto gewicht per doos (kg)" in netto.bron
    assert bruto.waarde == 2870 and bruto.eenheid == "g" and bruto.eenduidig
    assert ad.waarde(doosartikel, "netto_gewicht").waarde == 172
    assert ad.waarde(doosartikel, "ruw:Netto gewicht per doos (kg)").waarde == "A: 1,11"


@pytest.mark.parametrize("invoer, verwacht", [("1,72", 1720), ("1.72", 1720), (1.72, 1720), (2, 2000)])
def test_direct_doosgewicht_is_al_totaal(ad, doosartikel, invoer, verwacht):
    doosartikel["ruw"]["Netto gewicht per doos (kg)"] = invoer
    waarde = ad.waarde(doosartikel, "collo_netto_gewicht")
    assert waarde is not None and waarde.waarde == verwacht and waarde.eenduidig


def test_herhaalde_bron_zelfde_component_telt_niet_dubbel(ad, doosartikel):
    doosartikel["componenten"][0]["ruw"]["Netto gewicht per doos (kg)"] = "A: 1,11"
    assert ad.waarde(doosartikel, "collo_netto_gewicht").waarde == 1720


def test_gelijke_componentgewichten_worden_wel_beide_opgeteld(ad, doosartikel):
    doosartikel["componenten"][1]["ruw"]["Netto gewicht per doos (kg)"] = "B: 1,11"
    assert ad.waarde(doosartikel, "collo_netto_gewicht").waarde == 2220


@pytest.mark.parametrize("ongeldig", ["1.72 kg", "ca. 1,72", "1,2,3", "1,234.56", "NaN", float("nan"),
                                        float("inf"), True, -1.72, "-1,72", 0, "A: -1,11", "A: 1,11 / B: 0,61"])
def test_ongeldig_doosgewicht_geeft_geen_schijnzeker_getal(ad, doosartikel, ongeldig):
    doosartikel["ruw"]["Netto gewicht per doos (kg)"] = ongeldig
    waarde = ad.waarde(doosartikel, "collo_netto_gewicht")
    assert waarde is not None and waarde.waarde is None and not waarde.eenduidig
    assert waarde.onzeker_reden


@pytest.mark.parametrize("b_waarde", [None, "", "--", "A: 0,61", "C: 0,61", "B: fout"])
def test_onvolledige_of_verkeerd_gelabelde_componentdoosbron_blijft_onzeker(ad, doosartikel, b_waarde):
    doosartikel["componenten"][1]["ruw"]["Netto gewicht per doos (kg)"] = b_waarde
    waarde = ad.waarde(doosartikel, "collo_netto_gewicht")
    assert waarde is not None and waarde.waarde is None and not waarde.eenduidig


def test_tegenstrijdige_componentdoosbron_blijft_onzeker(ad, doosartikel):
    doosartikel["componenten"][0]["ruw"]["Netto gewicht per doos (kg)"] = "A: 1,12"
    waarde = ad.waarde(doosartikel, "collo_netto_gewicht")
    assert waarde is not None and waarde.waarde is None and not waarde.eenduidig


@pytest.mark.parametrize("namen", [("A", "A"), ("A", None), ("A", "C")])
def test_componentdoosgewicht_vereist_unieke_betrouwbare_componentnamen(ad, doosartikel, namen):
    for component, naam in zip(doosartikel["componenten"], namen):
        component["naam"] = naam
    waarde = ad.waarde(doosartikel, "collo_netto_gewicht")
    assert waarde is not None and waarde.waarde is None and not waarde.eenduidig


def test_bruto_componentdoosgewichten_kunnen_ook_worden_opgeteld(ad, doosartikel):
    doosartikel["ruw"]["Bruto gewicht per doos (kg)"] = "A: 2,0"
    doosartikel["componenten"][1]["ruw"]["Bruto gewicht per doos (kg)"] = "B: 0.87"
    waarde = ad.waarde(doosartikel, "collo_bruto_gewicht")
    assert waarde is not None and waarde.waarde == 2870 and waarde.eenduidig


def test_netto_doosgewicht_kan_uit_twee_gelabelde_componentbronnen_zonder_artikelbron(ad, doosartikel):
    doosartikel["ruw"].pop("Netto gewicht per doos (kg)")
    doosartikel["componenten"][0]["ruw"]["Netto gewicht per doos (kg)"] = "A: 1,11"
    assert ad.waarde(doosartikel, "collo_netto_gewicht").waarde == 1720


@pytest.mark.parametrize("invoer, verwacht", [("1 x 10", 10), ("4 x 10", 10), (" 30x1 ", 1),
                                             ("1 x 24", 24), (None, None), ("--", None),
                                             ("10", None), ("0 x 10", None), ("1 x 0", None),
                                             ("1 x 10 stuks", None), (True, None)])
def test_doosinhoud_komt_uit_verpakkingsbron_niet_minimale_afname(invoer, verwacht):
    import artikeldata
    assert hasattr(artikeldata, "doosinhoud")
    assert artikeldata.doosinhoud({"ruw": {"Inhoud (om)doos": invoer}, "min_verkoophoeveelheid": 999}) == verwacht


def test_ontbrekend_netto_doosgewicht_mag_uit_volledig_stukgewicht_en_doosinhoud(ad, doosartikel):
    doosartikel["ruw"].pop("Netto gewicht per doos (kg)")
    doosartikel["componenten"][1]["ruw"].clear()
    doosartikel["ruw"]["Inhoud (om)doos"] = "4 x 10"
    doosartikel["min_verkoophoeveelheid"] = 999
    waarde = ad.waarde(doosartikel, "collo_netto_gewicht")
    assert waarde is not None and waarde.waarde == 1720 and waarde.eenduidig
    assert "172" in waarde.regel and "10" in waarde.regel and "afgeleid" in waarde.regel.lower()


def test_bruto_doosgewicht_wordt_nooit_uit_stukgewicht_geschat(ad, doosartikel):
    doosartikel["ruw"].pop("Bruto gewicht per doos (kg)")
    assert ad.waarde(doosartikel, "collo_bruto_gewicht") is None


def test_netto_doosgewicht_single_product_afgeleid_uit_doosinhoud(ad):
    artikel = {"netto_g": 120, "ruw": {"Inhoud (om)doos": "1 x 10"}}
    waarde = ad.waarde(artikel, "collo_netto_gewicht")
    assert waarde is not None and waarde.waarde == 1200 and waarde.eenduidig


@pytest.mark.parametrize("wijziging", ["doosinhoud", "component", "stukgewicht", "negatief", "verschil"])
def test_netto_afleiding_eist_eenduidige_stukgewichten_en_doosinhoud(ad, doosartikel, wijziging):
    doosartikel["ruw"].pop("Netto gewicht per doos (kg)")
    doosartikel["componenten"][1]["ruw"].clear()
    if wijziging == "doosinhoud":
        doosartikel["ruw"].pop("Inhoud (om)doos")
    elif wijziging == "component":
        doosartikel["componenten"][1].pop("netto_g")
    elif wijziging == "stukgewicht":
        doosartikel["netto_g"] = float("nan")
    elif wijziging == "negatief":
        doosartikel["componenten"][1]["netto_g"] = -61
    else:
        doosartikel["netto_g"] = 111
    waarde = ad.waarde(doosartikel, "collo_netto_gewicht")
    assert waarde is None or (waarde.waarde is None and not waarde.eenduidig)
