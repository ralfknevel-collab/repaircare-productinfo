# Repair Care Dealerbestanden

Interne tool die dealerbestanden invult met Repair Care-productgegevens.
Upload een Excel- of CSV-bestand en download direct het resultaat met een
controletabblad. Bekende gegevens worden automatisch lokaal aangevuld.

## Wat zit erin

- `ingest.py`: leest alle PDF's en bouwt `kennisbank.json`.
- `app.py`: Streamlit-app voor het invullen van dealerbestanden.
- `kennisbank.json`: documentgegevens voor het opbouwen van de artikeldata.
  Dit bestand is niet nodig om de app te openen wanneer `artikeldata.json` al bestaat.

Voor de dealer-Excel invuller:

- `ingest_artikeldata.py` — zet het Product Data Sheet om naar `artikeldata.json`.
- `artikeldata.json` — gegenereerde productdata per artikelcode (gecommit).
- `veldcatalogus.py` — de doelvelden en hun eenheden; één bron voor prompt, UI en invullen.
- `artikeldata.py` — artikel zoeken (artikelnummer, EAN, omschrijving) en waarden opvragen.
- `mapping.py` — datamodel en Claude-aanroep voor kolom → doelveld.
- `dealer_invuller.py` — kern (kopregel, matchen, invullen, Controle-tab) en CLI.
- `dealer_profielen.py`: bewaart gekozen eenheden lokaal per dealerformaat.
- `vaste_waarden.json` — bedrijfsgegevens die niet in het sheet staan (land van
  oorsprong, Bundesland).

## Installatie (eenmalig)

```bash
# 1. Ga naar de projectmap
cd "/Users/ralfknevel/Desktop/Productinfo intern tool"

# 2. Maak een virtuele omgeving en installeer de pakketten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Optioneel: API-key voor extra AI-hulp bij kolomkoppelingen
export ANTHROPIC_API_KEY="sk-ant-..."
```

Automatisch invullen werkt zonder API-key. De tool herkent bekende leveranciers-,
EAN- en productkolommen lokaal. Onbekende of onzekere kolommen blijven ongemoeid.
Onder **Geavanceerd** kun je optioneel koppelingen aanpassen of AI-hulp vragen.
Voor nieuwe PDF-extracties is wel een API-key nodig.

## Stap 1 — PDF's inlezen (eenmalig, en bij nieuwe/gewijzigde bladen)

```bash
source venv/bin/activate          # als nog niet actief
export ANTHROPIC_API_KEY="sk-ant-..."
python3 ingest.py
```

Dit leest alle PDF's en schrijft `kennisbank.json`. Kost eenmalig een paar
cent/euro. Mislukt een bestand? Draai het script gewoon opnieuw.

### Stap 1b — Excel-artikeloverzicht toevoegen

`Product Data Sheet december 2024.xlsx` bevat artikel-/logistiekgegevens
(artikelcodes, EAN-codes, verpakking, VOC, transport). Voeg toe met:

```bash
python3 ingest_excel.py
```

Dit gebruikt geen API (puur lokaal) en voegt de Excel als één bron toe aan
`kennisbank.json`. Opnieuw draaien is veilig — het oude Excel-item wordt vervangen.

### Stap 1c — Artikeldata voor de dealer-Excel invuller

`ingest_artikeldata.py` zet het Product Data Sheet om naar `artikeldata.json`
(gestructureerd, per artikelcode). Draai dit opnieuw bij een nieuwe versie van
het sheet en commit het resultaat:

```bash
python3 ingest_artikeldata.py
```

### Aanvullende verkoopadviesprijslijst

De app leest daarnaast `data/verkoopadviesprijzen_2026.csv`, een lokale kopie van
de aangeleverde dealerprijslijst. Hiervoor is geen API nodig. De productdatasheet
blijft leidend voor technische gegevens. Voor alle artikelen in de prijslijst
gebruikt de tool de omschrijving uit die lijst, inclusief merktekens en spelling.
Artikelen zonder prijslijstvermelding houden hun omschrijving uit de productdatasheet.
Naamverschillen worden daarom niet meer als melding getoond. Bestaande dealercellen
blijven behouden, tenzij je bewust kiest voor overschrijven. Nieuwe artikelen krijgen alleen de
gegevens die werkelijk in die lijst staan. `artikeldata.json` wordt niet gewijzigd.

