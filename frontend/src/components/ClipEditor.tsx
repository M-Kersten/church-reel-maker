import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type ChurchInfo, type Project, type RenderStatus, type Segment, type Style } from '../api'
import RenderControls from './RenderControls'
import StylePanel from './StylePanel'
import SubtitleEditor from './SubtitleEditor'
import VideoPreview, { type PreviewHandle } from './VideoPreview'

const IDLE: RenderStatus = { status: 'idle', progress: 0, message: '', error: null }
const STORAGE_KEY = 'church-reel-maker.project'

interface Props {
  /** Project to open (for example a clip cut from a full service). */
  projectId: string | null
  onProjectChange: (id: string) => void
}

/** The Part 1 single-clip editor: upload, transcribe, subtitles, style, preview, render. */
export default function ClipEditor({ projectId, onProjectChange }: Props) {
  const [project, setProject] = useState<Project | null>(null)
  const [segments, setSegments] = useState<Segment[]>([])
  const [style, setStyle] = useState<Style | null>(null)
  const [church, setChurch] = useState<ChurchInfo | null>(null)
  const [renderStatus, setRenderStatus] = useState<RenderStatus>(IDLE)
  const [uploading, setUploading] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [outputVersion, setOutputVersion] = useState(0)
  const previewRef = useRef<PreviewHandle>(null)
  const dirty = useRef({ transcript: false, style: false })

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))

  const adopt = useCallback((p: Project) => {
    setProject(p)
    setStyle(p.style)
    setSegments(p.transcriptData?.segments ?? [])
    localStorage.setItem(STORAGE_KEY, p.id)
    onProjectChange(p.id)
  }, [onProjectChange])

  useEffect(() => {
    api.church().then(setChurch).catch(() => setChurch(null))
  }, [])

  // Open the requested project (or the last one after a page reload).
  useEffect(() => {
    const wanted = projectId ?? localStorage.getItem(STORAGE_KEY)
    if (!wanted || wanted === project?.id) return
    api
      .getProject(wanted)
      .then((p) => {
        adopt(p)
        dirty.current = { transcript: false, style: false }
        return api.renderStatus(p.id)
      })
      .then(setRenderStatus)
      .catch(() => localStorage.removeItem(STORAGE_KEY))
  }, [projectId, project?.id, adopt])

  const upload = async (file: File) => {
    setError(null)
    setUploading(true)
    try {
      const p = project?.sourceVideo ? await api.createProject() : project ?? (await api.createProject())
      adopt(await api.upload(p.id, file))
      setRenderStatus(IDLE)
      setSegments([])
    } catch (e) {
      fail(e)
    } finally {
      setUploading(false)
    }
  }

  // Debounced auto-save of subtitles and style.
  useEffect(() => {
    if (!project || !dirty.current.transcript) return
    const handle = setTimeout(() => {
      dirty.current.transcript = false
      api.saveTranscript(project.id, { language: 'nl', segments }).catch(fail)
    }, 600)
    return () => clearTimeout(handle)
  }, [segments, project])

  useEffect(() => {
    if (!project || !style || !dirty.current.style) return
    const handle = setTimeout(() => {
      dirty.current.style = false
      api.saveStyle(project.id, style).catch(fail)
    }, 400)
    return () => clearTimeout(handle)
  }, [style, project])

  const changeSegments = (next: Segment[]) => {
    dirty.current.transcript = true
    setSegments(next)
  }
  const changeStyle = (next: Style) => {
    dirty.current.style = true
    setStyle(next)
  }

  const transcribe = async () => {
    if (!project) return
    setError(null)
    setTranscribing(true)
    try {
      const t = await api.transcribe(project.id)
      dirty.current.transcript = false
      setSegments(t.segments)
    } catch (e) {
      fail(e)
    } finally {
      setTranscribing(false)
    }
  }

  const render = async () => {
    if (!project || !style) return
    setError(null)
    try {
      // Flush pending edits before rendering.
      await api.saveTranscript(project.id, { language: 'nl', segments })
      await api.saveStyle(project.id, style)
      dirty.current = { transcript: false, style: false }
      setRenderStatus(await api.render(project.id))
    } catch (e) {
      fail(e)
    }
  }

  // Poll render progress while a job runs.
  useEffect(() => {
    if (!project || renderStatus.status !== 'running') return
    const handle = setInterval(async () => {
      try {
        const s = await api.renderStatus(project.id)
        setRenderStatus(s)
        if (s.status === 'done') setOutputVersion((v) => v + 1)
      } catch (e) {
        fail(e)
      }
    }, 1000)
    return () => clearInterval(handle)
  }, [project, renderStatus.status])

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) void upload(file)
  }

  const hasVideo = Boolean(project?.sourceVideo && project.sourceInfo)

  return (
    <div>
      <p className="meta">
        {project ? `${project.title ? `${project.title} · ` : ''}${project.id}` : 'no project'}
        {project?.origin ? ` · cut from ${project.origin.serviceId}` : ''}
        {church ? ` · ${church.churchName}` : ''}
      </p>

      {error && <div className="error">{error}</div>}

      <label
        className={`dropzone ${dragging ? 'active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        style={{ marginBottom: '1.25rem', padding: hasVideo ? '1rem' : undefined }}
      >
        <input type="file" accept="video/*,.mp4,.mov,.m4v,.mkv,.webm" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        {uploading ? 'Uploading…' : hasVideo ? 'Drop another clip here to start a new project' : 'Drop a video clip here or click to choose one'}
      </label>

      {project && style && hasVideo && (
        <div className="layout">
          <div className="sticky">
            <VideoPreview
              ref={previewRef}
              sourceUrl={api.sourceUrl(project.id)}
              sourceInfo={project.sourceInfo!}
              outroUrl={api.outroUrl()}
              church={church}
              segments={segments}
              style={style}
              output={project.output}
              onTime={setCurrentTime}
            />
          </div>
          <div>
            <SubtitleEditor segments={segments} currentTime={currentTime} onChange={changeSegments} onSeek={(t) => previewRef.current?.seek(t)} />
            <StylePanel style={style} onChange={changeStyle} />
            <RenderControls
              canTranscribe={Boolean(project.sourceInfo?.hasAudio)}
              transcribing={transcribing}
              canRender={hasVideo}
              renderStatus={renderStatus}
              outputUrl={renderStatus.status === 'done' ? `${api.outputUrl(project.id)}?v=${outputVersion}` : null}
              onTranscribe={transcribe}
              onRender={render}
            />
          </div>
        </div>
      )}
    </div>
  )
}
