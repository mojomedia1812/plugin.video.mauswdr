import sys
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib import updater
from resources.lib import wdrmaus


ADDON_HANDLE = int(sys.argv[1])
PLUGIN_URL = sys.argv[0]
ADDON_NAME = "MausWDR"
ADDON = xbmcaddon.Addon()
INPUTSTREAM_ADAPTIVE = "inputstream.adaptive"


def make_list_item(label="", path=None):
    kwargs = {"label": label, "offscreen": True}
    if path is not None:
        kwargs["path"] = path
    try:
        return xbmcgui.ListItem(**kwargs)
    except TypeError:
        if path is None:
            return xbmcgui.ListItem(label=label)
        return xbmcgui.ListItem(label=label, path=path)


def build_url(params):
    return PLUGIN_URL + "?" + urllib.parse.urlencode(params)


def add_items(items):
    if not items:
        return
    add_many = getattr(xbmcplugin, "addDirectoryItems", None)
    if add_many:
        add_many(ADDON_HANDLE, items, len(items))
        return
    for url, item, is_folder in items:
        xbmcplugin.addDirectoryItem(ADDON_HANDLE, url, item, isFolder=is_folder)


def make_directory_item(label, params):
    item = make_list_item(label=label)
    item.setArt({"icon": "DefaultFolder.png"})
    return (
        build_url(params),
        item,
        True,
    )


def add_directory(label, params):
    add_items([make_directory_item(label, params)])


def video_art(video):
    thumb = video.get("thumb", "")
    if not thumb:
        return {"icon": "DefaultVideo.png"}
    return {
        "thumb": thumb,
        "icon": "DefaultVideo.png",
    }


def set_video_art(item, video):
    item.setArt(video_art(video))
    if video.get("thumb"):
        item.setProperty("fanart_image", video["thumb"])


def make_video_item(video):
    label = video.get("label") or video["title"]
    item = make_list_item(label=label)
    item.setProperty("IsPlayable", "true")
    info = {
        "title": video["title"],
        "plot": video.get("plot", ""),
        "mediatype": "video",
    }
    if video.get("year"):
        info["year"] = int(video["year"])
    item.setInfo("video", info)
    set_video_art(item, video)

    return (
        build_url({"mode": "play", "url": video["url"]}),
        item,
        False,
    )


def add_video(video):
    add_items([make_video_item(video)])


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


def show_info(message):
    xbmcgui.Dialog().notification(
        ADDON_NAME,
        message,
        getattr(xbmcgui, "NOTIFICATION_INFO", ""),
        7000,
    )


def execute_builtin(command, wait=False):
    try:
        xbmc.executebuiltin(command, wait)
    except TypeError:
        xbmc.executebuiltin(command)


def addon_available(addon_id):
    try:
        xbmcaddon.Addon(addon_id)
        return True
    except Exception:
        return False


def ensure_addon(addon_id, label, notify=False):
    if addon_available(addon_id):
        try:
            execute_builtin("EnableAddon({})".format(addon_id), True)
        except Exception as exc:
            wdrmaus.log_debug("Could not enable {}: {}".format(addon_id, exc))
        return addon_available(addon_id)

    if notify:
        show_info("{} wird installiert".format(label))
    try:
        execute_builtin("InstallAddon({})".format(addon_id), True)
    except Exception as exc:
        wdrmaus.log_debug("Could not install {}: {}".format(addon_id, exc))
    return addon_available(addon_id)


def ensure_playback_dependencies(stream_format="", notify=False):
    if stream_format != "hls":
        return True
    return ensure_addon(INPUTSTREAM_ADAPTIVE, "InputStream Adaptive", notify=notify)


def check_dependencies():
    ensure_addon(INPUTSTREAM_ADAPTIVE, "InputStream Adaptive", notify=False)


def check_for_updates():
    try:
        result = updater.check_and_install(
            ADDON.getAddonInfo("version"),
            xbmcvfs.translatePath(ADDON.getAddonInfo("path")),
            xbmcvfs.translatePath(ADDON.getAddonInfo("profile")),
        )
    except Exception as exc:
        wdrmaus.log_debug("Update check failed: {}".format(exc))
        return

    if result.get("status") == "installed":
        try:
            execute_builtin("UpdateLocalAddons")
        except Exception as exc:
            wdrmaus.log_debug("Could not scan local add-ons after update: {}".format(exc))
        show_info("Update {} installiert. Kodi bitte neu starten.".format(result["latest_version"]))


def list_root():
    items = [
        make_directory_item(section["label"], {"mode": "section", "section": section["id"]})
        for section in wdrmaus.get_sections()
    ]
    items.append(make_directory_item("Nach Jahren", {"mode": "years"}))
    add_items(items)
    finish_directory(content="files")


def list_section(section_id):
    try:
        menu_items = wdrmaus.get_section_menu(section_id)
    except Exception as exc:
        show_error("Menue konnte nicht geladen werden")
        wdrmaus.log_debug("Section menu error: {}".format(exc))
        finish_directory(succeeded=False)
        return

    add_items(
        [
            make_directory_item(
                item["label"],
                {"mode": "list", "section": section_id, "filter": item["filter"]},
            )
            for item in menu_items
        ]
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

    add_items([make_video_item(video) for video in videos])

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

    add_items(
        [
            make_directory_item(
                "{} ({})".format(year["year"], year["count"]),
                {"mode": "year", "year": year["year"]},
            )
            for year in years
        ]
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

    add_items([make_video_item(video) for video in videos])

    xbmcplugin.addSortMethod(ADDON_HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    finish_directory(content="videos")


def play(url):
    try:
        stream = wdrmaus.resolve_video_stream(url)
    except Exception as exc:
        show_error("Video konnte nicht gestartet werden")
        wdrmaus.log_debug("Playback error: {}".format(exc))
        xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, make_list_item())
        return

    stream_format = stream.get("format", "")
    if not ensure_playback_dependencies(stream_format, notify=True):
        show_error("InputStream Adaptive konnte nicht installiert werden")
        xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, make_list_item())
        return

    item = make_list_item(label=stream.get("title", ADDON_NAME), path=stream["url"])
    item.setProperty("IsPlayable", "true")
    item.setContentLookup(False)
    if stream_format == "hls":
        item.setMimeType("application/vnd.apple.mpegurl")
        item.setProperty("inputstream", INPUTSTREAM_ADAPTIVE)
        item.setProperty("inputstreamaddon", INPUTSTREAM_ADAPTIVE)
        item.setProperty("inputstream.adaptive.manifest_type", "hls")
    elif stream_format == "mp4":
        item.setMimeType("video/mp4")
    item.setInfo(
        "video",
        {
            "title": stream.get("title", ""),
            "plot": stream.get("plot", ""),
            "mediatype": "video",
        },
    )
    set_video_art(item, stream)

    xbmcplugin.setResolvedUrl(ADDON_HANDLE, True, item)


def main():
    wdrmaus.set_cache_dir(xbmcvfs.translatePath(ADDON.getAddonInfo("profile")))
    params = dict(urllib.parse.parse_qsl(sys.argv[2][1:], keep_blank_values=True))
    mode = params.get("mode", "root")

    if mode == "root":
        check_for_updates()
        check_dependencies()

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