De nieuwe velden zijn verkoopadviesprijs, prijseenheid (stuk/set), VE-aantal en
omschrijving volgens prijslijst. Prijzen zijn in EUR, exclusief btw, per stuk of
set, geldig van 1 januari tot en met 31 december 2026. Ze zijn **geen inkoopprijzen**.
VE wordt niet gebruikt als doosinhoud of minimale afname. Een duidelijke kop als
`Adviesprijs excl. btw (EUR)` wordt automatisch herkend. Onduidelijke prijsvelden
blijven leeg en kunnen onder Geavanceerd bewust worden gekoppeld.

Verschillende EAN-codes tussen de bronnen blokkeren automatisch invullen van het
betrokken artikel. De app toont de melding en het controleoverzicht legt uit
waarom. Eén bevestigde uitzondering: voor artikel `2023005` is EAN `8714748004740`
uit de prijslijst leidend in plaats van `8714748002616` uit de productdatasheet,
zoals Ralf op 7 september 2026 heeft aangegeven. Deze keuze wordt in de
broninformatie vastgelegd en geldt alleen voor dit artikel en deze twee EAN-codes.
Technische gegevens blijven ongewijzigd. De datum wordt bij iedere verwerking
gecontroleerd. Na afloop van de geldigheidsperiode worden
geen adviesprijzen aangevuld, maar blijven artikelidentificatie en technische
gegevens beschikbaar. Een eerder gemaakte download wordt niet achteraf ingetrokken;
ververs een open pagina om opnieuw te controleren. Ontbreekt de CSV of is die ongeldig, dan
meldt de app dit en blijft de productdatasheet bruikbaar.

## Dealer-Excel invullen

De app opent direct met **Dealerbestanden invullen**. Upload het bestand en
download het resultaat. Er is geen verplichte controlestap of AI-wachttijd.
Alleen lege cellen waarvoor een bekende koppeling en bruikbare brongegevens
bestaan worden aangevuld. Je ziet hoeveel cellen zijn ingevuld en welke artikelen
ontbreken. Als er niets aangevuld kan worden, krijg je dat duidelijk te zien en
kun je het bestand met een controleoverzicht downloaden.

Onder het ingeklapte **Geavanceerd** kun je het tabblad, de rij met kolomkoppen,
de eerste artikelrij en de koppelingen aanpassen. Wijzigingen worden direct
verwerkt. **AI-hulp bij kolommen** is optioneel en start alleen na een klik.
Als AI-hulp mislukt, blijven je bestaande keuzes en resultaat behouden.

Bekende maat- en gewichtskolommen worden ook zonder eenheid in de kolomkop
herkend. Staat er bijvoorbeeld alleen `Länge` of `Nettogewicht`, dan verschijnt
een korte eenheidskeuze boven het resultaat. Met **Onthouden voor dit
dealerformaat** bewaar je die lokaal in `.dealer_profielen/`. Volgende bestanden
met dezelfde dealeridentificatie, kolommen en tabblad gebruiken die keuze direct.
Zonder dealeridentificatie moet ook de bestandsstam overeenkomen. Deze lokale
keuzes worden niet met Git gepubliceerd.

Een expliciete eenheid in een kolom of een handmatige kolomkeuze heeft altijd
voorrang. Zolang een eenheid nog niet is gekozen, blijven alleen die maat- of
gewichtscellen leeg; andere beschikbare gegevens worden gewoon aangevuld.
Het controleoverzicht vermeldt ook waar de eenheidskeuze vandaan komt.

- Artikelen worden gezocht op Repair Care-artikelnummer en daarna EAN.
  Een overeenkomst op alleen een omschrijving is niet voldoende om automatisch
  in te vullen. Tegenstrijdige dubbele artikelnummer- of EAN-kolommen worden
  niet gebruikt om een artikel te gokken.
