import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local_app"))
from core import PlannerError, make_plan, repository, review_plan, report, safe_export, classify
import core
from server import App, create_server


class LocalAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="local-planner-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.env = {"PATH":"/usr/bin:/bin", "HOME":str(self.base), "GIT_CONFIG_NOSYSTEM":"1", "GIT_CONFIG_GLOBAL":"/dev/null",
                    "GIT_AUTHOR_DATE":"2020-01-01T00:00:00+0000", "GIT_COMMITTER_DATE":"2020-01-01T00:00:00+0000"}
        self.git("init", "--initial-branch=main")
        self.commit("feat: seed")

    def git(self, *args):
        return subprocess.run(["/usr/bin/git","-c","user.name=Fixture","-c","user.email=fixture@example.invalid",*args],
                              cwd=self.repo,env=self.env,capture_output=True,check=True).stdout.decode().strip()

    def commit(self, msg): self.git("commit", "--allow-empty", "-m", msg)

    def plan(self, base="1.2.3", message="fix: correction"):
        self.git("tag", "v"+base); self.commit(message)
        snap=repository(str(self.repo))
        return snap,make_plan(snap,"refs/tags/v"+base,None)

    def test_stable_patch_minor_major(self):
        snap,p=self.plan();self.assertEqual(p["candidateVersion"],"1.2.4")
        self.commit("feat: feature");snap=repository(str(self.repo));p=make_plan(snap,"refs/tags/v1.2.3",None)
        self.assertEqual(p["candidateVersion"],"1.3.0")
        self.commit("feat!: break");snap=repository(str(self.repo));p=make_plan(snap,"refs/tags/v1.2.3",None)
        self.assertEqual(p["candidateVersion"],"2.0.0")

    def test_zero_major_breaking_is_minor(self):
        _,p=self.plan("0.4.2","fix!: break")
        self.assertEqual(p["candidateVersion"],"0.5.0")

    def test_initial_requires_explicit_valid_version(self):
        snap=repository(str(self.repo))
        for v in [None,"", "v1.0.0","01.2.3"]:
            with self.subTest(v=v), self.assertRaises(PlannerError):make_plan(snap,None,v)
        p=make_plan(snap,None,"0.1.0");self.assertEqual(p["candidateVersion"],"0.1.0")

    def test_prerelease_initial_stays_review(self):
        p=make_plan(repository(str(self.repo)),None,"1.0.0-rc.1")
        self.assertEqual(p["status"],"needs_review");self.assertIsNone(p["candidateVersion"])

    def test_unknown_and_merge_need_review(self):
        _,p=self.plan(message="chore: cleanup");self.assertEqual(p["status"],"needs_review")
        self.git("checkout","-b","side");self.commit("feat: branch")
        self.git("checkout","main");self.commit("fix: main")
        self.git("merge","--no-ff","side","-m","Merge branch side")
        p=make_plan(repository(str(self.repo)),"refs/tags/v1.2.3",None)
        self.assertEqual(p["status"],"needs_review")
        self.assertEqual(len({c['oid'] for c in p['commits']}),len(p['commits']))

    def test_breaking_footer_not_substring(self):
        def c(m):return classify({'message':m,'parents':[], 'oid':'x'})
        self.assertFalse(c("fix: break in word")["breaking"])
        self.assertTrue(c("fix: api\n\nBREAKING CHANGE: removed")["breaking"])
        self.assertFalse(c("fix: api\nBREAKING CHANGE: no separator")["breaking"])

    def test_no_release_for_empty_difference(self):
        self.git("tag","v1.0.0")
        p=make_plan(repository(str(self.repo)),"refs/tags/v1.0.0",None)
        self.assertEqual(p["status"],"no_release");self.assertIsNone(p["candidateVersion"])

    def test_duplicate_tag_normalization_requires_review(self):
        _,p=self.plan();self.git("tag","1.2.3","v1.2.3")
        p=make_plan(repository(str(self.repo)),"refs/tags/v1.2.3",None)
        self.assertEqual(p["status"],"needs_review")

    def test_occupied_candidate_on_unreachable_branch(self):
        self.git("tag","v1.0.0");self.git("checkout","-b","other")
        self.commit("fix: other");self.git("tag","v1.0.1");self.git("checkout","main")
        self.commit("fix: here")
        p=make_plan(repository(str(self.repo)),"refs/tags/v1.0.0",None)
        self.assertEqual(p["status"],"needs_review");self.assertIsNone(p["candidateVersion"])

    def test_annotated_tags_and_linked_worktree(self):
        self.git("tag","-a","v1.0.0","-m","release")
        self.commit("fix: next")
        linked=self.base/'linked';self.git('worktree','add','--detach',str(linked),'HEAD')
        snap=repository(str(linked));p=make_plan(snap,'refs/tags/v1.0.0',None)
        self.assertEqual(p['candidateVersion'],'1.0.1')
        self.assertIn(str(self.repo),snap['protected'])

    def test_status_special_names_and_no_git_mutation(self):
        f=self.repo/'file';f.write_text('a');self.git('add','file');self.commit('fix: tracked')
        f.write_text('changed');(self.repo/'line\n$(touch executed)').write_text('safe')
        def hashes():return {str(p.relative_to(self.repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.repo.rglob('*') if p.is_file()}
        before=hashes();snap=repository(str(self.repo));self.assertEqual(before,hashes())
        self.assertEqual(snap['status']['unstaged'],1);self.assertEqual(snap['status']['untracked'],1)
        self.assertFalse((self.repo/'executed').exists())

    def test_fsmonitor_and_shell_environment_not_executed(self):
        marker=self.base/'executed';helper=self.base/'helper';helper.write_text('#!/bin/sh\ntouch '+str(marker)+'\n');helper.chmod(0o700)
        self.git('config','core.fsmonitor',str(helper));repository(str(self.repo));self.assertFalse(marker.exists())

    def filter_fixture(self):
        (self.repo/'.gitattributes').write_text('tracked filter=probe\n')
        tracked=self.repo/'tracked';tracked.write_text('before\n')
        self.git('add','.gitattributes','tracked');self.commit('fix: tracked file')
        tracked.write_text('after!\n')
        return self.base/'filter-executed'

    def test_clean_and_process_filters_rejected_before_equal_length_status(self):
        marker=self.filter_fixture()
        for kind in ['clean','process']:
            with self.subTest(kind=kind):
                self.git('config','filter.probe.'+kind,'touch '+str(marker)+'; cat')
                with self.assertRaises(PlannerError) as caught:repository(str(self.repo))
                self.assertEqual(caught.exception.code,'unsupported_config')
                self.assertFalse(marker.exists())
                self.git('config','--unset','filter.probe.'+kind)

    def test_filter_config_race_uses_sealed_configuration(self):
        marker=self.filter_fixture();original=core.run;injected=False
        def race(args,*pos,**kw):
            nonlocal injected
            if kw.get('config_view') and not injected:
                injected=True
                self.git('config','filter.probe.clean','touch '+str(marker)+'; cat')
            return original(args,*pos,**kw)
        with mock.patch.object(core,'run',side_effect=race):
            with self.assertRaises(PlannerError):repository(str(self.repo))
        self.assertTrue(injected);self.assertFalse(marker.exists())

    def test_status_isolation_unavailable_fails_closed(self):
        original=core.subprocess.Popen
        def unavailable(args,*pos,**kw):
            if args[0]=='/usr/bin/bwrap':raise FileNotFoundError()
            return original(args,*pos,**kw)
        with mock.patch.object(core.subprocess,'Popen',side_effect=unavailable):
            with self.assertRaises(PlannerError):repository(str(self.repo))

    def test_partial_includes_and_replace_rejected(self):
        self.git('config','include.path','/nonexistent')
        with self.assertRaises(PlannerError):repository(str(self.repo))
        self.git('config','--unset','include.path');self.git('config','remote.origin.promisor','true')
        with self.assertRaises(PlannerError):repository(str(self.repo))

    def test_bare_and_unborn_and_non_repo(self):
        with self.assertRaises(PlannerError):repository(str(self.base))
        empty=self.base/'empty';empty.mkdir();subprocess.run(['/usr/bin/git','init',str(empty)],capture_output=True,check=True,env=self.env)
        snap=repository(str(empty));self.assertIsNone(snap['head'])
        with self.assertRaises(PlannerError):make_plan(snap,None,'0.1.0')
        bare=self.base/'bare';subprocess.run(['/usr/bin/git','init','--bare',str(bare)],capture_output=True,check=True,env=self.env)
        with self.assertRaises(PlannerError):repository(str(bare))

    def test_manual_review_preserves_conflicts_and_requires_reason(self):
        snap,p=self.plan(message='docs: readme')
        with self.assertRaises(PlannerError):review_plan(p,snap,'',' ')
        r=review_plan(p,snap,'1.3.0','人工确认')
        self.assertEqual(r['status'],'needs_review');self.assertIsNone(r['candidateVersion'])
        self.assertTrue(r['manualReview']);self.assertFalse(r['releaseAuthorized'])
        with self.assertRaises(PlannerError):review_plan(p,snap,'1.0.0','理由')

    def test_stale_review_and_export_invalidated(self):
        self.plan();app=App();app.action('open',{'path':str(self.repo)})
        p=app.action('plan',{'confirmed':True,'baseline':'refs/tags/v1.2.3'})['plan']
        self.commit('fix: after')
        with self.assertRaises(PlannerError):app.action('review',{'planFingerprint':p['planFingerprint'],'reason':'r'})
        self.assertIsNone(app.plan)

    def test_export_no_overwrite_or_symlink_or_repository(self):
        snap,p=self.plan();out=self.base/'report.json';safe_export(str(out),report(p,'json'),snap['protected'])
        self.assertEqual(json.loads(out.read_text())['candidateVersion'],'1.2.4')
        with self.assertRaises(PlannerError):safe_export(str(out),'bad',snap['protected'])
        with self.assertRaises(PlannerError):safe_export(str(self.repo/'report.md'),'bad',snap['protected'])
        alias=self.base/'alias';alias.symlink_to(self.base,target_is_directory=True)
        with self.assertRaises(PlannerError):safe_export(str(alias/'other.md'),'bad',snap['protected'])
        link=self.base/'link';link.symlink_to(out)
        with self.assertRaises(PlannerError):safe_export(str(link),'bad',snap['protected'])

    def test_export_directory_move_before_unnamed_file_creation(self):
        outside=self.base/'outside';outside.mkdir();moved=self.repo/'moved'
        original=os.open
        def race(path,flags,*pos,**kw):
            if flags & os.O_TMPFILE==os.O_TMPFILE:outside.rename(moved)
            return original(path,flags,*pos,**kw)
        with mock.patch.object(core.os,'open',side_effect=race):
            with self.assertRaises(PlannerError) as caught:
                safe_export(str(outside/'report.md'),'private report',[str(self.repo)])
        self.assertEqual(caught.exception.code,'export_moved');self.assertEqual(list(moved.iterdir()),[])

    def test_export_directory_move_during_and_after_publication(self):
        for stage in ['link','fsync']:
            with self.subTest(stage=stage):
                outside=self.base/('outside-'+stage);outside.mkdir();moved=self.repo/('moved-'+stage)
                original=getattr(os,stage)
                def race(*pos,**kw):
                    result=original(*pos,**kw)
                    if stage=='link' or core.stat.S_ISDIR(os.fstat(pos[0]).st_mode):outside.rename(moved)
                    return result
                with mock.patch.object(core.os,stage,side_effect=race):
                    with self.assertRaises(PlannerError):
                        safe_export(str(outside/'report.md'),'private report',[str(self.repo)])
                self.assertEqual(list(moved.iterdir()),[])

    def test_export_no_unnamed_file_support_fails_without_named_fallback(self):
        original=os.open
        def unavailable(path,flags,*pos,**kw):
            if flags & os.O_TMPFILE==os.O_TMPFILE:raise OSError('unsupported')
            return original(path,flags,*pos,**kw)
        with mock.patch.object(core.os,'open',side_effect=unavailable):
            with self.assertRaises(PlannerError):safe_export(str(self.base/'out.md'),'data',[str(self.repo)])
        self.assertFalse((self.base/'out.md').exists())
        self.assertFalse(list(self.base.glob('.git-planner-*')))

    def two_plans(self):
        self.git('tag','v1.0.0');self.commit('feat!: first change');self.git('tag','v1.1.0');self.commit('fix: second change')
        app=App();app.action('open',{'path':str(self.repo)})
        a=app.action('plan',{'confirmed':True,'baseline':'refs/tags/v1.0.0'})['plan']
        b=app.action('plan',{'confirmed':True,'baseline':'refs/tags/v1.1.0'})['plan']
        return app,a,b

    def test_preview_export_reject_missing_and_stale_displayed_plan(self):
        app,a,b=self.two_plans();target=self.base/'out.json'
        self.assertEqual(a['candidateVersion'],'2.0.0');self.assertEqual(b['candidateVersion'],'1.1.1')
        for action in ['preview','export']:
            for fingerprint in [None,a['planFingerprint']]:
                with self.subTest(action=action,fingerprint=fingerprint),self.assertRaises(PlannerError):
                    app.action(action,{'format':'json','path':str(target),'planFingerprint':fingerprint})
        self.assertFalse(target.exists())
        result=app.action('preview',{'format':'json','planFingerprint':b['planFingerprint']})
        self.assertEqual(json.loads(result['content'])['candidateVersion'],'1.1.1')

    def test_export_rechecks_plan_after_file_dialog(self):
        app,a,b=self.two_plans();target=self.base/'out.json'
        def dialog(save=False):app.plan=a;return str(target)
        with mock.patch.object(app,'dialog',side_effect=dialog):
            with self.assertRaises(PlannerError):
                app.action('export',{'dialog':True,'format':'json','planFingerprint':b['planFingerprint']})
        self.assertFalse(target.exists())

    def test_markdown_preserves_breaking_footer_details_and_escapes_markup(self):
        _,p=self.plan('1.0.0','fix: API cleanup\n\nBREAKING CHANGE: removed old endpoint\nUse <script>safe()</script> instead.\nMigration: change clients')
        markdown=report(p,'md')
        self.assertEqual(p['candidateVersion'],'2.0.0')
        for expected in ['BREAKING CHANGE','removed old endpoint','Migration: change clients',p['commits'][0]['oid']]:
            self.assertIn(expected,markdown)
        self.assertNotIn('<script>',markdown);self.assertIn('\\<script\\>',markdown)

    def test_http_origin_host_token_and_no_cors(self):
        server=create_server();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def req(headers):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port)
            c.request('POST','/api/state','{}',headers);r=c.getresponse();code=r.status;r.read();c.close();return code
        h={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{server.server_port}','X-Planner-Token':server.token}
        self.assertEqual(req(h),200)
        self.assertEqual(req({**h,'Origin':'https://attacker.example'}),403)
        self.assertEqual(req({**h,'X-Planner-Token':'wrong'}),403)
        self.assertEqual(req({**h,'Host':'attacker.example'}),403)


if __name__=='__main__':unittest.main(verbosity=2)
