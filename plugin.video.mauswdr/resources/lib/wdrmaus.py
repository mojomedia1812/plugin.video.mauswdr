import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


BASE_URL = "https://www.wdrmaus.de/"
TIMEOUT_SECONDS = 15
CACHE_TTL_SECONDS = 24 * 60 * 60
YEARS_CACHE_VERSION = 2
CACHE_DIR = ""

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Kodi; plugin.video.mauswdr/2026.09.11.3)",
    "Accept": "text/html,application/json,application/javascript,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
}

COMMON_CATEGORIES = (
    ("Technik", "kat1"),
    ("Natur", "kat2"),
    ("Tiere", "kat3"),
    ("Pflanzen", "kat4"),
    ("L\u00e4nder", "kat5"),
    ("Alltag", "kat6"),
    ("Essen & Trinken", "kat7"),
    ("Verkehr", "kat8"),
    ("K\u00f6rper", "kat9"),
    ("Sport", "kat10"),
)

SECTION_CONFIGS = (
    {
        "id": "sachgeschichten",
        "label": "Sachgeschichten",
        "path": "filme/sachgeschichten/index.php5",
        "menu": (
            ("ALLE", "alle"),
            ("NEU", ""),
            *COMMON_CATEGORIES,
            ("Medien", "kat11"),
            ("Zukunft", "kat12"),
            ("Herstellung", "kat13"),
            ("Berufe", "kat14"),
            ("Kunst", "kat15"),
            ("Kultur", "kat16"),
            ("Energie", "kat17"),
            ("Sprache", "kat18"),
            ("Feiertage", "kat19"),
            ("Musik", "kat20"),
            ("MausBlick", "kat30"),
            ("Stell dir vor", "kat31"),
        ),
    },
    {
        "id": "lachgeschichten",
        "label": "Lachgeschichten",
        "path": "filme/lachgeschichten/index.php5",
        "menu": (
            ("ALLE", "alle"),
            ("NEU", ""),
            *COMMON_CATEGORIES,
            ("Zukunft", "kat12"),
            ("Herstellung", "kat13"),
            ("Berufe", "kat14"),
            ("Kunst", "kat15"),
            ("Kultur", "kat16"),
            ("Sprache", "kat18"),
            ("Feiertage", "kat19"),
            ("Musik", "kat20"),
            ("Der kleine Maulwurf", "kat22"),
            ("Trudes Tier", "kat23"),
            ("Rico und Oscar", "kat24"),
            ("M\u00e4rchen", "kat25"),
            ("Nulli und Priesemut", "kat26"),
            ("K\u00e4pt\u2019n Blaub\u00e4r", "kat27"),
            ("Was denkst du", "kat28"),
            ("Im Liegen", "kat29"),
        ),
    },
    {
        "id": "mausspots",
        "label": "Mausspots",
        "path": "filme/mausspots/index.php5",
        "menu": (
            ("ALLE", "alle"),
            ("NEU", ""),
            *COMMON_CATEGORIES,
            ("Medien", "kat11"),
            ("Zukunft", "kat12"),
            ("Herstellung", "kat13"),
            ("Berufe", "kat14"),
            ("Kunst", "kat15"),
            ("Kultur", "kat16"),
            ("Sprache", "kat18"),
            ("Feiertage", "kat19"),
            ("Musik", "kat20"),
        ),
    },
    {
        "id": "lieder",
        "label": "Lieder",
        "path": "filme/lieder/index.php5",
        "menu": (
            ("ALLE", "alle"),
            ("NEU", ""),
            ("Natur", "kat2"),
            ("Tiere", "kat3"),
            ("Alltag", "kat6"),
            ("K\u00f6rper", "kat9"),
            ("Sport", "kat10"),
            ("Berufe", "kat14"),
            ("Musik", "kat20"),
            ("M\u00e4rchen", "kat25"),
        ),
    },
)
SECTION_BY_ID = {section["id"]: section for section in SECTION_CONFIGS}

