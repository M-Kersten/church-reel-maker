"""Church Reel Maker API. Run from the repository root:

    uvicorn backend.main:app --reload --port 8000
"""

import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from datetime import datetime, timezone

from . import clips, discovery, renderer, transcription
from .jobs import Job, JobManager
from .models import (FONTS, ROOT, TEMPLATES_DIR, ChurchInfo, ClipCandidate, ClipOrigin, CropWindow, ProcessedClip, Project,
                     ProjectDetail, Service, ServiceDetail, Style, Transcript, load_church_info, load_project,
                     load_service, load_service_transcript, load_transcript, new_project, new_service, project_dir,
                     save_project, save_service, save_service_transcript, save_transcript, service_dir)
from .subtitles import write_ass

app = FastAPI(title="Church Reel Maker")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
jobs = JobManager()

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}


def get_project(project_id: str) -> Project:
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


def detail(project: Project) -> ProjectDetail:
    if project.crop is None and project.sourceInfo is not None:
        project.crop = renderer.default_crop(project.sourceInfo, project.output)
    return ProjectDetail(**project.model_dump(), transcriptData=load_transcript(project))


@app.post("/projects", response_model=ProjectDetail)
def create_project():
    return detail(new_project())


@app.get("/projects/{project_id}", response_model=ProjectDetail)
def read_project(project_id: str):
    return detail(get_project(project_id))


@app.post("/projects/{project_id}/upload", response_model=ProjectDetail)
def upload_video(project_id: str, file: UploadFile):
    project = get_project(project_id)
    ext = Path(file.filename or "").suffix.lower() or ".mp4"
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(400, f"unsupported file type {ext}")
    if project.sourceVideo:
        (project_dir(project.id) / project.sourceVideo).unlink(missing_ok=True)
    target = project_dir(project.id) / f"source{ext}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    try:
        info = renderer.probe(target)
    except Exception as exc:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise HTTPException(400, f"could not read video: {exc}") from exc
    project.sourceVideo = target.name
    project.sourceInfo = info
    project.crop = renderer.default_crop(info, project.output)
    save_project(project)
    return detail(project)


@app.get("/projects/{project_id}/source")
def read_source(project_id: str):
    project = get_project(project_id)
    if not project.sourceVideo:
        raise HTTPException(404, "no video uploaded")
    return FileResponse(project_dir(project.id) / project.sourceVideo)


@app.post("/projects/{project_id}/transcribe", response_model=Transcript)
def transcribe_project(project_id: str):
    project = get_project(project_id)
    if not project.sourceVideo or not project.sourceInfo:
        raise HTTPException(400, "upload a video first")
    if not project.sourceInfo.hasAudio:
        raise HTTPException(400, "the video has no audio track")
    transcript = transcription.transcribe(project_dir(project.id) / project.sourceVideo, project_dir(project.id) / "work")
    save_transcript(project, transcript)
    return transcript


@app.put("/projects/{project_id}/transcript", response_model=Transcript)
def update_transcript(project_id: str, transcript: Transcript):
    project = get_project(project_id)
    transcript.segments = sorted(transcript.segments, key=lambda s: s.start)
    save_transcript(project, transcript)
    return transcript


@app.put("/projects/{project_id}/style", response_model=ProjectDetail)
def update_style(project_id: str, style: Style):
    project = get_project(project_id)
    if style.font not in FONTS:
        raise HTTPException(400, f"font must be one of {FONTS}")
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
    if not project.sourceVideo or not project.sourceInfo:
        raise HTTPException(400, "upload a video first")
    if jobs.is_running(project.id):
        raise HTTPException(409, "render already running")

    source = project_dir(project.id) / project.sourceVideo
    info = project.sourceInfo
    transcript = load_transcript(project) or Transcript()
    work = project_dir(project.id) / "work"
    output_dir = project_dir(project.id) / "output"
    outro = ROOT / project.outro

    def work_fn(job: Job) -> None:
        job.message = "Writing subtitles"
        subtitles = write_ass(transcript, project.style, project.output, work / "subtitles.ass")

        def on_progress(fraction: float, message: str) -> None:
            job.progress, job.message = fraction, message

        renderer.render_video(
            source, info, subtitles, project.output, output_dir / "final.mp4",
            outro=outro if outro.is_file() else None,
            crop_strategy=project.cropStrategy, tracking=project.tracking, crop=project.crop,
            on_progress=on_progress,
        )

    return jobs.start(project.id, work_fn).to_dict()


@app.get("/projects/{project_id}/render-status")
def render_status(project_id: str):
    project = get_project(project_id)
    job = jobs.get(project.id)
    if job.status == "idle" and (project_dir(project.id) / "output" / "final.mp4").is_file():
        return {"status": "done", "progress": 1.0, "message": "Rendered earlier", "error": None}
    return job.to_dict()


@app.get("/projects/{project_id}/output")
def read_output(project_id: str):
    project = get_project(project_id)
    path = project_dir(project.id) / "output" / "final.mp4"
    if jobs.is_running(project.id) or not path.is_file():
        raise HTTPException(404, "no rendered video yet")
    return FileResponse(path, media_type="video/mp4", filename=f"{project.id}-reel.mp4")


