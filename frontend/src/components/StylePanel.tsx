import { useEffect, useState } from 'react'
import type { Style, SubtitleAnimation } from '../api'
import { WEIGHT_LABELS, resolveWeight, useFonts, weightsOf } from '../fonts'
import { cssWeight } from '../subtitleLayout'
import Section from './Section'

interface Props {
  style: Style
  onChange: (style: Style) => void
}

export default function StylePanel({ style, onChange }: Props) {
  const families = useFonts()
  const set = <K extends keyof Style>(key: K, value: Style[K]) => onChange({ ...style, [key]: value })
  // Some fonts have one weight only; keep the choice within what the family has.
  const pickFont = (font: string) => onChange({ ...style, font, fontWeight: resolveWeight(families, font, style.fontWeight) })
  const weights = weightsOf(families, style.font)
  const outline = style.outline * 0.45
  // Replay the specimen animation now and then; the key also replays it on every change.
  const [beat, setBeat] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setBeat((b) => b + 1), 2600)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <Section step={3} title="Stijl van de ondertitels" intro="Wit met een donkere rand leest bijna altijd het best.">
      <div className="specimen">
        <span
          key={`${style.animation}-${style.animationSpeed}-${beat}`}
          className={`sub-anim sub-anim-${style.animation}`}
          style={{
            animationDuration: `${style.animationSpeed}ms`,
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
        <select id="font" value={style.font} onChange={(e) => pickFont(e.target.value)}>
          {families.map((f) => (
            <option key={f.name} value={f.name}>{f.name}</option>
          ))}
        </select>

        <label htmlFor="weight">Dikte</label>
        <select id="weight" value={style.fontWeight} disabled={weights.length < 2} onChange={(e) => set('fontWeight', e.target.value as Style['fontWeight'])}>
          {weights.map((w) => (
            <option key={w} value={w}>{WEIGHT_LABELS[w]}</option>
          ))}
        </select>

        <label htmlFor="size">Grootte</label>
        <div className="inline">
          <input id="size" type="range" min={24} max={200} step={2} value={style.fontSize} onChange={(e) => set('fontSize', Number(e.target.value))} />
          <output>{style.fontSize}</output>
        </div>
        <p className="hint span">Boven de 110 vullen lange zinnen bijna het hele beeld. Kijk het na in het voorbeeld links.</p>

        <label htmlFor="animation">Beweging</label>
        <select id="animation" value={style.animation} onChange={(e) => set('animation', e.target.value as SubtitleAnimation)}>
          <option value="none">Geen, tekst staat er meteen</option>
          <option value="fade">Zacht opkomen</option>
          <option value="pop">Opveren, valt op</option>
          <option value="slide">Van onder omhoog</option>
        </select>

        {style.animation !== 'none' && (
          <>
            <label htmlFor="animspeed">Snelheid</label>
            <div className="inline">
              <input
                id="animspeed"
                type="range"
                min={60}
                max={600}
                step={20}
                value={style.animationSpeed}
                onChange={(e) => set('animationSpeed', Number(e.target.value))}
              />
              <output>{(style.animationSpeed / 1000).toFixed(2)}s</output>
            </div>
          </>
        )}

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
