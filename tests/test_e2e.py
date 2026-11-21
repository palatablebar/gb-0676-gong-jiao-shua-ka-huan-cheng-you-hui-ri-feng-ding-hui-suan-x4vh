import csv,io
from app.pipeline import execute,load_sample
from app import store
def test_full_sample_flow(client):
    r=client.post("/api/runs",json={"sample":"dirty.csv"});assert r.status_code==200
    p=r.get_json();assert len(p["stages"])==8
    assert p["stages"][5]["metrics"]["balanced"] is True
def test_idempotent_real_input(sample):
    a=execute(sample);b=execute(sample)
    assert a["run_id"]==b["run_id"] and len(store.history())==1
def test_stale_review_409(client):
    "TRAP-26 陈旧复核不得覆盖新版本"
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json();u="/api/runs/"+p["run_id"]+"/review"
    assert client.post(u,json={"version":1,"decision":"已复核"}).status_code==200
    assert client.post(u,json={"version":1,"decision":"退回复核"}).status_code==409
def test_export_has_manifest_and_quarantine(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    r=client.get("/api/runs/"+p["run_id"]+"/archive")
    rows=list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert rows[0][1]=="input_sha256" and any(x[3]=="quarantine" for x in rows[1:])
def test_failed_import_is_atomic(client):
    assert client.post("/api/runs",json={"csv":"bad"}).status_code==422
    assert store.history()==[]
def test_module_entrances(client):
    from app.config import MODULES
    for slug,name in MODULES:
        assert client.get("/api/"+slug).status_code==200
        assert client.get("/"+slug).status_code==200
def test_missing_run_404(client): assert client.get("/api/runs/missing").status_code==404
def test_reconcile_flow(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    assert p["reconciled"] is False and p["stages"][6]["metrics"]["compensation_total"]=="8.00"
    assert client.get("/settlement").data.decode().count("暂缓封存")>=1
    r=client.post("/api/runs/"+p["run_id"]+"/reconcile");assert r.status_code==200
    assert r.get_json()["reconciled"] is True
    assert client.post("/api/runs/"+p["run_id"]+"/reconcile").status_code==200
    assert "可封存" in client.get("/settlement").data.decode()
    c=client.get("/api/runs/"+p["run_id"]+"/compensations").get_json()["compensations"]
    assert len(c)==8 and {x["payer"] for x in c}=={"甲企业"} and {x["payee"] for x in c}=={"乙企业"}
def test_reconcile_missing_run_404(client): assert client.post("/api/runs/missing/reconcile").status_code==404
def test_compensations_missing_run_404(client): assert client.get("/api/runs/missing/compensations").status_code==404
def test_failed_switch_defers_settlement(client):
    switch={"attribution_switch":[{"route":"03","enterprise":"丙企业","start":"2026-11-01T00:00:00+08:00"}]}
    p=client.post("/api/runs",json={"sample":"dirty.csv","parameters":switch}).get_json()
    assert p["stages"][6]["metrics"]["switch_failed"]==1 and p["stages"][6]["metrics"]["reconciled"] is False
    assert p["stages"][7]["metrics"]["ready"] is False and p["stages"][7]["metrics"]["deferred"] is True
    assert any(q["reason"]=="SWITCH_REJECTED" for q in p["stages"][6]["cumulative_quarantine"])
def test_adjudication_page(client):
    client.post("/api/runs",json={"sample":"dirty.csv"})
    html=client.get("/adjudication").data.decode()
    for text in ("裁决结论","换乘前后程对照","责任企业","责任依据","企业间补偿台账","归属差异","甲企业","乙企业"): assert text in html
