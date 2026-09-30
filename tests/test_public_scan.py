import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.scan_public import private_values_from_file, scan, scan_blob


class PublicScanTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Example contributor")
        self.git("config", "user.email", "123+example@users.noreply.github.com")

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", f"safe.directory={self.root.as_posix()}", *args],
            cwd=self.root, capture_output=True, check=True,
        )

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-m", "Synthetic scan fixture")

    def test_clean_root_has_no_findings(self):
        (self.root / "app.py").write_text("print('example')\n")
        self.commit()
        self.assertEqual(scan(root=self.root)["findings"], [])

    def test_deleted_runtime_file_is_still_found_in_history(self):
        (self.root / "app.py").write_text("{}")
        # Identical blob at two paths must not hide its historical private filename.
        (self.root / "credentials.json").write_text("{}")
        self.commit()
        (self.root / "credentials.json").unlink()
        self.commit()
        result = scan(root=self.root)
        self.assertTrue(any("credentials.json" in item["file"] for item in result["findings"]))
        self.assertEqual(scan(history=False, root=self.root)["findings"], [])

    def test_known_value_in_binary_and_filename_is_not_printed(self):
        secret = "private" * 6
        (self.root / (secret + ".bin")).write_bytes(b"\0" + secret.encode())
        result = scan(history=False, root=self.root, private_values={secret})
        self.assertEqual(result["findings"][0]["kind"], "known private value")
        self.assertNotIn(secret, json.dumps(result))

    def test_commit_message_and_personal_email_are_scanned(self):
        secret = "confidential" * 4
        (self.root / "app.py").write_text("pass")
        self.git("config", "user.email", "example@example.invalid")
        self.git("add", "app.py")
        self.git("commit", "-m", secret)
        result = scan(root=self.root, private_values={secret})
        kinds = {item["kind"] for item in result["findings"]}
        self.assertIn("known private value", kinds)
        self.assertIn("personal author email", kinds)
        self.assertNotIn(secret, json.dumps(result))

    def test_private_file_collects_encoded_values_without_writing(self):
        path = self.root / "local.json"
        raw = json.dumps({"SESSDATA": "private%2C" * 4, "qr_login_context": {
            "cookies": {"DedeUserID": "1234567890", "buvid3": "device" * 6}}})
        path.write_text(raw)
        values = private_values_from_file(path)
        self.assertIn("private," * 4, values)
        self.assertIn("1234567890", values)
        self.assertIn("device" * 6, values)
        self.assertEqual(path.read_text(), raw)

    def test_cookie_literal_and_profile_path_report_only_location(self):
        findings = []
        content = "Cookie: SESSDATA=" + "s" * 32
        content += "\n" + "C:" + "/Users/" + "example/local.txt"
        scan_blob(content.encode(), "fixture.txt", findings)
        self.assertEqual({item["kind"] for item in findings}, {
            "session literal", "personal filesystem path"})
        self.assertNotIn("s" * 32, json.dumps(findings))


if __name__ == "__main__":
    unittest.main()
