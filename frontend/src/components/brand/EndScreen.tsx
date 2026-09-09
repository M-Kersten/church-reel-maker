import { useEffect, useRef, useState } from 'react'
import { api, type ChurchInfo, type OutroConfig, type OutroLine } from '../../api'
import { cssWeight } from '../../subtitleLayout'

const MARGIN = 60

interface Props {
  config: OutroConfig
  church: ChurchInfo | null
  active: number | null
  onPick: (index: number) => void
  onMove: (index: number, patch: Partial<OutroLine>) => void
}

/** Live end screen. Drag a line to move it up or down, or sideways to align it. */
export default function EndScreen({ config, church, active, onPick, onMove }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(220 / 1080)
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
