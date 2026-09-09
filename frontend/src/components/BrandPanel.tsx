import { useEffect, useRef, useState } from 'react'
import { api, type Brand, type BrandSummary, type ChurchInfo, type FontWeight, type LogoFile, type OutroConfig, type OutroLine, type OutroMotion } from '../api'
import { announceBrandChange } from '../church'
import { WEIGHT_LABELS, resolveWeight, useFonts, weightsOf } from '../fonts'
import { cssWeight } from '../subtitleLayout'

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
const MARGIN = 60

const newLine = (y: number, weight: FontWeight): OutroLine => ({
  text: 'Nieuwe regel', y, align: 'center', size: 48, weight, color: '#FFFFFF', font: '', spacing: 0, uppercase: false, delay: 0,
})

interface Props {
  onClose: () => void
}

/**
 * A brand holds everything that makes a video belong to one church: the details, the words
 * it uses, and the end screen behind every video. It sits apart from the clip you are
 * making, because it is set once and then holds for every clip afterwards. Several churches
 * can live side by side here.
 */
export default function BrandPanel({ onClose }: Props) {
  const families = useFonts()
  // The made end screen is a file on disk; bumping this asks the browser for the new one.
  const [version, setVersion] = useState(0)
  const outroUrl = api.outroUrl(version)
  const [brands, setBrands] = useState<BrandSummary[]>([])
  const [brand, setBrand] = useState<Brand | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [active, setActive] = useState<number | null>(null)
  const [logos, setLogos] = useState<LogoFile[]>([])

  const loadLogos = () => api.logos().then(setLogos).catch(() => setLogos([]))
  useEffect(() => {
    loadLogos()
  }, [])

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))
  const config = brand?.outro ?? null
  const church = brand?.church ?? null
  const vocabulary = brand?.vocabulary ?? null
  const corrections = Object.entries(vocabulary?.corrections ?? {})

  type WordGroup = 'preachers' | 'series' | 'songbooks' | 'places' | 'extra'
  const wordList = (group: WordGroup) => (vocabulary?.[group] ?? []).join(', ')
  const editWords = (group: WordGroup, value: string) => {
    const words = value.split(',').map((w) => w.trim()).filter(Boolean)
    setBrand((b) => (b ? { ...b, vocabulary: { ...b.vocabulary, [group]: words } } : b))
    setDirty(true)
    setSaved(false)
  }
  const forget = (heard: string) =>
    setBrand((b) => {
      if (!b) return b
      const rest = Object.fromEntries(Object.entries(b.vocabulary.corrections).filter(([k]) => k !== heard))
      setDirty(true)
      setSaved(false)
      return { ...b, vocabulary: { ...b.vocabulary, corrections: rest } }
    })

  const openBrand = (id: string) =>
    api
      .brand(id)
      .then((b) => {
        setBrand(b)
        setDirty(false)
        setSaved(false)
      })
      .catch(fail)

  useEffect(() => {
    api
      .brands()
      .then((list) => {
        setBrands(list)
        const current = list.find((b) => b.active) ?? list[0]
        if (current) void openBrand(current.id)
      })
      .catch(fail)
  }, [])

  const edit = (patch: Partial<OutroConfig>) => {
    if (!brand) return
    setBrand({ ...brand, outro: { ...brand.outro, ...patch } })
    setDirty(true)
    setSaved(false)
  }

  const editChurch = (patch: Partial<ChurchInfo>) => {
    if (!brand) return
    setBrand({ ...brand, church: { ...brand.church, ...patch } })
    setDirty(true)
    setSaved(false)
  }

  const switchBrand = async (id: string) => {
    setBusy(true)
    setError(null)
    try {
      await api.activateBrand(id)
      await openBrand(id)
      setBrands(await api.brands())
      announceBrandChange()
      setVersion((v) => v + 1)
    } catch (e) {
      fail(e)
    } finally {
      setBusy(false)
    }
  }

  const addBrand = async () => {
    const name = window.prompt('Naam van het nieuwe merk (bijvoorbeeld de naam van de kerk of locatie)')
    if (!name?.trim() || !brand) return
    setBusy(true)
    try {
      const created = await api.createBrand(name.trim(), brand.id)
      setBrands(await api.brands())
      await switchBrand(created.id)
    } catch (e) {
      fail(e)
    } finally {
      setBusy(false)
    }
  }

  const removeBrand = async () => {
    if (!brand || brands.length < 2) return
    if (!window.confirm(`Merk "${brand.name}" verwijderen?`)) return
    setBusy(true)
    try {
      const left = await api.deleteBrand(brand.id)
      setBrands(left)
      const next = left.find((b) => b.active) ?? left[0]
      if (next) await switchBrand(next.id)
    } catch (e) {
      fail(e)
    } finally {
      setBusy(false)
    }
  }
  const editLine = (index: number, patch: Partial<OutroLine>) =>
    edit({ lines: config!.lines.map((l, i) => (i === index ? { ...l, ...patch } : l)) })

  /** Move every line together, keeping the spacing between them. */
  const moveBlock = (where: 'top' | 'middle' | 'bottom') => {
    if (!config || config.lines.length === 0) return
    const top = Math.min(...config.lines.map((l) => l.y))
    const bottom = Math.max(...config.lines.map((l) => l.y))
    const target = where === 'top' ? 420 : where === 'bottom' ? HEIGHT - 420 - (bottom - top) : (HEIGHT - (bottom - top)) / 2
    const shift = target - top
    edit({ lines: config.lines.map((l) => ({ ...l, y: Math.round(Math.min(HEIGHT - 40, Math.max(40, l.y + shift))) })) })
  }

  const save = async () => {
    if (!brand) return
    setBusy(true)
    setError(null)
    try {
      setBrand(await api.saveBrand(brand))
      setBrands(await api.brands())
      setDirty(false)
      setSaved(true)
      announceBrandChange()
      setVersion((v) => v + 1)
    } catch (e) {
      fail(e)
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
      fail(e)
    } finally {
      setBusy(false)
    }
  }

  if (!brand || !config) {
    return (
      <div className="sheet" role="dialog" aria-label="Merk van de kerk">
        <div className="sheet-box wide">
          <header>
            <div>
              <h2>Merk van de kerk</h2>
            </div>
            <button className="bare" onClick={onClose} aria-label="Sluiten">✕</button>
          </header>
          {error ? <div className="error">{error}</div> : <p className="empty">Bezig met laden…</p>}
        </div>
      </div>
    )
  }

  const background = config.background
  const setBackground = (patch: Partial<OutroConfig['background']>) => edit({ background: { ...background, ...patch } })

  return (
    <div className="sheet" role="dialog" aria-label="Merk van de kerk">
      <div className="sheet-box wide">
        <header>
          <div>
            <h2>Merk van de kerk</h2>
            <p className="intro">
              De gegevens van de kerk, de woorden die in deze gemeente vallen en het eindscherm
              achter elke video. Werk je voor meerdere kerken of locaties, maak dan per kerk een
              merk aan en wissel hier.
            </p>
          </div>
          <button className="bare" onClick={onClose} aria-label="Sluiten">✕</button>
        </header>

      <div className="brand-row">
        <label htmlFor="brand">Merk</label>
        <select id="brand" value={brand.id} disabled={busy} onChange={(e) => switchBrand(e.target.value)}>
          {brands.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
        <button className="small" onClick={addBrand} disabled={busy}>Nieuw merk</button>
        <button className="small" onClick={removeBrand} disabled={busy || brands.length < 2}>Verwijderen</button>
      </div>

      <div className="fields" style={{ marginBottom: '1.2rem' }}>
        <label htmlFor="bname">Naam kerk</label>
        <input id="bname" value={church?.churchName ?? ''} onChange={(e) => { editChurch({ churchName: e.target.value }); setBrand((b) => (b ? { ...b, name: e.target.value } : b)) }} />
        <label htmlFor="btimes">Diensttijden</label>
        <input
          id="btimes"
          value={(church?.serviceTimes ?? []).join(', ')}
          onChange={(e) => editChurch({ serviceTimes: e.target.value.split(',').map((t) => t.trim()).filter(Boolean) })}
          placeholder="10:00 Wittevrouwen, 11:30 Wilhelminapark"
        />
        <label htmlFor="binsta">Instagram</label>
        <input id="binsta" value={church?.instagram ?? ''} onChange={(e) => editChurch({ instagram: e.target.value })} placeholder="@jouwkerk" />
      </div>

      <h3 style={{ marginTop: '0.4rem' }}>Woorden van deze kerk</h3>
      <p className="hint" style={{ marginTop: 0 }}>
        Namen die de computer niet kan raden. Hoe meer hiervan klopt, hoe minder je achteraf
        hoeft te verbeteren. Scheid ze met komma&rsquo;s.
      </p>
      <div className="fields" style={{ marginBottom: '1rem' }}>
        <label htmlFor="vpreach">Voorgangers</label>
        <input id="vpreach" value={wordList('preachers')} onChange={(e) => editWords('preachers', e.target.value)}
               placeholder="Dirk de Bree, Hanneke Ouwerkerk" />
        <label htmlFor="vseries">Series</label>
        <input id="vseries" value={wordList('series')} onChange={(e) => editWords('series', e.target.value)}
               placeholder="Onderweg, Het gaat om liefde" />
        <label htmlFor="vsongs">Liedbundels</label>
        <input id="vsongs" value={wordList('songbooks')} onChange={(e) => editWords('songbooks', e.target.value)}
               placeholder="Opwekking, Psalmen voor Nu" />
        <label htmlFor="vplaces">Locaties</label>
        <input id="vplaces" value={wordList('places')} onChange={(e) => editWords('places', e.target.value)}
               placeholder="Wittevrouwen, Wilhelminapark" />
        <label htmlFor="vextra">Overig</label>
        <input id="vextra" value={wordList('extra')} onChange={(e) => editWords('extra', e.target.value)}
               placeholder="andere woorden die vaak misgaan" />
      </div>
      {corrections.length > 0 && (
        <>
          <p className="hint" style={{ marginTop: '-0.5rem' }}>
            Onthouden verbeteringen ({corrections.length}). Deze worden na het uitschrijven automatisch toegepast.
          </p>
          <div className="fixes">
            {corrections.map(([heard, meant]) => (
              <span key={heard} className="fix">
                <span className="was">{heard}</span> → <strong>{meant}</strong>
                <button className="bare" title="Vergeten" onClick={() => forget(heard)}>✕</button>
              </span>
            ))}
          </div>
        </>
      )}
      <p className="hint" style={{ marginTop: '-0.6rem', marginBottom: '1rem' }}>
        Sleep de teksten in de voorvertoning naar de plek waar je ze wilt hebben. Met {'{churchName}'}, {'{serviceTimes}'} en {'{instagram}'} vul je deze gegevens automatisch in.
      </p>
      <div className="outro-edit">
        <div>
          <EndScreen
            config={config}
            church={church}
            active={active}
            onPick={setActive}
            onMove={(index, patch) => editLine(index, patch)}
          />
          <div className="place-row">
            <span className="meta">Zet alles</span>
            <button className="small" onClick={() => moveBlock('top')}>Boven</button>
            <button className="small" onClick={() => moveBlock('middle')}>Midden</button>
            <button className="small" onClick={() => moveBlock('bottom')}>Onder</button>
          </div>
          <div className="made">
            <p className="meta" style={{ margin: '0.7rem 0 0.25rem' }}>Zoals hij nu in de video staat:</p>
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

            <label htmlFor="motion">Camera</label>
            <select id="motion" value={config.motion} onChange={(e) => edit({ motion: e.target.value as OutroMotion })}>
              {MOTIONS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          <p className="hint" style={{ marginTop: '0.4rem' }}>
            Een trage beweging houdt het eindscherm levend. Je ziet het pas terug nadat je hebt opgeslagen.
          </p>

          <h3 style={{ marginTop: '1.2rem' }}>Logo</h3>
          <div className="logos">
            <button type="button" className={`plain ${config.logo.file ? '' : 'on'}`} onClick={() => edit({ logo: { ...config.logo, file: '' } })}>geen</button>
            {logos.map((f) => (
              <button
                type="button"
                key={f.file}
                title={f.file}
                className={config.logo.file === f.file ? 'on' : ''}
                onClick={() => edit({ logo: { ...config.logo, file: f.file } })}
              >
                <img src={api.logoUrl(f.file)} alt={f.file} />
              </button>
            ))}
            <label className="upload-link">
              Logo toevoegen
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                onChange={async (e) => {
                  const file = e.target.files?.[0]
                  if (!file) return
                  try {
                    const { file: name } = await api.uploadLogo(file)
                    await loadLogos()
                    edit({ logo: { ...config.logo, file: name } })
                  } catch (err) {
                    fail(err)
                  }
                }}
              />
            </label>
          </div>
          {config.logo.file && (
            <div className="fields">
              <label htmlFor="logow">Breedte</label>
              <div className="inline">
                <input id="logow" type="range" min={120} max={900} step={20} value={config.logo.width} onChange={(e) => edit({ logo: { ...config.logo, width: Number(e.target.value) } })} />
                <output>{config.logo.width}</output>
              </div>
              <label htmlFor="logoy">Hoogte</label>
              <div className="inline">
                <input id="logoy" type="range" min={80} max={1840} step={20} value={config.logo.y} onChange={(e) => edit({ logo: { ...config.logo, y: Number(e.target.value) } })} />
                <output>{config.logo.y}</output>
              </div>
            </div>
          )}

          <h3 style={{ marginTop: '1.2rem' }}>Teksten</h3>
          <p className="hint" style={{ marginTop: 0 }}>Klik een regel aan om hem in de voorvertoning te zien oplichten.</p>
          <div className="lines-edit">
            {config.lines.map((line, i) => {
              const weights = weightsOf(families, line.font || config.font)
              return (
                <div key={i} className={`line-edit ${active === i ? 'on' : ''}`} onFocusCapture={() => setActive(i)}>
                  <div className="top">
                    <input value={line.text} onChange={(e) => editLine(i, { text: e.target.value })} placeholder="Tekst van deze regel" />
                    <button className="bare small" onClick={() => edit({ lines: config.lines.filter((_, n) => n !== i) })} title="Regel verwijderen">✕</button>
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
                edit({ lines: [...config.lines, newLine(Math.min(1840, (last?.y ?? 900) + 140), resolveWeight(families, config.font, 'bold'))] })
              }}
            >
              Regel toevoegen
            </button>
          </p>

          <div className="save-row">
            <button className="primary" onClick={save} disabled={busy || !dirty}>
              {busy ? 'Bezig…' : 'Opslaan en vernieuwen'}
            </button>
            {saved && !dirty && <span className="meta">Opgeslagen; de afsluiter is opnieuw gemaakt.</span>}
            {dirty && <span className="meta">Nog niet opgeslagen.</span>}
          </div>
          {error && <div className="error" style={{ marginTop: '0.7rem', marginBottom: 0 }}>{error}</div>}
          <p className="hint">Liever je eigen filmpje? Zet het als outro.mp4 in de map templates en zet generate op false in templates/outro.json.</p>
        </div>
      </div>
      </div>
    </div>
  )
}

interface ScreenProps {
  config: OutroConfig
  church: ChurchInfo | null
  active: number | null
  onPick: (index: number) => void
  onMove: (index: number, patch: Partial<OutroLine>) => void
}

/** Live end screen. Drag a line to move it up or down, or sideways to align it. */
function EndScreen({ config, church, active, onPick, onMove }: ScreenProps) {
  const box = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(190 / 1080)
  const drag = useRef<{ index: number; y: number; startY: number; align: OutroLine['align'] } | null>(null)

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

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>, index: number) => {
    drag.current = { index, y: e.clientY, startY: config.lines[index].y, align: config.lines[index].align }
    onPick(index)
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    const el = box.current
    if (!d || !el) return
    const y = Math.round(Math.min(1880, Math.max(40, d.startY + (e.clientY - d.y) / scale)) / 5) * 5
    // Sideways: the third of the frame the pointer is in decides the alignment.
    const x = (e.clientX - el.getBoundingClientRect().left) / el.clientWidth
    const align: OutroLine['align'] = x < 0.28 ? 'left' : x > 0.72 ? 'right' : 'center'
    onMove(d.index, { y, align })
  }
  const onPointerUp = () => (drag.current = null)

  return (
    <div className="endscreen" ref={box} style={style}>
      {bg.type === 'image' && bg.darken > 0 && <div className="veil" style={{ background: `rgba(0,0,0,${bg.darken})` }} />}
      {config.logo.file && (
        <img
          className="outro-logo"
          alt=""
          src={api.logoUrl(config.logo.file)}
          style={{ width: config.logo.width * scale, left: '50%', top: config.logo.y * scale, transform: 'translate(-50%, -50%)' }}
        />
      )}
      {config.lines.map((line, i) => {
        const text = fill(line.text)
        const place: React.CSSProperties =
          line.align === 'left'
            ? { left: MARGIN * scale, right: 'auto', textAlign: 'left', maxWidth: `calc(100% - ${MARGIN * 2 * scale}px)` }
            : line.align === 'right'
              ? { right: MARGIN * scale, left: 'auto', textAlign: 'right', maxWidth: `calc(100% - ${MARGIN * 2 * scale}px)` }
              : { left: MARGIN * scale, right: MARGIN * scale, textAlign: 'center' }
        return (
          <div
            key={i}
            className={`line ${active === i ? 'on' : ''}`}
            style={{
              ...place,
              top: line.y * scale,
              transform: 'translateY(-50%)',
              fontFamily: `'${line.font || config.font}', sans-serif`,
              fontWeight: cssWeight(line.weight),
              fontSize: line.size * scale,
              letterSpacing: line.spacing * scale,
              color: line.color,
            }}
            onPointerDown={(e) => onPointerDown(e, i)}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            {line.uppercase ? text.toUpperCase() : text}
          </div>
        )
      })}
    </div>
  )
}
