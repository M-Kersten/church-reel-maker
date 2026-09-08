import { useEffect, useState } from 'react'
import { api, type Corner, type LogoFile, type Watermark } from '../api'
import Section from './Section'

interface Props {
  watermark: Watermark
  onChange: (watermark: Watermark) => void
}

const CORNERS: { key: Corner; label: string }[] = [
  { key: 'topLeft', label: 'linksboven' },
  { key: 'topRight', label: 'rechtsboven' },
  { key: 'bottomLeft', label: 'linksonder' },
  { key: 'bottomRight', label: 'rechtsonder' },
]

/** The church logo in a corner of the clip. Files are shared with the end screen. */
export default function LogoPanel({ watermark, onChange }: Props) {
  const [files, setFiles] = useState<LogoFile[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = () => api.logos().then(setFiles).catch(() => setFiles([]))
  useEffect(() => {
    load()
  }, [])

  const add = async (file: File) => {
    setBusy(true)
    setError(null)
    try {
      const { file: name } = await api.uploadLogo(file)
      await load()
      onChange({ ...watermark, file: name })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const set = <K extends keyof Watermark>(key: K, value: Watermark[K]) => onChange({ ...watermark, [key]: value })
  const on = Boolean(watermark.file)
  return (
    <Section step={4} title="Logo in beeld" intro="Een klein logo in de hoek maakt de video herkenbaar, ook als iemand hem doorstuurt.">
      <div className="logos">
        <button type="button" className={`plain ${on ? '' : 'on'}`} onClick={() => set('file', '')}>geen</button>
        {files.map((f) => (
          <button
            type="button"
            key={f.file}
            title={f.file}
            className={watermark.file === f.file ? 'on' : ''}
            onClick={() => set('file', f.file)}
          >
            <img src={api.logoUrl(f.file)} alt={f.file} />
          </button>
        ))}
        <label className="upload-link">
          {busy ? 'Bezig…' : 'Logo toevoegen'}
          <input type="file" accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" disabled={busy} onChange={(e) => e.target.files?.[0] && add(e.target.files[0])} />
        </label>
      </div>

      {on && (
        <div className="fields">
          <label>Hoek</label>
          <div className="seg small-seg">
            {CORNERS.map((c) => (
              <button type="button" key={c.key} className={watermark.corner === c.key ? 'on' : ''} onClick={() => set('corner', c.key)}>
                {c.label}
              </button>
            ))}
          </div>

          <label htmlFor="lw">Breedte</label>
          <div className="inline">
            <input id="lw" type="range" min={0.06} max={0.4} step={0.01} value={watermark.width} onChange={(e) => set('width', Number(e.target.value))} />
            <output>{Math.round(watermark.width * 100)}%</output>
          </div>

          <label htmlFor="lo">Dekking</label>
          <div className="inline">
            <input id="lo" type="range" min={0.1} max={1} step={0.05} value={watermark.opacity} onChange={(e) => set('opacity', Number(e.target.value))} />
            <output>{Math.round(watermark.opacity * 100)}%</output>
          </div>

          <label htmlFor="lm">Marge</label>
          <div className="inline">
            <input id="lm" type="range" min={0} max={200} step={10} value={watermark.margin} onChange={(e) => set('margin', Number(e.target.value))} />
            <output>{watermark.margin}</output>
          </div>
        </div>
      )}
      {error && <div className="error" style={{ marginTop: '0.7rem', marginBottom: 0 }}>{error}</div>}
      <p className="hint">
        {on
          ? 'Je ziet het logo meteen terug in de voorvertoning. Een png met transparante achtergrond werkt het mooist.'
          : 'Nog geen logo geüpload? Kies een png met transparante achtergrond. Hetzelfde bestand kun je ook op het eindscherm zetten.'}
      </p>
    </Section>
  )
}