- Meerdere kopregels en technische PIM-codes onder de koppen worden bij de
  herkenning onderscheiden van artikelrijen. Rijen zonder ingevulde
  artikelidentificatie worden overgeslagen.
- Bestaande formules en samengevoegde vervolgvelden worden niet overschreven.
  Zwarte cellen blijven intact wanneer het blad `Legende` aangeeft dat deze
  niet ingevuld mogen worden, zoals in het aangeleverde kenmerkenbestand.
- Ontbrekende artikelen blijven zichtbaar in het resultaat. De tool voegt geen
  productgegevens uit voorbeeldbestanden toe aan de brondata.
- Ontbrekende en onzekere waarden blijven leeg, zonder gele celkleuring. Ook
  componentkleuren worden niet als kleur van het totale product overgenomen.
  Bestaande waarden, opmaak en tabbladen blijven behouden. Een bestaand tabblad
  `Controle` blijft staan; het nieuwe overzicht krijgt dan een vrije naam.
- Tweecomponentproducten: nettogewicht kan uit A + B worden berekend. Bij sets
  komen de losse componentmaten samen in iedere maatcel, bijvoorbeeld lengte
  `A: 48 / B: 41` en hoogte `A: 184 / B: 145` in mm. Beide waarden worden naar
  de gekozen eenheid omgerekend. Dit zijn geen opgetelde verpakkingsmaten.
  Een rechtstreeks bekende product- of doosmaat blijft een gewoon getal.
  Ontbreekt een componentmaat, dan blijft die maatcel leeg met uitleg.
  Alleen kolommen met nieuw ingevulde componentmaten worden zo nodig verbreed
  om de A/B-tekst leesbaar te houden; celopmaak blijft behouden. Gedeelde
  kolominstellingen blijven intact om naburige kolommen niet te veranderen.
- Doosgewichten worden apart van stukgewichten herkend. Bij duidelijke
  dooskolommen gebruikt de tool het netto- of brutogewicht per doos uit de bron,
  zo nodig als som van de volledige componentgewichten A + B. Bij VPE-kolommen
  moeten ook het aantal, de doosverpakking en de gewichtseenheid duidelijk zijn.
  De waarde wordt naar de gevraagde kg of g omgerekend. Een afwijkend doosaantal
  wordt niet stilzwijgend overgenomen; het controleoverzicht vermeldt waarom een
  gewicht leeg blijft. Bestaande waarden blijven standaard behouden.
- Product- en veiligheidsbladen uit `kennisbank.json` worden bij de ingest aan
  de artikelen gekoppeld (via de productnaam). Zo zijn ook signaalwoord,
  H-zinnen, Kemler-nummer, EURAL-code, dichtheid, opslagtemperatuur,
  verwerkingstijd/-temperatuur, mengverhouding, laagdikte, uitharding en
  certificering invulbaar. Het PDS gaat vóór; afwijkingen tussen
  veiligheidsblad en PDS (bv. verpakkingsgroep) meldt de ingest.
- Gegevens die niet in het sheet staan (land van oorsprong, Bundesland) komen
  uit `vaste_waarden.json`. Vul daar `standaard`, `per_prefix` (bv. `"2": "NLD"`)
  of `per_artikel` in.
- Met "ook gevulde cellen overschrijven" blijft een bestaande waarde staan als er
  geen bruikbare brondata is. Deze optie staat standaard uit onder **Geavanceerd**.

Zonder browser:

```bash
python3 dealer_invuller.py dealerbestand.xlsx            # mapping via Claude
python3 dealer_invuller.py dealerbestand.xlsx --mapping mapping.json
```

De CLI behoudt de eerdere werkwijze met AI of een opgeslagen mapping en gele
markering van ontbrekende waarden. De vereenvoudigde, opmaakbehoudende werkwijze
hierboven geldt voor de app.

Tests: `pip install -r requirements-dev.txt && pytest`

## Stap 2: De tool starten

