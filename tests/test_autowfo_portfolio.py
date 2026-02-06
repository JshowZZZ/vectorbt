import numpy as np
import pandas as pd

from scripts import run_btc_regime_sweep as sweep
from scripts.autowfo import portfolio as p


def test_run_pf_wrapper_matches_module():
    index = pd.date_range("2024-01-01", periods=30, freq="h")
    trade_close = pd.DataFrame(
        {
            "ETH/BTC": np.linspace(1.0, 2.0, len(index)),
            "BNB/BTC": np.linspace(1.2, 2.1, len(index)),
        },
        index=index,
    )
    long_regime = pd.Series(True, index=index)
    short_regime = pd.Series(False, index=index)
    kwargs = dict(
        trade_close=trade_close,
        long_regime=long_regime,
        short_regime=short_regime,
        max_hold=2,
        fees=0.001,
        sl_stop=None,
        tp_stop=None,
        freq="1h",
        slippage=0.0,
        init_cash=1.0,
        size=1.0,
        size_type="percent",
        cash_sharing=True,
        lock_cash=True,
        allow_partial=False,
        max_positions=None,
    )
    pf_module = p._run_pf(**kwargs)
    pf_wrapper = sweep._run_pf(**kwargs)

    module_ret = float(pf_module.total_return(group_by=True))
    wrapper_ret = float(pf_wrapper.total_return(group_by=True))
    assert np.isclose(wrapper_ret, module_ret, equal_nan=True)
