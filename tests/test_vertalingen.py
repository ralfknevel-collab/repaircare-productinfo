"""De taalkeuze verandert schermteksten, zonder broninhoud te herschrijven."""

import pytest

from veldcatalogus import VELDEN
from vertalingen import DE, vertaal, vertaal_melding


@pytest.mark.parametrize("taal, verwacht", [
    ("nl", "Dealerbestanden invullen"),
    ("de", "Händlerdateien ausfüllen"),
    ("fr", "Dealerbestanden invullen"),
])
def test_taalkeuze_en_onbekende_taal_vallen_terug_op_nederlands(taal, verwacht):
    assert vertaal("Dealerbestanden invullen", taal) == verwacht


def test_standaardtaal_blijft_nederlands():
    assert vertaal("Geavanceerd") == "Geavanceerd"


@pytest.mark.parametrize("taal", ["nl", "de"])
def test_onbekende_tekst_blijft_letterlijk_behouden(taal):
    origineel = "DRY FLEX 4 A: 200 ml / B: 100 ml {etiket}\nEAN: 08714748004368"
    assert vertaal(origineel, taal) == origineel
    assert vertaal_melding(origineel, taal) == origineel


@pytest.mark.parametrize("taal, verwacht", [
    ("nl", "Tabblad: Artikel {A} / B. Bestaande waarden blijven staan tenzij je bij Geavanceerd anders kiest."),
    ("de", "Tabellenblatt: Artikel {A} / B. Vorhandene Werte bleiben erhalten, sofern unter Erweitert nichts anderes ausgewählt wird."),
])
def test_plaatshouders_bewaren_de_aangeleverde_tekst(taal, verwacht):
    assert vertaal(
        "Tabblad: {tabblad}. Bestaande waarden blijven staan tenzij je bij Geavanceerd anders kiest.",
        taal, tabblad="Artikel {A} / B",
    ) == verwacht


def test_onbekende_sjabloontekst_wordt_wel_ingevuld():
    assert vertaal("Nieuwe melding: {waarde}", "de", waarde="{A}: 1,72 kg") == "Nieuwe melding: {A}: 1,72 kg"


def test_alle_vaste_veldnamen_hebben_een_duitse_vertaling():
    ontbrekend = [v.label for v in VELDEN if v.label not in DE]
    assert ontbrekend == []
    assert vertaal("Nettogewicht per doos (collo)", "de") == "Nettogewicht pro Karton (Kollo)"
    assert vertaal("Adviesverkoopprijs exclusief btw (EUR)", "de") == "Unverbindliche Preisempfehlung ohne MwSt. (EUR)"


@pytest.mark.parametrize("tekst, verwacht", [
    ("Herkend aan de kolomkop.", "Anhand der Spaltenüberschrift erkannt."),
    ("Kolomherkenning bezig: 12,345 tekens ontvangen.", "Spaltenerkennung läuft: 12,345 Zeichen empfangen."),
    ("Bestandsformaat .xls wordt niet ondersteund. Sla het bestand op als .xlsx of .csv.",
     "Das Dateiformat .xls wird nicht unterstützt. Bitte die Datei als .xlsx oder .csv speichern."),
    ("Automatische kolomkoppeling mislukt (API: {ongekend}). Kies de velden handmatig.",
     "Die automatische Spaltenzuordnung ist fehlgeschlagen (API: {ongekend}). Bitte die Felder manuell zuordnen."),
    ("Geen sleutelkolom gekozen (artikelnummer, EAN of omschrijving).",
     "Keine Schlüsselspalte ausgewählt (Artikelnummer, EAN oder Beschreibung)."),
])
def test_bekende_programmameldingen_worden_vertaald(tekst, verwacht):
    assert vertaal_melding(tekst, "de") == verwacht
    assert vertaal_melding(tekst, "nl") == tekst


def test_vrije_ai_tekst_met_bekende_woorden_blijft_behouden():
    tekst = "Controleer 'Gewichten' bij deze productnaam. Geavanceerd: {toelichting}."
    assert vertaal_melding(tekst, "de") == tekst


def test_bekende_eenheidstoevoeging_na_vrije_ai_tekst():
    tekst = "AI zegt: artikel {A} / B. Eenheid ingesteld op kg (Keuze gebruiker in de tool)."
    assert vertaal_melding(tekst, "de") == (
        "AI zegt: artikel {A} / B. Einheit auf kg eingestellt (Auswahl in der Anwendung)."
    )


def test_bekende_eenheidstoevoeging_na_lokale_toelichting():
    tekst = "Herkend aan de volledige kolomkop. Eenheid ingesteld op mm (Bewaarde keuze voor dit dealerformaat)."
    assert vertaal_melding(tekst, "de") == (
        "Anhand der vollständigen Spaltenüberschrift erkannt. Einheit auf mm eingestellt "
        "(Gespeicherte Auswahl für dieses Händlerformat)."
    )


def test_onbekende_eenheidsbron_blijft_letterlijk_behouden():
    tekst = "Eenheid ingesteld op kg (bron {A} / B)."
    assert vertaal_melding(tekst, "de") == "Einheit auf kg eingestellt (bron {A} / B)."


@pytest.mark.parametrize("vooraf", ["", "AI: controleer artikel {A} / B. "])
def test_herhaalde_kolomwaarschuwingen_behouden_vrije_ai_tekst(vooraf):
    tekst = (
        vooraf + "Kolom 'Onbekend A' uit het Claude-voorstel niet gevonden in de kopregel. "
        "Kolom 'Hersteller'Nr {B}' uit het Claude-voorstel niet gevonden in de kopregel."
    )
    assert vertaal_melding(tekst, "de") == (
        vooraf + "Spalte 'Onbekend A' aus dem Claude-Vorschlag nicht in der Kopfzeile gefunden. "
        "Spalte 'Hersteller'Nr {B}' aus dem Claude-Vorschlag nicht in der Kopfzeile gefunden."
    )


def test_meerdere_eenheidsfouten_worden_afzonderlijk_vertaald():
    tekst = (
        "Kolom 'Lengte': eenheid kg past niet bij Lengte per stuk (mm) "
        "Kolom 'Gewicht': eenheid mm past niet bij Nettogewicht per stuk (g)"
    )
    assert vertaal_melding(tekst, "de") == (
        "Spalte 'Lengte': Einheit kg passt nicht zu Lengte per stuk (mm) "
        "Spalte 'Gewicht': Einheit mm passt nicht zu Nettogewicht per stuk (g)"
    )


def test_vertalen_wijzigt_catalogus_niet():
    voor = [(v.id, v.label, v.eenheid) for v in VELDEN]
    for v in VELDEN:
        vertaal(v.label, "de")
    assert [(v.id, v.label, v.eenheid) for v in VELDEN] == voor
