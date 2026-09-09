import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, type CropWindow, type MusicSettings, type Project, type RenderStatus, type Segment, type Style, type Watermark } from '../api'
import { useChurch } from '../church'
import FramingPanel from './FramingPanel'
import LogoPanel from './LogoPanel'
import MusicPanel from './MusicPanel'
import RenderControls from './RenderControls'
import StylePanel from './StylePanel'
import SubtitleEditor from './SubtitleEditor'
import WordSuggestions from './WordSuggestions'
import VideoPreview, { type PreviewHandle } from './VideoPreview'

const IDLE: RenderStatus = { status: 'idle', progress: 0, message: '', error: null }
const STORAGE_KEY = 'church-reel-maker.project'
const CLEAN = { transcript: false, style: false, crop: false, music: false, watermark: false }

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
  const [music, setMusic] = useState<MusicSettings | null>(null)
  const [watermark, setWatermark] = useState<Watermark | null>(null)
  const [playing, setPlaying] = useState(false)
  const church = useChurch()
  const [renderStatus, setRenderStatus] = useState<RenderStatus>(IDLE)
  const [uploading, setUploading] = useState<number | null>(null)
  const [offline, setOffline] = useState(false)
  const [transcribeStatus, setTranscribeStatus] = useState<RenderStatus>(IDLE)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [outputVersion, setOutputVersion] = useState(0)
  const [outroVersion, setOutroVersion] = useState(0)
  // Bumped when subtitles are saved, so the word suggestions look again.
  const [transcriptSavedAt, setTranscriptSavedAt] = useState(0)
  // The clip's own framing: whether it follows the speaker, and whether it is out looking.
  const [searching, setSearching] = useState(false)
  const [searchNote, setSearchNote] = useState('')
  const previewRef = useRef<PreviewHandle>(null)
  const dirty = useRef({ ...CLEAN })

  const fail = (e: unknown) => {
    if (e instanceof ApiError && e.offline) {
      setOffline(true)
      return
    }
    setOffline(false)
    setError(e instanceof Error ? e.message : String(e))
  }

  const adopt = useCallback((p: Project) => {
    setProject(p)
    setStyle(p.style)
    setCrop(p.crop)
    setMusic(p.music)
    setWatermark(p.watermark)
    setSegments(p.transcriptData?.segments ?? [])
    localStorage.setItem(STORAGE_KEY, p.id)
    onProjectChange(p.id)
  }, [onProjectChange])

  // Open the requested project (or the last one after a page reload).
  useEffect(() => {
    const wanted = projectId ?? localStorage.getItem(STORAGE_KEY)
    if (!wanted || wanted === project?.id) return
    api
      .getProject(wanted)
      .then((p) => {
        adopt(p)
        dirty.current = { ...CLEAN }
        return Promise.all([api.renderStatus(p.id), api.transcribeStatus(p.id)])
      })
      .then(([render, transcribe]) => {
        setRenderStatus(render)
        // A transcription that is still running survives a page reload.
        if (transcribe.status === 'running') setTranscribeStatus(transcribe)
      })
      .catch(() => localStorage.removeItem(STORAGE_KEY))
  }, [projectId, project?.id, adopt])

  // The brand lives in its own menu now; when it is saved the end screen is made again.
  useEffect(() => {
    const again = () => setOutroVersion((v) => v + 1)
    window.addEventListener('brand-changed', again)
    return () => window.removeEventListener('brand-changed', again)
  }, [])

  const upload = async (file: File) => {
    setError(null)
    setUploading(0)
    try {
      const p = project?.sourceVideo ? await api.createProject() : project ?? (await api.createProject())
      adopt(await api.upload(p.id, file, setUploading))
      setRenderStatus(IDLE)
      setSegments([])
    } catch (e) {
      fail(e)
    } finally {
      setUploading(null)
    }
  }

  // Debounced auto-save of subtitles, style and framing.
  useEffect(() => {
    if (!project || !dirty.current.transcript) return
    const handle = setTimeout(() => {
      dirty.current.transcript = false
      api.saveTranscript(project.id, { language: 'nl', segments })
        .then(() => setTranscriptSavedAt(Date.now()))
        .catch(fail)
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

  useEffect(() => {
    if (!project || !music || !dirty.current.music) return
    const handle = setTimeout(() => {
      dirty.current.music = false
      api.saveMusic(project.id, music).catch(fail)
    }, 400)
    return () => clearTimeout(handle)
  }, [music, project])

  useEffect(() => {
    if (!project || !watermark || !dirty.current.watermark) return
    const handle = setTimeout(() => {
      dirty.current.watermark = false
      api.saveWatermark(project.id, watermark).catch(fail)
    }, 400)
    return () => clearTimeout(handle)
  }, [watermark, project])

  const changeWatermark = (next: Watermark) => {
    dirty.current.watermark = true
    setWatermark(next)
  }

  const changeMusic = (next: MusicSettings) => {
    dirty.current.music = true
    setMusic(next)
  }

  const changeCrop = (next: CropWindow) => {
    dirty.current.crop = true
    setCrop(next)
  }

  const follow = (wanted: boolean) => {
    if (!project) return
    setError(null)
    api.setFraming(project.id, wanted).then(setProject).catch(fail)
  }

  /** Look through the clip for the speaker; poll until the job is over. */
  const search = async () => {
    if (!project || searching) return
    setError(null)
    setSearchNote('')
    setSearching(true)
    try {
      await api.track(project.id)
      for (;;) {
        await new Promise((wake) => setTimeout(wake, 1000))
        const state = await api.trackStatus(project.id)
        setSearchNote(state.job?.message ?? '')
        if (!state.job || state.job.status !== 'running') {
          setProject(await api.getProject(project.id))
          if (state.job?.status === 'error' && state.job.error) setError(state.job.error)
          break
        }
      }
    } catch (e) {
      fail(e)
    } finally {
      setSearching(false)
    }
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
    try {
      setTranscribeStatus(await api.transcribe(project.id))
    } catch (e) {
      fail(e)
    }
  }

  const stopTranscribe = () => {
    if (!project) return
    api.stopTranscribe(project.id).then(setTranscribeStatus).catch(fail)
  }

  // Follow the transcription and pick up the subtitles once they are written.
  useEffect(() => {
    if (!project || transcribeStatus.status !== 'running') return
    let misses = 0
    const handle = setInterval(async () => {
      try {
        const s = await api.transcribeStatus(project.id)
        misses = 0
        setOffline(false)
        setTranscribeStatus(s)
        if (s.status === 'done') {
          const fresh = await api.getProject(project.id)
          dirty.current.transcript = false
          setSegments(fresh.transcriptData?.segments ?? [])
        }
      } catch (e) {
        misses += 1
        if (misses >= 3) fail(e)
      }
    }, 1000)
    return () => clearInterval(handle)
  }, [project, transcribeStatus.status])

  const render = async () => {
    if (!project || !style) return
    setError(null)
    try {
      // Flush pending edits before rendering.
      await api.saveTranscript(project.id, { language: 'nl', segments })
      await api.saveStyle(project.id, style)
      if (crop) await api.saveCrop(project.id, crop)
      if (music) await api.saveMusic(project.id, music)
      if (watermark) await api.saveWatermark(project.id, watermark)
      dirty.current = { ...CLEAN }
      setRenderStatus(await api.render(project.id))
    } catch (e) {
      fail(e)
    }
  }

  // Poll render progress while a job runs. A hiccup in the connection is not an error yet.
  useEffect(() => {
    if (!project || renderStatus.status !== 'running') return
    let misses = 0
    const handle = setInterval(async () => {
      try {
        const s = await api.renderStatus(project.id)
        misses = 0
        setOffline(false)
        setRenderStatus(s)
        if (s.status === 'done') setOutputVersion((v) => v + 1)
      } catch (e) {
        misses += 1
        if (misses >= 3) fail(e)
      }
    }, 1000)
    return () => clearInterval(handle)
  }, [project, renderStatus.status])

  const stopRender = () => {
    if (!project) return
    api.stopRender(project.id).then(setRenderStatus).catch(fail)
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) void upload(file)
  }

  // A clip either owns a file or points at the recording it was cut from; both count.
  const hasVideo = Boolean(project?.sourceInfo && project.hasFootage)

  return (
    <div>
      <header className="page-head">
        <h1>Losse clip</h1>
        <p>Kies een fragment, verbeter de ondertitels, bepaal het beeldkader en maak de video. Links zie je steeds hoe het resultaat eruitziet.</p>
      </header>

      {offline && <div className="offline">Geen verbinding met de app. Staat het zwarte venster nog open? Zodra het weer draait gaat dit vanzelf verder.</div>}
      {error && <div className="error">{error}</div>}
      {project && !project.hasFootage && (
        <div className="error">
          De opname waar dit fragment uit komt is opgeruimd, dus er valt niets meer te bewerken of te maken.
          Upload de dienst opnieuw als je dit fragment alsnog wilt hebben.
        </div>
      )}

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
        {uploading !== null ? (
          <span className="uploading">
            <strong>Bezig met uploaden…</strong>
            <span className="bar"><span style={{ display: 'block', height: '100%', width: `${Math.round(uploading * 100)}%`, background: 'var(--purple)' }} /></span>
            <span className="meta">{Math.round(uploading * 100)}%</span>
          </span>
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

      {project && style && crop && music && watermark && hasVideo && (
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
              track={project.track}
              following={project.cropStrategy === 'tracked'}
              watermark={watermark}
              sourceStart={project.sourceStart}
              onCropChange={changeCrop}
              onTime={setCurrentTime}
              onPlayState={setPlaying}
            />
            <RenderControls
              hasAudio={Boolean(project.sourceInfo?.hasAudio)}
              hasSubtitles={segments.length > 0}
              transcribeStatus={transcribeStatus}
              canRender={hasVideo}
              renderStatus={renderStatus}
              outputUrl={renderStatus.status === 'done' ? `${api.outputUrl(project.id)}?v=${outputVersion}` : null}
              onTranscribe={transcribe}
              onRender={render}
              onStop={stopRender}
              onStopTranscribe={stopTranscribe}
            />
          </div>
          <div>
            <SubtitleEditor segments={segments} currentTime={currentTime} onChange={changeSegments} onSeek={(t) => previewRef.current?.seek(t)}>
              <WordSuggestions projectId={project.id} savedAt={transcriptSavedAt} />
            </SubtitleEditor>
            <FramingPanel
              sourceUrl={api.sourceUrl(project.id)}
              sourceInfo={project.sourceInfo!}
              output={project.output}
              crop={crop}
              currentTime={currentTime}
              playing={playing}
              sourceStart={project.sourceStart}
              track={project.track}
              following={project.cropStrategy === 'tracked'}
              searching={searching}
              searchNote={searchNote}
              onChange={changeCrop}
              onFollow={follow}
              onSearch={search}
            />
            <StylePanel style={style} onChange={changeStyle} />
            <LogoPanel watermark={watermark} onChange={changeWatermark} />
            <MusicPanel music={music} onChange={changeMusic} />
          </div>
        </div>
      )}
    </div>
  )
}
