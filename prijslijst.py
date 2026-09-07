"""Lees de aanvullende Repair Care-adviesprijslijst met controleerbare prijsbasis."""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def _tekst(waarde: str) -> str:
    return " ".join(waarde.strip().replace("’", "'").split()).casefold()


def _datum(waarde: str) -> str:
    try:
        return datetime.strptime(waarde, "%d-%m-%Y").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Ongeldige datum in adviesprijslijst: {waarde}.") from exc


def _lees_regels(pad: Path) -> list[tuple[int, list[str]]]:
    inhoud = pad.read_bytes()
    try:
        tekst = inhoud.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            tekst = inhoud.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise ValueError("De tekencodering van de adviesprijslijst is niet leesbaar.") from exc
    lezer = csv.reader(io.StringIO(tekst, newline=""), strict=True)
    regels = []
    try:
        while True:
            nummer = lezer.line_num + 1
            try:
                rij = next(lezer)
            except StopIteration:
                break
            regels.append((nummer, [cel.strip() for cel in rij]))
    except csv.Error as exc:
        raise ValueError(f"Ongeldige CSV-indeling bij regel {lezer.line_num}.") from exc
    return regels


def _metadata(regels: list[tuple[int, list[str]]]) -> tuple[dict, int]:
    titels, koppen, prijzen, geldigheden = [], [], [], []
    verwacht = ["artikel", "omschrijving", "eancode", "ve", "eenheid", "vk/st€"]
    for nummer, rij in regels:
        if not rij:
            continue
        eerste = _tekst(rij[0])
        if eerste.startswith("verkoopadviesprijzen"):
            titels.append(eerste)
        if eerste == "artikel":
            koppen.append((nummer, [re.sub(r"\s+", "", _tekst(cel)) for cel in rij[:6]]))
        if eerste == "prijzen":
            prijzen.append(_tekst(rij[1]) if len(rij) > 1 else "")
        if eerste == "geldigheid":
            geldigheden.append(_tekst(rij[1]) if len(rij) > 1 else "")

    if len(titels) != 1 or len(koppen) != 1 or len(prijzen) != 1 or len(geldigheden) != 1:
        raise ValueError("De adviesprijslijst mist unieke koppen, prijsvoorwaarden of geldigheidsdatums.")
    if koppen[0][1] != verwacht:
        raise ValueError("De kolommen van de adviesprijslijst worden niet herkend.")
    titel = re.fullmatch(r"verkoopadviesprijzen per (\d{2}-\d{2}-\d{4})", titels[0])
    periode = re.fullmatch(
        r"voor leveringen tussen (\d{2}-\d{2}-\d{4}) en (\d{2}-\d{2}-\d{4}), tot nader order",
        geldigheden[0],
    )
    if not titel or not periode:
        raise ValueError("De geldigheidsperiode van de adviesprijslijst is niet eenduidig.")
    if not re.fullmatch(r"in euro's excl\.\s*btw, per stuk resp\.\s*per set", prijzen[0]):
        raise ValueError("Alleen adviesprijzen in euro's exclusief btw per stuk of set worden ondersteund.")
    vanaf, tot = _datum(periode[1]), _datum(periode[2])
    if vanaf > tot or _datum(titel[1]) != vanaf:
        raise ValueError("De datums in titel en geldigheidsvoorwaarden spreken elkaar tegen.")
    return {
        "geldig_vanaf": vanaf, "geldig_tot": tot, "valuta": "EUR", "btw": "exclusief",
    }, koppen[0][0]


def _ean(waarde: str) -> str | None:
    if not waarde or _tekst(waarde).startswith("doorberekenen aan deelnemer "):
        return None
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", waarde):
        raise ValueError("EAN bevat geen herkenbare EAN-13.")
    cijfers = waarde.replace(".", "")
    if len(cijfers) != 13 or sum(int(cijfer) * (1 if i % 2 == 0 else 3)
                                for i, cijfer in enumerate(cijfers)) % 10:
        raise ValueError("EAN heeft een ongeldige lengte of controlecijfer.")
    return cijfers


def _prijs_cent(waarde: str) -> int:
    # Deze export gebruikt een decimale punt en eventueel komma's voor duizendtallen.
    match = re.fullmatch(r"€\s*((?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)\.[0-9]{2})", waarde)
    if not match:
        raise ValueError("Adviesprijs is geen herkenbaar niet-negatief eurobedrag met twee decimalen.")
    return int(Decimal(match[1].replace(",", "")) * 100)


def lees_prijslijst(pad: Path) -> dict:
    """Geef brongegevens terug; ongeldige rijen krijgen een melding, geen geschatte waarden."""
    pad = Path(pad)
    regels = _lees_regels(pad)
    metadata, kopregel = _metadata(regels)
    artikelen, meldingen = {}, []
    codes = defaultdict(list)
    eans = defaultdict(set)

    for nummer, rij in regels:
        if nummer <= kopregel or not rij or not any(rij):
            continue
        code = rij[0]
        if _tekst(code) in {"condities", "prijzen", "geldigheid"}:
            continue
        if not re.fullmatch(r"[0-9]+", code):
            if any(rij[1:]):
                meldingen.append(f"Regel {nummer} overgeslagen: geen herkenbaar artikelnummer.")
            continue
        codes[code].append(nummer)
        try:
            if len(rij) < 6 or any(rij[6:]):
                raise ValueError("Onvolledige of onverwachte artikelkolommen.")
            omschrijving, ean_tekst, ve, eenheid, prijs = rij[1:6]
            ean = _ean(ean_tekst)
            if ean:
                eans[ean].add(code)
            if not omschrijving or omschrijving.startswith(("=", "+", "-", "@")) or "\x00" in omschrijving:
                raise ValueError("Omschrijving is leeg of lijkt op een formule.")
            if not re.fullmatch(r"[1-9][0-9]*", ve):
                raise ValueError("VE is geen positief geheel aantal.")
            if eenheid not in {"st", "set"}:
                raise ValueError("Verkoopeenheid is niet 'st' of 'set'.")
            centen = _prijs_cent(prijs)
        except ValueError as exc:
            meldingen.append(f"Artikel {code}, regel {nummer}, overgeslagen: {exc}")
            continue
        if ean is None:
            meldingen.append(f"Artikel {code}, regel {nummer}: geen EAN beschikbaar; alleen koppelen op artikelnummer.")
        artikelen[code] = {
            "omschrijving": omschrijving, "ean": ean, "ve_aantal": int(ve),
            "eenheid": eenheid, "adviesprijs_cent": centen, "bronregel": nummer,
        }

    # Ook een ongeldige tweede regel mag niet stilzwijgend een eerste regel laten winnen.
    conflicten = set()
    for code, nummers in codes.items():
        if len(nummers) > 1:
            conflicten.add(code)
            meldingen.append(f"Artikel {code} staat dubbel op regels {', '.join(map(str, nummers))}; niet gebruikt.")
    for ean, eigenaars in eans.items():
        if len(eigenaars) > 1:
            conflicten.update(eigenaars)
            meldingen.append(f"EAN {ean} hoort bij meerdere artikelnummers ({', '.join(sorted(eigenaars))}); niet gebruikt.")
    for code in conflicten:
        artikelen.pop(code, None)
    return {"bron": pad.name, **metadata, "artikelen": artikelen, "meldingen": meldingen}
