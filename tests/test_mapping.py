import json
from types import SimpleNamespace

import pytest

from mapping import (
    MODEL,
    KolomMapping,
    Mapping,
    bouw_fragment,
    lege_mapping,
    mapping_schema,
    vraag_mapping,
)
from veldcatalogus import catalogus_voor_prompt


def test_mapping_sleutels_en_doelen():
    m = Mapping(0, [
        KolomMapping("HerstellerArtNr", "sleutel_artikelcode", None, "hoog", ""),
        KolomMapping("EAN13", "sleutel_ean", None, "hoog", ""),
        KolomMapping("Zolltarifnummer", "gn_code", None, "hoog", ""),
        KolomMapping("ArtBeschreibung", "geen", None, "hoog", "al gevuld"),
    ])
    assert [k.kolom for k in m.sleutels()] == ["HerstellerArtNr", "EAN13"]
    assert [k.kolom for k in m.doelen()] == ["Zolltarifnummer"]


def test_mapping_rondreis_dict():
    m = Mapping(2, [KolomMapping("Gewicht", "netto_gewicht", "kg", "middel", "eenheid gegokt")], "let op")
    d = m.naar_dict()
    assert json.loads(json.dumps(d)) == d
    assert Mapping.uit_dict(d) == m


def test_lege_mapping():
    m = lege_mapping(1, ["A", "B"])
    assert m.kopregel_index == 1
    assert all(k.doelveld == "geen" and k.zekerheid == "laag" for k in m.kolommen)
    assert [k.kolom for k in m.kolommen] == ["A", "B"]


def test_schema_is_strict_en_bevat_enums():
    s = mapping_schema(["gn_code", "geen", "sleutel_ean"])
    assert s["type"] == "object" and s["additionalProperties"] is False
    assert set(s["required"]) == {"kopregel_index", "kolommen", "opmerkingen"}
    kolom = s["properties"]["kolommen"]["items"]
    assert kolom["additionalProperties"] is False
    assert kolom["properties"]["doelveld"]["enum"] == ["gn_code", "geen", "sleutel_ean"]
    assert None in kolom["properties"]["eenheid"]["enum"]
    assert set(kolom["properties"]["zekerheid"]["enum"]) == {"hoog", "middel", "laag"}


def test_bouw_fragment():
    rijen = [["ArtNr", "Gewicht"], ["2010005", None], ["2511105", 452]]
    tekst = bouw_fragment(rijen, "Sheet1", 27)
    assert "Sheet1" in tekst and "27" in tekst
    assert "rij 0" in tekst and "ArtNr" in tekst and "2511105" in tekst


def _nep_client(antwoord: dict):
    """Minimale nep van anthropic.Anthropic: onthoudt de aanroep, geeft JSON-tekst terug."""
    aanroepen = []

    def create(**kwargs):
        aanroepen.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(antwoord))],
                               stop_reason="end_turn")

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return client, aanroepen


def test_vraag_mapping_gebruikt_schema_en_parset_antwoord():
    antwoord = {
        "kopregel_index": 0,
        "kolommen": [
            {"kolom": "HerstellerArtNr", "doelveld": "sleutel_artikelcode", "eenheid": None,
             "zekerheid": "hoog", "toelichting": ""},
            {"kolom": "Nettogewicht", "doelveld": "netto_gewicht", "eenheid": "g",
             "zekerheid": "middel", "toelichting": "gram volgens mail"},
        ],
        "opmerkingen": "ok",
    }
    client, aanroepen = _nep_client(antwoord)
    cat = catalogus_voor_prompt(["UFI-code"], {"ursprungsland": "Land"})
    m = vraag_mapping(client, [["HerstellerArtNr", "Nettogewicht"], ["2010005", None]], "Sheet1", 1, cat)

    assert isinstance(m, Mapping)
    assert m.kolommen[1].doelveld == "netto_gewicht" and m.kolommen[1].eenheid == "g"
    assert m.opmerkingen == "ok"

    kw = aanroepen[0]
    assert kw["model"] == MODEL
    assert kw["output_config"]["format"]["type"] == "json_schema"
    enum = kw["output_config"]["format"]["schema"]["properties"]["kolommen"]["items"]["properties"]["doelveld"]["enum"]
    assert "ruw:UFI-code" in enum and "vast:ursprungsland" in enum and "gn_code" in enum
    systeem = kw["system"]
    assert isinstance(systeem, list) and systeem[0]["cache_control"] == {"type": "ephemeral"}
    assert "ruw:UFI-code" in systeem[0]["text"]
    assert "HerstellerArtNr" in kw["messages"][0]["content"]


def test_vraag_mapping_onbekend_doelveld_faalt():
    antwoord = {"kopregel_index": 0, "kolommen": [
        {"kolom": "X", "doelveld": "bestaat_niet", "eenheid": None, "zekerheid": "hoog", "toelichting": ""}],
        "opmerkingen": ""}
    client, _ = _nep_client(antwoord)
    with pytest.raises(ValueError):
        vraag_mapping(client, [["X"]], "Sheet1", 0, catalogus_voor_prompt([], {}))
