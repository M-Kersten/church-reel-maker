/**
 * One class of bug neither the type checker nor a unit test can see: an unrelated rule
 * reaching an element through a shared class name.
 *
 * It is not hypothetical. The page header was `.bar`, and so is a progress track. The
 * header's `padding: 0.75rem 1.5rem` therefore applied to every 6px rail and, with
 * border-box sizing, left it exactly zero pixels tall. Every progress bar in the app
 * rendered as an empty groove for weeks, while the percentage beside it read correctly.
 *
 * The guard is narrow on purpose: a track must state its own box, so a rule somewhere else
 * cannot decide it. Shared component classes like `.card` and `.error` are meant to be
 * shared and are none of this test's business.
 */
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const problems: string[] = []

function ruleBody(selector: string): string | null {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = css.match(new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, 'm'))
  return match ? match[1] : null
}

// Every element that draws a fraction of something as a coloured strip.
const TRACKS = ['.progress .bar', '.uploading .bar']

for (const track of TRACKS) {
  const body = ruleBody(track)
  if (body === null) {
    problems.push(`${track} has no rule of its own; it is drawn by whatever else matches it.`)
    continue
  }
  if (!/(^|;)\s*height\s*:/.test(body)) {
    problems.push(`${track} does not set its own height.`)
  }
  if (!/(^|;)\s*padding\s*:/.test(body)) {
    problems.push(
      `${track} does not set its own padding. With border-box sizing, padding inherited ` +
      `from any other rule that matches this class is taken out of its ${'height'} and the ` +
      `strip inside it disappears. Set padding explicitly.`)
  }
}

// The header must not be called .bar again: that is the collision that started this.
if (/(?:^|\})\s*\.bar\s*\{/m.test(css)) {
  problems.push('.bar is a bare rule again. The page header is .appbar; a progress track is '
    + 'the .bar. Giving both the same name flattens the track.')
}

/**
 * The header holds two kinds of button that must never look alike: the switch between the
 * two workspaces, and the two panels that open on top of your work. They used to share one
 * style, and nobody could tell from the bar which of the four would change the page and
 * which would open a window. Each kind states its own fill and border, so a change to one
 * cannot quietly restyle the other.
 */
const KINDS = ['.appbar .pages button', '.appbar .tools button']

for (const kind of KINDS) {
  const body = ruleBody(kind)
  if (body === null) {
    problems.push(`${kind} has no rule of its own, so it looks like whatever else matches it.`)
    continue
  }
  for (const property of ['background', 'border']) {
    if (!new RegExp(`(^|;)\\s*${property}\\s*:`).test(body)) {
      problems.push(`${kind} does not state its own ${property}, so it can end up looking `
        + 'like the other kind of header button.')
    }
  }
}

if (problems.length) {
  console.error('The stylesheet leaves something to be decided elsewhere:\n')
  console.error(problems.map((p) => `  ${p}`).join('\n'))
  process.exit(1)
}
console.log(`${TRACKS.length} progress tracks state their own box, `
  + `${KINDS.length} kinds of header button state their own look`)
