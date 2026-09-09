import { useState } from 'react'
import { useChurch } from './church'
import BrandPanel from './components/BrandPanel'
import ClipEditor from './components/ClipEditor'
import ServiceView from './components/ServiceView'
import StoragePanel from './components/StoragePanel'
import SystemCheck from './components/SystemCheck'

type Mode = 'clip' | 'service'
const MODE_KEY = 'church-reel-maker.mode'

/** A wide recording split into parts: the whole service. */
const ServiceIcon = () => (
  <svg width="17" height="17" viewBox="0 0 17 17" fill="none" aria-hidden="true">
    <rect x="1.4" y="4.2" width="14.2" height="8.6" rx="1.6" stroke="currentColor" strokeWidth="1.4" />
    <path d="M6.1 4.2v8.6M10.9 4.2v8.6" stroke="currentColor" strokeWidth="1.4" />
  </svg>
)

/** One upright 9:16 fragment: a single clip. */
const ClipIcon = () => (
  <svg width="17" height="17" viewBox="0 0 17 17" fill="none" aria-hidden="true">
    <rect x="4.6" y="1.4" width="7.8" height="14.2" rx="1.6" stroke="currentColor" strokeWidth="1.4" />
    <path d="m7.5 6.2 3.2 2.3-3.2 2.3z" fill="currentColor" />
  </svg>
)

/** Sliders: what you set once for the church and then leave alone. */
const BrandIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M2 4.6h12M2 11.4h12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    <circle cx="5.8" cy="4.6" r="1.9" fill="currentColor" />
    <circle cx="10.4" cy="11.4" r="1.9" fill="currentColor" />
  </svg>
)

/** A bin: making room on the disk. */
const TidyIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M2.6 4.3h10.8M6.2 4.3V3c0-.4.3-.8.7-.8h2.2c.4 0 .7.4.7.8v1.3"
          stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    <path d="M4 4.3h8l-.6 8.4c0 .6-.5 1.1-1.1 1.1H5.7c-.6 0-1.1-.5-1.1-1.1z"
          stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
  </svg>
)

export default function App() {
  const [mode, setMode] = useState<Mode>(() => (localStorage.getItem(MODE_KEY) === 'clip' ? 'clip' : 'service'))
  const [projectId, setProjectId] = useState<string | null>(null)
  const [tidying, setTidying] = useState(false)
  const [branding, setBranding] = useState(false)
  const church = useChurch()

  const switchMode = (next: Mode) => {
    setMode(next)
    localStorage.setItem(MODE_KEY, next)
  }

  const openClip = (id: string) => {
    setProjectId(id)
    switchMode('clip')
  }

  return (
    <>
      <header className="appbar">
        <div className="brand">
          <svg width="24" height="28" viewBox="0 0 24 28" aria-hidden="true">
            <path d="M12 1C6.2 1 1.5 5.7 1.5 11.5V27h21V11.5C22.5 5.7 17.8 1 12 1Z" fill="#FFFFFF" />
            <path d="M9.6 10.4 17 14.7l-7.4 4.3z" fill="#2A1140" />
            <circle cx="12" cy="5.6" r="1.6" fill="#C9971C" />
          </svg>
          <div>
            <div className="name">Church Reel Maker</div>
            <div className="church">{church?.churchName ?? 'Kerk'}</div>
          </div>
        </div>

        {/* Where you are. One switch between two workspaces, so it cannot read as a menu. */}
        <nav className="pages" aria-label="Waar wil je aan werken">
          <button
            className={mode === 'service' ? 'on' : ''}
            aria-current={mode === 'service' ? 'page' : undefined}
            onClick={() => switchMode('service')}
          >
            <ServiceIcon /> Hele dienst
          </button>
          <button
            className={mode === 'clip' ? 'on' : ''}
            aria-current={mode === 'clip' ? 'page' : undefined}
            onClick={() => switchMode('clip')}
          >
            <ClipIcon /> Losse clip
          </button>
        </nav>

        <SystemCheck />

        {/* Things that open on top of your work and close again. Outlined, never filled, so
            they cannot be mistaken for the page you are on. */}
        <div className="tools">
          <button
            aria-haspopup="dialog"
            title="De gegevens van de kerk, de woorden die hier vallen en het eindscherm achter elke video"
            onClick={() => setBranding(true)}
          >
            <BrandIcon /> <span>Merk instellen</span>
          </button>
          <button
            aria-haspopup="dialog"
            title="Kijken wat de opnames op de schijf innemen, en oude weggooien"
            onClick={() => setTidying(true)}
          >
            <TidyIcon /> <span>Ruimte vrijmaken</span>
          </button>
        </div>
      </header>
      <main className="page">
        {mode === 'service' ? <ServiceView onOpenClip={openClip} /> : <ClipEditor projectId={projectId} onProjectChange={setProjectId} />}
      </main>
      {branding && <BrandPanel onClose={() => setBranding(false)} />}
      {tidying && <StoragePanel onClose={() => setTidying(false)} />}
    </>
  )
}
