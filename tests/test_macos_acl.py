"""Isolated macOS ACL regressions; --work-root is required.

Mocked API results are labelled simulations. Native cases run only on macOS,
using newly created fixture files; no real user data or permissions are changed.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import errno
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--work-root", required=True)
opts, remaining = parser.parse_known_args()
BASE = Path(opts.work_root).absolute()
BASE.mkdir(parents=True, exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix="macos-acl-tests-", dir=BASE))
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import storage_guard as G
import relocation_guard as R


class SimulatedDarwin:
    """Controlled native return values, not an ownership or platform proof."""
    def __init__(self, error=errno.ENOENT, body=None, during_acl=None, xattrs=0):
        self.error = error
        self.body = body
        self.during_acl = during_acl
        self.xattrs = xattrs
        self.acl_calls = 0
        self.frees = 0

    def listxattr(self, path, out, size, options):
        return self.xattrs

    def acl_get_link_np(self, path, kind):
        self.acl_calls += 1
        if self.during_acl:
            self.during_acl()
        if self.error is not None:
            ctypes.set_errno(self.error)
        return 1234 if self.body is not None else None

    def acl_size(self, acl):
        return len(self.body)

    def acl_copy_ext(self, out, acl, size):
        ctypes.memmove(out, self.body, len(self.body))
        return len(self.body)

    def acl_free(self, acl):
        self.frees += 1
        return 0


class MacAclTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.file = self.area / "ordinary.bin"
        self.file.write_bytes(b"retained fictional input")
        self.directory = self.area / "ordinary-directory"
        self.directory.mkdir()

    def inspect(self, path=None, **options):
        api = SimulatedDarwin(**options)
        with mock.patch.object(R, "DARWIN", api):
            value = R.darwin_metadata(path or self.file)
        return value, api

    def test_simulated_present_file_enoent_is_verified_absent_acl(self):
        before = self.file.read_bytes(), G.fingerprint(self.file.stat())
        value, api = self.inspect()
        self.assertEqual(value, "")
        self.assertEqual(api.acl_calls, 1)
        self.assertEqual((self.file.read_bytes(), G.fingerprint(self.file.stat())), before)

    def test_simulated_present_directory_enoent_is_verified_absent_acl(self):
        value, api = self.inspect(self.directory)
        self.assertEqual(value, "")
        self.assertEqual(api.acl_calls, 1)
        self.assertTrue(self.directory.is_dir())

    def test_missing_object_rejected_before_native_call(self):
        api = SimulatedDarwin()
        with mock.patch.object(R, "DARWIN", api), self.assertRaises(FileNotFoundError):
            R.darwin_metadata(self.area / "missing")
        self.assertEqual(api.acl_calls, 0)

    def test_disappearance_during_native_call_is_not_absent_acl(self):
        with self.assertRaises(FileNotFoundError):
            self.inspect(during_acl=self.file.unlink)

    def test_replacement_during_native_call_is_rejected(self):
        replacement = self.area / "replacement.bin"
        replacement.write_bytes(self.file.read_bytes())
        before = self.file.stat()
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertNotEqual((replacement.stat().st_dev, replacement.stat().st_ino),
                            (before.st_dev, before.st_ino))
        with self.assertRaises(G.GuardError):
            self.inspect(during_acl=lambda: os.replace(replacement, self.file))

    def test_metadata_drift_during_native_call_is_rejected(self):
        before = self.file.stat()
        def change():
            os.utime(self.file, ns=(before.st_atime_ns, before.st_mtime_ns + 4_000_000_000))
        with self.assertRaises(G.GuardError):
            self.inspect(during_acl=change)

    def test_simulated_nonordinary_object_rejected_before_native_call(self):
        api = SimulatedDarwin()
        for mode in (stat.S_IFIFO, stat.S_IFSOCK):
            with self.subTest(mode=mode), mock.patch.object(R, "DARWIN", api), \
                    mock.patch.object(G, "plain", return_value=types.SimpleNamespace(st_mode=mode)), \
                    self.assertRaises(G.GuardError):
                R.darwin_metadata(self.file)
        self.assertEqual(api.acl_calls, 0)

    def test_native_permission_io_invalid_errors_remain_errors(self):
        for code in (errno.EACCES, errno.EIO, errno.EINVAL):
            with self.subTest(errno=code), self.assertRaises(OSError) as caught:
                self.inspect(error=code)
            self.assertEqual(caught.exception.errno, code)
        self.assertTrue(self.file.exists())

    def test_unsupported_acl_remains_unknown(self):
        value, _ = self.inspect(error=errno.ENOTSUP)
        self.assertIsNone(value)

    def test_stale_enoent_is_cleared_before_native_call(self):
        ctypes.set_errno(errno.ENOENT)
        with self.assertRaises(OSError) as caught:
            self.inspect(error=None)
        self.assertEqual(caught.exception.errno, 0)

    def test_nonempty_acl_bytes_are_serialized_and_differences_preserved(self):
        a, api_a = self.inspect(body=b"simulated-native-acl-A", error=0)
        b, api_b = self.inspect(body=b"simulated-native-acl-B", error=0)
        self.assertEqual(base64.b64decode(a), b"simulated-native-acl-A")
        self.assertEqual(base64.b64decode(b), b"simulated-native-acl-B")
        self.assertNotEqual(a, b)
        self.assertEqual((api_a.frees, api_b.frees), (1, 1))
        source = {"directories": {"": {"metadata": {"darwin_acl": a}, "mtime_ns": 1}}, "files": {}}
        target = {"directories": {"": {"metadata": {"darwin_acl": b}, "mtime_ns": 1}}, "files": {}}
        with self.assertRaises(G.GuardError):
            R.same_copy(source, target, "preserve")

    def test_unknown_acl_still_refused_by_preserve(self):
        source = {"directories": {"": {"metadata": {"darwin_acl": None}, "mtime_ns": 1}}, "files": {}}
        with self.assertRaises(G.GuardError):
            R.same_copy(source, source, "preserve")

    def test_xattrs_still_refused_before_acl_call(self):
        api = SimulatedDarwin(xattrs=12)
        with mock.patch.object(R, "DARWIN", api), self.assertRaises(G.GuardError):
            R.darwin_metadata(self.file)
        self.assertEqual(api.acl_calls, 0)

    @unittest.skipUnless(sys.platform == "darwin", "Native Apple ACL API requires macOS")
    def test_native_new_file_and_directory_metadata(self):
        with mock.patch.object(R, "DARWIN", None):
            file_meta = R.metadata(self.file)
            dir_meta = R.metadata(self.directory, directory=True)
        self.assertIsInstance(file_meta, dict)
        self.assertIsInstance(file_meta["darwin_acl"], str)
        self.assertIsInstance(dir_meta["darwin_acl"], str)
        self.assertTrue(self.file.exists() and self.directory.is_dir())

    @unittest.skipUnless(sys.platform == "darwin", "Native ACL fixture requires macOS chmod")
    def test_native_nonempty_acl_is_captured(self):
        # Only this newly-created fixture receives an ordinary read ACL.
        with mock.patch.object(R, "DARWIN", None):
            before = R.metadata(self.file)
            subprocess.run(["/bin/chmod", "+a", "everyone allow read", str(self.file)],
                           check=True, capture_output=True)
            after = R.metadata(self.file)
        self.assertIsInstance(after["darwin_acl"], str)
        self.assertTrue(after["darwin_acl"])
        self.assertNotEqual(before["darwin_acl"], after["darwin_acl"])
        self.assertEqual(self.file.read_bytes(), b"retained fictional input")


if __name__ == "__main__":
    print("Isolated evidence directory:", RUN, flush=True)
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
