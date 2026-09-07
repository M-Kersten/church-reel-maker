import { useEffect, useRef } from 'react'
import type { CropWindow, Output, VideoInfo } from '../api'
import { MAX_ZOOM, canPan, clampCrop, cropGeometry, defaultCrop, minZoom } from '../crop'
import Section from './Section'

interface Props {
  sourceUrl: string
  sourceInfo: VideoInfo
  output: Output
  crop: CropWindow
  currentTime: number
  playing: boolean
  onChange: (crop: CropWindow) => void
}

/**
 * Shows the whole source with the 9:16 output frame drawn on top. Drag the frame to move
 * the crop window, use the slider to zoom; the same numbers drive the preview and the render.
 */
export default function FramingPanel({ sourceUrl, sourceInfo, output, crop, currentTime, playing, onChange }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; crop: CropWindow } | null>(null)

  // Keep the thumbnail roughly in step with the preview: follow play/pause, re-sync after seeks.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    if (Math.abs(v.currentTime - currentTime) > 0.75) v.currentTime = currentTime
    if (playing && v.paused) void v.play().catch(() => undefined)
    if (!playing && !v.paused) v.pause()
  }, [currentTime, playing])

  const g = cropGeometry(sourceInfo, output, crop)
  const pan = canPan(sourceInfo, output, crop)
  const low = minZoom(sourceInfo, output)
  // Frame rectangle in fractions of the source; the frame can be larger than the source (letterbox).
  const frame = {
    left: (g.left - (output.width - g.cropW) / 2) / g.scaledW,
    top: (g.top - (output.height - g.cropH) / 2) / g.scaledH,
    width: output.width / g.scaledW,
    height: output.height / g.scaledH,
  }

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, crop }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    const box = boxRef.current
    if (!d || !box) return
    onChange(clampCrop({
      x: pan.x ? d.crop.x + (e.clientX - d.x) / box.clientWidth : d.crop.x,
      y: pan.y ? d.crop.y + (e.clientY - d.y) / box.clientHeight : d.crop.y,
      zoom: d.crop.zoom,
    }, sourceInfo, output))
  }
  const onPointerUp = () => (drag.current = null)

  const setZoom = (zoom: number) => onChange(clampCrop({ ...crop, zoom }, sourceInfo, output))
  const isDefault = JSON.stringify(crop) === JSON.stringify(defaultCrop(sourceInfo, output))

  return (
    <Section
      eyebrow="Beeldkader"
      title="Welk deel van het beeld gebruiken we?"
      intro="Een staande video laat maar een deel van het brede beeld zien. Sleep het witte kader over het beeld tot de spreker er goed in staat. Je kunt ook de voorvertoning zelf verslepen."
    >
      <div className="framing-stage">
        <div
          ref={boxRef}
          className="framing-source"
          style={{ aspectRatio: `${sourceInfo.width} / ${sourceInfo.height}` }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <video ref={videoRef} src={sourceUrl} muted playsInline preload="auto" draggable={false} />
          <div
            className="framing-frame"
            style={{
              left: `${frame.left * 100}%`,
              top: `${frame.top * 100}%`,
              width: `${frame.width * 100}%`,
              height: `${frame.height * 100}%`,
              cursor: pan.x || pan.y ? 'grab' : 'default',
            }}
          >
            <span>9:16</span>
          </div>
        </div>
      </div>
      <div className="fields" style={{ marginTop: '1rem' }}>
        <label htmlFor="zoom">Zoom</label>
        <div className="inline">
          <input id="zoom" type="range" min={low} max={MAX_ZOOM} step={0.01} value={crop.zoom} onChange={(e) => setZoom(Number(e.target.value))} />
          <output>{crop.zoom.toFixed(2)}×</output>
        </div>
        <label>Positie</label>
        <div className="inline">
          <span className="meta">{Math.round(crop.x * 100)}% van links · {Math.round(crop.y * 100)}% van boven</span>
          <button className="small" onClick={() => onChange(defaultCrop(sourceInfo, output))} disabled={isDefault}>Herstel</button>
          <button className="small" onClick={() => setZoom(low)} title="Laat het hele beeld zien, met zwarte balken">Hele beeld</button>
          <button className="small" onClick={() => setZoom(1)} title="Vul de staande video helemaal">Beeldvullend</button>
        </div>
      </div>
      <p className="hint">Het donkere deel valt weg. Met de zoom-schuif snijd je verder in of laat je juist het hele beeld zien met zwarte balken.</p>
    </Section>
  )
}
