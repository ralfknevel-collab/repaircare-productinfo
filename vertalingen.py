"""Vaste Nederlandse en Duitse schermteksten; bron- en productdata blijven intact."""

from __future__ import annotations

import re
from string import Formatter


DE: dict[str, str] = {
    "Repair Care | Dealerbestanden invullen": "Repair Care | Händlerdateien ausfüllen",
    "Dealerbestanden invullen": "Händlerdateien ausfüllen",
    "DEALERBESTANDEN": "HÄNDLERDATEIEN",
    "Welkom": "Willkommen",
    "Log in om dealerbestanden in te vullen.": "Bitte anmelden, um Händlerdateien auszufüllen.",
    "Wachtwoord": "Passwort",
    "Inloggen": "Anmelden",
    "Uitloggen": "Abmelden",
    "Onjuist wachtwoord.": "Falsches Passwort.",
    "Taal": "Sprache",
    "Nederlands": "Nederländisch",
    "Duits": "Deutsch",
    "De online tool is nog niet beveiligd. Stel APP_PASSWORD in voordat je hem gebruikt.":
        "Die Online-Anwendung ist noch nicht geschützt. Bitte vor der Nutzung APP_PASSWORD einrichten.",
    "Brongegevens konden niet volledig worden geladen. Neem contact op met de beheerder.":
        "Die Quelldaten konnten nicht vollständig geladen werden. Bitte die Administration kontaktieren.",
    "Upload je dealerbestand. Bekende gegevens worden automatisch aangevuld. Download daarna het resultaat.":
        "Bitte die Händlerdatei hochladen. Bekannte Daten werden automatisch ergänzt. Anschließend kann das Ergebnis heruntergeladen werden.",
    "Bestand": "Datei",
    "Dealerbestand": "Händlerdatei",
    "artikeldata.json ontbreekt. Draai eerst:  python3 ingest_artikeldata.py":
        "artikeldata.json fehlt. Bitte zuerst ausführen:  python3 ingest_artikeldata.py",
    "Aanvullende bron: {bron}. Omschrijvingen uit deze prijslijst zijn leidend. Adviesprijzen in EUR, exclusief btw, per stuk of set; geldig van {geldig_vanaf} tot en met {geldig_tot}.":
        "Zusätzliche Quelle: {bron}. Die Beschreibungen aus dieser Preisliste sind maßgeblich. Unverbindliche Preisempfehlungen in EUR, ohne MwSt., pro Stück oder Set; gültig vom {geldig_vanaf} bis einschließlich {geldig_tot}.",
    "De aanvullende prijslijst kon niet worden gebruikt. De productdatasheet blijft beschikbaar.":
        "Die zusätzliche Preisliste konnte nicht verwendet werden. Das Produktdatenblatt bleibt verfügbar.",
    "Bronconflict bij artikel {artikelen}. De EAN-codes verschillen tussen de bronnen. Deze artikelen worden niet aangevuld.":
        "Widersprüchliche Quelldaten bei Artikel {artikelen}. Die EAN-Codes unterscheiden sich zwischen den Quellen. Diese Artikel werden nicht ergänzt.",
    "Broncontrole ({aantal} meldingen)": "Quellenprüfung ({aantal} Meldungen)",
    "Geavanceerd": "Erweitert",
    "Alleen nodig als je de indeling of kolomkoppelingen wilt aanpassen. Wijzigingen worden direct verwerkt; het originele bestand blijft ongewijzigd.":
        "Nur erforderlich, um den Aufbau oder die Spaltenzuordnungen anzupassen. Änderungen werden sofort verarbeitet; die Originaldatei bleibt unverändert.",
    "Tabblad": "Tabellenblatt",
    "AI-hulp bij kolommen": "KI-Hilfe bei Spalten",
    "Optioneel. Maakt nieuwe koppelingen en vervangt je huidige keuzes. Kan enkele minuten duren.":
        "Optional. Erstellt neue Zuordnungen und ersetzt die aktuelle Auswahl. Kann einige Minuten dauern.",
    "AI-voorstel maken…": "KI-Vorschlag wird erstellt…",
    "Het AI-voorstel heeft geen bruikbare sleutel of een ongeldige eenheid.":
        "Der KI-Vorschlag enthält keinen verwendbaren Schlüssel oder eine ungültige Einheit.",
    "AI-hulp gaf geen bruikbaar antwoord binnen de beschikbare tijd. Je bestaande koppelingen en resultaat zijn behouden.":
        "Die KI-Hilfe hat innerhalb der verfügbaren Zeit keine verwendbare Antwort geliefert. Bestehende Zuordnungen und Ergebnisse wurden beibehalten.",
    "Automatisch invullen werkt zonder AI. Voor optionele AI-hulp is een API-sleutel nodig.":
        "Das automatische Ausfüllen funktioniert ohne KI. Für die optionale KI-Hilfe wird ein API-Schlüssel benötigt.",
    "AI-hulp wacht maximaal {minuten} minuten; de gewone invulstap gebruikt geen AI.":
        "Die KI-Hilfe wartet höchstens {minuten} Minuten; das reguläre Ausfüllen verwendet keine KI.",
    "Rij met kolomkoppen": "Zeile mit Spaltenüberschriften",
    "Eerste artikelrij": "Erste Artikelzeile",
    "Ook gevulde cellen overschrijven": "Auch ausgefüllte Zellen überschreiben",
    "Het bestand kon niet worden verwerkt. Je originele bestand is ongewijzigd.":
        "Die Datei konnte nicht verarbeitet werden. Die Originaldatei ist unverändert.",
    "Resultaat": "Ergebnis",
    "Taal voor nieuwe productteksten: {taalnaam}.": "Sprache für neue Produkttexte: {taalnaam}.",
    "De Duitse productvertalingen konden niet worden geladen. Beschrijvende tekstvelden worden niet aangevuld; overige gegevens wel. Neem contact op met de beheerder.":
        "Die deutschen Produktübersetzungen konnten nicht geladen werden. Beschreibende Textfelder werden nicht ergänzt; die übrigen Daten schon. Bitte den Administrator kontaktieren.",
    "Voor {aantal} cellen ontbreekt een geldige Duitse vertaling van de huidige brontekst. Deze teksten zijn niet ingevuld. De overige gegevens zijn wel verwerkt; het controleoverzicht geeft uitleg.":
        "Für {aantal} Zellen fehlt eine gültige deutsche Übersetzung des aktuellen Quelltextes. Diese Texte wurden nicht eingetragen. Die übrigen Daten wurden verarbeitet; Einzelheiten stehen in der Prüfübersicht.",
    "Tabblad: {tabblad}. Bestaande waarden blijven staan tenzij je bij Geavanceerd anders kiest.":
        "Tabellenblatt: {tabblad}. Vorhandene Werte bleiben erhalten, sofern unter Erweitert nichts anderes ausgewählt wird.",
    " Controleer zo nodig de instellingen bij Geavanceerd.":
        " Bitte bei Bedarf die Einstellungen unter Erweitert prüfen.",
    "{aantal} cellen aangevuld. {gevonden} van {totaal} artikelen gevonden.":
        "{aantal} Zellen ergänzt. {gevonden} von {totaal} Artikeln gefunden.",
    "Aangevuld: ": "Ergänzt: ",
    ". Meer details staan in het controleoverzicht.": ". Weitere Details stehen in der Prüfübersicht.",
    "0 cellen aangevuld. Er zijn geen lege velden die we met zekerheid konden invullen.":
        "0 Zellen ergänzt. Es gibt keine leeren Felder, die mit sicheren Daten ausgefüllt werden konnten.",
    "Niet gevonden in de productbron: ": "Nicht in der Produktquelle gefunden: ",
    " en nog {aantal}.": " und {aantal} weitere.",
    " Deze artikelen zijn niet aangevuld; de overige artikelen zijn wel verwerkt.":
        " Diese Artikel wurden nicht ergänzt; die übrigen Artikel wurden verarbeitet.",
    "{aantal} artikelrijen hebben tegenstrijdige artikelgegevens of bronconflicten. Deze rijen zijn niet aangevuld. Het controleoverzicht geeft uitleg.":
        "{aantal} Artikelzeilen enthalten widersprüchliche Artikel- oder Quelldaten. Diese Zeilen wurden nicht ergänzt. Die Prüfübersicht enthält die Erläuterungen.",
    "{aantal} velden leeg gelaten omdat de brongegevens ontbreken.":
        "{aantal} Felder wurden leer gelassen, weil Quelldaten fehlen.",
    "Onzekere gegevens zijn niet ingevuld. Het controleoverzicht vermeldt waarom.":
        "Unsichere Daten wurden nicht eingetragen. Die Prüfübersicht nennt den Grund.",
    "{aantal} cellen wachten op een eenheidskeuze hierboven. De overige beschikbare gegevens zijn wel verwerkt.":
        "Für {aantal} Zellen muss oben noch eine Einheit ausgewählt werden. Die übrigen verfügbaren Daten wurden verarbeitet.",
    "Download ingevuld bestand": "Ausgefüllte Datei herunterladen",
    "Download bestand met controleoverzicht": "Datei mit Prüfübersicht herunterladen",
    "Alleen beschikbare gegevens zijn gebruikt. Het controleoverzicht in Excel vermeldt de bronnen.":
        "Es wurden ausschließlich verfügbare Daten verwendet. Die Prüfübersicht in Excel nennt die Quellen.",
    "{aantal} kolommen niet automatisch ingevuld": "{aantal} Spalten nicht automatisch ausgefüllt",
    "Deze kolommen zijn onbekend of niet eenduidig. Bestaande inhoud is behouden. Je kunt ze desgewenst koppelen bij Geavanceerd.":
        "Diese Spalten sind unbekannt oder nicht eindeutig. Vorhandene Inhalte wurden beibehalten. Bei Bedarf können sie unter Erweitert zugeordnet werden.",
    "De bewaarde eenheden konden niet worden gelezen. Kies ze hieronder opnieuw; er wordt niets aangenomen.":
        "Die gespeicherten Einheiten konnten nicht gelesen werden. Bitte unten erneut auswählen; es werden keine Annahmen getroffen.",
    "Kies eenheid": "Einheit auswählen",
    "Millimeters (mm)": "Millimeter (mm)",
    "Centimeters (cm)": "Zentimeter (cm)",
    "Meters (m)": "Meter (m)",
    "Gram (g)": "Gramm (g)",
    "Kilogram (kg)": "Kilogramm (kg)",
    "Eenheden kiezen": "Einheiten auswählen",
    "Eenheden wijzigen": "Einheiten ändern",
    "De kolommen zijn herkend, maar noemen geen eenheid. Kies die hier één keer. Een eenheid die al in een kolom staat of handmatig is ingesteld, blijft gelden.":
        "Die Spalten wurden erkannt, enthalten aber keine Einheit. Bitte hier einmal auswählen. Eine bereits in der Spalte angegebene oder manuell festgelegte Einheit bleibt gültig.",
    "Maten": "Maße",
    "Gewichten": "Gewichte",
    "Onthouden voor dit dealerformaat": "Für dieses Händlerformat speichern",
    "Eenheden onthouden voor volgende bestanden in dit dealerformaat.":
        "Die Einheiten wurden für weitere Dateien in diesem Händlerformat gespeichert.",
    "Deze keuze wordt nu gebruikt, maar kon niet worden opgeslagen. Bij een volgend bestand moet je de eenheden opnieuw kiezen.":
        "Diese Auswahl wird jetzt verwendet, konnte aber nicht gespeichert werden. Bei der nächsten Datei müssen die Einheiten erneut ausgewählt werden.",
    "maten in {eenheid}": "Maße in {eenheid}",
    "gewichten in {eenheid}": "Gewichte in {eenheid}",
    "Voor kolommen zonder eenheid: ": "Für Spalten ohne Einheit: ",
    ". Onthouden voor dit dealerformaat.": ". Für dieses Händlerformat gespeichert.",
    ". Alleen voor dit bestand gekozen.": ". Nur für diese Datei ausgewählt.",
    "Bewaarde keuze voor dit dealerformaat": "Gespeicherte Auswahl für dieses Händlerformat",
    "Keuze gebruiker in de tool": "Auswahl in der Anwendung",
    "Keuze gebruiker": "Benutzerauswahl",
    " (bronbestand)": " (Quelldatei)",
    " (productgegeven)": " (Produktangabe)",
    "Kolommen koppelen": "Spalten zuordnen",
    "Pas het productgegeven en de eenheid aan waar nodig. De volledige voorbeeldtekst en toelichting kun je onder de tabel bekijken.":
        "Bitte die Produktangabe und Einheit bei Bedarf anpassen. Der vollständige Beispieltext und die Erläuterung stehen unter der Tabelle.",
    "Kies hierboven de rij met de kolomkoppen om kolommen te koppelen.":
        "Bitte oben die Zeile mit den Spaltenüberschriften auswählen, um Spalten zuzuordnen.",
    "Kolom": "Spalte",
    "Doelveld": "Zielfeld",
    "Eenheid": "Einheit",
    "Zekerheid": "Sicherheit",
    "Toelichting": "Erläuterung",
    "hoog": "hoch",
    "middel": "mittel",
    "laag": "niedrig",
    "Kolom in dealerbestand": "Spalte in der Händlerdatei",
    "Productgegeven": "Produktangabe",
    "Bestandskeuze / niet nodig": "Dateiauswahl / nicht erforderlich",
    "{aantal} koppelingen. Kies hieronder een kolom om alle tekst te lezen.":
        "{aantal} Zuordnungen. Bitte unten eine Spalte auswählen, um den vollständigen Text zu lesen.",
    "Volledige tekst van een kolom": "Vollständiger Text einer Spalte",
    "Voorbeeld uit het dealerbestand": "Beispiel aus der Händlerdatei",
    "Geen voorbeeld ingevuld.": "Kein Beispiel eingetragen.",
    "Geen aanvullende toelichting.": "Keine zusätzliche Erläuterung.",
    # De vaste labels zijn schermnamen; technische veldcodes blijven ongewijzigd.
    "Repair Care-artikelnummer (sleutel)": "Repair Care-Artikelnummer (Schlüssel)",
    "EAN-13 (sleutel)": "EAN-13 (Schlüssel)",
    "Omschrijving (sleutel, fuzzy)": "Beschreibung (Schlüssel, Ähnlichkeitssuche)",
    "Douanetariefnummer (GN/HS-code)": "Zolltarifnummer (KN/HS-Code)",
    "Nettogewicht per stuk": "Nettogewicht pro Stück",
    "Brutogewicht per stuk": "Bruttogewicht pro Stück",
    "Nettogewicht per doos (collo)": "Nettogewicht pro Karton (Kollo)",
    "Brutogewicht per doos (collo)": "Bruttogewicht pro Karton (Kollo)",
    "Lengte per stuk": "Länge pro Stück",
    "Breedte per stuk": "Breite pro Stück",
    "Hoogte per stuk": "Höhe pro Stück",
    "Lengte verpakkingseenheid (collo)": "Länge der Verpackungseinheit (Kollo)",
    "Breedte verpakkingseenheid (collo)": "Breite der Verpackungseinheit (Kollo)",
    "Hoogte verpakkingseenheid (collo)": "Höhe der Verpackungseinheit (Kollo)",
    "EAN-13": "EAN-13",
    "Omschrijving": "Beschreibung",
    "Adviesverkoopprijs exclusief btw (EUR)": "Unverbindliche Preisempfehlung ohne MwSt. (EUR)",
    "Prijseenheid (stuk of set)": "Preiseinheit (Stück oder Set)",
    "VE-aantal volgens prijslijst": "VE-Menge laut Preisliste",
    "Omschrijving volgens prijslijst": "Beschreibung laut Preisliste",
    "Minimale afname": "Mindestabnahmemenge",
    "UN-nummer": "UN-Nummer",
    "Gevarenklasse (ADR)": "Gefahrgutklasse (ADR)",
    "Verpakkingsgroep": "Verpackungsgruppe",
    "Transportnaam (ADR)": "Beförderungsbezeichnung (ADR)",
    "Vlampunt": "Flammpunkt",
    "UFI-code": "UFI-Code",
    "VOC-gehalte": "VOC-Gehalt",
    "GHS-pictogrammen": "GHS-Piktogramme",
    "Signaalwoord (CLP)": "Signalwort (CLP)",
    "H-zinnen (gevarenaanduidingen)": "H-Sätze (Gefahrenhinweise)",
    "EUH-zinnen": "EUH-Sätze",
    "Gevarenklassen (CLP)": "Gefahrenklassen (CLP)",
    "ADR-classificatiecode": "ADR-Klassifizierungscode",
    "Kemler-nummer": "Nummer zur Kennzeichnung der Gefahr (Kemler-Zahl)",
    "Dichtheid / soortelijk gewicht": "Dichte / spezifisches Gewicht",
    "Opslagtemperatuur": "Lagertemperatur",
    "Kleur": "Farbe",
    "EURAL-afvalcode": "Abfallschlüssel (AVV)",
    "Verwerkingstemperatuur": "Verarbeitungstemperatur",
    "Verwerkingstijd / potlife": "Verarbeitungszeit / Topfzeit",
    "Uitharding / overschilderbaar na": "Aushärtung / überstreichbar nach",
    "Mengverhouding A:B": "Mischungsverhältnis A:B",
    "Laagdikte": "Schichtdicke",
    "Vaste-stofgehalte": "Festkörpergehalt",
    "Certificering (KOMO e.d.)": "Zertifizierung (KOMO usw.)",
    "Verpakking (inhoud)": "Verpackung (Inhalt)",
    "Verpakkingseenheid (doos)": "Verpackungseinheit (Karton)",
    "Verbruik": "Verbrauch",
    "Biobased gehalte": "Anteil biobasierter Rohstoffe",
    "Milieugevaarlijk (ADR)": "Umweltgefährdend (ADR)",
    "Versie veiligheidsblad": "Version des Sicherheitsdatenblatts",
    "Datum veiligheidsblad": "Datum des Sicherheitsdatenblatts",
    "Niet invullen": "Nicht ausfüllen",
    "Land van oorsprong (ISO-3, bv. NLD)": "Ursprungsland (ISO-3, z. B. NLD)",
    "Duits Bundesland (2 letters, alleen bij DEU)": "Deutsches Bundesland (2 Buchstaben, nur bei DEU)",
    "Naam leverancier": "Name des Lieferanten",
    "stuks": "Stück",
    # Lokale programmameldingen; vrije AI-toelichtingen worden niet herschreven.
    "Herkend aan de kolomkop.": "Anhand der Spaltenüberschrift erkannt.",
    "Herkend aan de volledige kolomkop.": "Anhand der vollständigen Spaltenüberschrift erkannt.",
    "Herkend aan de volledige kolomkop; de kop vermeldt geen eenheid.":
        "Anhand der vollständigen Spaltenüberschrift erkannt; die Überschrift enthält keine Einheit.",
    "Keuzeveld of x-markering; geen vrije producttekst invullen.":
        "Auswahlfeld oder x-Markierung; keinen freien Produkttext eintragen.",
    "De toevoeging bij deze tekstkolom is niet eenduidig.":
        "Der Zusatz zu dieser Textspalte ist nicht eindeutig.",
    "Kolom niet eenduidig herkend; blijft leeg.": "Spalte nicht eindeutig erkannt; bleibt leer.",
    "Geen eenduidige ondersteunde eenheid in de kolomkop; blijft leeg.":
        "Keine eindeutige unterstützte Einheit in der Spaltenüberschrift; bleibt leer.",
    "De eenheid in de kolomkop past niet bij dit veld; blijft leeg.":
        "Die Einheit in der Spaltenüberschrift passt nicht zu diesem Feld; bleibt leer.",
    "VPE-gewicht zonder eenduidige doosinhoud, verpakking en eenheidskolom.":
        "VPE-Gewicht ohne eindeutigen Kartoninhalt, Verpackung und Einheitenspalte.",
    "VPE-doosgewicht; doosinhoud en gewichtseenheid worden per artikelrij gecontroleerd.":
        "VPE-Kartongewicht; Kartoninhalt und Gewichtseinheit werden je Artikelzeile geprüft.",
    "Bekende kolommen lokaal herkend. Onzekere velden blijven leeg; je kunt ze handmatig koppelen.":
        "Bekannte Spalten wurden lokal erkannt. Unsichere Felder bleiben leer; sie können manuell zugeordnet werden.",
    "De maximale wachttijd voor automatische kolomherkenning is verstreken. Bekende kolommen lokaal herkend. Kies de overige velden handmatig.":
        "Die maximale Wartezeit für die automatische Spaltenerkennung ist abgelaufen. Bekannte Spalten wurden lokal erkannt. Bitte die übrigen Felder manuell zuordnen.",
    "Automatische kolomkoppeling mislukt ({fout}). Kies de velden handmatig.":
        "Die automatische Spaltenzuordnung ist fehlgeschlagen ({fout}). Bitte die Felder manuell zuordnen.",
    "Eenheid ingesteld op {eenheid} ({bron}).": "Einheit auf {eenheid} eingestellt ({bron}).",
    "Kolom '{kolom}' uit het Claude-voorstel niet gevonden in de kopregel.":
        "Spalte '{kolom}' aus dem Claude-Vorschlag nicht in der Kopfzeile gefunden.",
    "Kolom {kolom}: eenheid {eenheid} past niet bij {veld} ({broneenheid})":
        "Spalte {kolom}: Einheit {eenheid} passt nicht zu {veld} ({broneenheid})",
    "Ongeldige maateenheid; kies mm, cm of m.":
        "Ungültige Maßeinheit; bitte mm, cm oder m auswählen.",
    "Ongeldige gewichtseenheid; kies g of kg.": "Ungültige Gewichtseinheit; bitte g oder kg auswählen.",
    "Bestandsformaat {ext} wordt niet ondersteund. Sla het bestand op als .xlsx of .csv.":
        "Das Dateiformat {ext} wird nicht unterstützt. Bitte die Datei als .xlsx oder .csv speichern.",
    "Geen kopregel gevonden in de eerste rijen (verwacht een rij met minstens 3 tekstkoppen).":
        "Keine Kopfzeile in den ersten Zeilen gefunden (erwartet wird eine Zeile mit mindestens 3 Textüberschriften).",
    "Controleer de kopregel en de eerste artikelrij: de eerste artikelrij moet na de kopregel liggen.":
        "Bitte die Kopfzeile und die erste Artikelzeile prüfen: Die erste Artikelzeile muss hinter der Kopfzeile liegen.",
    "Geen sleutelkolom gekozen (artikelnummer, EAN of omschrijving).":
        "Keine Schlüsselspalte ausgewählt (Artikelnummer, EAN oder Beschreibung).",
    "Claude gaf geen bruikbare mapping (stop_reason={reden}).":
        "Claude hat keine verwendbare Zuordnung geliefert (stop_reason={reden}).",
    "Claude-antwoord bevat geen tekstblok met JSON.": "Die Claude-Antwort enthält keinen Textblock mit JSON.",
    "Claude-antwoord is geen geldige JSON: {fout}": "Die Claude-Antwort enthält kein gültiges JSON: {fout}",
    "Ongeldige kopregel_index: kies een bestaande rij uit het aangeleverde fragment.":
        "Ungültiger kopregel_index: Bitte eine vorhandene Zeile aus dem bereitgestellten Ausschnitt auswählen.",
    "Ongeldige data_start_index: kies een rij na de kop, uiterlijk direct na het werkblad.":
        "Ungültiger data_start_index: Bitte eine Zeile hinter der Kopfzeile auswählen, spätestens direkt hinter dem Tabellenblatt.",
    "Onbekende doelvelden in mapping: {velden}": "Unbekannte Zielfelder in der Zuordnung: {velden}",
    "Verbinding maken voor automatische kolomherkenning...":
        "Verbindung für die automatische Spaltenerkennung wird hergestellt...",
    "Kolomherkenning bezig: {tekens} tekens ontvangen.":
        "Spaltenerkennung läuft: {tekens} Zeichen empfangen.",
}


