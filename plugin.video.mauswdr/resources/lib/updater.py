import json
import os
import re
import shutil
import time
import urllib.request
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree


ADDON_ID = "plugin.video.mauswdr"
RELEASES_API_URL = "https://api.github.com/repos/mojomedia1812/plugin.video.mauswdr/releases?per_page=10"
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
STATE_FILE = "update-state.json"
REQUEST_HEADERS = {
    "User-Agent": "MausWDR/2026.09.11.2",
    "Accept": "application/vnd.github+json,application/json",
    "X-GitHub-Api-Version": "2022-11-28",
}
ASSET_RE = re.compile(r"^plugin\.video\.mauswdr-(?P<version>\d{4}\.\d{2}\.\d{2}\.\d+)\.zip$")


class UpdateError(RuntimeError):
    pass


def parse_version(value):
    version = normalize_version(value)
    parts = version.split(".")
    if len(parts) != 4:
        return ()
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return ()


def normalize_version(value):
    version = (value or "").strip()
    if version.startswith("v"):
        version = version[1:]
    return version


def is_newer_version(candidate, current):
    candidate_parts = parse_version(candidate)
    current_parts = parse_version(current)
    if not candidate_parts:
        return False
    if not current_parts:
        return True
    return candidate_parts > current_parts


def read_addon_version(addon_dir):
    path = os.path.join(addon_dir or "", "addon.xml")
    if not os.path.exists(path):
        return ""
    try:
        return ElementTree.parse(path).getroot().attrib.get("version", "")
    except Exception:
        return ""


def fetch_json(url, timeout=5):
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def download_file(url, target_path, timeout=30):
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    tmp_path = target_path + ".part"
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        with open(tmp_path, "wb") as handle:
            shutil.copyfileobj(response, handle)
    os.replace(tmp_path, target_path)
    return target_path


def find_release_asset(release):
    tag_version = normalize_version(release.get("tag_name", ""))
    for asset in release.get("assets", []):
        match = ASSET_RE.match(asset.get("name", ""))
        if not match:
            continue
        version = match.group("version")
        if tag_version and version != tag_version:
            continue
        download_url = asset.get("browser_download_url")
        if not download_url:
            continue
        return {
            "version": version,
            "tag": release.get("tag_name", ""),
            "name": asset.get("name", ""),
            "download_url": download_url,
            "html_url": release.get("html_url", ""),
        }
    return None


def latest_release_info(releases):
    candidates = []
    for release in releases if isinstance(releases, list) else [releases]:
        if release.get("draft") or release.get("prerelease"):
            continue
        asset = find_release_asset(release)
        if asset and parse_version(asset["version"]):
            candidates.append(asset)
    if not candidates:
        return None
    return max(candidates, key=lambda item: parse_version(item["version"]))


def check_and_install(current_version, addon_dir, profile_dir, now=None, force=False):
    now = time.time() if now is None else now
    current_version = normalize_version(current_version) or read_addon_version(addon_dir)
    if not current_version:
        raise UpdateError("Current add-on version could not be determined")
    if not addon_dir or not os.path.isdir(addon_dir):
        raise UpdateError("Add-on directory is missing")
    if not profile_dir:
        raise UpdateError("Add-on profile directory is missing")

    if not force and should_skip_check(profile_dir, current_version, now):
        return {"status": "skipped", "current_version": current_version}

    release = latest_release_info(fetch_json(RELEASES_API_URL))
    state = {"last_check": now, "current_version": current_version}
    if not release:
        write_state(profile_dir, state)
        return {"status": "unavailable", "current_version": current_version}
    state["latest_version"] = release["version"]

    if not is_newer_version(release["version"], current_version):
        write_state(profile_dir, state)
        return {
            "status": "current",
            "current_version": current_version,
            "latest_version": release["version"],
        }

    updates_dir = os.path.join(profile_dir, "updates")
    zip_path = os.path.join(updates_dir, release["name"])
    download_file(release["download_url"], zip_path)
    install_zip(zip_path, addon_dir, release["version"])
    state["current_version"] = release["version"]
    write_state(profile_dir, state)
    return {
        "status": "installed",
        "previous_version": current_version,
        "latest_version": release["version"],
        "zip_path": zip_path,
        "release_url": release.get("html_url", ""),
    }


def state_path(profile_dir):
    return os.path.join(profile_dir or "", STATE_FILE)


def read_state(profile_dir):
    path = state_path(profile_dir)
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def write_state(profile_dir, state):
    if not profile_dir:
        return
    os.makedirs(profile_dir, exist_ok=True)
    with open(state_path(profile_dir), "w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True)


def should_skip_check(profile_dir, current_version, now):
    state = read_state(profile_dir)
    if state.get("current_version") != current_version:
        return False
    last_check = float(state.get("last_check") or 0)
    return now - last_check < CHECK_INTERVAL_SECONDS


def install_zip(zip_path, addon_dir, expected_version):
    addon_dir = os.path.abspath(addon_dir)
    parent_dir = os.path.dirname(addon_dir)
    with zipfile.ZipFile(zip_path) as archive:
        validate_zip(archive, expected_version)
        remove_python_caches(addon_dir)
        for info, parts in safe_members(archive):
            target_path = os.path.abspath(os.path.join(parent_dir, *parts))
            if os.path.commonpath([addon_dir, target_path]) != addon_dir:
                raise UpdateError("Unsafe update path: {}".format(info.filename))
            if info.is_dir():
                os.makedirs(target_path, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with archive.open(info) as source, open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)
        remove_python_caches(addon_dir)


def validate_zip(archive, expected_version):
    addon_xml = "{}/addon.xml".format(ADDON_ID)
    try:
        root = ElementTree.fromstring(archive.read(addon_xml))
    except Exception as exc:
        raise UpdateError("Update package has no valid addon.xml") from exc

    if root.attrib.get("id") != ADDON_ID:
        raise UpdateError("Update package has the wrong add-on id")
    if normalize_version(root.attrib.get("version")) != normalize_version(expected_version):
        raise UpdateError("Update package version does not match release version")

    list(safe_members(archive))


def safe_members(archive):
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        parts = PurePosixPath(name).parts
        if not parts or parts[0] != ADDON_ID or any(part in ("", ".", "..") or ":" in part for part in parts):
            raise UpdateError("Unsafe update path: {}".format(info.filename))
        yield info, parts


def remove_python_caches(addon_dir):
    if not addon_dir or not os.path.isdir(addon_dir):
        return
    for root, dirs, _files in os.walk(addon_dir):
        for dirname in list(dirs):
            if dirname == "__pycache__":
                shutil.rmtree(os.path.join(root, dirname), ignore_errors=True)
                dirs.remove(dirname)
