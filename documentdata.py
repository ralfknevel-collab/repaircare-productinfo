"""
Koppelt product- en veiligheidsbladen uit kennisbank.json aan artikelen.

De kennisbank (gemaakt door ingest.py uit de PDF's) bevat per document losse
specs met wisselende veldnamen ("Vlampunt Component A", "Potlife/verwerkingstijd
DRY FIX UNI"). Dit module:
1. matcht documenten op artikelen via de productnaam (langste passende naam wint),
2. normaliseert de veldnamen naar vaste doelvelden uit de veldcatalogus,
3. zet de waarden op artikel- of componentniveau onder "documenten",
4. meldt afwijkingen tussen veiligheidsblad en Product Data Sheet (UN, klasse, groep).
"""

from __future__ import annotations

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
KENNISBANK_FILE = BASE_DIR / "kennisbank.json"
CATEGORIEEN = ("veiligheidsblad", "productdatablad")

# (regex op de opgeschoonde veldnaam, veld-id). Eerste treffer wint.
NORMALISATIE = [
    (r"signaalwoord", "signaalwoord"),
    (r"pictogram", "ghs"),
    (r"\beuh", "euh_zinnen"),
    (r"h-zinnen|gevarenaanduiding", "h_zinnen"),
    (r"gevarenklassen", "gevarenklassen"),
    (r"un-?nummer", "un_code"),
    (r"transportgevarenklasse|transportklasse|adr-klasse", "klasse"),
    (r"verpakkingsgroep", "verpakkingsgroep"),
    (r"classificatiecode", "adr_classificatiecode"),
    (r"kemler", "kemler"),
    (r"vlampunt", "vlampunt"),
    (r"dichtheid", "dichtheid"),
    (r"vos-gehalte|voc-gehalte", "voc"),
    (r"opslagtemperatuur|opslag/vervoer", "opslagtemperatuur"),
    (r"^kleur", "kleur"),
    (r"eural|eal-afvalcode|europese afval", "eural_code"),
    (r"verwerkingstemperatuur|toepassingstemperatuur", "verwerkingstemperatuur"),
    (r"verwerkingstijd|potlife", "verwerkingstijd"),
    (r"uitharding|overschilderbaar|doorharding", "uitharding"),
    (r"mengverhouding", "mengverhouding"),
    (r"laagdikte", "laagdikte"),
    (r"vaste stofgehalte", "vaste_stofgehalte"),
    (r"komo|certificering", "certificaat"),
    (r"verpakkingseenheid", "verpakkingseenheid"),
    (r"^verpakking\b", "verpakking"),
    (r"verbruik", "verbruik"),
    (r"biobased", "biobased_gehalte"),
    (r"milieugevaarlijk", "milieugevaarlijk"),
    (r"^versie", "sds_versie"),
    (r"datum herziening|herzieningsdatum", "sds_datum"),
]
# Velden waarvoor het productblad de voorkeur heeft boven het veiligheidsblad.
VOORKEUR_PRODUCTBLAD = {
    "verwerkingstijd", "verwerkingstemperatuur", "uitharding", "mengverhouding", "laagdikte",
    "vaste_stofgehalte", "certificaat", "verpakking", "verpakkingseenheid", "verbruik",
    "dichtheid", "kleur", "biobased_gehalte", "opslagtemperatuur",
}
VERGELIJK_MET_PDS = ("un_code", "klasse", "verpakkingsgroep")

_COMPONENT = re.compile(r"(?:component|comp\.?)\s*([AB])\b", re.I)
_LOSSE_LETTER = re.compile(r"(?<![\w-])([AB])(?![\w-])")


def normaliseer_veld(naam: str, productnamen: list[str] = ()) -> tuple[str | None, str | None]:
    """Veldnaam uit de kennisbank -> (veld-id, component 'A'/'B' of None).

    'Vlampunt Component A' -> ('vlampunt', 'A'); 'Verwerkingstijd bij 20°C (BIO FLEX)'
    -> ('verwerkingstijd', None); 'Vlampunt DRY FIX UNI A en B' -> ('vlampunt', None).
    """
    tekst = naam
    letters = {m.group(1).upper() for m in _COMPONENT.finditer(tekst)}
    schoon = _COMPONENT.sub(" ", tekst)
    schoon = re.sub(r"\([^)]*\)", " ", schoon)
    for p in sorted(productnamen, key=len, reverse=True):
        schoon = re.sub(re.escape(p), " ", schoon, flags=re.I)
    letters |= {m.group(1) for m in _LOSSE_LETTER.finditer(schoon)}
    schoon = _LOSSE_LETTER.sub(" ", schoon)
    schoon = " ".join(schoon.replace(" - ", " ").split()).strip(" -").casefold()
    component = letters.pop() if len(letters) == 1 else None
    for patroon, veld_id in NORMALISATIE:
        if re.search(patroon, schoon):
            return veld_id, component
    return None, None


