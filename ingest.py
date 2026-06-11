"""
Ingestie-script voor de Repair Care productinfo-tool.

Leest alle PDF's uit 'Productdatabladen' en 'Veiligheidsbladen', stuurt elke PDF
naar Claude voor gestructureerde extractie, en schrijft het resultaat naar
kennisbank.json. Draai dit script opnieuw wanneer er PDF's bijkomen of wijzigen.

Gebruik:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 ingest.py
"""

import base64
import json
import os
import sys
from pathlib import Path

import anthropic

# --- Configuratie ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
PRODUCTBLADEN_DIR = BASE_DIR / "Productdatabladen"
VEILIGHEIDSBLADEN_DIR = BASE_DIR / "Veiligheidsbladen"
OUTPUT_FILE = BASE_DIR / "kennisbank.json"

MODEL = "claude-opus-4-8"

# JSON-schema waaraan Claude's extractie per PDF moet voldoen.
EXTRACTIE_SCHEMA = {
    "type": "object",
    "properties": {
        "product": {
            "type": "string",
            "description": "De productnaam, bv. 'DRY FLEX 4'. Zonder 'component A/B'.",
        },
        "component": {
            "type": "string",
            "description": "Component-aanduiding indien van toepassing: 'A', 'B', "
            "'2-in-1', of leeg ('') als het document geen losse component betreft.",
        },
        "samenvatting": {
            "type": "string",
            "description": "Volledige, gestructureerde samenvatting in Markdown van ALLE "
            "relevante informatie in dit document: eigenschappen, toepassing, "
            "verwerking, technische specificaties, gevaren, opslag, etc. Wees "
            "compleet en feitelijk; verzin niets. Nederlands.",
        },
        "specs": {
            "type": "array",
            "description": "Belangrijke veld/waarde-paren voor snel zoeken "
            "(bv. VOS-gehalte, dichtheid, gevarenklasse, signaalwoord).",
            "items": {
                "type": "object",
                "properties": {
                    "veld": {"type": "string"},
                    "waarde": {"type": "string"},
                },
                "required": ["veld", "waarde"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["product", "component", "samenvatting", "specs"],
    "additionalProperties": False,
}


def extraheer_pdf(client: anthropic.Anthropic, pdf_path: Path, categorie: str) -> dict:
    """Stuur één PDF naar Claude en geef het gestructureerde resultaat terug."""
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")

    instructie = (
        f"Dit is een {categorie} van een Repair Care product. "
        "Extraheer ALLE informatie uit dit PDF-document volgens het schema. "
        "De samenvatting moet compleet zijn en alle technische details, "
        "veiligheidsinformatie en verwerkingsinstructies bevatten die in het "
        "document staan. Verzin nooit informatie die er niet staat."
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={
            "format": {"type": "json_schema", "schema": EXTRACTIE_SCHEMA}
        },
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": instructie},
                ],
            }
        ],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude weigerde extractie van {pdf_path.name}")

    tekst = next((b.text for b in response.content if b.type == "text"), "")
    data = json.loads(tekst)
    data["bestand"] = pdf_path.name
    data["categorie"] = categorie
    return data


def verzamel_pdfs() -> list[tuple[Path, str]]:
    """Geef lijst van (pad, categorie) voor alle PDF's."""
    taken: list[tuple[Path, str]] = []
    for pdf in sorted(PRODUCTBLADEN_DIR.glob("*.pdf")):
        taken.append((pdf, "productdatablad"))
    for pdf in sorted(VEILIGHEIDSBLADEN_DIR.glob("*.pdf")):
        taken.append((pdf, "veiligheidsblad"))
    return taken


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("FOUT: zet eerst je API-key:  export ANTHROPIC_API_KEY=\"sk-ant-...\"")
        return 1

    client = anthropic.Anthropic()
    taken = verzamel_pdfs()
    if not taken:
        print("Geen PDF's gevonden. Controleer de mappen.")
        return 1

    print(f"{len(taken)} PDF's gevonden. Start extractie met {MODEL}...\n")

    kennisbank: list[dict] = []
    fouten: list[str] = []

    for i, (pdf_path, categorie) in enumerate(taken, 1):
        print(f"[{i}/{len(taken)}] {pdf_path.name} ...", end=" ", flush=True)
        try:
            data = extraheer_pdf(client, pdf_path, categorie)
            kennisbank.append(data)
            print("OK")
        except Exception as e:  # noqa: BLE001 - per-bestand doorgaan
            print(f"MISLUKT ({e})")
            fouten.append(pdf_path.name)

    OUTPUT_FILE.write_text(
        json.dumps(kennisbank, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nKlaar. {len(kennisbank)} documenten weggeschreven naar {OUTPUT_FILE.name}")
    if fouten:
        print(f"Mislukt ({len(fouten)}): {', '.join(fouten)}")
        print("Draai het script opnieuw om mislukte bestanden opnieuw te proberen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
