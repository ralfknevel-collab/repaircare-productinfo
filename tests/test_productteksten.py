import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import pytest

from artikeldata import Waarde
from productteksten import Productteksten, VertalingOntbreekt


def waarde(tekst, **extra):
    return Waarde(tekst, extra.pop("eenheid", None), "Product Data Sheet", **extra)


def schrijf_catalogus(pad, velden, **extra):
    inhoud = {"taal": "de", "versie": 1, "velden": velden, **extra}
    pad.write_text(json.dumps(inhoud, ensure_ascii=False), encoding="utf-8")
    return pad


def test_vertaalt_exacte_brontekst_en_bewaart_herkomst_zonder_mutatie():
    bron = waarde("Wit", regel="Vastgesteld op artikelblad.", eenduidig=False,
                  onzeker_reden="Componentkleur", eenheid="kleurcode")
    origineel = asdict(bron)
    catalogus = Productteksten({"kleur": {"Wit": "Weiß"}}, versie="2026")

    resultaat = catalogus.vertaal(bron, "kleur", "de")

    assert resultaat is not bron
    assert resultaat.waarde == "Weiß"
    assert resultaat.bron == "Product Data Sheet"
    assert resultaat.eenheid == "kleurcode"
    assert resultaat.eenduidig is False
    assert resultaat.onzeker_reden == "Componentkleur"
    assert "Vastgesteld op artikelblad." in resultaat.regel
    assert "de" in resultaat.regel and "2026" in resultaat.regel
    assert "vertal" in resultaat.regel.lower()
    assert asdict(bron) == origineel


def test_prijslijst_omschrijving_gebruikt_dezelfde_vertaling():
    catalogus = Productteksten({"omschrijving": {"DRY FIX® UNI klein": "DRY FIX® UNI klein"}})
    bron = waarde("DRY FIX® UNI klein")
    assert catalogus.vertaal(bron, "prijslijst_omschrijving", "de").waarde == "DRY FIX® UNI klein"
    assert catalogus.vertaal(bron, "omschrijving", "de").waarde == "DRY FIX® UNI klein"


@pytest.mark.parametrize("veld_id", [
    "ean", "artikelcode", "adviesprijs", "ghs", "h_zinnen", "p_zinnen", "adr", "un_nummer",
    "vast:kleur", "ruw:Omschrijving", "component:A:kleur", "onbekend", None, 42,
])
def test_niet_toegestane_velden_blijven_ongewijzigd(veld_id):
    bron = waarde("Wit")
    assert Productteksten({"kleur": {"Wit": "Weiß"}}).vertaal(bron, veld_id, "de") is bron


def test_nederlands_vraagt_geen_vertaling_en_bewaart_hetzelfde_object():
    bron = waarde("Onbekende omschrijving")
    assert Productteksten({}).vertaal(bron, "omschrijving", "nl") is bron


@pytest.mark.parametrize("inhoud", [None, "", "  ", 0, 12.5, False, [], {}, "100", "1,25", "-3.5"])
def test_lege_en_numerieke_waarden_hebben_geen_vertaling_nodig(inhoud):
    bron = waarde(inhoud)
    assert Productteksten({}).vertaal(bron, "omschrijving", "de") is bron


@pytest.mark.parametrize("taal", ["en", "DE", "", None, [], 1])
def test_ongeldige_taal_wordt_zichtbaar_geweigerd(taal):
    with pytest.raises(ValueError, match="taal"):
        Productteksten({}).vertaal(waarde("Wit"), "kleur", taal)


@pytest.mark.parametrize("inhoud", ["wit", " Wit", "Wit ", "WIT", "Wit gewijzigd"])
def test_verouderde_of_bijna_gelijke_brontekst_krijgt_nooit_een_vertaling(inhoud):
    with pytest.raises(VertalingOntbreekt, match="kleur"):
        Productteksten({"kleur": {"Wit": "Weiß"}}).vertaal(waarde(inhoud), "kleur", "de")


def test_tekst_in_verkeerd_veld_is_geen_vertaling():
    with pytest.raises(VertalingOntbreekt, match="verpakking"):
        Productteksten({"kleur": {"Wit": "Weiß"}}).vertaal(waarde("Wit"), "verpakking", "de")


@pytest.mark.parametrize("bron,duits", [
    ("-5 tot +30°C", "-5 bis +30°C"),
    ("-5 - +30°C", "-5 - +30°C"),
])
def test_negatieve_temperatuurrange_met_eenheid_aan_het_einde_is_geen_formule(bron, duits):
    catalogus = Productteksten({"opslagtemperatuur": {bron: duits}})
    assert catalogus.vertaal(waarde(bron), "opslagtemperatuur", "de").waarde == duits


