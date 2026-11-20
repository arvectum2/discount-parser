"""Pinned source review; structural only, not product acceptance or task admission."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
DIR="specs/001-contained-product-traceability"
PIN="34217cbce3bbc8db3b10d115baae5142083de88a"
PRIOR="f4ac121b43f8a20f5a2ce885e6326ee54758e95f"
MODE="contained"
SOURCES=json.loads("[{\"path\":\"docs/ROADMAP.md\",\"sha256\":\"4d7c80ce5aba35488e8f5cfb1221eada7b9190a576e42d255307e0bff23a5bdc\"},{\"path\":\"docs/HARDENING_ROADMAP_2026-08-17.md\",\"sha256\":\"c9039ff39eebe4960b35370286cea9fc0b094f137d2e5c809179327c680c9dc7\"},{\"path\":\"docs/FINAL_ACCEPTANCE_CHECKLIST.md\",\"sha256\":\"e02d65ab36622e1523263f6c71d901992b5bd062f6d408c4cc59a7a7b0509ac7\"},{\"path\":\"docs/TECHNICAL_SPEC_V1.md\",\"sha256\":\"beba950871e26ea753c7222a749a38efacc55b72ce676131f13ff9927dc3bbe8\"}]")
GATES=json.loads("[{\"id\":\"REVIEW-01\",\"source\":\"docs/ROADMAP.md\",\"first_line\":35,\"last_line\":494,\"label\":\"MVP R0–R9\",\"rule\":\"Review source gates without restarting held product.\"},{\"id\":\"REVIEW-02\",\"source\":\"docs/HARDENING_ROADMAP_2026-08-17.md\",\"first_line\":16,\"last_line\":105,\"label\":\"Operational hardening\",\"rule\":\"Separate recorded lab/physical Windows evidence from current customer use.\"},{\"id\":\"REVIEW-03\",\"source\":\"docs/FINAL_ACCEPTANCE_CHECKLIST.md\",\"first_line\":5,\"last_line\":197,\"label\":\"Final acceptance\",\"rule\":\"Preserve all original checklist criteria; no customer acceptance inferred.\"}]")
def scan(raw):
    out=[];heading=0;fence=False
    for i,l in enumerate(raw.decode("utf-8").splitlines(),1):
        if not l.strip():continue
        if l.lstrip().startswith(("\x60\x60\x60","~~~")):
            fence=not fence;kind="format"
        elif fence:kind="code"
        elif re.match(r"^#{1,6}\s",l):heading=i;kind="heading"
        elif re.fullmatch(r"\s*\|?\s*[:\-]+(?:\s*\|\s*[:\-]+)+\s*\|?\s*",l) or re.fullmatch(r"\s*[-*_]{3,}\s*",l):kind="format"
        elif re.match(r"^\s*\|",l):kind="table"
        elif re.match(r"^\s*(?:[-*+]|\d+[.)])\s+",l):kind="list"
        else:kind="prose"
        out.append([i,heading,kind])
    return out
def validate(data,original,prior,current):
    errors=[]
    if data.get("schema")!="arvectum.source-section-review/1" or data.get("source_commit")!=PIN or data.get("review_baseline")!=PRIOR or data.get("mode")!=MODE or data.get("actual_acceptance_verified") is not False or data.get("execution_authorized") is not False:errors.append("scope/authority")
    if data.get("gates") is None: return errors+["missing gates"]
    src=data.get("sources",[]);paths=[s["path"] for s in src]
    if paths!=[s["path"] for s in SOURCES]:return errors+["source coverage"]
    for a,s in zip(src,SOURCES):
        p=s["path"];b=original[p]
        if hashlib.sha256(b).hexdigest()!=s["sha256"] or a.get("sha256")!=s["sha256"]:errors.append("source hash "+p)
        if not prior[p].startswith(b) or prior[p]!=current[p]:errors.append("unreviewed source change "+p)
        if a.get("rows")!=scan(b):errors.append("line/heading coverage "+p)
    rows=data["gates"]
    if len(rows)!=len(GATES):errors.append("gate coverage")
    for row,g in zip(rows,GATES):
        if any(row.get(k)!=v for k,v in g.items()):errors.append("gate identity/scope")
        if row.get("review_state") not in {"unverified","verified"}:errors.append("state")
        if row.get("review_state")=="verified":
            ev=row.get("evidence",[])
            if not ev or any(e.get("criterion")!=row["id"] or e.get("outcome")!="pass" or not re.fullmatch(r"[a-f0-9]{64}",e.get("artifact_sha256","")) or not e.get("receipt_ref") or not e.get("review_ref") for e in ev):errors.append("missing criterion-specific evidence "+row["id"])
    return errors
def inputs():
    def read(ref,p):return subprocess.check_output(["git","-C",str(ROOT),"show",ref+":"+p])
    original={s["path"]:read(PIN,s["path"]) for s in SOURCES}
    prior={p:read(PRIOR,p) for p in original}
    current={p:(ROOT/p).read_bytes() for p in original}
    return json.loads((ROOT/DIR/"section-review.json").read_text()),original,prior,current
if __name__=="__main__":
    errors=validate(*inputs())
    if errors:raise SystemExit("\n".join(errors))
    print("Structural source/section coverage PASS; no actual acceptance or authority.")
