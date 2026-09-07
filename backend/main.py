"""Church Reel Maker API. Run from the repository root:

    uvicorn backend.main:app --reload --port 8000
"""

import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import renderer, transcription
from .jobs import Job, JobManager
from .models import (FONTS, ROOT, TEMPLATES_DIR, ChurchInfo, Project, ProjectDetail, Style, Transcript,
                     load_church_info, load_project, load_transcript, new_project, project_dir, save_project,
                     save_transcript)
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
            crop_strategy=project.cropStrategy, tracking=project.tracking, on_progress=on_progress,
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


# Fonts and the outro template, used by the preview.
app.mount("/templates", StaticFiles(directory=TEMPLATES_DIR), name="templates")

# Serve the built frontend when it exists (npm run build), so one process runs the whole app.
dist = ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
