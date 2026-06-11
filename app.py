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
    "Wat is het brutogewicht per doos van DRY FLEX 4?",
    "Welke gevarenklasse heeft BIO FLEX COOL component A?",
    "Wat is de UN-code van DRY FIX UNI?",
    "Hoe lang is de verwerkingstijd van DRY FLEX SF?",
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
    .block-container {{ padding-top: 2.2rem; padding-bottom: 6rem; max-width: 780px; }}

    h1, h2, h3 {{ color: {DONKERGROEN} !important; font-weight: 700;
                  letter-spacing: -0.01em; }}

    /* Primaire knoppen: groen, afgerond, zachte schaduw, subtiele hover-lift */
    .stButton button[kind="primary"], .stButton button[kind="primaryFormSubmit"],
    [data-testid="stFormSubmitButton"] button {{
        background-color: {LICHTGROEN};
        color: #FFFFFF;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        padding: 9px 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.10);
        transition: transform .08s ease, background-color .15s ease, box-shadow .15s ease;
    }}
    .stButton button[kind="primary"]:hover,
    [data-testid="stFormSubmitButton"] button:hover {{
        background-color: {DONKERGROEN};
        color: #FFFFFF;
        transform: translateY(-1px);
        box-shadow: 0 3px 8px rgba(0,118,49,0.25);
    }}
    /* Voorbeeldvraag-kaarten: links uitgelijnd, gelijke hoogte, nette hover */
    .stButton button[kind="secondary"] {{
        background-color: #FFFFFF;
        color: {BODYGRIJS};
        border: 1px solid #E5E7E4;
        border-radius: 12px;
        font-weight: 500;
        min-height: 60px;
        padding: 12px 18px;
        justify-content: flex-start;
        text-align: left;
        line-height: 1.35;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        transition: transform .08s ease, border-color .15s ease, box-shadow .15s ease;
    }}
    .stButton button[kind="secondary"] p {{
        text-align: left;
        width: 100%;
        margin: 0;
    }}
    .stButton button[kind="secondary"]:hover {{
        border-color: {LICHTGROEN};
        color: {DONKERGROEN};
        transform: translateY(-1px);
        box-shadow: 0 3px 10px rgba(0,0,0,0.07);
    }}

    /* Chatbubbels: zachte witte kaarten met schaduw i.p.v. harde rand */
    [data-testid="stChatMessage"] {{
        border-radius: 16px;
        padding: 6px 18px;
        margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        border: none;
        background-color: #FFFFFF;
    }}
    /* Vraag van de gebruiker krijgt een zachte groene tint */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
        background-color: #ECF6EF;
    }}
    /* Avatars verbergen voor een strakke, moderne look */
    [data-testid="stChatMessageAvatarUser"],
    [data-testid="stChatMessageAvatarAssistant"] {{ display: none; }}

    /* Invoerbalk onderaan: afgerond, zachte schaduw */
    [data-testid="stChatInput"] {{
        border: 1px solid #E5E7E4;
        border-radius: 14px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }}
    [data-testid="stTextInput"] div[data-baseweb="input"],
    [data-testid="stTextInput"] div[data-baseweb="base-input"] {{
        border: 1px solid #E5E7E4;
        border-radius: 10px;
        background-color: #FFFFFF;
    }}

    /* Inlogkaart: gecentreerd, wit, zachte schaduw */
    [data-testid="stForm"] {{
        border: 1px solid #ECECEC;
        border-radius: 16px;
        background-color: #FFFFFF;
        padding: 22px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.06);
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
    """Toon een net inlogkader als APP_PASSWORD is ingesteld. True = toegang."""
    verwacht = get_secret("APP_PASSWORD")
    if not verwacht:
        return True  # geen wachtwoord ingesteld -> open (bv. lokaal)
    if st.session_state.get("toegang"):
        return True

    midden = st.columns([1, 2, 1])[1]
    with midden:
        st.markdown(
            f"<p style='color:{BODYGRIJS}; margin-bottom:4px;'>"
            "Voer het wachtwoord in om toegang te krijgen.</p>",
            unsafe_allow_html=True,
        )
        with st.form("inlogformulier"):
            invoer = st.text_input(
                "Wachtwoord", type="password",
                label_visibility="collapsed", placeholder="Wachtwoord",
            )
            ingelogd = st.form_submit_button("Inloggen", use_container_width=True)
        if ingelogd:
            if invoer == verwacht:
                st.session_state.toegang = True
                st.rerun()
            else:
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