@pytest.mark.parametrize("duits", ["", " ", "=1+1", " @SUM(A1)", "+SUM(A1)", "-SUM(A1)", "\t=1", "\u200b=1"])
def test_onbruikbare_of_formuleachtige_vertaling_wordt_per_waarde_geweigerd(duits):
    catalogus = Productteksten({"omschrijving": {"Hobbymes": duits}})
    with pytest.raises(VertalingOntbreekt, match="vertaling"):
        catalogus.vertaal(waarde("Hobbymes"), "omschrijving", "de")


@pytest.mark.parametrize("veld_id,bron,duits", [
    ("omschrijving", "EASY•Q™ Bolkopfrees 9,5 mm - 10 stuks", "EASY•Q™ Kugelfräser 9,5 mm - 10 Stück"),
    ("omschrijving", "EASY•Q™ RVS modelleermes 10 cm", "EASY•Q™ Edelstahl-Modelliermesser 10 cm"),
    ("verwerkingstijd", "15–20 minuten", "15–20 Minuten"),
    ("dichtheid", "1,05 kg/dm³ (gemengd)", "1,05 kg/dm³ (gemischt)"),
    ("opslagtemperatuur", "-5°C tot +30°C", "-5°C bis +30°C"),
    ("verwerkingstemperatuur", "+5°C tot +30°C", "+5°C bis +30°C"),
    ("opslagtemperatuur", "5°C tot 30°C, R.V. max. 65%", "5°C bis 30°C, rel. Luftfeuchtigkeit max. 65%"),
    ("mengverhouding", "A 2,5 volumedelen : B 1 volumedeel", "A 2,5 Volumenteile : B 1 Volumenteil"),
    ("vaste_stofgehalte", "100 vol.% (= 100 gew.%)", "100 vol.% (= 100 Gew.%)"),
    ("kleur", "Crème 🟡", "Creme 🟡"),
    ("omschrijving", "Houten 'spatel'; klein", "Holzspatel; klein"),
])
def test_gecontroleerde_vertalingen_behouden_technische_waarden(veld_id, bron, duits):
    catalogus = Productteksten({veld_id: {bron: duits}})
    assert catalogus.vertaal(waarde(bron), veld_id, "de").waarde == duits


@pytest.mark.parametrize("veld_id,bron,duits", [
    ("verwerkingstijd", "15-20 minuten", "15-25 Minuten"),
    ("verpakking", "200 ml", "200 l"),
    ("dichtheid", "1,05 kg/dm³", "1,05 g/dm³"),
    ("vaste_stofgehalte", "100 vol.%", "100 vol."),
    ("omschrijving", "Anker 230V SH", "Anker 230 SH"),
    ("opslagtemperatuur", "-5°C tot +30°C", "5°C bis +30°C"),
    ("omschrijving", "DRY FLEX® 4", "DRY FIX® 4"),
    ("omschrijving", "DRY FLEX® 4", "DRY FLEX 4"),
    ("omschrijving", "EAZYFIX Mengbeker", "Mengbecher"),
    ("omschrijving", "Duimstok Repair Care", "Zollstock"),
    ("omschrijving", "Houtconditiemeter CS1", "Holzfeuchtemessgerät XT1"),
    ("omschrijving", "Nieuwmerk® Houten spatel", "Holzspatel"),
    ("omschrijving", "Hobbymes", "Hobbymesser 2"),
    ("verwerkingstemperatuur", "0 tot 30°C", "+SUM(0;30)°C"),
])
def test_veranderde_techniek_en_productidentiteit_worden_geweigerd(veld_id, bron, duits):
    catalogus = Productteksten({veld_id: {bron: duits}})
    with pytest.raises(VertalingOntbreekt, match="vertaling"):
        catalogus.vertaal(waarde(bron), veld_id, "de")


def test_laad_twee_bestanden_en_behoud_beide_versies_in_herkomst(tmp_path):
    omschrijvingen = schrijf_catalogus(tmp_path / "omschrijvingen.json", {"omschrijving": {"Hobbymes": "Hobbymesser"}}, versie=2)
    velden = schrijf_catalogus(tmp_path / "velden.json", {"kleur": {"Wit": "Weiß"}}, versie=3)
    catalogus = Productteksten.laad((omschrijvingen, velden))
    assert catalogus.vertaal(waarde("Hobbymes"), "omschrijving", "de").waarde == "Hobbymesser"
    kleur = catalogus.vertaal(waarde("Wit"), "kleur", "de")
    assert kleur.waarde == "Weiß"
    assert "2" in kleur.regel and "3" in kleur.regel


@pytest.mark.parametrize("wijziging", [
    {"taal": "en"}, {"versie": None}, {"versie": True}, {"versie": 0},
    {"velden": []}, {"velden": {"kleur": []}}, {"velden": {"kleur": {"Wit": 123}}},
    {"velden": {"kleur": {"": "Weiß"}}}, {"velden": {"h_zinnen": {"Gevaar": "Gefahr"}}},
])
def test_laad_ongeldig_schema_geeft_begrijpelijke_fout(tmp_path, wijziging):
    pad = schrijf_catalogus(tmp_path / "catalogus.json", {}, **wijziging) if "velden" not in wijziging else schrijf_catalogus(tmp_path / "catalogus.json", wijziging["velden"])
    with pytest.raises(ValueError, match="[Cc]atalogus|[Vv]ertaalcatalogus"):
        Productteksten.laad((pad,))


