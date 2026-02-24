from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import constants as c


def test_constants_reexport_identity():
    # Keep backward compatibility while moving data out of the monolith.
    assert sweep.LABELS is c.LABELS
    assert sweep.INDICATOR_META is c.INDICATOR_META
    assert sweep.INDICATOR_PARAM_FIELDS is c.INDICATOR_PARAM_FIELDS
    assert sweep.REGIME_NAME_MAP is c.REGIME_NAME_MAP
    assert sweep.REGIME_TYPE_MAP is c.REGIME_TYPE_MAP


def test_constants_characterization_snapshot():
    # Characterization checks for extracted constant payload.
    assert c.LABELS["report_title"] == c._html_entity(c._u("\\u56de\\u6e2c\\u5831\\u544a"))
    assert c.LABELS["status_title"] == c._html_entity(c._u("\\u57f7\\u884c\\u72c0\\u614b"))
    assert len(c.INDICATOR_META) == 25
    assert len(c.REGIME_NAME_MAP) == 8
    assert "ma_trend" in c.INDICATOR_META
    assert "cci" in c.INDICATOR_META
    assert "chop" in c.INDICATOR_META
    assert "trend_high" in c.REGIME_NAME_MAP
