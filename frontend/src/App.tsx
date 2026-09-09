import { useState } from 'react'
import { useChurch } from './church'
import BrandPanel from './components/BrandPanel'
import ClipEditor from './components/ClipEditor'
import ServiceView from './components/ServiceView'
import StoragePanel from './components/StoragePanel'
import SystemCheck from './components/SystemCheck'

type Mode = 'clip' | 'service'
const MODE_KEY = 'church-reel-maker.mode'

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
        <SystemCheck />
        <nav aria-label="Wat wil je doen">
          <button className={mode === 'service' ? 'active' : ''} onClick={() => switchMode('service')}>Hele dienst</button>
          <button className={mode === 'clip' ? 'active' : ''} onClick={() => switchMode('clip')}>Losse clip</button>
          <button className="bare tidy-open" onClick={() => setBranding(true)}>Merk</button>
          <button className="bare tidy-open" onClick={() => setTidying(true)}>Opruimen</button>
        </nav>
      </header>
      <main className="page">
        {mode === 'service' ? <ServiceView onOpenClip={openClip} /> : <ClipEditor projectId={projectId} onProjectChange={setProjectId} />}
      </main>
      {branding && <BrandPanel onClose={() => setBranding(false)} />}
      {tidying && <StoragePanel onClose={() => setTidying(false)} />}
    </>
  )
}
