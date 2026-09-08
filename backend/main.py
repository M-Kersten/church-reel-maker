"""Church Reel Maker API. Run from the repository root:

    uvicorn backend.main:app --reload --port 8000
"""

import shutil
from pathlib import Path

import traceback

from fastapi import Body, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from . import brands, clips, discovery, fonts, health, outro, renderer, transcription
from .jobs import Cancelled, Estimator, Job, JobManager
from .models import (ROOT, TEMPLATES_DIR, ChurchInfo, ClipCandidate, ClipOrigin, CropWindow, MusicSettings, ProcessedClip, Project, Watermark,
                     ProjectDetail, Service, ServiceDetail, Style, Transcript, load_church_info, load_project,
                     load_service, load_service_transcript, load_transcript, new_project, new_service, project_dir,
                     recover_services, save_project, save_service, save_service_transcript, save_transcript, service_dir)
from .subtitles import write_ass

@asynccontextmanager
async def lifespan(app: FastAPI):
    transcription.load_vocabulary()  # writes templates/woordenlijst.json the first time
    stopped = recover_services()
    if stopped:
        print(f"[start] onderbroken diensten hersteld: {', '.join(stopped)}")
    # Rebuild the end screen when templates/outro.json or church.json changed.
    try:
        outro.ensure_outro()
    except Exception as exc:  # noqa: BLE001
        print(f"[outro] {exc}")
    yield


app = FastAPI(title="Church Reel Maker", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
jobs = JobManager()


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": f"Er ging iets mis in de app: {exc}"})

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}


def get_project(project_id: str) -> Project:
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "Project niet gevonden")
    return project


def detail(project: Project) -> ProjectDetail:
    if project.crop is None and project.sourceInfo is not None:
        project.crop = renderer.default_crop(project.sourceInfo, project.output)
    try:
        _path, start, _length = clips.source_of(project)
        present = True
    except clips.MissingFootage:
        start, present = 0.0, False
    return ProjectDetail(**project.model_dump(), transcriptData=load_transcript(project),
                         sourceStart=start, hasFootage=present)


@app.post("/projects", response_model=ProjectDetail)
def create_project():
    """A new clip starts from the active brand: its subtitle style and its music."""
    project = new_project()
    brand = brands.active()
    project.style = brand.subtitleStyle.model_copy(deep=True)
    project.music = brand.music.model_copy(deep=True)
    project.watermark = brand.watermark.model_copy(deep=True)
    save_project(project)
    return detail(project)


@app.get("/projects/{project_id}", response_model=ProjectDetail)
def read_project(project_id: str):
    return detail(get_project(project_id))


@app.post("/projects/{project_id}/upload", response_model=ProjectDetail)
def upload_video(project_id: str, file: UploadFile):
    project = get_project(project_id)
    ext = Path(file.filename or "").suffix.lower() or ".mp4"
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(400, f"Bestandstype {ext} wordt niet ondersteund; gebruik mp4, mov, m4v, mkv of webm")
    if project.sourceVideo:
        (project_dir(project.id) / project.sourceVideo).unlink(missing_ok=True)
    target = project_dir(project.id) / f"source{ext}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    try:
        info = renderer.probe(target)
    except Exception as exc:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise HTTPException(400, f"De video kan niet gelezen worden: {exc}") from exc
    project.sourceVideo = target.name
    project.sourceInfo = info
    project.crop = renderer.default_crop(info, project.output)
    save_project(project)
    return detail(project)


@app.get("/projects/{project_id}/source")
def read_source(project_id: str):
    """The footage behind this clip.

    For a clip cut from a service that is the whole recording; the interface skips to
    `sourceStart` and stops at the end of the range. Range requests keep that cheap.
    """
    project = get_project(project_id)
    try:
        path, _start, _length = clips.source_of(project)
    except clips.MissingFootage as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path)


# What each phase of writing out the speech is called, for the person watching the bar.
SPEECH_PHASE = {
    transcription.AUDIO: "Geluid wordt uit de video gehaald",
    transcription.MODEL: "Het spraakmodel wordt geladen",
    transcription.TEXT: "Gesproken tekst wordt uitgeschreven",
}


def transcribe_key(project_id: str) -> str:
    """Transcribing and rendering never overlap, but they report progress separately."""
    return f"{project_id}:transcribe"


