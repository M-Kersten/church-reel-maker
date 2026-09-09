import { useEffect, useRef } from 'react'
import type { CropWindow, Output, Track, VideoInfo } from '../api'
import { MAX_ZOOM, canPan, clampCrop, cropGeometry, defaultCrop, minZoom } from '../crop'
import { cropAt } from '../track'
import Section from './Section'

interface Props {
  sourceUrl: string
  sourceInfo: VideoInfo
  output: Output
  crop: CropWindow
  currentTime: number
  playing: boolean
  /** Seconds into the source file where this clip begins. */
  sourceStart?: number
  /** The path found for this clip, if one was found at all. */
  track: Track | null
  following: boolean
  /** True while the app is out looking for the speaker, and how far it has got. */
  searching: boolean
  searchNote: string
  onChange: (crop: CropWindow) => void
  onFollow: (follow: boolean) => void
  onSearch: () => void
}

/**
 * Shows the whole source with the 9:16 output frame drawn on top. Drag the frame to move
 * the crop window, use the slider to zoom; the same numbers drive the preview and the render.
 */
export default function FramingPanel({
  sourceUrl, sourceInfo, output, crop, currentTime, playing, sourceStart = 0,
  track, following, searching, searchNote, onChange, onFollow, onSearch,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; crop: CropWindow } | null>(null)

  // Keep the thumbnail roughly in step with the preview: follow play/pause, re-sync after seeks.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const wanted = sourceStart + currentTime
    if (Math.abs(v.currentTime - wanted) > 0.75) v.currentTime = wanted
    if (playing && v.paused) void v.play().catch(() => undefined)
    if (!playing && !v.paused) v.pause()
  }, [currentTime, playing, sourceStart])

  // While following, the box sits where the path says at this moment; the user's own
  // window is still what the height and the zoom come from, and what it falls back to.
  const shown = cropAt(crop, track, following, currentTime)
  const g = cropGeometry(sourceInfo, output, shown)
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
    if (following) return  // the path decides where it goes; dragging would only fight it
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

  const found = track ? Math.round(track.coverage * 100) : 0
  const canFollow = Boolean(track && track.x.length)

  return (
    <Section
      step={2}
      title="Beeldkader"
      intro="Een staande video toont maar een deel van het brede beeld. Laat het kader de spreker volgen, of zet het zelf op de goede plek."
    >
      <div className="seg framing-pick">
        <button className={following ? '' : 'on'} onClick={() => onFollow(false)} disabled={searching}>
          Zelf kaderen
        </button>
        <button
          className={following ? 'on' : ''}
          onClick={() => onFollow(true)}
          disabled={searching || !canFollow}
          title={canFollow ? undefined : 'Er is voor deze clip geen spreker gevonden om te volgen'}
        >
          Volg de spreker
        </button>
      </div>

      <p className="hint framing-said">
        {searching
          ? searchNote || 'De clip wordt doorgekeken op de spreker. Dit duurt ongeveer tien seconden per minuut video.'
          : following
            ? `Het kader volgt de spreker${track && track.cuts.length ? `, en springt mee met de ${track.cuts.length} camerawissel${track.cuts.length === 1 ? '' : 's'}` : ''}. Klopt het niet, zet het dan zelf.`
            : canFollow
              ? `De spreker is in ${found}% van deze clip gevonden. Sleep het gouden kader, of laat het hem volgen.`
              : 'Sleep het gouden kader tot de spreker er goed in staat; slepen in de voorvertoning links werkt ook.'}
        {!searching && !canFollow && (
          <> <button className="bare small" onClick={onSearch}>Zoek de spreker</button></>
        )}
        {!searching && canFollow && !following && track && !track.enough && (
          <> <span className="warn-inline">Er is te weinig van hem teruggevonden om op te vertrouwen.</span></>
        )}
        {!searching && canFollow && following && (
          <> <button className="bare small" onClick={onSearch}>Opnieuw zoeken</button></>
        )}
      </p>

      <div className="frame-stage">
        <div
          ref={boxRef}
          className="frame-source"
          style={{ aspectRatio: `${sourceInfo.width} / ${sourceInfo.height}` }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <video ref={videoRef} src={sourceUrl} muted playsInline preload="auto" draggable={false} />
          <div
            className={following ? 'frame-box auto' : 'frame-box'}
            style={{
              left: `${frame.left * 100}%`,
              top: `${frame.top * 100}%`,
              width: `${frame.width * 100}%`,
              height: `${frame.height * 100}%`,
              cursor: following ? 'default' : pan.x || pan.y ? 'grab' : 'default',
            }}
          >
            <span>{following ? 'volgt' : '9:16'}</span>
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
          <span className="meta">
            {following
              ? `${Math.round(shown.x * 100)}% van links · door de spreker bepaald`
              : `${Math.round(crop.x * 100)}% van links · ${Math.round(crop.y * 100)}% van boven`}
          </span>
          <button className="small" onClick={() => onChange(defaultCrop(sourceInfo, output))} disabled={isDefault}>Herstel</button>
          <button className="small" onClick={() => setZoom(low)} title="Laat het hele beeld zien, met zwarte balken">Hele beeld</button>
          <button className="small" onClick={() => setZoom(1)} title="Vul de staande video helemaal">Beeldvullend</button>
        </div>
      </div>
      <p className="hint">
        Het donkere deel valt weg. Met de zoom-schuif snijd je verder in, of laat je het hele beeld zien met zwarte balken.
        {following && ' Hoe verder je inzoomt, hoe meer het kader moet meebewegen.'}
      </p>
    </Section>
  )
}
