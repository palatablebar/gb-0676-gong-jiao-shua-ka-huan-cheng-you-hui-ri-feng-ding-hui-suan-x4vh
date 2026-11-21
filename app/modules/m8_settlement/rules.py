import hashlib,json
from decimal import Decimal
from app.errors import DomainError
from app.reasons import sources
def evaluate(rows,context):
    stages=[v for v in context.values() if isinstance(v,dict) and "metrics" in v]
    balances=[s["metrics"]["balanced"] for s in stages if "balanced" in s["metrics"]]
    if balances and not all(balances): raise DomainError("UNBALANCED","来源行未对平，不能归档")
    ids=[str(r.get("event_id",r.get("_line",""))) for r in rows]
    if len(ids)!=len(set(ids)): raise DomainError("ARCHIVE_DUPLICATE","归档业务键重复")
    adjudication=context.get("adjudication",{}).get("metrics",{})
    reconciled=adjudication.get("reconciled",True)
    compensation=adjudication.get("compensation_total","0.00")
    cross=adjudication.get("cross_transfers",0)
    deferred=not reconciled
    defer_reason="" if reconciled else "企业间账目未核清，日结暂缓封存"
    encoded=json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()
    return {"rows":rows,"quarantine":[],"metrics":{"records":len(rows),"source_lines":len(set(x for row in rows for x in sources(row))),"sha256":hashlib.sha256(encoded).hexdigest(),"ready":not deferred,"deferred":deferred,"defer_reason":defer_reason,"reconciled":reconciled,"cross_transfers":cross,"compensation_total":compensation,"differences":sum(r.get("status")=="差异" for r in rows)}}
