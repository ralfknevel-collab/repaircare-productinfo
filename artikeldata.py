"""
Toegang tot artikeldata.json en vaste_waarden.json: artikel zoeken op
artikelcode, EAN of omschrijving, en per doelveld de waarde met bron en
rekenregel teruggeven.
"""

from __future__ import annotations

import difflib
import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from documentdata import VOORKEUR_PRODUCTBLAD
from prijslijst import lees_prijslijst
from veldcatalogus import veld

FUZZY_DREMPEL = 0.85
BASE_DIR = Path(__file__).resolve().parent
ARTIKELDATA_FILE = BASE_DIR / "artikeldata.json"
VASTE_WAARDEN_FILE = BASE_DIR / "vaste_waarden.json"
PRIJSLIJST_FILE = BASE_DIR / "data" / "verkoopadviesprijzen_2026.csv"


@dataclass
class Match:
    artikel: dict
    via: str      # artikelcode | ean | omschrijving
    score: float  # 1.0 bij exacte match


@dataclass
class Waarde:
    waarde: object
    eenheid: str | None
    bron: str
    regel: str | None = None
    eenduidig: bool = True
    onzeker_reden: str | None = None


@dataclass(frozen=True)
class ComponentMaten:
    """Afzonderlijke bronmaten met hun componentnaam, nog zonder tekstconversie."""
    waarden: tuple[tuple[str, float], ...]


def _componentmaat(artikel: dict, as_: str) -> Waarde:
    """Een berekende setopstelling vervangen door de werkelijk bekende componentmaten."""
    bron = "Product Data Sheet, componentmaten"
    componenten = artikel.get("componenten") or []
    if len(componenten) < 2:
        return Waarde(None, "mm", bron, eenduidig=False,
                      onzeker_reden="Componentmaten ontbreken of zijn onvolledig voor deze set.")
    waarden = []
    namen = set()
    for component in componenten:
        naam = component.get("naam")
        if not isinstance(naam, str) or not naam.strip() or naam.strip().casefold() in namen:
            return Waarde(None, "mm", bron, eenduidig=False,
                          onzeker_reden="Componentnamen ontbreken of zijn dubbel; maten niet veilig te koppelen.")
        naam = naam.strip()
        namen.add(naam.casefold())
        maat = component.get("maat_mm") or {}
        getal = maat.get(as_)
        if (maat.get("vorm") == "samengesteld" or isinstance(getal, bool)
                or not isinstance(getal, (int, float)) or not math.isfinite(getal) or getal <= 0):
            return Waarde(None, "mm", bron, eenduidig=False,
                          onzeker_reden=f"Deze maat ontbreekt of is onbruikbaar voor component {naam}.")
        waarden.append((naam, getal))
    waarden.sort(key=lambda paar: paar[0].casefold())
    bron = "Product Data Sheet, componenten " + " en ".join(naam for naam, _ in waarden)
    regel = "Componentmaten apart weergegeven, geen totale setmaat: " + " / ".join(
        f"{naam}: {getal:g} mm" for naam, getal in waarden
    ) + "."
    return Waarde(ComponentMaten(tuple(waarden)), "mm", bron, regel)


def doosinhoud(artikel: dict) -> int | None:
    """Lees stuks per doos uit 'aantal dozen x stuks'; minimale afname is geen doosinhoud."""
    inhoud = artikel.get("ruw", {}).get("Inhoud (om)doos")
    if not isinstance(inhoud, str):
        return None
    match = re.fullmatch(r"\s*([1-9][0-9]*)\s*[xX×]\s*([1-9][0-9]*)\s*", inhoud)
    return int(match[2]) if match else None


def _positief_getal(waarde) -> float | None:
    """Alleen volledige, positieve en eindige getallen; geen vrije tekst wegpoetsen."""
    if isinstance(waarde, bool):
        return None
    if isinstance(waarde, str):
        if not re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", waarde.strip()):
            return None
        waarde = float(waarde.strip().replace(",", "."))
    if not isinstance(waarde, (int, float)) or not math.isfinite(waarde) or waarde <= 0:
        return None
    return float(waarde)


