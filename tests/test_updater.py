import os
import pathlib
import shutil
import sys
import tempfile
import unittest
import zipfile


LIB_DIR = pathlib.Path(__file__).resolve().parents[1] / "plugin.video.mauswdr" / "resources" / "lib"
sys.path.insert(0, str(LIB_DIR))

import updater  # noqa: E402


def release(version, draft=False, prerelease=False):
    asset_name = "plugin.video.mauswdr-{}.zip".format(version)
    return {
        "tag_name": "v{}".format(version),
        "draft": draft,
        "prerelease": prerelease,
        "html_url": "https://github.com/mojomedia1812/plugin.video.mauswdr/releases/tag/v{}".format(version),
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": "https://github.com/mojomedia1812/plugin.video.mauswdr/releases/download/v{}/{}".format(
                    version,
                    asset_name,
                ),
            }
        ],
    }


def write_package(path, version, extra_entries=None):
    addon_xml = '<addon id="plugin.video.mauswdr" name="MausWDR" version="{}"></addon>'.format(version)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.video.mauswdr/addon.xml", addon_xml)
        archive.writestr("plugin.video.mauswdr/default.py", "# update\n")
        for name, content in extra_entries or []:
            archive.writestr(name, content)


class UpdaterTests(unittest.TestCase):
    def test_version_comparison_uses_date_scheme(self):
        self.assertTrue(updater.is_newer_version("2026.09.11.2", "2026.09.11.1"))
        self.assertTrue(updater.is_newer_version("v2026.10.01.1", "2026.09.30.9"))
        self.assertFalse(updater.is_newer_version("2026.09.11.1", "2026.09.11.2"))
        self.assertFalse(updater.is_newer_version("1.0.2", "2026.09.11.1"))

    def test_latest_release_info_chooses_highest_valid_release(self):
        info = updater.latest_release_info(
            [
                release("2026.09.11.1"),
                release("2026.09.11.3", prerelease=True),
                release("2026.09.11.2"),
            ]
        )

        self.assertEqual(info["version"], "2026.09.11.2")
        self.assertEqual(info["name"], "plugin.video.mauswdr-2026.09.11.2.zip")

    def test_release_asset_must_match_tag_version(self):
        bad_release = release("2026.09.11.2")
        bad_release["tag_name"] = "v2026.09.11.3"

        self.assertIsNone(updater.find_release_asset(bad_release))

    def test_existing_state_does_not_skip_release_check(self):
        with tempfile.TemporaryDirectory() as root_dir:
            addon_dir = os.path.join(root_dir, "plugin.video.mauswdr")
            profile_dir = os.path.join(root_dir, "profile")
            os.makedirs(addon_dir)
            os.makedirs(profile_dir)
            updater.write_state(
                profile_dir,
                {"current_version": "2026.09.11.2"},
            )

            calls = []
            original_fetch_json = updater.fetch_json
            try:
                updater.fetch_json = lambda url: calls.append(url) or [release("2026.09.11.2")]

                result = updater.check_and_install("2026.09.11.2", addon_dir, profile_dir)

                self.assertEqual(calls, [updater.RELEASES_API_URL])
                self.assertEqual(result["status"], "current")
            finally:
                updater.fetch_json = original_fetch_json

    def test_install_zip_validates_and_extracts_package(self):
        with tempfile.TemporaryDirectory() as root_dir:
            addon_dir = os.path.join(root_dir, "plugin.video.mauswdr")
            os.makedirs(os.path.join(addon_dir, "__pycache__"))
            with open(os.path.join(addon_dir, "__pycache__", "old.pyc"), "wb") as handle:
                handle.write(b"old")

            package = os.path.join(root_dir, "update.zip")
            write_package(package, "2026.09.11.2")

            updater.install_zip(package, addon_dir, "2026.09.11.2")

            self.assertEqual(updater.read_addon_version(addon_dir), "2026.09.11.2")
            self.assertTrue(os.path.isfile(os.path.join(addon_dir, "default.py")))
            self.assertFalse(os.path.exists(os.path.join(addon_dir, "__pycache__")))

    def test_install_zip_rejects_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as root_dir:
            addon_dir = os.path.join(root_dir, "plugin.video.mauswdr")
            os.makedirs(addon_dir)
            package = os.path.join(root_dir, "update.zip")
            write_package(package, "2026.09.11.2", [("plugin.video.mauswdr/../escape.txt", "bad")])

            with self.assertRaises(updater.UpdateError):
                updater.install_zip(package, addon_dir, "2026.09.11.2")

            self.assertFalse(os.path.exists(os.path.join(root_dir, "escape.txt")))

    def test_install_zip_rejects_windows_drive_paths(self):
        with tempfile.TemporaryDirectory() as root_dir:
            addon_dir = os.path.join(root_dir, "plugin.video.mauswdr")
            os.makedirs(addon_dir)
            package = os.path.join(root_dir, "update.zip")
            write_package(package, "2026.09.11.2", [("plugin.video.mauswdr/C:/escape.txt", "bad")])

            with self.assertRaises(updater.UpdateError):
                updater.install_zip(package, addon_dir, "2026.09.11.2")

    def test_check_and_install_downloads_newer_release(self):
        with tempfile.TemporaryDirectory() as root_dir:
            addon_dir = os.path.join(root_dir, "plugin.video.mauswdr")
            profile_dir = os.path.join(root_dir, "profile")
            os.makedirs(addon_dir)
            os.makedirs(profile_dir)
            write_package(os.path.join(root_dir, "seed.zip"), "2026.09.11.1")
            updater.install_zip(os.path.join(root_dir, "seed.zip"), addon_dir, "2026.09.11.1")
            package = os.path.join(root_dir, "update.zip")
            write_package(package, "2026.09.11.3")

            original_fetch_json = updater.fetch_json
            original_download_file = updater.download_file
            try:
                updater.fetch_json = lambda url: [release("2026.09.11.3")]

                def fake_download(_url, target):
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copyfile(package, target)
                    return target

                updater.download_file = fake_download

                result = updater.check_and_install("2026.09.11.1", addon_dir, profile_dir)

                self.assertEqual(result["status"], "installed")
                self.assertEqual(result["latest_version"], "2026.09.11.3")
                self.assertEqual(updater.read_addon_version(addon_dir), "2026.09.11.3")
            finally:
                updater.fetch_json = original_fetch_json
                updater.download_file = original_download_file


if __name__ == "__main__":
    unittest.main()
