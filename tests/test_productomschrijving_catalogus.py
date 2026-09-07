"""Controleer dekking en inhoudsbehoud van de Duitse omschrijvingcatalogus."""

from collections import Counter
import json
from pathlib import Path
import re

import pytest

from artikeldata import Artikeldata


CATALOGUS_PAD = Path(__file__).resolve().parents[1] / "data" / "productomschrijvingen_de.json"


def lees_catalogus():
    assert CATALOGUS_PAD.exists(), "De Duitse productomschrijvingcatalogus ontbreekt."
    return json.loads(CATALOGUS_PAD.read_text(encoding="utf-8"))


def test_catalogus_dekt_alle_actuele_bronomschrijvingen_exact():
    catalogus = lees_catalogus()
    # Een ontbrekende of aangepaste bronsleutel verhindert de exacte vertaling.
    bron = {
        artikel["omschrijving"]
        for artikel in Artikeldata.laad().artikelen.values()
        if artikel.get("omschrijving")
    }
    assert catalogus["taal"] == "de"
    assert catalogus["versie"] == 1
    assert set(catalogus["velden"]["omschrijving"]) == bron
    assert all(
        isinstance(tekst, str) and tekst.strip()
        for tekst in catalogus["velden"]["omschrijving"].values()
    )


@pytest.mark.parametrize("bron, verwacht", [
    ("EASY•Q™ Nitrile wegwerphandschoenen XL", "EASY•Q™ Nitril-Einweghandschuhe XL"),
    ("EASY•Q™ RVS modelleermes 5 cm", "EASY•Q™ Edelstahl-Modellierspachtel 5 cm"),
    ("EASY•Q™ Aanbrandmes", "EASY•Q™ Schmalspachtel"),
    ("EASY•Q™ Kitmes", "EASY•Q™ Kittspachtel"),
    ("EASY•Q™ Houtconditiemeter CS1", "EASY•Q™ Holzfeuchteanzeiger CS1"),
    ("EASY•Q™ Mengplateau groot", "EASY•Q™ Mischbrett groß"),
    ("EASY•Q™ MIX & FIX mengbeker: set a 50 stuks", "EASY•Q™ MIX & FIX Mischbecher: Set zu 50 Stück"),
    ("EAZYFIX Nitril Wegwerphandschoenen (5 paar)", "EAZYFIX Nitril-Einweghandschuhe (5 Paar)"),
    ("EAZYFIX Reinigingsdoekjes (60 stuks)", "EAZYFIX Reinigungstücher (60 Stück)"),
    ("DRY SEAL™ MP Bruin (RAL 8007)", "DRY SEAL™ MP Braun (RAL 8007)"),
    ("DRY FLEX 4 component B", "DRY FLEX 4 Komponente B"),
    ("Niveau 2 opleiding: op locatie dealer", "Schulung Stufe 2: beim Händler vor Ort"),
    ("Opl.N2-N3 zijpaneel praktijksimulator betonplex 18x150x400mm",
     "Schulung N2-N3 Seitenplatte für Praxissimulator, beschichtetes Sperrholz 18x150x400mm"),
    ("DRY FLEX® 1  2-in-1", "DRY FLEX® 1  2-in-1"),
    ("BIO FLEX™ ALLROUND", "BIO FLEX™ ALLROUND"),
])
def test_vertaling_behoudt_betekenis_en_productvariant(bron, verwacht):
    catalogus = lees_catalogus()
    assert catalogus["velden"]["omschrijving"][bron] == verwacht


def test_vertalingen_behouden_getallen_eenheden_en_identificaties():
    catalogus = lees_catalogus()
    # Andere aantallen, maatnotaties of codes mogen geen ander product opleveren.
    getallen = r"\d+(?:[.,]\d+)?"
    eenheden = r"(?<![A-Za-z])(?:mm|cm|ml|kg|mtr\.|m|V)(?![A-Za-z])"
    codes = r"\b(?:CS1|DIN10|G22|WI-7|M6|K120|K36|K60|N[123](?:-N[123])?|RAL|JP|NL/EN/GE|XL|L)\b"
    merken = ("DRY FLEX", "DRY FIX", "DRY SEAL", "DRY SHIELD", "BIO FLEX",
              "EASY•Q", "EASY Q", "EAZYFIX", "Repair Care", "REPAIR CARE",
              "ANKO QUICK FIX", "BMH", "BURGY", "Calupaint", "Scotch Brite",
              "Heco", "Tesa", "M-Tork", "MIX & FIX", "High Performance", "LUMIN")
    for bron, vertaling in catalogus["velden"]["omschrijving"].items():
        assert re.findall(getallen, vertaling) == re.findall(getallen, bron), bron
        assert Counter(re.findall(eenheden, vertaling)) == Counter(re.findall(eenheden, bron)), bron
        assert Counter(re.findall(codes, vertaling)) == Counter(re.findall(codes, bron)), bron
        assert Counter(teken for teken in vertaling if teken in "®™") == Counter(
            teken for teken in bron if teken in "®™"
        ), bron
        for merk in merken:
            assert vertaling.count(merk) == bron.count(merk), (bron, merk)
