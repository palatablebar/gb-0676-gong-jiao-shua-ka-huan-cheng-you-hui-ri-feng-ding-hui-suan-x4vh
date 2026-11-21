from decimal import Decimal
from app.values import number,instant,money
from app.errors import DomainError
from app.reasons import reject,sources
ENTERPRISES=("甲企业","乙企业")
ATTRIBUTIONS={
    "01":[{"start":"2026-01-01T00:00:00+08:00","end":"2027-01-01T00:00:00+08:00","enterprise":"甲企业","version":"OP-01-A"}],
    "02":[{"start":"2026-01-01T00:00:00+08:00","end":"2027-01-01T00:00:00+08:00","enterprise":"乙企业","version":"OP-02-A"}],
    "03":[{"start":"2026-01-01T00:00:00+08:00","end":"2027-01-01T00:00:00+08:00","enterprise":"乙企业","version":"OP-03-A"}],
}
RULING_ID="裁字2026-11"
RULING_TEXT="跨企业换乘优惠由产生资格的前序企业承担：前序有效付费行程在换乘窗内产生优惠资格，资格产生方为该笔换乘唯一责任企业；接乘企业后程减收由前序企业按笔等额补偿，补偿金额等于后程实际优惠额。"
RULING_REASONS=[
    "资格因果：换乘优惠资格由前序有效付费行程在异线时间窗内产生，无前程则后程不会少扣，政策成本应归于资格产生方。",
    "联营公平：接乘企业履行联营换乘政策不应单方减收；前序企业已全额收取首程票款并获得联营接驳客流。",
    "风险受控：后程减收与前序补偿分账的固有风险，由每笔唯一责任企业、补偿台账批次幂等、核清前暂缓封存三项控制闭合。",
]
def select_attribution(route,at,table):
    hits=[v for v in table.get(route,[]) if instant(v["start"])<=at<instant(v["end"])]
    if len(hits)>1: raise DomainError("ATTRIBUTION_CONFLICT","运营归属版本生效窗重叠")
    return hits[0] if hits else None
def apply_switches(table,switches,enterprises):
    """校验并应用运营归属切换。任一条失败则整批不生效，保留旧版。"""
    if not isinstance(switches,list) or any(not isinstance(s,dict) for s in switches): raise DomainError("BAD_SWITCH","归属切换需要对象列表")
    errors=[];plan=[]
    for index,switch in enumerate(switches):
        route=str(switch.get("route",""));enterprise=str(switch.get("enterprise",""))
        try: start=instant(switch.get("start"))
        except DomainError:
            errors.append(f"第{index+1}条：切换生效时间无效");continue
        if route not in table: errors.append(f"第{index+1}条：线路{route}未登记");continue
        if enterprise not in enterprises: errors.append(f"第{index+1}条：企业{enterprise}未登记");continue
        covering=[v for v in table[route] if instant(v["start"])<=start<instant(v["end"])]
        if not covering: errors.append(f"第{index+1}条：{start.isoformat()}不在线路{route}任何归属版本生效窗内");continue
        current=covering[0]
        if current["enterprise"]==enterprise: errors.append(f"第{index+1}条：线路{route}在该时刻已归属{enterprise}，切换无效");continue
        plan.append((route,current,start,enterprise,str(switch.get("version","")) or f"{current['version']}-SW{index+1}"))
    if errors: return table,errors
    updated={route:list(versions) for route,versions in table.items()}
    for route,current,start,enterprise,label in plan:
        versions=updated[route];position=versions.index(current)
        remainder={**current,"start":start.isoformat(),"enterprise":enterprise,"version":label}
        head={**current,"end":start.isoformat()}
        versions[position:position+1]=([head] if instant(head["start"])<instant(head["end"]) else [])+[remainder]
    return updated,[]
