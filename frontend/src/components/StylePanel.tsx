import type { Style } from '../api'
import { FONTS, WEIGHTS, cssWeight } from '../subtitleLayout'
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
  const outline = style.outline * 0.45
  return (
    <Section step={3} title="Stijl van de ondertitels" intro="Wit met een donkere rand leest bijna altijd het best.">
      <div className="specimen">
        <span
          style={{
            fontFamily: `'${style.font}', sans-serif`,
            fontWeight: cssWeight(style.fontWeight),
            fontSize: `${style.fontSize * 0.4}px`,
            color: style.color,
            WebkitTextStroke: outline > 0 ? `${outline * 2}px ${style.outlineColor}` : undefined,
            paintOrder: 'stroke fill',
            background: style.background ? 'rgba(0,0,0,0.5)' : undefined,
            padding: style.background ? `0 ${outline}px` : undefined,
          }}
        >
          God is op zoek naar jou
        </span>
      </div>
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

        <label htmlFor="color">Kleur</label>
        <div className="inline">
          <input id="color" type="color" value={style.color} onChange={(e) => set('color', e.target.value.toUpperCase())} />
          <span className="meta">tekst</span>
          <input type="color" aria-label="Kleur van de rand" value={style.outlineColor} onChange={(e) => set('outlineColor', e.target.value.toUpperCase())} />
          <span className="meta">rand</span>
        </div>

        <label htmlFor="outline">Rand</label>
        <div className="inline">
          <input id="outline" type="range" min={0} max={12} step={1} value={style.outline} onChange={(e) => set('outline', Number(e.target.value))} />
          <output>{style.outline}</output>
        </div>

        <label htmlFor="background">Vlak</label>
        <div className="inline">
          <input id="background" type="checkbox" checked={style.background} onChange={(e) => set('background', e.target.checked)} />
          <label htmlFor="background">Donker vlak achter de tekst, bij druk beeld</label>
        </div>
      </div>
    </Section>
  )
}
