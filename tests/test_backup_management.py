import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import codex_config_tool as app


class BackupManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config_dir = self.root / "codex"
        settings_dir = self.root / "settings"
        self.settings_dir_patch = patch.object(app, "SETTINGS_DIR", settings_dir)
        self.settings_file_patch = patch.object(app, "SETTINGS_FILE", settings_dir / "settings.json")
        self.settings_dir_patch.start()
        self.settings_file_patch.start()
        app.clear_profile_cache()

    def tearDown(self) -> None:
        app.clear_profile_cache()
        self.settings_file_patch.stop()
        self.settings_dir_patch.stop()
        self.temp_dir.cleanup()

    def test_security_validation_rejects_conflicting_permission_keys(self) -> None:
        issues = app.validate_config_security(
            'model = "gpt-test"\n'
            'default_permissions = "ask"\n'
            'sandbox_mode = "workspace-write"\n'
        )
        self.assertTrue(any("同时设置了" in issue for issue in issues))

    def test_security_validation_rejects_invalid_toml(self) -> None:
        issues = app.validate_config_security("model = [\n")
        self.assertTrue(any("语法无效" in issue for issue in issues))

    def test_security_validation_detects_duplicate_project_paths(self) -> None:
        project = self.root / "Project"
        duplicate = str(project).replace("\\", "/")
        config = (
            f"[projects.{app.quote_toml_string(str(project))}]\ntrust_level = \"trusted\"\n\n"
            f"[projects.{app.quote_toml_string(duplicate)}]\ntrust_level = \"trusted\"\n"
        )
        issues = app.validate_config_security(config)
        self.assertTrue(any("指向同一位置" in issue for issue in issues))

    def test_redact_sensitive_text_hides_api_key(self) -> None:
        self.assertEqual("请求失败：***", app.redact_sensitive_text("请求失败：secret-key", ("secret-key",)))

    def test_release_parser_detects_newer_semantic_version(self) -> None:
        release_url = f"{app.PROJECT_URL}/releases/tag/v1.5.0"
        update = app.parse_latest_release_url(release_url, current_version="1.4.0")
        self.assertEqual("1.5.0", update.version)
        self.assertEqual(release_url, update.page_url)
        self.assertIsNone(app.parse_latest_release_url(release_url, current_version="1.5.0"))

    def test_release_parser_rejects_invalid_version(self) -> None:
        invalid_urls = (
            "https://example.com/z1099530893/Codex_ConfigTool/releases/tag/v1.5.0",
            "http://github.com/z1099530893/Codex_ConfigTool/releases/tag/v1.5.0",
            "https://github.com/other/Codex_ConfigTool/releases/tag/v1.5.0",
            f"{app.PROJECT_URL}/releases/tag/latest",
        )
        for release_url in invalid_urls:
            with self.subTest(release_url=release_url), self.assertRaises(app.UpdateCheckError):
                app.parse_latest_release_url(release_url)

    def test_fetch_latest_release_reads_github_release_redirect_without_page_download(self) -> None:
        calls = {}

        class Opener:
            def open(self, request, timeout):
                calls["url"] = request.full_url
                calls["method"] = request.get_method()
                calls["timeout"] = timeout
                calls["accept"] = request.get_header("Accept")
                raise app.urllib.error.HTTPError(
                    request.full_url,
                    302,
                    "Found",
                    {"Location": f"{app.PROJECT_URL}/releases/tag/v1.5.0"},
                    None,
                )

        with patch.object(app.urllib.request, "build_opener", return_value=Opener()) as builder:
            update = app.fetch_latest_release(timeout=2.5)

        self.assertEqual("1.5.0", update.version)
        self.assertEqual(app.LATEST_RELEASE_PAGE_URL, calls["url"])
        self.assertEqual("HEAD", calls["method"])
        self.assertEqual(2.5, calls["timeout"])
        self.assertEqual("text/html", calls["accept"])
        self.assertIsInstance(builder.call_args.args[0], app._NoRedirectHandler)

    def test_classify_config_rejects_permission_conflict(self) -> None:
        self.config_dir.mkdir(parents=True)
        (self.config_dir / "config.toml").write_text(
            'model = "gpt-test"\n'
            'model_provider = "custom"\n'
            'default_permissions = "ask"\n'
            'sandbox_mode = "workspace-write"\n'
            '\n[model_providers.custom]\n'
            'name = "Custom"\n'
            'base_url = "https://provider.example.com/v1"\n',
            encoding="utf-8",
        )
        state, issues = app.classify_config_for_editing(self.config_dir)
        self.assertEqual("conflict", state)
        self.assertTrue(any("同时设置了" in issue for issue in issues))

    def test_model_update_rejects_unsafe_permission_config(self) -> None:
        config_path = self.config_dir / "config.toml"
        config_path.parent.mkdir(parents=True)
        original = 'model = "old"\nsandbox_mode = "danger-full-access"\n'
        config_path.write_text(original, encoding="utf-8")
        with self.assertRaises(app.ConfigConflictError):
            app.update_config_model(config_path, "new")
        self.assertEqual(original, config_path.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "nt", "Windows named mutex test")
    def test_single_instance_mutex_rejects_duplicate_and_releases(self) -> None:
        name = f"Local\\CodexConfigTool-Test-{os.getpid()}-{id(self)}"
        first = app.acquire_single_instance(name)
        self.assertIsNotNone(first)
        try:
            self.assertIsNone(app.acquire_single_instance(name))
        finally:
            app.release_single_instance(first)
        second = app.acquire_single_instance(name)
        self.assertIsNotNone(second)
        app.release_single_instance(second)

    def test_appwindow_registration_notifies_shell_and_restores_window(self) -> None:
        calls = []

        class User32:
            def GetWindowLongW(self, hwnd, index):
                return 0x00000080 if index == -20 else 0

            def SetWindowLongW(self, hwnd, index, value):
                calls.append(("style", hwnd, index, value))

            def SetWindowPos(self, hwnd, *_args):
                calls.append(("position", hwnd, _args[-1]))

        app.register_appwindow_with_shell(42, User32())

        self.assertIn(("style", 42, -20, 0x00040000), calls)
        self.assertIn(("position", 42, 0x0027), calls)

    def test_codex_restart_target_uses_packaged_root_process(self) -> None:
        package_root = Path(
            r"C:\Program Files\WindowsApps\OpenAI.Codex_26.814.5517.0_x64__2p2nqsd0c76g0\app"
        )
        processes = [
            app.ProcessRecord(100, 50, package_root / "ChatGPT.exe"),
            app.ProcessRecord(101, 100, package_root / "ChatGPT.exe"),
            app.ProcessRecord(102, 100, package_root / "resources" / "codex.exe"),
        ]

        target = app.codex_restart_target(processes)

        self.assertIsNotNone(target)
        self.assertEqual(100, target.root_pid)
        self.assertEqual("OpenAI.Codex_2p2nqsd0c76g0!App", target.app_user_model_id)

    def test_codex_restart_target_ignores_unrelated_chatgpt_and_cli(self) -> None:
        processes = [
            app.ProcessRecord(100, 50, Path(r"C:\Program Files\WindowsApps\OpenAI.ChatGPT_1.0_x64__abc\app\ChatGPT.exe")),
            app.ProcessRecord(200, 50, Path(r"C:\Tools\codex.exe")),
        ]

        self.assertIsNone(app.codex_restart_target(processes))

    def test_codex_restart_target_supports_regular_desktop_install(self) -> None:
        executable = Path(r"C:\Users\Tester\AppData\Local\Programs\Codex\Codex.exe")

        target = app.codex_restart_target([app.ProcessRecord(300, 50, executable)])

        self.assertIsNotNone(target)
        self.assertEqual(executable, target.executable)
        self.assertIsNone(target.app_user_model_id)

    def test_codex_app_process_ids_excludes_packaged_cli_children(self) -> None:
        target = app.CodexRestartTarget(
            root_pid=100,
            executable=Path(r"C:\Program Files\WindowsApps\OpenAI.Codex_1.0_x64__publisher\app\ChatGPT.exe"),
            app_user_model_id="OpenAI.Codex_publisher!App",
        )
        processes = [
            app.ProcessRecord(100, 50, target.executable),
            app.ProcessRecord(101, 100, target.executable.parent / "Codex.exe"),
            app.ProcessRecord(102, 100, Path(r"C:\Users\Tester\AppData\Local\OpenAI\Codex\bin\codex.exe")),
            app.ProcessRecord(200, 50, Path(r"C:\Other\ChatGPT.exe")),
        ]

        self.assertEqual({100, 101}, app.codex_app_process_ids(processes, target))

    def test_wait_for_codex_app_exit_rechecks_packaged_host_processes(self) -> None:
        target = app.CodexRestartTarget(
            root_pid=100,
            executable=Path(r"C:\Program Files\WindowsApps\OpenAI.Codex_1.0_x64__publisher\app\ChatGPT.exe"),
            app_user_model_id="OpenAI.Codex_publisher!App",
        )
        running = [app.ProcessRecord(100, 50, target.executable)]
        with (
            patch.object(app, "list_windows_processes", side_effect=[running, []]),
            patch.object(app.time, "sleep"),
        ):
            self.assertTrue(app.wait_for_codex_app_exit(target, timeout=1.0))

    @unittest.skipUnless(os.name == "nt", "Windows Codex launch test")
    def test_codex_launch_starts_store_app_when_not_running(self) -> None:
        target = app.CodexRestartTarget(
            root_pid=0,
            executable=Path(),
            app_user_model_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        )
        with (
            patch.object(app, "list_windows_processes", return_value=[]),
            patch.object(app, "discover_codex_installation", return_value=target),
            patch.object(app, "activate_codex_window", return_value=True),
            patch.object(app.subprocess, "Popen") as popen,
        ):
            result = app.restart_codex_application()

        self.assertEqual("start", result.action)
        popen.assert_called_once_with(
            ["explorer.exe", "shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App"],
            close_fds=True,
        )

    @unittest.skipUnless(os.name == "nt", "Windows Codex restart test")
    def test_codex_restart_waits_for_normal_exit_before_launching(self) -> None:
        target = app.CodexRestartTarget(root_pid=100, executable=Path(r"C:\Codex\Codex.exe"))
        processes = [app.ProcessRecord(100, 50, target.executable)]
        with (
            patch.object(app, "list_windows_processes", return_value=processes),
            patch.object(app, "request_windows_close", return_value=1) as request_close,
            patch.object(app, "wait_for_processes_exit", return_value=True) as wait_exit,
            patch.object(app, "wait_for_codex_app_exit", return_value=True) as wait_app_exit,
            patch.object(app, "activate_codex_window", return_value=True),
            patch.object(app.time, "sleep") as sleep,
            patch.object(app.subprocess, "Popen") as popen,
            patch.object(app.subprocess, "run") as run,
        ):
            result = app.restart_codex_application()

        self.assertEqual("restart", result.action)
        request_close.assert_called_once_with({100})
        wait_exit.assert_called_once_with({100}, 8.0)
        wait_app_exit.assert_called_once_with(target)
        sleep.assert_called_once_with(app.CODEX_TRAY_SHELL_SETTLE_SECONDS)
        run.assert_not_called()
        popen.assert_called_once_with(
            [str(target.executable)],
            close_fds=True,
            creationflags=(
                getattr(app.subprocess, "DETACHED_PROCESS", 0)
                | getattr(app.subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            ),
        )

    @unittest.skipUnless(os.name == "nt", "Windows Codex restart test")
    def test_codex_restart_does_not_relaunch_while_host_process_remains(self) -> None:
        target = app.CodexRestartTarget(root_pid=100, executable=Path(r"C:\Codex\Codex.exe"))
        processes = [app.ProcessRecord(100, 50, target.executable)]
        with (
            patch.object(app, "list_windows_processes", return_value=processes),
            patch.object(app, "request_windows_close", return_value=1),
            patch.object(app, "wait_for_processes_exit", return_value=True),
            patch.object(app, "wait_for_codex_app_exit", return_value=False),
            patch.object(app.subprocess, "Popen") as popen,
        ):
            with self.assertRaises(app.CodexRestartError):
                app.restart_codex_application()

        popen.assert_not_called()

    def test_process_tree_ids_include_nested_codex_children_only(self) -> None:
        processes = [
            app.ProcessRecord(100, 50, Path(r"C:\Codex\ChatGPT.exe")),
            app.ProcessRecord(101, 100, Path(r"C:\Codex\ChatGPT.exe")),
            app.ProcessRecord(102, 101, Path(r"C:\Codex\resources\codex.exe")),
            app.ProcessRecord(200, 50, Path(r"C:\Other\ChatGPT.exe")),
        ]

        self.assertEqual({100, 101, 102}, app.process_tree_ids(processes, 100))

    def write_config(
        self,
        config_dir: Path,
        provider: str,
        base_url: str | None = None,
        model: str = "gpt-5.4",
        api_key: str = "test-key",
        extra_config: str = "",
        extra_auth: dict | None = None,
    ) -> None:
        config_dir.mkdir(parents=True, exist_ok=True)
        auth_data = {"OPENAI_API_KEY": api_key}
        if extra_auth:
            auth_data.update(extra_auth)
        (config_dir / "auth.json").write_text(
            json.dumps(auth_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        config_text = app.build_custom_template_config_toml(
            provider,
            base_url or f"https://{provider.lower()}.example.com/v1",
            model,
        )
        if extra_config:
            config_text += f"\n{extra_config.strip()}\n"
        (config_dir / "config.toml").write_text(config_text, encoding="utf-8")

    def create_profile(self, name: str, provider: str, **kwargs) -> app.BackupRecord:
        self.write_config(self.config_dir, provider, **kwargs)
        return app.create_named_backup(self.config_dir, name)

    def test_new_config_is_named_saved_and_applied(self) -> None:
        self.write_config(self.config_dir, "A", "https://a.example.com/v1")

        result = app.save_config_profile(
            self.config_dir,
            "key-b",
            "B",
            "https://b.example.com/v1",
            "gpt-5.5",
            "editable",
            "Provider B",
        )

        self.assertEqual("created", result.status)
        self.assertEqual("Provider B", result.record.name)
        self.assertEqual("B", app.read_codex_config(self.config_dir).provider)
        self.assertEqual(
            app.build_backup_signature(self.config_dir),
            app.build_backup_signature(result.record.path),
        )

    def test_existing_config_is_applied_without_a_name(self) -> None:
        profile_a = self.create_profile("Provider A", "A", base_url="https://a.example.com/v1")
        self.create_profile("Provider B", "B", base_url="https://b.example.com/v1")

        result = app.save_config_profile(
            self.config_dir,
            "test-key",
            "A",
            "https://a.example.com/v1",
            "gpt-5.4",
            "editable",
            None,
        )

        self.assertEqual("existing", result.status)
        self.assertEqual(profile_a.path, result.record.path)
        self.assertEqual("A", app.read_codex_config(self.config_dir).provider)
        self.assertEqual(2, len(app.list_backup_records(self.config_dir)))

    def test_direct_switch_never_saves_outgoing_configuration(self) -> None:
        profile_a = self.create_profile("Provider A", "A")
        self.create_profile("Provider B", "B")
        self.write_config(self.config_dir, "Unsaved C")

        app.restore_backup(self.config_dir, profile_a.path)

        self.assertEqual("A", app.read_codex_config(self.config_dir).provider)
        self.assertEqual({"Provider A", "Provider B"}, {item.name for item in app.list_backup_records(self.config_dir)})

    def test_switch_does_not_update_profile_time_or_content(self) -> None:
        profile_a = self.create_profile("Provider A", "A")
        original_mtime = profile_a.path.stat().st_mtime_ns
        original_auth = (profile_a.path / "auth.json").read_bytes()
        original_config = (profile_a.path / "config.toml").read_bytes()
        self.write_config(self.config_dir, "B")

        app.restore_backup(self.config_dir, profile_a.path)

        self.assertEqual(original_mtime, profile_a.path.stat().st_mtime_ns)
        self.assertEqual(original_auth, (profile_a.path / "auth.json").read_bytes())
        self.assertEqual(original_config, (profile_a.path / "config.toml").read_bytes())

    def test_matching_ignores_codex_managed_state_and_profile_name(self) -> None:
        profile = self.create_profile(
            "Any profile name",
            "A",
            extra_config='[desktop]\nwindow_state = "first"',
            extra_auth={"tokens": {"access_token": "first"}},
        )
        self.write_config(
            self.config_dir,
            "A",
            extra_config='[desktop]\nwindow_state = "changed"',
            extra_auth={"tokens": {"access_token": "changed"}},
        )

        result = app.save_config_profile(
            self.config_dir,
            "test-key",
            "A",
            "https://a.example.com/v1",
            "gpt-5.4",
            "editable",
            None,
        )

        self.assertEqual("existing", result.status)
        self.assertEqual(profile.path, result.record.path)
        self.assertIn('window_state = "changed"', (self.config_dir / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            {"access_token": "changed"},
            json.loads((self.config_dir / "auth.json").read_text(encoding="utf-8"))["tokens"],
        )

    def test_new_config_requires_name_and_cancellation_changes_nothing(self) -> None:
        self.write_config(self.config_dir, "A")
        before = app.capture_config_files(self.config_dir)

        with self.assertRaises(app.BackupNameError):
            app.save_config_profile(
                self.config_dir,
                "new-key",
                "B",
                "https://b.example.com/v1",
                "gpt-5.5",
                "editable",
                None,
            )

        self.assertEqual(before, app.capture_config_files(self.config_dir))
        self.assertFalse((self.config_dir / "backups").exists())

    def test_duplicate_profile_name_is_rejected_before_modifying_config(self) -> None:
        self.create_profile("Shared", "A")
        before = app.capture_config_files(self.config_dir)

        with self.assertRaises(app.BackupNameConflictError):
            app.save_config_profile(
                self.config_dir,
                "new-key",
                "B",
                "https://b.example.com/v1",
                "gpt-5.5",
                "editable",
                "shared",
            )

        self.assertEqual(before, app.capture_config_files(self.config_dir))

    def test_failed_profile_creation_rolls_back_current_config(self) -> None:
        self.write_config(self.config_dir, "A")
        before = app.capture_config_files(self.config_dir)

        with patch.object(app, "create_named_backup", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                app.save_config_profile(
                    self.config_dir,
                    "new-key",
                    "B",
                    "https://b.example.com/v1",
                    "gpt-5.5",
                    "editable",
                    "Provider B",
                )

        self.assertEqual(before, app.capture_config_files(self.config_dir))

    def test_template_state_can_be_saved_as_new_profile(self) -> None:
        result = app.save_config_profile(
            self.config_dir,
            "template-key",
            "Template Provider",
            "https://template.example.com/v1",
            "gpt-5.5",
            "needs_template",
            "Template",
        )

        self.assertEqual("created", result.status)
        self.assertEqual("Template Provider", app.read_codex_config(self.config_dir).provider)
        self.assertEqual("editable", app.classify_config_for_editing(self.config_dir)[0])

    def test_create_profile_without_apply_keeps_current_config(self) -> None:
        self.write_config(self.config_dir, "Current")
        before = app.capture_config_files(self.config_dir)

        created = app.create_config_profile(
            self.config_dir,
            "Saved only",
            "saved-key",
            "Saved Provider",
            "https://saved.example.com/v1",
            "gpt-5.6-sol",
        )

        self.assertEqual(before, app.capture_config_files(self.config_dir))
        self.assertEqual("Saved Provider", app.read_codex_config(created.path).provider)

    def test_new_profile_preserves_identity_and_unmanaged_fields(self) -> None:
        self.write_config(
            self.config_dir,
            "Current",
            extra_config='[session]\nconversation_id = "keep-this"',
            extra_auth={"tokens": {"access_token": "keep-token"}, "account_id": "account-1"},
        )
        before = app.capture_config_files(self.config_dir)

        created = app.create_config_profile(
            self.config_dir,
            "Preserved profile",
            "new-key",
            "New Provider",
            "https://new.example.com/v1",
            "gpt-5.6-sol",
        )

        self.assertEqual(before, app.capture_config_files(self.config_dir))
        profile_auth = json.loads((created.path / "auth.json").read_text(encoding="utf-8"))
        self.assertEqual({"access_token": "keep-token"}, profile_auth["tokens"])
        self.assertEqual("account-1", profile_auth["account_id"])
        profile_config = (created.path / "config.toml").read_text(encoding="utf-8")
        self.assertIn('conversation_id = "keep-this"', profile_config)
        self.assertEqual("new-key", app.read_codex_config(created.path).api_key)
        self.assertEqual("New Provider", app.read_codex_config(created.path).provider)

    def test_new_profile_and_apply_preserves_identity_and_unmanaged_fields(self) -> None:
        self.write_config(
            self.config_dir,
            "Current",
            extra_config='[session]\nconversation_id = "keep-this"',
            extra_auth={"tokens": {"access_token": "keep-token"}, "account_id": "account-1"},
        )

        created = app.create_config_profile(
            self.config_dir,
            "Active profile",
            "active-key",
            "Active Provider",
            "https://active.example.com/v1",
            "gpt-5.6-sol",
            apply_to_current=True,
        )

        current_auth = json.loads((self.config_dir / "auth.json").read_text(encoding="utf-8"))
        self.assertEqual({"access_token": "keep-token"}, current_auth["tokens"])
        self.assertEqual("account-1", current_auth["account_id"])
        current_config = (self.config_dir / "config.toml").read_text(encoding="utf-8")
        self.assertIn('conversation_id = "keep-this"', current_config)
        self.assertEqual("active-key", app.read_codex_config(self.config_dir).api_key)
        self.assertEqual("Active Provider", app.read_codex_config(self.config_dir).provider)
        self.assertIn('conversation_id = "keep-this"', current_config)
        self.assertIn('disable_response_storage = true', current_config)

    def test_template_state_save_preserves_existing_files(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "auth.json").write_text(
            json.dumps(
                {
                    "OPENAI_API_KEY": "old-key",
                    "tokens": {"access_token": "keep-token"},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.config_dir / "config.toml").write_text(
            'model_provider = "openai"\n'
            'model = "gpt-5.4"\n\n'
            '[session]\n'
            'conversation_id = "keep-this"\n',
            encoding="utf-8",
        )

        result = app.save_config_profile(
            self.config_dir,
            "new-key",
            "New Provider",
            "https://new.example.com/v1",
            "gpt-5.6-sol",
            "needs_template",
            "Template-preserved",
        )

        self.assertEqual("created", result.status)
        current_auth = json.loads((self.config_dir / "auth.json").read_text(encoding="utf-8"))
        self.assertEqual({"access_token": "keep-token"}, current_auth["tokens"])
        current_config = (self.config_dir / "config.toml").read_text(encoding="utf-8")
        self.assertIn('conversation_id = "keep-this"', current_config)
        self.assertEqual("New Provider", app.read_codex_config(self.config_dir).provider)
        self.assertEqual("gpt-5.6-sol", app.read_codex_config(self.config_dir).model)

    def test_create_profile_and_apply_switches_current_config(self) -> None:
        self.write_config(self.config_dir, "Current")

        created = app.create_config_profile(
            self.config_dir,
            "Created and active",
            "active-key",
            "Active Provider",
            "https://active.example.com/v1",
            "gpt-5.6-sol",
            apply_to_current=True,
        )

        self.assertEqual("Active Provider", app.read_codex_config(self.config_dir).provider)
        self.assertEqual(created.path, app.find_matching_backup(self.config_dir).path)

    def test_edit_inactive_profile_updates_all_fields_without_switching(self) -> None:
        active = self.create_profile("Active", "Active")
        inactive = self.create_profile("Inactive", "Inactive")
        app.restore_backup(self.config_dir, active.path)
        current_before = app.capture_config_files(self.config_dir)

        edited = app.update_config_profile(
            self.config_dir,
            inactive.path,
            "Renamed inactive",
            "edited-key",
            "Edited Provider",
            "https://edited.example.com/v1",
            "gpt-5.6-sol",
        )

        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(inactive.created_at, edited.created_at)
        edited_config = app.read_codex_config(edited.path)
        self.assertEqual("Edited Provider", edited_config.provider)
        self.assertEqual("edited-key", edited_config.api_key)

    def test_edit_active_profile_updates_library_and_current_config(self) -> None:
        active = self.create_profile("Active", "Active")
        app.restore_backup(self.config_dir, active.path)

        edited = app.update_config_profile(
            self.config_dir,
            active.path,
            "Active renamed",
            "new-key",
            "Active edited",
            "https://active-edited.example.com/v1",
            "gpt-5.6-sol",
            apply_to_current=True,
        )

        self.assertEqual("Active renamed", edited.name)
        self.assertEqual("Active edited", app.read_codex_config(self.config_dir).provider)
        self.assertEqual(
            app.build_backup_signature(edited.path),
            app.build_backup_signature(self.config_dir),
        )

    def test_duplicate_profile_content_is_rejected_without_changes(self) -> None:
        existing = self.create_profile("Existing", "Existing")
        current_before = app.capture_config_files(self.config_dir)

        with self.assertRaises(app.BackupNameConflictError):
            app.create_config_profile(
                self.config_dir,
                "Duplicate",
                "test-key",
                "Existing",
                "https://existing.example.com/v1",
                "gpt-5.4",
            )

        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual([existing.path], [record.path for record in app.list_backup_records(self.config_dir)])

    def test_profiles_are_never_pruned(self) -> None:
        for index in range(8):
            self.write_config(self.config_dir, f"Provider {index}")
            app.create_named_backup(self.config_dir, f"profile-{index}")

        self.assertEqual(8, len(app.list_backup_records(self.config_dir)))

    def test_rename_preserves_timestamp_and_content_and_rejects_duplicates(self) -> None:
        first = self.create_profile("First", "A")
        second = self.create_profile("Second", "B")
        original_auth = (first.path / "auth.json").read_bytes()
        original_config = (first.path / "config.toml").read_bytes()

        renamed = app.rename_backup(self.config_dir, first.path, "Renamed")

        self.assertEqual(first.created_at, renamed.created_at)
        self.assertEqual(original_auth, (renamed.path / "auth.json").read_bytes())
        self.assertEqual(original_config, (renamed.path / "config.toml").read_bytes())
        with self.assertRaises(app.BackupNameConflictError):
            app.rename_backup(self.config_dir, renamed.path, second.name.lower())

    def test_delete_only_removes_selected_profiles(self) -> None:
        records = [self.create_profile(f"item-{index}", f"Provider {index}") for index in range(3)]

        app.delete_backups(self.config_dir, [records[0].path, records[2].path])

        self.assertEqual(["item-1"], [record.name for record in app.list_backup_records(self.config_dir)])

    def test_deleting_active_profile_keeps_current_config_but_removes_saved_match(self) -> None:
        active = self.create_profile("Active", "Provider A")
        app.restore_backup(self.config_dir, active.path)
        current_before = app.capture_config_files(self.config_dir)

        app.delete_backups(self.config_dir, [active.path])

        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertIsNone(app.find_matching_backup(self.config_dir))

    def test_atomic_write_replace_failure_preserves_original_and_cleans_temp_file(self) -> None:
        target = self.config_dir / "auth.json"
        target.parent.mkdir(parents=True)
        target.write_text("original\n", encoding="utf-8")

        with patch.object(app.os, "replace", side_effect=OSError("injected replace failure")):
            with self.assertRaises(OSError):
                app.write_text(target, "changed\n")

        self.assertEqual("original\n", target.read_text(encoding="utf-8"))
        self.assertEqual([], list(target.parent.glob(".auth.json.*.tmp")))

    def test_save_config_rolls_back_both_files_when_second_replace_fails(self) -> None:
        self.write_config(self.config_dir, "Original")
        before = app.capture_config_files(self.config_dir)
        real_replace = app.os.replace
        failure_injected = False

        def fail_first_config_replace(source, target) -> None:
            nonlocal failure_injected
            if Path(target).name == "config.toml" and not failure_injected:
                failure_injected = True
                raise OSError("injected config replace failure")
            real_replace(source, target)

        with patch.object(app.os, "replace", side_effect=fail_first_config_replace):
            with self.assertRaises(OSError):
                app.save_codex_config(
                    self.config_dir,
                    "changed-key",
                    "Changed",
                    "https://changed.example.com/v1",
                    "gpt-5.6",
                    persist_settings=False,
                )

        self.assertEqual(before, app.capture_config_files(self.config_dir))
        self.assertEqual([], list(self.config_dir.glob(".*.tmp")))

    def test_profile_signature_cache_reuses_data_and_invalidates_after_write(self) -> None:
        self.write_config(self.config_dir, "Original")
        app.clear_profile_cache()

        with patch.object(
            app,
            "_build_backup_signature_uncached",
            wraps=app._build_backup_signature_uncached,
        ) as builder:
            first = app.build_backup_signature(self.config_dir)
            second = app.build_backup_signature(self.config_dir)
            self.assertEqual(first, second)
            self.assertEqual(1, builder.call_count)

            app.write_text(
                self.config_dir / "config.toml",
                app.build_custom_template_config_toml("Changed", "https://changed.example.com/v1", "gpt-5.6"),
            )
            changed = app.build_backup_signature(self.config_dir)

        self.assertEqual(2, builder.call_count)
        self.assertNotEqual(first, changed)

    def test_model_list_endpoint_appends_models_to_api_root(self) -> None:
        self.assertEqual(
            "https://provider.example.com/v1/models",
            app.model_list_endpoint("https://provider.example.com/v1/"),
        )
        self.assertEqual(
            "http://127.0.0.1:1234/models",
            app.model_list_endpoint("http://127.0.0.1:1234"),
        )
        self.assertEqual(
            "https://provider.example.com/v1/models",
            app.model_list_endpoint("https://provider.example.com/v1/models"),
        )

    def test_model_list_parser_deduplicates_and_sorts_model_ids(self) -> None:
        payload = json.dumps(
            {
                "object": "list",
                "data": [
                    {"id": "gpt-z"},
                    {"id": " gpt-a "},
                    {"id": "gpt-z"},
                    {"name": "ignored"},
                ],
            }
        ).encode("utf-8")

        self.assertEqual(["gpt-a", "gpt-z"], app.parse_model_list(payload))

    def test_fetch_models_uses_bearer_auth_and_disables_redirects(self) -> None:
        calls = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, size):
                calls["read_size"] = size
                return b'{"data":[{"id":"gpt-test"}]}'

        class Opener:
            def open(self, request, timeout):
                calls["url"] = request.full_url
                calls["authorization"] = request.get_header("Authorization")
                calls["timeout"] = timeout
                return Response()

        with patch.object(app.urllib.request, "build_opener", return_value=Opener()) as builder:
            models = app.fetch_available_models("https://provider.example.com/v1", " secret-key ", 3.5)

        self.assertEqual(["gpt-test"], models)
        self.assertEqual("https://provider.example.com/v1/models", calls["url"])
        self.assertEqual("Bearer secret-key", calls["authorization"])
        self.assertEqual(3.5, calls["timeout"])
        self.assertEqual(app.MODEL_LIST_MAX_BYTES + 1, calls["read_size"])
        self.assertIsInstance(builder.call_args.args[0], app._NoRedirectHandler)

    def test_model_selection_updates_current_and_matching_saved_profile(self) -> None:
        active = self.create_profile(
            "Active",
            "Provider A",
            extra_config='[session]\nconversation_id = "keep-this"',
        )

        updated = app.save_active_model(self.config_dir, "gpt-5.6-sol")

        self.assertEqual(active.path, updated.path)
        self.assertEqual("gpt-5.6-sol", app.read_codex_config(self.config_dir).model)
        self.assertEqual("gpt-5.6-sol", app.read_codex_config(active.path).model)
        self.assertIn(
            'conversation_id = "keep-this"',
            (self.config_dir / "config.toml").read_text(encoding="utf-8"),
        )
        self.assertEqual(active.path, app.find_matching_backup(self.config_dir).path)

    def test_model_selection_only_updates_current_when_it_is_unsaved(self) -> None:
        saved = self.create_profile("Saved", "Provider A", model="gpt-old")
        self.write_config(self.config_dir, "Provider B", model="gpt-current")

        updated = app.save_active_model(self.config_dir, "gpt-new")

        self.assertIsNone(updated)
        self.assertEqual("gpt-new", app.read_codex_config(self.config_dir).model)
        self.assertEqual("gpt-old", app.read_codex_config(saved.path).model)

    def test_model_selection_rolls_back_profile_when_current_write_fails(self) -> None:
        active = self.create_profile("Active", "Provider A", model="gpt-old")
        current_before = app.capture_config_files(self.config_dir)
        profile_before = app.capture_config_files(active.path)
        real_update = app.update_config_model

        def fail_current_write(config_path: Path, model: str) -> None:
            if config_path.parent.resolve() == self.config_dir.resolve():
                raise OSError("injected current model write failure")
            real_update(config_path, model)

        with patch.object(app, "update_config_model", side_effect=fail_current_write):
            with self.assertRaises(OSError):
                app.save_active_model(self.config_dir, "gpt-new")

        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(profile_before, app.capture_config_files(active.path))

    def test_restore_default_preserves_config_auth_and_session_data(self) -> None:
        self.write_config(
            self.config_dir,
            "A",
            extra_config='[session]\nconversation_id = "keep-this"\n[desktop]\nwindow_state = "open"',
            extra_auth={"tokens": {"access_token": "keep-token"}, "account_id": "account-1", "other": "keep"},
        )
        sessions = self.config_dir / "sessions"
        sessions.mkdir()
        marker = sessions / "keep.txt"
        marker.write_text("keep", encoding="utf-8")

        app.restore_default_config(self.config_dir)

        auth = json.loads((self.config_dir / "auth.json").read_text(encoding="utf-8"))
        self.assertNotIn("OPENAI_API_KEY", auth)
        self.assertEqual({"access_token": "keep-token"}, auth["tokens"])
        self.assertEqual("account-1", auth["account_id"])
        self.assertEqual("keep", auth["other"])
        config_text = (self.config_dir / "config.toml").read_text(encoding="utf-8")
        self.assertIn('model_provider = "openai"', config_text)
        self.assertIn('conversation_id = "keep-this"', config_text)
        self.assertIn('window_state = "open"', config_text)
        self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_api_official_api_round_trip_preserves_current_session_identity(self) -> None:
        api_a = self.create_profile(
            "API-A",
            "Provider A",
            extra_config='[session]\nconversation_id = "thread-a"',
            extra_auth={"tokens": {"access_token": "chatgpt-token"}, "account_id": "acct"},
        )
        app.apply_saved_profile(self.config_dir, api_a.path)
        app.restore_default_config(self.config_dir)
        config_path = self.config_dir / "config.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8") + '\n[session]\nconversation_id = "thread-official"\n',
            encoding="utf-8",
        )
        official_snapshot = app.capture_config_files(self.config_dir)
        api_k = self.create_profile("API-K", "Provider K", api_key="key-k")
        app.restore_config_files(self.config_dir, official_snapshot)
        app.apply_saved_profile(self.config_dir, api_k.path)

        current = app.read_codex_config(self.config_dir)
        self.assertEqual("Provider K", current.provider)
        self.assertEqual("key-k", current.api_key)
        current_text = config_path.read_text(encoding="utf-8")
        self.assertIn('conversation_id = "thread-official"', current_text)
        auth = json.loads((self.config_dir / "auth.json").read_text(encoding="utf-8"))
        self.assertEqual("chatgpt-token", auth["tokens"]["access_token"])
        self.assertEqual("acct", auth["account_id"])

    def test_restore_default_rolls_back_both_files_on_failure(self) -> None:
        self.write_config(self.config_dir, "A", extra_auth={"tokens": {"access_token": "keep"}})
        before = app.capture_config_files(self.config_dir)
        real_write = app.write_text

        def fail_config(path: Path, content: str) -> None:
            if path.name == "config.toml":
                raise OSError("injected config failure")
            real_write(path, content)

        with patch.object(app, "write_text", side_effect=fail_config):
            with self.assertRaises(OSError):
                app.restore_default_config(self.config_dir)
        self.assertEqual(before, app.capture_config_files(self.config_dir))

    def test_unreadable_core_config_is_never_matched(self) -> None:
        self.create_profile("A", "A")
        (self.config_dir / "auth.json").write_text("{invalid", encoding="utf-8")

        self.assertIsNone(app.find_matching_backup(self.config_dir))

    def test_legacy_duplicate_names_are_preserved_and_latest_matching_profile_is_found(self) -> None:
        older = self.config_dir / "backups" / "20260101-120000-before-save"
        newer = self.config_dir / "backups" / "20260102-120000-before-save"
        self.write_config(older, "A")
        self.write_config(newer, "B")
        self.write_config(self.config_dir, "B")

        matching = app.find_matching_backup(self.config_dir)

        self.assertEqual(newer.resolve(), matching.path.resolve())
        self.assertEqual(2, len(app.named_backup_records(self.config_dir, "before-save")))

    def test_chinese_provider_name_is_preserved_for_suggestion(self) -> None:
        self.write_config(self.config_dir, "中文服务")

        self.assertEqual("中文服务", app.read_codex_config(self.config_dir).provider)
        self.assertEqual("中文服务", app.suggested_config_name("中文服务"))

    def test_invalid_profile_names_are_rejected(self) -> None:
        self.write_config(self.config_dir, "A")
        for name in (None, "", "bad/name", "bad.", "x" * 41):
            with self.subTest(name=name):
                with self.assertRaises(app.BackupNameError):
                    app.create_named_backup(self.config_dir, name)

    def test_drag_selection_adds_a_contiguous_range_to_existing_selection(self) -> None:
        items = ("a", "b", "c", "d", "e")

        self.assertEqual(("b", "c", "d", "e"), app.drag_selection_items(items, "b", "d", ("e",)))
        self.assertEqual(("a", "b", "c", "d"), app.drag_selection_items(items, "d", "b", ("a",)))

    def test_key_drag_scroll_accelerates_outside_both_entry_edges(self) -> None:
        self.assertEqual(0, app.horizontal_drag_scroll_units(0, 400))
        self.assertEqual(0, app.horizontal_drag_scroll_units(399, 400))
        self.assertEqual(-2, app.horizontal_drag_scroll_units(-1, 400))
        self.assertEqual(2, app.horizontal_drag_scroll_units(400, 400))
        self.assertLess(app.horizontal_drag_scroll_units(-80, 400), -2)
        self.assertGreater(app.horizontal_drag_scroll_units(480, 400), 2)
        self.assertEqual(-16, app.horizontal_drag_scroll_units(-1000, 400))
        self.assertEqual(16, app.horizontal_drag_scroll_units(1400, 400))

    def test_key_pixel_scroll_target_is_smooth_and_clamped(self) -> None:
        self.assertAlmostEqual(0.12, app.horizontal_scroll_target(0.1, 0.3, 400, 40))
        self.assertEqual(0.0, app.horizontal_scroll_target(0.01, 0.21, 400, -1000))
        self.assertEqual(0.8, app.horizontal_scroll_target(0.79, 0.99, 400, 1000))
        self.assertEqual(0.0, app.horizontal_scroll_target(0.0, 1.0, 400, 100))
        self.assertEqual(0.0, app.horizontal_scroll_target(0.1, 0.3, 0, 100))

    def test_onboarding_is_automatic_until_explicitly_disabled(self) -> None:
        self.assertTrue(app.should_show_onboarding({}))
        self.assertTrue(app.should_show_onboarding({app.ONBOARDING_SHOWN_KEY: False}))
        self.assertTrue(app.should_show_onboarding({app.ONBOARDING_SHOWN_KEY: True}))

    def test_only_explicit_hide_setting_disables_onboarding(self) -> None:
        self.assertFalse(app.should_show_onboarding({app.HIDE_ONBOARDING_KEY: True}))
        self.assertTrue(app.should_show_onboarding({app.HIDE_ONBOARDING_KEY: False}))


if __name__ == "__main__":
    unittest.main()
