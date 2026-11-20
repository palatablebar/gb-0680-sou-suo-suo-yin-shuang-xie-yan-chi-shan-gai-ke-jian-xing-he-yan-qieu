from app.modules.m4_visibility.rules import evaluate
def state(side,version="5",op="delete",doc="01",document=None):return {"doc_id":doc,"side":side,"version":version,"op":op,"document":document,"source_at":"2026-11-16T10:00:00Z","visible_at":"2026-11-16T10:00:30Z","_sources":[1 if side=="source" else 2]}
def test_real_consistent_deleted_docs(result): assert result["stages"][3]["metrics"]["consistent"]==9
def test_missing_separate(): assert evaluate([state("source",op="upsert")],{})["rows"][0]["visibility_state"]=="MISSING_INDEX"
def test_delete_without_tombstone_confirmation(): assert evaluate([state("source")],{})["rows"][0]["visibility_state"]=="DELETE_NOT_CONFIRMED"
def test_stale_target(): assert evaluate([state("source"),state("index","4","upsert")],{})["rows"][0]["visibility_state"]=="STALE_INDEX"
def test_same_version_content_mismatch(): assert evaluate([state("source",op="upsert",document={"a":1}),state("index",op="upsert",document={"a":2})],{})["rows"][0]["visibility_state"]=="CONTENT_MISMATCH"
def test_orphan_target(): assert evaluate([state("index")],{})["rows"][0]["visibility_state"]=="ORPHAN_INDEX"
def test_real_deleted_op_not_resurrected(result): assert result["stages"][3]["rows"][0]["index_op"]=="delete"

def _pair(source_doc,index_doc):
    return evaluate([state("source",op="upsert",document=source_doc),
                     state("index",op="upsert",document=index_doc)],{})["rows"][0]

def test_equivalent_rewrite_is_consistent():
    "TRAP-30 等价写法不产生内容差异"
    row=_pair({"price":12.50,"name":" 货品 "},{"name":"货品","price":12.5})
    assert row["visibility_state"]=="CONSISTENT" and row["document_equal"] is True
    assert row["content_diff"]==[]
    assert row["source_fingerprint"]==row["index_fingerprint"]

def test_real_change_is_content_mismatch_with_diff():
    row=_pair({"price":12.50},{"price":12.60})
    assert row["visibility_state"]=="CONTENT_MISMATCH" and row["document_equal"] is False
    assert row["content_diff"][0]["path"]=="$.price" and row["content_diff"][0]["kind"]=="VALUE_CHANGED"

def test_type_change_caught_in_visibility():
    "TRAP-31 正文类型改变不放过"
    row=_pair({"sku":"00123"},{"sku":123})
    assert row["visibility_state"]=="CONTENT_MISMATCH"
    assert row["content_diff"][0]["kind"]=="TYPE_CHANGED"

def test_both_raw_documents_retained():
    "TRAP-32 双端原文与指纹随可见性结论留存"
    row=_pair({"v":"a"},{"v":"b"})
    assert row["source_document"]=={"v":"a"} and row["index_document"]=={"v":"b"}
    assert len(row["source_fingerprint"])==64 and row["source_fingerprint"]!=row["index_fingerprint"]
    assert set(row["_sources"])=={1,2}
