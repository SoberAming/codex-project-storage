"""Owned fictional builds; source/state sentinels never enter a deletion plan."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest import mock

parser=argparse.ArgumentParser(add_help=False);parser.add_argument("--work-root",required=True)
parser.add_argument("--runtime-bindings",help="Optional exact native/HTTP bindings on a desktop already hosting Next previews; never needed on isolated CI")
options,remaining=parser.parse_known_args()
BASE=Path(options.work_root).absolute(); BASE.mkdir(parents=True,exist_ok=True)
RUN=Path(tempfile.mkdtemp(prefix="build-guard-tests-",dir=BASE))
SCRIPT=Path(__file__).resolve().parents[1]/"scripts/build_artifact_guard.py"
spec=importlib.util.spec_from_file_location("build_guard_tested",SCRIPT)
T=importlib.util.module_from_spec(spec);spec.loader.exec_module(T)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.area=Path(tempfile.mkdtemp(prefix=self._testMethodName+"-",dir=RUN))
        self.project=self.area/"project";self.project.mkdir()
        self.relative=".tmp/closed-run-123/source/apps/web/.next"
        self.source=self.project/self.relative;self.source.mkdir(parents=True)
        self.app=self.source.parent
        self.manifest=self.app/"package.json"
        self.manifest.write_text(json.dumps({"scripts":{"build":"next build"},"dependencies":{"next":"15.1.6"}}))
        self.code=self.app/"app/page.tsx";self.code.parent.mkdir()
        self.code.write_text("export default function Page(){ return 'fixture'; }")
        self.current=self.project/"apps/current";self.current.mkdir(parents=True)
        self.ref=self.project/"tools/start-current.py";self.ref.parent.mkdir()
        self.ref.write_text("CURRENT = 'apps/current' # Retained current launcher; never executed")
        self.put("BUILD_ID",b"fictional-build-123")
        self.put("server/chunks/main.js",b"/* synthetic generated JS */"*1024)
        self.put("static/chunks/main.js",b"/* synthetic static JS */"*512)
        self.put("cache/webpack/client-production/0.pack",b"Fictional cache"*256)
        self.protected=[self.put("business.sqlite",b"fixture business database"),
                        self.put("server/app/page.html",b"fixture retained prerender"),
                        self.put("unique.mp4",b"fixture retained media"),
                        self.put("package.json",b'{"generated":"manifest"}')]
        for rel in ("src/source.py",".codex/sessions/current.jsonl",".codex/session_index.jsonl",
                    ".claude/projects/state.jsonl",".kimi-code/sessions/current.jsonl",
                    ".workbuddy/state/index.json","recovery/checkpoint.zip",".env"):
            p=self.project/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b"Fictional sentinel must stay byte-identical")
            self.protected.append(p)
        self.expected={str(p):p.read_bytes() for p in self.protected}
        self.assessment=self.area/"assessment.json";self.plan=self.area/"plan.json";self.receipt=self.area/"receipt.json"
        self.value={"schema":T.ASSESSMENT,"source":self.relative,"lifecycle_mode":"current-state-reconstruction",
            "review":{k:"Fictional isolated fixture review for "+k for k in
                ("reviewer","origin","inactive_reason","retained_source_and_results","not_rollback_or_deployment","reference_scope","rebuild_impact")},
            "producer":{"path":self.manifest.relative_to(self.project).as_posix(),"sha256":sha(self.manifest)},
            "retained_evidence":[{"path":self.code.relative_to(self.project).as_posix(),"sha256":sha(self.code)}],
            "reference_files":[{"path":self.ref.relative_to(self.project).as_posix(),"sha256":sha(self.ref)}],
            "retained_app_roots":["apps/current"],"runtime_bindings":[]}
        self.save()
    def put(self,relative,data):
        path=self.source/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path
    def save(self):self.assessment.write_text(json.dumps(self.value),encoding="utf-8")
    def args(self):
        return NS(project=str(self.project),source=self.relative,assessment=str(self.assessment),output=str(self.plan),
            codex_home=None,confirm_idle=True,max_files=1000,max_bytes=64*1024**2,idle_seconds=1)
    def make_plan(self):
        with mock.patch.object(T,"activity",return_value={"status":"clear","active_previews":[]}),mock.patch.object(T.time,"sleep"),contextlib.redirect_stdout(io.StringIO()):
            return T.plan_command(self.args())
    def apply(self,plan=None):
        args=NS(plan=str(self.plan),authorize_plan=sha(self.plan),receipt=str(self.receipt),confirm_idle=True)
        with mock.patch.object(T,"activity",return_value={"status":"clear","active_previews":[]}),mock.patch.object(T.time,"sleep"),contextlib.redirect_stdout(io.StringIO()):
            return T.apply_command(args)
    def assert_protected(self):
        for path,data in self.expected.items():self.assertEqual(Path(path).read_bytes(),data,path)
    def test_plan_distinguishes_supported_and_retained(self):
        p=self.make_plan();self.assertEqual(p["planned_files"],3)
        self.assertTrue(p["proof"]["historical_completion_log_required"] is False)
        self.assertTrue(self.source.joinpath("server/chunks/main.js").is_file())
        self.assert_protected()
    def test_selective_apply_keeps_source_sessions_indexes_and_database(self):
        p=self.make_plan();result=self.apply()
        self.assertEqual(result["status"],"completed");self.assertEqual(result["deleted_files"],3)
        self.assertFalse(self.source.joinpath("server/chunks/main.js").exists())
        self.assertTrue((self.source/"BUILD_ID").exists());self.assert_protected()
        self.assertTrue(self.manifest.exists());self.assertTrue(self.code.exists())
    def test_shared_file_is_kept_but_independent_files_still_delete(self):
        shared=self.source/"server/chunks/main.js";alias=self.project/"retained-shared.js"
        try:os.link(shared,alias)
        except OSError:self.skipTest("Actual hardlinks unavailable")
        before=sha(shared);p=self.make_plan()
        self.assertEqual(p["planned_files"],2)
        self.assertEqual(p["snapshot"]["retained"]["server/chunks/main.js"]["reason"],"protected_shared_identity")
        result=self.apply();self.assertEqual(result["deleted_files"],2)
        self.assertEqual(sha(shared),before);self.assertEqual(sha(alias),before);self.assert_protected()
    def test_new_member_after_plan_refuses_before_delete(self):
        self.make_plan();self.put("static/chunks/new.js",b"new")
        with self.assertRaises(T.g.GuardError):self.apply()
        r=json.loads(self.receipt.read_text());self.assertEqual(r["status"],"refused_before_delete")
        self.assertEqual(r["deleted_files"],0);self.assert_protected()
    def test_changed_file_after_plan_refuses_before_delete(self):
        self.make_plan();self.put("server/chunks/main.js",b"changed")
        with self.assertRaises(T.g.GuardError):self.apply()
        self.assertEqual(json.loads(self.receipt.read_text())["deleted_files"],0)
    def test_late_hardlink_refuses_before_delete(self):
        self.make_plan()
        try:os.link(self.source/"static/chunks/main.js",self.project/"late.js")
        except OSError:self.skipTest("Actual hardlinks unavailable")
        with self.assertRaises(T.g.GuardError):self.apply()
        self.assertEqual(json.loads(self.receipt.read_text())["deleted_files"],0)
    def test_changed_retained_source_refuses(self):
        self.make_plan();self.code.write_text("changed retained source")
        with self.assertRaises(T.g.GuardError):self.apply()
        self.assertTrue(self.source.joinpath("server/chunks/main.js").exists())
    def test_replay_with_new_receipt_is_refused(self):
        self.make_plan();self.put("server/chunks/main.js",b"changed")
        with self.assertRaises(T.g.GuardError):self.apply()
        self.receipt=self.area/"second.json"
        with self.assertRaises((T.g.GuardError,FileExistsError)):self.apply()
        self.assertFalse(self.receipt.exists())
    def test_current_or_rollback_keeper_is_rejected(self):
        self.value["retained_app_roots"]=[self.app.relative_to(self.project).as_posix()];self.save()
        with self.assertRaises(T.g.GuardError):self.make_plan()
    def test_source_root_of_current_app_not_accepted(self):
        args=self.args();args.source="apps/current/.next";(self.current/".next").mkdir()
        with self.assertRaises(T.g.GuardError):T.plan_command(args)
    def test_formal_release_build_is_not_accepted(self):
        for rel in ("releases/saved/apps/web/.next",".tmp/a/rollback/web/.next","node_modules/app/.next"):
            with self.subTest(rel=rel),self.assertRaises(T.g.GuardError):T.source_path(self.project,rel)
    def test_missing_source_producer_not_replaced_by_idle_claim(self):
        self.manifest.unlink()
        with self.assertRaises((T.g.GuardError,OSError)):self.make_plan()
    def test_custom_build_recipe_refused(self):
        self.manifest.write_text(json.dumps({"scripts":{"build":"node user-script.js && next build"},"dependencies":{"next":"15"}}))
        self.value["producer"]["sha256"]=sha(self.manifest);self.save()
        with self.assertRaises(T.g.GuardError):self.make_plan()
    def test_no_historical_log_is_needed_but_review_is(self):
        self.value["review"].pop("inactive_reason");self.save()
        with self.assertRaises(T.g.GuardError):self.make_plan()
    def test_current_literal_launcher_reference_blocks(self):
        self.ref.write_text("APP = "+repr(str(self.app)))
        self.value["reference_files"][0]["sha256"]=sha(self.ref);self.save()
        with self.assertRaises(T.g.GuardError):self.make_plan()
    def test_similar_prefix_launcher_does_not_block_exact_other_app(self):
        self.ref.write_text("APP = "+repr(str(self.app)+"-old"))
        self.value["reference_files"][0]["sha256"]=sha(self.ref);self.save()
        self.assertEqual(self.make_plan()["planned_files"],3)
    def test_live_build_identity_alias_is_protected(self):
        with mock.patch.object(T,"activity",return_value={"status":"clear","active_previews":[{"build_id":"fictional-build-123"}]}),mock.patch.object(T.time,"sleep"):
            with self.assertRaises(T.g.GuardError):T.plan_command(self.args())
    def test_unknown_live_next_process_refused(self):
        records=[{"pid":444444,"ppid":0,"name":"node","args":"node next-server -p 3000","stamp":"fake native stamp"}]
        with mock.patch.object(T,"process_inventory",return_value=records):
            with self.assertRaises(T.g.GuardError):T.activity(self.source,[],T.t.Budget(1024**2))
    def test_process_referencing_this_candidate_blocks(self):
        records=[{"pid":444444,"ppid":0,"name":"node","args":"node "+str(self.app)+"/start.js","stamp":"fake"}]
        with mock.patch.object(T,"process_inventory",return_value=records):
            with self.assertRaises(T.g.GuardError):T.activity(self.source,[],T.t.Budget(1024**2))
    def test_private_evidence_never_opened(self):
        self.value["retained_evidence"]=[{"path":".codex/sessions/current.jsonl","sha256":"0"*64}];self.save()
        calls=[];original=T.read_evidence
        def capture(path,*args,**kwargs):
            calls.append(str(path));return original(path,*args,**kwargs)
        with mock.patch.object(T,"read_evidence",side_effect=capture):
            with self.assertRaises(T.g.GuardError):self.make_plan()
        self.assertFalse(any(".codex" in p for p in calls));self.assert_protected()
    def test_bounded_unit_required(self):
        args=self.args();args.max_files=2
        with mock.patch.object(T,"activity",return_value={"status":"clear","active_previews":[]}):
            with self.assertRaises(T.g.GuardError):T.plan_command(args)
    def test_idle_false_and_nonfinite_refused(self):
        for value in (False,float("nan"),float("inf"),True,0):
            args=self.args()
            if value is False:args.confirm_idle=False
            else:args.idle_seconds=value
            with self.subTest(value=value),self.assertRaises(T.g.GuardError):T.limits(args)
    def test_source_symlink_does_not_enter_plan(self):
        outside=self.area/"other.js";outside.write_bytes(b"outside")
        link=self.source/"static/chunks/link.js"
        try:os.symlink(outside,link)
        except OSError:self.skipTest("Symlink privilege unavailable")
        p=self.make_plan();self.assertEqual(p["planned_files"],3)
        self.assertEqual(p["snapshot"]["retained"]["static/chunks/link.js"]["reason"],"protected_link_not_followed")
        self.apply();self.assertEqual(outside.read_bytes(),b"outside")
    def test_native_cli_plan_apply_and_live_writer_refusal(self):
        if os.name!="nt" and sys.platform!="darwin":self.skipTest("Native Windows/macOS only")
        if options.runtime_bindings:
            self.value["runtime_bindings"]=json.loads(Path(options.runtime_bindings).read_text(encoding="utf-8"))
            self.save()
        def run(*args,ok=True):
            r=subprocess.run([sys.executable,"-I","-B",str(SCRIPT),*map(str,args)],
                capture_output=True,text=True,encoding="utf-8",timeout=90)
            if ok:self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            else:self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
            return r
        run("plan","--project",self.project,"--source",self.relative,"--assessment",self.assessment,
            "--output",self.plan,"--confirm-idle")
        run("apply","--plan",self.plan,"--authorize-plan",sha(self.plan),"--receipt",self.receipt,"--confirm-idle")
        result=json.loads(self.receipt.read_text());self.assertEqual(result["deleted_files"],3);self.assert_protected()
        # A real test-owned writer must be refused and never terminated by cleaner.
        self.put("server/chunks/new.js",b"new generated fixture")
        writer=self.area/"writer.py";writer.write_text("import sys,time\nf=open(sys.argv[1],'ab');time.sleep(35)\n")
        child=subprocess.Popen([sys.executable,"-B",str(writer),str(self.source/"server/chunks/new.js")])
        try:
            time.sleep(0.5)
            run("plan","--project",self.project,"--source",self.relative,"--assessment",self.assessment,
                "--output",self.area/"writer-plan.json","--confirm-idle",ok=False)
            self.assertIsNone(child.poll())
        finally:
            child.terminate();child.wait(timeout=10) # Only this test-owned writer.
        print("BUILD_NATIVE_INTEGRATION="+json.dumps({"deleted_files":3,
            "protected_sentinels_unchanged":len(self.protected),"live_writer_refused":True,"cleaner_killed_processes":False}))


if __name__=="__main__":unittest.main(argv=[sys.argv[0],*remaining])
