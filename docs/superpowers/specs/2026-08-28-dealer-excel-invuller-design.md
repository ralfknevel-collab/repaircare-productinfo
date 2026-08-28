# Dealer-Excel invuller — ontwerp

**Datum:** 28 augustus 2026
**Status:** concept ter review
**Repo:** Productinfo intern tool (Streamlit-app + kennisbank)

## 1. Doel

Dealers sturen regelmatig Excel-bestanden met een lijst artikelen waarvoor zij
stamdata willen hebben (douanetariefnummer, gewicht, afmetingen, land van
oorsprong, EAN, gevaarlijke-stoffen-gegevens, enzovoort). Elk bestand heeft een
eigen indeling, taal en eenheden. Het invullen gebeurt nu handmatig en kost veel
tijd.

De tool laat een medewerker zo'n bestand uploaden, herkent welke kolom om welk
gegeven vraagt, zoekt elk artikel op in de Repair Care-productdata en vult de
lege cellen in. Het resultaat is hetzelfde bestand, ingevuld, plus een
controletabblad. Bron van de data is het Product Data Sheet (Excel), eenmalig
omgezet naar een gestructureerd JSON-bestand.

Voorbeeldcase: `Primärlieferant_973184.xlsx` van Seefelder (27 artikelen;
gevraagd: Zolltarifnummer, Ursprungsland, Bundesland, Nettogewicht, Länge,
Breite, Höhe). Alle 27 artikelen zijn terug te vinden in het Product Data Sheet.

## 2. Scope

**Wel**

- Invoer: `.xlsx` en `.csv`. Meerdere tabbladen: gebruiker kiest tabblad
  (standaard het eerste tabblad met data).
- Herkenning van de indeling door Claude, met een controlestap waarin de
  gebruiker de mapping kan corrigeren voordat er iets wordt ingevuld.
- Artikel zoeken op Repair Care-artikelcode, EAN of omschrijving.
- Invullen van alle velden die in het Product Data Sheet staan, plus een klein
  aantal vaste bedrijfswaarden uit een configbestand.
- Uitvoer: origineel bestand met alleen de lege cellen gevuld, opmaak intact,
  gaten geel gemarkeerd, extra tabblad "Controle".
- Onderdeel van de bestaande Streamlit-app (zelfde wachtwoord en API-key).
- Zelfde kern ook bruikbaar als commandoregelscript.

**Niet**

- `.xls` (oud binair formaat): melding "sla op als .xlsx".
- Land van oorsprong afleiden: staat nergens in de bron. De tool laat die
  cellen leeg en markeert ze; de waarden worden later in het configbestand
  toegevoegd.
- Bestaande waarden in het dealerbestand overschrijven (alleen via een
  expliciet vinkje "ook gevulde cellen overschrijven").
- Producten die niet in het Product Data Sheet staan.

## 3. Architectuur

Vier onderdelen, elk met één taak:

```
Product Data Sheet.xlsx ──ingest_artikeldata.py──▶ artikeldata.json  (committed)
                                                        │
dealerbestand.xlsx ──▶ dealer_invuller.py ◀── vaste_waarden.json
                          │        ▲
                          │        └── mapping (Claude-voorstel + correctie gebruiker)
                          ▼
                    ingevuld.xlsx + tabblad Controle
```

| Bestand | Taak | Afhankelijk van |
|---|---|---|
| `ingest_artikeldata.py` | Leest het Product Data Sheet en schrijft `artikeldata.json`. Eenmalig, en opnieuw bij een nieuwe versie van het sheet. Geen API. | openpyxl |
| `artikeldata.json` | Gestructureerde productdata per artikelcode (zie §4). Committed, want `*.xlsx` staat in `.gitignore` en Streamlit Cloud heeft het sheet niet. | — |
| `dealer_invuller.py` | Kernmodule: dealerbestand lezen, kopregel vinden, mapping opvragen bij Claude, artikelen matchen, waarden berekenen en omrekenen, bestand schrijven. Geen Streamlit-code. Ook aan te roepen als script. | openpyxl, anthropic, artikeldata.json, vaste_waarden.json |
| `vaste_waarden.json` | Bedrijfswaarden die niet in het sheet staan (land van oorsprong, Bundesland, leveranciersgegevens). Onderhoudbaar zonder code. | — |
| `app.py` | Krijgt een keuzeknop bovenin: "Productinfo-chat" of "Dealer-Excel". De Dealer-Excel-weergave is een dunne UI-laag over `dealer_invuller.py`. | dealer_invuller |

