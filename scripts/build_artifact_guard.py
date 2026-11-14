#!/usr/bin/env python3
"""Plan/apply selective cleanup of inactive Next.js build artifacts.

Historical shutdown logs are not invented or required by this separate policy.
Retained source, real build metadata, current runtime bindings, bounded reference
review and stable exact members are mandatory. Shared/protected files stay in
place. No npm, project script, install, build, process kill or DB access occurs.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import urllib.request


def sibling(filename):
    path = Path(__file__).absolute().with_name(filename)
    for parent in (path, *path.parents):
        if os.path.islink(parent) or getattr(os.lstat(parent), "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Linked guard code refused")
    spec = importlib.util.spec_from_file_location("_build_task_helpers", path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


A = sibling("agent_artifact_guard.py")
g, t, r = A.g, A.t, A.r
VERSION = "1.6.0"
POLICY = "inactive-next-build-selective-v1"
ASSESSMENT = "inactive-next-build-review-v1"
CLAIMS = ".storage-build-claims"
PRIVATE = g.PRUNE | {"state", "index", "indexes", "indices", "data", "pgdata"}
FORBIDDEN_ANCESTORS = PRIVATE | g.MANAGED_DIRS | {
    "releases", "release", "rollback", "prepared", "recovery", "backups", "backup",
    "assets", "media", "public", "static", "deliverables", "acceptance", "baselines", "golden"}
ROOT_MANIFESTS = {"BUILD_ID", "required-server-files.json", "package.json",
    "build-manifest.json", "app-build-manifest.json", "routes-manifest.json",
    "prerender-manifest.json", "react-loadable-manifest.json",
    "export-marker.json", "images-manifest.json", "next-minimal-server.js.nft.json",
    "next-server.js.nft.json", "trace"}
GENERATED_CODE = {".js", ".css", ".map", ".mjs", ".cjs"}
NEXT = re.compile(r"(?:next[/\\]dist[/\\](?:bin[/\\]next|server)|next-server|(?:^|\s)next\s+(?:start|dev))", re.I)
RUNTIME = re.compile(r"(?:node|python|pythonw|java|dotnet|chrome|chromium|msedge|codex|claude|kimi|workbuddy|codebuddy|pwsh|powershell|cmd|bun|deno|bash|zsh|sh)(?:[0-9.]*)(?:\.exe)?$", re.I)


def admin(value, root=None, output=False):
    path = t.administrative_path(value)
    if root is not None and g.below(path, root):
        raise g.GuardError("Administrative records must be outside the project")
    return g.safe_output(path) if output else path


def rel_path(root, relative, directory=False):
    r.relative(relative)
    path = root.joinpath(*relative.split("/"))
    g.protect_agent_state_path(path)
    g.ancestors(path.parent); g.plain(path, directory)
    return path


def source_path(root, relative):
    r.relative(relative)
    parts = relative.split("/")
    if (len(parts)<3 or parts[-1]!=".next"
            or parts[0] not in {".tmp","task-runs","task_runs","candidates",".candidates","task-artifacts"}
            or any(x.lower() in FORBIDDEN_ANCESTORS for x in parts[:-1])):
        raise g.GuardError("Only an exact ordinary Next .next root outside protected/managed boundaries is supported")
    source = rel_path(root, relative, True)
    if source.parent == root:
        raise g.GuardError("Select an isolated app/candidate, not a project-root build")
    return source


def classification(relative, s):
    """File-level retention. One shared file never protects unrelated files."""
    parts = relative.split("/"); name = parts[-1]
    if (any(x.lower() in PRIVATE for x in parts) or r.credential(relative)
            or name.startswith(".env") or Path(name).suffix.lower() in {".db",".sqlite",".sqlite3",".jsonl",".pem",".key",".bak"}):
        return "protected_state_or_data"
    if not stat.S_ISREG(s.st_mode) or getattr(s,"st_file_attributes",0)&0x400:
        return "protected_nonordinary"
    if s.st_nlink>1: return "protected_shared_identity"
    if not s.st_ino or s.st_nlink!=1: return "protected_unknown_identity"
    if getattr(s,"st_file_attributes",0)&(1|0x200|0x800|0x1000|0x4000|0x40000|0x400000):
        return "protected_file_attributes"
    if name in ROOT_MANIFESTS and len(parts)==1:
        return "retained_build_identity_or_manifest"
    # Next separates dev outputs from production outputs under .next/dev.
    # This is the same app-scoped generated layout, never a second project.
    # State/data and individual file protection above apply before this route.
    layout=parts[1:] if parts[0]=="dev" else parts
    # Compiled code only; original media, prerendered content and data stay.
    if layout and layout[0] in {"server","static"} and Path(name).suffix.lower() in GENERATED_CODE:
        return "generated_compiled_code"
    if (len(layout)>=3 and layout[:2]==["cache","webpack"]
            and re.fullmatch(r"(?:index|[0-9]+)\.pack(?:\.gz)?(?:\.old)?",name)):
        return "generated_webpack_cache"
    return "protected_unrecognized_or_unique_output"


def snapshot(source, max_files, budget=None):
    directories, files, selected, retained = {}, {}, {}, {}
    stack = [(source,"")]; count=0
    while stack:
        folder, rel = stack.pop()
        g.ancestors(folder)
        fs=g.plain(folder,True)
        if not fs.st_ino: raise g.GuardError("Unknown directory identity")
        directories[rel]={"fingerprint":g.fingerprint(fs)}
        if rel and any(x.lower() in PRIVATE for x in rel.split("/")):
            retained[rel+"/"]={"reason":"protected_subtree_not_entered","fingerprint":g.fingerprint(fs)}
            continue
        with os.scandir(folder) as entries:
            for entry in entries:
                count+=1
                if count>max_files: raise g.GuardError("Exact build unit exceeds its member budget; select another bounded unit")
                path=Path(entry.path); relative=rel+"/"+entry.name if rel else entry.name
                r.relative(relative)
                s=os.lstat(path)
                if getattr(s,"st_file_attributes",0)&0x400 or stat.S_ISLNK(s.st_mode):
                    retained[relative]={"reason":"protected_link_not_followed","fingerprint":g.fingerprint(s)}
                    continue
                if stat.S_ISDIR(s.st_mode):
                    stack.append((path,relative)); continue
                role=classification(relative,s)
                rec={"fingerprint":g.fingerprint(s),"reason":role}
                files[relative]=rec
                if role.startswith("generated_"):
                    try:
                        guarded=t.record(path)
                        # Probe release access without invoking the unlink callback.
                        # Failure retains this file; it never relaxes permissions.
                        with g.guarded_file(path,delete=True) as (fd,_):
                            if g.fingerprint(os.fstat(fd))!=guarded["fingerprint"]:
                                raise g.GuardError("File changed during release-access probe")
                    except (OSError,g.GuardError) as exc:
                        if g.fatal_io(exc): raise
                        rec["reason"]="protected_unverifiable_metadata"
                        retained[relative]=rec; continue
                    rec.update(guarded)
                    rec["allocated_bytes"]=g.allocated(path,s)
                    if budget is not None:
                        rec["sha256"]=t.file_hash(path,{k:v for k,v in rec.items() if k not in {"reason","allocated_bytes"}},budget)
                    selected[relative]=rec
                else:
                    retained[relative]=rec
    return {"directories":directories,"files":files,"selected":selected,"retained":retained}


def same_snapshot(actual,expected,hashes=False):
    def normalize(value):
        result=json.loads(json.dumps(value))
        for group in ("files","selected"):
            for item in result[group].values():
                if not hashes: item.pop("sha256",None)
        return result
    if normalize(actual)!=normalize(expected):
        raise g.GuardError("Build membership/identity/metadata/shared-file protection changed")


def read_evidence(path,budget,maximum=4*1024**2):
    if g.plain(path,False).st_size>maximum:
        raise g.GuardError("Evidence exceeds bounded read")
    rec=t.record(path)
    with g.guarded_file(path) as (fd,_):
        if g.fingerprint(os.fstat(fd))!=rec["fingerprint"]:
            raise g.GuardError("Evidence changed before read")
        chunks=[]; length=0
        while True:
            data=os.read(fd,min(1024*1024,maximum+1-length))
            if not data: break
            budget.add(len(data)); length+=len(data); chunks.append(data)
            if length>maximum: raise g.GuardError("Evidence grew beyond read limit")
        raw=b"".join(chunks)
        if t.record(path)!=rec: raise g.GuardError("Evidence changed while read")
    return raw,{**rec,"sha256":hashlib.sha256(raw).hexdigest()}


def evidence(root,spec,budget,source=None):
    if not isinstance(spec,dict) or not isinstance(spec.get("path"),str):
        raise g.GuardError("Missing exact retained evidence path")
    rel=spec["path"]
    if r.credential(rel) or any(x.lower() in PRIVATE for x in rel.split("/")):
        raise g.GuardError("State/credentials/data cannot be evidence")
    path=rel_path(root,rel)
    if source is not None and g.below(path,source):
        raise g.GuardError("Retained source/result evidence must be outside build")
    raw,rec=read_evidence(path,budget)
    if spec.get("sha256")!=rec["sha256"]:
        raise g.GuardError("Retained evidence hash changed")
    return rel,raw,rec


def assess(root,source,path,budget):
    if g.plain(path,False).st_size>1024**2:
        raise g.GuardError("Assessment exceeds 1 MiB")
    value,sha=g.read_json(path)
    if value.get("schema")!=ASSESSMENT or value.get("source")!=source.relative_to(root).as_posix():
        raise g.GuardError("Assessment scope/schema mismatch")
    if value.get("lifecycle_mode")!="current-state-reconstruction":
        raise g.GuardError("This policy requires an honest current-state review, not invented historical completion")
    review=value.get("review")
    if not isinstance(review,dict): raise g.GuardError("Substantive review required")
    for key in ("reviewer","origin","inactive_reason","retained_source_and_results","not_rollback_or_deployment","reference_scope","rebuild_impact"):
        t.text(review.get(key),key)
    producer=value.get("producer",{})
    rel,raw,rec=evidence(root,producer,budget,source)
    if root/rel != source.parent/"package.json":
        raise g.GuardError("Producer must be the adjacent app package.json")
    manifest=json.loads(raw.decode("utf-8-sig"))
    command=manifest.get("scripts",{}).get("build","")
    if not isinstance(command,str) or not re.fullmatch(r"next build(?: --(?:webpack|turbopack|no-lint|no-mangling))*",command):
        raise g.GuardError("Unsupported/custom build recipe; no project command is executed")
    dependencies={**manifest.get("devDependencies",{}),**manifest.get("dependencies",{})}
    if not isinstance(dependencies.get("next"),str) or not dependencies["next"]:
        raise g.GuardError("Adjacent manifest does not identify Next")
    records={rel:rec}; retained=[]
    for item in value.get("retained_evidence",[]):
        name,_,record=evidence(root,item,budget,source)
        if name in records: raise g.GuardError("Distinct retained source/result evidence required")
        records[name]=record; retained.append(name)
    if not retained: raise g.GuardError("Retain independent source/result evidence outside build")
    refs=[]
    for item in value.get("reference_files",[]):
        name,_,record=evidence(root,item,budget,source)
        if Path(name).suffix.lower() not in t.CODE|{".json",".md"}:
            raise g.GuardError("Reference review must use explicit safe code/configuration")
        records[name]=record; refs.append(name)
    if not refs: raise g.GuardError("Explicit current launch/configuration reference inputs are required")
    keepers={}
    for relative in value.get("retained_app_roots",[]):
        r.relative(relative)
        if any(x.lower() in PRIVATE for x in relative.split("/")):
            raise g.GuardError("State is not an application keeper")
        app=rel_path(root,relative,True)
        if g.below(source,app) or g.below(app,source):
            raise g.GuardError("Build overlaps a retained current/rollback app")
        keepers[relative]=g.root_identity(app)
    if not keepers: raise g.GuardError("Retain at least one explicitly identified current/rollback app")
    if len(records)>24: raise g.GuardError("Too many retained guards")
    build_id_path=source/"BUILD_ID"
    raw_id,id_record=read_evidence(build_id_path,budget,256)
    build_id=raw_id.decode("ascii").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}",build_id):
        raise g.GuardError("Missing genuine Next build identity; unfinished builds need a different policy")
    records[build_id_path.relative_to(root).as_posix()]=id_record
    return {"assessment_sha256":sha,"assessment_record":t.record(path),"evidence":records,
        "review":review,"producer":rel,"retained_evidence":retained,"reference_files":refs,"retained_app_roots":keepers,
        "build_id":build_id,"build_command_observed_not_executed":command,
        "lifecycle_mode":"current-state-reconstruction",
        "historical_completion_log_required":False,
        "limitation":"Semantic ownership/retirement is reviewed by the Agent; static metadata cannot prove every possible consumer."}


def process_inventory():
    if os.name=="nt":
        system=t.system_directory(); ps=system/"WindowsPowerShell/v1.0/powershell.exe"
        modules=ps.parent/"Modules"
        utility=str(modules/"Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1").replace("'","''")
        cim=str(modules/"CimCmdlets/CimCmdlets.psd1").replace("'","''")
        result=t._run([str(ps),"-NoProfile","-NonInteractive","-Command",
            "$ErrorActionPreference='Stop'; $PSModuleAutoLoadingPreference='None'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
            f"Import-Module '{utility}'; Import-Module '{cim}'; "
            "CimCmdlets\\Get-CimInstance Win32_Process | Microsoft.PowerShell.Utility\\Select-Object ProcessId,ParentProcessId,Name,CommandLine,CreationDate | Microsoft.PowerShell.Utility\\ConvertTo-Json -Compress"])
        if result.returncode or result.stderr.strip(): raise g.GuardError("Windows activity inventory incomplete")
        values=json.loads(result.stdout); values=[values] if isinstance(values,dict) else values
        return [{"pid":int(x["ProcessId"]),"ppid":int(x["ParentProcessId"]),"name":x["Name"],
                 "args":x.get("CommandLine"),"stamp":str(x.get("CreationDate"))} for x in values]
    if sys.platform=="darwin":
        result=t._run(["/bin/ps","-axo","pid=,ppid=,lstart=,args="])
        if result.returncode or result.stderr.strip(): raise g.GuardError("macOS activity inventory incomplete")
        values=[]
        for line in result.stdout.splitlines():
            fields=line.strip().split(None,7)
            if len(fields)!=8: raise g.GuardError("Incomplete native process record")
            values.append({"pid":int(fields[0]),"ppid":int(fields[1]),"name":fields[7].split()[0],
                           "args":fields[7],"stamp":" ".join(fields[2:7])})
        return values
    raise g.GuardError("Native build cleanup currently supports Windows/macOS")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def binding_proof(binding,process,budget):
    if binding.get("process_stamp")!=process["stamp"]:
        raise g.GuardError("Runtime PID identity changed; binding cannot be reused")
    app=g.protect_agent_state_path(binding.get("app","")); g.ancestors(app)
    if any(p.lower() in PRIVATE for p in app.parts): raise g.GuardError("Private runtime binding")
    raw,rec=read_evidence(app/".next/BUILD_ID",budget,256)
    identifier=raw.decode("ascii").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}",identifier):
        raise g.GuardError("Runtime build ID invalid")
    manifest=app/".next/static"/identifier/"_buildManifest.js"
    content,mrec=read_evidence(manifest,budget,1024**2)
    # A literal loopback URL and observed native CLI port, never supplied hosts.
    match=re.search(r"(?:--port(?:=|\s+)|(?:^|\s)-p\s+)([0-9]{1,5})(?:\s|$)",str(process["args"]))
    if not match: raise g.GuardError("Runtime port not resolved; preserve unknown preview")
    port=int(match[1])
    if not 1<=port<=65535: raise g.GuardError("Invalid runtime port")
    url=f"http://127.0.0.1:{port}/_next/static/{identifier}/_buildManifest.js"
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(url,timeout=3) as response:
        if response.status!=200: raise g.GuardError("Runtime build static proof unavailable")
        actual=response.read(1024**2+1)
    if actual!=content: raise g.GuardError("Runtime build does not match retained app; preserve")
    return {"pid":process["pid"],"process_stamp":process["stamp"],"app":str(app),"port":port,
        "build_id":identifier,"build_id_record":rec,"manifest_record":mrec,
        "native_command_sha256":hashlib.sha256(str(process["args"]).encode()).hexdigest()}


def activity(source,bindings,budget):
    processes=process_inventory()
    if not processes: raise g.GuardError("Empty native activity inventory")
    parents={p["pid"]:p["ppid"] for p in processes}; ignored=set(); pid=os.getpid()
    while pid and pid not in ignored: ignored.add(pid); pid=parents.get(pid,0)
    by_pid={}
    for b in bindings:
        if not isinstance(b,dict) or not isinstance(b.get("pid"),int) or b["pid"] in by_pid:
            raise g.GuardError("Invalid/duplicate runtime binding")
        by_pid[b["pid"]]=b
    needle=str(source.parent).replace("\\","/").casefold()
    records=[]; active=[]
    for p in processes:
        if p["pid"] in ignored: continue
        name=Path(str(p["name"]).replace("\\","/")).name
        args=p["args"]
        if not args or not str(args).strip():
            if RUNTIME.fullmatch(name) and not (os.name=="nt" and t.confirmed_exited_windows(p["pid"])):
                raise g.GuardError("Inaccessible live runtime; current activity cannot be proved")
            continue
        normal=str(args).replace("\\","/").casefold()
        if needle in normal: raise g.GuardError("Current process refers to this app; preserve its build")
        if NEXT.search(str(args)):
            if p["pid"] not in by_pid:
                raise g.GuardError("Unmapped live Next preview; resolve PID/build before cleanup")
            active.append(binding_proof(by_pid[p["pid"]],p,budget))
        records.append({"pid":p["pid"],"ppid":p["ppid"],"name":name,"stamp":p["stamp"],
                        "command_sha256":hashlib.sha256(str(args).encode()).hexdigest()})
    if sys.platform=="darwin":
        opened=t._run(["/usr/sbin/lsof","-nP","+D",str(source),"-Fpcn"])
        if opened.returncode not in (0,1) or opened.stderr.strip() or opened.stdout.strip():
            raise g.GuardError("Build open-file activity present or lsof visibility incomplete")
    return {"status":"clear","active_previews":active,"visible_processes":len(processes),
        "records_sha256":t.digest(records),"captured_at":g.utc()}


def verify_bindings(root,source,assessment,proof,budget):
    value,_=g.read_json(assessment)
    current=activity(source,value.get("runtime_bindings",[]),budget)
    if proof["build_id"] in {x["build_id"] for x in current["active_previews"]}:
        raise g.GuardError("Selected build ID is in use by a current preview (including aliases)")
    for item in current["active_previews"]:
        app=Path(item["app"])
        if g.below(source,app) or g.below(app,source):
            raise g.GuardError("Selected build overlaps an active app")
    return current


def reference_review(root,source,proof,budget):
    # The caller names reviewed launch/config scopes, bounded and hash-bound.
    # Unknown consumers remain an explicit semantic limitation, not a global claim.
    records={}
    for relative in proof["reference_files"]:
        path=rel_path(root,relative); raw,rec=read_evidence(path,budget)
        if rec!=proof["evidence"][relative]: raise g.GuardError("Reference input changed")
        body=raw.decode("utf-8-sig").replace("\\\\","/")
        for target in (source,source.parent):
            rel=target.relative_to(root).as_posix()
            if A.path_token(body,rel,root):
                raise g.GuardError("A current reviewed launch/configuration file references this candidate")
        records[relative]=rec
    return {"records":records,"scope":proof["review"]["reference_scope"],
            "global_reference_absence_proven":False}


def limits(args):
    if not args.confirm_idle: raise g.GuardError("--confirm-idle required; known writers must remain stopped")
    if (isinstance(args.idle_seconds,bool) or not isinstance(args.idle_seconds,(int,float))
            or not math.isfinite(args.idle_seconds) or not 1<=args.idle_seconds<=60):
        raise g.GuardError("Idle observation interval must be finite and 1..60 seconds")
    return {"max_files":t.integer(args.max_files,"max-files",1000000),
            "max_bytes":t.integer(args.max_bytes,"max-bytes",2**50),"idle_seconds":args.idle_seconds}


def plan_command(args):
    options=limits(args); budget=t.Budget(options["max_bytes"])
    root=g.project_root(args.project,args.codex_home); source=source_path(root,args.source)
    assessment=admin(args.assessment,root); output=admin(args.output,root,True)
    proof=assess(root,source,assessment,budget)
    first=snapshot(source,options["max_files"],budget)
    if not first["selected"]: raise g.GuardError("No independent supported generated files; shared/protected files remain")
    before=verify_bindings(root,source,assessment,proof,budget)
    refs=reference_review(root,source,proof,budget)
    time.sleep(options["idle_seconds"])
    same_snapshot(snapshot(source,options["max_files"]),first)
    after=verify_bindings(root,source,assessment,proof,budget)
    if before["active_previews"]!=after["active_previews"]:
        raise g.GuardError("Active preview bindings changed during review")
    if assess(root,source,assessment,budget)!=proof or reference_review(root,source,proof,budget)!=refs:
        raise g.GuardError("Retained evidence changed")
    allocated=[x["allocated_bytes"] for x in first["selected"].values()]
    value={"schema":POLICY,"tool_version":VERSION,"action":"delete-independent-inactive-next-build-files",
        "created_at":g.utc(),"project":str(root),"project_identity":g.root_identity(root),"codex_home":args.codex_home,
        "source":args.source,"source_volume":r.volume(source),"assessment_path":str(assessment),"proof":proof,
        "snapshot":first,"limits":options,"reference_evidence":refs,"activity_evidence":after,
        "planned_files":len(first["selected"]),"retained_files":len(first["retained"]),
        "logical_bytes":sum(x["fingerprint"]["size"] for x in first["selected"].values()),
        "allocated_bytes":sum(allocated) if all(x is not None for x in allocated) else None,
        "effect":"Only selected independent generated files will be deleted. Kept source/results/shared files stay. This inactive candidate must be rebuilt before serving again.",
        "project_commands_executed":False,"historical_logs_fabricated":False}
    sha=r.atomic_json(output,value)
    print(json.dumps({"plan":str(output),"plan_sha256":sha,"planned_files":value["planned_files"],
        "retained_files":value["retained_files"],"logical_bytes":value["logical_bytes"],"allocated_bytes":value["allocated_bytes"]}))
    return value


def claim(root,source,plan,sha,receipt):
    folder=root/CLAIMS
    try: os.mkdir(folder,0o700)
    except FileExistsError: g.ancestors(folder)
    name=t.digest({"project":plan["project_identity"],"source":plan["source"],"build_id":plan["proof"]["build_id"]})+".json"
    path=folder/name
    return {"path":str(path),"sha256":r.atomic_json(path,{"schema":POLICY,"plan_sha256":sha,
        "receipt":str(receipt),"source":plan["source"],"build_id":plan["proof"]["build_id"],"started_at":g.utc(),
        "automatic_retry":False})}


def hash_record(rec):
    return {k:v for k,v in rec.items() if k not in {"reason","allocated_bytes"}}


def apply_command(args):
    if not args.confirm_idle: raise g.GuardError("--confirm-idle required")
    path=admin(args.plan); plan,sha=g.read_json(path)
    if args.authorize_plan!=sha or plan.get("schema")!=POLICY or plan.get("tool_version")!=VERSION or plan.get("action")!="delete-independent-inactive-next-build-files":
        raise g.GuardError("Exact supported plan SHA/schema/version required")
    root=g.project_root(plan["project"],plan.get("codex_home")); g.same_root(root,plan["project_identity"])
    source=source_path(root,plan["source"]); admin(path,root)
    receipt=admin(args.receipt,root,True)
    options=limits(argparse.Namespace(**plan["limits"],confirm_idle=True)); budget=t.Budget(options["max_bytes"])
    stack,event_root,events=A.reserve_events(receipt)
    try: reservation=claim(root,source,plan,sha,receipt)
    except BaseException:
        stack.close(); raise
    value={"schema":POLICY,"plan_sha256":sha,"source":plan["source"],"started_at":g.utc(),
        "status":"validating","deleted_files":0,"deleted_logical_bytes":0,"deleted_allocated_bytes":0,
        "retained_files":len(plan["snapshot"]["retained"]),"pending_batch":[],"apply_claim":reservation,
        "source_free_before_bytes":g.volume_free(root),"project_code_executed":False,"database_connected":False,
        "automatic_retry":False}
    def checkpoint(event):
        events.write(json.dumps({"at":g.utc(),**event},ensure_ascii=False)+"\n")
        events.flush(); os.fsync(events.fileno())
    try:
        assessment=admin(plan["assessment_path"],root)
        proof=assess(root,source,assessment,budget)
        if proof!=plan["proof"] or r.volume(source)!=plan["source_volume"]:
            raise g.GuardError("Retained evidence or source volume changed")
        current=snapshot(source,options["max_files"],budget)
        same_snapshot(current,plan["snapshot"],True)
        if plan["planned_files"]!=len(current["selected"]) or plan["logical_bytes"]!=sum(v["fingerprint"]["size"] for v in current["selected"].values()):
            raise g.GuardError("Plan accounting changed")
        verify_bindings(root,source,assessment,proof,budget)
        if reference_review(root,source,proof,budget)!=plan["reference_evidence"]:
            raise g.GuardError("Reviewed reference scope changed")
        time.sleep(options["idle_seconds"])
        same_snapshot(snapshot(source,options["max_files"]),current)
        verify_bindings(root,source,assessment,proof,budget)
        # Rehashing all evidence immediately before holding prevents stale review.
        if assess(root,source,assessment,budget)!=proof: raise g.GuardError("Evidence changed before release")
        required=plan["logical_bytes"]+2*(proof["assessment_record"]["fingerprint"]["size"]+sum(x["fingerprint"]["size"] for x in proof["evidence"].values()))
        if budget.used+required>budget.maximum: raise g.GuardError("Insufficient complete-release read budget")
        with t.retained_guards(root,assessment,proof,budget) as held:
            value["status"]="releasing"; checkpoint({"status":"release_started"})
            items=sorted(current["selected"].items())
            for offset in range(0,len(items),64):
                g.same_root(root,plan["project_identity"]); t.check_held(held)
                batch=items[offset:offset+64]
                value["pending_batch"]=[rel for rel,_ in batch]
                checkpoint({"status":"batch_delete_pending","members":[{"relative":rel,"record":rec} for rel,rec in batch]})
                for rel,rec in batch:
                    file=source.joinpath(*rel.split("/"))
                    for prefix in ("",*["/".join(rel.split("/")[:i]) for i in range(1,len(rel.split("/")))]):
                        directory=source.joinpath(*prefix.split("/")) if prefix else source
                        expected=current["directories"][prefix]["fingerprint"]
                        g.same_root(directory,{k:expected[k] for k in ("device","inode")})
                    if classification(rel,g.plain(file,False))!=rec["reason"]:
                        raise g.GuardError("Shared/protected classification changed before deletion")
                    t.file_hash(file,hash_record(rec),budget,delete=True)
                    value["deleted_files"]+=1; value["deleted_logical_bytes"]+=rec["fingerprint"]["size"]
                    value["deleted_allocated_bytes"]+=rec["allocated_bytes"] or 0
                    value["pending_batch"].remove(rel)
                checkpoint({"status":"batch_completed","deleted_files":value["deleted_files"]})
            t.check_held(held)
        # Never remove the build root or retained files/directories.
        value["status"]="completed"
    except (OSError,g.GuardError,ValueError,KeyError,TypeError) as exc:
        value["status"]="partial_or_uncertain" if value["status"]=="releasing" else "refused_before_delete"
        value["error"]=str(exc)
    finally:
        value.update(finished_at=g.utc(),source_free_after_bytes=g.volume_free(root),bytes_read=budget.used)
        b,a=value["source_free_before_bytes"],value["source_free_after_bytes"]
        value["source_free_delta_bytes"]=a-b if a is not None and b is not None else None
        try:
            checkpoint({"status":value["status"],"deleted_files":value["deleted_files"]})
            events.close(); r.atomic_json(receipt,value)
        finally: stack.close()
    print(json.dumps({"receipt":str(receipt),"status":value["status"],"deleted_files":value["deleted_files"],
        "deleted_logical_bytes":value["deleted_logical_bytes"],"retained_files":value["retained_files"]}))
    if value["status"]!="completed": raise g.GuardError(value.get("error","Incomplete release; reconcile original claim"))
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version",action="version",version=VERSION)
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("plan")
    for name in ("project","source","assessment","output"): p.add_argument("--"+name,required=True)
    p.add_argument("--codex-home"); p.add_argument("--confirm-idle",action="store_true")
    p.add_argument("--max-files",type=int,default=50000); p.add_argument("--max-bytes",type=int,default=16*1024**3)
    p.add_argument("--idle-seconds",type=float,default=1)
    p=sub.add_parser("apply")
    for name in ("plan","authorize-plan","receipt"): p.add_argument("--"+name,required=True)
    p.add_argument("--confirm-idle",action="store_true")
    args=parser.parse_args(argv)
    try:
        if args.command=="plan": plan_command(args)
        else: apply_command(args)
        return 0
    except (OSError,g.GuardError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({"status":"refused","error":str(exc),"no_automatic_retry":True,**getattr(exc,"details",{})}),file=sys.stderr)
        return 2


if __name__=="__main__": sys.exit(main())
