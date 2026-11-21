from app.modules.m7_adjudication.rules import evaluate,ATTRIBUTIONS,RULING_ID
from app.pipeline import execute,calculate
from app import store
from decimal import Decimal
def leg(id,route="01",anchor="—",discount="0.00",at="2026-11-16T00:00:00+00:00",expected="2.50"):
    return {"event_id":id,"card":"0001","route":route,"at":at,"business_day":"2026-11-16","base_fare":"2.50","transfer_anchor":anchor,"transfer_discount":discount,"expected":expected,"reported":expected,"difference":"0","status":"通过","_line":2,"_sources":[2]}
def test_real_cross_transfers(result):
    m=result["stages"][6]["metrics"]
    assert m["transfers"]==16 and m["cross_transfers"]==8 and m["compensation_total"]=="8.00" and m["ledger_entries"]==8
def test_real_unique_responsible_per_transfer(result):
    transfers=[t for t in result["stages"][6]["transfers"] if t["cross_enterprise"]]
    assert len(transfers)==8
    for t in transfers:
        assert t["responsible"]=="甲企业" and t["responsible"]==t["prior_enterprise"]
        assert t["compensation"]==t["discount"]=="1.00" and t["booked"]=="乙企业" and t["difference"]=="1.00"
def test_real_ledger_keys_unique(result):
    keys=[e["transfer_key"] for e in result["stages"][6]["ledger"]]
    assert len(keys)==len(set(keys))
def test_real_enterprise_summary_conserved(result):
    summary={s["enterprise"]:s for s in result["stages"][6]["enterprise_summary"]}
    assert summary["甲企业"]["payable"]=="8.00" and summary["甲企业"]["net"]=="-8.00"
    assert summary["乙企业"]["reduce_total"]=="16.00" and summary["乙企业"]["receivable"]=="8.00" and summary["乙企业"]["net"]=="8.00"
    assert sum((Decimal(s["net"]) for s in summary.values()),Decimal(0))==Decimal("0.00")
    assert sum((Decimal(s["payable"]) for s in summary.values()),Decimal(0))==sum((Decimal(s["receivable"]) for s in summary.values()),Decimal(0))
def test_cross_transfer_adjudication():
    r=evaluate([leg("A1","01"),leg("B1","02",anchor="A1",discount="1.00",expected="1.50")],{})
    t=r["transfers"][0]
    assert t["cross_enterprise"] is True and t["responsible"]=="甲企业" and t["compensation"]=="1.00"
    assert t["booked"]=="乙企业" and t["difference"]=="1.00" and RULING_ID in t["basis"]
    rows={row["event_id"]:row for row in r["rows"]}
    assert rows["A1"]["transfer_role"]=="前程" and rows["A1"]["enterprise"]=="甲企业"
    assert rows["B1"]["transfer_role"]=="后程" and rows["B1"]["responsible_enterprise"]=="甲企业" and rows["B1"]["compensation"]=="1.00"
def test_same_enterprise_no_compensation():
    r=evaluate([leg("A1","02"),leg("B1","03",anchor="A1",discount="1.00")],{})
    t=r["transfers"][0]
    assert t["cross_enterprise"] is False and t["compensation"]=="0.00" and t["responsible"]=="乙企业"
    assert r["ledger"]==[] and r["metrics"]["reconciled"] is True
def test_mid_leg_has_both_roles():
    r=evaluate([leg("A1","01"),leg("B1","02",anchor="A1",discount="1.00"),leg("C1","03",anchor="B1",discount="1.00")],{})
    rows={row["event_id"]:row for row in r["rows"]}
    assert rows["B1"]["transfer_role"]=="后程·前程"
def test_switch_failure_keeps_old_version():
    context={"parameters":{"attribution_switch":[{"route":"03","enterprise":"丙企业","start":"2026-11-01T00:00:00+08:00"}]}}
    r=evaluate([leg("A1","03")],context)
    assert r["metrics"]["switch_failed"]==1 and r["metrics"]["switch_applied"]==0
    assert r["rows"][0]["enterprise"]=="乙企业" and r["rows"][0]["attrib_version"]=="OP-03-A"
    assert r["metrics"]["reconciled"] is False
    assert any(q["reason"]=="SWITCH_REJECTED" for q in r["quarantine"])
