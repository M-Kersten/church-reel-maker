"""Kerkdienstgemist: from a page address to the file its download button points at.

The recording page is a JavaScript app, so its HTML holds no video at all. The player asks
the platform's own API for the recording, and the download button in it is simply an anchor
around what that answer calls `download_url` — a signed link straight to the mp4 on S3.

This asks the same question the page asks, with the same anonymous token the site ships in
its own script bundle, and hands back that link. Two ids are needed and both are in the
address you paste:

    https://kerkdienstgemist.nl/stations/1341/events/recording/178807680001341
                                        ^^^^                   ^^^^^^^^^^^^^^^
                                        station                recording

This leans on a shape nobody promised to keep. When it changes, `resolve` returns None, the
link falls through to the ordinary route, and the reader gets the note in fetch.SITE_ADVICE
telling them to use the download button themselves. Nothing breaks silently.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

# The platform runs the same software under three names; the API sits on api.<that domain>.
# Only the Dutch one has been tried against a real recording.
HOSTS = {"kerkdienstgemist.nl", "unsergottesdienst.de", "unsergottesdienst.ch"}

# The token the site's own player uses for anonymous visitors, lifted from its script bundle
# (config.APP.API_CREDENTIALS). It grants exactly what any visitor already has: the public
# recordings of public stations. It is not anyone's account.
ANONYMOUS = ("eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJrZGdtIiwiYXVkIjoia2RnbTphbm9ueW1vdXMiLCJpYXQiOjE1OTcy"
             "MzY5NTcsImp0aSI6ImIzYzIzZWY0OGIxZDc4ZTg3ZWFkNTMyZjg1MWI2MmY1In0."
             "K0eQrCdMN3HDr-ytHECPs3jHDpgfz5IPM2bhJrgbezQ")

RECORDING = re.compile(r"/stations/(\d+)/events/recording/(\d+)")
TIMEOUT = 30.0

MONTHS = ["januari", "februari", "maart", "april", "mei", "juni",
          "juli", "augustus", "september", "oktober", "november", "december"]


@dataclass
class Recording:
    url: str  # the signed link the download button points at
    title: str
    duration: float | None = None
    sermon_starts: float | None = None  # the platform's own guess at where the preaching begins


def handles(url: str) -> bool:
    name = urlparse(url).netloc.lower().removeprefix("www.")
    return any(name == host or name.endswith("." + host) for host in HOSTS)


def ids(url: str) -> tuple[str, str] | None:
    """The station and the recording, straight out of the address."""
    found = RECORDING.search(urlparse(url).path)
    return (found.group(1), found.group(2)) if found else None


def api_for(url: str) -> str:
    """The API lives on api.<the domain you are looking at>, as the site's own script says."""
    parts = urlparse(url).netloc.lower().removeprefix("www.").split(".")
    domain = ".".join(parts[-2:]) if len(parts) >= 2 else parts[0]
    return f"https://api.{domain}/api/v2"


def ask(url: str, timeout: float = TIMEOUT) -> dict:
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {ANONYMOUS}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return json.loads(answer.read().decode("utf-8"))


def dutch_date(stamp: str) -> str:
    """2026-08-30T10:00:00+02:00 -> 30 augustus 2026."""
    found = re.match(r"(\d{4})-(\d{2})-(\d{2})", stamp or "")
    if not found:
        return ""
    year, month, day = found.groups()
    return f"{int(day)} {MONTHS[int(month) - 1]} {year}"


def read(answer: dict) -> Recording | None:
    """Pull the download link out of what the API said, or decide there is none."""
    data = answer.get("data") or {}
    said = data.get("attributes") or {}
    files = [item for item in answer.get("included") or [] if item.get("type") == "video_files"]
    for item in files:
        video = item.get("attributes") or {}
        link = video.get("download_url")
        if not link or video.get("locked") or video.get("private"):
            continue
        name = (said.get("title") or "Dienst").strip()
        when = dutch_date(said.get("start_at") or video.get("recorded_at") or "")
        return Recording(
            url=link,
            title=f"{name} · {when}" if when else name,
            duration=video.get("duration"),
            sermon_starts=video.get("sermon_start_time"),
        )
    return None


def resolve(url: str, timeout: float = TIMEOUT) -> Recording | None:
    """The recording behind this page address, or None if this route no longer works."""
    found = ids(url)
    if not found:
        return None
    station, recording = found
    try:
        answer = ask(f"{api_for(url)}/stations/{station}/recordings/{recording}?include=media", timeout)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None
    try:
        return read(answer)
    except (AttributeError, TypeError, KeyError):  # a shape we no longer recognise
        return None