def _ontbrekende_doosbron(waarde) -> bool:
    return waarde is None or (isinstance(waarde, str) and waarde.strip() in ("", "-", "--"))


def _doosgewicht(artikel: dict, veld_id: str) -> Waarde | None:
    netto = veld_id == "collo_netto_gewicht"
    kolom = ("Netto" if netto else "Bruto") + " gewicht per doos (kg)"
    bron = "Product Data Sheet, kolom " + kolom

    def onzeker(reden: str) -> Waarde:
        return Waarde(None, "g", bron, eenduidig=False, onzeker_reden=reden)

    ruw = artikel.get("ruw", {}).get(kolom)
    direct = _positief_getal(ruw)
    if direct is not None:
        # Een ongelabeld artikelgetal is het totale doosgewicht, geen component A.
        return Waarde(round(direct * 1000, 6), "g", bron,
                      f"Doosbron: {direct:g} kg × 1000 = {direct * 1000:g} g per doos.")

    componenten = artikel.get("componenten") or []
    bronnen = [(None, ruw)] + [(c.get("naam"), c.get("ruw", {}).get(kolom)) for c in componenten]
    aanwezig = [(naam, waarde) for naam, waarde in bronnen if not _ontbrekende_doosbron(waarde)]
    if aanwezig:
        namen = [c.get("naam") for c in componenten]
        if (not namen or any(naam not in ("A", "B") for naam in namen)
                or len(set(namen)) != len(namen) or set(namen) != {"A", "B"}):
            return onzeker("Componentnamen voor het doosgewicht ontbreken of zijn niet eenduidig A en B.")
        gewichten = {}
        for eigenaar, waarde in aanwezig:
            match = re.fullmatch(r"\s*([AB])\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*", waarde) if isinstance(waarde, str) else None
            if match is None:
                return onzeker("Doosgewicht is geen geldig getal of gelabeld componentgewicht in kg.")
            naam, getal = match[1], _positief_getal(match[2])
            if getal is None or (eigenaar is not None and naam != eigenaar):
                return onzeker("Label of getal van het componentdoosgewicht klopt niet met de broncomponent.")
            if naam in gewichten and gewichten[naam] != getal:
                return onzeker(f"Tegenstrijdige doosgewichten voor component {naam}.")
            gewichten[naam] = getal
        if set(gewichten) != {"A", "B"}:
            return onzeker("Doosgewicht ontbreekt voor een component; een gedeeltelijke som wordt niet ingevuld.")
        totaal = round(sum(gewichten.values()) * 1000, 6)
        regel = "Som componentdoosgewichten: " + " + ".join(
            f"{naam}: {gewichten[naam]:g} kg" for naam in ("A", "B")
        ) + f" = {totaal / 1000:g} kg = {totaal:g} g per doos."
        return Waarde(totaal, "g", bron + ", componenten A en B", regel)

    # Alleen netto is uit stukgewichten af te leiden; bruto mist anders de doosverpakking.
    aantal = doosinhoud(artikel) if netto else None
    stukgewicht = _positief_getal(artikel.get("netto_g")) if netto else None
    if aantal is None or stukgewicht is None:
        return None
    if componenten:
        gewichten = [_positief_getal(c.get("netto_g")) for c in componenten]
        namen = [c.get("naam") for c in componenten]
        if (any(gewicht is None for gewicht in gewichten) or any(naam not in ("A", "B") for naam in namen)
                or len(set(namen)) != len(namen)
                or not math.isclose(sum(gewichten), stukgewicht, rel_tol=1e-9, abs_tol=1e-6)):
            return onzeker("Stukgewicht is niet aantoonbaar de volledige, eenduidige som van de componenten.")
    totaal = round(stukgewicht * aantal, 6)
    return Waarde(totaal, "g", "Product Data Sheet, nettogewicht per stuk en Inhoud (om)doos",
                  f"Afgeleid uit {stukgewicht:g} g per stuk × {aantal} stuks per doos = {totaal:g} g per doos.")


def normaliseer_code(x) -> str | None:
    if x is None:
        return None
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    s = str(x).strip()
    if s == "" or s == "0":
        return None
    return s