De scheiding kern/UI maakt de kern testbaar zonder Streamlit en zonder API.

## 4. Datamodel `artikeldata.json`

```json
{
  "bron": "Product Data Sheet december 2024.xlsx",
  "gemaakt_op": "2026-08-28",
  "artikelen": {
    "2010005": {
      "artikelcode": "2010005",
      "omschrijving": "DRY FIX UNI",
      "ean": "8714748004368",
      "status": "Actief",
      "productgroep": "150, DRY FIX",
      "gn_code": "32141010",
      "min_verkoophoeveelheid": 10,
      "componenten": [
        {"naam": "A", "inhoud": "200 ml", "netto_g": 222, "bruto_g": 243,
         "maat_mm": {"vorm": "rond", "diameter": 48, "hoogte": 184},
         "un_code": "3082", "klasse": "9", "verpakkingsgroep": "III", "..." : "..."},
        {"naam": "B", "inhoud": "100 ml", "netto_g": 96, "bruto_g": 117,
         "maat_mm": {"vorm": "rond", "diameter": 41, "hoogte": 145}, "...": "..."}
      ],
      "netto_g": 318,
      "bruto_g": 360,
      "maat_mm": {"l": 89, "b": 48, "h": 184, "regel": "A+B naast elkaar"},
      "collo_mm": {"l": 180, "b": 226, "h": 200},
      "omdoos_cm": {"l": 39, "b": 26, "h": 42},
      "ghs": ["GHS07", "GHS05", "GHS09"],
      "pallet": {"afmeting_cm": "80x120x99", "stuks": 720, "...": "..."},
      "ruw": {"<originele kolomnaam>": "<originele celwaarde>", "...": "..."}
    }
  }
}
```

Regels bij het inlezen:

- Artikelcode altijd als string (in het sheet staan zowel getallen als teksten).
- EAN: twee cellen (`87.14748.` + `00436.8`) samenvoegen, alleen cijfers.
- GN-code: alleen cijfers (`3214 10 10` → `32141010`; 10-cijferige codes blijven
  10 cijfers).
- Componentrijen (rij zonder artikelcode direct onder een artikel) horen bij
  het artikel erboven. Waarden met prefix `A:`/`B:` worden aan het juiste
  component toegewezen; de prefix wordt gestript.
- Gewicht per artikel = som van de componenten. Bruto idem.
- Afmetingen per stuk: `LxBxH` → l/b/h; `Ø: 48 H: 184` → rond, l = b = 48;
  tweecomponentproduct → l = ØA + ØB, b = grootste Ø, h = grootste hoogte,
  met `regel` erbij zodat de Controle-tab kan uitleggen waar het getal vandaan
  komt; `n.v.t.`, `--` of leeg → geen afmeting.
- Alle originele kolommen blijven bewaard onder `ruw`, zodat ook velden die
  niet apart gemodelleerd zijn (UFI, VOC, vlampunt, palletgegevens…) via de
  mapping bereikbaar zijn.
- Omschrijving-index voor fuzzy zoeken wordt bij het laden opgebouwd, niet
  opgeslagen.

## 5. Veldcatalogus

Een vaste lijst doelvelden, in code gedefinieerd, met per veld: id, label,
standaardeenheid en korte uitleg. Deze lijst gaat naar Claude als
keuzemenu en vult de dropdowns in de controlestap. Kernvelden:

| id | label | eenheid | bron |
|---|---|---|---|
| `sleutel_artikelcode` | Repair Care-artikelnummer | — | sleutelkolom |
| `sleutel_ean` | EAN-13 | — | sleutelkolom |
| `sleutel_omschrijving` | Omschrijving (fuzzy) | — | sleutelkolom |
| `gn_code` | Douanetariefnummer (GN/HS) | — | artikel |
| `netto_gewicht` | Nettogewicht per stuk | g (of kg) | artikel, som componenten |
| `bruto_gewicht` | Brutogewicht per stuk | g (of kg) | artikel |
| `lengte`, `breedte`, `hoogte` | Afmeting per stuk | mm (of cm, m) | artikel |
| `collo_lengte` … | Afmeting verpakkingseenheid | mm (of cm) | artikel |
| `ean` | EAN-13 | — | artikel |
| `omschrijving` | Productnaam | — | artikel |
| `min_verkoophoeveelheid` | Minimale afname | stuks | artikel |
| `un_code`, `klasse`, `verpakkingsgroep`, `adr_naam`, `vlampunt`, `ufi`, `voc`, `ghs` | Gevaarlijke stoffen | — | component A (met B in Controle-tab) |
| `ruw:<kolomnaam>` | Elke overige kolom uit het sheet | — | `ruw` |
| `vast:<sleutel>` | Waarde uit `vaste_waarden.json` | — | config |
| `geen` | Kolom niet invullen | — | — |

