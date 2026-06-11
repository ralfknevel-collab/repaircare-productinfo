"""
Voegt het Excel-artikeloverzicht toe aan kennisbank.json.

Leest 'Product Data Sheet december 2024.xlsx' (artikel-/logistiekgegevens) en
zet alle artikelen om naar een doorzoekbaar tekstblok dat als één bron in de
kennisbank komt. Gebruikt GEEN API — puur lokaal en deterministisch.

Draai dit NA ingest.py (die de PDF's inleest). Opnieuw draaien is veilig: een
bestaand Excel-item wordt vervangen, niet gedupliceerd.

Gebruik:
    python3 ingest_excel.py
"""

import json
import sys
from pathlib import Path

import openpyxl

BASE_DIR = Path(__file__).resolve().parent
EXCEL_FILE = BASE_DIR / "Product Data Sheet december 2024.xlsx"
KENNISBANK_FILE = BASE_DIR / "kennisbank.json"
HEADER_RIJ = 2  # 0-based: rij 3 in Excel bevat de kolomnamen


def lees_artikelen() -> str:
    """Zet alle artikelrijen om naar een leesbaar tekstblok.

    Let op: sommige kolommen (zoals de EAN-code) zijn over twee cellen verdeeld
    waarvan de tweede geen kop heeft. Die kolommen-zonder-kop worden aan de
    waarde van de voorgaande kolom geplakt, zodat de uitlijning klopt.
    """
    wb = openpyxl.load_workbook(EXCEL_FILE, data_only=True)
    ws = wb["Sheet1"]
    rijen = list(ws.iter_rows(values_only=True))
    kop_rij = rijen[HEADER_RIJ]

    regels: list[str] = []
    for rij in rijen[HEADER_RIJ + 1:]:
        if not any(c is not None for c in rij):
            continue
        velden: list[dict] = []
        huidige: dict | None = None
        for i, kop in enumerate(kop_rij):
            waarde = rij[i] if i < len(rij) else None
            if kop is not None:
                kop_schoon = " ".join(str(kop).split())
                huidige = {"kop": kop_schoon, "delen": []}
                velden.append(huidige)
            if waarde is not None and huidige is not None:
                tekst = str(waarde).strip()
                if tekst and tekst.lower() != "none":
                    huidige["delen"].append(tekst)
        regel = " | ".join(
            f"{v['kop']}: {''.join(v['delen'])}" for v in velden if v["delen"]
        )
        if regel:
            regels.append(regel)

    intro = (
        "Dit is het artikel-/logistiekoverzicht uit de Repair Care productdatasheet "
        "(Excel). Per regel staat één artikel met o.a. artikelcode, EAN-code, "
        "verpakkingsinhoud, gevaarsymbolen (GHS), VOC-gehalte, UN-code, "
        "transportgegevens (ADR), gewichten en pallet-informatie.\n\n"
    )
    return intro + "\n".join(regels)


def main() -> int:
    if not EXCEL_FILE.exists():
        print(f"Excel niet gevonden: {EXCEL_FILE.name}")
        return 1
    if not KENNISBANK_FILE.exists():
        print("kennisbank.json niet gevonden. Draai eerst: python3 ingest.py")
        return 1

    tekst = lees_artikelen()

    kennisbank = json.loads(KENNISBANK_FILE.read_text(encoding="utf-8"))
    # Bestaand Excel-item verwijderen (idempotent).
    kennisbank = [d for d in kennisbank if d.get("categorie") != "artikeloverzicht"]

    kennisbank.append(
        {
            "bestand": EXCEL_FILE.name,
            "categorie": "artikeloverzicht",
            "product": "(diverse artikelen)",
            "component": "",
            "samenvatting": tekst,
            "specs": [],
        }
    )

    KENNISBANK_FILE.write_text(
        json.dumps(kennisbank, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    aantal_regels = tekst.count("\n") - 2  # min de intro-regels
    print(f"Excel toegevoegd aan kennisbank.json ({aantal_regels} artikelregels, "
          f"{len(tekst)} tekens). Totaal documenten: {len(kennisbank)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
