"""Exercise the exact Git operations used by the AutoIt helper in disposable repos."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

OPTIONS = ['--no-pager', '-c', 'color.ui=false', '-c', 'core.quotepath=false', '-c', 'apply.ignoreWhitespace=no']
ENV = os.environ.copy()
for k in list(ENV):
    if k.startswith('GIT_'):
        ENV.pop(k)
ENV.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')

def git(root, *args, check=True):
    p = subprocess.run(['git', *OPTIONS, '-C', str(root), *args], env=ENV, capture_output=True)
    if check and p.returncode:
        raise AssertionError(f'{args}: {p.stderr!r}')
    return p

class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='Patch to Repo Ä & 100% ! ')
        self.base = Path(self.tmp.name)
        self.repo = self.base / 'répo with spaces & symbols'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.name', 'Fixture')
        git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        (self.repo/'a.txt').write_bytes(b'alpha\nbeta\ngamma\n')
        (self.repo/'b.txt').write_bytes(b'one\ntwo\nthree\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'base')
        self.patch = self.base/'update ä & 100% !.patch'
        self.index = (self.repo/'.git/index').read_bytes()
    def tearDown(self): self.tmp.cleanup()
    def capture(self):
        self.patch.write_bytes(git(self.repo, 'diff', '--binary', '--full-index', 'HEAD').stdout)
        git(self.repo, 'reset', '--hard', '-q', 'HEAD')
        git(self.repo, 'clean', '-fdq')
    def text_patch(self):
        (self.repo/'a.txt').write_bytes(b'alpha\nBETA\ngamma\n')
        self.capture()
    def apply(self, *flags, check=False):
        return git(self.repo, 'apply', '--whitespace=warn', *flags, '--', str(self.patch), check=check)
    def test_check_is_read_only_and_apply_leaves_index(self):
        self.text_patch()
        self.index = (self.repo/'.git/index').read_bytes()
        before=(self.repo/'a.txt').read_bytes()
        self.assertEqual(self.apply('--check').returncode,0)
        self.assertEqual((self.repo/'a.txt').read_bytes(),before)
        self.assertIn(b'1 file changed',self.apply('--stat','--summary').stdout)
        self.assertEqual(self.apply('--verbose').returncode,0)
        self.assertIn(b'BETA',(self.repo/'a.txt').read_bytes())
        self.assertEqual((self.repo/'.git/index').read_bytes(),self.index)
        self.assertEqual(git(self.repo,'rev-list','--count','HEAD').stdout.strip(),b'1')
    def test_already_applied_reverse_diagnostic(self):
        self.text_patch();self.apply(check=True)
        self.assertNotEqual(self.apply('--check').returncode,0)
        self.assertEqual(self.apply('--reverse','--check').returncode,0)
        self.assertIn(b'BETA',(self.repo/'a.txt').read_bytes())
    def test_wrong_repository(self):
        self.text_patch()
        other=self.base/'other';other.mkdir();git(other,'init','-q')
        p=git(other,'apply','--whitespace=warn','--check','--',str(self.patch),check=False)
        self.assertNotEqual(p.returncode,0)
        self.assertFalse((other/'a.txt').exists())
    def test_conflict_does_not_apply_other_file(self):
        (self.repo/'a.txt').write_bytes(b'alpha\nBETA\ngamma\n')
        (self.repo/'b.txt').write_bytes(b'one\nTWO\nthree\n')
        self.capture()
        (self.repo/'b.txt').write_bytes(b'local rewrite\n')
        before={p.name:p.read_bytes() for p in self.repo.glob('*.txt')}
        self.assertNotEqual(self.apply('--check').returncode,0)
        self.assertNotEqual(self.apply().returncode,0)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.repo.glob('*.txt')})
        self.assertFalse(list(self.repo.glob('*.rej')))
    def test_local_unrelated_edit_survives(self):
        self.text_patch();(self.repo/'b.txt').write_bytes(b'my draft\n')
        self.apply('--check',check=True);self.apply(check=True)
        self.assertEqual((self.repo/'b.txt').read_bytes(),b'my draft\n')
    def test_untracked_addition_not_overwritten(self):
        (self.repo/'new.txt').write_bytes(b'new\n');git(self.repo,'add','new.txt');self.capture()
        (self.repo/'new.txt').write_bytes(b'local\n')
        self.assertNotEqual(self.apply('--check').returncode,0)
        self.assertEqual((self.repo/'new.txt').read_bytes(),b'local\n')
    def test_binary(self):
        data=bytes(range(256))*5
        (self.repo/'asset.bin').write_bytes(data);git(self.repo,'add','asset.bin');self.capture()
        self.apply('--check',check=True);self.apply(check=True)
        self.assertEqual((self.repo/'asset.bin').read_bytes(),data)
    def test_rename_delete_and_add(self):
        (self.repo/'a.txt').rename(self.repo/'renamed.txt')
        (self.repo/'b.txt').unlink()
        (self.repo/'new.txt').write_bytes(b'added\n')
        git(self.repo,'add','-A');self.capture()
        self.apply('--check',check=True);self.apply(check=True)
        self.assertEqual((self.repo/'renamed.txt').read_bytes(),b'alpha\nbeta\ngamma\n')
        self.assertFalse((self.repo/'a.txt').exists())
        self.assertFalse((self.repo/'b.txt').exists())
        self.assertTrue((self.repo/'new.txt').exists())
    def test_subfolder_and_linked_worktree_roots(self):
        folder=self.repo/'nested';folder.mkdir()
        self.assertEqual(Path(git(folder,'rev-parse','--show-toplevel').stdout.rstrip().decode()).resolve(),self.repo.resolve())
        linked=self.base/'linked';git(self.repo,'worktree','add','-qb','linked',str(linked))
        self.assertTrue((linked/'.git').is_file())
        self.assertEqual(git(linked,'rev-parse','--is-inside-work-tree').stdout.strip(),b'true')
        self.assertEqual(Path(git(linked,'rev-parse','--show-toplevel').stdout.rstrip().decode()).resolve(),linked.resolve())
    def test_bare_repository_rejected(self):
        bare=self.base/'bare';bare.mkdir();git(bare,'init','--bare','-q')
        self.assertEqual(git(bare,'rev-parse','--is-inside-work-tree').stdout.strip(),b'false')
    def test_unmerged_state_detected(self):
        git(self.repo,'checkout','-qb','side')
        (self.repo/'a.txt').write_bytes(b'side\n');git(self.repo,'commit','-qam','side')
        git(self.repo,'checkout','-q','-')
        (self.repo/'a.txt').write_bytes(b'main\n');git(self.repo,'commit','-qam','main')
        self.assertNotEqual(git(self.repo,'merge','side',check=False).returncode,0)
        self.assertTrue(git(self.repo,'ls-files','--unmerged').stdout)
    def test_traversal_rejected(self):
        self.patch.write_bytes(b'diff --git a/../escaped.txt b/../escaped.txt\nnew file mode 100644\n--- /dev/null\n+++ b/../escaped.txt\n@@ -0,0 +1 @@\n+escape\n')
        self.assertNotEqual(self.apply('--check').returncode,0)
        self.assertFalse((self.base/'escaped.txt').exists())
    def test_recheck_after_previous_check(self):
        self.text_patch();self.apply('--check',check=True)
        (self.repo/'a.txt').write_bytes(b'changed since check\n')
        self.assertNotEqual(self.apply('--check').returncode,0)
        self.assertNotEqual(self.apply().returncode,0)
        self.assertEqual((self.repo/'a.txt').read_bytes(),b'changed since check\n')
    def test_crlf_checkout(self):
        git(self.repo,'config','core.autocrlf','true')
        for p in self.repo.glob('*.txt'):p.unlink()
        git(self.repo,'checkout','--','.')
        self.assertIn(b'\r\n',(self.repo/'a.txt').read_bytes())
        (self.repo/'a.txt').write_bytes(b'alpha\r\nBETA\r\ngamma\r\n')
        self.capture();self.apply('--check',check=True);self.apply(check=True)
        self.assertEqual((self.repo/'a.txt').read_bytes(),b'alpha\r\nBETA\r\ngamma\r\n')
    def test_whitespace_warning_does_not_rewrite_patch(self):
        (self.repo/'a.txt').write_bytes(b'alpha\nbeta  \ngamma\n');self.capture()
        self.apply('--check',check=True);self.apply(check=True)
        self.assertEqual((self.repo/'a.txt').read_bytes(),b'alpha\nbeta  \ngamma\n')
    def test_snapshot_unchanged_when_original_replaced(self):
        self.text_patch();snapshot=self.base/'snapshot.patch';shutil.copyfile(self.patch,snapshot)
        self.patch.write_bytes(b'not a patch')
        git(self.repo,'apply','--whitespace=warn','--check','--',str(snapshot))
        git(self.repo,'apply','--whitespace=warn','--',str(snapshot))
        self.assertIn(b'BETA',(self.repo/'a.txt').read_bytes())
    def test_submodule_noop_requires_explicit_rejection(self):
        patch=(b'diff --git a/module b/module\nindex '+b'1'*40+b'..'+b'2'*40+b' 160000\n--- a/module\n+++ b/module\n@@ -1 +1 @@\n-Subproject commit '+b'1'*40+b'\n+Subproject commit '+b'2'*40+b'\n')
        self.patch.write_bytes(patch);(self.repo/'module').mkdir()
        self.assertEqual(self.apply('--check').returncode,0)
        self.assertEqual(self.apply().returncode,0)
        pattern=rb'^(?:index [0-9a-fA-F]+\.\.[0-9a-fA-F]+ |(?:new file|deleted file|old|new) mode )160000$'
        self.assertTrue(re.search(pattern,patch,re.M))

    def repeated_context_fixture(self, second='OLD'):
        old='aa\nbb\ncc\nOLD\ndd\nee\nff\n'
        (self.repo/'repeat.txt').write_text('padding\n'+old+old.replace('OLD',second)+'ending\n')
        self.patch.write_text('diff --git a/repeat.txt b/repeat.txt\n--- a/repeat.txt\n+++ b/repeat.txt\n@@ -2,7 +2,7 @@\n aa\n bb\n cc\n-OLD\n+NEW\n dd\n ee\n ff\n')

    def test_repeated_context_can_pass_both_checks_after_apply(self):
        self.repeated_context_fixture()
        self.assertEqual(self.apply('--check').returncode,0)
        self.assertNotEqual(self.apply('--reverse','--check').returncode,0)
        self.apply(check=True)
        before=(self.repo/'repeat.txt').read_bytes()
        self.assertEqual(before.count(b'NEW'),1)
        self.assertEqual(self.apply('--check').returncode,0)
        self.assertEqual(self.apply('--reverse','--check').returncode,0)
        self.assertEqual((self.repo/'repeat.txt').read_bytes(),before)
        # Demonstrates why a forward-only preflight is insufficient: raw Git
        # accepts the retry at an offset and changes the second matching block.
        self.apply(check=True)
        self.assertEqual((self.repo/'repeat.txt').read_bytes().count(b'NEW'),2)

    def test_bidirectional_check_is_ambiguity_not_proof_of_prior_apply(self):
        self.repeated_context_fixture(second='NEW')
        before=(self.repo/'repeat.txt').read_bytes()
        self.assertEqual(self.apply('--check').returncode,0)
        self.assertEqual(self.apply('--reverse','--check').returncode,0)
        self.assertEqual((self.repo/'repeat.txt').read_bytes(),before)

    def test_valid_end_of_file_addition_remains_unambiguous(self):
        self.patch.write_text('diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1,3 +1,4 @@\n alpha\n beta\n gamma\n+new entry\n')
        self.assertEqual(self.apply('--check').returncode,0)
        self.assertNotEqual(self.apply('--reverse','--check').returncode,0)
        self.apply(check=True)
        self.assertNotEqual(self.apply('--check').returncode,0)
        self.assertEqual(self.apply('--reverse','--check').returncode,0)
        self.assertEqual((self.repo/'a.txt').read_bytes().count(b'new entry'),1)

if __name__=='__main__':unittest.main(verbosity=2)