De catalogus is de enige plek waar velden worden gedefinieerd; ingest, mapping
en invullen gebruiken dezelfde lijst.

## 6. Mapping door Claude

**Invoer naar het model**

- Systeemprompt: rol, de veldcatalogus (als JSON), regels. Stabiel, dus met
  `cache_control` gecachet.
- Gebruikersbericht: naam van het tabblad, de eerste ~10 rijen van het
  dealerbestand als tabel (kopregel-kandidaten plus voorbeeldrijen), aantal
  rijen totaal. Er gaat dus alleen een klein fragment naar de API, niet het
  hele bestand.

**Uitvoer** (afgedwongen via `output_config.format` met JSON-schema):

```json
{
  "kopregel_index": 0,
  "sleutelkolommen": [
    {"kolom": "HerstellerArtNr", "type": "sleutel_artikelcode"},
    {"kolom": "EAN13", "type": "sleutel_ean"}
  ],
  "kolommen": [
    {"kolom": "Zolltarifnummer", "doelveld": "gn_code", "eenheid": null,
     "zekerheid": "hoog", "toelichting": "Duits voor douanetariefnummer"},
    {"kolom": "Nettogewicht", "doelveld": "netto_gewicht", "eenheid": "g",
     "zekerheid": "middel", "toelichting": "Eenheid niet in kop; mail vraagt gram"},
    {"kolom": "Ursprungsland", "doelveld": "vast:ursprungsland", "eenheid": null,
     "zekerheid": "hoog", "toelichting": ""},
    {"kolom": "ArtBeschreibung", "doelveld": "geen", "eenheid": null,
     "zekerheid": "hoog", "toelichting": "Al gevuld door dealer"}
  ],
  "opmerkingen": "Bundesland alleen relevant als land DEU is."
}
```

**Instellingen:** model `claude-opus-5`, adaptieve thinking (standaard),
`max_tokens` 8000, één aanroep per bestand. Verwachte kosten: enkele centen
per bestand.

**Zonder API of bij een fout:** de controlestap opent met alle kolommen op
`geen`; de gebruiker kiest zelf. De tool blijft dus bruikbaar.

## 7. Controlestap (UI)

Na upload en mapping toont de app een tabel met per dealerkolom: kolomnaam,
voorbeeldwaarde, doelveld (dropdown), eenheid (dropdown), zekerheid,
toelichting. Rijen met zekerheid "laag" of "middel" zijn gemarkeerd. De
gebruiker past aan en klikt "Invullen".

Daarbij toont de app alvast het matchresultaat: "25 van 27 artikelen gevonden
(23 op artikelnummer, 2 op EAN); niet gevonden: …". Zo is vóór het invullen
duidelijk of de sleutelkolom klopt.

Opties: vinkje "ook gevulde cellen overschrijven" (standaard uit); keuze
tabblad bij meerdere tabbladen.

## 8. Invullen

1. Bestand openen met openpyxl (opmaak, kolombreedtes en overige tabbladen
   blijven intact). CSV wordt eerst naar een nieuw werkboek gezet.
2. Per datarij (onder de kopregel, rijen zonder enige waarde overslaan):
   artikel zoeken via de sleutelkolommen, in volgorde artikelcode → EAN →
   omschrijving. Codes worden genormaliseerd (string, spaties weg, alleen
   cijfers voor EAN). Een sleutelwaarde `0` of leeg telt als ontbrekend.
   Omschrijving-match met `difflib`-ratio ≥ 0,85 telt als "controleer".
3. Per gemapte kolom: waarde ophalen, omrekenen naar de eenheid uit de mapping
   (g↔kg, mm↔cm↔m), getallen als getal schrijven, tekst als tekst. Alleen
   schrijven als de cel leeg is (tenzij overschrijven aan staat).
4. Geen waarde beschikbaar → cel blijft leeg en krijgt een gele vulling.
   Artikel niet gevonden → alle doelcellen van die rij geel.
