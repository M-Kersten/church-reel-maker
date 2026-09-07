import { useEffect, useState } from 'react'
import { api, type ChurchInfo } from './api'
import ClipEditor from './components/ClipEditor'
import ServiceView from './components/ServiceView'

type Mode = 'clip' | 'service'
const MODE_KEY = 'church-reel-maker.mode'

/**
 * Two entry points on one page:
 *  - Hele dienst: upload a complete recording, let the AI suggest clips, pick some.
 *  - Losse clip: the single-clip editor (subtitles, framing, style, preview, render).
 * Processing a suggestion creates a clip project and opens it in the editor.
 */
export default function App() {
  const [mode, setMode] = useState<Mode>(() => (localStorage.getItem(MODE_KEY) === 'clip' ? 'clip' : 'service'))
  const [projectId, setProjectId] = useState<string | null>(null)
  const [church, setChurch] = useState<ChurchInfo | null>(null)

  useEffect(() => {
    api.church().then(setChurch).catch(() => setChurch(null))
  }, [])

  const switchMode = (next: Mode) => {
    setMode(next)
    localStorage.setItem(MODE_KEY, next)
  }

  const openClip = (id: string) => {
    setProjectId(id)
    switchMode('clip')
  }

  return (
    <div className="app">
      <header className="hero">
        <span className="arch a1" />
        <span className="arch a2" />
        <span className="arch a3" />
        <span className="arch a4" />
        <span className="eyebrow">{church?.churchName ?? 'Kerk'}</span>
        <h1 className="wordmark">Church Reel Maker</h1>
        <p className="tagline">Maak van een preekmoment een staande video voor Instagram Reels en YouTube Shorts, met ondertitels en de afsluiter van de kerk.</p>
        <nav className="tabs" aria-label="Kies wat je wilt doen">
          <button className={mode === 'service' ? 'active' : ''} onClick={() => switchMode('service')}>Hele dienst</button>
          <button className={mode === 'clip' ? 'active' : ''} onClick={() => switchMode('clip')}>Losse clip</button>
        </nav>
        <p className="mode-help">
          {mode === 'service'
            ? 'Upload de opname van een hele dienst. De computer schrijft alles uit en stelt de mooiste momenten voor. Jij kiest welke clips worden.'
            : 'Heb je al een kort fragment? Upload het hier, kijk de ondertitels na, kies het beeldkader en maak de video.'}
        </p>
      </header>
      {mode === 'service' ? (
        <ServiceView onOpenClip={openClip} />
      ) : (
        <ClipEditor projectId={projectId} onProjectChange={setProjectId} />
      )}
    </div>
  )
}
