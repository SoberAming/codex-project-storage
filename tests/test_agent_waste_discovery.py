"""Isolated metadata-only Agent task residue discovery tests, no cleanup.

All fictional files and reports are retained beneath --work-root.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--work-root', required=True)
opts, remaining = parser.parse_known_args()
BASE = Path(os.path.abspath(os.path.expanduser(opts.work_root)))
if BASE.parent == BASE or BASE == Path.home().absolute() or any(p.lower() in {
        '.codex', '.agents', '.claude', '.kimi', '.kimi-code', '.workbuddy', '.codebuddy',
        'sessions', 'credentials', 'secrets'} for p in BASE.parts):
    parser.error('work-root must be a precise test directory outside Agent state')
for ancestor in reversed((BASE, *BASE.parents)):
    try:
        s = os.lstat(ancestor)
    except FileNotFoundError:
        continue
    if stat.S_ISLNK(s.st_mode) or getattr(s, 'st_file_attributes', 0) & 0x400:
        parser.error('work-root cannot contain linked ancestors')
BASE.mkdir(parents=True, exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix='agent-waste-discovery-', dir=BASE))
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/project_profiler.py'
spec = importlib.util.spec_from_file_location('agent_waste_profiler_under_test', SCRIPT)
PROFILE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PROFILE)


class AgentWasteDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=RUN))
        self.project, self.reports, self.codex = (self.area/x for x in ('project', 'reports', 'codex-fixture'))
        for p in (self.project, self.reports, self.codex):
            p.mkdir()
        self.env = dict(os.environ, CODEX_HOME=str(self.codex), PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        for key in ('CODEX_SQLITE_HOME', 'CLAUDE_CONFIG_DIR', 'KIMI_CODE_HOME', 'PROJECT_STORAGE_STATE_ROOTS'):
            self.env.pop(key, None)

    def put(self, rel, data=b'fictional task bytes', root=None):
        p = (root or self.project)/rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data.encode() if isinstance(data, str) else data)
        return p

    def cli(self, *args, ok=True, env=None, project=None, output=None):
        out = output or self.reports/('profile-'+str(len(list(self.reports.iterdir())))+'.json')
        result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), 'inspect',
            '--project', str(project or self.project), '--codex-home', str(self.codex),
            '--output', str(out), *map(str,args)], env=env or self.env,
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        if not ok:
            self.assertNotEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertFalse(out.exists())
            return result
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return json.loads(out.read_text(encoding='utf-8')), out

    def test_large_task_residue_is_prioritized_and_not_claimed_removable(self):
        self.put('scratch/run-a/capture.png', b'p'*(2*1024*1024))
        self.put('src/keep.py', 'print("source is valuable")')
        self.put('assets/original.png', b'original')
        self.put('deliverables/final.mp4', b'approved deliverable')
        report, out = self.cli()
        queue = report['agent_residue_review']
        self.assertEqual(queue['items'][0]['path'], 'scratch')
        self.assertEqual(queue['project_candidate_logical_bytes'], 2*1024*1024)
        self.assertEqual(queue['related_candidate_logical_bytes'], 0)
        self.assertFalse(queue['items'][0]['disposal_authorized'])
        self.assertEqual(queue['items'][0]['initiating_agent']['status'], 'not_established_by_metadata')
        self.assertFalse(queue['items'][0]['producer_verified'])
        self.assertEqual(queue['approved_release_bytes'], 0)
        self.assertEqual(queue['executed_release_bytes'], 0)
        self.assertIn('Agent task residue review queue',out.with_suffix('.md').read_text(encoding='utf-8'))
        self.assertEqual(report['commands_executed'], [])
        self.assertTrue((self.project/'scratch/run-a/capture.png').exists())

    def test_state_deliverables_and_sources_inside_scratch_are_retained(self):
        for root in ('.codex','.claude','.kimi','.kimi-code','.workbuddy','.codebuddy'):
            self.put(f'scratch/{root}/sessions/old.tmp', b'PRIVATE_STATE')
            self.put(f'scratch/{root}/direct.tmp', b'PRIVATE_STATE')
            self.put(f'scratch/{root}/package.json', '{"scripts":{"clean":"PRIVATE_STATE_COMMAND"}}')
        for rel in ('scratch/producer.py','scratch/config.json','scratch/business.sqlite',
                    'scratch/originals/capture.png','scratch/originals/important.tmp','scratch/evidence/screenshot.png',
                    'scratch/final.mp4','assets/scratch/keep.tmp','src/temp/keep.png'):
            self.put(rel,b'valuable')
        self.put('scratch/run-b/capture.png',b'candidate')
        report,out=self.cli()
        queue=report['agent_residue_review']
        self.assertEqual(queue['project_candidate_logical_bytes'],len(b'candidate'))
        combined=out.read_text(encoding='utf-8')+out.with_suffix('.md').read_text(encoding='utf-8')
        self.assertNotIn('PRIVATE_STATE',combined)
        self.assertEqual(report['coverage']['config_files_read'],0)

    def test_generic_runtime_children_are_separate_from_business_data(self):
        self.put('.runtime/old-capture-run/payload.bin',b'candidate'*100)
        self.put('.runtime/pgdata/base/123',b'business db')
        self.put('.runtime/old-capture-run/output.sqlite',b'unknown db')
        self.put('.runtime/old-capture-run/inputs/source.png',b'input')
        report,_=self.cli()
        paths={x['path'] for x in report['agent_residue_review']['items']}
        self.assertIn('.runtime/old-capture-run',paths)
        self.assertNotIn('.runtime',paths)
        self.assertNotIn('.runtime/pgdata',paths)
        self.assertEqual(report['agent_residue_review']['project_candidate_logical_bytes'],900)

    def test_partial_download_files_are_surfaced_without_opening_them(self):
        self.put('outputs/archive.zip.crdownload',b'partial'*100)
        self.put('outputs/keep-final.mp4',b'delivery')
        report,_=self.cli()
        items=report['agent_residue_review']['items']
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['path'],'outputs/archive.zip.crdownload')
        self.assertEqual(items[0]['category'],'task_download_fragment_clue')
        self.assertIn('completion', ' '.join(items[0]['evidence_required']))

    def test_related_roots_stay_separate_and_unconfigured_roots_are_not_scanned(self):
        ext=self.area/'explicit-related'
        unseen=self.area/'not-selected'
        self.put('captures/screen.png',b'related'*100,root=ext)
        self.put('scratch/huge.bin',b'never measured'*100,root=unseen)
        self.put('scratch/payload.bin',b'project')
        report,_=self.cli('--related-root',ext)
        queue=report['agent_residue_review']
        self.assertEqual(queue['project_candidate_logical_bytes'],7)
        self.assertEqual(queue['related_candidate_logical_bytes'],700)
        self.assertEqual(queue['items'][0]['scope'],'related_1')
        self.assertEqual(queue['items'][0]['action_support']['status'],'evidence_only')
        self.assertNotIn('not-selected',json.dumps(report))

    def test_state_roots_refused_for_project_related_and_report_outputs(self):
        for name in ('.claude','.kimi','.kimi-code','.workbuddy','.codebuddy'):
            state=self.area/name
            self.put('history.jsonl',b'PRIVATE',root=state)
            self.cli(project=state,ok=False)
            self.cli('--related-root',state,ok=False)
            self.cli(output=state/'report.json',ok=False)

    def test_configured_renamed_state_roots_are_rejected_before_content_read(self):
        for var in ('PROJECT_STORAGE_STATE_ROOTS','CLAUDE_CONFIG_DIR','KIMI_CODE_HOME'):
            state=self.area/(var.lower()+'-private')
            self.put('package.json','{"scripts":{"build":"PRIVATE_CONFIG_CONTENT"}}',root=state)
            env=dict(self.env)
            env[var]=json.dumps([str(state)]) if var=='PROJECT_STORAGE_STATE_ROOTS' else str(state)
            self.cli(project=state,env=env,ok=False)
            self.cli('--related-root',state,env=env,ok=False)
            self.cli(output=state/'report.json',env=env,ok=False)

    def test_metadata_queue_does_not_read_residue_or_source_bodies(self):
        self.put('scratch/capture.png',b'NEVER_READ_IMAGE')
        self.put('src/main.py',b'NEVER_READ_SOURCE')
        self.put('.claude/package.json',b'NEVER_READ_AGENT_STATE')
        with mock.patch.dict(os.environ,self.env,clear=True),mock.patch.object(PROFILE,'read_bounded',side_effect=AssertionError('no content reads expected')):
            profiler=PROFILE.Profiler(SimpleNamespace(max_files=100000,max_config_bytes=1048576),self.project,self.codex,[])
            profiler.walk(self.project,'project')
            profiler.parse_configs()
        self.assertEqual(profiler.config_count,0)
        self.assertEqual(profiler.config_bytes,0)

    def test_explicit_worktree_payload_still_profiles_and_custom_state_wins(self):
        worktree=self.codex/'worktrees/run-id/repository'
        self.put('.git','gitdir: /fictional/not-followed',root=worktree)
        self.put('package.json','{"dependencies":{"next":"1"}}',root=worktree)
        self.put('scratch/capture.png',b'fixture',root=worktree)
        report,_=self.cli(project=worktree)
        self.assertIn('Next.js',{x['name'] for x in report['ecosystems']})
        self.assertEqual(report['agent_residue_review']['project_candidate_logical_bytes'],7)
        env=dict(self.env,CLAUDE_CONFIG_DIR=str(worktree/'private-identity'))
        self.cli(project=worktree,env=env,ok=False)

    def test_bounded_git_common_pointer_remains_metadata_only(self):
        self.put('.git/commondir','../../external-common-repo')
        report,_=self.cli()
        self.assertTrue(any(x['field']=='commondir' for x in report['configured_path_clues']))
        self.assertFalse(any('content' in x for x in report['configured_path_clues']))
        self.assertEqual(report['commands_executed'],[])

    def test_native_cache_and_data_boundaries_do_not_become_task_scratch(self):
        self.put('.npm/scratch/cache.tmp',b'cache payload')
        self.put('data/download.part',b'valuable data')
        self.put('ms-playwright/captures/runtime.tmp',b'native runtime')
        report,_=self.cli()
        items=report['agent_residue_review']['items']
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['category'],'tool_managed_cache')
        self.assertEqual(items[0]['path'],'.npm')
        self.assertNotIn('agent_artifact_guard.py',items[0]['action_support'].get('executors_to_evaluate',[]))

    def test_linked_entries_are_not_followed_and_hardlinks_count_once(self):
        payload=b'fictional'*100
        source=self.put('scratch/one.bin',payload)
        other=self.project/'scratch/two.bin'
        try:
            os.link(source,other)
        except OSError as exc:
            self.skipTest('fixture filesystem lacks hardlinks: '+str(exc))
        report,_=self.cli()
        self.assertEqual(report['agent_residue_review']['project_candidate_logical_bytes'],len(payload))
        item=report['agent_residue_review']['items'][0]
        self.assertTrue(item['hardlink_cross_boundary'])
        self.assertEqual(item['action_support']['status'],'retained_shared_file_identity')
        self.assertIsNone(item['action_support']['executor'])
        self.assertEqual(item['action_support']['executors_to_evaluate'],[])
        self.assertFalse(item['disposal_authorized'])
        self.assertEqual(report['project_measurement']['logical_bytes'],len(payload))
        self.assertEqual(report['project_measurement']['unique_files'],1)
        self.assertEqual(report['project_measurement']['hardlink_duplicates'],1)
        self.assertEqual(report['agent_residue_review']['approved_release_bytes'],0)
        self.assertEqual(report['agent_residue_review']['executed_release_bytes'],0)
        self.assertEqual(source.read_bytes(),payload)
        self.assertEqual(other.read_bytes(),payload)

    def test_source_alias_is_retained_in_both_real_hardlink_traversal_orders(self):
        payload=b'fictional shared protected source'*31
        protected=self.put('src/keep.py',payload)
        candidate=self.project/'scratch/capture.png'
        candidate.parent.mkdir()
        try:
            os.link(protected,candidate)
        except OSError as exc:
            self.skipTest('fixture filesystem lacks hardlinks: '+str(exc))
        native_scandir=os.scandir
        for candidate_first in (True,False):
            with self.subTest(candidate_first=candidate_first):
                @contextlib.contextmanager
                def ordered_scandir(anchor):
                    # Only traversal order is controlled; DirEntry/stat/FileID,
                    # link counts and payloads are from the real filesystem.
                    with native_scandir(anchor) as iterator:
                        entries=list(iterator)
                        sid=(os.fstat(anchor) if isinstance(anchor,int) else os.stat(anchor))
                        root_stat=os.stat(self.project)
                        if (sid.st_dev,sid.st_ino)==(root_stat.st_dev,root_stat.st_ino):
                            entries.sort(key=lambda e: e.name,reverse=candidate_first)
                        yield iter(entries)
                with mock.patch.dict(os.environ,self.env,clear=True),mock.patch.object(PROFILE.os,'scandir',side_effect=ordered_scandir):
                    profiler=PROFILE.Profiler(SimpleNamespace(max_files=100000,max_config_bytes=1048576),self.project,self.codex,[])
                    profiler.walk(self.project,'project')
                nodes=list(profiler.nodes.values())
                for i,node in enumerate(nodes):
                    node['id']=f'fixture-{i}'
                queue=PROFILE.agent_residue_review(nodes)
                self.assertEqual(sum(n['measurement']['logical_bytes'] for n in nodes),len(payload))
                self.assertEqual(sum(n['measurement']['unique_files'] for n in nodes),1)
                self.assertEqual(sum(n['measurement']['hardlink_duplicates'] for n in nodes),1)
                candidate_node=next(n for n in nodes if n['category']=='agent_task_residue_clue')
                source_node=next(n for n in nodes if n['category']=='source_and_other')
                self.assertEqual(candidate_node['measurement']['logical_bytes'],len(payload) if candidate_first else 0)
                self.assertEqual(source_node['measurement']['logical_bytes'],0 if candidate_first else len(payload))
                for node in (candidate_node,source_node):
                    self.assertEqual(node['action_support']['status'],'retained_shared_file_identity')
                    self.assertIsNone(node['action_support']['executor'])
                for item in queue['items']:
                    self.assertFalse(item['disposal_authorized'])
                    self.assertEqual(item['action_support']['executors_to_evaluate'],[])
                self.assertEqual(queue['approved_release_bytes'],0)
                self.assertEqual(queue['executed_release_bytes'],0)
                self.assertEqual(protected.read_bytes(),payload)
                self.assertEqual(candidate.read_bytes(),payload)

    def test_bounded_scan_never_claims_complete_lifecycle_coverage(self):
        for i in range(8):
            self.put(f'scratch/run-{i}/payload.bin',b'fixture')
        report,_=self.cli('--max-files',2)
        self.assertTrue(report['coverage']['limit_hit'])
        self.assertFalse(report['coverage']['project_traversal_complete'])
        self.assertLessEqual(report['coverage']['files_observed'],2)
        self.assertEqual(report['agent_residue_review']['approved_release_bytes'],0)

    def test_empty_project_does_not_invent_residue_or_savings(self):
        report,_=self.cli()
        queue=report['agent_residue_review']
        self.assertEqual(queue['items'],[])
        self.assertEqual(queue['project_candidate_logical_bytes'],0)
        self.assertEqual(queue['related_candidate_logical_bytes'],0)
        self.assertEqual(queue['approved_release_bytes'],0)


    def test_shared_and_independent_files_in_one_partition_are_split_for_review(self):
        payload=b'fictional shared'*37
        shared=self.put('scratch/shared.bin',payload)
        try:
            os.link(shared,self.project/'scratch/alias.bin')
        except OSError:
            self.skipTest('Actual hardlinks unavailable')
        independent=b'fictional independent payload'
        self.put('scratch/independent.bin',independent)
        report,_=self.cli()
        item=next(n for n in report['nodes'] if n['category']=='agent_task_residue_clue')
        self.assertEqual(item['file_protection']['independent_review_logical_bytes'],len(independent))
        self.assertEqual(item['file_protection']['shared_retained_unique_logical_bytes'],len(payload))
        self.assertEqual(item['action_support']['status'],'requires_file_level_split')
        self.assertIsNone(item['action_support']['executor'])
        self.assertEqual(report['agent_residue_review']['approved_release_bytes'],0)
        self.assertEqual(shared.read_bytes(),payload)


if __name__=='__main__':
    print('Isolated Agent residue discovery fixtures retained at: '+str(RUN),flush=True)
    unittest.main(argv=[sys.argv[0],*remaining])
