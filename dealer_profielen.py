"""Bewaar expliciet gekozen eenheden lokaal per dealer en werkbladformaat."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROFIEL_MAP = BASE_DIR / ".dealer_profielen"


def _normaliseer_kop(waarde) -> str:
    tekst = "" if waarde is None else str(waarde)
    return " ".join(unicodedata.normalize("NFC", tekst).split()).casefold()


def _bestandsstam(bestandsnaam: str) -> str:
    stam = Path(bestandsnaam).stem
    while True:
        zonder_suffix = re.sub(r"(?:_ingevuld|_controle)(?:-\d+)?$", "", stam)
        if zonder_suffix == stam:
            return stam
        stam = zonder_suffix


def profielsleutel(ws, kopregel_index: int, bestandsnaam: str) -> str:
    """Gebruik ruwe kolomvolgorde en dealeridentiteit, nooit productinhoud of gokwerk."""
    koppen = [_normaliseer_kop(cel.value) for cel in ws[kopregel_index + 1]]
    leverancierskolommen = [i + 1 for i, kop in enumerate(koppen) if kop == "primärlieferant"]
    if leverancierskolommen:
        leveranciers = set()
        for rij in ws.iter_rows(min_row=kopregel_index + 2, values_only=True):
            for kolom in leverancierskolommen:
                waarde = rij[kolom - 1]
                if waarde is not None:
                    tekst = unicodedata.normalize("NFC", str(waarde)).strip()
                    if tekst:
                        leveranciers.add(tekst)
        identiteit = {"primärlieferant": sorted(leveranciers)}
        if not leveranciers:
            identiteit["bestandsstam"] = _bestandsstam(bestandsnaam)
    else:
        identiteit = {"bestandsstam": _bestandsstam(bestandsnaam)}
    inhoud = {"koppen": koppen, "tabblad": ws.title, "dealer": identiteit}
    gecodeerd = json.dumps(inhoud, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(gecodeerd.encode("utf-8")).hexdigest()


def _profielpad(sleutel: str) -> Path:
    if not isinstance(sleutel, str) or re.fullmatch(r"[0-9a-f]{64}", sleutel) is None:
        raise ValueError("Ongeldige dealersleutel; verwacht een SHA-256-code.")
    return PROFIEL_MAP / f"{sleutel}.json"


def _valideer_profiel(profiel) -> dict:
    if not isinstance(profiel, dict) or set(profiel) != {"maat_eenheid", "gewicht_eenheid"}:
        raise ValueError("Het dealerprofiel heeft een ongeldig formaat.")
    if profiel["maat_eenheid"] not in (None, "mm", "cm", "m"):
        raise ValueError("Het dealerprofiel heeft een ongeldige maateenheid.")
    if profiel["gewicht_eenheid"] not in (None, "g", "kg"):
        raise ValueError("Het dealerprofiel heeft een ongeldige gewichtseenheid.")
    return profiel


def laad_profiel(sleutel: str) -> dict | None:
    """Alleen een ontbrekend bestand is normaal; lees- en inhoudsfouten blijven zichtbaar."""
    pad = _profielpad(sleutel)
    try:
        inhoud = pad.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return _valideer_profiel(json.loads(inhoud))


def bewaar_profiel(sleutel: str, maat_eenheid: str | None, gewicht_eenheid: str | None) -> None:
    """Vervang één profiel atomisch, zodat andere profielen en vorige keuzes intact blijven."""
    pad = _profielpad(sleutel)
    profiel = _valideer_profiel({"maat_eenheid": maat_eenheid, "gewicht_eenheid": gewicht_eenheid})
    PROFIEL_MAP.mkdir(parents=True, exist_ok=True)
    tijdelijk_pad = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=PROFIEL_MAP, prefix=f".{sleutel}.", suffix=".tmp", delete=False,
        ) as tijdelijk:
            tijdelijk_pad = Path(tijdelijk.name)
            json.dump(profiel, tijdelijk, ensure_ascii=False)
            tijdelijk.write("\n")
        os.replace(tijdelijk_pad, pad)
    finally:
        if tijdelijk_pad is not None:
            tijdelijk_pad.unlink(missing_ok=True)