@app.post("/projects/{project_id}/transcribe")
def transcribe_project(project_id: str):
    """Start writing out the speech. Follow it with GET /projects/{id}/transcribe-status."""
    project = get_project(project_id)
    if not project.sourceInfo:
        raise HTTPException(400, "Upload eerst een video")
    if not project.sourceInfo.hasAudio:
        raise HTTPException(400, "De video heeft geen geluid")
    if jobs.is_running(transcribe_key(project.id)):
        raise HTTPException(409, "De ondertitels worden al gemaakt")

    try:
        source, start, duration = clips.source_of(project)
    except clips.MissingFootage as exc:
        raise HTTPException(400, str(exc)) from exc
    work_dir = project_dir(project.id) / "work"

    def work(job: Job) -> None:
        left = Estimator(after=transcription.EXTRACT_SHARE + transcription.MODEL_SHARE)

        seen = {"phase": ""}

        def on_progress(fraction: float, phase: str) -> None:
            if phase != seen["phase"]:
                seen["phase"] = phase
                job.start_phase()
            job.advance(fraction)
            wording = SPEECH_PHASE[phase]
            job.message = left.note(fraction, wording) if phase == transcription.TEXT else wording

        transcript = transcription.transcribe(
            source, work_dir, on_progress=on_progress, duration=duration, should_stop=job.check,
            start=start,
        )
        save_transcript(get_project(project_id), transcript)

    return jobs.start(transcribe_key(project.id), work).to_dict()


@app.get("/projects/{project_id}/transcribe-status")
def transcribe_status(project_id: str):
    get_project(project_id)
    return jobs.get(transcribe_key(project_id)).to_dict()


@app.post("/projects/{project_id}/transcribe/stop")
def stop_transcribe(project_id: str):
    get_project(project_id)
    jobs.cancel(transcribe_key(project_id))
    return jobs.get(transcribe_key(project_id)).to_dict()


@app.put("/projects/{project_id}/transcript", response_model=Transcript)
def update_transcript(project_id: str, transcript: Transcript):
    project = get_project(project_id)
    transcript.segments = sorted(transcript.segments, key=lambda s: s.start)
    save_transcript(project, transcript)
    return transcript


@app.put("/projects/{project_id}/style", response_model=ProjectDetail)
def update_style(project_id: str, style: Style):
    project = get_project(project_id)
    if style.font not in fonts.names():
        raise HTTPException(400, f"onbekend lettertype: {style.font}")
    project.style = style
    save_project(project)
    return detail(project)


@app.put("/projects/{project_id}/crop", response_model=ProjectDetail)
def update_crop(project_id: str, crop: CropWindow):
    project = get_project(project_id)
    project.crop = crop
    save_project(project)
    return detail(project)


@app.post("/projects/{project_id}/render")
def render_project(project_id: str):
    project = get_project(project_id)
    if not project.sourceInfo:
        raise HTTPException(400, "Upload eerst een video")
    if jobs.is_running(project.id):
        raise HTTPException(409, "De video wordt al gemaakt")

    try:
        source, source_start, _length = clips.source_of(project)
    except clips.MissingFootage as exc:
        raise HTTPException(400, str(exc)) from exc
    info = project.sourceInfo
    transcript = load_transcript(project) or Transcript()
    work = project_dir(project.id) / "work"
    output_dir = project_dir(project.id) / "output"
    outro = ROOT / project.outro

    def work_fn(job: Job) -> None:
        job.message = "Afsluiter wordt voorbereid"
        try:
            outro.ensure_outro()
        except Exception as exc:  # noqa: BLE001
            print(f"[outro] {exc}")  # keep the existing outro.mp4 and carry on
        job.message = "Ondertitels worden voorbereid"
        subtitles = write_ass(transcript, project.style, project.output, work / "subtitles.ass")

        left = Estimator()

        def on_progress(fraction: float, message: str) -> None:
            job.advance(fraction)
            job.message = left.note(fraction, message)

        renderer.render_video(
            source, info, subtitles, project.output, output_dir / "final.mp4",
            outro=outro if outro.is_file() else None,
            crop_strategy=project.cropStrategy, tracking=project.tracking, crop=project.crop, music=project.music,
            watermark=project.watermark,
            source_start=None if project.sourceVideo else source_start,
            on_progress=on_progress, should_stop=job.check,
        )

    return jobs.start(project.id, work_fn).to_dict()


