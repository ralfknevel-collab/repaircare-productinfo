import asyncio
import json
import time
from types import SimpleNamespace

import anthropic
import httpx
import pytest

import mapping as mapping_module

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


def test_mapping_oude_json_zonder_beginrij_blijft_bruikbaar():
    m = Mapping.uit_dict({"kopregel_index": 2, "kolommen": [], "opmerkingen": "oud"})
    assert m == Mapping(2, [], "oud")
    assert m.data_start_index is None


def test_mapping_rondreis_bewaart_afzonderlijke_beginrij():
    m = Mapping(2, [KolomMapping("Gewicht", "netto_gewicht", "kg", "hoog", "")], "ok", 5)
    opgeslagen = json.loads(json.dumps(m.naar_dict()))
    assert opgeslagen["data_start_index"] == 5
    assert Mapping.uit_dict(opgeslagen) == m


def test_lege_mapping():
    m = lege_mapping(1, ["A", "B"])
    assert m.kopregel_index == 1
    assert all(k.doelveld == "geen" and k.zekerheid == "laag" for k in m.kolommen)
    assert [k.kolom for k in m.kolommen] == ["A", "B"]


def test_schema_is_strict_en_bevat_enums():
    s = mapping_schema(["gn_code", "geen", "sleutel_ean"])
    assert s["type"] == "object" and s["additionalProperties"] is False
    assert set(s["required"]) == {"kopregel_index", "data_start_index", "kolommen", "opmerkingen"}
    assert s["properties"]["data_start_index"]["type"] == "integer"
    kolom = s["properties"]["kolommen"]["items"]
    assert kolom["additionalProperties"] is False
    assert kolom["properties"]["doelveld"]["enum"] == ["gn_code", "geen", "sleutel_ean"]
    assert kolom["properties"]["eenheid"]["type"] == "string"
    assert "" in kolom["properties"]["eenheid"]["enum"] and None not in kolom["properties"]["eenheid"]["enum"]
    assert set(kolom["properties"]["zekerheid"]["enum"]) == {"hoog", "middel", "laag"}


def test_bouw_fragment():
    rijen = [["ArtNr", "Gewicht"], ["2010005", None], ["2511105", 452]]
    tekst = bouw_fragment(rijen, "Sheet1", 27)
    assert "Sheet1" in tekst and "27" in tekst
    assert "rij 0" in tekst and "ArtNr" in tekst and "2511105" in tekst


def _nep_client(antwoord: dict):
    """Echte SDK met lokaal gesimuleerde HTTP-stream; geen netwerkverkeer."""
    aanroepen = []
    inhoud = _sse_antwoord([SimpleNamespace(type="text", text=json.dumps(antwoord))])
    def antwoord_http(request):
        aanroepen.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=inhoud)
    client = anthropic.AsyncAnthropic(api_key="test", http_client=httpx.AsyncClient(
        transport=httpx.MockTransport(antwoord_http)))
    return client, aanroepen


def _sse(event):
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()


