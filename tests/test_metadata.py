import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "plugin.video.mauswdr"


class AddonMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(ADDON_DIR / "addon.xml").getroot()
        cls.metadata = cls.root.find("./extension[@point='xbmc.addon.metadata']")

    def test_addon_identity(self):
        self.assertEqual(self.root.attrib["id"], "plugin.video.mauswdr")
        self.assertEqual(self.root.attrib["name"], "MausWDR")
        self.assertEqual(self.root.attrib["provider-name"], "m0j01812")
        self.assertRegex(self.root.attrib["version"], r"^\d{4}\.\d{2}\.\d{2}\.\d+$")

    def test_required_metadata_is_present(self):
        self.assertIsNotNone(self.metadata)
        texts = {}
        for child in self.metadata:
            texts.setdefault(child.tag, []).append((child.attrib.get("lang", ""), child.text or ""))

        for tag in ("summary", "description", "disclaimer"):
            langs = {lang for lang, value in texts[tag] if value.strip()}
            self.assertIn("de_DE", langs)
            self.assertIn("en_GB", langs)

        self.assertEqual(self.metadata.findtext("language"), "de")
        self.assertEqual(self.metadata.findtext("platform"), "all")
        self.assertEqual(self.metadata.findtext("license"), "MIT")
        self.assertEqual(self.metadata.findtext("website"), "https://www.wdrmaus.de/")
        self.assertEqual(
            self.metadata.findtext("source"),
            "https://github.com/mojomedia1812/plugin.video.mauswdr",
        )

    def test_assets_exist(self):
        assets = self.metadata.find("assets")
        self.assertIsNotNone(assets)

        for tag in ("icon", "fanart"):
            path = assets.findtext(tag)
            self.assertTrue(path)
            self.assertTrue((ADDON_DIR / path).is_file())

    def test_license_file_exists(self):
        text = (ADDON_DIR / "LICENSE.txt").read_text(encoding="utf-8")

        self.assertIn("MIT License", text)
        self.assertIn("m0j01812", text)


if __name__ == "__main__":
    unittest.main()
