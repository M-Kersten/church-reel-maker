import { useEffect, useState } from 'react'
import { api, type Brand, type BrandSummary, type ChurchInfo, type LogoFile, type OutroConfig } from '../api'
import { announceBrandChange } from '../church'
import { useFonts } from '../fonts'
import ChurchTab from './brand/ChurchTab'
import OutroTab from './brand/OutroTab'
import WordsTab, { type WordGroup } from './brand/WordsTab'

export type BrandTab = 'church' | 'words' | 'outro'

const TABS: { id: BrandTab; label: string; says: string }[] = [
  { id: 'church', label: 'Gegevens', says: 'Naam, diensttijden en Instagram van deze kerk' },
  { id: 'words', label: 'Woorden', says: 'Namen die de computer bij het uitschrijven moet kennen' },
  { id: 'outro', label: 'Afsluiter', says: 'Het eindscherm dat achter elke video komt' },
]

interface Props {
  /** Which tab to open on, when something sent you here for one of them. */
  tab?: BrandTab
  onClose: () => void
}

/**
 * A brand holds three unrelated things that happen to belong to the same church: who it is,
 * the words it uses, and the end screen behind its videos. They used to sit on one long
 * page, where the third drowned out the first two. One tab each now, with the brand you are
 * editing named above them and the save button always in view below.
 */
export default function BrandPanel({ tab: opensOn = 'church', onClose }: Props) {
  const families = useFonts()
  // The made end screen is a file on disk; bumping this asks the browser for the new one.
  const [version, setVersion] = useState(0)
  const [tab, setTab] = useState<BrandTab>(opensOn)
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

  // The panel is long; Escape gets you out of it wherever you have scrolled to.
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose])

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))
  const touched = () => {
    setDirty(true)
    setSaved(false)
  }

  const editWords = (group: WordGroup, value: string) => {
    const words = value.split(',').map((w) => w.trim()).filter(Boolean)
    setBrand((b) => (b ? { ...b, vocabulary: { ...b.vocabulary, [group]: words } } : b))
    touched()
  }

  const forget = (heard: string) =>
    setBrand((b) => {
      if (!b) return b
      const rest = Object.fromEntries(Object.entries(b.vocabulary.corrections).filter(([k]) => k !== heard))
      touched()
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
    setBrand((b) => (b ? { ...b, outro: { ...b.outro, ...patch } } : b))
    touched()
  }

  // The brand is named after the church, so renaming one renames the other.
  const editChurch = (patch: Partial<ChurchInfo>) => {
    setBrand((b) => {
      if (!b) return b
      const name = patch.churchName ?? b.name
      return { ...b, name, church: { ...b.church, ...patch } }
    })
    touched()
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

  const shell = (children: React.ReactNode, foot?: React.ReactNode) => (
    <div
      className="sheet"
      role="dialog"
      aria-label="Merk van de kerk"
      onPointerDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="sheet-box wide">
        {/* The chrome stays put and only the body scrolls, so the tabs and the save button
            are where you left them however far down a tab runs. */}
        <header>
          <div className="sheet-title">
            <div>
              <h2>Merk van de kerk</h2>
              {brand && (
                <div className="brand-row">
                  <select id="brand" aria-label="Merk" value={brand.id} disabled={busy} onChange={(e) => switchBrand(e.target.value)}>
                    {brands.map((b) => (
                      <option key={b.id} value={b.id}>{b.name}</option>
                    ))}
                  </select>
                  <button className="small" onClick={addBrand} disabled={busy}>Nieuw merk</button>
                  <button className="small" onClick={removeBrand} disabled={busy || brands.length < 2}>Verwijderen</button>
                  <span className="meta">Werk je voor meerdere kerken of locaties, maak er dan per kerk een aan.</span>
                </div>
              )}
            </div>
            <button className="bare" onClick={onClose} aria-label="Sluiten">✕</button>
          </div>
          {brand && (
            <div className="brand-tabs" role="tablist" aria-label="Onderdelen van het merk">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  id={`brandtab-${t.id}`}
                  aria-selected={tab === t.id}
                  aria-controls={`brandpane-${t.id}`}
                  className={tab === t.id ? 'on' : ''}
                  onClick={() => setTab(t.id)}
                >
                  <strong>{t.label}</strong>
                  <span>{t.says}</span>
                </button>
              ))}
            </div>
          )}
        </header>
        <div className="sheet-body" role="tabpanel" id={`brandpane-${tab}`} aria-labelledby={`brandtab-${tab}`}>
          {children}
        </div>
        {foot}
      </div>
    </div>
  )

  if (!brand) {
    return shell(error ? <div className="error">{error}</div> : <p className="empty">Bezig met laden…</p>)
  }

  return shell(
    <>
      {tab === 'church' && <ChurchTab church={brand.church} onChange={editChurch} />}
      {tab === 'words' && <WordsTab vocabulary={brand.vocabulary} onChange={editWords} onForget={forget} />}
      {tab === 'outro' && (
        <OutroTab
          config={brand.outro}
          church={brand.church}
          families={families}
          logos={logos}
          outroUrl={api.outroUrl(version)}
          active={active}
          onPickLine={setActive}
          onChange={edit}
          onLogosChanged={loadLogos}
          onError={fail}
        />
      )}
    </>,
    <footer className="sheet-foot">
      <button className="primary" onClick={save} disabled={busy || !dirty}>
        {busy ? 'Bezig…' : 'Opslaan en vernieuwen'}
      </button>
      {error ? (
        <span className="wrong">{error}</span>
      ) : dirty ? (
        <span className="meta">Nog niet opgeslagen. Opslaan geldt voor alle drie de tabbladen.</span>
      ) : saved ? (
        <span className="meta">Opgeslagen; de afsluiter is opnieuw gemaakt.</span>
      ) : (
        <span className="meta">Alles staat zoals het is opgeslagen.</span>
      )}
    </footer>,
  )
}