@app.post("/projects/{project_id}/render/stop")
def stop_render(project_id: str):
    project = get_project(project_id)
    if not jobs.cancel(project.id):
        raise HTTPException(409, "Er wordt op dit moment niets gemaakt")
    return jobs.get(project.id).to_dict()


@app.get("/projects/{project_id}/render-status")
def render_status(project_id: str):
    project = get_project(project_id)
    job = jobs.get(project.id)
    if job.status == "idle" and (project_dir(project.id) / "output" / "final.mp4").is_file():
        return {"status": "done", "progress": 1.0, "message": "Eerder gemaakt", "error": None}
    return job.to_dict()


@app.get("/projects/{project_id}/output")
def read_output(project_id: str):
    project = get_project(project_id)
    path = project_dir(project.id) / "output" / "final.mp4"
    if jobs.is_running(project.id) or not path.is_file():
        raise HTTPException(404, "Er is nog geen video gemaakt")
    name = brands.slug(project.title) if project.title else project.id
    return FileResponse(path, media_type="video/mp4", filename=f"{name}.mp4")


@app.get("/church", response_model=ChurchInfo)
def read_church():
    """The church of the brand that is active."""
    return brands.active().church


@app.get("/brands", response_model=list[brands.BrandSummary])
def read_brands():
    return brands.summaries()


@app.get("/brands/{brand_id}", response_model=brands.Brand)
def read_brand(brand_id: str):
    brand = brands.load(brand_id)
    if brand is None:
        raise HTTPException(404, "Merk niet gevonden")
    return brand


@app.put("/brands/{brand_id}", response_model=brands.Brand)
def update_brand(brand_id: str, brand: brands.Brand):
    if brands.load(brand_id) is None:
        raise HTTPException(404, "Merk niet gevonden")
    if brand.subtitleStyle.font not in fonts.names() or brand.outro.font not in fonts.names():
        raise HTTPException(400, "Onbekend lettertype")
    brand.id = brand_id
    brands.save(brand)
    if brands.active_id() == brand_id and brand.outro.generate:
        try:
            outro.build(brand.outro, brand.church)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc
    return brand


@app.post("/brands", response_model=brands.Brand)
def create_brand(name: str = Body(embed=True), copyFrom: str | None = Body(default=None, embed=True)):
    if not name.strip():
        raise HTTPException(400, "Geef het merk een naam")
    return brands.create(name.strip(), copyFrom)


@app.post("/brands/{brand_id}/activate", response_model=brands.Brand)
def activate_brand(brand_id: str):
    if brands.load(brand_id) is None:
        raise HTTPException(404, "Merk niet gevonden")
    brand = brands.set_active(brand_id)
    try:
        outro.ensure_outro()
    except Exception as exc:  # noqa: BLE001
        print(f"[outro] {exc}")
    return brand


@app.delete("/brands/{brand_id}", response_model=list[brands.BrandSummary])
def delete_brand(brand_id: str):
    if len(brands.all_brands()) <= 1:
        raise HTTPException(400, "Het laatste merk kan niet verwijderd worden")
    brands.delete(brand_id)
    return brands.summaries()


# --- logos ----------------------------------------------------------------------

LOGO_DIR = TEMPLATES_DIR / "logos"
ALLOWED_LOGOS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


@app.get("/logos")
def read_logos():
    """The logo files that can go in a corner of the clip or on the end screen."""
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    return [{"file": p.name} for p in sorted(LOGO_DIR.iterdir()) if p.suffix.lower() in ALLOWED_LOGOS]


@app.post("/logos")
def upload_logo(file: UploadFile):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_LOGOS:
        raise HTTPException(400, "Gebruik een png (met transparantie), jpg of webp")
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    target = LOGO_DIR / Path(file.filename or f"logo{ext}").name
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    return {"file": target.name}


@app.delete("/logos/{name}")
def delete_logo(name: str):
    target = LOGO_DIR / Path(name).name
    if not target.is_file():
        raise HTTPException(404, "Logo niet gevonden")
    target.unlink()
    return {"file": target.name}


# --- background music -----------------------------------------------------------