```bash
source venv/bin/activate
export ANTHROPIC_API_KEY="sk-ant-..."
streamlit run app.py
```

De app opent in je browser op het uploadscherm voor dealerbestanden.
Met **Nederlands / Deutsch** bovenaan kies je de bedieningstaal. De productteksten,
kolomkoppen en het controleoverzicht in Excel blijven in hun oorspronkelijke taal.
De broncontrole met informatieve meldingen staat niet meer op het hoofdscherm;
conflicten die invullen tegenhouden blijven wel zichtbaar.
De chatfunctie is verwijderd. De product- en veiligheidsbladen blijven als
bron voor de artikelgegevens beschikbaar.

## Online delen met collega's via Render

`render.yaml` bereidt een gratis webservice in Frankfurt voor, met Duits als
starttaal en verplichte wachtwoordtoegang. De collega heeft alleen een browser,
de link en het wachtwoord nodig. Gewoon invullen werkt zonder API-key.

### Voor het publiceren

De gekoppelde repository `ralfknevel-collab/repaircare-productinfo` is openbaar.
Een appwachtwoord beschermt geen bestanden op GitHub. Beslis daarom eerst of de
productdata en `data/verkoopadviesprijzen_2026.csv` openbaar mogen worden. Maak
de repository alleen na een bewuste keuze privé, of publiceer uitsluitend
goedgekeurde brondata. Zonder de aanvullende CSV werkt de app met de
productdatasheet en meldt hij dat de brongegevens niet volledig geladen zijn.

Neem de actuele versies mee van `app.py`, `vertalingen.py`, `artikeldata.py`,
`prijslijst.py`, `documentdata.py`, `dealer_invuller.py`, `dealer_profielen.py`,
`mapping.py`, `veldcatalogus.py`, `artikeldata.json`, `vaste_waarden.json`,
`requirements.txt`, `render.yaml`, `.python-version`, `assets/` en
`.streamlit/config.toml`. Voeg de prijs-CSV alleen toe na bovenstaande keuze.
De PDF's, originele Excel-bestanden en `kennisbank.json` zijn hiervoor niet nodig.
Zet geen wachtwoorden, API-keys, `.env` of `.streamlit/secrets.toml` in Git.
Commit en push pas na akkoord over de bestanden en hun publicatie.

### Render instellen