def vertaal(tekst: str, taal: str = "nl", **waarden) -> str:
    """Vertaal alleen een bekende schermtekst en vul expliciete waarden één keer in."""
    sjabloon = DE.get(tekst, tekst) if taal == "de" else tekst
    return sjabloon.format(**waarden) if waarden else sjabloon


# Alleen deze bekende programmaformaten mogen reeds ingevulde tekst herkennen.
_MELDINGSJABLONEN = (
    "Automatische kolomkoppeling mislukt ({fout}). Kies de velden handmatig.",
    "Bestandsformaat {ext} wordt niet ondersteund. Sla het bestand op als .xlsx of .csv.",
    "Claude gaf geen bruikbare mapping (stop_reason={reden}).",
    "Claude-antwoord is geen geldige JSON: {fout}",
    "Onbekende doelvelden in mapping: {velden}",
    "Kolomherkenning bezig: {tekens} tekens ontvangen.",
)


def _meldingpatroon(sjabloon: str) -> re.Pattern:
    """Behandel alle vaste tekens letterlijk, ook haakjes en punten."""
    delen = []
    for vast, naam, _, _ in Formatter().parse(sjabloon):
        delen.append(re.escape(vast))
        if naam is not None:
            delen.append(f"(?P<{naam}>.*?)")
    return re.compile("".join(delen), re.DOTALL)


