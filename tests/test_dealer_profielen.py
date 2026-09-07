"""Gebruikerskeuzes blijven lokaal bewaard en komen alleen bij hetzelfde formaat terug."""

import importlib
import json

import openpyxl
import pytest


def _profielen(tmp_path, monkeypatch):
    module = importlib.import_module("dealer_profielen")
    monkeypatch.setattr(module, "PROFIEL_MAP", tmp_path / "profielen")
    return module


def _werkblad(koppen=None, rijen=None, titel="Artikelen"):
    ws = openpyxl.Workbook().active
    ws.title = titel
    ws.append(koppen or ["HerstellerArtNr", "Primärlieferant", "Länge", "Nettogewicht"])
    for rij in rijen if rijen is not None else [["2010005", 973184, None, None]]:
        ws.append(rij)
    return ws


def test_bewaarde_keuzes_worden_bij_een_nieuwe_lezing_teruggelezen(tmp_path, monkeypatch):
    profielen = _profielen(tmp_path, monkeypatch)
    sleutel = profielen.profielsleutel(_werkblad(), 0, "dealer.xlsx")

    assert profielen.laad_profiel(sleutel) is None
    profielen.bewaar_profiel(sleutel, "mm", "g")
    assert profielen.laad_profiel(sleutel) == {"maat_eenheid": "mm", "gewicht_eenheid": "g"}
    assert json.loads((profielen.PROFIEL_MAP / f"{sleutel}.json").read_text()) == {
        "maat_eenheid": "mm", "gewicht_eenheid": "g",
    }


def test_nieuwe_productrijen_en_bestandsnaam_gebruiken_dezelfde_supplierkeuze(tmp_path, monkeypatch):
    profielen = _profielen(tmp_path, monkeypatch)
    sleutel = profielen.profielsleutel(_werkblad(), 0, "origineel.xlsx")
    profielen.bewaar_profiel(sleutel, "cm", "kg")
    gewijzigd = _werkblad(rijen=[["ander artikel", "973184", 5, 2], ["nieuw", 973184, 7, 3]])

    nieuwe_sleutel = profielen.profielsleutel(gewijzigd, 0, "nieuwe artikelen.csv")

    assert profielen.laad_profiel(nieuwe_sleutel) == {"maat_eenheid": "cm", "gewicht_eenheid": "kg"}


@pytest.mark.parametrize("leveranciers", [["andere leverancier"], [973184, "andere leverancier"], []])
def test_andere_of_ontbrekende_supplierwaarden_nemen_geen_keuze_over(tmp_path, monkeypatch, leveranciers):
    profielen = _profielen(tmp_path, monkeypatch)
    sleutel = profielen.profielsleutel(_werkblad(), 0, "dealer.xlsx")
    profielen.bewaar_profiel(sleutel, "mm", "g")
    ander = _werkblad(rijen=[["product", leverancier, None, None] for leverancier in leveranciers])

    assert profielen.laad_profiel(profielen.profielsleutel(ander, 0, "dealer.xlsx")) is None


def test_meerdere_leveranciers_gebruiken_de_hele_set_onafhankelijk_van_rijvolgorde(tmp_path, monkeypatch):
    profielen = _profielen(tmp_path, monkeypatch)
    eerste = _werkblad(rijen=[["a", 973184], ["b", 123456], ["c", 973184], ["d", None]])
    zelfde = _werkblad(rijen=[["x", 123456], ["y", 973184]])
    andere = _werkblad(rijen=[["x", 123456], ["y", 654321]])
    sleutel = profielen.profielsleutel(eerste, 0, "eerste.xlsx")
    profielen.bewaar_profiel(sleutel, "mm", "g")

    assert profielen.laad_profiel(profielen.profielsleutel(zelfde, 0, "andere-naam.xlsx")) is not None
    assert profielen.laad_profiel(profielen.profielsleutel(andere, 0, "eerste.xlsx")) is None


