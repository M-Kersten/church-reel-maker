import type { Style } from '../api'
import { FONTS, WEIGHTS } from '../subtitleLayout'
import Section from './Section'

interface Props {
  style: Style
  onChange: (style: Style) => void
}

const WEIGHT_LABELS: Record<Style['fontWeight'], string> = {
  regular: 'Normaal',
  medium: 'Medium',
  semibold: 'Halfvet',
  bold: 'Vet',
  extrabold: 'Extra vet',
}

export default function StylePanel({ style, onChange }: Props) {
  const set = <K extends keyof Style>(key: K, value: Style[K]) => onChange({ ...style, [key]: value })
  return (
    <Section
      eyebrow="Stijl"
      title="Zo zien de ondertitels eruit"
      intro="Kies lettertype, grootte en kleur. De voorvertoning laat elke wijziging meteen zien. Wit met een donkere rand is bijna altijd goed leesbaar."
    >
      <div className="fields">
        <label htmlFor="font">Lettertype</label>
        <select id="font" value={style.font} onChange={(e) => set('font', e.target.value)}>
          {FONTS.map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>

        <label htmlFor="weight">Dikte</label>
        <select id="weight" value={style.fontWeight} onChange={(e) => set('fontWeight', e.target.value as Style['fontWeight'])}>
          {WEIGHTS.map((w) => (
            <option key={w.value} value={w.value}>{WEIGHT_LABELS[w.value]}</option>
          ))}
        </select>

        <label htmlFor="size">Grootte</label>
        <div className="inline">
          <input id="size" type="range" min={24} max={120} step={2} value={style.fontSize} onChange={(e) => set('fontSize', Number(e.target.value))} />
          <output>{style.fontSize}</output>
        </div>

        <label htmlFor="color">Tekstkleur</label>
        <input id="color" type="color" value={style.color} onChange={(e) => set('color', e.target.value.toUpperCase())} />

        <label htmlFor="outline">Rand</label>
        <div className="inline">
          <input id="outline" type="range" min={0} max={12} step={1} value={style.outline} onChange={(e) => set('outline', Number(e.target.value))} />
          <output>{style.outline}</output>
          <input type="color" aria-label="Kleur van de rand" value={style.outlineColor} onChange={(e) => set('outlineColor', e.target.value.toUpperCase())} />
        </div>

        <label htmlFor="background">Achtergrond</label>
        <div className="inline">
          <input id="background" type="checkbox" checked={style.background} onChange={(e) => set('background', e.target.checked)} />
          <span>Donker vlak achter de tekst (handig bij druk beeld)</span>
        </div>
      </div>
    </Section>
  )
}
