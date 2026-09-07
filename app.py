"""
Dealerbestanden invullen met gecontroleerde Repair Care-artikeldata.

Laadt artikeldata.json en vult bekende gegevens direct lokaal in.
Handmatige instellingen en optionele AI-hulp staan onder Geavanceerd.
Vormgeving volgt de Repair Care Quote-tool met kaarten, merkgroen en Inter Tight.

Lokaal draaien: streamlit run app.py
Online delen: stel APP_PASSWORD in. APP_LANGUAGE kiest de starttaal (nl/de).
ANTHROPIC_API_KEY is alleen nodig voor optionele AI-hulp. Zie README.
"""

from __future__ import annotations

import base64
import asyncio
import hashlib
import hmac
import json
import os
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path

import anthropic
import httpx
import pandas as pd
import streamlit as st

import dealer_profielen
from artikeldata import Artikeldata
from dealer_invuller import (
    bepaal_data_start, bepaal_mapping, controleer_eenheden, kies_tabblad, koppen, laad_werkboek,
    ontbrekende_eenheden, pas_eenheden_toe, verwerk,
)
from mapping import MAPPING_TIMEOUT_SECONDS, KolomMapping, Mapping, lege_mapping
from productteksten import Productteksten
from veldcatalogus import EENHEID_OPTIES, catalogus_voor_prompt, veld
from vertalingen import vertaal, vertaal_melding

BASE_DIR = Path(__file__).resolve().parent
LOGO_SVG = BASE_DIR / "assets" / "repair-care-logo.svg"
LOGO_PNG = BASE_DIR / "assets" / "repair-care-logo.png"

# --- Repair Care huisstijl (tokens gelijk aan de Repair Care Quote-tool) -----
BRAND = "#007A37"        # merkgroen: primaire knoppen, kaarttitels
BRAND_700 = "#046B33"    # sectiekoppen
BRAND_SOFT2 = "#F3F9F5"  # nog zachter (uploader)
INK = "#13211A"          # tekst
MUTED = "#5C6B62"        # subtekst
LIJN = "#E6ECE7"         # randen
BG = "#EEF1EE"           # paginavlak
PANEL = "#FFFFFF"        # kaarten, zijbalk
WARN = "#C0392B"


def t(tekst: str, **waarden) -> str:
    """Vertaal bedieningstekst; productteksten hebben hun eigen brongebonden catalogus."""
    return vertaal(tekst, st.session_state.get("taal", "nl"), **waarden)


def melding(tekst: str) -> str:
    return vertaal_melding(tekst, st.session_state.get("taal", "nl"))


def behoud_keuzes_bij_taalwissel() -> None:
    """Bewaar gemaakte keuzes voordat vertaalde widgetlabels opnieuw worden opgebouwd."""
    staat = st.session_state.get("dealer", {})
    if staat.get("actieve_mapping"):
        staat["mapping"] = Mapping.uit_dict(staat["actieve_mapping"])
    for sleutel, waarde in list(st.session_state.items()):
        if sleutel.startswith(("maat_", "gewicht_", "tabblad_", "kopregel_", "beginrij_",
                               "overschrijven_", "kolomdetails_")):
            st.session_state[sleutel] = waarde


def get_secret(naam: str) -> str | None:
    """Haal een geheim op: eerst uit Streamlit-secrets, dan uit omgevingsvariabelen."""
    try:
        if naam in st.secrets:
            return st.secrets[naam]
    except Exception:  # noqa: BLE001 - geen secrets.toml lokaal = geen probleem
        pass
    return os.environ.get(naam)


