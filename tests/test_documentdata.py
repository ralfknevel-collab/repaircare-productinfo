import pytest

from artikeldata import Artikeldata
from documentdata import koppel_documenten, normaliseer_veld

PRODUCTNAMEN = ["DRY FLEX 4", "DRY FLEX 4 2-IN-1", "DRY FIX UNI", "BIO FLEX COOL", "DRY FLEX 1"]


@pytest.mark.parametrize("naam, verwacht", [
    ("Signaalwoord", ("signaalwoord", None)),
    ("Signaalwoord Component A", ("signaalwoord", "A")),
    ("Component B - UN-nummer", ("un_code", "B")),
    ("Vlampunt Component A (BIO FLEX)", ("vlampunt", "A")),
    ("Vlampunt component B", ("vlampunt", "B")),
    ("DRY FLEX 4 - Vlampunt A", ("vlampunt", "A")),
    ("Vlampunt DRY FIX UNI A en B", ("vlampunt", None)),
    ("Verwerkingstijd bij 20°C (BIO FLEX)", ("verwerkingstijd", None)),
    ("Potlife/verwerkingstijd DRY FIX UNI", ("verwerkingstijd", None)),
    ("DRY FLEX 4 - Verwerkingstijd bij 20°C", ("verwerkingstijd", None)),
    ("Uitharding/overschilderbaar bij 20°C", ("uitharding", None)),
    ("Transportgevarenklasse", ("klasse", None)),
    ("Component A - transportklasse", ("klasse", "A")),
    ("Pictogrammen", ("ghs", None)),
    ("Gevarenaanduidingen", ("h_zinnen", None)),
    ("EUH-zinnen", ("euh_zinnen", None)),
    ("Opslag/vervoer", ("opslagtemperatuur", None)),
    ("Relatieve dichtheid Component B", ("dichtheid", "B")),
    ("Dichtheid DRY FIX UNI bij 20°C", ("dichtheid", None)),
    ("Kleur componenten", ("kleur", None)),
    ("Verpakking BIO FLEX COOL", ("verpakking", None)),
    ("Verpakkingseenheid", ("verpakkingseenheid", None)),
    ("Verpakkingsgroep", ("verpakkingsgroep", None)),
    ("KOMO certificaatnummer DRY FIX UNI", ("certificaat", None)),
    ("EURAL afvalcode", ("eural_code", None)),
    ("Kemler-nr.", ("kemler", None)),
    ("ADR classificatiecode", ("adr_classificatiecode", None)),
    ("Datum herziening", ("sds_datum", None)),
    ("Versie Component A", ("sds_versie", "A")),
    ("ATE oraal", (None, None)),
    ("Kookpunt", (None, None)),
    ("Max. vochtgehalte ondergrond", (None, None)),
])
def test_normaliseer_veld(naam, verwacht):
    assert normaliseer_veld(naam, PRODUCTNAMEN) == verwacht


@pytest.mark.parametrize("veld_id, waarde, verwacht", [
    ("un_code", "UN 3082", "3082"),
    ("un_code", "UN 3082, klasse 9", "3082"),
    ("un_code", "Niet van toepassing", "Niet van toepassing"),
    ("klasse", "8, verpakkingsgroep II", "8"),
    ("klasse", "4.1", "4.1"),
    ("verpakkingsgroep", "III", "III"),
    ("verpakkingsgroep", "PG II (ADR)", "II"),
    ("ghs", "GHS05, GHS07, GHS09", ["GHS05", "GHS07", "GHS09"]),
    ("ghs", "Geen", "Geen"),
    ("kleur", "  Groen   transparant ", "Groen transparant"),
])
def test_schoon_waarde(veld_id, waarde, verwacht):
    from documentdata import _schoon_waarde
    assert _schoon_waarde(veld_id, waarde) == verwacht


def _art(code, omschrijving, comps=()):
    a = {"artikelcode": code, "omschrijving": omschrijving, "componenten": [], "ruw": {}}
    for naam, velden in comps:
        a["componenten"].append({"naam": naam, "ruw": {}, **velden})
    return a


