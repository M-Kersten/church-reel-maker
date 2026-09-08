/**
 * The preview draws subtitles and the crop window in the browser; the renderer draws them
 * with FFmpeg and libass. Those two live in different languages and are kept in step by
 * hand. This runs the same cases through the TypeScript copies and diffs the answers
 * against what Python produced, so drift fails a build instead of a church's clip.
 */
import { readFileSync } from 'node:fs'
import { cropGeometry } from '../src/crop.ts'
import { layoutText } from '../src/subtitleLayout.ts'
import type { CropWindow, Output, Style, VideoInfo } from '../src/api.ts'

interface LayoutCase { text: string; size: number; lines: string[]; fontSize: number }
interface CropCase {
  source: [number, number]
  window: [number, number, number]
  scaledW: number
  scaledH: number
  cropW: number
  cropH: number
  left: number
  top: number
}
interface Fixture { output: Output; layout: LayoutCase[]; crop: CropCase[] }

const path = process.argv[2]
if (!path) {
  console.error('usage: node mirror.mjs <path to tests/fixtures/mirror.json>')
  process.exit(2)
}
const fixture: Fixture = JSON.parse(readFileSync(path, 'utf8'))

const style = (fontSize: number): Style => ({
  font: 'Montserrat', fontSize, fontWeight: 'bold', color: '#FFFFFF', outline: 4,
  outlineColor: '#000000', background: false, animation: 'fade', animationSpeed: 180,
})

const source = (width: number, height: number): VideoInfo => ({
  width, height, duration: 30, fps: 30, videoCodec: 'h264',
  hasAudio: true, audioCodec: 'aac', audioSampleRate: 48000, audioChannels: 2,
})

const problems: string[] = []

for (const c of fixture.layout) {
  const got = layoutText(c.text, style(c.size), fixture.output)
  if (got.fontSize !== c.fontSize || got.lines.join('|') !== c.lines.join('|')) {
    problems.push(
      [`layoutText(${JSON.stringify(c.text.slice(0, 44))}, size ${c.size})`,
       `  python: ${c.fontSize}px ${JSON.stringify(c.lines)}`,
       `  ts:     ${got.fontSize}px ${JSON.stringify(got.lines)}`].join('\n'),
    )
  }
}

const CROP_KEYS = ['scaledW', 'scaledH', 'cropW', 'cropH', 'left', 'top'] as const

for (const c of fixture.crop) {
  const window: CropWindow = { x: c.window[0], y: c.window[1], zoom: c.window[2] }
  const got = cropGeometry(source(c.source[0], c.source[1]), fixture.output, window)
  const differs = CROP_KEYS.filter((k) => got[k] !== c[k])
  if (differs.length) {
    const pick = (o: Record<string, number>) => JSON.stringify(
      Object.fromEntries(CROP_KEYS.map((k) => [k, o[k]])))
    problems.push(
      [`cropGeometry(${c.source.join('x')}, window ${c.window.join(', ')}) differs on ${differs.join(', ')}`,
       `  python: ${pick(c as unknown as Record<string, number>)}`,
       `  ts:     ${pick(got as unknown as Record<string, number>)}`].join('\n'),
    )
  }
}

const total = fixture.layout.length + fixture.crop.length
if (problems.length) {
  console.error(`The preview and the renderer disagree on ${problems.length} of ${total} cases:`)
  console.error('')
  console.error(problems.join('\n\n'))
  console.error('')
  console.error('subtitleLayout.ts must match subtitles.py, and crop.ts must match renderer.py.')
  process.exit(1)
}
console.log(`preview matches the renderer on all ${total} cases`)
