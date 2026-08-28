import pytest

from veldcatalogus import (
    EENHEID_OPTIES,
    VELDEN,
    catalogus_voor_prompt,
    converteer,
    veld,
)


def test_kernvelden_aanwezig():
    ids = {v.id for v in VELDEN}
    for verwacht in [
        "sleutel_artikelcode", "sleutel_ean", "sleutel_omschrijving",
        "gn_code", "netto_gewicht", "bruto_gewicht",
        "lengte", "breedte", "hoogte",
        "collo_lengte", "collo_breedte", "collo_hoogte",
        "ean", "omschrijving", "min_verkoophoeveelheid",
        "un_code", "klasse", "verpakkingsgroep", "adr_naam", "vlampunt",
        "ufi", "voc", "ghs", "geen",
    ]:
        assert verwacht in ids


def test_ids_uniek():
    ids = [v.id for v in VELDEN]
    assert len(ids) == len(set(ids))


def test_veld_opzoeken():
    assert veld("gn_code").label.startswith("Douanetariefnummer")
    assert veld("netto_gewicht").eenheid == "g"
    assert veld("lengte").eenheid == "mm"
    assert veld("onbekend") is None


def test_dynamische_velden():
    r = veld("ruw:UFI-code")
    assert r is not None and r.soort == "ruw" and r.label == "UFI-code"
    v = veld("vast:ursprungsland")
    assert v is not None and v.soort == "vast" and v.label == "ursprungsland"


@pytest.mark.parametrize("waarde, van, naar, verwacht", [
    (318, "g", "kg", 0.318),
    (0.5, "kg", "g", 500),
    (184, "mm", "cm", 18.4),
    (18.4, "cm", "mm", 184),
    (1200, "mm", "m", 1.2),
    (7, "g", "g", 7),
    (7, None, "g", 7),
    (7, "g", None, 7),
])
def test_converteer(waarde, van, naar, verwacht):
    assert converteer(waarde, van, naar) == pytest.approx(verwacht)


def test_converteer_verschillende_dimensies_faalt():
    with pytest.raises(ValueError):
        converteer(1, "g", "mm")


def test_catalogus_voor_prompt_bevat_ruw_en_vast():
    cat = catalogus_voor_prompt(["UFI-code", "VOC-content"], {"ursprungsland": "Land van oorsprong"})
    ids = [c["id"] for c in cat]
    assert "gn_code" in ids
    assert "ruw:UFI-code" in ids
    assert "vast:ursprungsland" in ids
    assert all(set(c) == {"id", "label", "broneenheid", "uitleg"} for c in cat)
    netto = next(c for c in cat if c["id"] == "netto_gewicht")
    assert netto["broneenheid"] == "g"


def test_eenheid_opties():
    assert None in EENHEID_OPTIES
    assert {"g", "kg", "mm", "cm", "m", "stuks"} <= set(o for o in EENHEID_OPTIES if o)
