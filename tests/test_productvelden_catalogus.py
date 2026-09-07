"""Controleer Duitse productveldteksten tegen de werkelijk gebruikte bronwaarden."""

import json
import re
from pathlib import Path

import pytest

from artikeldata import Artikeldata


CATALOGUS = Path(__file__).resolve().parents[1] / "data" / "productvelden_de.json"
VELDEN = {
    "kleur", "verpakking", "verpakkingseenheid", "verwerkingstijd", "uitharding",
    "verbruik", "opslagtemperatuur", "verwerkingstemperatuur", "mengverhouding",
    "dichtheid", "laagdikte", "vaste_stofgehalte", "biobased_gehalte",
}


def lees_catalogus():
    # Zonder bestand kan de echte invuller deze bronwaarden niet Duits aanbieden.
    assert CATALOGUS.is_file(), "De Duitse catalogus voor productvelden ontbreekt."
    return json.loads(CATALOGUS.read_text(encoding="utf-8"))


def test_alle_huidige_productveldwaarden_hebben_een_duitse_vertaling():
    catalogus = lees_catalogus()
    bron = Artikeldata.laad()
    ontbrekend = []
    for veld_id in VELDEN:
        vertalingen = catalogus["velden"].get(veld_id, {})
        for artikel in bron.artikelen.values():
            waarde = bron.waarde(artikel, veld_id)
            if waarde and isinstance(waarde.waarde, str) and waarde.waarde:
                if not isinstance(vertalingen.get(waarde.waarde), str) or not vertalingen[waarde.waarde].strip():
                    ontbrekend.append((artikel["artikelcode"], veld_id, waarde.waarde))
    assert ontbrekend == []


def test_catalogus_bevat_geen_veiligheidsvelden_of_nieuwe_bronteksten():
    catalogus = lees_catalogus()
    bron = Artikeldata.laad()
    assert set(catalogus["velden"]) == VELDEN
    for veld_id, vertalingen in catalogus["velden"].items():
        bronteksten = {
            waarde.waarde
            for artikel in bron.artikelen.values()
            for waarde in [bron.waarde(artikel, veld_id)]
            if waarde and isinstance(waarde.waarde, str) and waarde.waarde
        }
        assert set(vertalingen) == bronteksten


def test_vertalingen_behouden_getallen_meettekens_en_componentletters():
    catalogus = lees_catalogus()
    # Een gewijzigd aantal, decimaal, temperatuursymbool of A/B-label is geen vertaling.
    beschermd = re.compile(r"\d+(?:[.,]\d+)*|[²³%°º<>=+]|\b[AB]\b")
    for veld_id, vertalingen in catalogus["velden"].items():
        for origineel, vertaald in vertalingen.items():
            assert beschermd.findall(vertaald) == beschermd.findall(origineel), (veld_id, origineel)
            assert not vertaald.startswith(("=", "+", "-", "@"))
            assert "\x00" not in vertaald


@pytest.mark.parametrize("veld_id, origineel, verwacht", [
    ("kleur", "Standaard wit en reebruin", "Standardmäßig weiß und rehbraun"),
    ("kleur", "A oranje transparant, B transparant, gemengd transparante massa",
     "A orange transparent, B transparent, gemischt transparente Masse"),
    ("verpakking", "Koker A 300 ml + Koker B 100 ml = 400 ml",
     "Kartusche A 300 ml + Kartusche B 100 ml = 400 ml"),
    ("verpakkingseenheid", "Kartonnen doos met 20 sets", "Karton mit 20 Sets"),
    ("verwerkingstijd", "1,5 - 2 uur", "1,5 - 2 Stunden"),
    ("uitharding", "Schuurbaar en overschilderbaar na ca. 4 uur",
     "Schleifbar und überstreichbar nach ca. 4 Stunden"),
    ("verbruik", "Ca. 250 g/m²", "Ca. 250 g/m²"),
    ("opslagtemperatuur", "5°C tot 30°C, R.V. max. 65%",
     "5°C bis 30°C, rel. Luftfeuchtigkeit max. 65%"),
    ("verwerkingstemperatuur", "0 - 30°C (verpakking: 0-35°C)",
     "0 - 30°C (Verpackung: 0-35°C)"),
    ("mengverhouding", "A: 2 volumedelen / B: 1 volumedeel",
     "A: 2 Volumenteile / B: 1 Volumenteil"),
    ("dichtheid", "1,05 kg/dm³ (gemengd)", "1,05 kg/dm³ (gemischt)"),
    ("laagdikte", "0 - 20 mm (minimaal 5 mm bij systeemopbouw)",
     "0 - 20 mm (mindestens 5 mm beim Systemaufbau)"),
    ("vaste_stofgehalte", "100 vol.% (= 100 gew.%)", "100 vol.% (= 100 gew.%)"),
    ("biobased_gehalte", "35% (OK Biobased, TüV Austria, 1 ster)",
     "35% (OK Biobased, TüV Austria, 1 Stern)"),
])
def test_representatieve_duitse_productteksten(veld_id, origineel, verwacht):
    catalogus = lees_catalogus()
    assert catalogus["velden"][veld_id][origineel] == verwacht
