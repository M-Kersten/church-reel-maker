import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import type { ChurchInfo, CropWindow, Output, Segment, Style, VideoInfo, Watermark } from '../api'
import { api } from '../api'
import { canPan, clampCrop, cropGeometry } from '../crop'
import { BACKGROUND_ALPHA, SAFE_MARGIN_BOTTOM, SAFE_MARGIN_SIDE, cssWeight, formatTime, layoutText } from '../subtitleLayout'

export interface PreviewHandle {
  seek: (time: number) => void
}

interface Props {
  sourceUrl: string
  sourceInfo: VideoInfo
  outroUrl: string
  church: ChurchInfo | null
  segments: Segment[]
  style: Style
  output: Output
  crop: CropWindow
  watermark?: Watermark
  onCropChange?: (crop: CropWindow) => void
  onTime: (time: number) => void
  onPlayState?: (playing: boolean) => void
}

/**
 * 9:16 preview: the <video> is cropped/padded with object-fit exactly like the
 * static crop in the renderer, and subtitles are drawn as an HTML overlay using
 * the same layout rules as the ASS file. When the clip ends the outro plays.
 */
const VideoPreview = forwardRef<PreviewHandle, Props>(function VideoPreview(props, ref) {
  const { sourceUrl, sourceInfo, outroUrl, church, segments, style, output, crop, watermark, onCropChange, onTime, onPlayState } = props
  const boxRef = useRef<HTMLDivElement>(null)
  const mainRef = useRef<HTMLVideoElement>(null)
  const outroRef = useRef<HTMLVideoElement>(null)
  const [phase, setPhase] = useState<'main' | 'outro'>('main')
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(0)
  const [scale, setScale] = useState(360 / output.width)
  const drag = useRef<{ x: number; y: number; crop: CropWindow; moved: boolean } | null>(null)

  useImperativeHandle(ref, () => ({
    seek: (t: number) => {
      const v = mainRef.current
      if (!v) return
      outroRef.current?.pause()
      setPhase('main')
      v.currentTime = t
      setTime(t)
      onTime(t)
    },
  }))

  // Preview pixels per output pixel.
  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const observer = new ResizeObserver(() => setScale(el.clientWidth / output.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [output.width])

  // Smooth time updates while playing.
  useEffect(() => {
    onPlayState?.(playing)
  }, [playing, onPlayState])

  useEffect(() => {
    let frame = 0
    const tick = () => {
      const v = mainRef.current
      if (v && phase === 'main') {
        setTime(v.currentTime)
        onTime(v.currentTime)
      }
      frame = requestAnimationFrame(tick)
    }
    if (playing) frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, phase, onTime])

  const active = useMemo(() => segments.find((s) => time >= s.start && time < s.end && s.text.trim()), [segments, time])
  const layout = active ? layoutText(active.text, style, output) : null

  const togglePlay = () => {
    const v = phase === 'main' ? mainRef.current : outroRef.current
    if (!v) return
    if (v.paused) void v.play()
    else v.pause()
  }

  const onMainEnded = () => {
    setPhase('outro')
    const o = outroRef.current
    if (o) {
      o.currentTime = 0
      void o.play().catch(() => setPlaying(false))
    }
  }

  const onOutroEnded = () => {
    setPlaying(false)
    setPhase('main')
    if (mainRef.current) mainRef.current.currentTime = 0
    setTime(0)
  }

  const portrait = sourceInfo.height > sourceInfo.width
  const fontSize = layout ? layout.fontSize * scale : 0
  const outline = style.outline * scale

  // Place the source inside the 9:16 frame exactly like the renderer's scale/crop/pad chain.
  const g = cropGeometry(sourceInfo, output, crop)
  const padX = (output.width - g.cropW) / 2
  const padY = (output.height - g.cropH) / 2
  const videoStyle: React.CSSProperties = {
    width: g.scaledW * scale,
    height: g.scaledH * scale,
    left: (padX - g.left) * scale,
    top: (padY - g.top) * scale,
    display: phase === 'main' ? 'block' : 'none',
    cursor: onCropChange ? 'grab' : 'pointer',
  }
  const pan = canPan(sourceInfo, output, crop)

  // Drag the video to move the crop window; a click without movement toggles playback.
  const onPointerDown = (e: React.PointerEvent<HTMLVideoElement>) => {
    if (!onCropChange) return
    drag.current = { x: e.clientX, y: e.clientY, crop, moved: false }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: React.PointerEvent<HTMLVideoElement>) => {
    const d = drag.current
    if (!d || !onCropChange) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    if (!d.moved && Math.abs(dx) + Math.abs(dy) < 4) return
    d.moved = true
    onCropChange(clampCrop({
      x: pan.x ? d.crop.x - dx / (g.scaledW * scale) : d.crop.x,
      y: pan.y ? d.crop.y - dy / (g.scaledH * scale) : d.crop.y,
      zoom: d.crop.zoom,
    }, sourceInfo, output))
  }
  const onPointerUp = () => {
    const moved = drag.current?.moved
    drag.current = null
    if (!moved) togglePlay()
  }

  return (
    <div>
      <div className="phone">
      <div className="preview" ref={boxRef}>
        <video
          ref={mainRef}
          src={sourceUrl}
          playsInline
          preload="auto"
          style={videoStyle}
          draggable={false}
          onPlay={() => setPlaying(true)}
          onPause={() => phase === 'main' && setPlaying(false)}
          onEnded={onMainEnded}
          onSeeked={() => mainRef.current && (setTime(mainRef.current.currentTime), onTime(mainRef.current.currentTime))}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={() => (drag.current = null)}
          onClick={onCropChange ? undefined : togglePlay}
        />
        <video
          ref={outroRef}
          src={outroUrl}
          playsInline
          preload="auto"
          style={{ objectFit: 'contain', display: phase === 'outro' ? 'block' : 'none' }}
          onPlay={() => setPlaying(true)}
          onPause={() => phase === 'outro' && setPlaying(false)}
          onEnded={onOutroEnded}
          onClick={togglePlay}
        />
        {phase === 'main' && watermark?.file && (
          <img
            className="mark"
            alt=""
            src={api.logoUrl(watermark.file)}
            style={{
              width: output.width * watermark.width * scale,
              opacity: watermark.opacity,
              top: watermark.corner.startsWith('top') ? watermark.margin * scale : undefined,
              bottom: watermark.corner.startsWith('bottom') ? watermark.margin * scale : undefined,
              left: watermark.corner.endsWith('Left') ? watermark.margin * scale : undefined,
              right: watermark.corner.endsWith('Right') ? watermark.margin * scale : undefined,
            }}
          />
        )}
        {phase === 'main' && <div className="safe" style={{ bottom: SAFE_MARGIN_BOTTOM * scale }} />}
        {phase === 'main' && layout && (
          <div
            key={`${active?.start}-${style.animation}-${style.animationSpeed}`}
            className={`subtitle sub-anim sub-anim-${style.animation}`}
            style={{
              animationDuration: `${style.animationSpeed}ms`,
              bottom: SAFE_MARGIN_BOTTOM * scale,
              paddingLeft: SAFE_MARGIN_SIDE * scale,
              paddingRight: SAFE_MARGIN_SIDE * scale,
              fontFamily: `'${style.font}', sans-serif`,
              fontWeight: cssWeight(style.fontWeight),
              fontSize,
              color: style.color,
              WebkitTextStroke: outline > 0 ? `${outline * 2}px ${style.outlineColor}` : undefined,
              paintOrder: 'stroke fill',
            }}
          >
            {layout.lines.map((line, i) => (
              <div key={i}>
                <span
                  style={
                    style.background
                      ? { background: `rgba(0,0,0,${BACKGROUND_ALPHA})`, padding: `0 ${outline}px`, boxShadow: `0 0 0 ${outline}px rgba(0,0,0,${BACKGROUND_ALPHA})` }
                      : undefined
                  }
                >
                  {line}
                </span>
              </div>
            ))}
          </div>
        )}
        <span className="badge">{phase === 'main' ? `9:16 · ${portrait ? 'staand' : 'liggend'} · zoom ${crop.zoom.toFixed(2)}` : `Afsluiter · ${church?.churchName ?? ''}`}</span>
      </div>
      </div>
      <div className="transport">
        <button className="small" onClick={togglePlay}>{playing ? 'Pauze' : 'Afspelen'}</button>
        <span className="tc">{phase === 'main' ? formatTime(time) : 'afsluiter'}</span>
        <input
          type="range"
          min={0}
          max={sourceInfo.duration}
          step={0.05}
          value={phase === 'main' ? time : sourceInfo.duration}
          onChange={(e) => {
            const t = Number(e.target.value)
            if (mainRef.current) mainRef.current.currentTime = t
            if (phase === 'outro') {
              outroRef.current?.pause()
              setPhase('main')
            }
            setTime(t)
            onTime(t)
          }}
        />
        <span className="tc">{formatTime(sourceInfo.duration)}</span>
      </div>
      <p className="facts">
        Bron {sourceInfo.width}×{sourceInfo.height} · {sourceInfo.duration.toFixed(1).replace('.', ',')} s ·{' '}
        {sourceInfo.hasAudio ? 'met geluid' : 'zonder geluid'} → video {output.width}×{output.height}, {output.fps} beelden per seconde
      </p>
    </div>
  )
})

export default VideoPreview
