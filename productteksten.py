"""Gecontroleerde Duitse productteksten, gekoppeld aan de exacte Nederlandse bron."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import replace
from pathlib import Path

from artikeldata import Waarde


_DATA = Path(__file__).resolve().parent / "data"
_PADEN = (_DATA / "productomschrijvingen_de.json", _DATA / "productvelden_de.json")
_VELDEN = frozenset({
    "omschrijving", "prijslijst_omschrijving", "kleur", "verpakking", "verpakkingseenheid",
    "verwerkingstijd", "uitharding", "verbruik", "opslagtemperatuur", "verwerkingstemperatuur",
    "mengverhouding", "dichtheid", "laagdikte", "vaste_stofgehalte", "biobased_gehalte",
})
_GETALLEN = re.compile(r"[+-]?[0-9]+(?:[.,][0-9]+)?")
_EENHEDEN = re.compile(
    r"(?<![A-Za-zÀ-ÿ])(?:°C|ºC|kg|mg|ml|cl|dl|mm|cm|dm|mtr\.?|g|l|m|(?<!\.)V|%)(?:[²³])?(?![A-Za-zÀ-ÿ])"
)
_MERKEN = re.compile(
    r"\b(?:DRY (?:FIX|FLEX|SEAL|SHIELD)|BIO FLEX|EASY[ •]Q|EAZYFIX|Repair Care|REPAIR CARE)"
    r"(?:[®™])?(?: (?:UNI|ALLROUND|COOL|MP|SK|IN|SF|WIPES|BOX))?(?!\w)|\w+[®™]"
)
_CODES = re.compile(r"\b[A-Z]+[0-9]+[A-Z]?\b")
_TEMPERATUURBEGIN = re.compile(
    r"[+-][0-9]+(?:[.,][0-9]+)?\s*"
    r"(?:(?:bis|tot|t/m|[-–])\s*[+-]?[0-9]+(?:[.,][0-9]+)?\s*)?[°º]C\b"
)


class VertalingOntbreekt(ValueError):
    """De bronwaarde heeft geen aantoonbaar bruikbare Duitse vertaling."""


def _veldnaam(veld_id: str) -> str:
    return "omschrijving" if veld_id == "prijslijst_omschrijving" else veld_id


def _samenvoegen(doel: dict, velden: dict) -> None:
    """Valideer de tabelstructuur en weiger conflicterende bronkoppelingen."""
    if not isinstance(velden, dict):
        raise ValueError("Vertaalcatalogus: 'velden' moet een tabel zijn.")
    for veld_id, vertalingen in velden.items():
        if veld_id not in _VELDEN or not isinstance(vertalingen, dict):
            raise ValueError(f"Vertaalcatalogus: ongeldige veldtabel {veld_id!r}.")
        tabel = doel.setdefault(_veldnaam(veld_id), {})
        for bron, duits in vertalingen.items():
            if not isinstance(bron, str) or not bron.strip() or not isinstance(duits, str):
                raise ValueError(f"Vertaalcatalogus: bron en vertaling voor {veld_id} moeten tekst zijn.")
            if bron in tabel and tabel[bron] != duits:
                raise ValueError(f"Vertaalcatalogus: tegenstrijdige vertalingen voor {veld_id}, {bron!r}.")
            tabel[bron] = duits


def _zonder_dubbele_sleutels(paren: list) -> dict:
    resultaat = {}
    for sleutel, inhoud in paren:
        if sleutel in resultaat:
            raise ValueError(f"Vertaalcatalogus: dubbele JSON-sleutel {sleutel!r}.")
        resultaat[sleutel] = inhoud
    return resultaat


def _ongeldige_vertaling(bron: str, duits: str, veld_id: str) -> str | None:
    """Behoud getallen, technische eenheden en herkenbare productidentiteit."""
    if not duits.strip():
        return "de vertaling is leeg"
    if any(unicodedata.category(teken) in {"Cc", "Cf"} for teken in duits):
        return "de vertaling bevat verborgen of besturingstekens"
    begin = duits.lstrip()
    if begin.startswith(("=", "@")):
        return "de vertaling begint als een Excel-formule"
    if begin.startswith(("+", "-")):
        # Een getekende temperatuur is gewone producttekst; andere formules niet.
        temperatuur = veld_id in {"opslagtemperatuur", "verwerkingstemperatuur"}
        if not temperatuur or not _TEMPERATUURBEGIN.match(begin):
            return "de vertaling begint als een Excel-formule"
    if _GETALLEN.findall(bron) != _GETALLEN.findall(duits):
        return "getallen of hun tekens wijken af van de bron"
    if Counter(_EENHEDEN.findall(bron)) != Counter(_EENHEDEN.findall(duits)):
        return "technische eenheden wijken af van de bron"
    if Counter(_MERKEN.findall(bron)) != Counter(_MERKEN.findall(duits)):
        return "merk of productfamilie wijkt af van de bron"
    if Counter(_CODES.findall(bron)) != Counter(_CODES.findall(duits)):
        return "productcodes wijken af van de bron"
    return None


class Productteksten:
    """Een eigen momentopname van de lokale catalogus, zonder netwerkverzoeken."""

    def __init__(self, velden: dict[str, dict[str, str]], versie: str = "1"):
        if not isinstance(versie, str) or not versie.strip():
            raise ValueError("Vertaalcatalogus: de versie moet niet-lege tekst zijn.")
        self._velden: dict[str, dict[str, str]] = {}
        _samenvoegen(self._velden, velden)
        self._versie = versie
        inhoud = json.dumps({"versie": versie, "velden": self._velden}, sort_keys=True, ensure_ascii=False)
        self._vingerafdruk = hashlib.sha256(inhoud.encode("utf-8")).hexdigest()

    @classmethod
    def laad(cls, paden: tuple[Path, ...] | None = None) -> Productteksten:
        """Lees beide tabellen; kapotte of ontbrekende bestanden blijven zichtbaar."""
        velden: dict[str, dict[str, str]] = {}
        versies = []
        for pad in _PADEN if paden is None else paden:
            try:
                inhoud = json.loads(Path(pad).read_text(encoding="utf-8"), object_pairs_hook=_zonder_dubbele_sleutels)
                if (not isinstance(inhoud, dict) or inhoud.get("taal") != "de"
                        or type(inhoud.get("versie")) is not int or inhoud["versie"] < 1
                        or "velden" not in inhoud):
                    raise ValueError("Vertaalcatalogus: verwacht taal 'de', een positief versienummer en veldtabellen.")
                _samenvoegen(velden, inhoud["velden"])
                versies.append(str(inhoud["versie"]))
            except (OSError, UnicodeError, ValueError) as fout:
                raise ValueError(f"Vertaalcatalogus kon niet worden geladen uit {pad}: {fout}") from fout
        return cls(velden, versie="/".join(versies))

    @property
    def vingerafdruk(self) -> str:
        """Dezelfde tekstinhoud en versie leveren dezelfde cachesleutel op."""
        return self._vingerafdruk

    def vertaal(self, w: Waarde, veld_id: str, taal: str) -> Waarde:
        """Vertaal alleen een exact bekende tekst en behoud alle bronmetadata."""
        if not isinstance(taal, str) or taal not in {"nl", "de"}:
            raise ValueError("Ongeldige taal: kies 'nl' of 'de'.")
        if (taal == "nl" or not isinstance(veld_id, str) or veld_id not in _VELDEN
                or not isinstance(w.waarde, str) or not w.waarde.strip()
                or re.fullmatch(r"\s*[+-]?[0-9]+(?:[.,][0-9]+)?\s*", w.waarde)):
            return w
        veld_id = _veldnaam(veld_id)
        duits = self._velden.get(veld_id, {}).get(w.waarde)
        reden = "geen exacte bronkoppeling beschikbaar" if duits is None else _ongeldige_vertaling(w.waarde, duits, veld_id)
        if reden:
            raise VertalingOntbreekt(f"Duitse vertaling ontbreekt of is onbruikbaar voor {veld_id}: {reden}.")
        herkomst = f"Gecontroleerde vertaling naar de, catalogusversie {self._versie}."
        regel = f"{w.regel} {herkomst}" if w.regel else herkomst
        return replace(w, waarde=duits, regel=regel)
