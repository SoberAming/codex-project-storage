"""Behavioral tests of resumable metadata inventory on owned fictional projects."""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

parser=argparse.ArgumentParser(add_help=False)
parser.add_argument("--work-root",required=True)
options,remaining=parser.parse_known_args()
BASE=Path(options.work_root).absolute(); BASE.mkdir(parents=True,exist_ok=True)
RUN=Path(tempfile.mkdtemp(prefix="batch-inventory-tests-",dir=BASE))
SCRIPT=Path(__file__).resolve().parents[1]/"scripts/project_batches.py"
spec=importlib.util.spec_from_file_location("batch_tested",SCRIPT)
T=importlib.util.module_from_spec(spec); spec.loader.exec_module(T)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.area=Path(tempfile.mkdtemp(prefix=self._testMethodName+"-",dir=RUN))
        self.project=self.area/"project"; self.project.mkdir()
        self.folder=self.area/"ledger"
    def put(self,rel,data=b"fixture"):
        p=self.project/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data); return p
    def discover(self,units=None,focus="metadata",**extra):
        args=NS(project=str(self.project),output=str(self.folder),codex_home=None,unit=units or [],
                focus=focus,max_units=20000,max_directory_entries=200000)
        for k,v in extra.items():setattr(args,k,v)
        with contextlib.redirect_stdout(io.StringIO()): return T.discover(args)
    def scan(self,maximum=10,units=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return T.scan(NS(ledger=str(self.folder),unit=units or [],max_files=maximum,max_seconds=30))
    def finish(self):
        for _ in range(100):
            r=self.scan(29)
            if not r["pending_entries"]: return r
        self.fail("metadata queue did not finish")
    def report(self):
        path=self.area/("report-"+str(len(list(self.area.glob("report-*"))))+".json")
        with contextlib.redirect_stdout(io.StringIO()):
            return T.report(NS(ledger=str(self.folder),output=str(path)))
    def test_resume_preserves_completed_work_without_double_count(self):
        for i in range(47): self.put(".tmp/task-a/tree/f"+str(i),b"x"*10)
        self.put(".tmp/task-b/second",b"y"*13)
        self.discover()
        a=self.scan(8); self.assertGreater(a["pending_entries"],0)
        self.finish(); r=self.report()
        self.assertEqual(r["file_paths"],48); self.assertEqual(r["observed_unique_logical_bytes"],483)
        before=r["file_paths"];self.scan(10);self.assertEqual(self.report()["file_paths"],before)
    def test_completed_small_unit_available_when_other_unit_pending(self):
        self.put(".tmp/a/.next/server/chunks/a.js",b"x"*23)
        for i in range(200):self.put(".tmp/z/file"+str(i))
        self.discover();self.scan(100,[".tmp/a"]);r=self.report()
        self.assertFalse(r["coverage"]["project_complete"])
        self.assertTrue(r["build_units"][0]["metadata_complete"])
        self.assertEqual(r["build_units"][0]["independent_review_bytes"],23)
    def test_shared_file_does_not_protect_unrelated_independent_files(self):
        p=self.put(".tmp/a/.next/server/chunks/a.js",b"shared"*20)
        q=self.project/".tmp/b/.next/server/chunks/a.js";q.parent.mkdir(parents=True)
        try:os.link(p,q)
        except OSError:self.skipTest("Actual hardlinks unavailable on this test filesystem")
        self.put(".tmp/a/.next/server/chunks/b.js",b"independent")
        self.discover();self.finish();r=self.report()
        self.assertEqual(r["observed_unique_logical_bytes"],131)
        self.assertEqual(sum(x["independent_review_bytes"]for x in r["build_units"]),11)
        self.assertEqual(sum(x["shared_files"]for x in r["build_units"]),2)
    def test_private_state_never_body_read_or_descended(self):
        s=self.put(".codex/sessions/current.jsonl",b"protected")
        self.put(".tmp/a/.claude/projects/secret.jsonl",b"protected")
        self.put(".tmp/a/.next/server/chunks/a.js",b"ordinary")
        self.discover()
        self.finish();r=self.report()
        self.assertEqual(r["file_paths"],1)
        self.assertTrue(any("private/state" in x["reason"]for x in r["excluded"]))
        self.assertEqual(s.read_bytes(),b"protected")
    def test_build_focus_prunes_dependencies_but_measures_next(self):
        self.put(".tmp/a/node_modules/large-library.js",b"z"*1000)
        self.put(".tmp/a/source/.next/server/chunks/a.js",b"x"*101)
        self.discover(focus="builds");self.finish();r=self.report()
        self.assertEqual(r["observed_unique_logical_bytes"],101)
        self.assertTrue(any("node_modules" in x["path"]for x in r["excluded"]))
    def test_link_not_followed(self):
        outside=self.area/"outside";outside.mkdir();(outside/"large.js").write_bytes(b"x"*1000)
        d=self.project/".tmp/a";d.mkdir(parents=True)
        try:os.symlink(outside,d/"redirect",target_is_directory=True)
        except OSError:self.skipTest("Symlink privilege unavailable")
        self.discover();self.finish();r=self.report()
        self.assertEqual(r["file_paths"],0);self.assertEqual(len(r["excluded"]),1)
    def test_explicit_units_cannot_escape(self):
        for bad in ("../outside","a/../../x","a\\b","a:stream"):
            with self.subTest(bad=bad):
                with self.assertRaises(T.G.GuardError):self.discover([bad])
    def test_overlapping_units_refused(self):
        with self.assertRaises(T.G.GuardError):self.discover(["a","a/b"])
    def test_state_ledger_location_refused_before_creation(self):
        self.folder=self.area/".claude"/"ledger"
        with self.assertRaises(T.G.GuardError):self.discover()
        self.assertFalse(self.folder.exists())
    def test_changed_root_rejected_on_resume(self):
        self.put("a");self.discover();self.project.rename(self.area/"old");self.project.mkdir()
        with self.assertRaises(T.G.GuardError):self.scan()
    def test_existing_command_lock_is_never_removed(self):
        self.put("a");self.discover();lock=self.folder/".command-lock";lock.write_text("other")
        with self.assertRaises(T.G.GuardError):self.scan()
        self.assertEqual(lock.read_text(),"other")
    def test_oversized_directory_is_explicit_error_not_complete(self):
        for i in range(5):self.put(".tmp/a/f"+str(i))
        self.discover(max_directory_entries=2);self.scan(10);r=self.report()
        self.assertEqual(r["units"][0]["status"],"error")
        self.assertFalse(r["coverage"]["project_complete"])
    def test_bad_unit_does_not_block_other_independent_unit(self):
        self.put(".tmp/a/f");self.put(".tmp/b/f")
        self.discover();self.project.joinpath(".tmp/a").rename(self.project/".tmp/a-renamed")
        self.finish();r=self.report()
        self.assertEqual({t["path"]:t["status"]for t in r["units"]},{".tmp/a":"error",".tmp/b":"complete"})
    def test_no_anonymous_partition_after_4096_tasks(self):
        # Discovery/report need not scan every task to retain their exact names.
        for i in range(4100):(self.project/".tmp"/("task-"+str(i))).mkdir(parents=True)
        self.discover();r=self.report()
        self.assertEqual(len(r["units"]),4100)
        self.assertFalse(r["coverage"]["anonymous_overflow_buckets"])
        self.assertEqual(len({t["path"]for t in r["units"]}),4100)
    def test_unknown_identity_never_collapses_files(self):
        self.put(".tmp/a/.next/server/chunks/a.js",b"a")
        self.put(".tmp/a/.next/server/chunks/b.js",b"bb")
        self.discover()
        # Path-index preservation is independently asserted even without a global byte promise.
        self.finish();r=self.report();self.assertEqual(r["file_paths"],2)
        self.assertEqual(r["observed_unique_logical_bytes"],3)
    def test_cli_resumes_in_separate_process(self):
        self.put(".tmp/a/.next/server/chunks/a.js",b"x"*127)
        def run(*args):
            r=subprocess.run([sys.executable,"-I","-B",str(SCRIPT),*map(str,args)],
                capture_output=True,text=True,encoding="utf-8",timeout=40)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            return json.loads(r.stdout)
        run("discover","--project",self.project,"--output",self.folder,"--focus","builds")
        run("scan","--ledger",self.folder,"--max-files",2)
        run("scan","--ledger",self.folder,"--max-files",100)
        result=run("report","--ledger",self.folder,"--output",self.area/"cli-report.json")
        self.assertTrue(result["selected_units_complete"])
        self.assertFalse(result["project_complete"])
        self.assertEqual(self.project.joinpath(".tmp/a/.next/server/chunks/a.js").read_bytes(),b"x"*127)


if __name__=="__main__":unittest.main(argv=[sys.argv[0],*remaining])