@pytest.mark.parametrize("koppen,titel", [
    (["HerstellerArtNr", "Primärlieferant", "Nettogewicht", "Länge"], "Artikelen"),
    (["HerstellerArtNr", "Primärlieferant", "Länge (mm)", "Nettogewicht"], "Artikelen"),
    (["HerstellerArtNr", "Primärlieferant", None, "Länge", "Nettogewicht"], "Artikelen"),
    (["HerstellerArtNr", "Primärlieferant", "Länge", "Nettogewicht"], "Andere artikelen"),
])
def test_afwijkende_koppen_volgorde_of_tabblad_nemen_geen_keuze_over(tmp_path, monkeypatch, koppen, titel):
    profielen = _profielen(tmp_path, monkeypatch)
    sleutel = profielen.profielsleutel(_werkblad(), 0, "dealer.xlsx")
    profielen.bewaar_profiel(sleutel, "mm", "g")

    assert profielen.laad_profiel(profielen.profielsleutel(_werkblad(koppen=koppen, titel=titel), 0, "dealer.xlsx")) is None


def test_unicode_en_witruimte_in_koppen_veranderen_het_profiel_niet(tmp_path, monkeypatch):
    profielen = _profielen(tmp_path, monkeypatch)
    sleutel = profielen.profielsleutel(_werkblad(), 0, "dealer.xlsx")
    genormaliseerd = _werkblad(koppen=["  HerstellerArtNr ", "Prima\u0308rlieferant", "LÄNGE", "Nettogewicht\n"])

    assert profielen.profielsleutel(genormaliseerd, 0, "dealer.xlsx") == sleutel


def test_kopregel_op_andere_rij_wordt_juist_gelezen(tmp_path, monkeypatch):
    profielen = _profielen(tmp_path, monkeypatch)
    normaal = _werkblad()
    voorloop = _werkblad()
    voorloop.insert_rows(1)
    voorloop.cell(1, 1, "Invullen a.u.b.")

    assert profielen.profielsleutel(voorloop, 1, "dealer.xlsx") == profielen.profielsleutel(normaal, 0, "dealer.xlsx")


@pytest.mark.parametrize("naam", ["Dealer.xlsx", "Dealer_ingevuld.xlsx", "Dealer_ingevuld-2.xlsx", "Dealer_ingevuld-2_controle.xlsx"])
def test_zonder_supplierkolom_herkent_bestandsstam_alleen_uitvoersuffixen(tmp_path, monkeypatch, naam):
    profielen = _profielen(tmp_path, monkeypatch)
    ws = _werkblad(koppen=["Artikelcode", "Lengte", "Netto gewicht"], rijen=[["a", None, None]])
    sleutel = profielen.profielsleutel(ws, 0, "/map/Dealer.xlsx")
    profielen.bewaar_profiel(sleutel, "m", None)

    assert profielen.laad_profiel(profielen.profielsleutel(ws, 0, naam)) == {"maat_eenheid": "m", "gewicht_eenheid": None}


@pytest.mark.parametrize("naam", ["Andere dealer.xlsx", "dealer.xlsx", "Dealer_2026.xlsx", "Dealer origineel.xlsx", "Dealer-2.xlsx", "Dealer-2_ingevuld.xlsx"])
def test_zonder_supplierkolom_deelt_andere_exacte_stam_geen_profiel(tmp_path, monkeypatch, naam):
    profielen = _profielen(tmp_path, monkeypatch)
    ws = _werkblad(koppen=["Artikelcode", "Lengte", "Netto gewicht"], rijen=[["a", None, None]])
    sleutel = profielen.profielsleutel(ws, 0, "Dealer.xlsx")
    profielen.bewaar_profiel(sleutel, "mm", "g")

    assert profielen.laad_profiel(profielen.profielsleutel(ws, 0, naam)) is None


def test_lege_supplierkolom_deelt_keuzes_alleen_bij_dezelfde_bestandsstam(tmp_path, monkeypatch):
    profielen = _profielen(tmp_path, monkeypatch)
    ws = _werkblad(rijen=[["a", None, None, None]])
    sleutel = profielen.profielsleutel(ws, 0, "Dealer.xlsx")
    profielen.bewaar_profiel(sleutel, "mm", "g")

    assert profielen.laad_profiel(profielen.profielsleutel(ws, 0, "Andere dealer.xlsx")) is None
    assert profielen.laad_profiel(profielen.profielsleutel(ws, 0, "Dealer_ingevuld-2.xlsx")) == {
        "maat_eenheid": "mm", "gewicht_eenheid": "g",
    }


