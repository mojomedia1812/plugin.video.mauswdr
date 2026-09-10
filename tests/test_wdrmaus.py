import pathlib
import sys
import unittest


LIB_DIR = pathlib.Path(__file__).resolve().parents[1] / "plugin.video.mauswdr" / "resources" / "lib"
sys.path.insert(0, str(LIB_DIR))

import wdrmaus  # noqa: E402


class WdrMausParserTests(unittest.TestCase):
    def test_parse_video_items_uses_dynamic_teasers_only(self):
        page = """
        <ul class="links">
            <li class="siteteaser type1">
                <a href="../../filme/sachgeschichten/ignore.php5">
                    <img src="../../_teaserbilder/1_355.jpg" alt="Ignore" />
                    <span><i></i>Ignore me</span>
                </a>
            </li>
            <li class="dynamicteaser" data-date="4102268400,">
                <a href="../../filme/sachgeschichten/woelfe.php5">
                    <img src="../../_teaserbilder/672952_355.jpg" alt="Ein Wolf" />
                    <span><i></i>W&ouml;lfe</span>
                </a>
            </li>
        </ul>
        """

        videos = wdrmaus.parse_video_items(page, wdrmaus.make_index_url("sachgeschichten", "alle"))

        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0]["title"], "W\u00f6lfe")
        self.assertEqual(videos[0]["plot"], "Ein Wolf")
        self.assertEqual(videos[0]["section"], "sachgeschichten")
        self.assertEqual(videos[0]["section_label"], "Sachgeschichten")
        self.assertEqual(videos[0]["date_sort"], 4102268400)
        self.assertEqual(
            videos[0]["url"],
            "https://www.wdrmaus.de/filme/sachgeschichten/woelfe.php5",
        )
        self.assertEqual(
            videos[0]["thumb"],
            "https://www.wdrmaus.de/_teaserbilder/672952_355.jpg",
        )

    def test_parse_filter_groups(self):
        page = """
        <ul class="filterbuchstaben">
            <li><a href="../../filme/sachgeschichten/index.php5?filter=">Neu</a></li>
            <li><a href="../../filme/sachgeschichten/index.php5?filter=alle">Alle</a></li>
            <li><a href="../../filme/sachgeschichten/index.php5?filter=a">a</a></li>
        </ul>
        <ul class="filterkategorien">
            <li><a href="../../filme/sachgeschichten/index.php5?filter=kat1">Technik</a></li>
        </ul>
        """

        groups = wdrmaus.parse_filter_groups(
            page,
            "https://www.wdrmaus.de/filme/sachgeschichten/index.php5?filter=alle",
        )

        self.assertEqual(groups["letters"], [{"label": "a", "filter": "a"}])
        self.assertEqual(groups["categories"], [{"label": "Technik", "filter": "kat1"}])

    def test_section_menus_match_requested_order(self):
        sections = wdrmaus.get_sections()

        self.assertEqual([section["id"] for section in sections], ["sachgeschichten", "lachgeschichten", "mausspots", "lieder"])
        self.assertEqual(
            [item["label"] for item in wdrmaus.get_section_menu("sachgeschichten")[:4]],
            ["ALLE", "NEU", "Technik", "Natur"],
        )
        self.assertEqual(wdrmaus.get_section_menu("lachgeschichten")[-1], {"label": "Im Liegen", "filter": "kat29"})
        self.assertEqual(wdrmaus.get_section_menu("mausspots")[-1], {"label": "Musik", "filter": "kat20"})
        self.assertEqual(wdrmaus.get_section_menu("lieder")[-1], {"label": "M\u00e4rchen", "filter": "kat25"})

    def test_parse_video_page_finds_ard_media_js(self):
        page = """
        <meta property="og:description" content="Beschreibung">
        <meta property="og:image" content="https://www.wdrmaus.de//_teaserbilder/682651_512.jpg">
        <h1 id="schild2">Abwasser</h1>
        <a data-extension-ard="{ 'mediaObj': { 'url': 'http://deviceids-medp.wdr.de/ondemand/120/1208061.js', 'embedURL' : 'https://www.wdrmaus.de//filme/sachgeschichten/abwasser.php5'}}"></a>
        """

        details = wdrmaus.parse_video_page(
            page,
            "https://www.wdrmaus.de/filme/sachgeschichten/abwasser.php5",
        )

        self.assertEqual(details["title"], "Abwasser")
        self.assertEqual(details["plot"], "Beschreibung")
        self.assertEqual(
            details["media_js_url"],
            "http://deviceids-medp.wdr.de/ondemand/120/1208061.js",
        )
        self.assertEqual(details["published"], "")

    def test_parse_video_page_finds_assetjsonp_media_js_and_date(self):
        page = """
        <h1 id="schild2">Baba Jaga</h1>
        <script type="application/ld+json">{"datePublished":"2021-03-07T12:00+01:00"}</script>
        <a data-extension="{ 'mediaObj': { 'url': 'https://kinder.wdr.de/tv/die-sendung-mit-der-maus/av/video-lachgeschichte-baba-jaga-100.assetjsonp', 'embedURL' : 'https://www.wdrmaus.de//filme/lachgeschichten/baba_jaga.php5'}}"></a>
        """

        details = wdrmaus.parse_video_page(
            page,
            "https://www.wdrmaus.de/filme/lachgeschichten/baba_jaga.php5",
        )

        self.assertEqual(details["title"], "Baba Jaga")
        self.assertEqual(
            details["media_js_url"],
            "https://kinder.wdr.de/tv/die-sendung-mit-der-maus/av/video-lachgeschichte-baba-jaga-100.assetjsonp",
        )
        self.assertEqual(details["published"], "2021-03-07T12:00+01:00")

    def test_parse_media_jsonp_and_pick_stream(self):
        payload = """
        $mediaObject.jsonpHelper.storeAndPlay({
            "mediaResource": {
                "dflt": {
                    "videoURL": "//example.test/master.m3u8",
                    "mediaFormat": "hls"
                }
            },
            "trackerData": {"trackerClipTitle": "Abwasser"}
        });
        """

        media = wdrmaus.parse_media_jsonp(payload)

        self.assertEqual(wdrmaus.pick_stream_url(media), "//example.test/master.m3u8")
        self.assertEqual(wdrmaus.pick_media_format(media), "hls")
        self.assertEqual(wdrmaus.normalize_url(wdrmaus.pick_stream_url(media)), "https://example.test/master.m3u8")

    def test_parse_air_time_and_year(self):
        published = wdrmaus.parse_air_time("04.05.2020 09:30")

        self.assertEqual(published, "2020-05-04T09:30:00")
        self.assertEqual(wdrmaus.year_from_published(published), "2020")
        self.assertEqual(wdrmaus.date_label(published), "04.05.2020")

    def test_year_listing_sorts_old_to_new_then_title(self):
        original = wdrmaus.get_all_video_items_with_dates
        try:
            wdrmaus.get_all_video_items_with_dates = lambda: [
                {"title": "B", "published": "2020-02-01T00:00:00", "year": "2020"},
                {"title": "A", "published": "2020-01-01T00:00:00", "year": "2020"},
                {"title": "C", "published": "2019-01-01T00:00:00", "year": "2019"},
            ]
            self.assertEqual([item["title"] for item in wdrmaus.get_videos_by_year("2020")], ["A", "B"])
        finally:
            wdrmaus.get_all_video_items_with_dates = original


if __name__ == "__main__":
    unittest.main()