1. Open [Render](https://dashboard.render.com/) en kies **New > Blueprint**.
   Koppel het GitHub-account en de repository met de voorbereide bestanden.
2. Kies de gewenste branch en `render.yaml`. Controleer vóór **Deploy Blueprint**
   dat er één webservice op **Free** staat, zonder database of extra schijf.
3. Render maakt `APP_PASSWORD` automatisch aan. Bekijk de waarde onder
   **Environment** van de webservice en deel deze apart van de link met de
   collega. Zet het wachtwoord niet in de repository of een screenshot.
4. Open de toegewezen `onrender.com`-link. Controleer het Duitse inlogscherm,
   probeer een verkeerd en het juiste wachtwoord en test uploaden en downloaden
   met een dealerbestand. Controleer ook het tabblad `Controle` in de download.

De Blueprint zet `APP_LANGUAGE=de` en `REQUIRE_APP_PASSWORD=true`. Op Render
weigert de app toegang wanneer `APP_PASSWORD` ontbreekt. Voor Nederlands kun je
`APP_LANGUAGE` op `nl` zetten. Voeg `ANTHROPIC_API_KEY` alleen toe onder
**Environment** als de optionele AI-hulp nodig is; die kan API-kosten veroorzaken.

Gewone commits worden niet automatisch uitgerold (`autoDeployTrigger: "off"`).
Zet ook **Auto Sync** van de Blueprint uit als wijzigingen in `render.yaml`
uitsluitend handmatig mogen worden toegepast. Gebruik daarna een handmatige
deploy voor nieuwe appcode. Zie de [Blueprint-handleiding van Render](https://render.com/docs/infrastructure-as-code).

### Grenzen van de gratis versie

Na 15 minuten zonder verkeer kan de app slapen; opnieuw openen duurt dan ongeveer
een minuut. Nieuwe keuzes in `.dealer_profielen/` verdwijnen bij slapen,
herstarten of opnieuw publiceren. Downloads moet de collega zelf bewaren.
De gratis server heeft beperkte capaciteit en gebruikslimieten. Bij een
gekoppelde betaalmethode kunnen overschrijdingen van dataverkeer of bouwminuten
kosten geven. Zie [de actuele gratis limieten](https://render.com/docs/free).

`.python-version` kiest Python 3.12 met de nieuwste beschikbare 3.12-patch volgens
[Render's Python-instellingen](https://render.com/docs/python-version). De lokale
omgeving gebruikt Python 3.9; de eerste Render-build en bovenstaande gebruikstest
blijven nodig om de Linux-hosting te bevestigen.

## Online delen met collega's (Streamlit Community Cloud)

Zo krijgen collega's een link, zonder installatie en zonder eigen API-key. Jouw
key staat veilig als server-geheim — nooit in de code.

**Vereisten:** een GitHub-account en een Streamlit-account (gratis, log in met
GitHub via https://share.streamlit.io).

**Stappen:**

1. **Zet de map op GitHub.** De repo is lokaal al voorbereid (git-commit gemaakt).
   Maak een lege repo op github.com (mag privé) en push:
   ```bash
   cd "/Users/ralfknevel/Desktop/Productinfo intern tool"
   git remote add origin https://github.com/<jouw-gebruikersnaam>/<repo-naam>.git
   git branch -M main
   git push -u origin main
   ```
   > De `.gitignore` zorgt dat `.env`, `secrets.toml`, de venv en de PDF-mappen
   > NIET meegaan. Voor de online app zijn nodig: `app.py`, `requirements.txt`,
   > `artikeldata.py`, `prijslijst.py`,
   > `dealer_invuller.py`, `dealer_profielen.py`, `mapping.py`, `veldcatalogus.py`, `artikeldata.json`
   > en `vaste_waarden.json`. Voeg `data/verkoopadviesprijzen_2026.csv` alleen toe
   > als de aanvullende prijslijst ook voor die omgeving bestemd is.
   > Neem ook `assets/` en `.streamlit/config.toml`
   > mee voor het logo en de huisstijl.

2. **Maak de app aan op Streamlit Cloud.** Ga naar https://share.streamlit.io →
   "Create app" → kies je repo, branch `main`, main file `app.py`.

3. **Zet de secrets.** Onder "Advanced settings" → "Secrets", plak:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   APP_PASSWORD = "kies-een-wachtwoord"
   ```
   (Zelfde format als `.streamlit/secrets.toml.example`.)

4. **Deploy.** Na een minuut krijg je een URL zoals
   `https://<iets>.streamlit.app`.

5. **Beperk de toegang.** Twee lagen:
   - Het `APP_PASSWORD` in de app: collega's hebben de link én het wachtwoord nodig.
   - Optioneel strenger: in de app-instellingen op Streamlit Cloud kun je de app
     op privé zetten en collega's per e-mailadres uitnodigen.

6. **Doorsturen.** Stuur de URL (en het wachtwoord) naar je collega's. Klaar.

> Automatische kolomherkenning via Claude gebruikt jouw API-key en kost geld. Het
> wachtwoord voorkomt dat willekeurige mensen met de link je rekening belasten.

## Onderhoud

Komen er nieuwe of gewijzigde PDF's in `Productdatabladen/` of
`Veiligheidsbladen/`? Draai `python3 ingest.py` opnieuw; `kennisbank.json` wordt
dan ververst. Draai daarna `python3 ingest_artikeldata.py` om deze gegevens
opnieuw aan de artikelen te koppelen. Doe dit ook bij een nieuw Product Data Sheet.
Voor de online versie moet de vernieuwde `artikeldata.json` gepubliceerd worden.

## Belangrijk

Controleer het tabblad `Controle`, ontbrekende artikelen en de gekozen eenheden
voordat je het bestand aan de dealer levert. Raadpleeg bij twijfel over
veiligheidsgegevens het originele document.
