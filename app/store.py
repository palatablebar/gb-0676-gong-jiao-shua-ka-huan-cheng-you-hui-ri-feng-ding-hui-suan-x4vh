import sqlite3,json
from pathlib import Path
from app.config import DATA_DIR
from app.errors import DomainError
def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"records.db",timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核')")
    db.execute("CREATE TABLE IF NOT EXISTS compensations (run_id TEXT NOT NULL,transfer_key TEXT NOT NULL,payer TEXT NOT NULL,payee TEXT NOT NULL,amount TEXT NOT NULL,basis TEXT NOT NULL,PRIMARY KEY (run_id,transfer_key))")
    columns=[row[1] for row in db.execute("PRAGMA table_info(runs)")]
    if "reconciled" not in columns: db.execute("ALTER TABLE runs ADD COLUMN reconciled INTEGER NOT NULL DEFAULT 0")
    return db
def save(run_id,payload):
    ledger=[entry for stage in payload.get("stages",[]) for entry in stage.get("ledger",[])]
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO runs(id,payload) VALUES (?,?)",(run_id,json.dumps(payload,ensure_ascii=False)))
        for entry in ledger:
            db.execute("INSERT OR IGNORE INTO compensations(run_id,transfer_key,payer,payee,amount,basis) VALUES (?,?,?,?,?,?)",(run_id,entry["transfer_key"],entry["payer"],entry["payee"],entry["amount"],entry["basis"]))
    return get(run_id)
def get(run_id):
    with connect() as db: row=db.execute("SELECT payload,version,decision,reconciled FROM runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","批次不存在",404)
    return {**json.loads(row[0]),"version":row[1],"decision":row[2],"reconciled":bool(row[3])}
def latest():
    with connect() as db: row=db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return get(row[0]) if row else None
def history():
    with connect() as db: return [{"run_id":i,"version":v,"decision":d,"reconciled":bool(r)} for i,v,d,r in db.execute("SELECT id,version,decision,reconciled FROM runs ORDER BY rowid DESC")]
def review(run_id,version,decision):
    if decision not in {"已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    with connect() as db:
        cursor=db.execute("UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?",(decision,run_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): raise DomainError("NOT_FOUND","批次不存在",404)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get(run_id)
def reconcile(run_id):
    with connect() as db:
        cursor=db.execute("UPDATE runs SET reconciled=1 WHERE id=?",(run_id,))
        if cursor.rowcount!=1: raise DomainError("NOT_FOUND","批次不存在",404)
    return get(run_id)
def compensations(run_id):
    with connect() as db: return [{"run_id":r,"transfer_key":k,"payer":p,"payee":q,"amount":a,"basis":b} for r,k,p,q,a,b in db.execute("SELECT run_id,transfer_key,payer,payee,amount,basis FROM compensations WHERE run_id=? ORDER BY transfer_key",(run_id,))]