@pytest.mark.parametrize("maat,gewicht", [(None, None), ("mm", "g"), ("cm", "kg"), ("m", None), (None, "kg")])
def test_alleen_ondersteunde_keuzes_worden_ongewijzigd_bewaard(tmp_path, monkeypatch, maat, gewicht):
    profielen = _profielen(tmp_path, monkeypatch)
    profielen.bewaar_profiel("a" * 64, maat, gewicht)

    assert profielen.laad_profiel("a" * 64) == {"maat_eenheid": maat, "gewicht_eenheid": gewicht}


@pytest.mark.parametrize("maat,gewicht", [("inch", "g"), ("mm", "ton"), ("g", "mm"), ([], "g"), (True, "kg")])
def test_ongeldige_eenheden_overschrijven_geen_bestaand_profiel(tmp_path, monkeypatch, maat, gewicht):
    profielen = _profielen(tmp_path, monkeypatch)
    profielen.bewaar_profiel("a" * 64, "mm", "g")

    with pytest.raises(ValueError):
        profielen.bewaar_profiel("a" * 64, maat, gewicht)

    assert profielen.laad_profiel("a" * 64) == {"maat_eenheid": "mm", "gewicht_eenheid": "g"}


@pytest.mark.parametrize("sleutel", ["../dealer", "a" * 63, "a" * 65, "z" * 64, None, 12])
def test_ongeldige_sleutels_mogen_geen_bestand_lezen_of_schrijven(tmp_path, monkeypatch, sleutel):
    profielen = _profielen(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        profielen.laad_profiel(sleutel)
    with pytest.raises(ValueError):
        profielen.bewaar_profiel(sleutel, "mm", "g")

    assert not profielen.PROFIEL_MAP.exists()


@pytest.mark.parametrize("inhoud", [
    "{geen geldige json", "[]", "null", "{}", '{"maat_eenheid":"mm"}',
    '{"maat_eenheid":"inch","gewicht_eenheid":"g"}',
    '{"maat_eenheid":"mm","gewicht_eenheid":"g","onbekend":true}',
])
def test_beschadigd_profiel_wordt_zichtbaar_gemeld(tmp_path, monkeypatch, inhoud):
    profielen = _profielen(tmp_path, monkeypatch)
    profielen.PROFIEL_MAP.mkdir()
    (profielen.PROFIEL_MAP / f"{'a' * 64}.json").write_text(inhoud)

    with pytest.raises(ValueError):
        profielen.laad_profiel("a" * 64)


def test_profielen_blijven_onafhankelijk_bij_opnieuw_opslaan(tmp_path, monkeypatch):
    profielen = _profielen(tmp_path, monkeypatch)
    profielen.bewaar_profiel("a" * 64, "mm", "g")
    profielen.bewaar_profiel("b" * 64, "cm", "kg")
    profielen.bewaar_profiel("a" * 64, "m", "kg")

    assert profielen.laad_profiel("a" * 64) == {"maat_eenheid": "m", "gewicht_eenheid": "kg"}
    assert profielen.laad_profiel("b" * 64) == {"maat_eenheid": "cm", "gewicht_eenheid": "kg"}
    assert sorted(p.suffix for p in profielen.PROFIEL_MAP.iterdir()) == [".json", ".json"]


def test_mislukte_atomische_vervanging_laat_vorige_keuze_intact(tmp_path, monkeypatch):
    profielen = _profielen(tmp_path, monkeypatch)
    profielen.bewaar_profiel("a" * 64, "mm", "g")

    def geweigerd(bron, doel):
        raise PermissionError("Geen schrijfrechten")

    monkeypatch.setattr(profielen.os, "replace", geweigerd)
    with pytest.raises(PermissionError):
        profielen.bewaar_profiel("a" * 64, "cm", "kg")

    assert profielen.laad_profiel("a" * 64) == {"maat_eenheid": "mm", "gewicht_eenheid": "g"}
    assert [p.name for p in profielen.PROFIEL_MAP.iterdir()] == [f"{'a' * 64}.json"]


def test_leesfout_is_geen_ontbrekend_profiel(tmp_path, monkeypatch):
    profielen = _profielen(tmp_path, monkeypatch)
    (profielen.PROFIEL_MAP / f"{'a' * 64}.json").mkdir(parents=True)

    with pytest.raises(OSError):
        profielen.laad_profiel("a" * 64)
