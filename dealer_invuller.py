"""
Kern van de dealer-Excel invuller (geen Streamlit-code).

Leest een dealerbestand (.xlsx/.csv), vindt de kopregel, matcht artikelen via de
mapping, vult lege cellen met productdata en voegt een tabblad 'Controle' toe.
Ook bruikbaar als script:

    python3 dealer_invuller.py dealerbestand.xlsx [--mapping mapping.json] [--overschrijven]
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

from artikeldata import Artikeldata, Match, Waarde
from mapping import Mapping
from veldcatalogus import converteer, veld

SLEUTELTYPE_ARG = {
    "sleutel_artikelcode": "artikelcode",
    "sleutel_ean": "ean",
    "sleutel_omschrijving": "omschrijving",
}
GEEL = openpyxl.styles.PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
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
            dialect = csv.excel
            dialect.delimiter = ";"
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
