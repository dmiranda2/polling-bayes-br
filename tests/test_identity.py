from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common import coerce_canonical, normalize_cnpj, pollster_cnpj_conflicts


def test_cnpj_csv_roundtrip():
    assert normalize_cnpj(19259002000128.0) == "19259002000128"
    assert normalize_cnpj(7630546000175.0) == "07630546000175"
    assert normalize_cnpj("07.630.546/0001-75") == "07630546000175"
    assert normalize_cnpj("-1") == ""
    assert normalize_cnpj("12345678901") == ""


def test_missing_cnpj_inherits_unambiguous_current_identity():
    df = pd.DataFrame([
        dict(election_year=2026, round=1, poll_id="BR-1/2026", pollster="Quaest", pollster_source="Quaest", pollster_cnpj="22445600000104", field_start="2026-09-01", field_end="2026-09-02", publish_date="2026-09-03", method="presencial", scenario="1º turno", candidate="Lula", pct=40),
        dict(election_year=2026, round=1, poll_id="", pollster="Quaest", pollster_source="Quaest", pollster_cnpj="", field_start="2026-09-10", field_end="2026-09-11", publish_date="2026-09-12", method="presencial", scenario="1º turno", candidate="Lula", pct=41),
    ])
    out = coerce_canonical(df)
    assert set(out["pollster_key"]) == {"CNPJ:22445600000104"}


def test_isolated_wrong_registration_does_not_steal_identity():
    rows = []
    # Datafolha dominates its real CNPJ.
    for i in range(4):
        rows.append(dict(election_year=2026, round=1, poll_id=f"BR-D{i}/2026", pollster="Datafolha", pollster_source="Datafolha", pollster_cnpj="07630546000175", field_start="2026-08-01", field_end="2026-08-02", publish_date="2026-08-03", method="presencial", scenario="1º turno", candidate="Lula", pct=40+i))
    # One Indexa row carries the wrong Datafolha registration/CNPJ.
    rows.append(dict(election_year=2026, round=1, poll_id="BR-WRONG/2026", pollster="Indexa", pollster_source="Indexa", pollster_cnpj="07630546000175", field_start="2026-07-01", field_end="2026-07-02", publish_date="2026-07-03", method="telefone", scenario="1º turno", candidate="Lula", pct=39))
    # Another Indexa survey establishes its own CNPJ.
    rows.append(dict(election_year=2026, round=1, poll_id="BR-I/2026", pollster="Indexa", pollster_source="Indexa/Broadcast", pollster_cnpj="10340949000194", field_start="2026-08-20", field_end="2026-08-23", publish_date="2026-08-26", method="telefone", scenario="1º turno", candidate="Lula", pct=39))
    df = pd.DataFrame(rows)
    conflicts = pollster_cnpj_conflicts(df)
    assert len(conflicts) == 1
    assert conflicts.iloc[0]["pollster"] == "Indexa"
    out = coerce_canonical(df)
    idx = out[out["pollster"].eq("Indexa")]
    assert set(idx["pollster_key"]) == {"CNPJ:10340949000194"}


if __name__ == "__main__":
    test_cnpj_csv_roundtrip()
    test_missing_cnpj_inherits_unambiguous_current_identity()
    test_isolated_wrong_registration_does_not_steal_identity()
    print("identity tests: OK")