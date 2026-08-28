"""
Kern van de dealer-Excel invuller (geen Streamlit-code).

Leest een dealerbestand (.xlsx/.csv), vindt de kopregel, matcht artikelen via de
mapping, vult lege cellen met productdata en voegt een tabblad 'Controle' toe.
Ook bruikbaar als script:

    python3 dealer_invuller.py dealerbestand.xlsx [--mapping mapping.json] [--overschrijven]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
import openpyxl
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter

from artikeldata import Artikeldata, Match, Waarde
from mapping import Mapping, lege_mapping, vraag_mapping
from veldcatalogus import catalogus_voor_prompt, converteer, veld

SLEUTELTYPE_ARG = {
    "sleutel_artikelcode": "artikelcode",
    "sleutel_ean": "ean",
    "sleutel_omschrijving": "omschrijving",
}


class _PUNTKOMMA(csv.excel):
    """Fallback-dialect als csv.Sniffer het scheidingsteken niet herkent."""
    delimiter = ";"


GEEL = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
CONTROLE_TAB = "Controle"


def laad_werkboek(inhoud: bytes, bestandsnaam: str) -> openpyxl.Workbook:
    ext = Path(bestandsnaam).suffix.lower()
    if ext == ".xlsx":
        return openpyxl.load_workbook(io.BytesIO(inhoud))
    if ext == ".csv":
        tekst = inhoud.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(tekst[:2000], delimiters=";,\t")
        except csv.Error:
            dialect = _PUNTKOMMA
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        for rij in csv.reader(io.StringIO(tekst), dialect):
            ws.append([c if c != "" else None for c in rij])
        return wb
    raise ValueError(f"Bestandsformaat {ext or '(geen)'} wordt niet ondersteund. Sla het bestand op als .xlsx of .csv.")


def kies_tabblad(wb: openpyxl.Workbook, naam: str | None):
    if naam:
        return wb[naam]
    for ws in wb.worksheets:
        for rij in ws.iter_rows(values_only=True):
            if any(c is not None for c in rij):
                return ws
    return wb.worksheets[0]


def lees_rijen(ws, n: int = 10) -> list[list]:
    uit = []
    for i, rij in enumerate(ws.iter_rows(values_only=True)):
        if i >= n:
            break
        uit.append(list(rij))
    return uit


def vind_kopregel(rijen: list[list]) -> int:
    for i, rij in enumerate(rijen):
        teksten = [c for c in rij if isinstance(c, str) and c.strip()]
        if len(teksten) >= 3:
            return i
    raise ValueError("Geen kopregel gevonden in de eerste rijen (verwacht een rij met minstens 3 tekstkoppen).")


def koppen(ws, kopregel_index: int) -> dict[str, int]:
    rij = next(ws.iter_rows(min_row=kopregel_index + 1, max_row=kopregel_index + 1, values_only=True))
    uit: dict[str, int] = {}
    for i, c in enumerate(rij):
        naam = str(c).strip() if c is not None and str(c).strip() else f"Kolom {get_column_letter(i + 1)}"
        basis, n = naam, 2
        while naam in uit:
            naam = f"{basis} ({n})"
            n += 1
        uit[naam] = i
    return uit


@dataclass
class VeldResultaat:
    kolom: str
    veld_id: str
    waarde: object
    eenheid: str | None
    bron: str
    regel: str | None
    status: str  # ingevuld | leeg | bestaand | controleer


@dataclass
class RijResultaat:
    rij: int                     # 1-based Excel-rijnummer
    sleutel: str
    match: Match | None
    velden: list[VeldResultaat] = field(default_factory=list)


@dataclass
class Rapport:
    rijen: list[RijResultaat]

    def samenvatting(self) -> dict:
        via: dict[str, int] = {}
        gaten_per_kolom: dict[str, int] = {}
        ingevuld = gaten = 0
        for r in self.rijen:
            if r.match:
                via[r.match.via] = via.get(r.match.via, 0) + 1
            for v in r.velden:
                if v.status == "ingevuld":
                    ingevuld += 1
                elif v.status == "leeg":
                    gaten += 1
                    gaten_per_kolom[v.kolom] = gaten_per_kolom.get(v.kolom, 0) + 1
        gevonden = sum(1 for r in self.rijen if r.match)
        return {
            "totaal": len(self.rijen), "gevonden": gevonden, "niet_gevonden": len(self.rijen) - gevonden,
            "via": via, "ingevuld": ingevuld, "gaten": gaten, "gaten_per_kolom": gaten_per_kolom,
        }


def maak_waarde(w: Waarde, eenheid_doel: str | None):
    """Bronwaarde omrekenen naar de gevraagde eenheid; getallen netjes afronden."""
    if isinstance(w.waarde, bool) or not isinstance(w.waarde, (int, float)):
        return w.waarde
    getal = float(w.waarde)
    if w.eenheid and eenheid_doel:
        getal = converteer(getal, w.eenheid, eenheid_doel)
    getal = round(getal, 3)
    return int(getal) if getal.is_integer() else getal


def _is_leeg(cel) -> bool:
    return cel.value is None or (isinstance(cel.value, str) and not cel.value.strip())


def _datarijen(ws, kopregel_index: int):
    for rijnr in range(kopregel_index + 2, ws.max_row + 1):
        cellen = ws[rijnr]
        if any(not _is_leeg(c) for c in cellen):
            yield rijnr, cellen


def _zoek_match(cellen, mapping: Mapping, kolomindex: dict[str, int], artikeldata: Artikeldata):
    argumenten: dict[str, object] = {}
    delen = []
    for k in mapping.sleutels():
        i = kolomindex.get(k.kolom)
        if i is None:
            continue
        waarde = cellen[i].value
        argumenten[SLEUTELTYPE_ARG[k.doelveld]] = waarde
        delen.append("" if waarde is None else str(waarde))
    return artikeldata.zoek(**argumenten), " / ".join(delen)


def match_rijen(ws, mapping: Mapping, artikeldata: Artikeldata) -> list[RijResultaat]:
    if not mapping.sleutels():
        raise ValueError("Geen sleutelkolom gekozen (artikelnummer, EAN of omschrijving).")
    kolomindex = koppen(ws, mapping.kopregel_index)
    uit = []
    for rijnr, cellen in _datarijen(ws, mapping.kopregel_index):
        match, sleutel = _zoek_match(cellen, mapping, kolomindex, artikeldata)
        uit.append(RijResultaat(rijnr, sleutel, match))
    return uit


def vul_in(ws, mapping: Mapping, artikeldata: Artikeldata, overschrijven: bool = False) -> Rapport:
    rijen = match_rijen(ws, mapping, artikeldata)
    kolomindex = koppen(ws, mapping.kopregel_index)
    doelen = [(k, kolomindex[k.kolom]) for k in mapping.doelen() if k.kolom in kolomindex]
    for r in rijen:
        for k, i in doelen:
            cel = ws.cell(row=r.rij, column=i + 1)
            w = artikeldata.waarde(r.match.artikel, k.doelveld) if r.match else None
            if not _is_leeg(cel) and not overschrijven:
                r.velden.append(VeldResultaat(k.kolom, k.doelveld, cel.value, k.eenheid,
                                              "dealer (bestaande waarde)", None, "bestaand"))
                continue
            if w is None or w.waarde is None or w.waarde == "":
                cel.fill = GEEL
                bron = "artikel niet gevonden" if r.match is None else "geen waarde in productdata"
                r.velden.append(VeldResultaat(k.kolom, k.doelveld, None, k.eenheid, bron, None, "leeg"))
                continue
            cel.value = maak_waarde(w, k.eenheid)
            status = "controleer" if r.match.via == "omschrijving" else "ingevuld"
            r.velden.append(VeldResultaat(k.kolom, k.doelveld, cel.value, k.eenheid, w.bron, w.regel, status))
    return Rapport(rijen)


def schrijf_controle(wb, rapport: Rapport) -> None:
    if CONTROLE_TAB in wb.sheetnames:
        del wb[CONTROLE_TAB]
    ct = wb.create_sheet(CONTROLE_TAB)
    s = rapport.samenvatting()
    ct.append(["Samenvatting"])
    ct.append([f"Rijen: {s['totaal']}", f"Gevonden: {s['gevonden']}", f"Niet gevonden: {s['niet_gevonden']}",
               f"Ingevuld: {s['ingevuld']}", f"Gaten: {s['gaten']}"])
    ct.append(["Gevonden via: " + ", ".join(f"{k} {v}" for k, v in s["via"].items())])
    ct.append(["Gaten per kolom: " + ", ".join(f"{k} {v}" for k, v in s["gaten_per_kolom"].items())])
    ct.append([])
    ct.append(["Rij", "Sleutel", "Artikelcode", "Gevonden via", "Kolom", "Doelveld", "Waarde", "Eenheid",
               "Status", "Bron", "Rekenregel"])
    for r in rapport.rijen:
        if r.match is None:
            ct.append([r.rij, r.sleutel, None, "niet gevonden"])
            continue
        code = r.match.artikel.get("artikelcode")
        via = r.match.via if r.match.score >= 1.0 else f"{r.match.via} ({r.match.score:.2f})"
        for v in r.velden:
            ct.append([r.rij, r.sleutel, code, via, v.kolom, v.veld_id, v.waarde, v.eenheid,
                       v.status, v.bron, v.regel])
    for kol, breedte in zip("ABCDEFGHIJK", (6, 26, 12, 14, 20, 22, 16, 8, 11, 34, 50)):
        ct.column_dimensions[kol].width = breedte


def werkboek_naar_bytes(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def verwerk(inhoud: bytes, bestandsnaam: str, mapping: Mapping, artikeldata: Artikeldata,
            tabblad: str | None = None, overschrijven: bool = False) -> tuple[bytes, Rapport]:
    wb = laad_werkboek(inhoud, bestandsnaam)
    ws = kies_tabblad(wb, tabblad)
    rapport = vul_in(ws, mapping, artikeldata, overschrijven)
    schrijf_controle(wb, rapport)
    return werkboek_naar_bytes(wb), rapport


def bepaal_mapping(client, ws, artikeldata: Artikeldata) -> Mapping:
    """Kopregel zoeken en Claude om een mapping vragen; bij een fout een lege mapping."""
    rijen = lees_rijen(ws, 10)
    try:
        kopregel = vind_kopregel(rijen)
    except ValueError as e:
        return Mapping(0, [], opmerkingen=str(e))
    namen = list(koppen(ws, kopregel).keys())
    if client is None:
        m = lege_mapping(kopregel, namen)
        m.opmerkingen = "Geen API-client: mapping handmatig kiezen."
        return m
    catalogus = catalogus_voor_prompt(artikeldata.ruwe_kolommen, artikeldata.vaste_sleutels)
    try:
        m = vraag_mapping(client, rijen, ws.title, ws.max_row - kopregel - 1, catalogus)
    except (anthropic.APIError, ValueError, StopIteration, json.JSONDecodeError) as e:
        m = lege_mapping(kopregel, namen)
        m.opmerkingen = f"Mapping door Claude mislukt ({e}). Kies de velden handmatig."
        return m
    # Kolommen die Claude niet noemde toevoegen als 'geen', zodat de UI compleet is.
    genoemd = {k.kolom for k in m.kolommen}
    for naam in namen:
        if naam not in genoemd:
            m.kolommen.append(lege_mapping(kopregel, [naam]).kolommen[0])
    return m


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Vul een dealer-Excelbestand met Repair Care-productdata.")
    p.add_argument("bestand")
    p.add_argument("--mapping", help="mapping.json gebruiken in plaats van Claude")
    p.add_argument("--schrijf-mapping", help="gebruikte mapping opslaan als JSON")
    p.add_argument("--overschrijven", action="store_true")
    p.add_argument("--tabblad")
    p.add_argument("--uit")
    args = p.parse_args(argv)

    pad = Path(args.bestand)
    inhoud = pad.read_bytes()
    artikeldata = Artikeldata.laad()
    wb = laad_werkboek(inhoud, pad.name)
    ws = kies_tabblad(wb, args.tabblad)

    if args.mapping:
        mapping = Mapping.uit_dict(json.loads(Path(args.mapping).read_text(encoding="utf-8")))
    else:
        client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
        mapping = bepaal_mapping(client, ws, artikeldata)
        if mapping.opmerkingen:
            print("Opmerking:", mapping.opmerkingen)
    if args.schrijf_mapping:
        Path(args.schrijf_mapping).write_text(json.dumps(mapping.naar_dict(), ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    for k in mapping.kolommen:
        print(f"  {k.kolom:30} -> {k.doelveld:24} {k.eenheid or '':4} [{k.zekerheid}] {k.toelichting}")

    try:
        uit_bytes, rapport = verwerk(inhoud, pad.name, mapping, artikeldata, ws.title, args.overschrijven)
    except ValueError as e:
        print(f"Invullen niet mogelijk: {e}")
        print("Tip: geef een mapping mee met --mapping, of kies een sleutelkolom.")
        return 1
    uit = Path(args.uit) if args.uit else pad.with_name(pad.stem + "_ingevuld.xlsx")
    uit.write_bytes(uit_bytes)
    s = rapport.samenvatting()
    print(f"Geschreven: {uit}")
    print(f"Rijen {s['totaal']}, gevonden {s['gevonden']}, niet gevonden {s['niet_gevonden']}, "
          f"ingevuld {s['ingevuld']}, gaten {s['gaten']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
