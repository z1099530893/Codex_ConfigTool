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

    def test_restore_default_does_not_create_a_profile_or_delete_other_data(self) -> None:
        self.write_config(self.config_dir, "A")
        sessions = self.config_dir / "sessions"
        sessions.mkdir()
        marker = sessions / "keep.txt"
        marker.write_text("keep", encoding="utf-8")

        app.restore_default_config(self.config_dir)

        self.assertFalse((self.config_dir / "auth.json").exists())
        self.assertFalse((self.config_dir / "config.toml").exists())
        self.assertEqual("keep", marker.read_text(encoding="utf-8"))
        self.assertEqual([], app.list_backup_records(self.config_dir))

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

    def test_onboarding_is_automatic_until_explicitly_disabled(self) -> None:
        self.assertTrue(app.should_show_onboarding({}))
        self.assertTrue(app.should_show_onboarding({app.ONBOARDING_SHOWN_KEY: False}))
        self.assertTrue(app.should_show_onboarding({app.ONBOARDING_SHOWN_KEY: True}))

    def test_only_explicit_hide_setting_disables_onboarding(self) -> None:
        self.assertFalse(app.should_show_onboarding({app.HIDE_ONBOARDING_KEY: True}))
        self.assertTrue(app.should_show_onboarding({app.HIDE_ONBOARDING_KEY: False}))


if __name__ == "__main__":
    unittest.main()
