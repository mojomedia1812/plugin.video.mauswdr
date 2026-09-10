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

    def test_video_art_sets_kodi_preview_fields(self):
        thumb = "https://www.wdrmaus.de/_teaserbilder/672952_355.jpg"

        self.assertEqual(
            self.default.video_art({"thumb": thumb}),
            {
                "thumb": thumb,
                "icon": thumb,
                "poster": thumb,
                "fanart": thumb,
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

        self.assertEqual(item.art["poster"], thumb)
        self.assertEqual(item.art["fanart"], thumb)
        self.assertEqual(item.properties["fanart_image"], thumb)


if __name__ == "__main__":
    unittest.main()
