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
SITE = "kerkdienstgemist.nl"  # the one a Dutch church is on unless it says otherwise
TIMEOUT = 30.0
HOW_MANY = 10  # what one page of the recordings list holds

MONTHS = ["januari", "februari", "maart", "april", "mei", "juni",
          "juli", "augustus", "september", "oktober", "november", "december"]


@dataclass
class Recording:
    url: str  # the signed link the download button points at
    title: str
    duration: float | None = None
    sermon_starts: float | None = None  # the platform's own guess at where the preaching begins


@dataclass
class Service:
    """One service in a station's list, as something to choose from."""

    id: str
    title: str
    when: str  # 2026-08-30T10:00:00+02:00, as the platform gives it
    url: str  # the page address, which is what the app knows how to fetch
    duration: float | None = None


@dataclass
class Station:
    """A church as the platform knows it."""

    id: str
    name: str
    url: str
    services: list[Service]


def handles(url: str) -> bool:
    name = urlparse(url).netloc.lower().removeprefix("www.")
    return any(name == host or name.endswith("." + host) for host in HOSTS)


def ids(url: str) -> tuple[str, str] | None:
    """The station and the recording, straight out of the address."""
    found = RECORDING.search(urlparse(url).path)
    return (found.group(1), found.group(2)) if found else None


def api_of(site: str) -> str:
    """The API lives on api.<domain>, as the site's own script says."""
    return f"https://api.{site}/api/v2"


def api_for(url: str) -> str:
    """The API belonging to the page you are looking at."""
    parts = urlparse(url).netloc.lower().removeprefix("www.").split(".")
    return api_of(".".join(parts[-2:]) if len(parts) >= 2 else parts[0])


def station_url(station_id: str, site: str = SITE) -> str:
    return f"https://{site}/stations/{station_id}"


def page_url(station_id: str, recording_id: str, site: str = SITE) -> str:
    """The address of one service, the same one you would copy from your browser."""
    return f"https://{site}/stations/{station_id}/events/recording/{recording_id}"


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


# --- the church's own list of services ------------------------------------------


class NotFound(RuntimeError):
    """No station with this number, or the platform will not talk about it."""


def services_in(answer: dict, station_id: str, site: str) -> list[Service]:
    """The recordings out of a listing, newest first, minus the ones that cannot be had."""
    media = {item["id"]: (item.get("attributes") or {})
             for item in answer.get("included") or [] if item.get("type") == "video_files"}
    out: list[Service] = []
    for item in answer.get("data") or []:
        said = item.get("attributes") or {}
        if said.get("private"):
            continue
        refs = ((item.get("relationships") or {}).get("media") or {}).get("data") or []
        video = media.get(refs[0]["id"], {}) if refs else {}
        if video.get("locked") or video.get("private"):
            continue
        out.append(Service(
            id=str(item.get("id", "")),
            title=(said.get("title") or "Dienst").strip(),
            when=said.get("start_at") or video.get("recorded_at") or "",
            url=page_url(station_id, str(item.get("id", "")), site),
            duration=video.get("duration"),
        ))
    return out


def station(station_id: str, site: str = SITE, timeout: float = TIMEOUT) -> Station:
    """The church behind a station number, and the services it has standing.

    One call for the name and one for the list. Raises NotFound with something worth
    reading, because this one is asked for on purpose rather than tried in passing.
    """
    station_id = str(station_id).strip()
    if not station_id.isdigit():
        raise NotFound("Een stationnummer bestaat alleen uit cijfers. Je vindt het in het adres "
                       "van de pagina van je kerk: kerkdienstgemist.nl/stations/1341 → 1341.")
    base = f"{api_of(site)}/stations/{station_id}"
    try:
        about = ask(base, timeout)
        listing = ask(f"{base}/recordings?include=media", timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound(f"Er is geen kerk met nummer {station_id} op {site}. Controleer het "
                           "nummer in het adres van de pagina van je kerk.") from exc
        raise NotFound(f"{site} antwoordde niet zoals verwacht ({exc.code}). Probeer het later "
                       "nog eens.") from exc
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise NotFound(f"Geen verbinding met {site}. Kijk of je internet het doet.") from exc

    try:
        said = (about.get("data") or {}).get("attributes") or {}
        return Station(
            id=station_id,
            name=(said.get("name") or f"Station {station_id}").strip(),
            url=station_url(station_id, site),
            services=services_in(listing, station_id, site),
        )
    except (AttributeError, TypeError, KeyError) as exc:  # a shape we no longer recognise
        raise NotFound("Kerkdienstgemist antwoordde in een vorm die de app niet kent. Plak het "
                       "adres van de dienst zolang zelf hieronder.") from exc
