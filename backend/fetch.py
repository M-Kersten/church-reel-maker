"""Bringing a service in from a link instead of a file.

Most churches already publish the service somewhere: YouTube, Vimeo, a church-stream
platform, or a plain mp4 on their own website. Uploading the same recording a second time
means finding it on disk first and then waiting out a two-gigabyte copy, so pasting the
address it already lives at is the shorter way in.

The downloading itself is yt-dlp's job. It knows well over a thousand sites, and for a page
it does not know it still reads the page for an embedded player, an og:video tag or a
playlist. What this module adds is the part yt-dlp has no opinion about: which links are
worth trying, how far along a download is, stopping halfway, and saying in Dutch what went
wrong when a link cannot be used.
"""

import re
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .jobs import Cancelled

ProgressCallback = Callable[[float, str], None]

# Suffixes that mean the link points straight at a video rather than at a page about one.
MEDIA_SUFFIXES = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".m3u8", ".mpd", ".ts"}

# What a download is allowed to weigh, so a mistyped link cannot fill the disk.
MAX_GB = 12.0

# Sites we know hand their video to a player over a private call, so the page address alone
# is not enough. Rather than a bare "unsupported", say what does work there.
SITE_ADVICE = {
    "kerkdienstgemist.nl": (
        "Kerkdienstgemist geeft de video pas aan zijn eigen speler, dus aan het adres van de "
        "pagina heeft de app niets. Log in op het account van de kerk, kies bij de dienst "
        "Downloaden, en plak dan de downloadlink hier. Of download het bestand en sleep het "
        "hierboven naar binnen."
    ),
    "kerkomroep.nl": (
        "Kerkomroep geeft de video pas aan zijn eigen speler. Download de dienst daar en "
        "sleep het bestand hierboven naar binnen."
    ),
}


class LinkNotUsable(RuntimeError):
    """The link cannot be turned into a recording, with a reason a volunteer can act on."""


def tidy(text: str) -> str:
    """What someone pastes is not always only the address."""
    url = text.strip().strip('<>"\'')
    if url and "://" not in url and re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", url, re.I):
        url = "https://" + url  # people paste "youtube.com/watch?v=..." without the scheme
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LinkNotUsable("Dat is geen webadres. Plak de link zoals hij in de adresbalk van "
                            "je browser staat, beginnend met https://")
    return url


def host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def advice_for(url: str) -> str | None:
    """The site-specific note, if we have one for this host or a parent of it."""
    name = host(url)
    for site, said in SITE_ADVICE.items():
        if name == site or name.endswith("." + site):
            return said
    return None


def is_direct_media(url: str) -> bool:
    return Path(urlparse(url).path).suffix.lower() in MEDIA_SUFFIXES


def safe_title(name: str) -> str:
    """A recording's own name, trimmed to something that reads well in the interface."""
    name = re.sub(r"\s+", " ", (name or "").strip())
    return name[:80] or "Dienst"


class Hush:
    """yt-dlp writes its complaints to the console; here they belong in the message instead."""

    def debug(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


def options(folder: Path, hook) -> dict:
    """How to ask for a recording: one video, with sound, as mp4 where the site allows it."""
    return {
        "outtmpl": str(folder / "source.%(ext)s"),
        # Prefer a single mp4 with sound; fall back to merging the best video and audio.
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,  # a link into a playlist means that one service, not the series
        "restrictfilenames": True,
        "overwrites": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "consoletitle": False,
        "retries": 3,
        "fragment_retries": 5,
        "progress_hooks": [hook],
        "max_filesize": int(MAX_GB * 1024 ** 3),
        "logger": Hush(),
    }


def readable(message: str, url: str) -> str:
    """Turn yt-dlp's English complaint into something worth reading."""
    said = re.sub(r"^ERROR:\s*", "", message.strip())
    said = re.sub(r"\s*;\s*please report this issue.*$", "", said, flags=re.I | re.S)
    low = said.lower()
    note = advice_for(url)
    if "unsupported url" in low or "no video" in low or "unable to extract" in low:
        if note:
            return note
        return (f"Op {host(url)} is via deze link geen video te vinden. Staat de dienst op YouTube "
                "of Vimeo, plak dan die link. Anders: download het bestand en sleep het hierboven "
                "naar binnen.")
    if "private" in low or "login" in low or "sign in" in low or "members-only" in low:
        return ("Deze video is niet openbaar, dus de app komt er niet bij. Zet hem op verborgen "
                "in plaats van privé, of download het bestand en sleep het hierboven naar binnen.")
    if "geo" in low and "block" in low:
        return "Deze video is in Nederland niet beschikbaar."
    if "max-filesize" in low or "larger than" in low:
        return f"Deze opname is groter dan {MAX_GB:.0f} GB. Download hem zelf en knip hem eerst korter."
    if "404" in said or "not found" in low:
        return "Op dit adres staat niets (meer). Controleer de link."
    return f"De opname kon niet opgehaald worden: {said[:300]}"


def sweep(folder: Path) -> None:
    """Half-downloaded pieces are of no use to anyone; they only take up room."""
    for leftover in folder.glob("source.*"):
        if leftover.suffix in {".part", ".ytdl"} or ".part-" in leftover.name:
            leftover.unlink(missing_ok=True)


def fetch(url: str, folder: Path, on_progress: ProgressCallback | None = None,
          should_stop: Callable[[], None] | None = None) -> tuple[Path, str]:
    """Download what `url` points at into `folder`. Returns the file and its own title."""
    url = tidy(url)
    try:
        import yt_dlp
    except ImportError as exc:
        raise LinkNotUsable(
            "Het onderdeel dat video's van een link haalt ontbreekt. Sluit de app en start "
            "opnieuw met start.bat of start.command; het wordt dan geïnstalleerd."
        ) from exc

    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("source.*"):
        old.unlink(missing_ok=True)

    stopped = False

    def hook(state: dict) -> None:
        nonlocal stopped
        if should_stop:
            try:
                should_stop()
            except Cancelled:
                stopped = True
                raise yt_dlp.utils.DownloadCancelled from None
        if not on_progress:
            return
        if state.get("status") == "downloading":
            total = state.get("total_bytes") or state.get("total_bytes_estimate") or 0
            done = state.get("downloaded_bytes") or 0
            share = min(0.99, done / total) if total else 0.0
            on_progress(share, f"Opname wordt opgehaald · {int(share * 100)}%")
        elif state.get("status") == "finished":
            on_progress(0.99, "Opname wordt klaargezet")

    with yt_dlp.YoutubeDL(options(folder, hook)) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadCancelled as exc:
            sweep(folder)
            raise Cancelled() from exc
        except yt_dlp.utils.DownloadError as exc:
            sweep(folder)
            if stopped:
                raise Cancelled() from exc
            raise LinkNotUsable(readable(str(exc), url)) from exc
        except Cancelled:
            sweep(folder)
            raise
        except Exception as exc:  # noqa: BLE001  any other failure is still just a bad link
            sweep(folder)
            raise LinkNotUsable(readable(str(exc), url)) from exc

    sweep(folder)  # the bookkeeping files a finished download leaves behind
    written = sorted(folder.glob("source.*"), key=lambda p: p.stat().st_size, reverse=True)
    if not written:
        raise LinkNotUsable("De opname is niet binnengekomen. Probeer het opnieuw, of download "
                            "het bestand en sleep het hierboven naar binnen.")
    title = safe_title((info or {}).get("title", "")) if isinstance(info, dict) else "Dienst"
    return written[0], title
