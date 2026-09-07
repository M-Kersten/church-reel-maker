import type { Style } from '../api'
import { FONTS, WEIGHTS } from '../subtitleLayout'

interface Props {
  style: Style
  onChange: (style: Style) => void
}

export default function StylePanel({ style, onChange }: Props) {
  const set = <K extends keyof Style>(key: K, value: Style[K]) => onChange({ ...style, [key]: value })
  return (
    <section className="panel">
      <h2>Subtitle style</h2>
      <div className="fields">
        <label htmlFor="font">Font</label>
        <select id="font" value={style.font} onChange={(e) => set('font', e.target.value)}>
          {FONTS.map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>

        <label htmlFor="weight">Weight</label>
        <select id="weight" value={style.fontWeight} onChange={(e) => set('fontWeight', e.target.value as Style['fontWeight'])}>
          {WEIGHTS.map((w) => (
            <option key={w.value} value={w.value}>{w.label}</option>
          ))}
        </select>

        <label htmlFor="size">Size</label>
        <div className="inline">
          <input id="size" type="range" min={24} max={120} step={2} value={style.fontSize} onChange={(e) => set('fontSize', Number(e.target.value))} />
          <output>{style.fontSize}</output>
        </div>

        <label htmlFor="color">Text color</label>
        <input id="color" type="color" value={style.color} onChange={(e) => set('color', e.target.value.toUpperCase())} />

        <label htmlFor="outline">Outline</label>
        <div className="inline">
          <input id="outline" type="range" min={0} max={12} step={1} value={style.outline} onChange={(e) => set('outline', Number(e.target.value))} />
          <output>{style.outline}</output>
          <input type="color" aria-label="Outline color" value={style.outlineColor} onChange={(e) => set('outlineColor', e.target.value.toUpperCase())} />
        </div>

        <label htmlFor="background">Background</label>
        <div className="inline">
          <input id="background" type="checkbox" checked={style.background} onChange={(e) => set('background', e.target.checked)} />
          <span>Dark translucent box</span>
        </div>
      </div>
    </section>
  )
}