def _sse_antwoord(content, stop_reason="end_turn"):
    events = [{"type": "message_start", "message": {
        "id": "msg_test", "type": "message", "role": "assistant", "model": MODEL,
        "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 0},
    }}]
    for index, blok in enumerate(content):
        events.append({"type": "content_block_start", "index": index,
                       "content_block": {"type": "text", "text": ""} if blok.type == "text" else vars(blok)})
        if blok.type == "text":
            events.append({"type": "content_block_delta", "index": index,
                           "delta": {"type": "text_delta", "text": blok.text}})
        events.append({"type": "content_block_stop", "index": index})
    events += [{"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 10}}, {"type": "message_stop"}]
    return b"".join(_sse(event) for event in events)


def test_vraag_mapping_gebruikt_schema_en_parset_antwoord():
    antwoord = {
        "kopregel_index": 0,
        "data_start_index": 1,
        "kolommen": [
            {"kolom": "HerstellerArtNr", "doelveld": "sleutel_artikelcode", "eenheid": "",
             "zekerheid": "hoog", "toelichting": ""},
            {"kolom": "Nettogewicht", "doelveld": "netto_gewicht", "eenheid": "g",
             "zekerheid": "middel", "toelichting": "gram volgens mail"},
        ],
        "opmerkingen": "ok",
    }
    client, aanroepen = _nep_client(antwoord)
    cat = catalogus_voor_prompt(["UFI-code"], {"ursprungsland": "Land"})
    m = vraag_mapping(client, [["HerstellerArtNr", "Nettogewicht"], ["2010005", None]], "Sheet1", 2, cat)

    assert isinstance(m, Mapping)
    assert m.kolommen[1].doelveld == "netto_gewicht" and m.kolommen[1].eenheid == "g"
    assert m.opmerkingen == "ok"
    assert m.kolommen[0].eenheid is None
    assert m.data_start_index == 1

    kw = aanroepen[0]
    assert kw["model"] == MODEL
    assert kw["output_config"]["format"]["type"] == "json_schema"
    enum = kw["output_config"]["format"]["schema"]["properties"]["kolommen"]["items"]["properties"]["doelveld"]["enum"]
    assert "ruw:UFI-code" in enum and "vast:ursprungsland" in enum and "gn_code" in enum
    systeem = kw["system"]
    assert isinstance(systeem, list) and systeem[0]["cache_control"] == {"type": "ephemeral"}
    assert "ruw:UFI-code" in systeem[0]["text"]
    assert "HerstellerArtNr" in kw["messages"][0]["content"]


@pytest.mark.parametrize("kopregel,beginrij", [
    (-1, 1), (3, 4), (1.5, 2), (True, 2), ("1", 2),
    (0, -1), (1, 1), (1, 4), (0, 1.5), (0, True), (0, "2"),
])
def test_vraag_mapping_weigert_ongeldige_rij_indices(kopregel, beginrij):
    antwoord = {"kopregel_index": kopregel, "data_start_index": beginrij,
                "kolommen": [], "opmerkingen": ""}
    client, _ = _nep_client(antwoord)
    with pytest.raises(ValueError, match="kopregel_index|data_start_index"):
        vraag_mapping(client, [["Kop"], ["Eenheid"], ["2010005"]], "Sheet1", 3, [])


def test_vraag_mapping_kop_moet_in_aangeleverde_rijen_staan():
    client, _ = _nep_client({"kopregel_index": 2, "data_start_index": 3,
                           "kolommen": [], "opmerkingen": ""})
    with pytest.raises(ValueError, match="kopregel_index"):
        vraag_mapping(client, [["Titel"], ["Kop"]], "Sheet1", 20, [])


def test_vraag_mapping_kop_moet_in_werkblad_staan():
    client, _ = _nep_client({"kopregel_index": 2, "data_start_index": 3,
                           "kolommen": [], "opmerkingen": ""})
    with pytest.raises(ValueError, match="kopregel_index"):
        vraag_mapping(client, [["Titel"], ["Kop"], ["Eenheid"]], "Sheet1", 2, [])


@pytest.mark.parametrize("antwoord,verwachte_beginrij", [
    ({"kopregel_index": 0, "data_start_index": 2}, 2),
    ({"kopregel_index": 0, "data_start_index": 3}, 3),
    ({"kopregel_index": 0}, None),
])
def test_vraag_mapping_accepteert_beginrij_en_oude_mapping(antwoord, verwachte_beginrij):
    client, _ = _nep_client({**antwoord, "kolommen": [], "opmerkingen": ""})
    m = vraag_mapping(client, [["Kop"], ["Eenheid"], [None]], "Leeg sjabloon", 3, [])
    assert m.data_start_index == verwachte_beginrij


def test_vraag_mapping_onbekend_doelveld_faalt():
    antwoord = {"kopregel_index": 0, "kolommen": [
        {"kolom": "X", "doelveld": "bestaat_niet", "eenheid": None, "zekerheid": "hoog", "toelichting": ""}],
        "opmerkingen": ""}
    client, _ = _nep_client(antwoord)
    with pytest.raises(ValueError, match="Onbekende doelvelden"):
        vraag_mapping(client, [["X"]], "Sheet1", 1, catalogus_voor_prompt([], {}))


def _nep_client_ruw(content, stop_reason="end_turn"):
    return anthropic.AsyncAnthropic(api_key="test", http_client=httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse_antwoord(content, stop_reason)))))