KENNISBANK = [
    {"bestand": "Productsheet DRY FLEX 4.pdf", "categorie": "productdatablad", "product": "DRY FLEX 4",
     "component": "2-in-1", "specs": [
         {"veld": "Verwerkingstijd bij 20°C", "waarde": "20 - 25 minuten"},
         {"veld": "Vlampunt Component A", "waarde": ">65°C"},
         {"veld": "Mengverhouding", "waarde": "A 3 : B 1 (volumedelen)"},
         {"veld": "Kleur", "waarde": "Groen"}]},
    {"bestand": "Veiligheidsblad DRY FLEX 4 - component A.pdf", "categorie": "veiligheidsblad",
     "product": "DRY FLEX 4", "component": "A", "specs": [
         {"veld": "Signaalwoord", "waarde": "Waarschuwing"},
         {"veld": "UN-nummer", "waarde": "UN 3082"},
         {"veld": "Pictogrammen", "waarde": "GHS07, GHS09"},
         {"veld": "Kleur", "waarde": "Lichtgroen"},
         {"veld": "Opslagtemperatuur", "waarde": "10 – 30 °C"}]},
    {"bestand": "Veiligheidsblad DRY FLEX 4 - component B.pdf", "categorie": "veiligheidsblad",
     "product": "DRY FLEX 4", "component": "B", "specs": [
         {"veld": "Signaalwoord", "waarde": "Gevaar"},
         {"veld": "UN-nummer", "waarde": "UN 2735"}]},
    {"bestand": "Veiligheidsblad DRY FLEX 4 2-in-1.pdf", "categorie": "veiligheidsblad",
     "product": "DRY FLEX 4 2-IN-1", "component": "2-in-1", "specs": [
         {"veld": "Signaalwoord", "waarde": "Gevaar"},
         {"veld": "UN-nummer", "waarde": "UN 3082"}]},
    {"bestand": "Veiligheidsblad DRY FLEX 1 - component A.pdf", "categorie": "veiligheidsblad",
     "product": "DRY FLEX 1", "component": "A", "specs": [
         {"veld": "UN-nummer", "waarde": "UN 9999"}]},
    {"bestand": "x.xlsx", "categorie": "artikeloverzicht", "product": "(diverse artikelen)", "specs": []},
]


@pytest.fixture
def artikelen():
    return {
        "2022005": _art("2022005", "DRY FLEX 4", [("A", {"netto_g": 330, "un_code": "3082"}), ("B", {"netto_g": 114, "un_code": "2735"})]),
        "2022205": _art("2022205", "DRY FLEX® 4 2-in-1 150 ml", [("A", {"netto_g": 109}), ("B", {"netto_g": 52})]),
        "2021005": _art("2021005", "DRY FLEX 16", [("A", {}), ("B", {})]),
        "2023005": _art("2023005", "DRY FLEX 1", [("A", {"un_code": "3082"}), ("B", {})]),
        "4513032": _art("4513032", "EASY Q Modelleerspatel metaal 50 mm"),
    }