5. Tabblad "Controle" toevoegen: per rij artikelcode, gevonden-via, en per
   ingevuld veld de bron en rekenregel ("netto = A 222 g + B 96 g";
   "L = ØA 48 + ØB 41"); bovenaan een samenvatting (gevonden, niet gevonden,
   gaten per veld). Bestaat het tabblad al, dan wordt het vervangen.
6. Resultaat in geheugen als bytes → downloadknop `<naam>_ingevuld.xlsx`.

## 9. Vaste waarden

`vaste_waarden.json`:

```json
{
  "ursprungsland": {"label": "Land van oorsprong (ISO-3)", "standaard": null,
                    "per_prefix": {}, "per_artikel": {}},
  "bundesland":    {"label": "Duits Bundesland", "standaard": null,
                    "per_prefix": {}, "per_artikel": {}},
  "leverancier_naam": {"label": "Leverancier", "standaard": "Repair Care International B.V."}
}
```

Volgorde bij opzoeken: `per_artikel` → `per_prefix` (langste passende prefix
van de artikelcode) → `standaard`. `null` betekent: leeg laten en geel
markeren. Zo kan het land van oorsprong later per artikel of per artikelgroep
(bijvoorbeeld prefix `2` voor de chemie) worden toegevoegd zonder code te
wijzigen.

## 10. Foutafhandeling

| Situatie | Gedrag |
|---|---|
| Geen kopregel herkend | Gebruiker kiest de kopregel handmatig (dropdown met eerste 10 rijen). |
| API-fout of geen API-key | Melding; mapping start leeg; handmatig kiezen blijft mogelijk. |
| Geen sleutelkolom gekozen | Invullen geblokkeerd met melding. |
| 0 artikelen gevonden | Waarschuwing vóór invullen; invullen mag wel. |
| `.xls` of ander formaat | Melding: sla op als `.xlsx`. |
| `artikeldata.json` ontbreekt | Melding: draai `python3 ingest_artikeldata.py`. |
| Product Data Sheet gewijzigd van kolomnamen | Ingest stopt met een lijst van ontbrekende verwachte kolommen. |

## 11. Testen

`pytest` (toevoegen aan een `requirements-dev.txt`). Tests draaien zonder API
en zonder het echte Product Data Sheet:

- **Ingest:** kleine fixture-Excel met drie artikelen (rond enkel, A+B, LxBxH,
  ontbrekende waarden) → verwacht JSON. Aparte test op het echte sheet die
  wordt overgeslagen als het bestand ontbreekt (controleert onder meer:
  167 artikelen, DRY FIX UNI netto 318 g, GN-code 32141010).
- **Matching:** artikelcode als int en string, EAN met punten, `0` als
  ontbrekend, fuzzy omschrijving met en zonder drempel.
- **Omrekenen:** g↔kg, mm↔cm, afronding.
- **Invullen:** fixture-dealerbestanden in drie varianten (Duits zoals
  Seefelder, Engels, Nederlands met kg/cm) met een handmatig aangeleverde
  mapping → cellen gevuld, bestaande waarden ongemoeid, gaten geel, Controle-
  tab aanwezig, opmaak behouden.
- **Mapping-schema:** het JSON-schema valideert een goed voorbeeld en wijst
  een onbekend doelveld af.
- **Claude-mapping:** één handmatige rooktest op het Seefelder-bestand
  (gemarkeerd, niet in de standaard testrun).

Werkwijze: test-driven — per onderdeel eerst de test, dan de code.

## 12. Uitrol

- `artikeldata.json` en `vaste_waarden.json` committen; `ingest_artikeldata.py`
  in de README opnemen als stap 1c.
- Geen nieuwe runtime-afhankelijkheden (openpyxl, anthropic en pydantic zijn
  al aanwezig). Python 3.9-compatibel houden (venv draait 3.9.6).
- Streamlit Cloud: geen extra secrets nodig.

## 13. Open punten

- Land van oorsprong: door Ralf later in te vullen in `vaste_waarden.json`.
- Voor kits (bijvoorbeeld "Holzreparatur Box 5") ontbreekt de GN-code in het
  sheet; de tool laat de cel leeg en markeert hem. Aanvulling hoort in het
  Product Data Sheet, niet in de tool.
- Als dealers in de praktijk vaak `.xls` sturen, later alsnog ondersteunen
  (extra afhankelijkheid `xlrd`).
