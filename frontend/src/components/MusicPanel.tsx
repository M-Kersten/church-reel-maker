import { useEffect, useState } from 'react'
import { api, type MusicFile, type MusicSettings } from '../api'
import Section from './Section'

interface Props {
  music: MusicSettings
  onChange: (music: MusicSettings) => void
}

/** Optional background music under the clip, with the speech staying on top. */
export default function MusicPanel({ music, onChange }: Props) {
  const [files, setFiles] = useState<MusicFile[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = () => api.music().then(setFiles).catch(() => setFiles([]))
  useEffect(() => {
    load()
  }, [])

  const add = async (file: File) => {
    setBusy(true)
    setError(null)
    try {
      const { file: name } = await api.uploadMusic(file)
      await load()
      onChange({ ...music, file: name })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const on = Boolean(music.file)
  return (
    <Section
      step={4}
      title="Muziek"
      intro="Zet er een rustige track onder als je wilt. De stem blijft leidend: zodra er gepraat wordt gaat de muziek automatisch zachter."
    >
      <div className="fields">
        <label htmlFor="track">Track</label>
        <div className="inline">
          <select id="track" value={music.file} onChange={(e) => onChange({ ...music, file: e.target.value })}>
            <option value="">Geen muziek</option>
            {files.map((f) => (
              <option key={f.file} value={f.file}>{f.file} ({String(f.sizeMb).replace('.', ',')} MB)</option>
            ))}
          </select>
          <label className="upload-link">
            {busy ? 'Bezig…' : 'Bestand toevoegen'}
            <input type="file" accept="audio/*,.mp3,.m4a,.wav,.aac,.ogg" disabled={busy} onChange={(e) => e.target.files?.[0] && add(e.target.files[0])} />
          </label>
        </div>

        {on && (
          <>
            <label htmlFor="vol">Volume</label>
            <div className="inline">
              <input id="vol" type="range" min={0.02} max={0.6} step={0.01} value={music.volume} onChange={(e) => onChange({ ...music, volume: Number(e.target.value) })} />
              <output>{Math.round(music.volume * 100)}%</output>
            </div>

            <label htmlFor="duck">Onder de stem</label>
            <div className="inline">
              <input id="duck" type="checkbox" checked={music.duck} onChange={(e) => onChange({ ...music, duck: e.target.checked })} />
              <label htmlFor="duck">Muziek zachter zetten zodra er gesproken wordt</label>
            </div>

            <label htmlFor="fade">Uitfaden</label>
            <div className="inline">
              <input id="fade" type="range" min={0} max={6} step={0.5} value={music.fadeOut} onChange={(e) => onChange({ ...music, fadeOut: Number(e.target.value) })} />
              <output>{String(music.fadeOut).replace('.', ',')} s</output>
            </div>
          </>
        )}
      </div>
      {error && <div className="error" style={{ marginTop: '0.7rem', marginBottom: 0 }}>{error}</div>}
      <p className="hint">
        {on
          ? 'De muziek loopt ook onder de afsluiter door en fadet aan het eind uit. Je hoort het pas terug in de gemaakte video, niet in de voorvertoning.'
          : 'Gebruik alleen muziek waarvan je de rechten hebt. Instagram en YouTube halen video’s met beschermde muziek weg.'}
      </p>
    </Section>
  )
}
