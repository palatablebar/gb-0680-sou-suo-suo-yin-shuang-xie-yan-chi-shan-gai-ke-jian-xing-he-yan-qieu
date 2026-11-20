from app.modules.m3_versions.rules import evaluate
def event(id,ver,op="upsert",document=None):return {"event_id":str(id),"doc_id":"01","side":"index","version":str(ver),"op":op,"document":document or {"a":1},"_sources":[id]}
def test_tombstone_beats_late_old_write():
    "TRAP-13"
    r=evaluate([event(1,5,"delete"),event(2,4)],{})["rows"][0];assert r["version"]=="5" and r["tombstone"] is True
def test_same_version_content_conflict():
    "TRAP-14"
    r=evaluate([event(1,5,document={"a":1}),event(2,5,document={"a":2})],{})
    assert len(r["quarantine"])==2 and r["rows"]==[]
def test_order_independent():
    rows=[event(1,4),event(2,5,"delete")];assert evaluate(rows,{})==evaluate(list(reversed(rows)),{})
def test_same_version_same_content_merged():
    r=evaluate([event(1,5),event(2,5)],{})["rows"][0];assert r["_sources"]==[1,2]
def test_real_tombstones(result): assert result["stages"][2]["metrics"]["tombstones"]==16
def test_real_same_version_conflict_rows(result): assert result["stages"][2]["metrics"]["conflict_rows"]==2
def test_large_versions_compared_exactly(): assert evaluate([event(1,"9007199254740992"),event(2,"9007199254740993")],{})["rows"][0]["version"]=="9007199254740993"

def test_conflicting_latest_not_fallback_to_old_state():
    rows=[event(1,4),event(2,5,document={"a":1}),event(3,5,document={"a":2})]
    result=evaluate(rows,{})
    assert result["rows"]==[] and len(result["quarantine"])==3

def event_full(id,ver,payload,side="index",op="upsert"):
    return {"event_id":str(id),"doc_id":"01","side":side,"version":str(ver),"op":op,
            "document":payload,"_sources":[id],"_raw":[str(id)]}

def test_equivalent_rewrites_merge_without_conflict():
    "TRAP-30 字段顺序/等价数字/空白差异不重复生差异"
    rows=[event_full(1,7,{"price":12.50,"name":" 货品 A "}),
          event_full(2,7,{"name":"货品 A","price":12.5})]
    result=evaluate(rows,{})
    assert result["quarantine"]==[] and len(result["rows"])==1
    assert result["rows"][0]["_sources"]==[1,2]
    assert result["metrics"]["equivalent_merges"]==1

def test_equivalent_merge_keeps_original_raw_and_fingerprint():
    rows=[event_full(1,7,{"a":1}),event_full(2,7,{"a":1.0})]
    winner=evaluate(rows,{})["rows"][0]
    assert winner["_raw"]==["1"] and len(winner["_fingerprint"])==64

def test_real_value_change_still_conflicts_with_diff():
    rows=[event_full(1,7,{"price":12.50}),event_full(2,7,{"price":12.60})]
    q=evaluate(rows,{})["quarantine"]
    diffs=[r for r in q if r["conflict_diff"]]
    assert len(q)==2 and diffs and diffs[0]["conflict_diff"][0]["kind"]=="VALUE_CHANGED"

def test_text_to_number_change_is_conflict_not_flattened():
    "TRAP-31 文本编号变数字必须被抓到"
    rows=[event_full(1,7,{"sku":"00123"}),event_full(2,7,{"sku":123})]
    q=evaluate(rows,{})["quarantine"]
    assert len(q)==2 and q[0]["reason"]=="SAME_VERSION_CONFLICT"
    assert any(d["kind"]=="TYPE_CHANGED" for r in q for d in r["conflict_diff"])

def test_missing_field_change_is_conflict():
    rows=[event_full(1,7,{"a":1,"b":2}),event_full(2,7,{"a":1})]
    q=evaluate(rows,{})["quarantine"]
    assert any(d["kind"]=="FIELD_MISSING" for r in q for d in r["conflict_diff"])

def test_conflict_keeps_both_original_documents():
    "TRAP-32 两端原文留存，可追回，不覆盖"
    rows=[event_full(1,7,{"v":"a"}),event_full(2,7,{"v":"b"})]
    q=evaluate(rows,{})["quarantine"]
    evidence=next(r["conflict_evidence"] for r in q if r["conflict_evidence"]["event_document"]=={"v":"b"})
    assert evidence["anchor_document"]=={"v":"a"} and evidence["event_document"]=={"v":"b"}
    assert all(r["_raw"] for r in q)

def test_equivalent_rerun_is_stable():
    rows=[event_full(1,7,{"b":2,"a":1}),event_full(2,7,{"a":1.0,"b":2.0})]
    assert evaluate(rows,{})==evaluate(rows,{})

def test_same_version_delete_vs_upsert_conflicts():
    rows=[event_full(1,7,None,op="delete"),event_full(2,7,{"a":1},op="upsert")]
    q=evaluate(rows,{})["quarantine"]
    assert len(q)==2 and any(d["kind"]=="OP_MISMATCH" for r in q for d in r["conflict_diff"])

def test_equivalent_deletes_merge():
    rows=[event_full(1,7,None,op="delete"),event_full(2,7,None,op="delete")]
    result=evaluate(rows,{})
    assert result["quarantine"]==[] and result["rows"][0]["_sources"]==[1,2]
