import csv,io,json
from app.pipeline import execute,load_sample
from app import store
def test_full_sample_flow(client):
    r=client.post("/api/runs",json={"sample":"dirty.csv"});assert r.status_code==200
    p=r.get_json();assert len(p["stages"])==7
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

def test_archive_evidence_keeps_raw_documents_and_verdict(client):
    "TRAP-32 归档凭据携带双端原文、指纹与差异，原样可追回"
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    data=client.get("/api/runs/"+p["run_id"]+"/archive").data.decode("utf-8-sig")
    rows=list(csv.reader(io.StringIO(data)))
    accepted=[json.loads(r[6]) for r in rows[1:] if r[3]=="accepted"]
    assert all("source_document" in r and "index_document" in r for r in accepted)
    assert all("source_fingerprint" in r and "content_diff" in r for r in accepted)
    quarantined=[json.loads(r[6]) for r in rows[1:] if r[3]=="quarantine"]
    conflicts=[r for r in quarantined if r.get("reason")=="SAME_VERSION_CONFLICT"]
    assert conflicts and all("conflict_evidence" in r for r in conflicts)

def test_equivalent_payload_does_not_raise_conflict(client):
    "TRAP-30 等价写法经真实导入路径不产生版本冲突/内容差异"
    header=",".join(["event_id","doc_id","version","op","source_time","visible_time","side","payload","reported","note"])+"\n"
    csv_text=header+'1,D1,7,upsert,2026-11-16T10:00:00Z,-,index,"{""price"": 12.50, ""name"": "" 货品 ""}",1,x\n'
    run=client.post("/api/runs",json={"csv":csv_text}).get_json()
    assert run["stages"][2]["metrics"]["conflict_rows"]==0
    m3_row=run["stages"][2]["rows"][0]
    assert len(m3_row["_fingerprint"])==64

def test_same_input_rerun_is_same_batch(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    q=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    assert p["run_id"]==q["run_id"] and len(store.history())==1
