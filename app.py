"""
Chat-app voor de Repair Care productinfo-tool.

Laadt kennisbank.json (gemaakt door ingest.py) en biedt een chatbot die vragen
beantwoordt over de product- en veiligheidsbladen, met bronvermelding.
Vormgeving volgt de Repair Care Quote-tool (witte zijbalk met navigatie, kaarten,
merkgroen, Inter Tight-font).

Lokaal draaien:
    export ANTHROPIC_API_KEY="sk-ant-..."
    streamlit run app.py

In de cloud (Streamlit Community Cloud): zet ANTHROPIC_API_KEY en (optioneel)
APP_PASSWORD als secrets in de app-instellingen. Zie README.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path

import anthropic
import pandas as pd
import streamlit as st

from artikeldata import Artikeldata
from dealer_invuller import (
    bepaal_mapping, controleer_eenheden, kies_tabblad, koppen, laad_werkboek, lees_rijen,
    match_rijen, verwerk,
)
from mapping import KolomMapping, Mapping, lege_mapping
from veldcatalogus import EENHEID_OPTIES, catalogus_voor_prompt

BASE_DIR = Path(__file__).resolve().parent
KENNISBANK_FILE = BASE_DIR / "kennisbank.json"
LOGO_SVG = BASE_DIR / "assets" / "repair-care-logo.svg"
LOGO_PNG = BASE_DIR / "assets" / "repair-care-logo.png"
MODEL = "claude-opus-4-8"

# --- Repair Care huisstijl (tokens gelijk aan de Repair Care Quote-tool) -----
BRAND = "#007A37"        # merkgroen: primaire knoppen, kaarttitels
BRAND_700 = "#046B33"    # sectiekoppen, actieve navigatie
BRAND_SOFT = "#E9F3EC"   # zachte groene vlakken (actieve nav, gebruikersbubbel)
BRAND_SOFT2 = "#F3F9F5"  # nog zachter (uploader)
GEEL = "#FFDC00"         # accentbalkje bij actieve navigatie
INK = "#13211A"          # tekst
MUTED = "#5C6B62"        # subtekst
LIJN = "#E6ECE7"         # randen
BG = "#EEF1EE"           # paginavlak
PANEL = "#FFFFFF"        # kaarten, zijbalk
WARN = "#C0392B"

NAVIGATIE = [
    ("chat", "Productinfo-chat", ":material/forum:"),
    ("dealer", "Dealer-Excel", ":material/table_view:"),
]

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
    """Injecteer de huisstijl van de Repair Care Quote-tool: witte zijbalk met
    navigatie, licht groengrijs paginavlak, witte kaarten, groene accenten."""
    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700;800&display=swap');

    html, body, [class*="st-"], [data-testid="stAppViewContainer"] *,
    .stMarkdown, .stChatMessage, button, input, textarea {{
        font-family: 'Inter Tight', Arial, Helvetica, sans-serif !important;
    }}
    [data-testid="stIconMaterial"] {{ font-family: 'Material Symbols Rounded' !important; }}

    /* Streamlit-balk, menu en zijbalk-inklapknop verbergen: app-achtige look */
    [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
    #MainMenu, footer, [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"],
    [data-testid="stSidebarHeader"], [data-testid="stLogoSpacer"] {{
        display: none !important;
    }}

    .stApp {{ background-color: {BG}; color: {INK}; }}

    /* ---- zijbalk: wit, 248px, dunne rand, logo + navigatie ---- */
    [data-testid="stSidebar"] {{
        background-color: {PANEL};
        border-right: 1px solid {LIJN};
        width: 248px !important; min-width: 248px !important;
    }}
    [data-testid="stSidebar"] > div:first-child {{ width: 248px !important; }}
    [data-testid="stSidebarUserContent"] {{ padding: 0 12px 20px; }}
    .rc-logo {{
        display: flex; align-items: center;
        margin: 0 -12px 10px; padding: 22px 18px 18px;
        border-bottom: 1px solid {LIJN};
    }}
    .rc-logo img {{ height: 32px; width: auto; display: block; }}
    [data-testid="stSidebar"] .stButton button {{
        width: 100%; justify-content: flex-start; text-align: left; gap: 11px;
        background: transparent; border: 0; border-radius: 10px;
        color: #3C4A42; font-weight: 600; padding: 10px 12px;
        box-shadow: none; position: relative;
        transition: background .12s, color .12s;
    }}
    [data-testid="stSidebar"] .stButton button p {{ font-size: 14px; }}
    [data-testid="stSidebar"] .stButton button:hover {{
        background: rgba(0,122,55,.06); color: {INK}; border: 0;
    }}
    [data-testid="stSidebar"] .stButton button[kind="primary"] {{
        background: {BRAND_SOFT}; color: {BRAND_700}; font-weight: 700;
    }}
    [data-testid="stSidebar"] .stButton button[kind="primary"]:hover {{
        background: {BRAND_SOFT}; color: {BRAND_700};
    }}
    [data-testid="stSidebar"] .stButton button[kind="primary"]::before {{
        content: ""; position: absolute; left: -12px; top: 8px; bottom: 8px;
        width: 4px; border-radius: 0 3px 3px 0; background: {GEEL};
    }}

    /* ---- content: max 1080px, kaarten ---- */
    .block-container {{ max-width: 1080px !important; padding: 30px 34px 90px !important; }}
    [class*="st-key-kaart"] {{
        background: {PANEL}; border: 0 !important; border-radius: 16px;
        box-shadow: 0 1px 2px rgba(16,40,26,.05), 0 8px 24px -16px rgba(16,40,26,.30);
        padding: 24px !important; margin-bottom: 20px;
    }}
    .rc-kaarttitel {{ margin: 0 0 5px; font-size: 20px; font-weight: 800;
                      letter-spacing: -.01em; color: {BRAND}; }}
    .rc-sub {{ color: {MUTED}; margin: 0 0 18px; font-size: 13px; }}
    .rc-sectie {{
        margin: 18px 0 10px; padding-top: 14px; border-top: 1px solid {LIJN};
        font-size: 11.5px; font-weight: 800; letter-spacing: .7px;
        color: {BRAND_700}; text-transform: uppercase;
    }}
    .rc-sectie.eerste {{ border-top: 0; padding-top: 0; margin-top: 4px; }}
    .rc-tekst {{ color: {MUTED}; font-size: 14px; line-height: 1.5; margin: 0 0 12px; }}
    .rc-tekst b {{ color: {INK}; }}

    /* ---- labels en invoer ---- */
    [data-testid="stWidgetLabel"] p {{ font-size: 13px; font-weight: 700; color: {INK}; }}
    [data-testid="stTextInput"] div[data-baseweb="input"],
    [data-testid="stTextInput"] div[data-baseweb="base-input"],
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    [data-testid="stChatInput"] {{
        border: 1px solid {LIJN}; border-radius: 9px; background: {PANEL};
        box-shadow: none;
    }}
    [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within,
    [data-testid="stChatInput"]:focus-within {{
        border-color: {BRAND}; box-shadow: 0 0 0 3px rgba(0,119,50,.12);
    }}
    [data-testid="stFileUploaderDropzone"] {{
        border: 1px dashed #C9D6CD; border-radius: 12px; background: {BRAND_SOFT2};
    }}

    /* ---- knoppen: secundair wit met rand, primair merkgroen ---- */
    section.stMain .stButton button,
    [data-testid="stFormSubmitButton"] button,
    [data-testid="stDownloadButton"] button {{
        border: 1px solid {LIJN}; background: {PANEL}; border-radius: 9px;
        padding: 9px 16px; font-weight: 600; color: {INK}; box-shadow: none;
        transition: background .12s, border-color .12s, color .12s;
    }}
    section.stMain .stButton button:hover,
    [data-testid="stDownloadButton"] button:hover {{
        border-color: #C2CCC5; background: #F7F9F7; color: {INK};
    }}
    section.stMain .stButton button[kind="primary"],
    [data-testid="stFormSubmitButton"] button,
    [data-testid="stDownloadButton"] button {{
        background: {BRAND}; border-color: {BRAND}; color: #FFFFFF;
    }}
    section.stMain .stButton button[kind="primary"]:hover,
    [data-testid="stFormSubmitButton"] button:hover,
    [data-testid="stDownloadButton"] button:hover {{
        background: #005F28; border-color: #005F28; color: #FFFFFF;
    }}
    section.stMain .stButton button[kind="primary"]:disabled {{
        background: #C9D6CD; border-color: #C9D6CD; color: #FFFFFF;
    }}
    /* voorbeeldvragen: kaartjes, links uitgelijnd, gelijke hoogte */
    section.stMain .stButton button.rc-voorbeeld,
    section.stMain [data-testid="stColumn"] .stButton button[kind="secondary"] {{
        min-height: 60px; justify-content: flex-start; text-align: left;
        line-height: 1.35; font-weight: 500; color: {INK};
    }}
    section.stMain [data-testid="stColumn"] .stButton button[kind="secondary"] p {{
        text-align: left; width: 100%; margin: 0;
    }}
    section.stMain [data-testid="stColumn"] .stButton button[kind="secondary"]:hover {{
        border-color: {BRAND}; color: {BRAND_700}; background: {BRAND_SOFT2};
    }}

    /* ---- meldingen: rustige witte notice met rand ---- */
    [data-testid="stAlert"], [data-testid="stAlertContainer"] {{
        background: {PANEL} !important; border: 1px solid {LIJN}; border-radius: 12px;
        color: {MUTED};
    }}
    [data-testid="stAlert"] p {{ color: {MUTED}; font-size: 13px; line-height: 1.55; }}
    [data-testid="stAlert"] [data-testid="stAlertContentWarning"] p,
    [data-testid="stAlert"] [data-testid="stAlertContentError"] p {{ color: {WARN}; }}

    /* ---- chat ---- */
    [data-testid="stChatMessage"] {{
        border-radius: 16px; padding: 6px 18px; margin-bottom: 10px;
        background: {PANEL}; border: 1px solid {LIJN}; box-shadow: none;
    }}
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
        background: {BRAND_SOFT}; border-color: transparent;
    }}
    [data-testid="stChatMessageAvatarUser"],
    [data-testid="stChatMessageAvatarAssistant"] {{ display: none; }}

    /* ---- tabellen ---- */
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
        border: 1px solid {LIJN}; border-radius: 12px; overflow: hidden;
    }}

    /* ---- inlogkaart ---- */
    .rc-login {{ text-align: center; padding: 8px 0 2px; }}
    .rc-login img {{ height: 38px; width: auto; }}
    .rc-login .merk {{ margin-top: 10px; font-size: 12px; font-weight: 800;
                       letter-spacing: .28em; color: {BRAND}; }}
    .rc-login h2 {{ font-size: 26px; font-weight: 800; color: {INK} !important;
                    margin: 18px 0 4px; letter-spacing: -.02em; }}
    .rc-login p {{ color: {MUTED}; font-size: 14px; margin: 0 0 14px; }}
    [data-testid="stForm"] {{ border: 0; background: transparent; padding: 0; box-shadow: none; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def logo_data_uri() -> str | None:
    """Het Repair Care-logo als data-URI (svg, anders png)."""
    if LOGO_SVG.exists():
        return "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.read_bytes()).decode("utf-8")
    if LOGO_PNG.exists():
        return "data:image/png;base64," + base64.b64encode(LOGO_PNG.read_bytes()).decode("utf-8")
    return None


def kaarttitel(titel: str, sub: str) -> None:
    st.markdown(f"<div class='rc-kaarttitel'>{titel}</div><p class='rc-sub'>{sub}</p>",
                unsafe_allow_html=True)


def sectie(titel: str, eerste: bool = False) -> None:
    klasse = "rc-sectie eerste" if eerste else "rc-sectie"
    st.markdown(f"<div class='{klasse}'>{titel}</div>", unsafe_allow_html=True)


def toon_sidebar() -> str:
    """Logo en navigatie in de zijbalk; geeft de gekozen weergave terug."""
    huidig = st.session_state.get("weergave", NAVIGATIE[0][0])
    with st.sidebar:
        logo = logo_data_uri()
        if logo:
            st.markdown(f"<div class='rc-logo'><img src='{logo}' alt='Repair Care'></div>",
                        unsafe_allow_html=True)
        for sleutel, label, icoon in NAVIGATIE:
            actief = sleutel == huidig
            if st.button(label, key=f"nav_{sleutel}", icon=icoon,
                         type="primary" if actief else "secondary", use_container_width=True):
                if not actief:
                    st.session_state.weergave = sleutel
                    st.rerun()
    return huidig


def check_wachtwoord() -> bool:
    """Inlogkaart zoals het welkomstscherm van de Quote-tool. True = toegang."""
    verwacht = get_secret("APP_PASSWORD")
    if not verwacht:
        return True  # geen wachtwoord ingesteld -> open (bv. lokaal)
    if st.session_state.get("toegang"):
        return True

    st.markdown("<div style='height:14vh'></div>", unsafe_allow_html=True)
    midden = st.columns([1, 1.15, 1])[1]
    with midden, st.container(key="kaart_login"):
        logo = logo_data_uri()
        st.markdown(
            "<div class='rc-login'>"
            + (f"<img src='{logo}' alt='Repair Care'>" if logo else "")
            + "<div class='merk'>PRODUCTINFO</div>"
            "<h2>Welkom</h2><p>Log in om de productinfo-tools te gebruiken.</p></div>",
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
        layout="wide",
        initial_sidebar_state="expanded",
    )
    pas_huisstijl_toe()

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

    if "client" not in st.session_state:
        st.session_state.client = anthropic.Anthropic(api_key=api_key)

    weergave = toon_sidebar()
    if weergave == "dealer":
        toon_dealer_excel()
    else:
        toon_chat(documenten)


def toon_chat(documenten: list[dict]) -> None:
    if "kennisbank_tekst" not in st.session_state:
        st.session_state.kennisbank_tekst = bouw_kennisbank_tekst(documenten)
    if "messages" not in st.session_state:
        st.session_state.messages = []

    gekozen_voorbeeld = None
    with st.container(key="kaart_chat"):
        links, rechts = st.columns([4, 1])
        with links:
            kaarttitel("Productinfo", "Stel je vraag over de product- en veiligheidsbladen.")
        # Knop om het gesprek te wissen (rechtsboven, alleen tijdens een gesprek).
        if st.session_state.messages and rechts.button("Wissen", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        # Welkomstscherm met voorbeeldvragen zolang er nog niets gevraagd is.
        if not st.session_state.messages:
            sectie("Probeer bijvoorbeeld", eerste=True)
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


def toon_dealer_excel() -> None:
    with st.container(key="kaart_dealer"):
        kaarttitel("Dealer-Excel", "Upload een invulbestand van een dealer. De tool herkent de kolommen, "
                   "jij controleert de mapping, daarna worden de lege cellen ingevuld.")
        sectie("Bestand", eerste=True)
        try:
            artikeldata = Artikeldata.laad()
        except FileNotFoundError:
            st.error("artikeldata.json ontbreekt. Draai eerst:  python3 ingest_artikeldata.py")
            return

        bestand = st.file_uploader("Dealerbestand", type=["xlsx", "csv"], label_visibility="collapsed")
        if bestand is None:
            st.session_state.pop("dealer", None)
            return
        inhoud = bestand.getvalue()
        sleutel = hashlib.sha256(inhoud).hexdigest()

        try:
            wb = laad_werkboek(inhoud, bestand.name)
        except ValueError as e:
            st.error(str(e))
            return
        tabblad = None
        if len(wb.sheetnames) > 1:
            tabblad = st.selectbox("Tabblad", wb.sheetnames, index=wb.sheetnames.index(kies_tabblad(wb, None).title))
        ws = kies_tabblad(wb, tabblad)

        staat = st.session_state.get("dealer")
        if not staat or staat["sleutel"] != (sleutel, ws.title):
            with st.spinner("Kolommen herkennen…"):
                mapping = bepaal_mapping(st.session_state.client, ws, artikeldata)
            staat = {"sleutel": (sleutel, ws.title), "mapping": mapping}
            st.session_state.dealer = staat
        mapping: Mapping = staat["mapping"]
        if mapping.opmerkingen:
            st.info(mapping.opmerkingen)
        if "kopregel_handmatig" not in staat:
            staat["kopregel_handmatig"] = not mapping.kolommen
        if staat["kopregel_handmatig"]:
            # Geen kopregel herkend: gebruiker wijst de rij aan; keuze blijft over reruns bewaard.
            rijen = lees_rijen(ws, 10)
            opties = [f"rij {i + 1}: " + " | ".join(str(c) for c in r if c is not None)[:80]
                      for i, r in enumerate(rijen)]
            gekozen = st.selectbox("Kopregel niet herkend — kies de rij met de kolomkoppen",
                                   list(range(len(opties))), format_func=lambda i: opties[i],
                                   key=f"kopregel_{sleutel}_{ws.title}")
            mapping = lege_mapping(gekozen, list(koppen(ws, gekozen).keys()))

        catalogus = catalogus_voor_prompt(artikeldata.ruwe_kolommen, artikeldata.vaste_sleutels)
        labels = {c["id"]: f"{c['label']}  [{c['id']}]" for c in catalogus}
        ids_per_label = {v: k for k, v in labels.items()}
        voorbeeld = {}
        kolomindex = koppen(ws, mapping.kopregel_index)
        for rij in ws.iter_rows(min_row=mapping.kopregel_index + 2, max_row=mapping.kopregel_index + 4, values_only=True):
            for naam, i in kolomindex.items():
                if naam not in voorbeeld and i < len(rij) and rij[i] is not None:
                    voorbeeld[naam] = str(rij[i])

        sectie("Mapping")
        st.markdown("<p class='rc-tekst'>Pas aan waar nodig, dan <b>Invullen</b>.</p>", unsafe_allow_html=True)
        tabel = pd.DataFrame([{
            "Kolom": k.kolom,
            "Voorbeeld": voorbeeld.get(k.kolom, ""),
            "Doelveld": labels.get(k.doelveld, labels["geen"]),
            "Eenheid": k.eenheid or "",
            "Zekerheid": k.zekerheid,
            "Toelichting": k.toelichting,
        } for k in mapping.kolommen])
        bewerkt = st.data_editor(
            tabel, hide_index=True, use_container_width=True, key=f"mapping_{sleutel}_{ws.title}_{mapping.kopregel_index}",
            disabled=["Kolom", "Voorbeeld", "Zekerheid", "Toelichting"],
            column_config={
                "Doelveld": st.column_config.SelectboxColumn(options=list(labels.values()), required=True),
                "Eenheid": st.column_config.SelectboxColumn(options=[o or "" for o in EENHEID_OPTIES]),
            },
        )
        mapping = Mapping(mapping.kopregel_index, [
            KolomMapping(r["Kolom"], ids_per_label[r["Doelveld"]], r["Eenheid"] or None, r["Zekerheid"], r["Toelichting"])
            for _, r in bewerkt.iterrows()
        ], mapping.opmerkingen)

        try:
            res = match_rijen(ws, mapping, artikeldata)
        except ValueError as e:
            st.warning(str(e))
            return
        sectie("Resultaat")
        gevonden = [r for r in res if r.match]
        niet = [f"rij {r.rij}: {r.sleutel or '(leeg)'}" for r in res if not r.match]
        via: dict[str, int] = {}
        for r in gevonden:
            via[r.match.via] = via.get(r.match.via, 0) + 1
        delen = ", ".join(f"{n} op {sleuteltype}" for sleuteltype, n in via.items())
        st.markdown("<p class='rc-tekst'>"
                    f"<b>{len(gevonden)} van {len(res)} artikelen gevonden.</b>"
                    + (f" ({delen})" if delen else "")
                    + (f" Niet gevonden: {', '.join(niet[:10])}{'…' if len(niet) > 10 else ''}" if niet else "")
                    + "</p>", unsafe_allow_html=True)
        if res and not gevonden:
            st.warning("Geen enkel artikel gevonden. Controleer de sleutelkolom (artikelnummer of EAN).")

        meldingen = controleer_eenheden(mapping)
        for melding in meldingen:
            st.warning(melding)

        overschrijven = st.checkbox("Ook gevulde cellen overschrijven", value=False)
        if st.button("Invullen", type="primary", disabled=bool(meldingen)):
            try:
                uit, rapport = verwerk(inhoud, bestand.name, mapping, artikeldata, ws.title, overschrijven)
            except Exception as e:                      # ook openpyxl-fouten bij opslaan
                st.error(f"Invullen mislukt: {e}")
                return
            s = rapport.samenvatting()
            st.success(f"Ingevuld: {s['ingevuld']} cellen. Gaten (geel): {s['gaten']}. "
                       f"Zie tabblad 'Controle' in het bestand.")
            naam = bestand.name.rsplit(".", 1)[0] + "_ingevuld.xlsx"
            st.download_button("Download ingevuld bestand", data=uit, file_name=naam,
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def kolommen_klik(kolommen, index: int, vraag: str) -> bool:
    """Render een voorbeeldvraag-knop in de juiste kolom; True bij klik."""
    kol = kolommen[index % 2]
    return kol.button(vraag, key=f"voorbeeld_{index}", type="secondary",
                      use_container_width=True)


if __name__ == "__main__":
    main()
