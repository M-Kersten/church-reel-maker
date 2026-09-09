import { api, type ChurchInfo, type FontFamily, type FontWeight, type LogoFile, type OutroConfig, type OutroLine, type OutroMotion } from '../../api'
import { WEIGHT_LABELS, resolveWeight, weightsOf } from '../../fonts'
import EndScreen from './EndScreen'

const BACKGROUNDS: { value: OutroConfig['background']['type']; label: string }[] = [
  { value: 'gradient', label: 'Kleurverloop' },
  { value: 'solid', label: 'Effen kleur' },
  { value: 'image', label: 'Afbeelding' },
]
const ALIGNMENTS: { value: OutroLine['align']; label: string; title: string }[] = [
  { value: 'left', label: '◧', title: 'Links uitlijnen' },
  { value: 'center', label: '▣', title: 'Midden' },
  { value: 'right', label: '◨', title: 'Rechts uitlijnen' },
]
const MOTIONS: { value: OutroMotion; label: string }[] = [
  { value: 'none', label: 'Stilstaand' },
  { value: 'in', label: 'Langzaam inzoomen' },
  { value: 'out', label: 'Langzaam uitzoomen' },
  { value: 'up', label: 'Rustig omhoog' },
]
const HEIGHT = 1920

const newLine = (y: number, weight: FontWeight): OutroLine => ({
  text: 'Nieuwe regel', y, align: 'center', size: 48, weight, color: '#FFFFFF', font: '', spacing: 0, uppercase: false, delay: 0,
})

interface Props {
  config: OutroConfig
  church: ChurchInfo
  families: FontFamily[]
  logos: LogoFile[]
  outroUrl: string
  active: number | null
  onPickLine: (index: number | null) => void
  onChange: (patch: Partial<OutroConfig>) => void
  onLogosChanged: () => Promise<unknown>
  onError: (e: unknown) => void
}

/**
 * The end screen behind every video. Four things to set, in the order you would think of
 * them: what it looks like, how it moves, the logo, and the words. The preview on the left
 * stays put while you work down the list.
 */