MUSIC_DIR = TEMPLATES_DIR / "music"
ALLOWED_MUSIC = {".mp3", ".m4a", ".wav", ".aac", ".ogg"}


@app.get("/music")
def read_music():
    """The music files that can go under a clip."""
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    return [{"file": p.name, "sizeMb": round(p.stat().st_size / 1e6, 1)}
            for p in sorted(MUSIC_DIR.iterdir()) if p.suffix.lower() in ALLOWED_MUSIC]


@app.post("/music")
def upload_music(file: UploadFile):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_MUSIC:
        raise HTTPException(400, "Gebruik een mp3-, m4a-, wav-, aac- of ogg-bestand")
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    target = MUSIC_DIR / Path(file.filename or f"muziek{ext}").name
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    return {"file": target.name}


@app.delete("/music/{name}")
def delete_music(name: str):
    target = MUSIC_DIR / Path(name).name
    if not target.is_file():
        raise HTTPException(404, "Muziekbestand niet gevonden")
    target.unlink()
    return {"file": target.name}


@app.put("/projects/{project_id}/meta", response_model=ProjectDetail)
def update_meta(project_id: str, title: str = Body(default="", embed=True), description: str = Body(default="", embed=True)):
    """The title names the downloaded file; the description is the text to paste under the post."""
    project = get_project(project_id)
    project.title = title.strip() or None
    project.description = description.strip()
    save_project(project)
    return detail(project)


@app.put("/projects/{project_id}/watermark", response_model=ProjectDetail)
def update_watermark(project_id: str, watermark: Watermark):
    project = get_project(project_id)
    if watermark.file and not (LOGO_DIR / Path(watermark.file).name).is_file():
        raise HTTPException(400, f"Het logo {watermark.file} staat niet in templates/logos")
    project.watermark = watermark
    save_project(project)
    return detail(project)


@app.put("/projects/{project_id}/music", response_model=ProjectDetail)
def update_music(project_id: str, music: MusicSettings):
    project = get_project(project_id)
    if music.file and not (MUSIC_DIR / Path(music.file).name).is_file():
        raise HTTPException(400, f"Het muziekbestand {music.file} staat niet in templates/music")
    project.music = music
    save_project(project)
    return detail(project)


@app.get("/health")
def read_health():
    """What the app needs to work: FFmpeg, the speech model, the analysis model, disk space, folders."""
    return health.report()


@app.get("/fonts", response_model=list[fonts.FontFamily])
def read_fonts():
    """Font families found in templates/fonts, plus the system font."""
    return fonts.catalogue()


@app.get("/outro", response_model=outro.OutroConfig)
def read_outro():
    """The look of the end screen, from templates/outro.json."""
    outro.save_default_config()
    return outro.load_config()


@app.put("/outro", response_model=outro.OutroConfig)
def update_outro(config: outro.OutroConfig):
    """Save the end-screen settings from the interface and rebuild the video."""
    for line in config.lines:
        if line.font and line.font not in fonts.names():
            raise HTTPException(400, f"onbekend lettertype: {line.font}")
    if config.font not in fonts.names():
        raise HTTPException(400, f"onbekend lettertype: {config.font}")
    outro.save_config(config)
    if config.generate:
        try:
            outro.build(config)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc
    return config