@app.get("/church", response_model=ChurchInfo)
def read_church():
    return load_church_info()



# --- full-service clip discovery ------------------------------------------------
#
# Discovery is an input layer for the clip editor above: it finds moments in a
# complete service and hands "source video + start + end" to clips.create_clip.


def get_service(service_id: str) -> Service:
    service = load_service(service_id)
    if service is None:
        raise HTTPException(404, "service not found")
    return service


def service_detail(service: Service) -> ServiceDetail:
    job = jobs.get(service.id)
    return ServiceDetail(
        **service.model_dump(),
        transcriptData=load_service_transcript(service),
        job=job.to_dict() if job.status == "running" else None,
    )


def set_status(service: Service, status: str, error: str | None = None) -> None:
    service.status = status  # type: ignore[assignment]
    service.error = error
    save_service(service)


def run_service_job(service: Service, busy_status: str, done_status: str, work) -> ServiceDetail:
    """Run `work(job, service)` in the shared job manager and keep service.status in sync."""
    if jobs.is_running(service.id):
        raise HTTPException(409, "the service is busy")
    set_status(service, busy_status)

    def wrapped(job: Job) -> None:
        try:
            work(job, service)
            set_status(service, done_status)
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
        raise HTTPException(409, "the service is busy")
    ext = Path(file.filename or "").suffix.lower() or ".mp4"
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(400, f"unsupported file type {ext}")
    if service.sourceVideo:
        (service_dir(service.id) / service.sourceVideo).unlink(missing_ok=True)
    target = service_dir(service.id) / f"source{ext}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    try:
        info = renderer.probe(target)
    except Exception as exc:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise HTTPException(400, f"could not read video: {exc}") from exc
    if not info.hasAudio:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "the video has no audio track")
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
        raise HTTPException(404, "no video uploaded")
    return FileResponse(service_dir(service.id) / service.sourceVideo)


@app.post("/services/{service_id}/transcribe", response_model=ServiceDetail)
def transcribe_service(service_id: str):
    service = get_service(service_id)
    if not service.sourceVideo or not service.sourceInfo:
        raise HTTPException(400, "upload a video first")

    def work(job: Job, service: Service) -> None:
        job.message = "Extracting audio"

        def on_progress(fraction: float) -> None:
            job.progress, job.message = fraction, "Transcribing"

        transcript = transcription.transcribe(
            service_dir(service.id) / service.sourceVideo, service_dir(service.id) / "work",
            on_progress=on_progress, duration=service.sourceInfo.duration,
        )
        save_service_transcript(service, transcript)

    return run_service_job(service, "transcribing", "transcribed", work)


@app.post("/services/{service_id}/analyze", response_model=ServiceDetail)
def analyze_service(service_id: str):
    service = get_service(service_id)
    transcript = load_service_transcript(service)
    if transcript is None:
        raise HTTPException(400, "transcribe the service first")

    def work(job: Job, service: Service) -> None:
        def on_progress(fraction: float, message: str) -> None:
            job.progress, job.message = fraction, message

        service.candidates = discovery.discover(transcript, on_progress)
        save_service(service)

    return run_service_job(service, "analyzing", "ready", work)


@app.get("/services/{service_id}/candidates", response_model=list[ClipCandidate])
def read_candidates(service_id: str):
    return get_service(service_id).candidates


@app.put("/services/{service_id}/candidates", response_model=list[ClipCandidate])
def update_candidates(service_id: str, candidates: list[ClipCandidate]):
    """Save user adjustments: selection and boundary changes. Order is preserved as given."""
    service = get_service(service_id)
    if jobs.is_running(service.id):
        raise HTTPException(409, "the service is busy")
    duration = service.sourceInfo.duration if service.sourceInfo else None
    for cand in candidates:
        if cand.end <= cand.start or cand.start < 0 or (duration and cand.end > duration + 0.5):
            raise HTTPException(400, f"invalid boundaries for {cand.id}")
    service.candidates = candidates
    save_service(service)
    return service.candidates


@app.post("/services/{service_id}/process-selected", response_model=ServiceDetail)
def process_selected(service_id: str):
    """Hand every selected candidate to the existing clip pipeline (clips.create_clip)."""
    service = get_service(service_id)
    if not service.sourceVideo:
        raise HTTPException(400, "upload a video first")
    selected = [c for c in service.candidates if c.selected]
    if not selected:
        raise HTTPException(400, "no candidates selected")
    source = service_dir(service.id) / service.sourceVideo
    transcript = load_service_transcript(service)

    def work(job: Job, service: Service) -> None:
        for n, cand in enumerate(selected, start=1):
            job.progress, job.message = (n - 1) / len(selected), f"Processing clip {n} of {len(selected)}"
            project = clips.create_clip(
                source, cand.start, cand.end, transcript, title=cand.title,
                origin=ClipOrigin(serviceId=service.id, candidateId=cand.id, start=cand.start, end=cand.end),
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
