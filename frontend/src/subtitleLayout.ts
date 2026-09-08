// Mirror of backend/subtitles.py: keep both in sync so the preview matches the render.
import type { Output, Style } from './api'

export const SAFE_MARGIN_BOTTOM = 320
export const SAFE_MARGIN_SIDE = 90
export const CHAR_WIDTH_RATIO = 0.58
export const MIN_FONT_SCALE = 0.6
export const MAX_LINES = 3
export const BACKGROUND_ALPHA = 0.5

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

/** Greedy fill: put as many words on a line as fit within `width` characters. */
function wrapWords(words: string[], width: number): string[] {
  const lines: string[] = []
  let current = ''
  for (const word of words) {
    const candidate = `${current} ${word}`.trim()
    if (current && candidate.length > width) {
      lines.push(current)
      current = word
    } else {
      current = candidate
    }
  }
  if (current) lines.push(current)
  return lines
}

/**
 * Split the words over at most `count` lines, none wider than maxChars.
 * Starts from evenly divided lines and widens until the greedy fill needs no extra line.
 */
function fitLines(words: string[], count: number, maxChars: number): string[] | null {
  const total = words.join(' ').length
  const start = Math.max(Math.max(...words.map((w) => w.length)), Math.ceil(total / count))
  for (let width = start; width <= maxChars; width++) {
    const lines = wrapWords(words, width)
    if (lines.length <= count) return lines
  }
  return null
}

/** Wrap over as few lines as the text needs; shrink the font only as a last resort. */
export function layoutText(text: string, style: Style, output: Output): { lines: string[]; fontSize: number } {
  text = text.split(/\s+/).filter(Boolean).join(' ')
  const available = output.width - 2 * SAFE_MARGIN_SIDE
  const maxChars = Math.max(8, Math.floor(available / (style.fontSize * CHAR_WIDTH_RATIO)))
  if (text.length <= maxChars) return { lines: [text], fontSize: style.fontSize }

  const words = text.split(' ')
  if (words.length === 1) return { lines: [text], fontSize: style.fontSize }

  for (let count = 2; count <= MAX_LINES; count++) {
    const lines = fitLines(words, count, maxChars)
    if (lines) return { lines, fontSize: style.fontSize }
  }

  const lines = fitLines(words, MAX_LINES, text.length) ?? [text]
  const longest = Math.max(...lines.map((l) => l.length))
  const fitted = Math.floor(available / (longest * CHAR_WIDTH_RATIO))
  return { lines, fontSize: Math.max(Math.trunc(style.fontSize * MIN_FONT_SCALE), Math.min(style.fontSize, fitted)) }
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
