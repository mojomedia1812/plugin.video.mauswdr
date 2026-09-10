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

    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = lambda: types.SimpleNamespace(getAddonInfo=lambda key: "")

    xbmcgui = types.ModuleType("xbmcgui")
    xbmcgui.NOTIFICATION_ERROR = "error"

    class StubListItem:
        created = []

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.art = {}
            self.properties = {}

        def setArt(self, art):
            self.art = art

        def setProperty(self, key, value):
            self.properties[key] = value

    xbmcgui.ListItem = StubListItem

    xbmcplugin = types.ModuleType("xbmcplugin")
    xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE = 0

    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.translatePath = lambda path: path

    sys.modules.update(
        {
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


if __name__ == "__main__":
    unittest.main()
