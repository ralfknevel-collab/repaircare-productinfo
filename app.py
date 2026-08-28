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

    if "client" not in st.session_state:
        st.session_state.client = anthropic.Anthropic(api_key=api_key)

    keuze = st.segmented_control(
        "Onderdeel", ["Productinfo-chat", "Dealer-Excel"],
        default="Productinfo-chat", label_visibility="collapsed",
    )
    if keuze == "Dealer-Excel":
        toon_dealer_excel()
    else:
        toon_chat(documenten)


def toon_chat(documenten: list[dict]) -> None:
    if "kennisbank_tekst" not in st.session_state:
        st.session_state.kennisbank_tekst = bouw_kennisbank_tekst(documenten)
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


def toon_dealer_excel() -> None:
    st.markdown(
        f"<p style='color:{BODYGRIJS};'>Upload een invulbestand van een dealer. De tool herkent de "
        "kolommen, jij controleert de mapping, daarna worden de lege cellen ingevuld.</p>",
        unsafe_allow_html=True,
    )
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

    st.markdown("**Mapping** — pas aan waar nodig, dan *Invullen*.")
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
    gevonden = [r for r in res if r.match]
    niet = [f"rij {r.rij}: {r.sleutel or '(leeg)'}" for r in res if not r.match]
    via: dict[str, int] = {}
    for r in gevonden:
        via[r.match.via] = via.get(r.match.via, 0) + 1
    delen = ", ".join(f"{n} op {sleuteltype}" for sleuteltype, n in via.items())
    st.markdown(f"**{len(gevonden)} van {len(res)} artikelen gevonden.**"
                + (f" ({delen})" if delen else "")
                + (f" Niet gevonden: {', '.join(niet[:10])}{'…' if len(niet) > 10 else ''}" if niet else ""))
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