def _tokens(naam: str) -> list[str]:
    s = str(naam or "").replace("®", "").casefold().split(" / ")[0]
    s = re.sub(r"\b\d+\s*ml\b", " ", s)
    return s.split()


def _schoon_waarde(veld_id: str, waarde) -> object:
    tekst = " ".join(str(waarde).split())
    if veld_id == "un_code":
        # 'UN 3082' of 'UN 3082, klasse 9' -> '3082' (UN-nummers zijn vier cijfers)
        m = re.search(r"\b(\d{4})\b", tekst)
        return m.group(1) if m else tekst
    if veld_id == "klasse":
        # '8, verpakkingsgroep II' -> '8'; '4.1' blijft '4.1'
        m = re.match(r"\s*(\d(?:\.\d)?)\b", tekst)
        return m.group(1) if m else tekst
    if veld_id == "verpakkingsgroep":
        m = re.search(r"\b(I{1,3})\b", tekst)
        return m.group(1) if m else tekst
    if veld_id == "ghs":
        codes = re.findall(r"GHS\s*0?(\d)", tekst, re.I)
        return [f"GHS0{c}" for c in codes] if codes else tekst
    return tekst


def _houder(artikel: dict, naam: str) -> dict:
    for c in artikel.setdefault("componenten", []):
        if c["naam"] == naam:
            return c
    c = {"naam": naam, "ruw": {}}
    artikel["componenten"].append(c)
    return c


def _zet_document(houder: dict, veld_id: str, waarde, doc: dict) -> None:
    docs = houder.setdefault("documenten", {})
    bestaand = docs.get(veld_id)
    if bestaand:
        wil_productblad = veld_id in VOORKEUR_PRODUCTBLAD
        heeft_voorkeur = (bestaand["categorie"] == "productdatablad") == wil_productblad
        if heeft_voorkeur or bestaand["categorie"] == doc["categorie"]:
            return
    docs[veld_id] = {"waarde": _schoon_waarde(veld_id, waarde), "bron": doc.get("bestand", "?"),
                     "categorie": doc["categorie"]}


def _verwerk_document(artikel: dict, doc: dict, productnamen: list[str]) -> None:
    doc_component = doc.get("component") if doc.get("component") in ("A", "B") else None
    for spec in doc.get("specs", []):
        veld_id, naam_component = normaliseer_veld(str(spec.get("veld", "")), productnamen)
        if not veld_id or spec.get("waarde") in (None, ""):
            continue
        component = naam_component or doc_component
        houder = _houder(artikel, component) if component else artikel
        _zet_document(houder, veld_id, spec["waarde"], doc)


def _vergelijk(artikel: dict) -> list[str]:
    meldingen = []
    for houder in [artikel] + artikel.get("componenten", []):
        docs = houder.get("documenten", {})
        for veld_id in VERGELIJK_MET_PDS:
            if veld_id in houder and veld_id in docs:
                pds = " ".join(str(houder[veld_id]).split()).casefold()
                sds = " ".join(str(docs[veld_id]["waarde"]).split()).casefold()
                if pds != sds:
                    waar = f"component {houder['naam']}" if "naam" in houder else "artikel"
                    meldingen.append(f"{artikel['artikelcode']} {waar}: {veld_id} in PDS '{houder[veld_id]}' "
                                     f"maar in {docs[veld_id]['bron']} '{docs[veld_id]['waarde']}'")
    return meldingen


def koppel_documenten(artikelen: dict[str, dict], kennisbank: list[dict]) -> tuple[int, list[str]]:
    """Verrijk artikelen in-place met documentwaarden. Geeft (aantal gekoppelde artikelen, meldingen)."""
    docs = [d for d in kennisbank if d.get("categorie") in CATEGORIEEN]
    productnamen = sorted({str(d.get("product", "")) for d in docs if d.get("product")}, key=len, reverse=True)
    gekoppeld = 0
    meldingen: list[str] = []
    for artikel in artikelen.values():
        art_tokens = _tokens(artikel.get("omschrijving", ""))
        beste, passend = 0, []
        for d in docs:
            dt = _tokens(d.get("product", ""))
            if dt and art_tokens[:len(dt)] == dt:
                if len(dt) > beste:
                    beste, passend = len(dt), [d]
                elif len(dt) == beste:
                    passend.append(d)
        if not passend:
            continue
        gekoppeld += 1
        for d in sorted(passend, key=lambda d: d["categorie"] != "veiligheidsblad"):
            _verwerk_document(artikel, d, productnamen)
        meldingen.extend(_vergelijk(artikel))
    return gekoppeld, meldingen