def normaliseer_ean(x) -> str | None:
    if x is None:
        return None
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    cijfers = re.sub(r"\D", "", str(x))
    return cijfers if len(cijfers) in (8, 13) else None


def _normaliseer_tekst(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _als_tekst(w):
    """Lijstwaarden (zoals GHS-codes) als één leesbare string."""
    return ", ".join(w) if isinstance(w, list) else w


def _productwaarde(veld_id: str, waarde, bron: str) -> Waarde:
    """Een kleuropsomming bewijst geen enkele kleur voor dit specifieke artikel."""
    tekst = _als_tekst(waarde)
    if veld_id == "kleur" and isinstance(tekst, str) and re.search(
        r"[,;/\n&+]|\b(?:en|of|und|oder|and|or|component(?:en|s)?|komponenten?)\b|\b[AB]\s*[:=]",
        tekst, re.IGNORECASE,
    ):
        return Waarde(tekst, None, bron, eenduidig=False,
                      onzeker_reden="Kleurbron bevat meerdere kleuren, keuzes of componenten; artikelkleur is onzeker.")
    return Waarde(tekst, None, bron)


def vaste_waarde(vaste: dict, sleutel: str, artikelcode: str) -> str | None:
    regel = vaste.get(sleutel)
    if not regel:
        return None
    per_artikel = regel.get("per_artikel") or {}
    if artikelcode in per_artikel:
        return per_artikel[artikelcode]
    per_prefix = regel.get("per_prefix") or {}
    for prefix in sorted(per_prefix, key=len, reverse=True):
        if artikelcode.startswith(prefix):
            return per_prefix[prefix]
    return regel.get("standaard")


# veld-id -> (artikelsleutel, eenheid, regelsleutel)
_ARTIKELVELDEN = {
    "gn_code": ("gn_code", None, None),
    "netto_gewicht": ("netto_g", "g", "netto_regel"),
    "bruto_gewicht": ("bruto_g", "g", "bruto_regel"),
    "ean": ("ean", None, None),
    "omschrijving": ("omschrijving", None, None),
    "min_verkoophoeveelheid": ("min_verkoophoeveelheid", "stuks", None),
}
_MAATVELDEN = {
    "lengte": ("maat_mm", "l"), "breedte": ("maat_mm", "b"), "hoogte": ("maat_mm", "h"),
    "collo_lengte": ("collo_mm", "l"), "collo_breedte": ("collo_mm", "b"), "collo_hoogte": ("collo_mm", "h"),
}
_COMPONENTVELDEN = {"un_code", "klasse", "verpakkingsgroep", "adr_naam", "vlampunt", "ufi", "voc", "ghs"}
_PRIJSVELDEN = {
    "adviesprijs": "adviesprijs_cent", "adviesprijs_eenheid": "eenheid",
    "ve_aantal": "ve_aantal", "prijslijst_omschrijving": "omschrijving",
}


def _prijslijst_bron(prijs: dict) -> str:
    return f"{prijs['bron']}, rij {prijs['bronregel']}"


def _prijsregel(prijs: dict) -> str:
    eenheid = "stuk" if prijs["eenheid"] == "st" else "set"
    return (f"Adviesprijs in {prijs['valuta']}, exclusief btw, per {eenheid}; "
            f"geldig van {prijs['geldig_vanaf']} tot en met {prijs['geldig_tot']}.")


def _prijs_geldigheidsreden(prijs: dict) -> str | None:
    vandaag = date.today()
    if vandaag < date.fromisoformat(prijs["geldig_vanaf"]):
        return f"Prijslijst is nog niet geldig: prijzen gelden vanaf {prijs['geldig_vanaf']}."
    if vandaag > date.fromisoformat(prijs["geldig_tot"]):
        return f"Prijslijst is verlopen: prijzen waren geldig tot en met {prijs['geldig_tot']}."
    return None


class Artikeldata:
    def __init__(self, data: dict, vaste_waarden: dict | None = None, prijslijst: dict | None = None):
        # Aanvullingen bestaan alleen in het geheugen; de technische bron blijft ongewijzigd.
        self.artikelen: dict[str, dict] = deepcopy(data["artikelen"]) if prijslijst is not None else data["artikelen"]
        self.ruwe_kolommen: list[str] = list(data.get("ruwe_kolommen", []))
        self.vaste: dict = vaste_waarden or {}
        self.vaste_sleutels: dict[str, str] = {k: v.get("label", k) for k, v in self.vaste.items()}
        self.bron_meldingen: list[str] = []
        self.prijslijst_info: dict = {}
        if prijslijst is not None:
            self._koppel_prijslijst(prijslijst)
        self._op_ean = {a["ean"]: a for a in self.artikelen.values()
                        if a.get("ean") and not (a.get("alleen_prijslijst") and a.get("bron_conflicten"))}
        self._omschrijvingen = {_normaliseer_tekst(a["omschrijving"]): a
                                for a in self.artikelen.values() if a.get("omschrijving")}

    @classmethod
    def laad(cls, pad_json: Path | None = None, pad_vast: Path | None = None,
             pad_prijslijst: Path | None = None) -> "Artikeldata":
        # Defaults hier oplossen (niet in de signatuur) zodat tests de module-constanten kunnen vervangen.
        if pad_json is None and pad_prijslijst is None:
            pad_prijslijst = PRIJSLIJST_FILE
        pad_json = pad_json or ARTIKELDATA_FILE
        pad_vast = pad_vast or VASTE_WAARDEN_FILE
        data = json.loads(Path(pad_json).read_text(encoding="utf-8"))
        vaste = None
        if Path(pad_vast).exists():
            vaste = json.loads(Path(pad_vast).read_text(encoding="utf-8"))
        prijslijst = None
        melding = None
        if pad_prijslijst is not None:
            try:
                prijslijst = lees_prijslijst(Path(pad_prijslijst))
            except (OSError, ValueError) as fout:
                melding = (f"Aanvullende prijslijst {Path(pad_prijslijst).name} kon niet worden geladen: {fout}. "
                           "Alleen de productdatasheet wordt gebruikt.")
        resultaat = cls(data, vaste, prijslijst)
        if melding:
            resultaat.bron_meldingen.append(melding)
        return resultaat

    def _koppel_prijslijst(self, prijslijst: dict) -> None:
        metadata = {sleutel: prijslijst[sleutel] for sleutel in
                    ("bron", "geldig_vanaf", "geldig_tot", "valuta", "btw")}
        self.prijslijst_info = {**metadata, "aantal_artikelen": len(prijslijst["artikelen"]), "toegevoegd": 0}
        self.bron_meldingen.extend(prijslijst.get("meldingen", []))
        geldigheidsreden = _prijs_geldigheidsreden(metadata)
        if geldigheidsreden:
            self.bron_meldingen.append(geldigheidsreden)
        pds_eans: dict[str, list[str]] = {}
        for code, artikel in self.artikelen.items():
            if artikel.get("ean"):
                pds_eans.setdefault(artikel["ean"], []).append(code)

        def conflict(codes: list[str], reden: str) -> None:
            if reden not in self.bron_meldingen:
                self.bron_meldingen.append(reden)
            for code in codes:
                conflicten = self.artikelen[code].setdefault("bron_conflicten", [])
                if reden not in conflicten:
                    conflicten.append(reden)

        for code, prijs in prijslijst["artikelen"].items():
            nieuw = code not in self.artikelen
            if nieuw:
                self.artikelen[code] = {"artikelcode": code, "omschrijving": prijs["omschrijving"],
                                        "alleen_prijslijst": True}
                if prijs.get("ean"):
                    self.artikelen[code]["ean"] = prijs["ean"]
                self.prijslijst_info["toegevoegd"] += 1
            artikel = self.artikelen[code]
            artikel["prijslijst"] = {**metadata, **deepcopy(prijs)}
            # De prijslijst is de bevestigde bron voor alle productomschrijvingen die daarin staan.
            artikel["omschrijving"] = prijs["omschrijving"]
            bron_ean = artikel.get("ean")
            prijs_ean = prijs.get("ean")
            andere_codes = [ander for ander in pds_eans.get(prijs_ean, []) if ander != code]
            if not nieuw and bron_ean and prijs_ean and bron_ean != prijs_ean:
                # Ralf bevestigde op 7 september 2026 alleen dit bronpaar voor dit artikel.
                if (code, bron_ean, prijs_ean) == ("2023005", "8714748002616", "8714748004740") and not andere_codes:
                    regel = (f"Artikel {code}: EAN {prijs_ean} uit de prijslijst is leidend, "
                             f"bevestigd door Ralf op 2026-09-07. EAN in de productdatasheet: {bron_ean}. "
                             "Technische gegevens blijven uit de productdatasheet komen.")
                    artikel["ean"] = prijs_ean
                    artikel["ean_bronkeuze"] = {"pds_ean": bron_ean, "bron": _prijslijst_bron(artikel["prijslijst"]),
                                                "regel": regel}
                    self.bron_meldingen.append(regel)
                else:
                    conflict([code], f"Artikel {code}: EAN {bron_ean} in de productdatasheet wijkt af van "
                                     f"EAN {prijs_ean} in {metadata['bron']}. Niet automatisch invullen.")
            if andere_codes:
                conflict([code, *andere_codes], f"EAN {prijs_ean} uit {metadata['bron']} hoort daar bij artikel {code}, "
                         f"maar in de productdatasheet bij artikel {', '.join(andere_codes)}. Niet automatisch invullen.")

    def zoek(self, artikelcode=None, ean=None, omschrijving=None) -> Match | None:
        code = normaliseer_code(artikelcode)
        if code and code in self.artikelen:
            return Match(self.artikelen[code], "artikelcode", 1.0)
        e = normaliseer_ean(ean)
        if e and e in self._op_ean:
            return Match(self._op_ean[e], "ean", 1.0)
        if omschrijving:
            doel = _normaliseer_tekst(str(omschrijving))
            if doel:
                kandidaten = difflib.get_close_matches(doel, self._omschrijvingen.keys(), n=1, cutoff=FUZZY_DREMPEL)
                if kandidaten:
                    score = difflib.SequenceMatcher(None, doel, kandidaten[0]).ratio()
                    return Match(self._omschrijvingen[kandidaten[0]], "omschrijving", score)
        return None

    def waarde(self, artikel: dict, veld_id: str) -> Waarde | None:
        v = veld(veld_id)
        if v is None or v.soort in ("geen", "sleutel"):
            return None
        code = artikel.get("artikelcode", "")
        if v.soort == "ruw":
            w = artikel.get("ruw", {}).get(v.label)
            return Waarde(w, None, "Product Data Sheet, kolom " + v.label) if w is not None else None
        if v.soort == "vast":
            w = vaste_waarde(self.vaste, v.label, code)
            return Waarde(w, None, "vaste_waarden.json: " + v.label) if w is not None else None
        if veld_id in _PRIJSVELDEN:
            prijs = artikel.get("prijslijst")
            if not prijs:
                return None
            bron, regel = _prijslijst_bron(prijs), _prijsregel(prijs)
            if veld_id == "adviesprijs":
                reden = " ".join(artikel.get("bron_conflicten", [])) or _prijs_geldigheidsreden(prijs)
                if reden:
                    return Waarde(None, "EUR", bron, regel, eenduidig=False, onzeker_reden=reden)
                return Waarde(prijs["adviesprijs_cent"] / 100, "EUR", bron, regel)
            if veld_id == "ve_aantal":
                regel += " VE is het commerciële aantal in deze eenheid, geen doosinhoud of minimale afname."
            return Waarde(prijs[_PRIJSVELDEN[veld_id]], None, bron, regel)
        if veld_id in ("collo_netto_gewicht", "collo_bruto_gewicht"):
            return _doosgewicht(artikel, veld_id)
        if veld_id in _ARTIKELVELDEN:
            sleutel, eenheid, regelsleutel = _ARTIKELVELDEN[veld_id]
            if sleutel not in artikel:
                return None
            if veld_id == "ean" and artikel.get("ean_bronkeuze"):
                keuze = artikel["ean_bronkeuze"]
                return Waarde(artikel[sleutel], eenheid, keuze["bron"], keuze["regel"])
            if veld_id == "omschrijving" and artikel.get("prijslijst"):
                return Waarde(artikel[sleutel], eenheid, _prijslijst_bron(artikel["prijslijst"]),
                              "Omschrijving uit de prijslijst is leidend, bevestigd door Ralf op 2026-09-07.")
            if artikel.get("alleen_prijslijst") and veld_id == "ean":
                prijs = artikel["prijslijst"]
                return Waarde(artikel[sleutel], eenheid, _prijslijst_bron(prijs), _prijsregel(prijs))
            return Waarde(artikel[sleutel], eenheid, "Product Data Sheet",
                          artikel.get(regelsleutel) if regelsleutel else None)
        if veld_id in _MAATVELDEN:
            maatsleutel, as_ = _MAATVELDEN[veld_id]
            maat = artikel.get(maatsleutel)
            if maatsleutel == "maat_mm" and maat and maat.get("vorm") == "samengesteld":
                return _componentmaat(artikel, as_)
            if not maat or as_ not in maat:
                return None
            regel = maat.get("regel")
            if maat.get("vorm") == "rond" and as_ in ("l", "b"):
                regel = f"ronde verpakking: L = B = Ø {maat['diameter']:g} mm"
            if maat.get("vorm") == "samengesteld":
                return Waarde(maat[as_], "mm", "Product Data Sheet", regel, eenduidig=False,
                              onzeker_reden="Berekende opstelling van componenten, geen gemeten setverpakking.")
            return Waarde(maat[as_], "mm", "Product Data Sheet", regel)
        if veld_id in _COMPONENTVELDEN or v.soort == "document":
            # Volgorde: PDS op artikelniveau (samengevoegd, bv. GHS-unie) -> per
            # component (PDS, anders product-/veiligheidsblad) -> document op artikelniveau.
            if veld_id in artikel:
                return _productwaarde(veld_id, artikel[veld_id], "Product Data Sheet")
            doc = artikel.get("documenten", {}).get(veld_id)
            # Toepassingsvelden (dichtheid, kleur, opslagtemperatuur, ...): het productblad
            # beschrijft het product als geheel en gaat vóór losse componentwaarden uit de SDS.
            if doc is not None and veld_id in VOORKEUR_PRODUCTBLAD:
                return _productwaarde(veld_id, doc["waarde"], doc["bron"])
            houders = []  # (componentnaam, waarde, bron)
            for c in artikel.get("componenten", []):
                if veld_id in c:
                    houders.append((c["naam"], _als_tekst(c[veld_id]), "Product Data Sheet"))
                elif veld_id in c.get("documenten", {}):
                    d = c["documenten"][veld_id]
                    houders.append((c["naam"], _als_tekst(d["waarde"]), d["bron"]))
            if not houders:
                if doc is None:
                    return None
                return _productwaarde(veld_id, doc["waarde"], doc["bron"])
            naam, w, bronnaam = houders[0]
            afwijkend = [(n, x) for n, x, _ in houders[1:] if x != w]
            bron = f"{bronnaam}, component {naam}"
            regel = None
            if afwijkend:
                # Het dealerbestand krijgt alleen de waarde van het eerste component;
                # de rest komt zo in de Controle-tab terecht.
                regel = "ook " + ", ".join(f"{n}: {x}" for n, x in afwijkend)
                werkwoord = "wijkt af" if len(afwijkend) == 1 else "wijken af"
                bron += " (" + ", ".join(n for n, _ in afwijkend) + f" {werkwoord})"
            # Een losse componentkleur bewijst ook bij gelijke componenten niet
            # welke kleur het gemengde product heeft.
            onzeker_reden = None
            if veld_id == "kleur":
                onzeker_reden = "Componentkleur is geen eenduidige kleur van het totale product."
            elif afwijkend:
                onzeker_reden = "Componentwaarden geven geen eenduidige productwaarde."
            return Waarde(w, None, bron, regel, eenduidig=onzeker_reden is None, onzeker_reden=onzeker_reden)
        return None
