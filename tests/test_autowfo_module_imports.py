import importlib


def test_autowfo_modules_importable_with_expected_symbols():
    expected = {
        "scripts.autowfo.constants": ["LABELS", "INDICATOR_META", "INDICATOR_PARAM_FIELDS"],
        "scripts.autowfo.strategy_schema": ["load_strategy_schema", "validate_strategy_schema"],
        "scripts.autowfo.metric_contract": ["load_metric_contract", "validate_metric_contract"],
        "scripts.autowfo.artifact_contract": ["load_artifact_contract", "validate_artifact_contract"],
        "scripts.autowfo.data": ["_prepare_timeframe_context", "_load_or_update_symbol"],
        "scripts.autowfo.split_protocol": ["load_split_protocol", "validate_split_protocol"],
        "scripts.autowfo.split": ["_build_walk_forward_slices"],
        "scripts.autowfo.metrics": ["_calc_pf_series", "_aggregate_oos_metrics"],
        "scripts.autowfo.evaluator": ["evaluate_combo_task"],
        "scripts.autowfo.artifacts": ["_ensure_csv_schema", "_append_db_rows"],
        "scripts.autowfo.parallel": ["_run_combo_tasks"],
        "scripts.autowfo.registry": ["_update_run_registry"],
        "scripts.autowfo.strategy": ["_build_indicator_param_options_coarse", "_apply_indicator_combo"],
        "scripts.autowfo.search": ["_normalize_key_value", "_combo_key_from_dict"],
        "scripts.autowfo.ranking": ["_top_by_score", "_sort_by_score"],
        "scripts.autowfo.report": ["_df_to_html", "_plot_portfolio"],
        "scripts.autowfo.portfolio": ["_run_pf"],
        "scripts.autowfo.engine": ["DEFAULT_CONFIG"],
        "scripts.autowfo.baseline": ["_trigger_decision", "_comparison_summary"],
    }

    for module_name, symbols in expected.items():
        module = importlib.import_module(module_name)
        for symbol in symbols:
            assert hasattr(module, symbol), f"{module_name} missing symbol: {symbol}"
