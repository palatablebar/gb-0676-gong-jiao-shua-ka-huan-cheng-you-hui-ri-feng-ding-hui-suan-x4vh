from app.modules.m8_settlement.rules import evaluate
from app.errors import DomainError
import pytest
def test_real_sample_archive_ready(result): assert result["stages"][7]["metrics"]["ready"] is True
def test_real_sample_archive_source_count(result): assert result["stages"][7]["metrics"]["source_lines"]==result["stages"][5]["metrics"]["accepted_inputs"]
def test_real_sample_seal_stable(result):
    rows=result["stages"][6]["rows"];assert evaluate(rows,{})["metrics"]["sha256"]==evaluate(rows,{})["metrics"]["sha256"]
def test_unbalanced_blocked():
    with pytest.raises(DomainError) as e:evaluate([],{"reconcile":{"metrics":{"balanced":False}}})
    assert e.value.code=="UNBALANCED"
def test_duplicate_archive_key():
    with pytest.raises(DomainError):evaluate([{"event_id":"1"},{"event_id":"1"}],{})
def test_real_sample_manifest_has_hash(result): assert len(result["manifest"]["input_sha256"])==64
def test_real_sample_export_rows_match(result): assert result["stages"][7]["rows"]==result["stages"][6]["rows"]
def test_unreconciled_defers_seal():
    r=evaluate([],{"adjudication":{"metrics":{"reconciled":False,"compensation_total":"8.00","cross_transfers":8}}})
    m=r["metrics"];assert m["ready"] is False and m["deferred"] is True and "暂缓封存" in m["defer_reason"]
def test_reconciled_allows_seal():
    r=evaluate([],{"adjudication":{"metrics":{"reconciled":True,"compensation_total":"8.00","cross_transfers":8}}})
    assert r["metrics"]["ready"] is True and r["metrics"]["deferred"] is False
def test_no_adjudication_stage_defaults_ready():
    assert evaluate([],{})["metrics"]["ready"] is True
def test_real_sample_not_deferred(result):
    m=result["stages"][7]["metrics"];assert m["deferred"] is False and m["reconciled"] is True and m["compensation_total"]=="8.00"
