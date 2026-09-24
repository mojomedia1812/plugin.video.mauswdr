import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "plugin.video.mauswdr"


def load_default_module():
    sys.path.insert(0, str(ADDON_DIR))
    sys.argv = ["plugin://plugin.video.mauswdr", "1", ""]

    xbmc = types.ModuleType("xbmc")
    xbmc.executebuiltin = lambda command: None

    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = lambda: types.SimpleNamespace(getAddonInfo=lambda key: "")

    xbmcgui = types.ModuleType("xbmcgui")
    xbmcgui.NOTIFICATION_ERROR = "error"
    xbmcgui.NOTIFICATION_INFO = "info"

    class StubListItem:
        created = []

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.art = {}
            self.properties = {}
            self.info = {}
            self.mime_type = ""
            self.content_lookup = None

        def setArt(self, art):
            self.art = art

        def setProperty(self, key, value):
            self.properties[key] = value

        def setInfo(self, content_type, info):
            self.info[content_type] = info

        def setMimeType(self, mime_type):
            self.mime_type = mime_type

        def setContentLookup(self, enabled):
            self.content_lookup = enabled

    xbmcgui.ListItem = StubListItem
    xbmcgui.Dialog = lambda: types.SimpleNamespace(notification=lambda *args, **kwargs: None)

    xbmcplugin = types.ModuleType("xbmcplugin")
    xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE = 0

    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.translatePath = lambda path: path

    sys.modules.update(
        {
            "xbmc": xbmc,
            "xbmcaddon": xbmcaddon,
            "xbmcgui": xbmcgui,
            "xbmcplugin": xbmcplugin,
            "xbmcvfs": xbmcvfs,
        }
    )

    spec = importlib.util.spec_from_file_location("mauswdr_default", ADDON_DIR / "default.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DefaultArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.default = load_default_module()

    def test_make_list_item_uses_offscreen_creation(self):
        item = self.default.make_list_item(label="Abwasser", path="plugin://video")

        self.assertEqual(item.kwargs["label"], "Abwasser")
        self.assertEqual(item.kwargs["path"], "plugin://video")
        self.assertIs(item.kwargs["offscreen"], True)

    def test_video_art_sets_one_remote_preview_field(self):
        thumb = "https://www.wdrmaus.de/_teaserbilder/672952_355.jpg"

        self.assertEqual(
            self.default.video_art({"thumb": thumb}),
            {
                "thumb": thumb,
                "icon": "DefaultVideo.png",
            },
        )

    def test_video_art_uses_default_icon_without_thumbnail(self):
        self.assertEqual(self.default.video_art({}), {"icon": "DefaultVideo.png"})

    def test_set_video_art_adds_legacy_fanart_property(self):
        class FakeItem:
            def __init__(self):
                self.art = {}
                self.properties = {}

            def setArt(self, art):
                self.art = art

            def setProperty(self, key, value):
                self.properties[key] = value

        thumb = "https://www.wdrmaus.de/_teaserbilder/672952_355.jpg"
        item = FakeItem()

        self.default.set_video_art(item, {"thumb": thumb})

        self.assertEqual(item.art["thumb"], thumb)
        self.assertNotIn("poster", item.art)
        self.assertNotIn("fanart", item.art)
        self.assertEqual(item.properties["fanart_image"], thumb)

    def test_add_items_batches_directory_items_when_supported(self):
        calls = []
        items = [("plugin://one", object(), True), ("plugin://two", object(), False)]

        self.default.xbmcplugin.addDirectoryItems = lambda handle, listing, total: calls.append(
            (handle, listing, total)
        )

        self.default.add_items(items)

        self.assertEqual(calls, [(1, items, 2)])

    def test_check_for_updates_scans_local_addons_after_install(self):
        calls = []
        original_check = self.default.updater.check_and_install
        original_builtin = self.default.xbmc.executebuiltin
        original_addon = self.default.ADDON
        try:
            self.default.ADDON = types.SimpleNamespace(
                getAddonInfo=lambda key: {
                    "version": "2026.09.11.1",
                    "path": "addon-path",
                    "profile": "profile-path",
                }[key]
            )
            self.default.updater.check_and_install = lambda *args, **kwargs: {
                "status": "installed",
                "latest_version": "2026.09.11.3",
            }
            self.default.xbmc.executebuiltin = calls.append

            self.default.check_for_updates()

            self.assertEqual(calls, ["UpdateLocalAddons"])
        finally:
            self.default.updater.check_and_install = original_check
            self.default.xbmc.executebuiltin = original_builtin
            self.default.ADDON = original_addon

    def test_hls_dependency_install_is_triggered_when_missing(self):
        calls = []
        installed = {"inputstream.adaptive": False}
        original_addon = self.default.xbmcaddon.Addon
        original_builtin = self.default.xbmc.executebuiltin
        try:
            def fake_addon(addon_id=None):
                if addon_id == "inputstream.adaptive" and not installed[addon_id]:
                    raise RuntimeError("missing")
                return types.SimpleNamespace(getAddonInfo=lambda key: "")

            def fake_builtin(command, *args):
                calls.append(command)
                if command == "InstallAddon(inputstream.adaptive)":
                    installed["inputstream.adaptive"] = True

            self.default.xbmcaddon.Addon = fake_addon
            self.default.xbmc.executebuiltin = fake_builtin

            self.assertTrue(self.default.ensure_playback_dependencies("hls", notify=True))
            self.assertIn("InstallAddon(inputstream.adaptive)", calls)
        finally:
            self.default.xbmcaddon.Addon = original_addon
            self.default.xbmc.executebuiltin = original_builtin

    def test_play_configures_inputstream_adaptive_for_hls(self):
        calls = []
        original_resolve = self.default.wdrmaus.resolve_video_stream
        original_set_resolved = getattr(self.default.xbmcplugin, "setResolvedUrl", None)
        original_addon = self.default.xbmcaddon.Addon
        try:
            self.default.wdrmaus.resolve_video_stream = lambda url: {
                "url": "https://example.test/master.m3u8",
                "title": "Abwasser",
                "plot": "",
                "thumb": "",
                "format": "hls",
            }
            self.default.xbmcaddon.Addon = lambda addon_id=None: types.SimpleNamespace(getAddonInfo=lambda key: "")
            self.default.xbmcplugin.setResolvedUrl = lambda handle, succeeded, item: calls.append(
                (handle, succeeded, item)
            )

            self.default.play("https://www.wdrmaus.de/video.php5")

            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0][1])
            item = calls[0][2]
            self.assertEqual(item.mime_type, "application/vnd.apple.mpegurl")
            self.assertEqual(item.properties["inputstream"], "inputstream.adaptive")
            self.assertEqual(item.properties["inputstreamaddon"], "inputstream.adaptive")
            self.assertEqual(item.properties["inputstream.adaptive.manifest_type"], "hls")
            self.assertIs(item.content_lookup, False)
        finally:
            self.default.wdrmaus.resolve_video_stream = original_resolve
            self.default.xbmcaddon.Addon = original_addon
            if original_set_resolved is None:
                delattr(self.default.xbmcplugin, "setResolvedUrl")
            else:
                self.default.xbmcplugin.setResolvedUrl = original_set_resolved

    def test_play_sets_mp4_mime_without_inputstream(self):
        calls = []
        original_resolve = self.default.wdrmaus.resolve_video_stream
        original_set_resolved = getattr(self.default.xbmcplugin, "setResolvedUrl", None)
        try:
            self.default.wdrmaus.resolve_video_stream = lambda url: {
                "url": "https://example.test/video.mp4",
                "title": "Abwasser",
                "plot": "",
                "thumb": "",
                "format": "mp4",
            }
            self.default.xbmcplugin.setResolvedUrl = lambda handle, succeeded, item: calls.append(
                (handle, succeeded, item)
            )

            self.default.play("https://www.wdrmaus.de/video.php5")

            item = calls[0][2]
            self.assertEqual(item.mime_type, "video/mp4")
            self.assertNotIn("inputstream", item.properties)
        finally:
            self.default.wdrmaus.resolve_video_stream = original_resolve
            if original_set_resolved is None:
                delattr(self.default.xbmcplugin, "setResolvedUrl")
            else:
                self.default.xbmcplugin.setResolvedUrl = original_set_resolved


if __name__ == "__main__":
    unittest.main()