TAG_RE = re.compile(r"<[^>]+>")
VIDEO_LI_RE = re.compile(
    r"<li\b(?P<attrs>(?=[^>]*\bclass=[\"'][^\"']*\bdynamicteaser\b)[^>]*)>(?P<li>.*?)</li>",
    re.IGNORECASE | re.DOTALL,
)
ANCHOR_RE = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL)
IMG_RE = re.compile(r"<img\b(?P<attrs>[^>]*)>", re.IGNORECASE | re.DOTALL)
SPAN_RE = re.compile(r"<span>\s*<i></i>\s*(?P<title>.*?)</span>", re.IGNORECASE | re.DOTALL)
FILTER_BLOCK_RE = re.compile(
    r"<ul\b[^>]*\bclass=[\"'](?P<class>filterbuchstaben|filterkategorien)[\"'][^>]*>"
    r"(?P<body>.*?)</ul>",
    re.IGNORECASE | re.DOTALL,
)
LINK_RE = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<label>.*?)</a>", re.IGNORECASE | re.DOTALL)
JSONP_RE = re.compile(r"storeAndPlay\((?P<json>\{.*\})\)\s*;?\s*$", re.DOTALL)
AIR_TIME_RE = re.compile(r"^(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})(?:\s+(?P<hour>\d{2}):(?P<minute>\d{2}))?")


class WdrMausError(RuntimeError):
    pass


def log_debug(message):
    try:
        import xbmc

        xbmc.log("[plugin.video.mauswdr] {}".format(message), xbmc.LOGDEBUG)
    except Exception:
        pass


def set_cache_dir(path):
    global CACHE_DIR
    CACHE_DIR = path or ""


def get_sections():
    return [{"id": section["id"], "label": section["label"]} for section in SECTION_CONFIGS]


def get_section_menu(section_id):
    section = get_section_config(section_id)
    return [{"label": label, "filter": filter_value} for label, filter_value in section["menu"]]


def get_section_config(section_id):
    try:
        return SECTION_BY_ID[section_id]
    except KeyError:
        raise WdrMausError("Unknown section: {}".format(section_id))


def get_section_label(section_id):
    return get_section_config(section_id)["label"]