def test_switch_noop_rejected():
    context={"parameters":{"attribution_switch":[{"route":"01","enterprise":"甲企业","start":"2026-11-01T00:00:00+08:00"}]}}
    r=evaluate([leg("A1","01")],context)
    assert r["metrics"]["switch_failed"]==1 and r["rows"][0]["enterprise"]=="甲企业"
def test_switch_batch_atomic():
    context={"parameters":{"attribution_switch":[{"route":"03","enterprise":"甲企业","start":"2026-11-01T00:00:00+08:00"},{"route":"02","enterprise":"丙企业","start":"2026-11-01T00:00:00+08:00"}]}}
    r=evaluate([leg("A1","03"),leg("B1","02")],context)
    assert r["metrics"]["switch_failed"]==2 and r["metrics"]["switch_applied"]==0
    assert {row["event_id"]:row["enterprise"] for row in r["rows"]}=={"A1":"乙企业","B1":"乙企业"}
def test_valid_switch_applies_from_effective_time():
    context={"parameters":{"attribution_switch":[{"route":"03","enterprise":"甲企业","start":"2026-11-01T00:00:00+08:00"}]}}
    r=evaluate([leg("OLD","03",at="2026-06-01T00:00:00+00:00"),leg("NEW","03")],context)
    rows={row["event_id"]:row for row in r["rows"]}
    assert r["metrics"]["switch_applied"]==1 and r["metrics"]["reconciled"] is True
    assert rows["OLD"]["enterprise"]=="乙企业" and rows["NEW"]["enterprise"]=="甲企业"
def test_switch_changes_cross_transfers(sample):
    r=calculate(sample,{"attribution_switch":[{"route":"03","enterprise":"甲企业","start":"2026-11-01T00:00:00+08:00"}]})
    m=r["stages"][6]["metrics"]
    assert m["cross_transfers"]==16 and m["compensation_total"]=="16.00" and m["switch_applied"]==1
def test_missing_attribution_quarantined():
    r=evaluate([leg("A1","01",at="2027-06-01T00:00:00+00:00")],{})
    assert r["rows"]==[] and r["quarantine"][0]["reason"]=="NO_ATTRIBUTION"
    assert r["metrics"]["reconciled"] is False and r["metrics"]["attribution_missing"]==1
def test_retry_no_duplicate_compensation(sample):
    a=execute(sample);b=execute(sample)
    assert a["run_id"]==b["run_id"] and len(store.history())==1
    assert len(store.compensations(a["run_id"]))==8
def test_compensation_ledger_matches_stage(sample):
    run=execute(sample)
    table={e["transfer_key"]:e for e in store.compensations(run["run_id"])}
    stage={e["transfer_key"]:e for e in run["stages"][6]["ledger"]}
    assert table.keys()==stage.keys()
    for key in table: assert table[key]["amount"]==stage[key]["amount"]=="1.00" and table[key]["payer"]=="甲企业" and table[key]["payee"]=="乙企业"
def test_sources_and_basis_preserved(result):
    for t in result["stages"][6]["transfers"]:
        assert len(t["_sources"])==2 and all(isinstance(x,int) and x>1 for x in t["_sources"])
        assert t["basis"] and t["prior_version"] and t["next_version"]
    for row in result["stages"][6]["rows"]:
        assert row["event_id"] and row["event_time"] and row["_raw"] and row["enterprise"] and row["attrib_version"]
def test_archive_keeps_attribution_evidence(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    text=client.get("/api/runs/"+p["run_id"]+"/archive").data.decode("utf-8-sig")
    assert "OP-01-A" in text and "OP-02-A" in text and "甲企业" in text
def test_ruling_present(result):
    ruling=result["stages"][6]["ruling"]
    assert ruling["id"]==RULING_ID and "前序企业" in ruling["text"] and len(ruling["reasons"])==3
