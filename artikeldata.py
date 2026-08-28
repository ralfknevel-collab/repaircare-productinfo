"""
Toegang tot artikeldata.json en vaste_waarden.json: artikel zoeken op
artikelcode, EAN of omschrijving, en per doelveld de waarde met bron en
rekenregel teruggeven.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from veldcatalogus import veld

FUZZY_DREMPEL = 0.85
BASE_DIR = Path(__file__).resolve().parent
ARTIKELDATA_FILE = BASE_DIR / "artikeldata.json"
VASTE_WAARDEN_FILE = BASE_DIR / "vaste_waarden.json"


@dataclass
class Match:
    artikel: dict
    via: str      # artikelcode | ean | omschrijving
    score: float  # 1.0 bij exacte match


@dataclass
class Waarde:
    waarde: object
    eenheid: str | None
    bron: str
    regel: str | None = None


def normaliseer_code(x) -> str | None:
    if x is None:
        return None
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    s = str(x).strip()
    if s == "" or s == "0":
        return None
    return s


def normaliseer_ean(x) -> str | None:
    if x is None:
        return None
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    cijfers = re.sub(r"\D", "", str(x))
    return cijfers if len(cijfers) in (8, 13) else None


def _normaliseer_tekst(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def vaste_waarde(vaste: dict, sleutel: str, artikelcode: str) -> str | None:
    regel = vaste.get(sleutel)
    if not regel:
        return None
    per_artikel = regel.get("per_artikel") or {}
    if artikelcode in per_artikel:
        return per_artikel[artikelcode]
    per_prefix = regel.get("per_prefix") or {}
    for prefix in sorted(per_prefix, key=len, reverse=True):
        if artikelcode.startswith(prefix):
            return per_prefix[prefix]
    return regel.get("standaard")


# veld-id -> (artikelsleutel, eenheid, regelsleutel)
_ARTIKELVELDEN = {
    "gn_code": ("gn_code", None, None),
    "netto_gewicht": ("netto_g", "g", "netto_regel"),
    "bruto_gewicht": ("bruto_g", "g", "bruto_regel"),
    "ean": ("ean", None, None),
    "omschrijving": ("omschrijving", None, None),
    "min_verkoophoeveelheid": ("min_verkoophoeveelheid", "stuks", None),
}
_MAATVELDEN = {
    "lengte": ("maat_mm", "l"), "breedte": ("maat_mm", "b"), "hoogte": ("maat_mm", "h"),
    "collo_lengte": ("collo_mm", "l"), "collo_breedte": ("collo_mm", "b"), "collo_hoogte": ("collo_mm", "h"),
}
_COMPONENTVELDEN = {"un_code", "klasse", "verpakkingsgroep", "adr_naam", "vlampunt", "ufi", "voc", "ghs"}


class Artikeldata:
    def __init__(self, data: dict, vaste_waarden: dict | None = None):
        self.artikelen: dict[str, dict] = data["artikelen"]
        self.ruwe_kolommen: list[str] = list(data.get("ruwe_kolommen", []))
        self.vaste: dict = vaste_waarden or {}
        self.vaste_sleutels: dict[str, str] = {k: v.get("label", k) for k, v in self.vaste.items()}
        self._op_ean = {a["ean"]: a for a in self.artikelen.values() if a.get("ean")}
        self._omschrijvingen = {_normaliseer_tekst(a["omschrijving"]): a
                                for a in self.artikelen.values() if a.get("omschrijving")}

    @classmethod
    def laad(cls, pad_json: Path | None = None, pad_vast: Path | None = None) -> "Artikeldata":
        # Defaults hier oplossen (niet in de signatuur) zodat tests de module-constanten kunnen vervangen.
        pad_json = pad_json or ARTIKELDATA_FILE
        pad_vast = pad_vast or VASTE_WAARDEN_FILE
        data = json.loads(Path(pad_json).read_text(encoding="utf-8"))
        vaste = None
        if Path(pad_vast).exists():
            vaste = json.loads(Path(pad_vast).read_text(encoding="utf-8"))
        return cls(data, vaste)

    def zoek(self, artikelcode=None, ean=None, omschrijving=None) -> Match | None:
        code = normaliseer_code(artikelcode)
        if code and code in self.artikelen:
            return Match(self.artikelen[code], "artikelcode", 1.0)
        e = normaliseer_ean(ean)
        if e and e in self._op_ean:
            return Match(self._op_ean[e], "ean", 1.0)
        if omschrijving:
            doel = _normaliseer_tekst(str(omschrijving))
            if doel:
                kandidaten = difflib.get_close_matches(doel, self._omschrijvingen.keys(), n=1, cutoff=FUZZY_DREMPEL)
                if kandidaten:
                    score = difflib.SequenceMatcher(None, doel, kandidaten[0]).ratio()
                    return Match(self._omschrijvingen[kandidaten[0]], "omschrijving", score)
        return None

    def waarde(self, artikel: dict, veld_id: str) -> Waarde | None:
        v = veld(veld_id)
        if v is None or v.soort in ("geen", "sleutel"):
            return None
        code = artikel.get("artikelcode", "")
        if v.soort == "ruw":
            w = artikel.get("ruw", {}).get(v.label)
            return Waarde(w, None, "Product Data Sheet, kolom " + v.label) if w is not None else None
        if v.soort == "vast":
            w = vaste_waarde(self.vaste, v.label, code)
            return Waarde(w, None, "vaste_waarden.json: " + v.label) if w is not None else None
        if veld_id in _ARTIKELVELDEN:
            sleutel, eenheid, regelsleutel = _ARTIKELVELDEN[veld_id]
            if sleutel not in artikel:
                return None
            return Waarde(artikel[sleutel], eenheid, "Product Data Sheet",
                          artikel.get(regelsleutel) if regelsleutel else None)
        if veld_id in _MAATVELDEN:
            maatsleutel, as_ = _MAATVELDEN[veld_id]
            maat = artikel.get(maatsleutel)
            if not maat or as_ not in maat:
                return None
            regel = maat.get("regel")
            if maat.get("vorm") == "rond" and as_ in ("l", "b"):
                regel = f"ronde verpakking: L = B = Ø {maat['diameter']:g} mm"
            return Waarde(maat[as_], "mm", "Product Data Sheet", regel)
        if veld_id in _COMPONENTVELDEN:
            bronnen = [(artikel, "Product Data Sheet")] + [
                (c, f"Product Data Sheet, component {c['naam']}") for c in artikel.get("componenten", [])]
            for houder, bron in bronnen:
                if veld_id in houder:
                    w = houder[veld_id]
                    if isinstance(w, list):
                        w = ", ".join(w)
                    return Waarde(w, None, bron)
            return None
        return None
