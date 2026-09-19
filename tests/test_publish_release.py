"""Tests for scripts/publish_release.py, the tool that uploads a GitHub release.

Deliberately narrow. These cover the three things that are easy to get wrong and that
fail *silently* or in a confusing way when they are wrong:

* ``preflight`` must accept a complete tree. It once appended a blank entry to its
  problem list before testing the list, so the list was never empty and every release
  would have died at ``create`` with a complaint that named no actual problem.
* token resolution must never hand the job to a ``helper-selector`` git. That helper is
  a picker dialog, not a credential store, so calling it unattended blocks forever.
  Nothing here talks to GitHub, and nothing here reads a real token.
* ``publish`` must refuse to flip a draft public when verification failed - that is the
  whole reason the release is a draft until the last step.

The tests never touch the network, never need a git installation, and never depend on
``dist/`` being populated (it is gitignored, so a fresh clone has no assets).
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_publish_release() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "publish_release", ROOT / "scripts" / "publish_release.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublishReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_publish_release()

    # --- version, tag and asset names all come from one place ---------------------

    def test_version_is_read_from_the_constant_the_application_uses(self) -> None:
        # If this drifts, the release is published under a name that does not match the
        # executable's own file version.
        app = (ROOT / "codex_config_tool.py").read_text(encoding="utf-8")
        match = re.search(r'^APP_VERSION = "([^"]+)"$', app, re.MULTILINE)
        self.assertIsNotNone(match, "APP_VERSION not found in codex_config_tool.py")
        self.assertEqual(self.module.read_version(), match.group(1))

    def test_tag_and_asset_names_are_derived_from_the_version(self) -> None:
        with mock.patch.object(self.module, "run_git", return_value="https://github.com/o/r.git"):
            context = self.module.Context()
        self.assertEqual(context.tag, f"v{context.version}")
        self.assertEqual(
            [asset.name for asset in context.assets],
            [
                f"CodexConfigTool-Setup-v{context.version}.exe",
                f"CodexConfigTool-Portable-v{context.version}.exe",
            ],
        )

    def test_repository_is_derived_from_the_git_remote(self) -> None:
        # The repository name is "Codex_ConfigTool" with underscores; the hyphenated
        # form does not exist and 404s. Parsing the remote instead of hardcoding it is
        # what keeps that mistake impossible.
        for url, expected in (
            ("https://github.com/z1099530893/Codex_ConfigTool.git", "z1099530893/Codex_ConfigTool"),
            ("https://github.com/z1099530893/Codex_ConfigTool", "z1099530893/Codex_ConfigTool"),
            ("git@github.com:z1099530893/Codex_ConfigTool.git", "z1099530893/Codex_ConfigTool"),
        ):
            with self.subTest(url=url):
                with mock.patch.object(self.module, "run_git", return_value=url):
                    self.assertEqual(self.module.resolve_repo(), expected)

    # --- preflight -----------------------------------------------------------------

    def test_preflight_accepts_a_complete_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.md"
            notes.write_text("x", encoding="utf-8")
            asset = Path(tmp) / "asset.exe"
            asset.write_bytes(b"x")
            context = types.SimpleNamespace(notes=notes, assets=[asset])
            self.module.preflight(context)  # must not raise

    def test_preflight_names_only_the_files_that_are_actually_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.md"
            notes.write_text("x", encoding="utf-8")
            context = types.SimpleNamespace(
                notes=notes, assets=[Path(tmp) / "CodexConfigTool-Setup-v0.0.0.exe"]
            )
            with self.assertRaises(SystemExit) as caught:
                self.module.preflight(context)
            message = str(caught.exception)
            self.assertIn("CodexConfigTool-Setup-v0.0.0.exe", message)
            self.assertNotIn("notes.md", message)

    # --- token resolution ----------------------------------------------------------

    def test_environment_token_wins_and_git_is_not_consulted(self) -> None:
        with mock.patch.dict(os.environ, {"GH_TOKEN": "from-env"}), mock.patch.object(
            self.module, "git_candidates", side_effect=AssertionError("git must not be consulted")
        ):
            self.assertEqual(self.module.resolve_token(), "from-env")

    def test_token_resolution_never_invokes_a_helper_selector_git(self) -> None:
        selector_git = r"C:\portable\git.exe"
        manager_git = r"C:\Program Files\Git\cmd\git.exe"

        def fake_helper(git: str) -> str:
            return "helper-selector" if git == selector_git else "manager"

        invoked: list[str] = []

        def fake_run(command, **_kwargs):
            invoked.append(command[0])
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=b"protocol=https\nhost=github.com\nusername=x\npassword=token-abc\n",
                stderr=b"",
            )

        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(
            self.module, "git_candidates", return_value=[selector_git, manager_git]
        ), mock.patch.object(
            self.module, "credential_helper", side_effect=fake_helper
        ), mock.patch.object(
            self.module, "subprocess", types.SimpleNamespace(run=fake_run)
        ):
            os.environ.pop("GH_TOKEN", None)
            os.environ.pop("GITHUB_TOKEN", None)
            token = self.module.resolve_token()

        self.assertEqual(token, "token-abc")
        self.assertNotIn(selector_git, invoked, "the picker helper must be skipped, not called")
        self.assertEqual(invoked, [manager_git])

    def test_missing_token_is_an_explicit_failure(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(
            self.module, "git_candidates", return_value=[]
        ):
            os.environ.pop("GH_TOKEN", None)
            os.environ.pop("GITHUB_TOKEN", None)
            with self.assertRaises(SystemExit) as caught:
                self.module.resolve_token()
        self.assertIn("No GitHub token", str(caught.exception))

    # --- the publish invariant -----------------------------------------------------

    def test_publish_refuses_when_verification_fails(self) -> None:
        context = mock.Mock()
        context.release_by_tag.return_value = {"id": 1, "html_url": "https://example.invalid"}
        with mock.patch.object(self.module, "cmd_verify", return_value=1):
            with self.assertRaises(SystemExit) as caught:
                self.module.cmd_publish(context)
        self.assertIn("not publishing", str(caught.exception))
        # The PATCH that would make the draft public must never be sent.
        context.call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