@app.post("/outro/background")
def upload_outro_background(file: UploadFile):
    """Store a background image for the end screen and return its file name."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Gebruik een jpg-, png- of webp-afbeelding")
    target = TEMPLATES_DIR / f"outro-achtergrond{ext}"
    for old in TEMPLATES_DIR.glob("outro-achtergrond.*"):
        old.unlink(missing_ok=True)
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    return {"image": target.name}


@app.post("/outro/rebuild", response_model=outro.OutroConfig)
def rebuild_outro():
    """Rebuild templates/outro.mp4 from the config after the user edited it."""
    config = outro.load_config()
    if not config.generate:
        raise HTTPException(400, 'In templates/outro.json staat "generate": false, dus de afsluiter blijft zoals hij is.')
    try:
        outro.build(config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return config



# --- full-service clip discovery ------------------------------------------------
#
# Discovery is an input layer for the clip editor above: it finds moments in a
# complete service and hands "source video + start + end" to clips.create_clip.


def get_service(service_id: str) -> Service:
    service = load_service(service_id)
    if service is None:
        raise HTTPException(404, "Dienst niet gevonden")
    return service


def service_detail(service: Service) -> ServiceDetail:
    job = jobs.get(service.id)
    transcript = load_service_transcript(service)
    return ServiceDetail(
        **service.model_dump(),
        transcriptData=transcript,
        analysis=discovery.estimate(transcript) if transcript else None,
        job=job.to_dict() if job.status == "running" else None,
    )


def set_status(service: Service, status: str, error: str | None = None) -> None:
    service.status = status  # type: ignore[assignment]
    service.error = error
    if status == "analyzing":
        service.warning = None
    save_service(service)


def run_service_job(service: Service, busy_status: str, done_status: str, work) -> ServiceDetail:
    """Run `work(job, service)` in the shared job manager and keep service.status in sync."""
    if jobs.is_running(service.id):
        raise HTTPException(409, "De dienst wordt nog verwerkt, wacht even")
    set_status(service, busy_status)

    def wrapped(job: Job) -> None:
        try:
            work(job, service)
            set_status(service, done_status)
        except Cancelled:
            set_status(service, "uploaded" if busy_status == "transcribing" else "transcribed"
                       if busy_status == "analyzing" else "ready")
            raise
        except Exception as exc:  # noqa: BLE001
            set_status(service, "error", str(exc))
            raise

    jobs.start(service.id, wrapped)
    return service_detail(service)


@app.post("/services", response_model=ServiceDetail)
def create_service():
    return service_detail(new_service())


@app.get("/services/{service_id}", response_model=ServiceDetail)
def read_service(service_id: str):
    return service_detail(get_service(service_id))


@app.post("/services/{service_id}/upload", response_model=ServiceDetail)
def upload_service_video(service_id: str, file: UploadFile):
    service = get_service(service_id)
    if jobs.is_running(service.id):
        raise HTTPException(409, "De dienst wordt nog verwerkt, wacht even")
    ext = Path(file.filename or "").suffix.lower() or ".mp4"
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(400, f"Bestandstype {ext} wordt niet ondersteund; gebruik mp4, mov, m4v, mkv of webm")
    if service.sourceVideo:
        (service_dir(service.id) / service.sourceVideo).unlink(missing_ok=True)
    target = service_dir(service.id) / f"source{ext}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    try:
        info = renderer.probe(target)
    except Exception as exc:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise HTTPException(400, f"De video kan niet gelezen worden: {exc}") from exc
    if not info.hasAudio:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "De video heeft geen geluid")
    service.sourceVideo = target.name
    service.sourceInfo = info
    service.title = Path(file.filename or "Service").stem or "Service"
    service.transcript = None
    service.candidates = []
    set_status(service, "uploaded")
    return service_detail(service)


@app.get("/services/{service_id}/source")
def read_service_source(service_id: str):
    service = get_service(service_id)
    if not service.sourceVideo:
        raise HTTPException(404, "Er is nog geen video geüpload")
    return FileResponse(service_dir(service.id) / service.sourceVideo)


@app.post("/services/{service_id}/transcribe", response_model=ServiceDetail)
def transcribe_service(service_id: str):
    service = get_service(service_id)
    if not service.sourceVideo or not service.sourceInfo:
        raise HTTPException(400, "Upload eerst een video")

    def work(job: Job, service: Service) -> None:
        job.message = SPEECH_PHASE[transcription.AUDIO]
        # The three phases run at different speeds, so the estimate only counts the last one.
        left = Estimator(after=transcription.EXTRACT_SHARE + transcription.MODEL_SHARE)

        seen = {"phase": ""}

        def on_progress(fraction: float, phase: str) -> None:
            if phase != seen["phase"]:
                seen["phase"] = phase
                job.start_phase()
            job.advance(fraction)
            wording = SPEECH_PHASE[phase]
            job.message = left.note(fraction, wording) if phase == transcription.TEXT else wording

        transcript = transcription.transcribe(
            service_dir(service.id) / service.sourceVideo, service_dir(service.id) / "work",
            on_progress=on_progress, duration=service.sourceInfo.duration, should_stop=job.check,
            accurate=service.accurate,
        )
        save_service_transcript(service, transcript)

    return run_service_job(service, "transcribing", "transcribed", work)


@app.put("/services/{service_id}/accuracy", response_model=ServiceDetail)
def set_accuracy(service_id: str, accurate: bool = Body(default=False, embed=True)):
    """Choose between the quick model and the one that hears more. Takes effect next run."""
    service = get_service(service_id)
    service.accurate = accurate
    save_service(service)
    return service_detail(service)


@app.post("/services/{service_id}/analyze", response_model=ServiceDetail)
def analyze_service(service_id: str):
    service = get_service(service_id)
    transcript = load_service_transcript(service)
    if transcript is None:
        raise HTTPException(400, "Schrijf de dienst eerst uit")

    def work(job: Job, service: Service) -> None:
        def on_progress(fraction: float, message: str) -> None:
            job.advance(fraction)
            job.message = message

        result = discovery.discover(transcript, on_progress, should_stop=job.check)
        service.candidates = result.candidates
        service.warning = result.warning
        save_service(service)

    return run_service_job(service, "analyzing", "ready", work)


@app.get("/services/{service_id}/status")
def read_service_status(service_id: str):
    """Small payload for polling: the transcript itself would be sent over and over."""
    service = get_service(service_id)
    job = jobs.get(service.id)
    return {
        "status": service.status,
        "error": service.error,
        "warning": service.warning,
        "job": job.to_dict() if job.status == "running" else None,
        "candidates": len(service.candidates),
        "clips": len(service.clips),
    }


@app.post("/services/{service_id}/stop", response_model=ServiceDetail)
def stop_service_job(service_id: str):
    """Stop the transcription, the analysis or the clip cutting that is running."""
    service = get_service(service_id)
    if not jobs.cancel(service.id):
        raise HTTPException(409, "Er is niets bezig voor deze dienst")
    return service_detail(service)


@app.get("/services/{service_id}/candidates", response_model=list[ClipCandidate])
def read_candidates(service_id: str):
    return get_service(service_id).candidates


@app.put("/services/{service_id}/candidates", response_model=list[ClipCandidate])
def update_candidates(service_id: str, candidates: list[ClipCandidate]):
    """Save user adjustments: selection and boundary changes. Order is preserved as given."""
    service = get_service(service_id)
    if jobs.is_running(service.id):
        raise HTTPException(409, "De dienst wordt nog verwerkt, wacht even")
    duration = service.sourceInfo.duration if service.sourceInfo else None
    for cand in candidates:
        if cand.end <= cand.start or cand.start < 0 or (duration and cand.end > duration + 0.5):
            raise HTTPException(400, f"Ongeldig begin of einde bij fragment {cand.id}")
    service.candidates = candidates
    save_service(service)
    return service.candidates


@app.post("/services/{service_id}/process-selected", response_model=ServiceDetail)
def process_selected(service_id: str):
    """Hand every selected candidate to the existing clip pipeline (clips.create_clip)."""
    service = get_service(service_id)
    if not service.sourceVideo:
        raise HTTPException(400, "Upload eerst een video")
    selected = [c for c in service.candidates if c.selected]
    if not selected:
        raise HTTPException(400, "Er zijn geen fragmenten gekozen")
    source = service_dir(service.id) / service.sourceVideo
    transcript = load_service_transcript(service)

    def work(job: Job, service: Service) -> None:
        for n, cand in enumerate(selected, start=1):
            job.check()
            job.progress, job.message = (n - 1) / len(selected), f"Fragment {n} van {len(selected)} wordt klaargezet"
            project = clips.create_clip(
                source, cand.start, cand.end, transcript, title=cand.title,
                origin=ClipOrigin(serviceId=service.id, candidateId=cand.id, start=cand.start, end=cand.end),
                source_info=service.sourceInfo,
            )
            service.clips.append(ProcessedClip(
                candidateId=cand.id, projectId=project.id, title=cand.title, start=cand.start, end=cand.end,
                createdAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ))
            for c in service.candidates:
                if c.id == cand.id:
                    c.selected = False
            save_service(service)

    return run_service_job(service, "processing", "complete", work)


# Fonts and the outro template, used by the preview.
app.mount("/templates", StaticFiles(directory=TEMPLATES_DIR), name="templates")

# Serve the built frontend when it exists (npm run build), so one process runs the whole app.
dist = ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
