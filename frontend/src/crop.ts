// Mirror of the crop geometry in backend/renderer.py: keep both in sync so the preview matches the render.
import type { CropWindow, Output, VideoInfo } from './api'

export const MAX_ZOOM = 3

export interface CropGeometry {
  scaledW: number
  scaledH: number
  cropW: number
  cropH: number
  left: number
  top: number
}

export function coverScale(info: VideoInfo, output: Output): number {
  return Math.max(output.width / info.width, output.height / info.height)
}

/** Zoom at which the whole source fits inside the frame (letterboxed). */
export function minZoom(info: VideoInfo, output: Output): number {
  return Math.min(output.width / info.width, output.height / info.height) / coverScale(info, output)
}

export function defaultCrop(info: VideoInfo, output: Output): CropWindow {
  if (info.height > info.width) return { x: 0.5, y: 0.5, zoom: Math.round(minZoom(info, output) * 10000) / 10000 }
  return { x: 0.5, y: 0.5, zoom: 1 }
}

export function clampCrop(crop: CropWindow, info: VideoInfo, output: Output): CropWindow {
  return {
    x: Math.min(1, Math.max(0, crop.x)),
    y: Math.min(1, Math.max(0, crop.y)),
    zoom: Math.min(MAX_ZOOM, Math.max(minZoom(info, output), crop.zoom)),
  }
}

const even = (n: number) => Math.max(2, Math.round(n / 2) * 2)

export function cropGeometry(info: VideoInfo, output: Output, crop: CropWindow): CropGeometry {
  const zoom = Math.min(4, Math.max(minZoom(info, output), crop.zoom))
  const scale = coverScale(info, output) * zoom
  const scaledW = even(info.width * scale)
  const scaledH = even(info.height * scale)
  const cropW = Math.min(scaledW, output.width)
  const cropH = Math.min(scaledH, output.height)
  const left = Math.round(Math.min(Math.max(crop.x * scaledW - cropW / 2, 0), scaledW - cropW))
  const top = Math.round(Math.min(Math.max(crop.y * scaledH - cropH / 2, 0), scaledH - cropH))
  return { scaledW, scaledH, cropW, cropH, left, top }
}

/** Where the frame's centre can actually move: with a small zoom the source is narrower than the frame. */
export function canPan(info: VideoInfo, output: Output, crop: CropWindow): { x: boolean; y: boolean } {
  const g = cropGeometry(info, output, crop)
  return { x: g.scaledW > g.cropW, y: g.scaledH > g.cropH }
}