def test_koppel_documenten(artikelen):
    gekoppeld, meldingen = koppel_documenten(artikelen, KENNISBANK)
    assert gekoppeld == 3  # DRY FLEX 4, 2-in-1, DRY FLEX 1; niet DRY FLEX 16, niet de spatel

    a = artikelen["2022005"]
    assert a["documenten"]["verwerkingstijd"] == {"waarde": "20 - 25 minuten", "bron": "Productsheet DRY FLEX 4.pdf", "categorie": "productdatablad"}
    assert a["documenten"]["mengverhouding"]["waarde"] == "A 3 : B 1 (volumedelen)"
    comp_a = a["componenten"][0]
    assert comp_a["documenten"]["signaalwoord"]["waarde"] == "Waarschuwing"
    assert comp_a["documenten"]["un_code"]["waarde"] == "3082"          # 'UN 3082' -> cijfers
    assert comp_a["documenten"]["ghs"]["waarde"] == ["GHS07", "GHS09"]
    assert comp_a["documenten"]["vlampunt"]["categorie"] == "productdatablad"  # uit 'Vlampunt Component A'
    assert a["documenten"]["kleur"]["waarde"] == "Groen"                # productblad heeft voorkeur voor kleur
    assert comp_a["documenten"]["kleur"]["waarde"] == "Lichtgroen"
    assert a["componenten"][1]["documenten"]["signaalwoord"]["waarde"] == "Gevaar"

    # 2-in-1: alleen de langst passende documenten (de 2-in-1 SDS), niet de losse A/B-bladen.
    s = artikelen["2022205"]
    assert s["documenten"]["signaalwoord"]["bron"] == "Veiligheidsblad DRY FLEX 4 2-in-1.pdf"
    assert "documenten" not in s["componenten"][0]

    assert "documenten" not in artikelen["2021005"]                     # 'DRY FLEX 1' matcht niet op 'DRY FLEX 16'
    assert "documenten" not in artikelen["4513032"]

    assert len(meldingen) == 1 and meldingen[0].startswith("2023005 component A: un_code in PDS '3082'")


def test_waarde_uit_documenten(artikelen):
    koppel_documenten(artikelen, KENNISBANK)
    ad = Artikeldata({"artikelen": artikelen, "ruwe_kolommen": []})
    a = artikelen["2022005"]
    w = ad.waarde(a, "signaalwoord")
    assert w.waarde == "Waarschuwing"
    assert w.bron.startswith("Veiligheidsblad DRY FLEX 4 - component A.pdf, component A")
    assert w.regel == "ook B: Gevaar"
    w = ad.waarde(a, "un_code")                                          # PDS gaat vóór het veiligheidsblad
    assert w.waarde == "3082" and w.bron.startswith("Product Data Sheet, component A")
    w = ad.waarde(a, "verwerkingstijd")
    assert w.waarde == "20 - 25 minuten" and w.bron == "Productsheet DRY FLEX 4.pdf" and w.regel is None
    # Productbladwaarde op artikelniveau gaat vóór de SDS-waarde per component (kleur: Groen, niet Lichtgroen).
    w = ad.waarde(a, "kleur")
    assert w.waarde == "Groen" and w.bron == "Productsheet DRY FLEX 4.pdf" and w.regel is None
    assert ad.waarde(a, "ghs").waarde == "GHS07, GHS09"
    assert ad.waarde(artikelen["4513032"], "signaalwoord") is None
    s = artikelen["2022205"]
    assert ad.waarde(s, "signaalwoord").waarde == "Gevaar"


def test_los_component_artikel_krijgt_alleen_eigen_blad():
    artikelen = {
        "ZD2210A": _art("ZD2210A", "DRY FLEX 4 component A", [("A", {})]),
        "ZD2210B": _art("ZD2210B", "DRY FLEX 4 component B", [("B", {})]),
    }
    koppel_documenten(artikelen, KENNISBANK)
    a = artikelen["ZD2210A"]
    assert [c["naam"] for c in a["componenten"]] == ["A"]
    assert a["componenten"][0]["documenten"]["signaalwoord"]["waarde"] == "Waarschuwing"
    assert "vlampunt" in a["componenten"][0]["documenten"]          # 'Vlampunt Component A' uit het productblad
    b = artikelen["ZD2210B"]
    assert [c["naam"] for c in b["componenten"]] == ["B"]
    assert b["componenten"][0]["documenten"]["signaalwoord"]["waarde"] == "Gevaar"
    ad = Artikeldata({"artikelen": artikelen, "ruwe_kolommen": []})
    assert ad.waarde(a, "signaalwoord").regel is None                # geen 'ook B: ...'


def test_vergelijking_schoont_beide_kanten():
    artikelen = {"2023005": _art("2023005", "DRY FLEX 1", [("A", {"un_code": "UN 9999"}), ("B", {})])}
    _, meldingen = koppel_documenten(artikelen, KENNISBANK)
    assert meldingen == []                                            # 'UN 9999' == '9999' na opschonen
