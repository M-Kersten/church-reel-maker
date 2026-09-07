import { useState } from 'react'
import ClipEditor from './components/ClipEditor'
import ServiceView from './components/ServiceView'

type Mode = 'clip' | 'service'
const MODE_KEY = 'church-reel-maker.mode'

/**
 * Two entry points on one page:
 *  - Full service: upload a complete recording, let the AI suggest clips, pick some.
 *  - Clip: the existing single-clip editor (subtitles, style, preview, render).
 * Processing a suggestion creates a clip project and opens it in the editor.
 */
export default function App() {
  const [mode, setMode] = useState<Mode>(() => (localStorage.getItem(MODE_KEY) === 'service' ? 'service' : 'clip'))
  const [projectId, setProjectId] = useState<string | null>(null)

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
      <header>
        <h1>Church Reel Maker</h1>
        <nav className="tabs">
          <button className={mode === 'service' ? 'active' : ''} onClick={() => switchMode('service')}>Full service</button>
          <button className={mode === 'clip' ? 'active' : ''} onClick={() => switchMode('clip')}>Clip</button>
        </nav>
      </header>
      {mode === 'service' ? (
        <ServiceView onOpenClip={openClip} />
      ) : (
        <ClipEditor projectId={projectId} onProjectChange={setProjectId} />
      )}
    </div>
  )
}
