import ctypes
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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
    def test_discover_codex_installation_reads_manifest_application_id(self) -> None:
        completed = app.subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="OpenAI.Codex_2p2nqsd0c76g0!CodexDesktop\n",
            stderr="",
        )
        with patch.object(app.subprocess, "run", return_value=completed) as run:
            target = app.discover_codex_installation()

        self.assertIsNotNone(target)
        self.assertEqual("OpenAI.Codex_2p2nqsd0c76g0!CodexDesktop", target.app_user_model_id)
        command = run.call_args.args[0]
        self.assertIn("Get-AppxPackageManifest", command[-1])
        self.assertIn("Get-StartApps", command[-1])

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
            patch.object(app, "wait_for_new_codex_process", return_value=True) as wait_for_start,
            patch.object(app, "activate_codex_window", return_value=True),
            patch.object(app.subprocess, "Popen") as popen,
        ):
            result = app.restart_codex_application()

        self.assertEqual("start", result.action)
        wait_for_start.assert_called_once_with(target, set())
        popen.assert_called_once_with(
            ["explorer.exe", "shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App"],
            close_fds=True,
        )

    @unittest.skipUnless(os.name == "nt", "Windows Codex restart test")
    def test_request_codex_normal_exit_uses_codex_ctrl_q_accelerator(self) -> None:
        target = app.CodexRestartTarget(root_pid=100, executable=Path(r"C:\Codex\Codex.exe"))
        processes = [app.ProcessRecord(100, 50, target.executable)]
        with (
            patch.object(app, "list_windows_processes", return_value=processes),
            patch.object(app, "send_codex_quit_shortcut", return_value=True) as send_quit,
            patch.object(app, "wait_for_codex_app_exit", return_value=True) as wait_app_exit,
            patch.object(app.subprocess, "run") as run,
        ):
            self.assertTrue(app.request_codex_normal_exit(target))

        send_quit.assert_called_once_with({100})
        wait_app_exit.assert_called_once_with(target, app.CODEX_NORMAL_EXIT_TIMEOUT_SECONDS)
        run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows Codex restart test")
    def test_request_codex_normal_exit_does_not_wait_if_focus_verification_fails(self) -> None:
        target = app.CodexRestartTarget(root_pid=100, executable=Path(r"C:\Codex\Codex.exe"))
        processes = [app.ProcessRecord(100, 50, target.executable)]
        with (
            patch.object(app, "list_windows_processes", return_value=processes),
            patch.object(app, "send_codex_quit_shortcut", return_value=False),
            patch.object(app, "wait_for_codex_app_exit") as wait_app_exit,
        ):
            self.assertFalse(app.request_codex_normal_exit(target))

        wait_app_exit.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows INPUT ABI test")
    def test_windows_input_structure_has_native_abi_size(self) -> None:
        _keyboard_input, input_type = app.windows_keyboard_input_types()

        expected_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(expected_size, ctypes.sizeof(input_type))

    def test_codex_tray_guid_only_matches_store_production_package(self) -> None:
        store_target = app.CodexRestartTarget(
            root_pid=100,
            executable=Path(),
            app_user_model_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        )
        other_target = app.CodexRestartTarget(
            root_pid=100,
            executable=Path(r"C:\Codex\Codex.exe"),
        )

        self.assertEqual(app.CODEX_STORE_PROD_TRAY_GUID, app.codex_tray_guid(store_target))
        self.assertIsNone(app.codex_tray_guid(other_target))

    @unittest.skipUnless(os.name == "nt", "Windows notification area test")
    def test_remove_stale_codex_tray_registration_deletes_exact_guid(self) -> None:
        target = app.CodexRestartTarget(
            root_pid=100,
            executable=Path(),
            app_user_model_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        )
        captured = {}

        class ShellNotifyIcon:
            argtypes = None
            restype = None

            def __call__(self, message, data_pointer):
                data = data_pointer._obj
                captured["message"] = message
                captured["flags"] = data.uFlags
                captured["guid"] = (
                    data.guidItem.Data1,
                    data.guidItem.Data2,
                    data.guidItem.Data3,
                    bytes(data.guidItem.Data4),
                )
                return True

        shell32 = SimpleNamespace(Shell_NotifyIconW=ShellNotifyIcon())
        with patch.object(ctypes, "WinDLL", return_value=shell32):
            self.assertTrue(app.remove_stale_codex_tray_registration(target))

        expected = app.uuid.UUID(app.CODEX_STORE_PROD_TRAY_GUID)
        self.assertEqual(0x00000002, captured["message"])
        self.assertEqual(0x00000020, captured["flags"])
        self.assertEqual(
            (expected.time_low, expected.time_mid, expected.time_hi_version, expected.bytes[8:]),
            captured["guid"],
        )

    @unittest.skipUnless(os.name == "nt", "Windows Codex restart test")
    def test_codex_restart_closes_normally_before_launching(self) -> None:
        target = app.CodexRestartTarget(root_pid=100, executable=Path(r"C:\Codex\Codex.exe"))
        processes = [app.ProcessRecord(100, 50, target.executable)]
        with (
            patch.object(app, "list_windows_processes", return_value=processes),
            patch.object(app, "discover_codex_installation", return_value=None),
            patch.object(app, "request_codex_normal_exit", return_value=True) as request_exit,
            patch.object(app, "wait_for_new_codex_process", return_value=True),
            patch.object(app, "activate_codex_window", return_value=True),
            patch.object(app.time, "sleep") as sleep,
            patch.object(app.subprocess, "Popen") as popen,
        ):
            result = app.restart_codex_application()

        self.assertEqual("restart", result.action)
        request_exit.assert_called_once_with(target)
        sleep.assert_called_once_with(app.CODEX_TRAY_SHELL_SETTLE_SECONDS)
        popen.assert_called_once_with(
            [str(target.executable)],
            close_fds=True,
            creationflags=(
                getattr(app.subprocess, "DETACHED_PROCESS", 0)
                | getattr(app.subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            ),
        )

    @unittest.skipUnless(os.name == "nt", "Windows Codex restart test")
    def test_codex_restart_does_not_relaunch_when_normal_exit_fails(self) -> None:
        target = app.CodexRestartTarget(root_pid=100, executable=Path(r"C:\Codex\Codex.exe"))
        processes = [app.ProcessRecord(100, 50, target.executable)]
        with (
            patch.object(app, "list_windows_processes", return_value=processes),
            patch.object(app, "discover_codex_installation", return_value=None),
            patch.object(app, "request_codex_normal_exit", return_value=False),
            patch.object(app.subprocess, "Popen") as popen,
        ):
            with self.assertRaises(app.CodexRestartError):
                app.restart_codex_application()

        popen.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows Codex restart test")
    def test_codex_restart_replaces_guessed_aumid_with_manifest_aumid(self) -> None:
        target = app.CodexRestartTarget(
            root_pid=100,
            executable=Path(r"C:\Program Files\WindowsApps\OpenAI.Codex_1.0_x64__publisher\app\ChatGPT.exe"),
            app_user_model_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        )
        installed = app.CodexRestartTarget(
            root_pid=0,
            executable=Path(),
            app_user_model_id="OpenAI.Codex_2p2nqsd0c76g0!CodexDesktop",
        )
        with (
            patch.object(app, "discover_codex_installation", return_value=installed),
            patch.object(app, "request_codex_normal_exit", return_value=True) as request_exit,
            patch.object(app, "remove_stale_codex_tray_registration") as remove_tray,
            patch.object(app, "list_windows_processes", return_value=[]),
            patch.object(app, "wait_for_new_codex_process", return_value=True),
            patch.object(app, "activate_codex_window", return_value=True),
            patch.object(app.time, "sleep"),
            patch.object(app.subprocess, "Popen") as popen,
        ):
            result = app.restart_codex_application(target)

        self.assertEqual("restart", result.action)
        resolved = request_exit.call_args.args[0]
        self.assertEqual("OpenAI.Codex_2p2nqsd0c76g0!CodexDesktop", resolved.app_user_model_id)
        remove_tray.assert_called_once_with(resolved)
        popen.assert_called_once_with(
            ["explorer.exe", "shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!CodexDesktop"],
            close_fds=True,
        )

    @unittest.skipUnless(os.name == "nt", "Windows Codex launch test")
    def test_codex_launch_requires_a_new_main_process(self) -> None:
        target = app.CodexRestartTarget(
            root_pid=0,
            executable=Path(),
            app_user_model_id="OpenAI.Codex_2p2nqsd0c76g0!CodexDesktop",
        )
        with (
            patch.object(app, "list_windows_processes", return_value=[]),
            patch.object(app, "wait_for_new_codex_process", return_value=False),
            patch.object(app, "activate_codex_window") as activate,
            patch.object(app.subprocess, "Popen"),
        ):
            with self.assertRaises(app.CodexRestartError):
                app.launch_codex_application(target, "start")

        activate.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows Codex launch test")
    def test_packaged_launch_falls_back_to_exe_without_no_window_flag(self) -> None:
        executable = self.root / "ChatGPT.exe"
        executable.write_bytes(b"")
        target = app.CodexRestartTarget(
            root_pid=100,
            executable=executable,
            app_user_model_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        )
        with (
            patch.object(app, "list_windows_processes", return_value=[]),
            patch.object(app, "wait_for_new_codex_process", side_effect=[False, True]),
            patch.object(app, "activate_codex_window", return_value=True),
            patch.object(app.subprocess, "Popen") as popen,
        ):
            result = app.launch_codex_application(target, "start")

        self.assertIsNone(result.target.app_user_model_id)
        self.assertEqual(2, popen.call_count)
        fallback_call = popen.call_args_list[1]
        self.assertEqual([str(executable)], fallback_call.args[0])
        self.assertEqual(
            getattr(app.subprocess, "DETACHED_PROCESS", 0)
            | getattr(app.subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            fallback_call.kwargs["creationflags"],
        )

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

    def write_native_model_cache(self, entries: list[dict]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / app.CODEX_NATIVE_MODEL_CACHE_FILENAME).write_text(
            json.dumps({"models": entries}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def read_owned_catalog(self, config_dir: Path) -> dict:
        return json.loads((config_dir / app.MODEL_CATALOG_FILENAME).read_text(encoding="utf-8"))

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

    def test_sync_current_to_active_profile_writes_back_codex_model_before_switch(self) -> None:
        active = self.create_profile("Active", "Provider A", model="deepseek-v4-pro")
        other = self.create_profile("Other", "Provider B", model="other-model")
        app.set_active_profile_path(active.path)
        self.write_config(self.config_dir, "Provider A", model="deepseek-v4-flash")

        synced = app.sync_current_to_active_profile(self.config_dir)

        self.assertEqual(app.normalized_path_key(active.path), app.normalized_path_key(synced.path))
        self.assertEqual("deepseek-v4-flash", app.read_codex_config(active.path).model)
        self.assertEqual("other-model", app.read_codex_config(other.path).model)

    def test_reasoning_change_keeps_active_profile_identity_and_syncs_public_default(self) -> None:
        active = self.create_profile("GPT", "Provider A", model="gpt-test")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        config_path = self.config_dir / "config.toml"
        lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
        config_path.write_text(
            "".join(app.replace_existing_top_level(lines, "model_reasoning_effort", "medium")),
            encoding="utf-8",
        )
        app.clear_profile_cache()

        resolved = app.resolve_active_profile(self.config_dir)
        synced = app.sync_current_to_active_profile(self.config_dir)

        self.assertEqual(app.normalized_path_key(active.path), app.normalized_path_key(resolved.path))
        self.assertEqual(app.normalized_path_key(active.path), app.normalized_path_key(synced.path))
        synced_lines = (active.path / "config.toml").read_text(encoding="utf-8").splitlines(keepends=True)
        self.assertEqual("medium", app.get_top_level_value(synced_lines, "model_reasoning_effort"))

    def test_profile_switch_starts_codex_after_projecting_target_when_stopped(self) -> None:
        active = self.create_profile("Provider A", "Provider A", api_key="key-a")
        target_profile = self.create_profile("Provider B", "Provider B", api_key="key-b")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        installed = app.CodexRestartTarget(
            root_pid=0,
            executable=Path(r"C:\Codex\Codex.exe"),
        )
        launch_result = app.CodexLaunchResult(target=installed, action="start")
        events = []
        real_sync = app.sync_current_to_active_profile
        real_restore = app.restore_backup

        def sync_current(config_dir):
            events.append("sync")
            return real_sync(config_dir)

        def restore_target(config_dir, backup_dir):
            events.append("restore")
            return real_restore(config_dir, backup_dir)

        with (
            patch.object(app, "list_windows_processes", return_value=[]),
            patch.object(app, "discover_codex_installation", return_value=installed),
            patch.object(app, "sync_current_to_active_profile", side_effect=sync_current),
            patch.object(app, "restore_backup", side_effect=restore_target),
            patch.object(
                app,
                "launch_codex_application",
                side_effect=lambda target, action: events.append("launch") or launch_result,
            ) as launch_codex,
        ):
            result = app.switch_saved_profile(self.config_dir, target_profile.path)

        self.assertEqual("start", result.action)
        self.assertEqual(["sync", "restore", "launch"], events)
        launch_codex.assert_called_once_with(installed, "start")
        self.assertEqual(
            app.normalized_path_key(target_profile.path),
            app.normalized_path_key(app.active_profile_path(self.config_dir)),
        )
        self.assertEqual("Provider B", app.read_codex_config(self.config_dir).provider)

    def test_profile_switch_closes_syncs_projects_and_restarts_in_order(self) -> None:
        active = self.create_profile("Provider A", "Provider A", api_key="key-a")
        target_profile = self.create_profile("Provider B", "Provider B", api_key="key-b")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        executable = Path(r"C:\Codex\Codex.exe")
        running = app.CodexRestartTarget(root_pid=100, executable=executable)
        records = [app.ProcessRecord(100, 50, executable)]
        launch_result = app.CodexLaunchResult(target=running, action="restart")
        events = []
        real_sync = app.sync_current_to_active_profile
        real_restore = app.restore_backup

        with (
            patch.object(app, "list_windows_processes", return_value=records),
            patch.object(app, "discover_codex_installation", return_value=None),
            patch.object(app, "request_codex_normal_exit", side_effect=lambda target: events.append("exit") or True),
            patch.object(app, "remove_stale_codex_tray_registration", side_effect=lambda target: events.append("tray")),
            patch.object(app, "sync_current_to_active_profile", side_effect=lambda path: events.append("sync") or real_sync(path)),
            patch.object(app, "restore_backup", side_effect=lambda path, target: events.append("restore") or real_restore(path, target)),
            patch.object(
                app,
                "launch_codex_application",
                side_effect=lambda target, action: events.append("launch") or launch_result,
            ),
        ):
            result = app.switch_saved_profile(
                self.config_dir,
                target_profile.path,
                allow_running_restart=True,
            )

        self.assertEqual("restart", result.action)
        self.assertEqual(["exit", "tray", "sync", "restore", "launch"], events)
        self.assertEqual("Provider B", app.read_codex_config(self.config_dir).provider)

    def test_profile_switch_requires_confirmation_before_closing_running_codex(self) -> None:
        active = self.create_profile("Provider A", "Provider A", api_key="key-a")
        target_profile = self.create_profile("Provider B", "Provider B", api_key="key-b")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        current_before = app.capture_config_files(self.config_dir)
        active_before = app.capture_config_files(active.path)
        executable = Path(r"C:\Codex\Codex.exe")
        records = [app.ProcessRecord(100, 50, executable)]

        with (
            patch.object(app, "list_windows_processes", return_value=records),
            patch.object(app, "request_codex_normal_exit") as request_exit,
            patch.object(app, "sync_current_to_active_profile") as sync_current,
            patch.object(app, "restore_backup") as restore_target,
        ):
            with self.assertRaises(app.ConfigConflictError) as raised:
                app.switch_saved_profile(self.config_dir, target_profile.path)

        self.assertIn("确认自动重启", str(raised.exception))
        request_exit.assert_not_called()
        sync_current.assert_not_called()
        restore_target.assert_not_called()
        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(active_before, app.capture_config_files(active.path))

    def test_profile_switch_restores_original_state_when_projection_fails(self) -> None:
        active = self.create_profile("Provider A", "Provider A", api_key="key-a", model="a-old")
        target_profile = self.create_profile("Provider B", "Provider B", api_key="key-b")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        app.update_config_model(self.config_dir / "config.toml", "a-latest")
        current_before = app.capture_config_files(self.config_dir)
        active_before = app.capture_config_files(active.path)
        settings_before = app.SETTINGS_FILE.read_bytes()
        executable = Path(r"C:\Codex\Codex.exe")
        running = app.CodexRestartTarget(root_pid=100, executable=executable)
        records = [app.ProcessRecord(100, 50, executable)]
        launch_result = app.CodexLaunchResult(target=running, action="restart")

        with (
            patch.object(app, "list_windows_processes", return_value=records),
            patch.object(app, "discover_codex_installation", return_value=None),
            patch.object(app, "request_codex_normal_exit", return_value=True),
            patch.object(app, "remove_stale_codex_tray_registration"),
            patch.object(app, "restore_backup", side_effect=app.ConfigConflictError("injected projection failure")),
            patch.object(app, "launch_codex_application", return_value=launch_result) as relaunch,
        ):
            with self.assertRaises(app.ConfigConflictError) as raised:
                app.switch_saved_profile(
                    self.config_dir,
                    target_profile.path,
                    allow_running_restart=True,
                )

        self.assertIn("原配置已恢复", str(raised.exception))
        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(active_before, app.capture_config_files(active.path))
        self.assertEqual(settings_before, app.SETTINGS_FILE.read_bytes())
        relaunch.assert_called_once_with(running, "restart")

    def test_profile_switch_restores_and_relaunches_original_when_target_start_fails(self) -> None:
        active = self.create_profile("Provider A", "Provider A", api_key="key-a")
        target_profile = self.create_profile("Provider B", "Provider B", api_key="key-b")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        current_before = app.capture_config_files(self.config_dir)
        active_before = app.capture_config_files(active.path)
        settings_before = app.SETTINGS_FILE.read_bytes()
        executable = Path(r"C:\Codex\Codex.exe")
        running = app.CodexRestartTarget(root_pid=100, executable=executable)
        records = [app.ProcessRecord(100, 50, executable)]
        recovered = app.CodexLaunchResult(target=running, action="restart")

        with (
            patch.object(app, "list_windows_processes", return_value=records),
            patch.object(app, "discover_codex_installation", return_value=None),
            patch.object(app, "request_codex_normal_exit", return_value=True),
            patch.object(app, "remove_stale_codex_tray_registration"),
            patch.object(app, "is_codex_application_running", return_value=False),
            patch.object(
                app,
                "launch_codex_application",
                side_effect=[app.CodexRestartError("injected start failure"), recovered],
            ) as launch,
        ):
            with self.assertRaises(app.CodexRestartError) as raised:
                app.switch_saved_profile(
                    self.config_dir,
                    target_profile.path,
                    allow_running_restart=True,
                )

        self.assertIn("原配置已恢复", str(raised.exception))
        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(active_before, app.capture_config_files(active.path))
        self.assertEqual(settings_before, app.SETTINGS_FILE.read_bytes())
        self.assertEqual(2, launch.call_count)
        self.assertEqual("restart", launch.call_args_list[1].args[1])

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

    def test_model_display_name_uses_real_model_slug_and_syncs_active_profile(self) -> None:
        active = self.create_profile("DeepSeek", "DeepSeek", model="deepseek-chat")

        updated = app.save_active_model_display_name(self.config_dir, "DS")

        self.assertEqual(active.path, updated.path)
        for target in (self.config_dir, active.path):
            config_text = (target / "config.toml").read_text(encoding="utf-8")
            self.assertIn('model = "deepseek-chat"', config_text)
            self.assertIn(
                f'model_catalog_json = "{app.MODEL_CATALOG_FILENAME}"',
                config_text,
            )
            catalog = json.loads((target / app.MODEL_CATALOG_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual("deepseek-chat", catalog["models"][0]["slug"])
            self.assertEqual("DS", catalog["models"][0]["display_name"])
            self.assertEqual("DS", app.read_codex_config(target).model_display_name)

    def test_model_display_name_never_overwrites_external_catalog(self) -> None:
        self.write_config(self.config_dir, "Provider A", model="deepseek-chat")
        config_path = self.config_dir / "config.toml"
        original = 'model_catalog_json = "my-models.json"\n' + config_path.read_text(encoding="utf-8")
        config_path.write_text(original, encoding="utf-8")

        with self.assertRaises(app.ConfigConflictError):
            app.save_active_model_display_name(self.config_dir, "DS")

        self.assertEqual(original, config_path.read_text(encoding="utf-8"))
        self.assertFalse((self.config_dir / app.MODEL_CATALOG_FILENAME).exists())

    def test_model_selection_preserves_full_owned_catalog_in_current_and_profile(self) -> None:
        active = self.create_profile("DeepSeek", "DeepSeek", model="deepseek-v4-pro")
        models = ["deepseek-v4-pro", "deepseek-v4-flash"]
        app.update_owned_model_catalog_models(self.config_dir, models)
        app.update_owned_model_catalog_models(active.path, models)
        app.set_active_profile_path(active.path)

        app.save_active_model(self.config_dir, "deepseek-v4-flash")

        for target in (self.config_dir, active.path):
            self.assertEqual("deepseek-v4-flash", app.read_codex_config(target).model)
            self.assertEqual(models, app.read_owned_model_catalog_models(target))
            self.assertIn("model_catalog_json", (target / "config.toml").read_text(encoding="utf-8"))

    def test_model_catalog_exposes_standard_reasoning_choices_instead_of_only_current_value(self) -> None:
        self.write_config(self.config_dir, "Provider A", model="gpt-5.6-sol")
        config_path = self.config_dir / "config.toml"
        lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
        lines = app.replace_or_insert_top_level(lines, "model_reasoning_effort", "medium")

        model = app.build_model_catalog("gpt-5.6-sol", "GPT 5.6 Sol", lines)["models"][0]

        self.assertEqual("medium", model["default_reasoning_level"])
        self.assertEqual(
            ["low", "medium", "high", "xhigh"],
            [item["effort"] for item in model["supported_reasoning_levels"]],
        )

    def test_native_model_slug_reuses_complete_codex_metadata(self) -> None:
        native_entry = {
            "slug": "gpt-5.5",
            "display_name": "GPT-5.5",
            "description": "Native Codex model",
            "default_reasoning_level": "medium",
            "supported_reasoning_levels": [
                {"effort": "low", "description": "Fast"},
                {"effort": "high", "description": "Deep"},
            ],
            "supported_in_api": True,
            "priority": 7,
            "nested_capability": {"enabled": True, "modes": ["text", "image"]},
        }
        self.write_config(self.config_dir, "Provider A", model="gpt-5.5")
        self.write_native_model_cache([native_entry])

        app.update_owned_model_catalog_models(self.config_dir, ["gpt-5.5"])

        self.assertEqual(native_entry, self.read_owned_catalog(self.config_dir)["models"][0])

    def test_gpt_prefix_without_exact_native_slug_uses_generated_metadata(self) -> None:
        self.write_config(self.config_dir, "Provider A", model="gpt-5.6-custom")
        self.write_native_model_cache(
            [{"slug": "gpt-5.5", "display_name": "Native GPT", "priority": 1}]
        )

        app.update_owned_model_catalog_models(self.config_dir, ["gpt-5.6-custom"])

        entry = self.read_owned_catalog(self.config_dir)["models"][0]
        self.assertEqual("gpt-5.6-custom", entry["slug"])
        self.assertEqual("Gpt 5.6 Custom", entry["display_name"])
        self.assertEqual(1000, entry["priority"])

    def test_native_model_slug_matching_is_case_sensitive(self) -> None:
        self.write_config(self.config_dir, "Provider A", model="GPT-5.5")
        self.write_native_model_cache(
            [{"slug": "gpt-5.5", "display_name": "Native GPT", "priority": 1}]
        )

        app.update_owned_model_catalog_models(self.config_dir, ["GPT-5.5"])

        entry = self.read_owned_catalog(self.config_dir)["models"][0]
        self.assertEqual("GPT-5.5", entry["slug"])
        self.assertEqual(1000, entry["priority"])

    def test_mixed_catalog_uses_native_and_generated_entries(self) -> None:
        native_entry = {
            "slug": "gpt-5.5",
            "display_name": "GPT-5.5 Native",
            "default_reasoning_level": "high",
            "supported_reasoning_levels": [{"effort": "high", "description": "Native"}],
            "priority": 3,
        }
        self.write_config(self.config_dir, "Provider A", model="deepseek-v4-flash")
        self.write_native_model_cache([native_entry])

        app.update_owned_model_catalog_models(
            self.config_dir,
            ["gpt-5.5", "deepseek-v4-flash"],
        )

        entries = {entry["slug"]: entry for entry in self.read_owned_catalog(self.config_dir)["models"]}
        self.assertEqual(native_entry, entries["gpt-5.5"])
        self.assertEqual("Deepseek V4 Flash", entries["deepseek-v4-flash"]["display_name"])
        self.assertEqual(
            ["low", "medium", "high", "xhigh"],
            [item["effort"] for item in entries["deepseek-v4-flash"]["supported_reasoning_levels"]],
        )

    def test_saved_profile_uses_native_cache_from_live_config_root(self) -> None:
        native_entry = {
            "slug": "gpt-5.5",
            "display_name": "GPT-5.5 Native",
            "default_reasoning_level": "medium",
            "supported_reasoning_levels": [{"effort": "medium", "description": "Native"}],
            "priority": 5,
        }
        active = self.create_profile("Provider A", "Provider A", model="gpt-5.5")
        self.write_native_model_cache([native_entry])
        app.set_active_profile_path(active.path)

        app.save_available_models(self.config_dir, ["gpt-5.5"])

        self.assertEqual(native_entry, self.read_owned_catalog(self.config_dir)["models"][0])
        self.assertEqual(native_entry, self.read_owned_catalog(active.path)["models"][0])
        self.assertFalse((active.path / app.CODEX_NATIVE_MODEL_CACHE_FILENAME).exists())

    def test_official_provider_removes_owned_catalog_but_preserves_external_catalog(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.config_dir / "config.toml"
        config_path.write_text(
            'model_provider = "openai"\n'
            'model = "gpt-5.5"\n'
            f'model_catalog_json = "{app.MODEL_CATALOG_FILENAME}"\n',
            encoding="utf-8",
        )
        owned_path = self.config_dir / app.MODEL_CATALOG_FILENAME
        owned_path.write_text('{"models": [{"slug": "gpt-5.5"}]}\n', encoding="utf-8")

        app.update_owned_model_catalog_models(self.config_dir, ["gpt-5.5"])

        self.assertNotIn("model_catalog_json", config_path.read_text(encoding="utf-8"))
        self.assertFalse(owned_path.exists())

        external_path = self.config_dir / "user-models.json"
        external_bytes = b'{"models": [{"slug": "user-model"}]}\n'
        external_path.write_bytes(external_bytes)
        config_path.write_text(
            'model_provider = "openai"\n'
            'model = "gpt-5.5"\n'
            'model_catalog_json = "user-models.json"\n',
            encoding="utf-8",
        )
        owned_path.write_text('{"stale": true}\n', encoding="utf-8")

        app.update_owned_model_catalog_models(self.config_dir, ["gpt-5.5"])

        self.assertEqual("user-models.json", app.get_top_level_value(
            config_path.read_text(encoding="utf-8").splitlines(keepends=True),
            "model_catalog_json",
        ))
        self.assertEqual(external_bytes, external_path.read_bytes())
        self.assertTrue(owned_path.exists())

    def test_missing_or_malformed_native_cache_falls_back_to_generated_metadata(self) -> None:
        for malformed in (False, True):
            with self.subTest(malformed=malformed):
                case_dir = self.root / f"cache-{malformed}"
                self.write_config(case_dir, "Provider A", model="gpt-5.6-custom")
                if malformed:
                    (case_dir / app.CODEX_NATIVE_MODEL_CACHE_FILENAME).write_text(
                        "{broken",
                        encoding="utf-8",
                    )

                app.update_owned_model_catalog_models(case_dir, ["gpt-5.6-custom"])

                entry = self.read_owned_catalog(case_dir)["models"][0]
                self.assertEqual("gpt-5.6-custom", entry["slug"])
                self.assertEqual(1000, entry["priority"])

    def test_switch_upgrades_legacy_reasoning_metadata_in_live_catalog_only(self) -> None:
        target = self.create_profile("Provider B", "Provider B", model="gpt-5.6-sol")
        target_config = target.path / "config.toml"
        target_lines = target_config.read_text(encoding="utf-8").splitlines(keepends=True)
        target_config.write_text(
            "".join(app.replace_or_insert_top_level(target_lines, "model_reasoning_effort", "medium")),
            encoding="utf-8",
        )
        legacy_catalog = app.build_model_catalog("gpt-5.6-sol", "GPT 5.6 Sol", target_lines)
        legacy_model = legacy_catalog["models"][0]
        legacy_model["supported_reasoning_levels"] = [
            {"effort": "none", "description": "Disable reasoning"},
            {"effort": "medium", "description": "Use configured reasoning effort"},
        ]
        legacy_bytes = (json.dumps(legacy_catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (target.path / app.MODEL_CATALOG_FILENAME).write_bytes(legacy_bytes)
        target_config.write_text(
            f'model_catalog_json = "{app.MODEL_CATALOG_FILENAME}"\n' + target_config.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        app.apply_saved_profile(self.config_dir, target.path)

        live_catalog = json.loads((self.config_dir / app.MODEL_CATALOG_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(
            ["low", "medium", "high", "xhigh"],
            [item["effort"] for item in live_catalog["models"][0]["supported_reasoning_levels"]],
        )
        self.assertEqual("medium", live_catalog["models"][0]["default_reasoning_level"])
        self.assertEqual(legacy_bytes, (target.path / app.MODEL_CATALOG_FILENAME).read_bytes())

    def test_switch_refreshes_native_entry_and_upgrades_only_generated_entry(self) -> None:
        target = self.create_profile("Mixed", "Provider B", model="gpt-5.5")
        target_config = target.path / "config.toml"
        target_lines = target_config.read_text(encoding="utf-8").splitlines(keepends=True)
        target_config.write_text(
            "".join(app.replace_or_insert_top_level(target_lines, "model_reasoning_effort", "medium")),
            encoding="utf-8",
        )
        source_catalog = {
            "models": [
                app.build_model_catalog("gpt-5.5", "Generated GPT", target_lines)["models"][0],
                app.build_model_catalog("deepseek-v4-flash", "DeepSeek", target_lines)["models"][0],
            ]
        }
        source_catalog["models"][1]["supported_reasoning_levels"] = [
            {"effort": "medium", "description": "Legacy"}
        ]
        source_bytes = (json.dumps(source_catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (target.path / app.MODEL_CATALOG_FILENAME).write_bytes(source_bytes)
        target_config.write_text(
            f'model_catalog_json = "{app.MODEL_CATALOG_FILENAME}"\n'
            + target_config.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        native_entry = {
            "slug": "gpt-5.5",
            "display_name": "GPT-5.5 Native",
            "default_reasoning_level": "high",
            "supported_reasoning_levels": [{"effort": "high", "description": "Native"}],
            "priority": 2,
            "native_only": {"value": True},
        }
        self.write_native_model_cache([native_entry])

        app.apply_saved_profile(self.config_dir, target.path)

        live_entries = {
            entry["slug"]: entry
            for entry in self.read_owned_catalog(self.config_dir)["models"]
        }
        self.assertEqual(native_entry, live_entries["gpt-5.5"])
        self.assertEqual(
            ["low", "medium", "high", "xhigh"],
            [
                item["effort"]
                for item in live_entries["deepseek-v4-flash"]["supported_reasoning_levels"]
            ],
        )
        self.assertEqual(source_bytes, (target.path / app.MODEL_CATALOG_FILENAME).read_bytes())

    def test_switch_to_official_provider_ignores_historical_owned_catalog(self) -> None:
        target = self.create_profile("Official", "Provider B", model="gpt-5.5")
        target_config = target.path / "config.toml"
        target_config.write_text(
            'model_provider = "openai"\n'
            'model = "gpt-5.5"\n'
            f'model_catalog_json = "{app.MODEL_CATALOG_FILENAME}"\n',
            encoding="utf-8",
        )
        source_catalog_bytes = b'{"models": [{"slug": "gpt-5.5"}]}\n'
        (target.path / app.MODEL_CATALOG_FILENAME).write_bytes(source_catalog_bytes)
        self.write_config(self.config_dir, "Provider A", model="deepseek-v4-flash")
        app.update_owned_model_catalog_models(self.config_dir, ["deepseek-v4-flash"])

        app.apply_saved_profile(self.config_dir, target.path)

        live_config = (self.config_dir / "config.toml").read_text(encoding="utf-8")
        self.assertEqual("openai", app.read_codex_config(self.config_dir).provider)
        self.assertNotIn("model_catalog_json", live_config)
        self.assertFalse((self.config_dir / app.MODEL_CATALOG_FILENAME).exists())
        self.assertEqual(source_catalog_bytes, (target.path / app.MODEL_CATALOG_FILENAME).read_bytes())

    def test_switch_restores_target_full_catalog_and_default_reasoning_effort(self) -> None:
        self.write_config(self.config_dir, "DeepSeek", model="deepseek-v4-flash")
        config_path = self.config_dir / "config.toml"
        lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
        config_path.write_text("".join(app.replace_or_insert_top_level(lines, "model_reasoning_effort", "high")), encoding="utf-8")
        app.update_owned_model_catalog_models(self.config_dir, ["deepseek-v4-pro", "deepseek-v4-flash"])
        profile_a = app.create_named_backup(self.config_dir, "DeepSeek")

        self.write_config(self.config_dir, "Sol", model="gpt-5.6-sol")
        lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
        config_path.write_text("".join(app.replace_or_insert_top_level(lines, "model_reasoning_effort", "medium")), encoding="utf-8")
        target_models = ["gpt-5.5-sol", "gpt-5.6-sol"]
        app.update_owned_model_catalog_models(self.config_dir, target_models)
        profile_b = app.create_named_backup(self.config_dir, "Sol")

        app.apply_saved_profile(self.config_dir, profile_a.path)
        app.set_active_profile_path(profile_a.path)
        app.apply_saved_profile(self.config_dir, profile_b.path)

        live_lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
        self.assertEqual("gpt-5.6-sol", app.read_codex_config(self.config_dir).model)
        self.assertEqual("medium", app.get_top_level_value(live_lines, "model_reasoning_effort"))
        self.assertEqual(target_models, app.read_owned_model_catalog_models(self.config_dir))
        self.assertNotIn("deepseek-v4-flash", app.read_owned_model_catalog_models(self.config_dir))

    def test_switch_to_profile_without_catalog_clears_previous_owned_catalog(self) -> None:
        source = self.create_profile("With models", "Provider A", model="a-model")
        app.update_owned_model_catalog_models(self.config_dir, ["a-model", "a-other"])
        app.update_owned_model_catalog_models(source.path, ["a-model", "a-other"])
        target = self.create_profile("Without models", "Provider B", model="b-model")

        app.apply_saved_profile(self.config_dir, source.path)
        app.apply_saved_profile(self.config_dir, target.path)

        text = (self.config_dir / "config.toml").read_text(encoding="utf-8")
        self.assertNotIn("model_catalog_json", text)
        self.assertFalse((self.config_dir / app.MODEL_CATALOG_FILENAME).exists())

    def test_save_available_models_rolls_back_current_and_profile_on_failure(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-model")
        app.set_active_profile_path(active.path)
        current_before = app.capture_config_files(self.config_dir)
        profile_before = app.capture_config_files(active.path)
        real_update = app.update_owned_model_catalog_models
        calls = 0

        def fail_second(
            target: Path,
            models: list[str],
            native_catalog_dir: Path | None = None,
        ) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second write failure")
            real_update(target, models, native_catalog_dir=native_catalog_dir)

        with patch.object(app, "update_owned_model_catalog_models", side_effect=fail_second):
            with self.assertRaises(OSError):
                app.save_available_models(self.config_dir, ["a-model", "a-other"])

        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(profile_before, app.capture_config_files(active.path))

    def test_save_available_models_rolls_back_on_profile_catalog_conflict(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-model")
        app.set_active_profile_path(active.path)
        profile_config = active.path / "config.toml"
        lines = profile_config.read_text(encoding="utf-8").splitlines(keepends=True)
        profile_config.write_text(
            "".join(app.replace_or_insert_top_level(lines, "model_catalog_json", "user-models.json")),
            encoding="utf-8",
        )
        current_before = app.capture_config_files(self.config_dir)
        profile_before = app.capture_config_files(active.path)

        with self.assertRaises(app.ConfigConflictError):
            app.save_available_models(
                self.config_dir,
                ["a-model", "a-other"],
                profile_dir=active.path,
            )

        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(profile_before, app.capture_config_files(active.path))

    def test_save_active_model_rolls_back_when_owned_catalog_is_malformed(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-model")
        app.update_owned_model_catalog_models(self.config_dir, ["a-model", "a-other"])
        app.update_owned_model_catalog_models(active.path, ["a-model", "a-other"])
        app.set_active_profile_path(active.path)
        (active.path / app.MODEL_CATALOG_FILENAME).write_text("{broken", encoding="utf-8")
        current_before = app.capture_config_files(self.config_dir)
        profile_before = app.capture_config_files(active.path)

        with self.assertRaises(app.ConfigConflictError):
            app.save_active_model(self.config_dir, "a-other")

        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(profile_before, app.capture_config_files(active.path))

    def test_sync_rolls_back_profile_when_live_owned_catalog_is_malformed(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-model")
        app.update_owned_model_catalog_models(self.config_dir, ["a-model", "a-other"])
        app.update_owned_model_catalog_models(active.path, ["a-model", "a-other"])
        app.set_active_profile_path(active.path)
        (self.config_dir / app.MODEL_CATALOG_FILENAME).write_text("{broken", encoding="utf-8")
        profile_before = app.capture_config_files(active.path)

        with self.assertRaises(app.ConfigConflictError):
            app.sync_current_to_active_profile(self.config_dir)

        self.assertEqual(profile_before, app.capture_config_files(active.path))

    def test_switch_rejects_owned_catalog_missing_default_model_without_live_changes(self) -> None:
        target = self.create_profile("Provider B", "Provider B", model="b-model")
        app.update_owned_model_catalog_models(target.path, ["b-model", "b-other"])
        catalog_path = target.path / app.MODEL_CATALOG_FILENAME
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["models"] = [entry for entry in catalog["models"] if entry["slug"] != "b-model"]
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        current_before = app.capture_config_files(self.config_dir)

        with self.assertRaises(app.ConfigConflictError):
            app.apply_saved_profile(self.config_dir, target.path)

        self.assertEqual(current_before, app.capture_config_files(self.config_dir))

    def test_create_profile_persists_available_models_without_inheriting_current_catalog(self) -> None:
        self.write_config(self.config_dir, "Provider A", model="a-model")
        app.update_owned_model_catalog_models(self.config_dir, ["a-model", "a-other"])

        saved = app.create_config_profile(
            self.config_dir,
            "Provider B",
            "key-b",
            "Provider B",
            "https://provider-b.example.com/v1",
            "b-model",
            apply_to_current=True,
            available_models=["b-model", "b-other"],
        )

        self.assertEqual(["b-model", "b-other"], app.read_owned_model_catalog_models(saved.path))
        self.assertEqual(["b-model", "b-other"], app.read_owned_model_catalog_models(self.config_dir))
        self.assertNotIn("a-other", app.read_owned_model_catalog_models(saved.path))

    def test_openai_profile_ignores_fetched_models_and_keeps_native_config(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "auth.json").write_text('{"OPENAI_API_KEY": "key-openai"}\n', encoding="utf-8")
        (self.config_dir / "config.toml").write_text(
            'model_provider = "openai"\n'
            'model = "gpt-5.6-sol"\n'
            'model_reasoning_effort = "medium"\n',
            encoding="utf-8",
        )
        app.save_available_models(self.config_dir, ["gpt-5.6-sol", "gpt-5.6-terra"])

        config_text = (self.config_dir / "config.toml").read_text(encoding="utf-8")
        self.assertNotIn("model_catalog_json", config_text)
        self.assertFalse((self.config_dir / app.MODEL_CATALOG_FILENAME).exists())
        self.assertEqual("gpt-5.6-sol", app.read_codex_config(self.config_dir).model)
        config_lines = config_text.splitlines(keepends=True)
        self.assertEqual("medium", app.get_top_level_value(config_lines, "model_reasoning_effort"))

    def test_saved_profile_switch_restores_owned_model_catalog(self) -> None:
        deepseek = self.create_profile("DeepSeek", "DeepSeek", model="deepseek-chat")
        app.save_active_model_display_name(self.config_dir, "DS")
        other = self.create_profile("Other", "Other", model="other-model")

        app.apply_saved_profile(self.config_dir, other.path)
        self.assertEqual("", app.read_codex_config(self.config_dir).model_display_name)
        self.assertFalse((self.config_dir / app.MODEL_CATALOG_FILENAME).exists())

        app.apply_saved_profile(self.config_dir, deepseek.path)
        current = app.read_codex_config(self.config_dir)
        self.assertEqual("deepseek-chat", current.model)
        self.assertEqual("DS", current.model_display_name)

    def test_model_display_name_rolls_back_current_and_profile_on_failure(self) -> None:
        active = self.create_profile("DeepSeek", "DeepSeek", model="deepseek-chat")
        current_before = app.capture_config_files(self.config_dir)
        profile_before = app.capture_config_files(active.path)
        real_write = app.write_text

        def fail_current_config(path: Path, content: str) -> None:
            if path == self.config_dir / "config.toml" and "model_catalog_json" in content:
                raise OSError("injected catalog config failure")
            real_write(path, content)

        with patch.object(app, "write_text", side_effect=fail_current_config):
            with self.assertRaises(OSError):
                app.save_active_model_display_name(self.config_dir, "DS")

        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(profile_before, app.capture_config_files(active.path))

    def test_sync_does_not_overwrite_active_profile_when_provider_identity_changed(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-model")
        app.set_active_profile_path(active.path)
        before = app.capture_config_files(active.path)
        self.write_config(self.config_dir, "Unsaved Provider", model="other-model", api_key="other-key")

        self.assertIsNone(app.sync_current_to_active_profile(self.config_dir))
        self.assertEqual(before, app.capture_config_files(active.path))

    def test_switch_projects_external_catalog_reference_without_copying_or_deleting_it(self) -> None:
        target = self.create_profile("External", "Provider B", model="b-model")
        target_config = target.path / "config.toml"
        lines = target_config.read_text(encoding="utf-8").splitlines(keepends=True)
        target_config.write_text(
            "".join(app.replace_or_insert_top_level(lines, "model_catalog_json", "user-models.json")),
            encoding="utf-8",
        )
        external = target.path / "user-models.json"
        external.write_text('{"models": [{"slug": "b-model"}]}\n', encoding="utf-8")
        app.update_owned_model_catalog_models(self.config_dir, ["old-model"])

        app.apply_saved_profile(self.config_dir, target.path)

        live_lines = (self.config_dir / "config.toml").read_text(encoding="utf-8").splitlines(keepends=True)
        self.assertEqual("user-models.json", app.get_top_level_value(live_lines, "model_catalog_json"))
        self.assertFalse((self.config_dir / app.MODEL_CATALOG_FILENAME).exists())
        self.assertTrue(external.exists())

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
        app.save_active_model_display_name(self.config_dir, "Model A")

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
        self.assertNotIn("model_catalog_json", config_text)
        self.assertFalse((self.config_dir / app.MODEL_CATALOG_FILENAME).exists())
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


    def test_pending_active_profile_path_ignores_missing_or_external_paths(self) -> None:
        active = self.create_profile("Provider A", "Provider A")
        app.set_pending_active_profile_path(active.path)
        self.assertEqual(
            app.normalized_path_key(active.path),
            app.normalized_path_key(app.pending_active_profile_path(self.config_dir)),
        )

        app.delete_backups(self.config_dir, [active.path])
        self.assertIsNone(app.pending_active_profile_path(self.config_dir))

        external = self.root / "external-profile"
        external.mkdir()
        app.save_setting_value(app.PENDING_ACTIVE_PROFILE_PATH_KEY, str(external))
        self.assertIsNone(app.pending_active_profile_path(self.config_dir))

    def test_profile_model_catalog_is_replaced_only_when_saved(self) -> None:
        saved = app.create_config_profile(
            self.config_dir,
            "Provider A",
            "key-a",
            "Provider A",
            "https://provider-a.example.com/v1",
            "a-old",
            available_models=["a-old", "a-legacy"],
        )
        self.assertEqual(["a-old", "a-legacy"], app.read_owned_model_catalog_models(saved.path))

        edited = app.update_config_profile(
            self.config_dir,
            saved.path,
            "Provider A",
            "key-a",
            "Provider A",
            "https://provider-a.example.com/v1",
            "a-manual",
            available_models=["a-new", "a-fast"],
        )

        self.assertEqual(
            ["a-manual", "a-new", "a-fast"],
            app.read_owned_model_catalog_models(edited.path),
        )
        self.assertNotIn("a-legacy", app.read_owned_model_catalog_models(edited.path))

    def test_current_page_model_is_readonly_and_profile_editor_has_single_save_action(self) -> None:
        source = Path(app.__file__).read_text(encoding="utf-8")
        self.assertIn('self._readonly_field(details, 3, "启动默认模型", self.model_var)', source)
        self.assertNotIn('text="保存并使用"', source)
        self.assertNotIn('text="保存并应用"', source)
        self.assertNotIn("def fetch_models(self)", source)
        self.assertIn("self.center_window(dialog, 570, 385)", source)
        self.assertIn('button_row.grid(row=7, column=0, columnspan=3', source)
        self.assertIn("OpenAI 原生模型无需获取列表", source)
        self.assertIn("“获取模型”仅用于第三方 Provider", source)
        self.assertIn('JM2API_CHANNEL_URL = "https://jm2api.lol"', source)
        self.assertIn('JM2API_ICON_NAME = "jm2api.png"', source)
        self.assertIn('add_channel("JM2 API", JM2API_CHANNEL_URL, icon_image=self.jm2api_icon_image)', source)

    def test_switching_current_profile_when_stopped_syncs_then_starts(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-model")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        app.save_active_model(self.config_dir, "a-latest")
        installed = app.CodexRestartTarget(root_pid=0, executable=Path(r"C:\Codex\Codex.exe"))
        launch_result = app.CodexLaunchResult(target=installed, action="start")
        events = []
        real_sync = app.sync_current_to_active_profile
        real_restore = app.restore_backup

        with (
            patch.object(app, "list_windows_processes", return_value=[]),
            patch.object(app, "discover_codex_installation", return_value=installed),
            patch.object(app, "sync_current_to_active_profile", side_effect=lambda path: events.append("sync") or real_sync(path)),
            patch.object(app, "restore_backup", side_effect=lambda path, target: events.append("restore") or real_restore(path, target)),
            patch.object(app, "launch_codex_application", side_effect=lambda target, action: events.append("launch") or launch_result),
        ):
            result = app.switch_saved_profile(self.config_dir, active.path)

        self.assertEqual("start", result.action)
        self.assertEqual(["sync", "restore", "launch"], events)
        self.assertEqual("a-latest", app.read_codex_config(active.path).model)
        self.assertEqual("a-latest", app.read_codex_config(self.config_dir).model)

    def test_pending_current_profile_when_stopped_applies_without_reverse_sync(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-old")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        edited = app.update_config_profile(
            self.config_dir,
            active.path,
            "Provider A",
            "key-new",
            "Provider A",
            "https://provider-a.example.com/v1",
            "a-new",
            apply_to_current=False,
            available_models=["a-new", "a-other"],
        )
        app.set_active_profile_path(edited.path)
        app.set_pending_active_profile_path(edited.path)
        installed = app.CodexRestartTarget(root_pid=0, executable=Path(r"C:\Codex\Codex.exe"))
        launch_result = app.CodexLaunchResult(target=installed, action="start")
        events = []
        real_restore = app.restore_backup

        with (
            patch.object(app, "list_windows_processes", return_value=[]),
            patch.object(app, "discover_codex_installation", return_value=installed),
            patch.object(app, "sync_current_to_active_profile") as sync_current,
            patch.object(app, "restore_backup", side_effect=lambda path, target: events.append("restore") or real_restore(path, target)),
            patch.object(app, "launch_codex_application", side_effect=lambda target, action: events.append("launch") or launch_result),
        ):
            result = app.switch_saved_profile(self.config_dir, edited.path)

        self.assertEqual("start", result.action)
        self.assertEqual(["restore", "launch"], events)
        sync_current.assert_not_called()
        self.assertEqual("a-new", app.read_codex_config(self.config_dir).model)
        self.assertEqual(["a-new", "a-other"], app.read_owned_model_catalog_models(self.config_dir))
        self.assertIsNone(app.pending_active_profile_path(self.config_dir))

    def test_pending_current_profile_when_running_exits_applies_and_restarts(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-old")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        edited = app.update_config_profile(
            self.config_dir,
            active.path,
            "Provider A",
            "key-new",
            "Provider A",
            "https://provider-a.example.com/v1",
            "a-new",
            apply_to_current=False,
        )
        app.set_active_profile_path(edited.path)
        app.set_pending_active_profile_path(edited.path)
        executable = Path(r"C:\Codex\Codex.exe")
        running = app.CodexRestartTarget(root_pid=100, executable=executable)
        records = [app.ProcessRecord(100, 50, executable)]
        launch_result = app.CodexLaunchResult(target=running, action="restart")
        events = []
        real_restore = app.restore_backup

        with (
            patch.object(app, "list_windows_processes", return_value=records),
            patch.object(app, "discover_codex_installation", return_value=None),
            patch.object(app, "request_codex_normal_exit", side_effect=lambda target: events.append("exit") or True),
            patch.object(app, "remove_stale_codex_tray_registration", side_effect=lambda target: events.append("tray")),
            patch.object(app, "sync_current_to_active_profile") as sync_current,
            patch.object(app, "restore_backup", side_effect=lambda path, target: events.append("restore") or real_restore(path, target)),
            patch.object(app, "launch_codex_application", side_effect=lambda target, action: events.append("launch") or launch_result),
        ):
            result = app.switch_saved_profile(
                self.config_dir,
                edited.path,
                allow_running_restart=True,
            )

        self.assertEqual("restart", result.action)
        self.assertEqual(["exit", "tray", "restore", "launch"], events)
        sync_current.assert_not_called()
        self.assertEqual("a-new", app.read_codex_config(self.config_dir).model)
        self.assertIsNone(app.pending_active_profile_path(self.config_dir))

    def test_switching_away_from_pending_profile_does_not_overwrite_edited_library_copy(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-old")
        target = self.create_profile("Provider B", "Provider B", model="b-model")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        edited = app.update_config_profile(
            self.config_dir,
            active.path,
            "Provider A",
            "key-new",
            "Provider A",
            "https://provider-a.example.com/v1",
            "a-new",
            apply_to_current=False,
        )
        app.set_active_profile_path(edited.path)
        app.set_pending_active_profile_path(edited.path)
        installed = app.CodexRestartTarget(root_pid=0, executable=Path(r"C:\Codex\Codex.exe"))
        launch_result = app.CodexLaunchResult(target=installed, action="start")

        with (
            patch.object(app, "list_windows_processes", return_value=[]),
            patch.object(app, "discover_codex_installation", return_value=installed),
            patch.object(app, "launch_codex_application", return_value=launch_result),
        ):
            app.switch_saved_profile(self.config_dir, target.path)

        self.assertEqual("a-new", app.read_codex_config(edited.path).model)
        self.assertEqual("b-model", app.read_codex_config(self.config_dir).model)
        self.assertIsNone(app.pending_active_profile_path(self.config_dir))

    def test_pending_profile_projection_failure_restores_live_library_and_settings(self) -> None:
        active = self.create_profile("Provider A", "Provider A", model="a-old")
        app.apply_saved_profile(self.config_dir, active.path)
        app.set_active_profile_path(active.path)
        edited = app.update_config_profile(
            self.config_dir,
            active.path,
            "Provider A",
            "key-new",
            "Provider A",
            "https://provider-a.example.com/v1",
            "a-new",
            apply_to_current=False,
        )
        app.set_active_profile_path(edited.path)
        app.set_pending_active_profile_path(edited.path)
        current_before = app.capture_config_files(self.config_dir)
        profile_before = app.capture_config_files(edited.path)
        settings_before = app.SETTINGS_FILE.read_bytes()
        installed = app.CodexRestartTarget(root_pid=0, executable=Path(r"C:\Codex\Codex.exe"))

        with (
            patch.object(app, "list_windows_processes", return_value=[]),
            patch.object(app, "discover_codex_installation", return_value=installed),
            patch.object(app, "sync_current_to_active_profile") as sync_current,
            patch.object(app, "restore_backup", side_effect=app.ConfigConflictError("injected projection failure")),
        ):
            with self.assertRaises(app.ConfigConflictError):
                app.switch_saved_profile(self.config_dir, edited.path)

        sync_current.assert_not_called()
        self.assertEqual(current_before, app.capture_config_files(self.config_dir))
        self.assertEqual(profile_before, app.capture_config_files(edited.path))
        self.assertEqual(settings_before, app.SETTINGS_FILE.read_bytes())
        self.assertEqual(
            app.normalized_path_key(edited.path),
            app.normalized_path_key(app.pending_active_profile_path(self.config_dir)),
        )


if __name__ == "__main__":
    unittest.main()