def evaluate(rows,context):
    params=context.get("parameters",{})
    enterprises=tuple(params.get("enterprises",ENTERPRISES))
    table={route:list(versions) for route,versions in ATTRIBUTIONS.items()}
    bad=[];switch_applied=switch_failed=0
    switches=params.get("attribution_switch",[])
    if switches:
        table,errors=apply_switches(table,switches,enterprises)
        if errors:
            switch_failed=len(switches)
            for detail in errors: bad.append({"_line":"—","_sources":[],"reason":"SWITCH_REJECTED","detail":f"归属切换失败，保留旧版：{detail}"})
        else: switch_applied=len(switches)
    good=[];missing=0
    for row in rows:
        version=select_attribution(row["route"],instant(row["at"]),table)
        if version is None:
            missing+=1;bad.append(reject(row,"NO_ATTRIBUTION","该时刻线路无运营归属，保留原始刷卡待补登记"));continue
        good.append({**row,"enterprise":version["enterprise"],"attrib_version":version["version"],"transfer_role":"—","pair_event":"—","compensation":"0.00","responsible_enterprise":"—"})
    by_id={row["event_id"]:row for row in good}
    transfers=[];ledger={};reduce_totals={enterprise:Decimal(0) for enterprise in enterprises}
    payable={enterprise:Decimal(0) for enterprise in enterprises};receivable={enterprise:Decimal(0) for enterprise in enterprises}
    for row in good:
        anchor_id=row.get("transfer_anchor","—")
        if anchor_id=="—": continue
        anchor=by_id.get(anchor_id)
        if anchor is None:
            bad.append(reject(row,"ANCHOR_MISSING","换乘锚点行程缺失，原始刷卡保留待查"));continue
        discount=number(row["transfer_discount"]);cross=anchor["enterprise"]!=row["enterprise"]
        anchor["transfer_role"]="前程" if anchor["transfer_role"]=="—" else anchor["transfer_role"]+"·前程"
        row["transfer_role"]="后程" if row["transfer_role"]=="—" else row["transfer_role"]+"·后程"
        row["pair_event"]=anchor["event_id"] if row["pair_event"]=="—" else row["pair_event"]+"·"+anchor["event_id"]
        anchor["pair_event"]=row["event_id"] if anchor["pair_event"]=="—" else anchor["pair_event"]+"·"+row["event_id"]
        responsible=anchor["enterprise"] if cross else row["enterprise"]
        compensation=discount if cross else Decimal(0)
        row["responsible_enterprise"]=responsible
        row["compensation"]=money(compensation)
        basis=(f"{RULING_ID}：资格锚点{anchor['event_id']}（{anchor['enterprise']}·{anchor['route']}路，{anchor['attrib_version']}）在换乘窗内产生资格；"
               f"后程{row['event_id']}（{row['enterprise']}·{row['route']}路，{row['attrib_version']}）实际少收{money(discount)}元；"
               f"责任企业={responsible}，补偿{money(compensation)}元至{row['enterprise']}" if cross else
               f"同企业（{row['enterprise']}）账内换乘，减收与优惠同账闭合，无跨企业补偿")
        transfers.append({"transfer_key":row["event_id"],"business_day":row["business_day"],"cross_enterprise":cross,
            "prior_event":anchor["event_id"],"prior_route":anchor["route"],"prior_enterprise":anchor["enterprise"],"prior_at":anchor["at"],"prior_paid":anchor["expected"],"prior_version":anchor["attrib_version"],
            "next_event":row["event_id"],"next_route":row["route"],"next_enterprise":row["enterprise"],"next_at":row["at"],"base_fare":row["base_fare"],"discount":money(discount),"next_version":row["attrib_version"],
            "responsible":responsible,"compensation":money(compensation),"booked":row["enterprise"],"difference":money(compensation),"basis":basis,
            "_sources":list(sources(anchor))+list(sources(row))})
        reduce_totals[row["enterprise"]]=reduce_totals.get(row["enterprise"],Decimal(0))+discount
        if cross and compensation>0:
            ledger[row["event_id"]]={"transfer_key":row["event_id"],"business_day":row["business_day"],"payer":anchor["enterprise"],"payee":row["enterprise"],
                "amount":money(compensation),"basis":basis,"_sources":list(sources(anchor))+list(sources(row))}
            payable[anchor["enterprise"]]=payable.get(anchor["enterprise"],Decimal(0))+compensation
            receivable[row["enterprise"]]=receivable.get(row["enterprise"],Decimal(0))+compensation
    payable_total=sum(payable.values(),Decimal(0));receivable_total=sum(receivable.values(),Decimal(0))
    cross_reduce=sum((number(t["discount"]) for t in transfers if t["cross_enterprise"]),Decimal(0))
    balanced=payable_total==receivable_total==cross_reduce
    reconciled=balanced and switch_failed==0 and missing==0 and not any(b["reason"]=="ANCHOR_MISSING" for b in bad)
    summary=[{"enterprise":enterprise,"reduce_total":money(reduce_totals.get(enterprise,Decimal(0))),"payable":money(payable.get(enterprise,Decimal(0))),
        "receivable":money(receivable.get(enterprise,Decimal(0))),"net":money(receivable.get(enterprise,Decimal(0))-payable.get(enterprise,Decimal(0)))} for enterprise in enterprises]
    attribution_diff=[{"enterprise":enterprise,"current":money(-reduce_totals.get(enterprise,Decimal(0))),
        "adjudicated":money(-(reduce_totals.get(enterprise,Decimal(0))-receivable.get(enterprise,Decimal(0))+payable.get(enterprise,Decimal(0)))),
        "difference":money(receivable.get(enterprise,Decimal(0))-payable.get(enterprise,Decimal(0)))} for enterprise in enterprises]
    metrics={"transfers":len(transfers),"cross_transfers":sum(1 for t in transfers if t["cross_enterprise"]),
        "compensation_total":money(payable_total),"reduce_total":money(sum(reduce_totals.values(),Decimal(0))),
        "ledger_entries":len(ledger),"reconciled":reconciled,"balanced":balanced,
        "switch_applied":switch_applied,"switch_failed":switch_failed,"attribution_missing":missing,"enterprises":len(enterprises)}
    return {"rows":good,"quarantine":bad,"transfers":transfers,"ledger":list(ledger.values()),"enterprise_summary":summary,
        "attribution_diff":attribution_diff,"ruling":{"id":RULING_ID,"text":RULING_TEXT,"reasons":RULING_REASONS},"metrics":metrics}
