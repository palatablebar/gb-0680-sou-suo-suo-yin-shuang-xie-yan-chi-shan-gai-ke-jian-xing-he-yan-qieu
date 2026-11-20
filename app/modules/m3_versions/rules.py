from collections import defaultdict
from app.reasons import reject,sources
from app.values import number
from app.canonical import fingerprint,document_diff

def event_fingerprint(row):
    # op 是版本裁决的一部分；delete 不带 document，仅按 op 归一。
    if row["op"] == "delete":
        return fingerprint({"__op__": "delete"})
    return fingerprint({"__op__": row["op"], "document": row.get("document")})

def evaluate(rows,context):
    grouped=defaultdict(list);good=[];bad=[]
    for row in rows:grouped[(row["doc_id"],row["side"],row["version"])].append(row)
    by_doc=defaultdict(list);blocked=set();equivalent_merges=0;conflicts=0;conflict_event_rows=0
    for key,events in sorted(grouped.items()):
        # 等价正文（字段顺序/数字写法/空白差异已被规范指纹吸收）合并；
        # 真实不同（含类型改变、字段缺失）保留各自原文并隔离，不挑一个覆盖另一个。
        distinct=[]
        for event in events:
            event["_fingerprint"]=event_fingerprint(event)
            if not any(event["_fingerprint"]==seen for seen in distinct):
                distinct.append(event["_fingerprint"])
        if len(distinct)>1:
            conflicts+=1;conflict_event_rows+=len(events)
            # 以 event_id 最小的事件为锚，其余事件与锚逐一比对，差异路径入证据。
            anchor=sorted(events,key=lambda e:e["event_id"])[0]
            for event in events:
                if event["_fingerprint"]==anchor["_fingerprint"]:
                    diffs=[]
                elif event["op"]=="delete" or anchor["op"]=="delete":
                    diffs=[{"path":"$.op","kind":"OP_MISMATCH","left":anchor["op"],"right":event["op"]}]
                else:
                    diffs=document_diff(anchor.get("document"),event.get("document"))
                detail="同文档同版本内容冲突"
                if diffs:
                    detail+="："+"；".join(f"{d['path']} {d['kind']}" for d in diffs)
                bad.append(reject(event,"SAME_VERSION_CONFLICT",detail))
                bad[-1]["conflict_diff"]=diffs
                bad[-1]["conflict_evidence"]={
                    "anchor_event_id":anchor["event_id"],
                    "anchor_document":anchor.get("document"),
                    "event_document":event.get("document"),
                    "fingerprints":sorted(distinct),
                }
            blocked.add((key[0],key[1]));continue
        first=sorted(events,key=lambda e:e["event_id"])[0]
        if len(events)>1: equivalent_merges+=1
        # 合并只汇总来源行；首条原文（含 _raw 原始单元格）原样保留，等价写法的其余原文经 _sources 可回溯。
        by_doc[(key[0],key[1])].append({**first,"_sources":[n for e in events for n in sources(e)],"version_duplicate_count":len(events)-1,"_fingerprint":first["_fingerprint"],"equivalent_duplicate_events":[e["event_id"] for e in events if e is not first]})
    for (doc,side),events in sorted(by_doc.items()):
        if (doc,side) in blocked:
            bad.extend(reject(e,"UNRESOLVED_VERSION","当前文档存在版本冲突") for e in events);continue
        winner=max(events,key=lambda e:number(e["version"]))
        good.append({**winner,"_sources":[n for e in events for n in sources(e)],"superseded_versions":sorted([e["version"] for e in events if e is not winner],key=number),"tombstone":winner["op"]=="delete"})
    return {"rows":good,"quarantine":bad,"metrics":{"states":len(good),"tombstones":sum(r["tombstone"] for r in good),"conflict_rows":conflict_event_rows,"conflict_groups":conflicts,"equivalent_merges":equivalent_merges}}
