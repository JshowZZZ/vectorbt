import importlib


def test_autowfo_modules_importable_with_expected_symbols():
    expected = {
        "autowfo.constants": ["LABELS", "INDICATOR_META", "INDICATOR_PARAM_FIELDS"],
        "autowfo.strategy_schema": ["load_strategy_schema", "validate_strategy_schema"],
        "autowfo.metric_contract": ["load_metric_contract", "validate_metric_contract"],
        "autowfo.artifact_contract": ["load_artifact_contract", "validate_artifact_contract"],
        "autowfo.data": ["_prepare_timeframe_context", "_load_or_update_symbol"],
        "autowfo.split_protocol": ["load_split_protocol", "validate_split_protocol"],
        "autowfo.split": ["_build_walk_forward_slices"],
        "autowfo.metrics": ["_calc_pf_series", "_aggregate_oos_metrics"],
        "autowfo.evaluator": ["evaluate_combo_task"],
        "autowfo.artifacts": ["_ensure_csv_schema", "_append_db_rows"],
        "autowfo.parallel": ["_run_combo_tasks"],
        "autowfo.registry": ["_update_run_registry"],
        "autowfo.strategy": ["_build_indicator_param_options_coarse", "_apply_indicator_combo"],
        "autowfo.search": ["_normalize_key_value", "_combo_key_from_dict"],
        "autowfo.ranking": ["_top_by_score", "_sort_by_score"],
        "autowfo.report": ["_df_to_html", "_plot_portfolio"],
        "autowfo.portfolio": ["_run_pf"],
        "autowfo.engine": ["DEFAULT_CONFIG"],
        "autowfo.baseline": ["_trigger_decision", "_comparison_summary"],
    }

    for module_name, symbols in expected.items():
        module = importlib.import_module(module_name)
        for symbol in symbols:
            assert hasattr(module, symbol), f"{module_name} missing symbol: {symbol}"

