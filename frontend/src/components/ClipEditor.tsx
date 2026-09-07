import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type ChurchInfo, type CropWindow, type Project, type RenderStatus, type Segment, type Style } from '../api'
import FramingPanel from './FramingPanel'
import OutroPanel from './OutroPanel'
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

/** The single-clip editor: upload, transcribe, subtitles, framing, style, preview, render. */
export default function ClipEditor({ projectId, onProjectChange }: Props) {
  const [project, setProject] = useState<Project | null>(null)
  const [segments, setSegments] = useState<Segment[]>([])
  const [style, setStyle] = useState<Style | null>(null)
  const [crop, setCrop] = useState<CropWindow | null>(null)
  const [playing, setPlaying] = useState(false)
  const [church, setChurch] = useState<ChurchInfo | null>(null)
  const [renderStatus, setRenderStatus] = useState<RenderStatus>(IDLE)
  const [uploading, setUploading] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [outputVersion, setOutputVersion] = useState(0)
  const [outroVersion, setOutroVersion] = useState(0)
  const previewRef = useRef<PreviewHandle>(null)
  const dirty = useRef({ transcript: false, style: false, crop: false })

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))

  const adopt = useCallback((p: Project) => {
    setProject(p)
    setStyle(p.style)
    setCrop(p.crop)
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
        dirty.current = { transcript: false, style: false, crop: false }
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

  // Debounced auto-save of subtitles, style and framing.
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

  useEffect(() => {
    if (!project || !crop || !dirty.current.crop) return
    const handle = setTimeout(() => {
      dirty.current.crop = false
      api.saveCrop(project.id, crop).catch(fail)
    }, 400)
    return () => clearTimeout(handle)
  }, [crop, project])

  const changeCrop = (next: CropWindow) => {
    dirty.current.crop = true
    setCrop(next)
  }
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
      if (crop) await api.saveCrop(project.id, crop)
      dirty.current = { transcript: false, style: false, crop: false }
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
      <p className="lede">
        <strong>Losse clip.</strong> Kies een fragment, verbeter de ondertitels, bepaal het beeldkader en maak de video.
        Links zie je steeds hoe het resultaat eruitziet.
      </p>

      {error && <div className="error">{error}</div>}

      <label
        className={`drop ${dragging ? 'active' : ''} ${hasVideo ? 'compact' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input type="file" accept="video/*,.mp4,.mov,.m4v,.mkv,.webm" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        {uploading ? (
          <strong>Bezig met uploaden…</strong>
        ) : hasVideo ? (
          <>
            <strong style={{ flex: 1 }}>{project?.title ?? 'Fragment'}</strong>
            <span className="meta">{project?.origin ? 'Geknipt uit de dienst. ' : ''}Sleep hier een ander fragment om opnieuw te beginnen.</span>
          </>
        ) : (
          <>
            <strong>Sleep hier een videofragment, of klik om een bestand te kiezen</strong>
            <span className="hint">Twintig tot negentig seconden werkt het best. Mp4 en mov zijn prima.</span>
          </>
        )}
      </label>

      {!hasVideo && (
        <div className="card start">
          <div className="ghost">9:16</div>
          <div>
            <h2>Van fragment naar reel</h2>
            <ol className="how">
              <li><b>Ondertitels</b> worden automatisch uitgeschreven; jij verbetert wat er misging.</li>
              <li><b>Beeldkader</b> bepaalt welk deel van het brede beeld in de staande video komt.</li>
              <li><b>Stijl</b> regelt lettertype, grootte en kleur van de ondertitels.</li>
              <li><b>Afsluiter</b> plakt het eindscherm van de kerk achter je clip.</li>
            </ol>
          </div>
        </div>
      )}

      {project && style && crop && hasVideo && (
        <div className="workbench">
          <div className="stage card">
            <VideoPreview
              ref={previewRef}
              sourceUrl={api.sourceUrl(project.id)}
              sourceInfo={project.sourceInfo!}
              outroUrl={api.outroUrl(outroVersion)}
              church={church}
              segments={segments}
              style={style}
              output={project.output}
              crop={crop}
              onCropChange={changeCrop}
              onTime={setCurrentTime}
              onPlayState={setPlaying}
            />
            <RenderControls
              hasAudio={Boolean(project.sourceInfo?.hasAudio)}
              hasSubtitles={segments.length > 0}
              transcribing={transcribing}
              canRender={hasVideo}
              renderStatus={renderStatus}
              outputUrl={renderStatus.status === 'done' ? `${api.outputUrl(project.id)}?v=${outputVersion}` : null}
              onTranscribe={transcribe}
              onRender={render}
            />
          </div>
          <div>
            <SubtitleEditor segments={segments} currentTime={currentTime} onChange={changeSegments} onSeek={(t) => previewRef.current?.seek(t)} />
            <FramingPanel
              sourceUrl={api.sourceUrl(project.id)}
              sourceInfo={project.sourceInfo!}
              output={project.output}
              crop={crop}
              currentTime={currentTime}
              playing={playing}
              onChange={changeCrop}
            />
            <StylePanel style={style} onChange={changeStyle} />
            <OutroPanel church={church} outroUrl={api.outroUrl(outroVersion)} onRebuilt={() => setOutroVersion((v) => v + 1)} />
          </div>
        </div>
      )}
    </div>
  )
}
