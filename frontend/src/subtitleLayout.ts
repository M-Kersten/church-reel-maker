// Mirror of backend/subtitles.py: keep both in sync so the preview matches the render.
import type { Output, Style } from './api'

export const SAFE_MARGIN_BOTTOM = 320
export const SAFE_MARGIN_SIDE = 90
export const CHAR_WIDTH_RATIO = 0.58
export const MIN_FONT_SCALE = 0.6
export const BACKGROUND_ALPHA = 0.5

export const FONTS = ['Inter', 'Montserrat', 'Poppins', 'Arial']
export const WEIGHTS: { value: Style['fontWeight']; label: string; css: number }[] = [
  { value: 'regular', label: 'Regular', css: 400 },
  { value: 'medium', label: 'Medium', css: 500 },
  { value: 'semibold', label: 'Semi bold', css: 600 },
  { value: 'bold', label: 'Bold', css: 700 },
  { value: 'extrabold', label: 'Extra bold', css: 800 },
]

export function cssWeight(weight: Style['fontWeight']): number {
  return WEIGHTS.find((w) => w.value === weight)?.css ?? 700
}

/** Wrap to at most two lines; shrink the font when two lines are not enough. */
export function layoutText(text: string, style: Style, output: Output): { lines: string[]; fontSize: number } {
  text = text.split(/\s+/).filter(Boolean).join(' ')
  const available = output.width - 2 * SAFE_MARGIN_SIDE
  const maxChars = Math.max(8, Math.floor(available / (style.fontSize * CHAR_WIDTH_RATIO)))
  if (text.length <= maxChars) return { lines: [text], fontSize: style.fontSize }

  const words = text.split(' ')
  if (words.length === 1) return { lines: [text], fontSize: style.fontSize }
  let best: { longest: number; first: string; second: string } | null = null
  for (let i = 1; i < words.length; i++) {
    const first = words.slice(0, i).join(' ')
    const second = words.slice(i).join(' ')
    const longest = Math.max(first.length, second.length)
    if (best === null || longest < best.longest) best = { longest, first, second }
  }
  const { longest, first, second } = best!
  if (longest <= maxChars) return { lines: [first, second], fontSize: style.fontSize }
  const scale = Math.max(MIN_FONT_SCALE, maxChars / longest)
  return { lines: [first, second], fontSize: Math.round(style.fontSize * scale) }
}

export function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds - m * 60
  return `${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`
}

/** Accepts "mm:ss.s", "m:ss", or plain seconds. Returns null when unparsable. */
export function parseTime(value: string): number | null {
  const trimmed = value.trim().replace(',', '.')
  if (!trimmed) return null
  const parts = trimmed.split(':')
  if (parts.some((p) => p === '' || Number.isNaN(Number(p)))) return null
  const nums = parts.map(Number)
  const seconds = nums.reduce((acc, n) => acc * 60 + n, 0)
  return seconds >= 0 ? Math.round(seconds * 100) / 100 : null
}
