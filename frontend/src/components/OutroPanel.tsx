import { useEffect, useRef, useState } from 'react'
import { api, type ChurchInfo, type FontWeight, type OutroConfig, type OutroLine } from '../api'
import { WEIGHT_LABELS, resolveWeight, useFonts, weightsOf } from '../fonts'
import { cssWeight } from '../subtitleLayout'
import Section from './Section'

const BACKGROUNDS: { value: OutroConfig['background']['type']; label: string }[] = [
  { value: 'gradient', label: 'Kleurverloop' },
  { value: 'solid', label: 'Effen kleur' },
  { value: 'image', label: 'Afbeelding' },
]

interface Props {
  church: ChurchInfo | null
  outroUrl: string
  /** Called after saving, so the preview elsewhere reloads the new end screen. */
  onRebuilt: () => void
}

/** Edit the end screen: background, font, and the lines of text. */
export default function OutroPanel({ church, outroUrl, onRebuilt }: Props) {
  const families = useFonts()
  const [config, setConfig] = useState<OutroConfig | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.outroConfig().then(setConfig).catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const edit = (patch: Partial<OutroConfig>) => {
    if (!config) return
    setConfig({ ...config, ...patch })
    setDirty(true)
    setSaved(false)
  }
  const editLine = (index: number, patch: Partial<OutroLine>) =>
    edit({ lines: config!.lines.map((l, i) => (i === index ? { ...l, ...patch } : l)) })

  const save = async () => {
    if (!config) return
    setBusy(true)
    setError(null)
    try {
      setConfig(await api.saveOutro(config))
      setDirty(false)
      setSaved(true)
      onRebuilt()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const uploadBackground = async (file: File) => {
    if (!config) return
    setBusy(true)
    setError(null)
    try {
      const { image } = await api.uploadOutroBackground(file)
      edit({ background: { ...config.background, type: 'image', image } })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (!config) {
    return (
      <Section step={4} title="Afsluiter" intro="Het eindscherm dat achter elke video komt.">
        {error ? <div className="error">{error}</div> : <p className="empty">Bezig met laden…</p>}
      </Section>
    )
  }

  const background = config.background
  const setBackground = (patch: Partial<OutroConfig['background']>) => edit({ background: { ...background, ...patch } })

  return (
    <Section
      step={4}
      title="Afsluiter"
      intro="Elke video eindigt met dit scherm. Wijzig kleuren, lettertype en teksten; links zie je het meteen. Met {churchName}, {serviceTimes} en {instagram} vul je automatisch de gegevens van de kerk in."
    >
      <div className="outro-edit">
        <div>
          <EndScreen config={config} church={church} />
          <div className="made">
            <p className="meta" style={{ margin: '0.5rem 0 0.25rem' }}>Zoals hij nu in de video staat:</p>
            <video src={outroUrl} muted playsInline controls preload="auto" onLoadedMetadata={(e) => (e.currentTarget.currentTime = e.currentTarget.duration / 2)} />
          </div>
        </div>

        <div>
          <div className="fields">
            <label>Achtergrond</label>
            <div className="seg">
              {BACKGROUNDS.map((b) => (
                <button key={b.value} className={background.type === b.value ? 'on' : ''} onClick={() => setBackground({ type: b.value })}>
                  {b.label}
                </button>
              ))}
            </div>

            {background.type === 'solid' && (
              <>
                <label htmlFor="bgcolor">Kleur</label>
                <input id="bgcolor" type="color" value={background.color} onChange={(e) => setBackground({ color: e.target.value.toUpperCase() })} />
              </>
            )}

            {background.type === 'gradient' && (
              <>
                <label>Kleuren</label>
                <div className="swatches">
                  {background.colors.map((c, i) => (
                    <input
                      key={i}
                      type="color"
                      aria-label={`Kleur ${i + 1}`}
                      value={c}
                      onChange={(e) => setBackground({ colors: background.colors.map((old, n) => (n === i ? e.target.value.toUpperCase() : old)) })}
                    />
                  ))}
                  {background.colors.length < 4 && (
                    <button className="small" onClick={() => setBackground({ colors: [...background.colors, '#4B1E78'] })}>+</button>
                  )}
                  {background.colors.length > 2 && (
                    <button className="small" onClick={() => setBackground({ colors: background.colors.slice(0, -1) })}>−</button>
                  )}
                </div>
                <label htmlFor="angle">Richting</label>
                <div className="inline">
                  <input id="angle" type="range" min={0} max={360} step={5} value={background.angle} onChange={(e) => setBackground({ angle: Number(e.target.value) })} />
                  <output>{background.angle}°</output>
                </div>
              </>
            )}

            {background.type === 'image' && (
              <>
                <label>Afbeelding</label>
                <div className="inline">
                  <input type="file" accept="image/*" onChange={(e) => e.target.files?.[0] && uploadBackground(e.target.files[0])} />
                </div>
                <label htmlFor="darken">Verdonkeren</label>
                <div className="inline">
                  <input id="darken" type="range" min={0} max={0.8} step={0.05} value={background.darken} onChange={(e) => setBackground({ darken: Number(e.target.value) })} />
                  <output>{Math.round(background.darken * 100)}%</output>
                </div>
              </>
            )}

            <label htmlFor="ofont">Lettertype</label>
            <select
              id="ofont"
              value={config.font}
              onChange={(e) => {
                const font = e.target.value
                edit({ font, lines: config.lines.map((l) => ({ ...l, weight: l.font ? l.weight : resolveWeight(families, font, l.weight) })) })
              }}
            >
              {families.map((f) => (
                <option key={f.name} value={f.name}>{f.name}</option>
              ))}
            </select>

            <label htmlFor="dur">Duur</label>
            <div className="inline">
              <input id="dur" type="range" min={2} max={12} step={0.5} value={config.duration} onChange={(e) => edit({ duration: Number(e.target.value) })} />
              <output>{String(config.duration).replace('.', ',')} s</output>
            </div>
          </div>

          <h3 style={{ marginTop: '1.1rem' }}>Teksten</h3>
          <div className="lines-edit">
            {config.lines.map((line, i) => {
              const weights = weightsOf(families, line.font || config.font)
              return (
                <div key={i} className="line-edit">
                  <div className="top">
                    <input value={line.text} onChange={(e) => editLine(i, { text: e.target.value })} placeholder="Tekst van deze regel" />
                    <button className="bare small" onClick={() => edit({ lines: config.lines.filter((_, n) => n !== i) })} title="Regel verwijderen">✕</button>
                  </div>
                  <div className="bits">
                    <label>Grootte <input type="number" min={16} max={160} step={2} value={line.size} onChange={(e) => editLine(i, { size: Number(e.target.value) })} /></label>
                    <label>Kleur <input type="color" value={line.color} onChange={(e) => editLine(i, { color: e.target.value.toUpperCase() })} /></label>
                    <label>
                      Dikte
                      <select value={line.weight} disabled={weights.length < 2} onChange={(e) => editLine(i, { weight: e.target.value as FontWeight })}>
                        {weights.map((w) => (
                          <option key={w} value={w}>{WEIGHT_LABELS[w]}</option>
                        ))}
                      </select>
                    </label>
                    <label>Hoogte <input type="range" min={80} max={1840} step={10} value={line.y} onChange={(e) => editLine(i, { y: Number(e.target.value) })} /></label>
                    <label>Letterafstand <input type="number" min={0} max={30} step={1} value={line.spacing} onChange={(e) => editLine(i, { spacing: Number(e.target.value) })} /></label>
                    <label><input type="checkbox" checked={line.uppercase} onChange={(e) => editLine(i, { uppercase: e.target.checked })} /> Hoofdletters</label>
                  </div>
                </div>
              )
            })}
          </div>
          <p style={{ marginTop: '0.6rem' }}>
            <button
              className="small"
              onClick={() => {
                const last = config.lines[config.lines.length - 1]
                edit({ lines: [...config.lines, { text: 'Nieuwe regel', y: Math.min(1840, (last?.y ?? 900) + 140), size: 48, weight: resolveWeight(families, config.font, 'bold'), color: '#FFFFFF', font: '', spacing: 0, uppercase: false, delay: 0 }] })
              }}
            >
              Regel toevoegen
            </button>
          </p>

          <div className="save-row">
            <button className="primary" onClick={save} disabled={busy || !dirty}>
              {busy ? 'Bezig…' : 'Opslaan en vernieuwen'}
            </button>
            {saved && !dirty && <span className="meta">Opgeslagen en opnieuw gemaakt.</span>}
            {dirty && <span className="meta">Nog niet opgeslagen.</span>}
          </div>
          {error && <div className="error" style={{ marginTop: '0.7rem', marginBottom: 0 }}>{error}</div>}
          <p className="hint">Liever je eigen filmpje? Zet het als outro.mp4 in de map templates en zet generate op false in templates/outro.json.</p>
        </div>
      </div>
    </Section>
  )
}

/** Live approximation of the end screen, drawn with the same fonts as the render. */
function EndScreen({ config, church }: { config: OutroConfig; church: ChurchInfo | null }) {
  const box = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(190 / 1080)

  useEffect(() => {
    const el = box.current
    if (!el) return
    const observer = new ResizeObserver(() => setScale(el.clientWidth / 1080))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const bg = config.background
  const style: React.CSSProperties =
    bg.type === 'gradient'
      ? { backgroundImage: `linear-gradient(${bg.angle + 90}deg, ${bg.colors.join(', ')})` }
      : bg.type === 'image'
        ? { backgroundImage: `url(/templates/${bg.image})`, backgroundSize: 'cover', backgroundPosition: 'center' }
        : { background: bg.color }

  const fill = (text: string) =>
    text
      .replace('{churchName}', church?.churchName ?? 'Kerk')
      .replace('{serviceTimes}', (church?.serviceTimes ?? []).join('  ·  '))
      .replace('{instagram}', church?.instagram ?? '')

  return (
    <div className="endscreen" ref={box} style={style}>
      {bg.type === 'image' && bg.darken > 0 && <div style={{ position: 'absolute', inset: 0, background: `rgba(0,0,0,${bg.darken})` }} />}
      {config.lines.map((line, i) => {
        const text = fill(line.text)
        return (
          <div
            key={i}
            className="line"
            style={{
              top: line.y * scale,
              transform: 'translateY(-50%)',
              padding: `0 ${60 * scale}px`,
              fontFamily: `'${line.font || config.font}', sans-serif`,
              fontWeight: cssWeight(line.weight),
              fontSize: line.size * scale,
              letterSpacing: line.spacing * scale,
              color: line.color,
            }}
          >
            {line.uppercase ? text.toUpperCase() : text}
          </div>
        )
      })}
    </div>
  )
}