def pas_huisstijl_toe() -> None:
    """Pas de huisstijl toe: witte zijbalk, witte kaarten en groene accenten."""
    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700;800&display=swap');

    html, body, [class*="st-"], [data-testid="stAppViewContainer"] *,
    .stMarkdown, button, input, textarea {{
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

    /* ---- zijbalk: wit, 248px, dunne rand en logo ---- */
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

    /* ---- content: extra ruimte voor kolomkoppelingen ---- */
    .block-container {{ max-width: 1400px !important; padding: 30px 34px 90px !important; }}
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
    .rc-detailtekst {{
        white-space: pre-wrap; overflow-wrap: anywhere;
        color: {INK}; font-size: 14px; line-height: 1.6; margin-bottom: 12px;
    }}

    /* ---- labels en invoer ---- */
    [data-testid="stWidgetLabel"] p {{ font-size: 13px; font-weight: 700; color: {INK}; }}
    [data-testid="stTextInput"] div[data-baseweb="input"],
    [data-testid="stTextInput"] div[data-baseweb="base-input"],
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
        border: 1px solid {LIJN}; border-radius: 9px; background: {PANEL};
        box-shadow: none;
    }}
    [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within {{
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
    /* ---- meldingen: rustige witte notice met rand ---- */
    [data-testid="stAlert"], [data-testid="stAlertContainer"] {{
        background: {PANEL} !important; border: 1px solid {LIJN}; border-radius: 12px;
        color: {MUTED};
    }}
    [data-testid="stAlert"] p {{ color: {MUTED}; font-size: 13px; line-height: 1.55; }}
    [data-testid="stAlert"] [data-testid="stAlertContentWarning"] p,
    [data-testid="stAlert"] [data-testid="stAlertContentError"] p {{ color: {WARN}; }}

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


def toon_sidebar() -> None:
    """Toon het Repair Care-logo en de naam van de tool."""
    with st.sidebar:
        logo = logo_data_uri()
        if logo:
            st.markdown(f"<div class='rc-logo'><img src='{logo}' alt='Repair Care'></div>",
                        unsafe_allow_html=True)
        st.caption(t("Dealerbestanden invullen"))


def check_wachtwoord() -> bool:
    """Inlogkaart zoals het welkomstscherm van de Quote-tool. True = toegang."""
    verwacht = get_secret("APP_PASSWORD")
    online = any(os.environ.get(naam, "").strip().lower() == "true"
                 for naam in ("RENDER", "REQUIRE_APP_PASSWORD"))
    if not isinstance(verwacht, str) or not verwacht.strip():
        if not online and verwacht in (None, ""):
            return True  # Zonder wachtwoord alleen lokaal openstellen.
        st.error(t("De online tool is nog niet beveiligd. Stel APP_PASSWORD in voordat je hem gebruikt."))
        return False
    if st.session_state.get("toegang"):
        return True

    st.markdown("<div style='height:14vh'></div>", unsafe_allow_html=True)
    midden = st.columns([1, 1.15, 1])[1]
    with midden, st.container(key="kaart_login"):
        logo = logo_data_uri()
        st.markdown(
            "<div class='rc-login'>"
            + (f"<img src='{logo}' alt='Repair Care'>" if logo else "")
            + f"<div class='merk'>{t('DEALERBESTANDEN')}</div>"
            f"<h2>{t('Welkom')}</h2><p>{t('Log in om dealerbestanden in te vullen.')}</p></div>",
            unsafe_allow_html=True,
        )
        with st.form("inlogformulier"):
            invoer = st.text_input(
                t("Wachtwoord"), type="password", key="wachtwoord_invoer",
                label_visibility="collapsed", placeholder=t("Wachtwoord"),
            )
            ingelogd = st.form_submit_button(t("Inloggen"), use_container_width=True)
        if ingelogd:
            if hmac.compare_digest(invoer.encode("utf-8"), verwacht.encode("utf-8")):
                st.session_state.toegang = True
                st.rerun()
            else:
                st.error(t("Onjuist wachtwoord."))
    st.stop()


def main() -> None:
    if "taal" not in st.session_state:
        voorkeur = os.environ.get("APP_LANGUAGE", "nl").lower()
        st.session_state.taal = voorkeur if voorkeur in {"nl", "de"} else "nl"
    st.set_page_config(
        page_title="Repair Care | " + t("Dealerbestanden invullen"),
        page_icon="🔧",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    pas_huisstijl_toe()
    st.radio("Taal / Sprache", ["nl", "de"], key="taal", horizontal=True,
             format_func=lambda code: {"nl": "Nederlands", "de": "Deutsch"}[code],
             on_change=behoud_keuzes_bij_taalwissel)

    if not check_wachtwoord():
        return

    toon_sidebar()
    toon_dealer_excel()


def toon_dealer_excel() -> None:
    with st.container(key="kaart_dealer"):
        kaarttitel(t("Dealerbestanden invullen"), t("Upload je dealerbestand. Bekende gegevens worden automatisch "
                   "aangevuld. Download daarna het resultaat."))
        sectie(t("Bestand"), eerste=True)
        try:
            artikeldata = Artikeldata.laad()
        except FileNotFoundError:
            st.error(t("artikeldata.json ontbreekt. Draai eerst:  python3 ingest_artikeldata.py"))
            return

        prijsinfo = getattr(artikeldata, "prijslijst_info", {})
        bronmeldingen = getattr(artikeldata, "bron_meldingen", [])
        if not prijsinfo and bronmeldingen:
            st.warning(t("Brongegevens konden niet volledig worden geladen. Neem contact op met de beheerder."))
        bronconflicten = [code for code, artikel in getattr(artikeldata, "artikelen", {}).items()
                         if artikel.get("bron_conflicten")]
        if bronconflicten:
            st.warning(t("Bronconflict bij artikel {artikelen}. De EAN-codes verschillen tussen de bronnen. "
                         "Deze artikelen worden niet aangevuld.", artikelen=", ".join(bronconflicten)))

        # Een gewijzigd uploadlabel wist bij Streamlit ook met dezelfde sleutel het bestand.
        bestand = st.file_uploader("Dealerbestand / Händlerdatei", type=["xlsx", "csv"],
                                   label_visibility="collapsed", key="dealer_upload")
        if bestand is None:
            st.session_state.pop("dealer", None)
            return
        inhoud = bestand.getvalue()
        sleutel = hashlib.sha256(inhoud).hexdigest()

        try:
            wb = laad_werkboek(inhoud, bestand.name)
        except ValueError as e:
            st.error(melding(str(e)))
            return
        # Het resultaat staat boven de instellingen, maar gebruikt wel hun actuele waarden.
        eenhedengebied = st.container()
        resultaatgebied = st.container()
        with st.expander(t("Geavanceerd"), expanded=False):
            st.caption(t("Alleen nodig als je de indeling of kolomkoppelingen wilt aanpassen. "
                       "Wijzigingen worden direct verwerkt; het originele bestand blijft ongewijzigd."))
            tabblad = None
            if len(wb.sheetnames) > 1:
                tabblad = st.selectbox(
                    t("Tabblad"), wb.sheetnames, index=wb.sheetnames.index(kies_tabblad(wb, None).title),
                    key=f"tabblad_{sleutel}",
                )
            ws = kies_tabblad(wb, tabblad)
            staat = st.session_state.get("dealer")
            if not staat or staat.get("werkwijze") != "direct_eenheden" or staat["sleutel"] != (sleutel, ws.title):
                staat = {"sleutel": (sleutel, ws.title), "werkwijze": "direct_eenheden", "versie": 0,
                         "mapping": bepaal_mapping(None, ws, artikeldata), "mapping_versie": "prijslijst_v1"}
                st.session_state.dealer = staat
            elif staat.get("mapping_versie") != "prijslijst_v1":
                # Vul nieuw herkenbare bronkolommen aan; behoud bestaande handmatige keuzes.
                bestaand = staat["mapping"]
                nieuw = bepaal_mapping(None, ws, artikeldata)
                editor_sleutel = f"mapping_{sleutel}_{ws.title}_{bestaand.kopregel_index}_{staat['versie']}"
                bewerkt = st.session_state.get(editor_sleutel, {}).get("edited_rows", {})
                nieuwe_kolommen = {k.kolom: k for k in nieuw.kolommen}
                labels = {f"{v['label']}  [{v['id']}]": v["id"]
                          for v in catalogus_voor_prompt(artikeldata.ruwe_kolommen, artikeldata.vaste_sleutels)}
                if bestaand.kopregel_index == nieuw.kopregel_index:
                    for index, kolom in enumerate(bestaand.kolommen):
                        handmatig = bewerkt.get(index, bewerkt.get(str(index), {}))
                        voorstel = nieuwe_kolommen.get(kolom.kolom)
                        if handmatig:
                            # Nieuwe tabeldata reset de editor; neem de bestaande bewerkingen eerst over.
                            if handmatig.get("Doelveld") in labels:
                                kolom.doelveld = labels[handmatig["Doelveld"]]
                            if "Eenheid" in handmatig:
                                kolom.eenheid = handmatig["Eenheid"] or None
                        elif (kolom.doelveld == "geen" and voorstel is not None
                                and voorstel.doelveld in {"collo_netto_gewicht", "collo_bruto_gewicht",
                                                         "adviesprijs", "adviesprijs_eenheid", "ve_aantal",
                                                         "prijslijst_omschrijving"}):
                            bestaand.kolommen[index] = voorstel
                staat["mapping_versie"] = "prijslijst_v1"
            api_key = get_secret("ANTHROPIC_API_KEY")
            if st.button(t("AI-hulp bij kolommen"), disabled=not api_key,
                         help=t("Optioneel. Maakt nieuwe koppelingen en vervangt je huidige keuzes. Kan enkele minuten duren.")):
                status = st.empty()
                try:
                    with st.spinner(t("AI-voorstel maken…"), show_time=True):
                        client = anthropic.AsyncAnthropic(api_key=api_key)
                        voorstel = bepaal_mapping(client, ws, artikeldata, lambda tekst: status.caption(melding(tekst)),
                                                 ai_fouten_doorgeven=True)
                    # Onzekere AI-voorstellen zijn geen toestemming om productdata in te vullen.
                    for k in voorstel.kolommen:
                        if k.zekerheid != "hoog":
                            k.doelveld, k.eenheid = "geen", None
                    if not voorstel.sleutels() or controleer_eenheden(voorstel):
                        raise ValueError("Het AI-voorstel heeft geen bruikbare sleutel of een ongeldige eenheid.")
                    staat["mapping"] = voorstel
                    staat["versie"] += 1
                    staat.pop("ai_fout", None)
                except (asyncio.TimeoutError, anthropic.APIError, httpx.TransportError, ValueError, KeyError):
                    staat["ai_fout"] = "AI-hulp gaf geen bruikbaar antwoord binnen de beschikbare tijd. " \
                                       "Je bestaande koppelingen en resultaat zijn behouden."
                finally:
                    status.empty()
            if not api_key:
                st.caption(t("Automatisch invullen werkt zonder AI. Voor optionele AI-hulp is een API-sleutel nodig."))
            else:
                st.caption(t("AI-hulp wacht maximaal {minuten} minuten; de gewone invulstap gebruikt geen AI.",
                             minuten=MAPPING_TIMEOUT_SECONDS // 60))
            if staat.get("ai_fout"):
                st.warning(t(staat["ai_fout"]))
            mapping = Mapping.uit_dict(staat["mapping"].naar_dict())
            versie = staat["versie"]
            if mapping.opmerkingen:
                st.caption(melding(mapping.opmerkingen))
            kopregel = st.number_input(
                t("Rij met kolomkoppen"), min_value=1, max_value=max(1, ws.max_row),
                value=mapping.kopregel_index + 1, step=1, key=f"kopregel_{sleutel}_{ws.title}_{versie}",
            ) - 1
            if kopregel != mapping.kopregel_index or not mapping.kolommen:
                mapping = lege_mapping(kopregel, list(koppen(ws, kopregel).keys()))
            beginrij = mapping.data_start_index
            if beginrij is None:
                beginrij = bepaal_data_start(ws, kopregel)
            data_start_index = st.number_input(
                t("Eerste artikelrij"), min_value=kopregel + 2, max_value=max(kopregel + 2, ws.max_row + 1),
                value=beginrij + 1, step=1, key=f"beginrij_{sleutel}_{ws.title}_{kopregel}_{versie}",
            ) - 1
            mapping.data_start_index = data_start_index
            mapping = toon_kolomkoppelingen(ws, mapping, artikeldata, sleutel, versie)
            staat["actieve_mapping"] = mapping.naar_dict()
            overschrijven = st.checkbox(t("Ook gevulde cellen overschrijven"), value=False,
                                        key=f"overschrijven_{sleutel}_{ws.title}")

        with eenhedengebied:
            mapping = toon_eenheidskeuze(ws, mapping, bestand.name, sleutel)

        producttaal = st.session_state.get("taal", "nl")
        productteksten = Productteksten({})
        if producttaal == "de":
            try:
                productteksten = Productteksten.laad()
            except (OSError, ValueError):
                st.warning(t("De Duitse productvertalingen konden niet worden geladen. "
                             "Beschrijvende tekstvelden worden niet aangevuld; overige gegevens wel. "
                             "Neem contact op met de beheerder."))
        broninhoud = json.dumps([artikeldata.artikelen, artikeldata.vaste, artikeldata.ruwe_kolommen],
                               ensure_ascii=False, sort_keys=True)
        bronsleutel = hashlib.sha256(broninhoud.encode("utf-8")).hexdigest()
        # Vernieuw downloads bij bronwijzigingen en na het verstrijken van een prijslijst.
        uitvoersleutel = json.dumps([bestand.name, sleutel, ws.title, mapping.naar_dict(), overschrijven, bronsleutel,
                                    "componentmaten_v1", "doosgewichten_v1", "prijslijst_v1", date.today().isoformat(),
                                    producttaal, productteksten.vingerafdruk],
                                   ensure_ascii=False, sort_keys=True)
        if staat.get("uitvoersleutel") != uitvoersleutel:
            # Nooit een oude download tonen bij gewijzigde of ongeldige instellingen.
            staat.update(uitvoersleutel=uitvoersleutel, uit=None, rapport=None, fout=None)
            meldingen = controleer_eenheden(mapping)
            if meldingen:
                staat["fout"] = " ".join(meldingen)
            else:
                try:
                    staat["uit"], staat["rapport"] = verwerk(
                        inhoud, bestand.name, mapping, artikeldata, ws.title, overschrijven,
                        behoud_sjabloon=True, producttaal=producttaal, productteksten=productteksten,
                    )
                except ValueError as e:
                    staat["fout"] = str(e)
                except Exception:
                    staat["fout"] = "Het bestand kon niet worden verwerkt. Je originele bestand is ongewijzigd."

        with resultaatgebied:
            sectie(t("Resultaat"))
            st.caption(t("Tabblad: {tabblad}. Bestaande waarden blijven staan tenzij je bij Geavanceerd anders kiest.",
                         tabblad=ws.title))
            st.caption(t("Taal voor nieuwe productteksten: {taalnaam}.",
                         taalnaam={"nl": "Nederlands", "de": "Deutsch"}[producttaal]))
            if staat["fout"]:
                st.warning(melding(staat["fout"]) + t(" Controleer zo nodig de instellingen bij Geavanceerd."))
                return
            rapport = staat["rapport"]
            s = rapport.samenvatting()
            if s["ingevuld"]:
                st.success(t("{aantal} cellen aangevuld. {gevonden} van {totaal} artikelen gevonden.",
                             aantal=s["ingevuld"], gevonden=s["gevonden"], totaal=s["totaal"]))
                aantallen = Counter(v.kolom for r in rapport.rijen for v in r.velden if v.status == "ingevuld")
                st.caption(t("Aangevuld: ") + ", ".join(f"{naam}: {n}" for naam, n in list(aantallen.items())[:6])
                           + (t(". Meer details staan in het controleoverzicht.") if len(aantallen) > 6 else "."))
            else:
                st.info(t("0 cellen aangevuld. Er zijn geen lege velden die we met zekerheid konden invullen."))
            niet_gevonden = [r.sleutel for r in rapport.rijen if not r.match and not r.toelichting]
            if niet_gevonden:
                st.warning(t("Niet gevonden in de productbron: ") + escape(", ".join(niet_gevonden[:5]))
                           + (t(" en nog {aantal}.", aantal=len(niet_gevonden) - 5) if len(niet_gevonden) > 5 else ".")
                           + t(" Deze artikelen zijn niet aangevuld; de overige artikelen zijn wel verwerkt."))
            conflicten = [r for r in rapport.rijen if r.toelichting]
            if conflicten:
                st.warning(t("{aantal} artikelrijen hebben tegenstrijdige artikelgegevens of bronconflicten. "
                             "Deze rijen zijn niet aangevuld. Het controleoverzicht geeft uitleg.", aantal=len(conflicten)))
            if s["gaten"]:
                st.caption(t("{aantal} velden leeg gelaten omdat de brongegevens ontbreken.", aantal=s["gaten"]))
            if s["onzeker"]:
                st.caption(t("Onzekere gegevens zijn niet ingevuld. Het controleoverzicht vermeldt waarom."))
            if s["eenheid_nodig"]:
                st.warning(t("{aantal} cellen wachten op een eenheidskeuze hierboven. "
                             "De overige beschikbare gegevens zijn wel verwerkt.", aantal=s["eenheid_nodig"]))
            if s["vertaling_ontbreekt"]:
                st.warning(t("Voor {aantal} cellen ontbreekt een geldige Duitse vertaling van de huidige brontekst. "
                             "Deze teksten zijn niet ingevuld. De overige gegevens zijn wel verwerkt; "
                             "het controleoverzicht geeft uitleg.", aantal=s["vertaling_ontbreekt"]))
            naam = bestand.name.rsplit(".", 1)[0] + ("_ingevuld.xlsx" if s["ingevuld"] else "_controle.xlsx")
            st.download_button(
                t("Download ingevuld bestand" if s["ingevuld"] else "Download bestand met controleoverzicht"),
                data=staat["uit"], file_name=naam,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", on_click="ignore",
            )
            st.caption(t("Alleen beschikbare gegevens zijn gebruikt. Het controleoverzicht in Excel vermeldt de bronnen."))
            overgeslagen = [k.kolom for k in mapping.kolommen if k.doelveld == "geen"]
            if overgeslagen:
                with st.expander(t("{aantal} kolommen niet automatisch ingevuld", aantal=len(overgeslagen)), expanded=False):
                    st.write(t("Deze kolommen zijn onbekend of niet eenduidig. Bestaande inhoud is behouden. "
                               "Je kunt ze desgewenst koppelen bij Geavanceerd."))
                    for naam in overgeslagen:
                        st.text(naam)


def toon_eenheidskeuze(ws, mapping: Mapping, bestandsnaam: str, bestandssleutel: str) -> Mapping:
    """Vraag alleen ontbrekende eenheden; expliciete kolomeenheden hebben voorrang."""
    ontbrekend = ontbrekende_eenheden(mapping)
    if not ontbrekend:
        return mapping
    profiel_id = dealer_profielen.profielsleutel(ws, mapping.kopregel_index, bestandsnaam)
    try:
        profiel = dealer_profielen.laad_profiel(profiel_id) or {}
    except (ValueError, OSError):
        st.warning(t("De bewaarde eenheden konden niet worden gelezen. Kies ze hieronder opnieuw; "
                     "er wordt niets aangenomen."))
        profiel = {}
    maat_nodig = any(veld(k.doelveld).eenheid == "mm" for k in ontbrekend)
    gewicht_nodig = any(veld(k.doelveld).eenheid == "g" for k in ontbrekend)
    maat = profiel.get("maat_eenheid")
    gewicht = profiel.get("gewicht_eenheid")
    mist_keuze = (maat_nodig and maat is None) or (gewicht_nodig and gewicht is None)
    profielversie = hashlib.sha256(json.dumps(profiel, sort_keys=True).encode()).hexdigest()[:12]
    widgetsleutel = f"{bestandssleutel}_{profiel_id}_{profielversie}"
    labels = {None: "Kies eenheid", "mm": "Millimeters (mm)", "cm": "Centimeters (cm)",
              "m": "Meters (m)", "g": "Gram (g)", "kg": "Kilogram (kg)"}
    weergavelabels = {code: t(label) for code, label in labels.items()}
    with st.expander(t("Eenheden kiezen" if mist_keuze else "Eenheden wijzigen"), expanded=mist_keuze):
        st.caption(t("De kolommen zijn herkend, maar noemen geen eenheid. Kies die hier één keer. "
                     "Een eenheid die al in een kolom staat of handmatig is ingesteld, blijft gelden."))
        kolommen = st.columns(2 if maat_nodig and gewicht_nodig else 1)
        if maat_nodig:
            with kolommen[0]:
                opties = [None, "mm", "cm", "m"]
                maat = st.selectbox(t("Maten"), opties, index=opties.index(maat), format_func=weergavelabels.get,
                                    key=f"maat_{widgetsleutel}")
        if gewicht_nodig:
            with kolommen[-1]:
                opties = [None, "g", "kg"]
                gewicht = st.selectbox(t("Gewichten"), opties, index=opties.index(gewicht), format_func=weergavelabels.get,
                                       key=f"gewicht_{widgetsleutel}")
        klaar = not ((maat_nodig and maat is None) or (gewicht_nodig and gewicht is None))
        if st.button(t("Onthouden voor dit dealerformaat"), disabled=not klaar, key=f"onthoud_{widgetsleutel}"):
            try:
                dealer_profielen.bewaar_profiel(profiel_id, maat, gewicht)
                profiel = {"maat_eenheid": maat, "gewicht_eenheid": gewicht}
                st.caption(t("Eenheden onthouden voor volgende bestanden in dit dealerformaat."))
            except (ValueError, OSError):
                st.warning(t("Deze keuze wordt nu gebruikt, maar kon niet worden opgeslagen. "
                             "Bij een volgend bestand moet je de eenheden opnieuw kiezen."))
    actief = []
    if maat_nodig and maat:
        actief.append(t("maten in {eenheid}", eenheid=t(labels[maat])))
    if gewicht_nodig and gewicht:
        actief.append(t("gewichten in {eenheid}", eenheid=t(labels[gewicht])))
    bewaard = bool(profiel) and maat == profiel.get("maat_eenheid") and gewicht == profiel.get("gewicht_eenheid")
    if actief:
        st.caption(t("Voor kolommen zonder eenheid: ") + ", ".join(actief)
                   + t(". Onthouden voor dit dealerformaat." if bewaard else ". Alleen voor dit bestand gekozen."))
    return pas_eenheden_toe(mapping, maat_eenheid=maat, gewicht_eenheid=gewicht,
                           bron="Bewaarde keuze voor dit dealerformaat" if bewaard else "Keuze gebruiker in de tool")


def toon_kolomkoppelingen(ws, mapping: Mapping, artikeldata: Artikeldata, sleutel: str, versie: int) -> Mapping:
    """Bewerk optionele koppelingen met een stabiele tabel en volledige tekstweergave."""

    catalogus = catalogus_voor_prompt(artikeldata.ruwe_kolommen, artikeldata.vaste_sleutels)
    labels = {c["id"]: f"{c['label']}  [{c['id']}]" for c in catalogus}
    labelaantallen = Counter(c["label"] for c in catalogus)
    leesbare_labels = {}
    for c in catalogus:
        # Bronkoppen en interne waarden blijven ongewijzigd; alleen de bediening wordt vertaald.
        label = c["label"] if c["id"].startswith("ruw:") else t(c["label"])
        if labelaantallen[c["label"]] > 1:
            label += t(" (bronbestand)" if c["id"].startswith("ruw:") else " (productgegeven)")
        leesbare_labels[labels[c["id"]]] = label
    ids_per_label = {v: k for k, v in labels.items()}
    voorbeeld = {}
    kolomindex = koppen(ws, mapping.kopregel_index)
    for rij in ws.iter_rows(min_row=mapping.data_start_index + 1,
                            max_row=mapping.data_start_index + 3, values_only=True):
        for naam, i in kolomindex.items():
            if naam not in voorbeeld and i < len(rij) and rij[i] is not None:
                voorbeeld[naam] = str(rij[i])

    sectie(t("Kolommen koppelen"))
    st.markdown("<p class='rc-tekst'>" + t("Pas het productgegeven en de eenheid aan waar nodig. "
                "De volledige voorbeeldtekst en toelichting kun je onder de tabel bekijken.") + "</p>",
                unsafe_allow_html=True)
    tabel = pd.DataFrame([{
        "Kolom": k.kolom,
        "Doelveld": labels.get(k.doelveld, labels["geen"]),
        "Eenheid": k.eenheid or "",
        "Zekerheid": k.zekerheid,
        "Toelichting": k.toelichting,
    } for k in mapping.kolommen])
    if tabel.empty:
        st.info(t("Kies hierboven de rij met de kolomkoppen om kolommen te koppelen."))
        return mapping
    tabelhoogte = (len(tabel) + 1) * 42 + 3
    bewerkt = st.data_editor(
        tabel, hide_index=True, use_container_width=True, key=f"mapping_{sleutel}_{ws.title}_{mapping.kopregel_index}_{versie}",
        height=min(633, tabelhoogte), row_height=42,
        column_order=["Kolom", "Doelveld", "Eenheid", "Zekerheid"],
        disabled=["Kolom", "Zekerheid", "Toelichting"],
        column_config={
            "Kolom": st.column_config.TextColumn(t("Kolom in dealerbestand"), width="large"),
            "Doelveld": st.column_config.SelectboxColumn(
                t("Productgegeven"), options=list(labels.values()), required=True, width="large",
                format_func=lambda waarde: leesbare_labels.get(waarde, waarde),
            ),
            "Eenheid": st.column_config.SelectboxColumn(
                t("Eenheid"), options=[o or "" for o in EENHEID_OPTIES], width="small",
                format_func=lambda waarde: waarde or t("Bestandskeuze / niet nodig"),
            ),
            "Zekerheid": st.column_config.SelectboxColumn(t("Zekerheid"), width="small",
                                                         options=["hoog", "middel", "laag"], format_func=t),
            "Toelichting": None,
        },
    )
    st.caption(t("{aantal} koppelingen. Kies hieronder een kolom om alle tekst te lezen.", aantal=len(tabel)))
    mapping = Mapping(mapping.kopregel_index, [
        KolomMapping(r["Kolom"], ids_per_label[r["Doelveld"]], r["Eenheid"] or None, r["Zekerheid"], r["Toelichting"])
        for _, r in bewerkt.iterrows()
    ], mapping.opmerkingen, mapping.data_start_index)

    detailkolom = st.selectbox(
        t("Volledige tekst van een kolom"), [k.kolom for k in mapping.kolommen],
        format_func=lambda naam: " ".join(naam.split()),
        key=f"kolomdetails_{sleutel}_{ws.title}_{mapping.kopregel_index}_{versie}",
    )
    if detailkolom is not None:
        detail = next(k for k in mapping.kolommen if k.kolom == detailkolom)
        for titel, tekst in [
            ("Kolom in dealerbestand", detail.kolom),
            ("Productgegeven", leesbare_labels[labels[detail.doelveld]]),
            ("Voorbeeld uit het dealerbestand", voorbeeld.get(detail.kolom) or t("Geen voorbeeld ingevuld.")),
            ("Toelichting", melding(detail.toelichting) if detail.toelichting else t("Geen aanvullende toelichting.")),
        ]:
            st.caption(t(titel))
            st.markdown(f"<div class='rc-detailtekst'>{escape(tekst)}</div>", unsafe_allow_html=True)

    return mapping


if __name__ == "__main__":
    main()
