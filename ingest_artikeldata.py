"""
Zet het Product Data Sheet (Excel) om naar artikeldata.json: gestructureerde
productdata per artikelcode, met componenten (A/B) apart én opgeteld.

Gebruik:
    python3 ingest_artikeldata.py

Gebruikt geen API. Opnieuw draaien overschrijft artikeldata.json.
"""

from __future__ import annotations

import re

LEEG = {"", "--", "-", "n.v.t.", "nvt", "inapplicable", "none"}

_GETAL = re.compile(r"-?\d+(?:[.,]\d+)?")
_PREFIX = re.compile(r"^([AB])\s*:\s*(.*)$", re.S)
_BLOK = re.compile(r"^(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)$")
_ROND = re.compile(r"Ø\s*:?\s*(\d+(?:[.,]\d+)?)\s*H\s*:?\s*(\d+(?:[.,]\d+)?)")


def normaliseer_kop(tekst) -> str:
    """Vouw alle whitespace samen tot één spatie en trim."""
    return " ".join(str(tekst).split()) if tekst is not None else ""


def alleen_cijfers(tekst) -> str:
    return re.sub(r"\D", "", str(tekst)) if tekst is not None else ""


def split_prefix(tekst: str) -> tuple[str | None, str]:
    """Haal een componentprefix 'A:'/'B:' van de tekst af."""
    schoon = normaliseer_kop(tekst)
    m = _PREFIX.match(schoon)
    if not m:
        return None, schoon
    return m.group(1), normaliseer_kop(m.group(2))


def parse_getal(tekst) -> float | None:
    """Eerste getal in de tekst als float; komma als decimaalteken toegestaan."""
    if tekst is None:
        return None
    if isinstance(tekst, (int, float)):
        return float(tekst)
    _, rest = split_prefix(str(tekst))
    if rest.lower() in LEEG:
        return None
    m = _GETAL.search(rest)
    if not m:
        return None
    return float(m.group(0).replace(",", "."))


def parse_maat(tekst) -> dict | None:
    """'262x290x242' -> blok; 'Ø: 48 H: 184' -> rond (l = b = diameter)."""
    if tekst is None:
        return None
    _, schoon = split_prefix(str(tekst))
    if schoon.lower() in LEEG:
        return None
    m = _BLOK.match(schoon)
    if m:
        l, b, h = (float(x.replace(",", ".")) for x in m.groups())
        return {"vorm": "blok", "l": l, "b": b, "h": h}
    m = _ROND.search(schoon)
    if m:
        d, h = (float(x.replace(",", ".")) for x in m.groups())
        return {"vorm": "rond", "diameter": d, "hoogte": h, "l": d, "b": d, "h": h}
    return None


def combineer_maat(maten: list[dict]) -> dict | None:
    """Maat van een verkoopeenheid uit componentmaten: naast elkaar gezet."""
    if not maten:
        return None
    if len(maten) == 1:
        return dict(maten[0])
    delen = " + ".join(f"{m['l']:g}" for m in maten)
    return {
        "vorm": "samengesteld",
        "l": sum(m["l"] for m in maten),
        "b": max(m["b"] for m in maten),
        "h": max(m["h"] for m in maten),
        "regel": f"componenten naast elkaar: L = {delen}, B en H = grootste component",
    }
