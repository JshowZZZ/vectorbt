"""Deep diagnostic: compare seen_key from CSV vs runtime-generated key."""
import sys; sys.path.insert(0, ".")
import pandas as pd, numpy as np, json
from autowfo import engine_helpers as E, search as S, artifacts as A
from autowfo.engine_helpers import _strip_data_range_from_combo_key

ROW_META = list(A.ROW_METADATA_FIELDS)
SCHEMA = E._build_sweep_schema_fields(artifact_row_metadata_fields=ROW_META)
CKF = SCHEMA["combo_key_fields"]
SCF = SCHEMA["strict_config_fields"]
defaults = E._SEEN_KEY_NULL_FIELD_DEFAULTS

ckfn = lambda v: S._combo_key_from_dict(v, CKF)
hacf = lambda v: E._has_all_config_fields(v, SCF)

# Load CSV
df = pd.read_csv("artifacts/param_sweep_combo_summary.csv", low_memory=False)
print(f"rows={len(df)}")

# Build seen_keys
r = E._build_seen_keys(df, has_all_config_fields_fn=hacf, combo_key_from_dict_fn=ckfn)
stripped_seen = r["stripped"]
print(f"stripped_seen={len(stripped_seen)}")

# Load config
with open("artifacts/sweep_config.json") as f:
    config = json.load(f)

# Show the relevant config values
print(f"\n--- Config values for key fields ---")
print(f"  trade_symbols_key from config: {config.get('trade_symbols')}")
print(f"  exchange: {config.get('exchange')}")
print(f"  base_symbol: {config.get('base_symbol')}")
print(f"  data_days: {config.get('data_days')}")
print(f"  capital_mode: {config.get('capital_mode')}")
print(f"  fees: {config.get('fees')}")
print(f"  wf_train_days: {config.get('wf_train_days')}")
print(f"  wf_test_days: {config.get('wf_test_days')}")
print(f"  wf_step_days: {config.get('wf_step_days')}")
print(f"  wf_valid_days: {config.get('wf_valid_days')}")
print(f"  wf_mode: {config.get('wf_mode')}")

# Pick a row from the LATEST data_end group
latest_end = df['data_end'].value_counts().index[0]
latest_rows = df[df['data_end'] == latest_end]
print(f"\nLatest data_end={latest_end}, rows={len(latest_rows)}")

# Take first row from latest group
row = latest_rows.iloc[0].to_dict()
filled_row = dict(row)
for field, default in defaults.items():
    val = filled_row.get(field)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        filled_row[field] = default

# Build key from CSV row
csv_key = ckfn(filled_row)
csv_stripped = _strip_data_range_from_combo_key(csv_key)

print(f"\n--- CSV Row stripped key ---")
print(f"  In seen_keys: {csv_stripped in stripped_seen}")
# Split the key into parts for readability
print(f"  Key parts:")
for part in csv_stripped.split("|"):
    print(f"    {part}")

# Now simulate just the key fields changing trade_symbols to what config says
ts_key = config.get("trade_symbols", [])
if isinstance(ts_key, list):
    ts_key = ",".join(ts_key)
# The config trade_symbols_key
print(f"\n  config trade_symbols_key: {ts_key!r}")
print(f"  csv trade_symbols_key: {row.get('trade_symbols_key')!r}")

# Check: how many seen_keys match the current config's trade_symbols_key?
matching = [k for k in stripped_seen if f"trade_symbols_key={ts_key}" in k]
print(f"\n--- Seen keys matching current config trade_symbols_key ---")
print(f"  Matching: {len(matching)} out of {len(stripped_seen)}")

# Also check data_days
dd = config.get("data_days")
matching_dd = [k for k in matching if f"data_days={dd}" in k]
print(f"  Also matching data_days={dd}: {len(matching_dd)}")

# Check timeframes
tfs = config.get("timeframes")
if tfs:
    for tf in tfs:
        m = [k for k in matching_dd if f"timeframe={tf}" in k]
        print(f"    timeframe={tf}: {len(m)} keys")

# Check total unique combos per timeframe in the config matching subset
if matching_dd:
    print(f"\n--- Sample matching key ---")
    for part in matching_dd[0].split("|"):
        print(f"    {part}")

