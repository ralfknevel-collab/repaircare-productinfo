# Repair Care Productinfo Tool

Interne chatbot die vragen beantwoordt over de Repair Care product- en
veiligheidsbladen. Werkt in twee stappen: eenmalig de PDF's inlezen, daarna
chatten.

## Wat zit erin

- `ingest.py` — leest alle PDF's en bouwt `kennisbank.json` (eenmalig draaien).
- `app.py` — Streamlit-chatapp die `kennisbank.json` gebruikt.
- `kennisbank.json` — gegenereerde kennisbank (komt na stap 3).

## Installatie (eenmalig)

```bash
# 1. Ga naar de projectmap
cd "/Users/ralfknevel/Desktop/Productinfo intern tool"

# 2. Maak een virtuele omgeving en installeer de pakketten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Zet je Anthropic API-key (haal er een op via console.anthropic.com)
export ANTHROPIC_API_KEY="sk-ant-..."
```

> Tip: zet de `export`-regel in `~/.zshrc` zodat je hem niet elke keer hoeft te typen.

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

## Stap 2 — De chatbot starten

```bash
source venv/bin/activate
export ANTHROPIC_API_KEY="sk-ant-..."
streamlit run app.py
```

De app opent in je browser. Stel vragen zoals:

- "Wat is het VOS-gehalte van DRY FLEX 4?"
- "Welke gevarenklasse heeft BIO FLEX COOL component A?"
- "Hoe verwerk ik DRY SEAL MP?"

De chatbot antwoordt met bronvermelding. Bij twijfel verwijst hij naar het
originele PDF-bestand — open dat altijd voor juridisch bindende informatie.

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
   > NIET meegaan. Alleen `app.py`, `requirements.txt` en `kennisbank.json` zijn
   > nodig voor de online app.

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

> Let op: elke vraag van een collega draait op jouw API-key en kost geld. Het
> wachtwoord voorkomt dat willekeurige mensen met de link je rekening belasten.

## Onderhoud

Komen er nieuwe of gewijzigde PDF's in `Productdatabladen/` of
`Veiligheidsbladen/`? Draai `python3 ingest.py` opnieuw; `kennisbank.json` wordt
dan ververst. Nieuwe Excel? Draai daarna ook `python3 ingest_excel.py`.
Bij de online versie: commit en push de nieuwe `kennisbank.json`
naar GitHub — Streamlit Cloud werkt dan automatisch bij.

## Belangrijk

Veiligheidsbladen zijn juridisch belangrijk. De chatbot is een hulpmiddel om
snel informatie te vinden, geen vervanging van de originele documenten.