@pytest.mark.parametrize("inhoud", ["{", "[]", '{"taal":"de","versie":1}', '{"taal":"de","versie":1,"velden":{"kleur":{"Wit":"Weiß","Wit":"Schwarz"}}}'])
def test_laad_ongeldige_json_en_dubbele_sleutels_worden_niet_stil_hersteld(tmp_path, inhoud):
    pad = tmp_path / "fout.json"
    pad.write_text(inhoud, encoding="utf-8")
    with pytest.raises(ValueError, match="[Cc]atalogus|[Vv]ertaalcatalogus"):
        Productteksten.laad((pad,))


def test_laad_ontbrekend_bestand_geeft_zichtbare_fout(tmp_path):
    with pytest.raises(ValueError, match="[Cc]atalogus|[Vv]ertaalcatalogus"):
        Productteksten.laad((tmp_path / "ontbreekt.json",))


def test_laad_onleesbare_tekencodering_geeft_zichtbare_fout(tmp_path):
    pad = tmp_path / "ongeldige_utf8.json"
    pad.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="[Cc]atalogus|[Vv]ertaalcatalogus"):
        Productteksten.laad((pad,))


@pytest.mark.parametrize("velden,versie", [(None, "1"), ({"kleur": {42: "Weiß"}}, "1"), ({}, ""), ({}, 1)])
def test_constructor_weigert_ongeldige_tabel_en_versie(velden, versie):
    with pytest.raises(ValueError, match="[Cc]atalogus|[Vv]ertaalcatalogus"):
        Productteksten(velden, versie)


def test_tegenstrijdige_duplicaten_tussen_bestanden_worden_geweigerd(tmp_path):
    een = schrijf_catalogus(tmp_path / "een.json", {"omschrijving": {"Hobbymes": "Hobbymesser"}})
    twee = schrijf_catalogus(tmp_path / "twee.json", {"prijslijst_omschrijving": {"Hobbymes": "Bastelmesser"}})
    with pytest.raises(ValueError, match="[Cc]atalogus|[Vv]ertaalcatalogus"):
        Productteksten.laad((een, twee))


def test_identieke_duplicaten_tussen_bestanden_mogen_samenkomen(tmp_path):
    een = schrijf_catalogus(tmp_path / "een.json", {"omschrijving": {"Hobbymes": "Hobbymesser"}})
    twee = schrijf_catalogus(tmp_path / "twee.json", {"omschrijving": {"Hobbymes": "Hobbymesser"}})
    assert Productteksten.laad((een, twee)).vertaal(waarde("Hobbymes"), "omschrijving", "de").waarde == "Hobbymesser"


def test_vingerafdruk_verandert_bij_bron_vertaling_of_versie_en_niet_door_volgorde():
    basis = Productteksten({"kleur": {"Wit": "Weiß", "Zwart": "Schwarz"}}, versie="1")
    omgekeerd = Productteksten({"kleur": {"Zwart": "Schwarz", "Wit": "Weiß"}}, versie="1")
    assert basis.vingerafdruk == omgekeerd.vingerafdruk
    for velden, versie in [({"kleur": {"Wit nieuw": "Weiß", "Zwart": "Schwarz"}}, "1"),
                           ({"kleur": {"Wit": "Weiss", "Zwart": "Schwarz"}}, "1"),
                           ({"kleur": {"Wit": "Weiß", "Zwart": "Schwarz"}}, "2")]:
        assert Productteksten(velden, versie).vingerafdruk != basis.vingerafdruk


def test_wijziging_aangeleverde_dict_verandert_bestaande_catalogus_niet():
    velden = {"kleur": {"Wit": "Weiß"}}
    catalogus = Productteksten(velden)
    afdruk = catalogus.vingerafdruk
    velden["kleur"]["Wit"] = "Schwarz"
    assert catalogus.vertaal(waarde("Wit"), "kleur", "de").waarde == "Weiß"
    assert catalogus.vingerafdruk == afdruk


def test_catalogus_met_tienduizend_teksten_ondersteunt_gelijktijdig_lezen():
    catalogus = Productteksten({"omschrijving": {f"Hobbymes {n}": f"Hobbymesser {n}" for n in range(10000)}})
    with ThreadPoolExecutor(max_workers=4) as executor:
        resultaten = list(executor.map(lambda n: catalogus.vertaal(waarde(f"Hobbymes {n}"), "omschrijving", "de").waarde, [0, 9999, 5000, 1]))
    assert resultaten == ["Hobbymesser 0", "Hobbymesser 9999", "Hobbymesser 5000", "Hobbymesser 1"]
