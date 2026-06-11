"""
Chat-app voor de Repair Care productinfo-tool.

Laadt kennisbank.json (gemaakt door ingest.py) en biedt een chatbot die vragen
beantwoordt over de product- en veiligheidsbladen, met bronvermelding.
Vormgeving volgt de Repair Care huisstijl (kleuren, logo, Inter Tight-font).

Lokaal draaien:
    export ANTHROPIC_API_KEY="sk-ant-..."
    streamlit run app.py

In de cloud (Streamlit Community Cloud): zet ANTHROPIC_API_KEY en (optioneel)
APP_PASSWORD als secrets in de app-instellingen. Zie README.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import anthropic
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
KENNISBANK_FILE = BASE_DIR / "kennisbank.json"
LOGO_FILE = BASE_DIR / "assets" / "repair-care-logo.png"
MODEL = "claude-opus-4-8"

# --- Repair Care huisstijl ---------------------------------------------------
DONKERGROEN = "#007631"   # koppen, accenten
LICHTGROEN = "#00953F"    # knoppen
GEEL = "#FFDC00"          # accent
BODYGRIJS = "#6F6F6E"     # bodytekst
ACHTERGROND = "#F5F5F5"   # paginavlak

VOORBEELDVRAGEN = [
    "Wat is de mengverhouding van BIO FLEX ALLROUND?",
    "Welke gevarenklasse heeft DRY FLEX 4 component A?",
    "Hoe lang is de verwerkingstijd van DRY SEAL MP?",
    "Welke producten zijn 2-componenten?",
]

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


def pas_huisstijl_toe() -> None:
    """Injecteer Repair Care kleuren en het Inter Tight-lettertype via CSS."""
    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700;800&display=swap');

    /* Lettertype overal afdwingen */
    html, body, [class*="st-"], [data-testid="stAppViewContainer"] *,
    .stMarkdown, .stChatMessage, button, input, textarea {{
        font-family: 'Inter Tight', Arial, sans-serif !important;
    }}

    /* Streamlit-balk en menu verbergen voor een schone, app-achtige look */
    [data-testid="stHeader"], [data-testid="stToolbar"],
    [data-testid="stDecoration"], #MainMenu, footer {{
        display: none !important;
    }}

    .stApp {{ background-color: {ACHTERGROND}; }}
    .block-container {{ padding-top: 2.5rem; max-width: 820px; }}

    h1, h2, h3 {{ color: {DONKERGROEN} !important; font-weight: 700; }}

    /* Knoppen in huisstijl-groen, normale breedte/hoeken */
    .stButton button {{
        background-color: {LICHTGROEN};
        color: #FFFFFF;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        padding: 8px 16px;
    }}
    .stButton button:hover {{ background-color: {DONKERGROEN}; color: #FFFFFF; }}

    /* Voorbeeldvragen als zachte kaartjes (secundaire knoppen) */
    .stButton button[kind="secondary"] {{
        background-color: #FFFFFF;
        color: {BODYGRIJS};
        border: 1px solid #E0E0E0;
        text-align: left;
        font-weight: 500;
    }}
    .stButton button[kind="secondary"]:hover {{
        border-color: {LICHTGROEN};
        color: {DONKERGROEN};
        background-color: #FFFFFF;
    }}

    /* Chatbubbels op witte kaarten met afgeronde hoeken */
    .stChatMessage {{
        background-color: #FFFFFF;
        border: 1px solid #E0E0E0;
        border-radius: 12px;
        padding: 4px 14px;
    }}

    /* Invoerveld */
    [data-testid="stChatInput"] {{
        border: 1px solid #E0E0E0;
        border-radius: 12px;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def toon_header() -> None:
    """Toon het Repair Care logo met een groene accentlijn en de titel."""
    if LOGO_FILE.exists():
        logo_b64 = base64.b64encode(LOGO_FILE.read_bytes()).decode("utf-8")
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; padding:0 0 8px;">
                <img src="data:image/png;base64,{logo_b64}" style="height:52px;">
            </div>
            <hr style="border:none; border-top:3px solid {DONKERGROEN};
                       margin:0 0 16px;">
            """,
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<h2 style='margin-top:0;'>Productinfo</h2>"
        f"<p style='color:{BODYGRIJS}; margin-top:-8px;'>"
        "Stel je vraag over de product- en veiligheidsbladen.</p>",
        unsafe_allow_html=True,
    )


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


def beantwoord(vraag: str) -> None:
    """Voeg de vraag toe, toon hem, en stream het antwoord van Claude."""
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


def main() -> None:
    st.set_page_config(
        page_title="Repair Care Productinfo",
        page_icon="🔧",
        initial_sidebar_state="collapsed",
    )
    pas_huisstijl_toe()
    toon_header()

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

    if "kennisbank_tekst" not in st.session_state:
        st.session_state.kennisbank_tekst = bouw_kennisbank_tekst(documenten)
    if "client" not in st.session_state:
        st.session_state.client = anthropic.Anthropic(api_key=api_key)
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Knop om het gesprek te wissen (rechtsboven, alleen tijdens een gesprek).
    if st.session_state.messages:
        _, rechts = st.columns([4, 1])
        if rechts.button("Wissen", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # Welkomstscherm met voorbeeldvragen zolang er nog niets gevraagd is.
    gekozen_voorbeeld = None
    if not st.session_state.messages:
        st.markdown(
            f"<p style='color:{BODYGRIJS}; margin-bottom:6px;'>"
            "Waar kan ik je mee helpen? Probeer bijvoorbeeld:</p>",
            unsafe_allow_html=True,
        )
        kolommen = st.columns(2)
        for i, v in enumerate(VOORBEELDVRAGEN):
            if kolommen_klik(kolommen=kolommen, index=i, vraag=v):
                gekozen_voorbeeld = v

    # Eerdere berichten tonen.
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    getypt = st.chat_input("Stel je vraag over een product...")
    vraag = getypt or gekozen_voorbeeld
    if vraag:
        beantwoord(vraag)
        st.rerun()


def kolommen_klik(kolommen, index: int, vraag: str) -> bool:
    """Render een voorbeeldvraag-knop in de juiste kolom; True bij klik."""
    kol = kolommen[index % 2]
    return kol.button(vraag, key=f"voorbeeld_{index}", type="secondary",
                      use_container_width=True)


if __name__ == "__main__":
    main()
