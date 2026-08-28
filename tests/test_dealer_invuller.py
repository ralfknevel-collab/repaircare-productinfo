from pathlib import Path
from types import SimpleNamespace

import csv
import io
import json
import openpyxl
import pytest

from artikeldata import Artikeldata, Waarde
from dealer_invuller import (
    CONTROLE_TAB,
    Rapport,
    bepaal_mapping,
    controleer_eenheden,
    kies_tabblad,
    koppen,
    laad_werkboek,
    lees_rijen,
    maak_waarde,
    match_rijen,
    schrijf_controle,
    verwerk,
    vind_kopregel,
    vul_in,
    werkboek_naar_bytes,
)
from dealer_invuller import main as cli_main
from mapping import KolomMapping, Mapping
from tests.conftest import SEEFELDER_KOPPEN, SEEFELDER_RIJEN, maak_dealerbestand
from tests.test_mapping import _nep_client


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


def test_laad_csv_cp1252():
    # Duitse ERP-exports zijn vaak Windows-1252; umlauten mogen niet verminken.
    wb = laad_werkboek("Länge;Gewicht\n1;\n".encode("cp1252"), "lijst.csv")
    ws = kies_tabblad(wb, None)
    assert [c.value for c in ws[1]] == ["Länge", "Gewicht"]


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


def test_laad_csv_fallback_muteert_stdlib_niet():
    # Eén kolom: de Sniffer kan geen scheidingsteken bepalen -> fallback op ';'.
    wb = laad_werkboek("ArtNr\n2010005\n".encode("utf-8"), "een.csv")
    ws = kies_tabblad(wb, None)
    assert ws.cell(1, 1).value == "ArtNr" and ws.cell(2, 1).value == "2010005"
    assert csv.excel.delimiter == ","


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


def test_cli_zonder_sleutel_geeft_melding(seefelder_bestand, tmp_path, artikeldata_dict, monkeypatch, capsys):
    pj = tmp_path / "artikeldata.json"
    pj.write_text(json.dumps(artikeldata_dict), encoding="utf-8")
    import artikeldata as ad_mod
    monkeypatch.setattr(ad_mod, "ARTIKELDATA_FILE", pj)
    monkeypatch.setattr(ad_mod, "VASTE_WAARDEN_FILE", tmp_path / "geen.json")
    pm = tmp_path / "leeg.json"
    pm.write_text(json.dumps(Mapping(0, []).naar_dict()), encoding="utf-8")
    assert cli_main([str(seefelder_bestand), "--mapping", str(pm), "--uit", str(tmp_path / "u.xlsx")]) == 1
    assert "Geen sleutelkolom" in capsys.readouterr().out


def test_controleer_eenheden():
    m = Mapping(0, [
        KolomMapping("HerstellerArtNr", "sleutel_artikelcode", None, "hoog", ""),
        KolomMapping("Nettogewicht", "netto_gewicht", "cm", "middel", ""),
        KolomMapping("Länge", "lengte", "cm", "hoog", ""),
        KolomMapping("Zolltarifnummer", "gn_code", None, "hoog", ""),
    ])
    meldingen = controleer_eenheden(m)
    assert len(meldingen) == 1
    assert meldingen[0] == "Kolom 'Nettogewicht': eenheid cm past niet bij Nettogewicht per stuk (g)"

    m.kolommen[1].eenheid = "kg"
    assert controleer_eenheden(m) == []


def test_vul_in_meldt_kolommen_buiten_de_kopregel(seefelder_bestand, ad):
    ws = kies_tabblad(laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name), None)
    m = Mapping(0, SEEFELDER_MAPPING.kolommen + [
        KolomMapping("Bestaat niet", "bruto_gewicht", "g", "laag", ""),
        KolomMapping("Ook weg", "sleutel_ean", None, "laag", ""),
        KolomMapping("Genegeerd", "geen", None, "laag", ""),
    ])
    rapport = vul_in(ws, m, ad)
    assert rapport.overgeslagen_kolommen == ["Bestaat niet", "Ook weg"]


