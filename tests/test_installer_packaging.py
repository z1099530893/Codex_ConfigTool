import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallerPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installer = (ROOT / "packaging" / "CodexConfigTool.iss").read_text(encoding="utf-8")
        cls.build_script = (ROOT / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")

    def test_installer_is_per_user_and_does_not_require_admin(self) -> None:
        self.assertIn("DefaultDirName={localappdata}\\Programs\\CodexConfigTool", self.installer)
        self.assertIn("PrivilegesRequired=lowest", self.installer)

    def test_desktop_shortcut_is_selected_by_default_but_optional(self) -> None:
        self.assertIn('Name: "desktopicon"', self.installer)
        self.assertIn("Flags: checkedonce", self.installer)
        self.assertIn('Name: "{userdesktop}\\{#MyAppName}"', self.installer)
        self.assertIn("Tasks: desktopicon", self.installer)

    def test_installer_only_packages_the_application_executable(self) -> None:
        self.assertIn('Source: "..\\dist\\{#MyAppExeName}"', self.installer)
        self.assertNotIn('Source: "..\\.codex', self.installer)
        self.assertNotIn('Source: "..\\auth.json', self.installer)
        self.assertNotIn('Source: "..\\config.toml', self.installer)

    def test_installer_bundles_its_chinese_message_overrides(self) -> None:
        language_file = ROOT / "packaging" / "ChineseSimplifiedOverrides.isl"
        self.assertTrue(language_file.is_file())
        self.assertIn("ChineseSimplifiedOverrides.isl", self.installer)
        language_text = language_file.read_text(encoding="utf-8")
        self.assertIn("CreateDesktopIcon=创建桌面快捷方式", language_text)
        self.assertNotIn("CreateDesktopIcon=创建桌面快捷方式(&D)", language_text)
        self.assertIn("[CustomMessages]", language_text)
        self.assertIn("ButtonCancel=取消", language_text)

    def test_uninstall_prompts_before_removing_tool_settings_only(self) -> None:
        self.assertIn("function InitializeUninstall(): Boolean;", self.installer)
        self.assertIn("AskUninstallDataPolicy", self.installer)
        self.assertIn("{userappdata}\\CodexConfigTool", self.installer)
        self.assertIn("{userprofile}\\.codex\\backups", self.installer)
        self.assertIn("DelTree(ExpandConstant('{userappdata}\\CodexConfigTool'), True, True, True);", self.installer)
        self.assertIn("DelTree(ExpandConstant('{userprofile}\\.codex\\backups'), True, True, True);", self.installer)
        self.assertNotIn("DelTree(ExpandConstant('{userappdata}\\Codex'),", self.installer)
        self.assertNotIn("DelTree(ExpandConstant('{localappdata}\\Codex'),", self.installer)
        for protected_name in ("auth.json", "config.toml", "sessions", "history.jsonl"):
            self.assertNotIn("DelTree(ExpandConstant('{userprofile}\\.codex\\" + protected_name, self.installer)
        language_text = (ROOT / "packaging" / "ChineseSimplifiedOverrides.isl").read_text(encoding="utf-8")
        self.assertIn("KeepUserDataOption=保留用户数据", language_text)
        self.assertIn("DeleteUserDataOption=完全删除用户数据", language_text)

    def test_build_produces_versioned_portable_and_setup_files(self) -> None:
        self.assertIn('"CodexConfigTool-Portable-v$appVersion.exe"', self.build_script)
        self.assertIn('"CodexConfigTool-Setup-v$appVersion.exe"', self.build_script)
        self.assertIn('"/DMyAppVersion=$appVersion"', self.build_script)


if __name__ == "__main__":
    unittest.main()
