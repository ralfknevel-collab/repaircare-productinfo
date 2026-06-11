"""
Chat-app voor de Repair Care productinfo-tool.

Laadt kennisbank.json (gemaakt door ingest.py) en biedt een chatbot die vragen
beantwoordt over de product- en veiligheidsbladen, met bronvermelding.

Lokaal draaien:
    export ANTHROPIC_API_KEY="sk-ant-..."
    streamlit run app.py

In de cloud (Streamlit Community Cloud): zet ANTHROPIC_API_KEY en (optioneel)
APP_PASSWORD als secrets in de app-instellingen. Zie README.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
KENNISBANK_FILE = BASE_DIR / "kennisbank.json"
MODEL = "claude-opus-4-8"

SYSTEEM_INSTRUCTIE = """Je bent een interne assistent voor medewerkers van Repair Care.
Je beantwoordt vragen over de Repair Care producten op basis van de product-
databladen en veiligheidsbladen die hieronder staan.

REGELS:
- Beantwoord uitsluitend op basis van de informatie in de documenten hieronder.
- Verzin NOOIT informatie. Weet je iets niet of staat het niet in de documenten,
  zeg dat dan eerlijk en verwijs naar het originele PDF-bestand.
- Vermeld bij elk antwoord de bron: het bestand (en component) waar de informatie
  vandaan komt, bv. "(bron: Veiligheidsblad DRY FLEX 4 - component A)".
- Veiligheidsbladen bevatten juridisch belangrijke informatie. Wees hierbij extra
  precies en verwijs bij twijfel altijd naar het originele veiligheidsblad.
- Antwoord in het Nederlands, helder en bondig.

=== KENNISBANK ===
"""


def get_secret(naam: str) -> str | None:
    """Haal een geheim op: eerst uit Streamlit-secrets, dan uit omgevingsvariabelen."""
    try:
        if naam in st.secrets:
            return st.secrets[naam]
    except Exception:  # noqa: BLE001 - geen secrets.toml lokaal = geen probleem
        pass
    return os.environ.get(naam)


def check_wachtwoord() -> bool:
    """Toon een wachtwoordslot als APP_PASSWORD is ingesteld. True = toegang."""
    verwacht = get_secret("APP_PASSWORD")
    if not verwacht:
        return True  # geen wachtwoord ingesteld -> open (bv. lokaal)
    if st.session_state.get("toegang"):
        return True
    invoer = st.text_input("Wachtwoord", type="password")
    if invoer == "":
        st.stop()
    if invoer == verwacht:
        st.session_state.toegang = True
        return True
    st.error("Onjuist wachtwoord.")
    st.stop()


def laad_kennisbank() -> list[dict]:
    if not KENNISBANK_FILE.exists():
        return []
    return json.loads(KENNISBANK_FILE.read_text(encoding="utf-8"))


def bouw_kennisbank_tekst(documenten: list[dict]) -> str:
    """Zet alle documenten om naar één tekstblok voor de systeem-prompt."""
    delen = []
    for doc in documenten:
        component = f" - component {doc['component']}" if doc.get("component") else ""
        kop = f"BESTAND: {doc.get('bestand', '?')} | CATEGORIE: {doc.get('categorie', '?')}"
        specs = "\n".join(
            f"  - {s['veld']}: {s['waarde']}" for s in doc.get("specs", [])
        )
        delen.append(
            f"--- {kop} ---\n"
            f"Product: {doc.get('product', '?')}{component}\n\n"
            f"{doc.get('samenvatting', '')}\n"
            + (f"\nKerngegevens:\n{specs}\n" if specs else "")
        )
    return "\n\n".join(delen)


def main() -> None:
    st.set_page_config(page_title="Repair Care Productinfo", page_icon="🔧")
    st.title("🔧 Repair Care Productinfo")
    st.caption("Stel vragen over de product- en veiligheidsbladen.")

    if not check_wachtwoord():
        return

    api_key = get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("Geen ANTHROPIC_API_KEY gevonden. Stel deze in als secret "
                 "(cloud) of als omgevingsvariabele (lokaal).")
        st.stop()

    documenten = laad_kennisbank()
    if not documenten:
        st.warning("Geen kennisbank gevonden. Draai eerst:  python3 ingest.py")
        st.stop()

    # Kennisbank-tekst en client cachen over reruns heen.
    if "kennisbank_tekst" not in st.session_state:
        st.session_state.kennisbank_tekst = bouw_kennisbank_tekst(documenten)
    if "client" not in st.session_state:
        st.session_state.client = anthropic.Anthropic(api_key=api_key)
    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.sidebar:
        st.subheader("Geladen documenten")
        st.write(f"{len(documenten)} documenten in de kennisbank.")
        producten = sorted({d.get("product", "?").upper() for d in documenten})
        st.write("**Producten:**")
        for p in producten:
            st.write(f"- {p}")
        if st.button("Gesprek wissen"):
            st.session_state.messages = []
            st.rerun()

    # Eerdere berichten tonen.
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    vraag = st.chat_input("Stel je vraag over een product...")
    if not vraag:
        return

    st.session_state.messages.append({"role": "user", "content": vraag})
    with st.chat_message("user"):
        st.markdown(vraag)

    systeem = [
        {
            "type": "text",
            "text": SYSTEEM_INSTRUCTIE + st.session_state.kennisbank_tekst,
            # Kennisbank is stabiel -> cachen scheelt kosten bij volgende vragen.
            "cache_control": {"type": "ephemeral"},
        }
    ]

    with st.chat_message("assistant"):
        plek = st.empty()
        antwoord = ""
        try:
            with st.session_state.client.messages.stream(
                model=MODEL,
                max_tokens=4000,
                system=systeem,
                messages=st.session_state.messages,
            ) as stream:
                for tekst in stream.text_stream:
                    antwoord += tekst
                    plek.markdown(antwoord)
        except anthropic.APIError as e:
            antwoord = f"Er ging iets mis met de API: {e}"
            plek.markdown(antwoord)

    st.session_state.messages.append({"role": "assistant", "content": antwoord})


if __name__ == "__main__":
    main()
