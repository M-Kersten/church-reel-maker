import { useEffect, useRef, useState } from 'react'
import { ApiError, serviceApi, type ClipCandidate, type Service } from '../api'
import { formatTime } from '../subtitleLayout'
import ClipSuggestions from './ClipSuggestions'
import Steps from './Steps'

const STORAGE_KEY = 'church-reel-maker.service'
const BUSY = new Set(['fetching', 'transcribing', 'analyzing', 'processing'])
const STEPS = ['Opname binnenhalen', 'Uitschrijven', 'Momenten zoeken', 'Fragmenten kiezen', 'Clips maken']

const STATUS_LABEL: Record<Service['status'], string> = {
  created: 'Wacht op een opname',
  fetching: 'Opname wordt opgehaald',
  uploaded: 'Opname ontvangen',
  transcribing: 'Dienst wordt uitgeschreven',
  transcribed: 'Uitgeschreven',
  analyzing: 'Beste momenten worden gezocht',
  ready: 'Suggesties staan klaar',
  processing: 'Clips worden gemaakt',
  complete: 'Klaar',
  error: 'Er ging iets mis',
}

const STATUS_TEXT: Record<Service['status'], string> = {
  created: 'Plak hierboven de link naar de dienst, of sleep het bestand naar binnen.',
  fetching: 'De opname wordt binnengehaald van het adres dat je gaf. Hoe lang dat duurt hangt af van je verbinding.',
  uploaded: 'De opname is binnen. Klik op Uitschrijven om de gesproken tekst om te zetten in tekst.',
  transcribing:
    'De gesproken tekst wordt omgezet in tekst. Bij een dienst van anderhalf uur duurt dit ongeveer een half uur. Laat dit venster open staan; de balk hieronder laat de voortgang zien.',
  transcribed: 'De tekst is klaar. Klik op Beste momenten zoeken om de computer de dienst te laten doorlezen.',
  analyzing: 'De tekst wordt stuk voor stuk doorgelezen op momenten die als losse video werken. Dit duurt een paar minuten.',
  ready:
    'Hieronder staan de voorgestelde fragmenten, de beste bovenaan. Beluister ze, vink aan wat je wilt gebruiken en pas zo nodig het begin en einde aan. Klik daarna onderaan op Gekozen fragmenten verwerken.',
  processing: 'De gekozen fragmenten worden uit de opname geknipt. Dit duurt een paar seconden per fragment.',
  complete: 'De clips staan klaar bij Gemaakte clips. Open een clip om de ondertitels na te kijken, het beeldkader te kiezen en de video te maken.',
  error: 'Probeer de laatste stap opnieuw. Blijft het misgaan, geef de melding hieronder dan door aan degene die de app beheert.',
}

const STEP_FOR_STATUS: Record<Service['status'], number> = {
  created: 0, fetching: 0, uploaded: 1, transcribing: 1, transcribed: 2, analyzing: 2, ready: 3, processing: 4, complete: 5, error: 0,
}

interface Props {
  onOpenClip: (projectId: string) => void
}

/** Full-service entry point: upload -> transcribe -> analyze -> review candidates -> process. */
/** Says what the search sends to Claude and what it costs, before the user spends anything. */
function CostNote({ analysis }: { analysis: NonNullable<Service['analysis']> }) {
  if (analysis.provider === 'ollama') {
    return (
      <p className="cost">
        Bij <strong>Beste momenten zoeken</strong> gaat de uitgeschreven tekst naar het model op deze computer
        ({analysis.model}). Dat kost niets en er gaat niets naar buiten.
      </p>
    )
  }
  return (
    <p className="cost">
      Bij <strong>Beste momenten zoeken</strong> gaat alleen de uitgeschreven tekst naar Claude, in {analysis.windows} stukken
      {analysis.skipped > 0 && (
        <> · {analysis.skipped} {analysis.skipped === 1 ? 'stuk blijft' : 'stukken blijven'} thuis, want daar wordt gezongen,
        gecollecteerd of afgekondigd</>
      )}. Dat kost tokens: ongeveer <strong>{analysis.tokens.toLocaleString('nl-NL')} tokens</strong>, dus rond de{' '}
      <strong>${analysis.costUsd.toFixed(2).replace('.', ',')}</strong> met {analysis.model}. De video en het geluid blijven
      op deze computer.
    </p>
  )
}

