from collections import defaultdict
from app.reasons import sources
from app.values import number
from app.canonical import equivalent,document_diff,fingerprint

def evaluate(rows,context):
    grouped=defaultdict(dict)
    for row in rows:grouped[row["doc_id"]][row["side"]]=row
    out=[]
    for doc,sides in sorted(grouped.items()):
        source=sides.get("source");target=sides.get("index");lines=[n for r in sides.values() for n in sources(r)]
        content_diff=[]
        if source is None:state="ORPHAN_INDEX"
        elif target is None:state="MISSING_INDEX" if source["op"]=="upsert" else "DELETE_NOT_CONFIRMED"
        elif number(target["version"])>number(source["version"]):state="INDEX_AHEAD"
        elif number(target["version"])<number(source["version"]):state="STALE_INDEX"
        elif source["op"]!=target["op"]:state="OP_MISMATCH"
        elif source["op"]=="upsert":
            # 同一业务版本裁决：吸收字段顺序/等价数字/空白，真实变化（类型、缺字段、值）照报。
            if equivalent(source.get("document"),target.get("document")):
                state="CONSISTENT"
            else:
                state="CONTENT_MISMATCH"
                content_diff=document_diff(source.get("document"),target.get("document"))
        else:state="CONSISTENT"
        anchor=source or target
        out.append({**anchor,"_sources":lines,
            # 双端原文全部留存，归档凭据可追回，不被任一规范结果覆盖。
            "source_document":source.get("document") if source else None,
            "index_document":target.get("document") if target else None,
            "source_fingerprint":fingerprint(source.get("document")) if source and source.get("document") is not None else None,
            "index_fingerprint":fingerprint(target.get("document")) if target and target.get("document") is not None else None,
            "content_diff":content_diff,
            "source_version":source["version"] if source else "—","index_version":target["version"] if target else "—","source_op":source["op"] if source else "—","index_op":target["op"] if target else "—","visible_at":target.get("visible_at") if target else None,"visibility_state":state,"expected":"1","reported":"1" if state=="CONSISTENT" else "0","document_equal":state=="CONSISTENT"})
    return {"rows":out,"quarantine":[],"metrics":{"documents":len(out),"consistent":sum(r["visibility_state"]=="CONSISTENT" for r in out),"missing":sum(r["visibility_state"] in {"MISSING_INDEX","DELETE_NOT_CONFIRMED"} for r in out),"content_mismatches":sum(r["visibility_state"]=="CONTENT_MISMATCH" for r in out)}}