def fetch_text(url, timeout=TIMEOUT_SECONDS):
    req = urllib.request.Request(normalize_url(url), headers=REQUEST_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def normalize_url(url, base=BASE_URL):
    if not url:
        return ""
    normalized = html.unescape(url).strip()
    if normalized.startswith("//"):
        normalized = "https:" + normalized
    return urllib.parse.urljoin(base, normalized)


def clean_text(value):
    text = TAG_RE.sub("", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def attr(attrs, name):
    match = re.search(
        r"\b{}\s*=\s*([\"'])(?P<value>.*?)\1".format(re.escape(name)),
        attrs or "",
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return html.unescape(match.group("value")).strip()


def make_index_url(section_id="sachgeschichten", filter_value="alle"):
    section = get_section_config(section_id)
    url = urllib.parse.urljoin(BASE_URL, section["path"])
    return url + "?filter=" + urllib.parse.quote(filter_value or "", safe="")


def get_video_items(section_id="sachgeschichten", filter_value="alle", query=None):
    page_url = make_index_url(section_id, filter_value)
    page = fetch_text(page_url)
    items = parse_video_items(page, page_url, section_id=section_id)

    if query:
        needle = query.casefold()
        items = [item for item in items if needle in item["title"].casefold()]

    return items


def parse_video_items(page, page_url=BASE_URL, section_id="sachgeschichten"):
    videos = []
    seen_urls = set()
    for li_match in VIDEO_LI_RE.finditer(page):
        anchor_match = ANCHOR_RE.search(li_match.group("li"))
        if not anchor_match:
            continue

        href = attr(anchor_match.group("attrs"), "href")
        if not href:
            continue

        body = anchor_match.group("body")
        title_match = SPAN_RE.search(body)
        title = clean_text(title_match.group("title") if title_match else body)
        if not title:
            continue

        image = ""
        plot = ""
        image_match = IMG_RE.search(body)
        if image_match:
            image = normalize_url(attr(image_match.group("attrs"), "src"), page_url)
            plot = clean_text(attr(image_match.group("attrs"), "alt"))

        url = normalize_url(href, page_url)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        date_sort = parse_int_prefix(attr(li_match.group("attrs"), "data-date"))
        videos.append(
            {
                "title": title,
                "url": url,
                "thumb": image,
                "plot": plot,
                "section": section_id,
                "section_label": get_section_label(section_id),
                "date_sort": date_sort,
            }
        )

    return videos


def get_filter_groups():
    page = fetch_text(make_index_url("sachgeschichten", "alle"))
    return parse_filter_groups(page, make_index_url("sachgeschichten", "alle"))


def parse_filter_groups(page, page_url=BASE_URL):
    groups = {"letters": [], "categories": []}

    for block in FILTER_BLOCK_RE.finditer(page):
        group_name = "letters" if block.group("class").lower() == "filterbuchstaben" else "categories"
        for link in LINK_RE.finditer(block.group("body")):
            label = clean_text(link.group("label"))
            href = attr(link.group("attrs"), "href")
            filter_value = filter_from_url(normalize_url(href, page_url))
            if not label:
                continue
            if group_name == "letters" and label in ("Neu", "Alle"):
                continue
            groups[group_name].append({"label": label, "filter": filter_value})

    return groups


def filter_from_url(url):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query, keep_blank_values=True)
    return query.get("filter", [""])[0]


def resolve_video_stream(page_url):
    page_url = normalize_url(page_url)
    page = fetch_text(page_url)
    metadata = parse_video_page(page, page_url)
    media_js_url = metadata.get("media_js_url")
    if not media_js_url:
        raise WdrMausError("No WDR media JavaScript URL found on {}".format(page_url))

    media = parse_media_jsonp(fetch_text(media_js_url))
    stream_url = pick_stream_url(media)
    if not stream_url:
        raise WdrMausError("No playable stream found for {}".format(page_url))

    tracker = media.get("trackerData", {})
    published = parse_air_time(tracker.get("trackerClipAirTime", "")) or metadata.get("published")
    return {
        "url": normalize_url(stream_url),
        "title": metadata.get("title") or tracker.get("trackerClipTitle") or "MausWDR",
        "plot": metadata.get("plot", ""),
        "thumb": metadata.get("thumb", ""),
        "format": pick_media_format(media),
        "published": published,
        "year": year_from_published(published),
    }


def parse_video_page(page, page_url):
    data = {
        "title": first_match(page, r"<h1\b[^>]*id=[\"']schild2[\"'][^>]*>(?P<value>.*?)</h1>"),
        "plot": meta_content(page, "og:description") or meta_content(page, "twitter:description"),
        "thumb": normalize_url(meta_content(page, "og:image") or meta_content(page, "twitter:image"), page_url),
        "media_js_url": "",
        "published": first_match(page, r"[\"']datePublished[\"']\s*:\s*[\"'](?P<value>[^\"']+)[\"']")
        or first_match(page, r"[\"']uploadDate[\"']\s*:\s*[\"'](?P<value>[^\"']+)[\"']")
        or meta_content(page, "DC.Date"),
    }

    extension_match = re.search(
        r"\bdata-extension(?:-ard)?\s*=\s*([\"'])(?P<value>.*?)\1",
        page,
        re.IGNORECASE | re.DOTALL,
    )
    if extension_match:
        extension_data = html.unescape(extension_match.group("value"))
        media_url = re.search(
            r"[\"']url[\"']\s*:\s*[\"'](?P<url>[^\"']+)[\"']",
            extension_data,
            re.IGNORECASE,
        )
        if media_url:
            data["media_js_url"] = normalize_url(media_url.group("url"), page_url)

    if not data["media_js_url"]:
        fallback = re.search(
            r"https?://deviceids-medp\.wdr\.de/ondemand/\d+/\d+\.js",
            page,
            re.IGNORECASE,
        )
        if fallback:
            data["media_js_url"] = normalize_url(fallback.group(0), page_url)

    return data


def meta_content(page, property_name):
    escaped = re.escape(property_name)
    patterns = (
        r"<meta\b(?=[^>]*(?:property|name)=[\"']{}[\"'])[^>]*content=[\"'](?P<value>.*?)[\"'][^>]*>".format(
            escaped
        ),
        r"<meta\b(?=[^>]*content=[\"'](?P<value>.*?)[\"'])[^>]*(?:property|name)=[\"']{}[\"'][^>]*>".format(
            escaped
        ),
    )
    for pattern in patterns:
        value = first_match(page, pattern)
        if value:
            return value
    return ""


def first_match(page, pattern):
    match = re.search(pattern, page, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return clean_text(match.group("value"))


def parse_media_jsonp(payload):
    match = JSONP_RE.search(payload.strip())
    if match:
        return json.loads(match.group("json"))

    first = payload.find("{")
    last = payload.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise WdrMausError("Could not parse WDR media JSONP")
    return json.loads(payload[first : last + 1])


def pick_stream_url(media):
    resources = media.get("mediaResource", {})
    for resource_name in ("dflt", "alt"):
        resource = resources.get(resource_name) or {}
        stream_url = resource.get("videoURL")
        if stream_url:
            return stream_url
    for resource in resources.values():
        if isinstance(resource, dict) and resource.get("videoURL"):
            return resource["videoURL"]
    return ""


def pick_media_format(media):
    resources = media.get("mediaResource", {})
    for resource_name in ("dflt", "alt"):
        resource = resources.get(resource_name) or {}
        media_format = resource.get("mediaFormat")
        if media_format:
            return media_format
    return ""


def parse_air_time(value):
    match = AIR_TIME_RE.match(value or "")
    if not match:
        return ""
    hour = match.group("hour") or "00"
    minute = match.group("minute") or "00"
    return "{year}-{month}-{day}T{hour}:{minute}:00".format(
        year=match.group("year"),
        month=match.group("month"),
        day=match.group("day"),
        hour=hour,
        minute=minute,
    )


def parse_int_prefix(value):
    match = re.match(r"\s*(\d+)", value or "")
    return int(match.group(1)) if match else 0


def year_from_published(value):
    match = re.match(r"(?P<year>\d{4})", value or "")
    return match.group("year") if match else ""


def date_label(value):
    match = re.match(r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})", value or "")
    if not match:
        return ""
    return "{day}.{month}.{year}".format(**match.groupdict())


def get_all_video_items():
    items = []
    seen = set()
    for section in SECTION_CONFIGS:
        for item in get_video_items(section["id"], "alle"):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            items.append(item)
    return items


def get_years():
    items = get_all_video_items_with_dates()
    counts = {}
    for item in items:
        year = item.get("year")
        if year:
            counts[year] = counts.get(year, 0) + 1
    return [{"year": year, "count": counts[year]} for year in sorted(counts)]


def get_videos_by_year(year):
    items = [item for item in get_all_video_items_with_dates() if item.get("year") == str(year)]
    return sorted(items, key=lambda item: (item.get("published", ""), item["title"].casefold()))


def get_all_video_items_with_dates():
    cached = read_years_cache()
    if cached:
        return cached

    items = get_all_video_items()
    enriched = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(enrich_video_item, item) for item in items]
        for future in as_completed(futures):
            try:
                enriched.append(future.result())
            except Exception as exc:
                log_debug("Date enrichment failed: {}".format(exc))

    enriched.sort(key=lambda item: (item.get("published", ""), item["title"].casefold()))
    write_years_cache(enriched)
    return enriched


def enrich_video_item(item):
    enriched = dict(item)
    page = fetch_text(item["url"])
    metadata = parse_video_page(page, item["url"])
    published = ""
    if metadata.get("media_js_url"):
        media = parse_media_jsonp(fetch_text(metadata["media_js_url"]))
        published = parse_air_time((media.get("trackerData") or {}).get("trackerClipAirTime", ""))
    published = published or metadata.get("published", "")

    if metadata.get("title"):
        enriched["title"] = metadata["title"]
    if metadata.get("plot"):
        enriched["plot"] = metadata["plot"]
    if metadata.get("thumb"):
        enriched["thumb"] = metadata["thumb"]

    year = year_from_published(published)
    enriched["published"] = published
    enriched["year"] = year
    details = []
    if enriched.get("section_label"):
        details.append(enriched["section_label"])
    if date_label(published):
        details.append(date_label(published))
    if details:
        plot = enriched.get("plot", "")
        enriched["plot"] = "{}\n\n{}".format(" | ".join(details), plot) if plot else " | ".join(details)
    return enriched


def cache_path(name):
    if not CACHE_DIR:
        return ""
    return os.path.join(CACHE_DIR, name)


def read_years_cache():
    path = cache_path("years-v{}.json".format(YEARS_CACHE_VERSION))
    if not path or not os.path.exists(path):
        return []
    if time.time() - os.path.getmtime(path) > CACHE_TTL_SECONDS:
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        log_debug("Could not read years cache: {}".format(exc))
        return []
    if payload.get("version") != YEARS_CACHE_VERSION:
        return []
    return payload.get("items", [])


def write_years_cache(items):
    path = cache_path("years-v{}.json".format(YEARS_CACHE_VERSION))
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"version": YEARS_CACHE_VERSION, "created": time.time(), "items": items}, handle)
    except Exception as exc:
        log_debug("Could not write years cache: {}".format(exc))
