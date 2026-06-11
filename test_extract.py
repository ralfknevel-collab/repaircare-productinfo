"""Testscript: extraheert één PDF en print het JSON-resultaat. Voor verificatie."""

import json
import sys
from pathlib import Path

import anthropic

from ingest import extraheer_pdf, PRODUCTBLADEN_DIR


def main() -> int:
    pdf = sorted(PRODUCTBLADEN_DIR.glob("*.pdf"))[0]
    print(f"Test-extractie op: {pdf.name}\n", flush=True)

    client = anthropic.Anthropic()
    data = extraheer_pdf(client, pdf, "productdatablad")

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