def test_schrijf_controle_meldt_overgeslagen_kolommen(seefelder_bestand, ad):
    wb = laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name)
    ws = kies_tabblad(wb, None)
    rapport = vul_in(ws, SEEFELDER_MAPPING, ad)
    rapport.overgeslagen_kolommen = ["Bestaat niet"]
    schrijf_controle(wb, rapport)
    tekst = "\n".join(" ".join(str(c) for c in rij if c is not None)
                      for rij in wb[CONTROLE_TAB].iter_rows(values_only=True))
    assert "Overgeslagen kolommen (niet in kopregel): Bestaat niet" in tekst


# --- bepaal_mapping ---------------------------------------------------------

def _antwoord_een_kolom(kolom: str) -> dict:
    return {"kopregel_index": 0, "kolommen": [
        {"kolom": kolom, "doelveld": "sleutel_artikelcode", "eenheid": "",
         "zekerheid": "hoog", "toelichting": ""}], "opmerkingen": ""}


def test_bepaal_mapping_vult_aan_en_reconcilieert_kolomnamen(seefelder_bestand, ad):
    ws = kies_tabblad(laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name), None)
    # Claude noemt de kolom met afwijkende hoofdletters en extra whitespace.
    client, aanroepen = _nep_client(_antwoord_een_kolom("  herstellerartnr "))
    m = bepaal_mapping(client, ws, ad)

    assert m.kopregel_index == 0
    assert len(aanroepen) == 1
    # Claude's kolom eerst, daarna de rest in kopregelvolgorde als 'geen'.
    assert sorted(k.kolom for k in m.kolommen) == sorted(SEEFELDER_KOPPEN)
    assert m.kolommen[0].kolom == "HerstellerArtNr" and m.kolommen[0].doelveld == "sleutel_artikelcode"
    assert all(k.doelveld == "geen" for k in m.kolommen[1:])
    assert m.opmerkingen == ""


def test_bepaal_mapping_verwijdert_onbekende_kolom(seefelder_bestand, ad):
    ws = kies_tabblad(laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name), None)
    client, _ = _nep_client(_antwoord_een_kolom("Bestaat niet"))
    m = bepaal_mapping(client, ws, ad)
    assert "Bestaat niet" not in [k.kolom for k in m.kolommen]
    assert [k.kolom for k in m.kolommen] == SEEFELDER_KOPPEN
    assert "Kolom 'Bestaat niet' uit het Claude-voorstel niet gevonden in de kopregel." in m.opmerkingen


def test_bepaal_mapping_zonder_client(seefelder_bestand, ad):
    ws = kies_tabblad(laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name), None)
    m = bepaal_mapping(None, ws, ad)
    assert [k.kolom for k in m.kolommen] == SEEFELDER_KOPPEN
    assert all(k.doelveld == "geen" for k in m.kolommen)
    assert "handmatig" in m.opmerkingen


def test_bepaal_mapping_bij_fout_lege_mapping(seefelder_bestand, ad):
    ws = kies_tabblad(laad_werkboek(seefelder_bestand.read_bytes(), seefelder_bestand.name), None)

    def create(**kwargs):
        raise ValueError("API stuk")

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    m = bepaal_mapping(client, ws, ad)
    assert [k.kolom for k in m.kolommen] == SEEFELDER_KOPPEN
    assert all(k.doelveld == "geen" for k in m.kolommen)
    assert "API stuk" in m.opmerkingen


def test_bepaal_mapping_zonder_kopregel(tmp_path, ad):
    pad = maak_dealerbestand(tmp_path / "geenkop.xlsx", [1, 2, 3], [[4, 5, 6]])
    ws = kies_tabblad(laad_werkboek(pad.read_bytes(), pad.name), None)
    m = bepaal_mapping(None, ws, ad)
    assert m.kopregel_index == 0 and m.kolommen == []
    assert "kopregel" in m.opmerkingen.lower()