export default function ServiceView({ onOpenClip }: Props) {
  const [service, setService] = useState<Service | null>(null)
  const [uploading, setUploading] = useState<number | null>(null)
  // Most churches already publish the service somewhere, so the link is the shorter way in.
  const [how, setHow] = useState<'link' | 'file'>('link')
  const [link, setLink] = useState('')
  const [offline, setOffline] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const autoChain = useRef(false)
  const dirty = useRef(false)

  const fail = (e: unknown) => {
    if (e instanceof ApiError && e.offline) {
      setOffline(true)
      return
    }
    setOffline(false)
    setError(e instanceof Error ? e.message : String(e))
  }

  const adopt = (s: Service) => {
    setService(s)
    localStorage.setItem(STORAGE_KEY, s.id)
  }

  // Restore the last service after a reload.
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (!saved) return
    serviceApi.get(saved).then(setService).catch(() => localStorage.removeItem(STORAGE_KEY))
  }, [])

  // Poll while a job runs; chain transcribe -> analyze automatically after an upload.
  useEffect(() => {
    if (!service) return
    if (BUSY.has(service.status)) {
      // A few missed polls are a hiccup, not a failure: the work carries on in the app itself.
      let misses = 0
      const handle = setInterval(() => {
        serviceApi
          .status(service.id)
          .then((s) => {
            misses = 0
            setOffline(false)
            // While a job runs the small payload is enough; when it is over, load everything once.
            if (BUSY.has(s.status)) {
              setService((prev) => (prev ? { ...prev, status: s.status, error: s.error, warning: s.warning, job: s.job } : prev))
            } else {
              serviceApi.get(service.id).then(setService).catch(fail)
            }
          })
          .catch((e) => {
            misses += 1
            if (misses >= 3) fail(e)
          })
      }, 2000)
      return () => clearInterval(handle)
    }
    if (autoChain.current && service.status === 'uploaded') {
      serviceApi.transcribe(service.id).then(setService).catch(fail)
    } else if (autoChain.current && service.status === 'transcribed') {
      autoChain.current = false
      serviceApi.analyze(service.id).then(setService).catch(fail)
    }
  }, [service])

  const upload = async (file: File) => {
    setError(null)
    setUploading(0)
    try {
      const s = service && !service.sourceVideo ? service : await serviceApi.create()
      autoChain.current = true
      adopt(await serviceApi.upload(s.id, file, setUploading))
    } catch (e) {
      fail(e)
      autoChain.current = false
    } finally {
      setUploading(null)
    }
  }

  const fetchLink = async () => {
    if (!link.trim()) return
    setError(null)
    try {
      const s = service && !service.sourceVideo ? service : await serviceApi.create()
      autoChain.current = true
      adopt(await serviceApi.link(s.id, link.trim()))
      setLink('')
    } catch (e) {
      fail(e)
      autoChain.current = false
    }
  }

  const run = (action: (id: string) => Promise<Service>) => {
    if (!service) return
    setError(null)
    action(service.id).then(setService).catch(fail)
  }

  // Candidate edits (selection, boundaries) are saved with a short debounce.
  const changeCandidates = (candidates: ClipCandidate[]) => {
    if (!service) return
    dirty.current = true
    setService({ ...service, candidates })
  }
  useEffect(() => {
    if (!service || !dirty.current) return
    const handle = setTimeout(() => {
      dirty.current = false
      setSaving(true)
      serviceApi.saveCandidates(service.id, service.candidates).catch(fail).finally(() => setSaving(false))
    }, 500)
    return () => clearTimeout(handle)
  }, [service])

  const processSelected = async () => {
    if (!service) return
    setError(null)
    try {
      await serviceApi.saveCandidates(service.id, service.candidates)
      dirty.current = false
      setService(await serviceApi.processSelected(service.id))
    } catch (e) {
      fail(e)
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) void upload(file)
  }

  const busy = service ? BUSY.has(service.status) : false
  const hasVideo = Boolean(service?.sourceVideo && service.sourceInfo)
  const selectedCount = service?.candidates.filter((c) => c.selected).length ?? 0
  const progress = service?.job ? Math.round(service.job.progress * 100) : null
  const stopping = Boolean(service?.job?.message?.startsWith('Bezig met stoppen'))
  // While a recording is being fetched there is nothing to choose; the card below says what
  // is happening. Once one is in, the drop zone stays as the way to start over.
  const showSource = hasVideo || !busy

  return (
    <div>
      <header className="page-head">
        <h1>Hele dienst</h1>
        <p>Geef de link naar de dienst, of upload het bestand. De computer schrijft de dienst uit en zoekt de momenten die als korte video werken. Jij luistert ze na en kiest.</p>
      </header>

      <Steps steps={STEPS} current={service && hasVideo ? STEP_FOR_STATUS[service.status] : 0} />

      {offline && <div className="offline">Geen verbinding met de app. Staat het zwarte venster nog open? Het werk gaat daar gewoon door; zodra de verbinding terug is, zie je de voortgang weer.</div>}
      {error && <div className="error">{error}</div>}

      {showSource && !hasVideo && uploading === null && (
        <div className="seg source-pick">
          <button className={how === 'link' ? 'on' : ''} onClick={() => setHow('link')}>Link naar de dienst</button>
          <button className={how === 'file' ? 'on' : ''} onClick={() => setHow('file')}>Bestand van deze computer</button>
        </div>
      )}

      {!showSource ? null : how === 'link' && !hasVideo && uploading === null ? (
        <div className="paste">
          <label htmlFor="link"><strong>Plak het adres van de dienst</strong></label>
          <div className="row">
            <input
              id="link"
              type="url"
              value={link}
              disabled={busy}
              placeholder="https://www.youtube.com/watch?v=…"
              onChange={(e) => setLink(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && fetchLink()}
            />
            <button className="primary" disabled={busy || !link.trim()} onClick={fetchLink}>Ophalen</button>
          </div>
          <p className="hint">
            YouTube, Vimeo, Facebook of een directe link naar een mp4 werken. Geeft de site de
            video alleen aan zijn eigen speler, zoals Kerkdienstgemist en Kerkomroep doen, download
            hem daar dan en gebruik het tabblad hiernaast.
          </p>
        </div>
      ) : (
        <label
          className={`drop ${dragging ? 'active' : ''} ${hasVideo ? 'compact' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <input type="file" accept="video/*,.mp4,.mov,.m4v,.mkv,.webm" disabled={uploading !== null || busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          {uploading !== null ? (
            <span className="uploading">
              <strong>Bezig met uploaden…</strong>
              <span className="bar"><span style={{ display: 'block', height: '100%', background: 'var(--purple)', width: `${Math.round(uploading * 100)}%` }} /></span>
              <span className="meta">{Math.round(uploading * 100)}%</span>
            </span>
          ) : hasVideo ? (
            <span className="meta">Sleep hier een andere opname om met een nieuwe dienst te beginnen.</span>
          ) : (
            <>
              <strong>Sleep hier de opname van de hele dienst, of klik om een bestand te kiezen</strong>
              <span className="hint">Daarna loopt het vanzelf door: uitschrijven, en dan zoeken naar bruikbare momenten.</span>
            </>
          )}
        </label>
      )}

      {service && (hasVideo || service.status === 'fetching' || service.status === 'error') && (
        <>
          <section className="card">
            <header className="service-head">
              <div>
                <h2>{hasVideo ? service.title : service.status === 'error' ? 'Deze link werkte niet' : STATUS_LABEL[service.status]}</h2>
                {hasVideo && (
                  <span className="meta">{formatTime(service.sourceInfo!.duration)} · {service.sourceInfo!.width}×{service.sourceInfo!.height}</span>
                )}
              </div>
              {/* Without a recording the heading already says the state; twice is once too many. */}
              {hasVideo && (
                <div className={`state ${service.status === 'ready' || service.status === 'complete' ? 'ok' : ''} ${service.status === 'error' ? 'bad' : ''}`}>
                  {busy && <span className="spinner" />}
                  {STATUS_LABEL[service.status]}
                  {saving ? ' · opslaan' : ''}
                </div>
              )}
            </header>
            {/* Without a recording the failure is the link's, and its own message says more
                than the general "try the last step again" would. */}
            {(hasVideo || service.status !== 'error') && <p className="say">{STATUS_TEXT[service.status]}</p>}
            {service.status === 'error' && <div className="error" style={{ marginTop: '0.8rem', marginBottom: 0 }}>{service.error}</div>}
            {service.warning && <div className="warning">{service.warning}</div>}
            {busy && stopping && <p className="hint">Stoppen kan een halve minuut duren; de app maakt het huidige stukje eerst af.</p>}
            {busy && (
              <div className={`progress ${progress ? 'busy' : 'waiting'}`}>
                <div className="bar"><div style={{ width: `${progress ?? 0}%` }} /></div>
                <div className="label">
                  <span>{service.job?.message ?? STATUS_LABEL[service.status]}</span>
                  <span>
                    {progress ? `${progress}%` : ''}
                    <button
                      className="bare small"
                      style={{ marginLeft: '0.6rem' }}
                      disabled={stopping}
                      onClick={() => run(serviceApi.stop)}
                    >
                      {stopping ? 'Stoppen…' : 'Stoppen'}
                    </button>
                  </span>
                </div>
              </div>
            )}
            {!busy && hasVideo && !service.transcript && (
              <div className="fields about">
                <label htmlFor="sermonTitle">Waar gaat het over?</label>
                <input
                  id="sermonTitle"
                  defaultValue={service.sermonTitle}
                  placeholder="Rust in een druk leven"
                  onBlur={(e) => serviceApi.setAbout(service.id, e.target.value, service.series).then(setService).catch(fail)}
                />
                <label htmlFor="sermonSeries">Serie</label>
                <input
                  id="sermonSeries"
                  defaultValue={service.series}
                  placeholder="Onderweg"
                  onBlur={(e) => serviceApi.setAbout(service.id, service.sermonTitle, e.target.value).then(setService).catch(fail)}
                />
                <p className="hint span">
                  Niet verplicht. Als je het invult weet de computer waar hij op moet letten bij het uitschrijven
                  en bij het kiezen van momenten.
                </p>
              </div>
            )}
            {!busy && hasVideo && (
              <label className="choice">
                <input
                  type="checkbox"
                  checked={service.accurate}
                  onChange={(e) => serviceApi.setAccuracy(service.id, e.target.checked).then(setService).catch(fail)}
                />
                <span>
                  <strong>Nauwkeuriger uitschrijven</strong>
                  <span className="meta"> · hoort namen en moeilijke woorden beter, maar duurt ongeveer drie keer zo lang</span>
                </span>
              </label>
            )}
            {!busy && hasVideo && (
              <div className="acts" style={{ marginTop: '1rem' }}>
                {!service.transcript && <button className="primary" onClick={() => run(serviceApi.transcribe)}>Uitschrijven</button>}
                {service.transcript && service.candidates.length === 0 && (
                  <button className="primary" onClick={() => run(serviceApi.analyze)}>Beste momenten zoeken</button>
                )}
                {service.transcript && service.candidates.length > 0 && (
                  <button onClick={() => run(serviceApi.analyze)}>Opnieuw zoeken</button>
                )}
                {service.transcript && <button onClick={() => run(serviceApi.transcribe)}>Opnieuw uitschrijven</button>}
              </div>
            )}
            {!busy && service.transcript && service.analysis && <CostNote analysis={service.analysis} />}
          </section>

          {service.candidates.length > 0 && (
            <ClipSuggestions
              service={service}
              sourceUrl={serviceApi.sourceUrl(service.id)}
              disabled={busy}
              onChange={changeCandidates}
            />
          )}

          {(service.candidates.length > 0 || service.clips.length > 0) && (
            <div className="dock">
              {service.clips.length > 0 && (
                <div className="ready">
                  <span className="meta">Klaar om te bewerken</span>
                  <div className="chips">
                    {service.clips.map((clip) => (
                      <button
                        key={clip.projectId}
                        className="chip"
                        title={`${clip.title} · ${formatTime(clip.start)} – ${formatTime(clip.end)}`}
                        onClick={() => onOpenClip(clip.projectId)}
                      >
                        {clip.title} →
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {service.candidates.length > 0 && (
                <div className="row">
                  <span>{selectedCount === 0 ? 'Nog geen fragment gekozen' : selectedCount === 1 ? '1 fragment gekozen' : `${selectedCount} fragmenten gekozen`}</span>
                  <button className="primary" disabled={busy || selectedCount === 0} onClick={processSelected}>
                    {service.status === 'processing' ? 'Bezig…' : 'Gekozen fragmenten verwerken'}
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