@pytest.mark.parametrize("actief", [False, True])
def test_totale_wachttijd_is_begrensd_ook_bij_blijvende_pings(monkeypatch, actief):
    monkeypatch.setattr(mapping_module, "MAPPING_TIMEOUT_SECONDS", 0.05, raising=False)
    class TrageStream(httpx.AsyncByteStream):
        gesloten = False
        async def __aiter__(self):
            # Eindig ook zonder de productielimiet, zodat een regressie niet de test ophangt.
            for _ in range(30):
                await asyncio.sleep(0.01)
                if actief:
                    yield _sse({"type": "ping"})
            yield _sse_antwoord([SimpleNamespace(type="text", text='{"kopregel_index":0,"kolommen":[]}')])
        async def aclose(self):
            self.gesloten = True
    stream = TrageStream()
    client = anthropic.AsyncAnthropic(api_key="test", http_client=httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=stream))))
    begin = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        vraag_mapping(client, [["Artikelnummer"], ["2010005"]], "Sheet1", 2, [])
    assert time.monotonic() - begin < 0.3
    assert stream.gesloten and client.is_closed()


def test_http_wachttijd_en_herhalingen_zijn_begrensd():
    verzoeken = []
    def antwoord_http(request):
        verzoeken.append(request)
        raise httpx.ReadTimeout("Geen antwoord", request=request)
    client = anthropic.AsyncAnthropic(api_key="test", http_client=httpx.AsyncClient(
        transport=httpx.MockTransport(antwoord_http)))
    with pytest.raises(anthropic.APITimeoutError):
        vraag_mapping(client, [["Artikelnummer"], ["2010005"]], "Sheet1", 2, [])
    assert len(verzoeken) == 1
    assert all(waarde <= 30 for waarde in verzoeken[0].extensions["timeout"].values())
    assert client.is_closed()


@pytest.mark.parametrize("fout", [httpx.ReadTimeout("Geen vervolg"),
                                 httpx.RemoteProtocolError("Verbinding verbroken")])
def test_streamonderbreking_geeft_geen_deelantwoord_en_sluit_verbinding(fout):
    class GebrokenStream(httpx.AsyncByteStream):
        gesloten = False
        async def __aiter__(self):
            volledig = _sse_antwoord([SimpleNamespace(type="text", text='{"kopregel_index":')])
            yield volledig.split(b"event: content_block_stop")[0]
            raise fout
        async def aclose(self):
            self.gesloten = True
    stream = GebrokenStream()
    client = anthropic.AsyncAnthropic(api_key="test", http_client=httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=stream))))
    with pytest.raises(type(fout)):
        vraag_mapping(client, [["Artikelnummer"], ["2010005"]], "Sheet1", 2, [])
    assert stream.gesloten and client.is_closed()


def test_voortgang_toont_geen_antwoordtekst_en_client_sluit():
    client, _ = _nep_client({"kopregel_index": 0, "kolommen": [], "opmerkingen": "vertrouwelijke tekst"})
    meldingen = []
    m = vraag_mapping(client, [["Artikelnummer"], ["2010005"]], "Sheet1", 2, [], voortgang=meldingen.append)
    assert m.opmerkingen == "vertrouwelijke tekst"
    assert meldingen and all("vertrouwelijke tekst" not in tekst for tekst in meldingen)
    assert len(meldingen) <= 2
    assert client.is_closed()


def test_vraag_mapping_zonder_tekstblok_faalt_duidelijk():
    client = _nep_client_ruw([SimpleNamespace(type="thinking", thinking="")])
    with pytest.raises(ValueError, match="geen tekstblok"):
        vraag_mapping(client, [["X"]], "Sheet1", 0, catalogus_voor_prompt([], {}))


def test_vraag_mapping_afgekapt_of_geweigerd_faalt_duidelijk():
    client = _nep_client_ruw([SimpleNamespace(type="text", text='{"kopregel_index": 0, "kolom')], stop_reason="max_tokens")
    with pytest.raises(ValueError, match="stop_reason=max_tokens"):
        vraag_mapping(client, [["X"]], "Sheet1", 0, catalogus_voor_prompt([], {}))
    client = _nep_client_ruw([SimpleNamespace(type="text", text='{"kopregel_index": 0, "kolom')])
    with pytest.raises(ValueError, match="geen geldige JSON"):
        vraag_mapping(client, [["X"]], "Sheet1", 0, catalogus_voor_prompt([], {}))
