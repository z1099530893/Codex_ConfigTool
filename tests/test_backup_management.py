import json
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

    def tearDown(self) -> None:
        self.settings_file_patch.stop()
        self.settings_dir_patch.stop()
        self.temp_dir.cleanup()

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

    def test_switching_between_a_and_b_reuses_existing_named_backups(self) -> None:
        self.write_config(self.config_dir, "A", "https://a.example.com/v1")

        first = app.save_codex_config(
            self.config_dir,
            "test-key",
            "B",
            "https://b.example.com/v1",
            "gpt-5.4",
            "A",
        )
        second = app.save_codex_config(
            self.config_dir,
            "test-key",
            "A",
            "https://a.example.com/v1",
            "gpt-5.4",
            "B",
        )
        third = app.save_codex_config(
            self.config_dir,
            "test-key",
            "B",
            "https://b.example.com/v1",
            "gpt-5.4",
            "A",
        )

        self.assertEqual("created", first.status)
        self.assertEqual("created", second.status)
        self.assertEqual("reused", third.status)
        self.assertEqual({"A", "B"}, {record.name for record in app.list_backup_records(self.config_dir)})
        self.assertEqual(2, len(app.list_backup_records(self.config_dir)))

    def test_deduplication_ignores_codex_managed_state(self) -> None:
        self.write_config(self.config_dir, "A")
        created = app.create_or_reuse_backup(self.config_dir, "A")
        self.write_config(
            self.config_dir,
            "A",
            extra_config='[desktop]\nwindow_state = "changed"',
            extra_auth={"tokens": {"access_token": "changed"}},
        )

        reused = app.create_or_reuse_backup(self.config_dir, "A")

        self.assertEqual("created", created.status)
        self.assertEqual("reused", reused.status)
        self.assertEqual(created.record.path, reused.record.path)

    def test_same_name_with_different_core_config_is_rejected(self) -> None:
        self.write_config(self.config_dir, "A", model="gpt-5.4")
        app.create_or_reuse_backup(self.config_dir, "A")
        self.write_config(self.config_dir, "A", model="gpt-5.5")

        with self.assertRaises(app.BackupNameConflictError):
            app.create_or_reuse_backup(self.config_dir, "A")

    def test_unreadable_core_config_is_never_reused_automatically(self) -> None:
        self.write_config(self.config_dir, "A")
        (self.config_dir / "auth.json").write_text("{invalid", encoding="utf-8")
        first = app.create_or_reuse_backup(self.config_dir, "A")

        with self.assertRaises(app.BackupNameConflictError):
            app.create_or_reuse_backup(self.config_dir, "A")

        self.assertEqual("created", first.status)

    def test_no_existing_config_skips_backup(self) -> None:
        result = app.create_or_reuse_backup(self.config_dir, None)

        self.assertEqual("not_needed", result.status)
        self.assertIsNone(result.record)
        self.assertFalse((self.config_dir / "backups").exists())

    def test_backups_are_never_pruned(self) -> None:
        self.write_config(self.config_dir, "A")
        for index in range(8):
            result = app.create_or_reuse_backup(self.config_dir, f"backup-{index}")
            self.assertEqual("created", result.status)

        self.assertEqual(8, len(app.list_backup_records(self.config_dir)))

    def test_rename_preserves_timestamp_and_content_and_rejects_duplicates(self) -> None:
        self.write_config(self.config_dir, "A")
        first = app.create_or_reuse_backup(self.config_dir, "First").record
        second = app.create_or_reuse_backup(self.config_dir, "Second").record
        original_auth = (first.path / "auth.json").read_bytes()
        original_config = (first.path / "config.toml").read_bytes()

        renamed = app.rename_backup(self.config_dir, first.path, "Renamed backup")

        self.assertEqual(first.created_at, renamed.created_at)
        self.assertEqual("Renamed backup", renamed.name)
        self.assertEqual(original_auth, (renamed.path / "auth.json").read_bytes())
        self.assertEqual(original_config, (renamed.path / "config.toml").read_bytes())
        with self.assertRaises(app.BackupNameConflictError):
            app.rename_backup(self.config_dir, renamed.path, second.name.lower())

    def test_delete_backups_only_deletes_selected_directories(self) -> None:
        self.write_config(self.config_dir, "A")
        records = [app.create_or_reuse_backup(self.config_dir, f"item-{index}").record for index in range(3)]

        app.delete_backups(self.config_dir, [records[0].path, records[2].path])

        remaining = app.list_backup_records(self.config_dir)
        self.assertEqual(["item-1"], [record.name for record in remaining])

    def test_restore_creates_named_safety_backup(self) -> None:
        self.write_config(self.config_dir, "A", "https://a.example.com/v1")
        backup_a = app.create_or_reuse_backup(self.config_dir, "A").record
        app.save_codex_config(
            self.config_dir,
            "test-key",
            "B",
            "https://b.example.com/v1",
            "gpt-5.4",
            "A",
        )

        safety = app.restore_backup(self.config_dir, backup_a.path, "B")

        self.assertEqual("created", safety.status)
        self.assertEqual("A", app.read_codex_config(self.config_dir).provider)
        self.assertEqual({"A", "B"}, {record.name for record in app.list_backup_records(self.config_dir)})

    def test_existing_config_requires_a_name_before_every_destructive_operation(self) -> None:
        operations = ("save", "template", "default", "restore")
        for operation in operations:
            with self.subTest(operation=operation):
                config_dir = self.root / operation
                self.write_config(config_dir, "A")
                restore_source = app.create_or_reuse_backup(config_dir, "restore-source").record
                before_auth = (config_dir / "auth.json").read_bytes()
                before_config = (config_dir / "config.toml").read_bytes()

                with self.assertRaises(app.BackupNameError):
                    if operation == "save":
                        app.save_codex_config(config_dir, "new-key", "B", "https://b.example.com/v1", "gpt-5.4", None)
                    elif operation == "template":
                        app.create_custom_template_config(config_dir, "new-key", "B", "https://b.example.com/v1", "gpt-5.4", None)
                    elif operation == "default":
                        app.restore_default_config(config_dir, None)
                    else:
                        app.restore_backup(config_dir, restore_source.path, None)

                self.assertEqual(before_auth, (config_dir / "auth.json").read_bytes())
                self.assertEqual(before_config, (config_dir / "config.toml").read_bytes())

    def test_legacy_duplicate_names_are_preserved_and_newest_matching_one_is_reused(self) -> None:
        older = self.config_dir / "backups" / "20260101-120000-before-save"
        newer = self.config_dir / "backups" / "20260102-120000-before-save"
        self.write_config(older, "A")
        self.write_config(newer, "B")
        self.write_config(self.config_dir, "B")

        reusable = app.find_reusable_backup(self.config_dir, "before-save")

        self.assertEqual(newer.resolve(), reusable.path.resolve())
        self.assertEqual(2, len(app.named_backup_records(self.config_dir, "before-save")))

    def test_chinese_provider_name_is_preserved_for_default_backup_name(self) -> None:
        self.write_config(self.config_dir, "中文服务")

        self.assertEqual("中文服务", app.read_codex_config(self.config_dir).provider)
        self.assertEqual("中文服务", app.suggested_backup_name(self.config_dir))

    def test_invalid_backup_names_are_rejected(self) -> None:
        self.write_config(self.config_dir, "A")
        for name in ("", "bad/name", "bad.", "x" * 41):
            with self.subTest(name=name):
                with self.assertRaises(app.BackupNameError):
                    app.create_or_reuse_backup(self.config_dir, name)

    def test_drag_selection_adds_a_contiguous_range_to_existing_selection(self) -> None:
        items = ("a", "b", "c", "d", "e")

        downward = app.drag_selection_items(items, "b", "d", ("e",))
        upward = app.drag_selection_items(items, "d", "b", ("a",))

        self.assertEqual(("b", "c", "d", "e"), downward)
        self.assertEqual(("a", "b", "c", "d"), upward)

    def test_onboarding_is_only_automatic_before_first_close(self) -> None:
        self.assertTrue(app.should_show_onboarding({}))
        self.assertTrue(app.should_show_onboarding({app.ONBOARDING_SHOWN_KEY: False}))
        self.assertFalse(app.should_show_onboarding({app.ONBOARDING_SHOWN_KEY: True}))

    def test_legacy_onboarding_setting_marks_guide_as_seen(self) -> None:
        self.assertFalse(app.should_show_onboarding({app.HIDE_ONBOARDING_KEY: True}))
        self.assertFalse(app.should_show_onboarding({app.HIDE_ONBOARDING_KEY: False}))


if __name__ == "__main__":
    unittest.main()