_MELDINGPATRONEN = tuple((sjabloon, _meldingpatroon(sjabloon)) for sjabloon in _MELDINGSJABLONEN)
_EENHEIDTOEVOEGING = re.compile(
    r"(?:^| )Eenheid ingesteld op (?P<eenheid>mm|cm|m|g|kg) \((?P<bron>[^\n]*)\)\.$"
)
_KOLOMSJABLOON = "Kolom '{kolom}' uit het Claude-voorstel niet gevonden in de kopregel."
_KOLOMTOEVOEGING = re.compile(r"(?:^| )" + _meldingpatroon(_KOLOMSJABLOON).pattern, re.DOTALL)
_EENHEIDFOUT_SJABLOON = "Kolom {kolom}: eenheid {eenheid} past niet bij {veld} ({broneenheid})"
_EENHEIDFOUT = re.compile(
    r"Kolom (?P<kolom>.+?): eenheid (?P<eenheid>[^\s()]+) past niet bij "
    r"(?P<veld>.+?) \((?P<broneenheid>g|mm|stuks|EUR)\)"
)


def vertaal_melding(tekst: str, taal: str = "nl") -> str:
    """Vertaal bekende programmameldingen en behoud onbekende tekst letterlijk."""
    if taal != "de":
        return tekst
    if tekst in DE:
        return DE[tekst]
    eenheidsfouten = list(_EENHEIDFOUT.finditer(tekst))
    if eenheidsfouten and " ".join(fout[0] for fout in eenheidsfouten) == tekst:
        return " ".join(vertaal(_EENHEIDFOUT_SJABLOON, taal, **fout.groupdict())
                        for fout in eenheidsfouten)
    # Alleen aaneengesloten waarschuwingen aan het einde zijn door de tool toegevoegd.
    kolommen = list(_KOLOMTOEVOEGING.finditer(tekst))
    einde, achtervoegsels = len(tekst), []
    for kolom in reversed(kolommen):
        if kolom.end() != einde:
            break
        scheiding = " " if kolom[0].startswith(" ") else ""
        achtervoegsels.append(scheiding + vertaal(_KOLOMSJABLOON, taal, kolom=kolom["kolom"]))
        einde = kolom.start()
    if achtervoegsels:
        return vertaal_melding(tekst[:einde], taal) + "".join(reversed(achtervoegsels))
    eenheid = _EENHEIDTOEVOEGING.search(tekst)
    if eenheid:
        begin = tekst[:eenheid.start()]
        achtervoegsel = vertaal(
            "Eenheid ingesteld op {eenheid} ({bron}).", taal,
            eenheid=eenheid["eenheid"], bron=vertaal(eenheid["bron"], taal),
        )
        return (vertaal_melding(begin, taal) + " " if begin else "") + achtervoegsel
    for sjabloon, patroon in _MELDINGPATRONEN:
        overeenkomst = patroon.fullmatch(tekst)
        if overeenkomst:
            return vertaal(sjabloon, taal, **overeenkomst.groupdict())
    return tekst