export default function OutroTab({
  config, church, families, logos, outroUrl, active, onPickLine, onChange, onLogosChanged, onError,
}: Props) {
  const background = config.background
  const setBackground = (patch: Partial<OutroConfig['background']>) => onChange({ background: { ...background, ...patch } })
  const editLine = (index: number, patch: Partial<OutroLine>) =>
    onChange({ lines: config.lines.map((l, i) => (i === index ? { ...l, ...patch } : l)) })

  /** Move every line together, keeping the spacing between them. */
  const moveBlock = (where: 'top' | 'middle' | 'bottom') => {
    if (config.lines.length === 0) return
    const top = Math.min(...config.lines.map((l) => l.y))
    const bottom = Math.max(...config.lines.map((l) => l.y))
    const target = where === 'top' ? 420 : where === 'bottom' ? HEIGHT - 420 - (bottom - top) : (HEIGHT - (bottom - top)) / 2
    const shift = target - top
    onChange({ lines: config.lines.map((l) => ({ ...l, y: Math.round(Math.min(HEIGHT - 40, Math.max(40, l.y + shift))) })) })
  }

  const uploadBackground = async (file: File) => {
    try {
      const { image } = await api.uploadOutroBackground(file)
      setBackground({ type: 'image', image })
    } catch (e) {
      onError(e)
    }
  }

  const uploadLogo = async (file: File) => {
    try {
      const { file: name } = await api.uploadLogo(file)
      await onLogosChanged()
      onChange({ logo: { ...config.logo, file: name } })
    } catch (e) {
      onError(e)
    }
  }

  return (
    <div className="outro-edit">
      <div className="outro-preview">
        {/* Only the live preview is pinned. The made video is looked at once, so it lives
            with the settings instead of taking up half the column that stays in view. */}
        <div className="stuck">
          <EndScreen config={config} church={church} active={active} onPick={onPickLine} onMove={editLine} />
          <div className="place-row">
            <span className="meta">Zet alles</span>
            <button className="small" onClick={() => moveBlock('top')}>Boven</button>
            <button className="small" onClick={() => moveBlock('middle')}>Midden</button>
            <button className="small" onClick={() => moveBlock('bottom')}>Onder</button>
          </div>
          <p className="hint">Sleep een regel naar de plek waar je hem wilt hebben.</p>
        </div>
      </div>

      <div className="outro-settings">
        <section className="group">
          <h3>Achtergrond</h3>
          <div className="fields">
            <label>Soort</label>
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
                <p className="hint span">Een donkere laag over de foto houdt de tekst leesbaar.</p>
              </>
            )}
          </div>
        </section>

        <section className="group">
          <h3>Beweging en duur</h3>
          <div className="fields">
            <label htmlFor="dur">Duur</label>
            <div className="inline">
              <input id="dur" type="range" min={2} max={12} step={0.5} value={config.duration} onChange={(e) => onChange({ duration: Number(e.target.value) })} />
              <output>{String(config.duration).replace('.', ',')} s</output>
            </div>

            <label htmlFor="motion">Camera</label>
            <select id="motion" value={config.motion} onChange={(e) => onChange({ motion: e.target.value as OutroMotion })}>
              {MOTIONS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
            <p className="hint span">Een trage beweging houdt het eindscherm levend. Je ziet hem pas terug nadat je hebt opgeslagen.</p>
          </div>
        </section>

        <section className="group">
          <h3>Logo</h3>
          <p className="hint">Komt op met de tekst en verdwijnt er weer mee.</p>
          <div className="logos">
            <button type="button" className={`plain ${config.logo.file ? '' : 'on'}`} onClick={() => onChange({ logo: { ...config.logo, file: '' } })}>geen</button>
            {logos.map((f) => (
              <button
                type="button"
                key={f.file}
                title={f.file}
                className={config.logo.file === f.file ? 'on' : ''}
                onClick={() => onChange({ logo: { ...config.logo, file: f.file } })}
              >
                <img src={api.logoUrl(f.file)} alt={f.file} />
              </button>
            ))}
            <label className="upload-link">
              Logo toevoegen
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                onChange={(e) => e.target.files?.[0] && uploadLogo(e.target.files[0])}
              />
            </label>
          </div>
          {config.logo.file && (
            <div className="fields">
              <label htmlFor="logow">Breedte</label>
              <div className="inline">
                <input id="logow" type="range" min={120} max={900} step={20} value={config.logo.width} onChange={(e) => onChange({ logo: { ...config.logo, width: Number(e.target.value) } })} />
                <output>{config.logo.width}</output>
              </div>
              <label htmlFor="logoy">Hoogte</label>
              <div className="inline">
                <input id="logoy" type="range" min={80} max={1840} step={20} value={config.logo.y} onChange={(e) => onChange({ logo: { ...config.logo, y: Number(e.target.value) } })} />
                <output>{config.logo.y}</output>
              </div>
            </div>
          )}
        </section>

        <section className="group">
          <h3>Teksten</h3>
          <div className="fields">
            <label htmlFor="ofont">Lettertype</label>
            <select
              id="ofont"
              value={config.font}
              onChange={(e) => {
                const font = e.target.value
                onChange({ font, lines: config.lines.map((l) => ({ ...l, weight: l.font ? l.weight : resolveWeight(families, font, l.weight) })) })
              }}
            >
              {families.map((f) => (
                <option key={f.name} value={f.name}>{f.name}</option>
              ))}
            </select>
            <p className="hint span">
              Geldt voor alle regels die geen eigen lettertype hebben. Met {'{churchName}'},{' '}
              {'{serviceTimes}'} en {'{instagram}'} vul je de gegevens van de kerk automatisch in.
            </p>
          </div>
          <div className="lines-edit">
            {config.lines.map((line, i) => {
              const weights = weightsOf(families, line.font || config.font)
              return (
                <div key={i} className={`line-edit ${active === i ? 'on' : ''}`} onFocusCapture={() => onPickLine(i)}>
                  <div className="top">
                    <input value={line.text} onChange={(e) => editLine(i, { text: e.target.value })} placeholder="Tekst van deze regel" />
                    <button className="bare small" onClick={() => onChange({ lines: config.lines.filter((_, n) => n !== i) })} title="Regel verwijderen">✕</button>
                  </div>
                  <div className="bits">
                    <span className="seg small-seg">
                      {ALIGNMENTS.map((a) => (
                        <button key={a.value} className={line.align === a.value ? 'on' : ''} title={a.title} onClick={() => editLine(i, { align: a.value })}>
                          {a.label}
                        </button>
                      ))}
                    </span>
                    <label>Hoogte <input type="number" min={40} max={1880} step={10} value={line.y} onChange={(e) => editLine(i, { y: Number(e.target.value) })} /></label>
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
                    <label>
                      Lettertype
                      <select value={line.font} onChange={(e) => editLine(i, { font: e.target.value, weight: resolveWeight(families, e.target.value || config.font, line.weight) })}>
                        <option value="">Zelfde als scherm</option>
                        {families.map((f) => (
                          <option key={f.name} value={f.name}>{f.name}</option>
                        ))}
                      </select>
                    </label>
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
                onChange({ lines: [...config.lines, newLine(Math.min(1840, (last?.y ?? 900) + 140), resolveWeight(families, config.font, 'bold'))] })
              }}
            >
              Regel toevoegen
            </button>
          </p>
        </section>

        <section className="group">
          <h3>Zoals hij nu in de video staat</h3>
          <div className="made">
            <video src={outroUrl} muted playsInline controls preload="auto"
                   onLoadedMetadata={(e) => (e.currentTarget.currentTime = e.currentTarget.duration / 2)} />
            <div>
              <p className="hint">Deze wordt opnieuw gemaakt zodra je opslaat, en komt achter elke clip die je daarna maakt.</p>
              <p className="hint">
                Liever je eigen filmpje? Zet het als outro.mp4 in de map templates en zet generate
                op false in templates/outro.json.
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
