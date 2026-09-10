import sys
import urllib.parse

import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib import wdrmaus


ADDON_HANDLE = int(sys.argv[1])
PLUGIN_URL = sys.argv[0]
ADDON_NAME = "MausWDR"
ADDON = xbmcaddon.Addon()


def build_url(params):
    return PLUGIN_URL + "?" + urllib.parse.urlencode(params)


def add_directory(label, params):
    item = xbmcgui.ListItem(label=label)
    item.setArt({"icon": "DefaultFolder.png"})
    xbmcplugin.addDirectoryItem(
        ADDON_HANDLE,
        build_url(params),
        item,
        isFolder=True,
    )


def add_video(video):
    label = video.get("label") or video["title"]
    item = xbmcgui.ListItem(label=label)
    item.setProperty("IsPlayable", "true")
    info = {
        "title": video["title"],
        "plot": video.get("plot", ""),
        "mediatype": "video",
    }
    if video.get("year"):
        info["year"] = int(video["year"])
    item.setInfo("video", info)
    art = {}
    if video.get("thumb"):
        art["thumb"] = video["thumb"]
        art["icon"] = video["thumb"]
    if art:
        item.setArt(art)

    xbmcplugin.addDirectoryItem(
        ADDON_HANDLE,
        build_url({"mode": "play", "url": video["url"]}),
        item,
        isFolder=False,
    )


def finish_directory(content="videos", succeeded=True):
    if content:
        xbmcplugin.setContent(ADDON_HANDLE, content)
    xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=succeeded)


def show_error(message):
    xbmcgui.Dialog().notification(
        ADDON_NAME,
        message,
        xbmcgui.NOTIFICATION_ERROR,
        7000,
    )


def list_root():
    for section in wdrmaus.get_sections():
        add_directory(section["label"], {"mode": "section", "section": section["id"]})
    add_directory("Nach Jahren", {"mode": "years"})
    finish_directory(content="files")


def list_section(section_id):
    try:
        menu_items = wdrmaus.get_section_menu(section_id)
    except Exception as exc:
        show_error("Menue konnte nicht geladen werden")
        wdrmaus.log_debug("Section menu error: {}".format(exc))
        finish_directory(succeeded=False)
        return

    for item in menu_items:
        add_directory(
            item["label"],
            {"mode": "list", "section": section_id, "filter": item["filter"]},
        )
    finish_directory(content="files")


def list_videos(section_id="sachgeschichten", filter_value="alle", query=None):
    try:
        videos = wdrmaus.get_video_items(section_id, filter_value, query=query)
    except Exception as exc:
        show_error("Videos konnten nicht geladen werden")
        wdrmaus.log_debug("Listing error: {}".format(exc))
        finish_directory(succeeded=False)
        return

    for video in videos:
        add_video(video)

    xbmcplugin.addSortMethod(ADDON_HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    finish_directory(content="videos")


def search():
    keyboard = xbmcgui.Keyboard("", "Video suchen")
    keyboard.doModal()
    if not keyboard.isConfirmed():
        finish_directory(content="videos", succeeded=False)
        return

    query = keyboard.getText().strip()
    if not query:
        finish_directory(content="videos", succeeded=False)
        return

    list_videos("sachgeschichten", "alle", query=query)


def list_years():
    try:
        years = wdrmaus.get_years()
    except Exception as exc:
        show_error("Jahre konnten nicht geladen werden")
        wdrmaus.log_debug("Years error: {}".format(exc))
        finish_directory(succeeded=False)
        return

    for year in years:
        add_directory(
            "{} ({})".format(year["year"], year["count"]),
            {"mode": "year", "year": year["year"]},
        )
    finish_directory(content="files")


def list_year(year):
    try:
        videos = wdrmaus.get_videos_by_year(year)
    except Exception as exc:
        show_error("Jahr konnte nicht geladen werden")
        wdrmaus.log_debug("Year listing error: {}".format(exc))
        finish_directory(succeeded=False)
        return

    for video in videos:
        add_video(video)

    xbmcplugin.addSortMethod(ADDON_HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    finish_directory(content="videos")


def play(url):
    try:
        stream = wdrmaus.resolve_video_stream(url)
    except Exception as exc:
        show_error("Video konnte nicht gestartet werden")
        wdrmaus.log_debug("Playback error: {}".format(exc))
        xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())
        return

    item = xbmcgui.ListItem(label=stream.get("title", ADDON_NAME), path=stream["url"])
    item.setProperty("IsPlayable", "true")
    item.setMimeType("application/vnd.apple.mpegurl")
    item.setContentLookup(False)
    item.setInfo(
        "video",
        {
            "title": stream.get("title", ""),
            "plot": stream.get("plot", ""),
            "mediatype": "video",
        },
    )
    if stream.get("thumb"):
        item.setArt({"thumb": stream["thumb"], "icon": stream["thumb"]})

    xbmcplugin.setResolvedUrl(ADDON_HANDLE, True, item)


def main():
    wdrmaus.set_cache_dir(xbmcvfs.translatePath(ADDON.getAddonInfo("profile")))
    params = dict(urllib.parse.parse_qsl(sys.argv[2][1:], keep_blank_values=True))
    mode = params.get("mode", "root")

    if mode == "list":
        list_videos(
            params.get("section", "sachgeschichten"),
            params.get("filter", "alle"),
            query=params.get("query"),
        )
    elif mode == "section":
        list_section(params.get("section", "sachgeschichten"))
    elif mode == "years":
        list_years()
    elif mode == "year":
        list_year(params.get("year", ""))
    elif mode == "search":
        search()
    elif mode == "play":
        play(params["url"])
    else:
        list_root()


if __name__ == "__main__":
    main()
