/**
 * When a service was, as the church would say it.
 *
 * The platform stamps each recording with its own offset (`+02:00`). Running that through
 * `new Date(...)` re-tells it in whatever timezone the viewer's computer is set to, so a
 * service at ten o'clock reads as eight on a machine on UTC. These cases pin the reading to
 * what the stamp says.
 */
import { minutes, said } from '../src/serviceTimes.ts'

interface Case { when: string; year?: number; want: string }

const CASES: Case[] = [
  { when: '2026-08-30T10:00:00+02:00', year: 2026, want: 'zondag 30 augustus · 10:00' },
  { when: '2026-09-06T10:00:00+02:00', year: 2026, want: 'zondag 6 september · 10:00' },
  // Winter time, one hour of offset less, still ten o'clock.
  { when: '2026-01-04T10:00:00+01:00', year: 2026, want: 'zondag 4 januari · 10:00' },
  // Another year is worth saying.
  { when: '2025-12-25T09:30:00+01:00', year: 2026, want: 'donderdag 25 december 2025 · 09:30' },
  // An evening service, and a weekday one.
  { when: '2026-08-30T18:30:00+02:00', year: 2026, want: 'zondag 30 augustus · 18:30' },
  { when: '2026-12-24T22:00:00+01:00', year: 2026, want: 'donderdag 24 december · 22:00' },
  // Nothing we recognise comes back untouched rather than as "Invalid Date".
  { when: '', want: '' },
  { when: 'binnenkort', want: 'binnenkort' },
]

const problems: string[] = []

for (const c of CASES) {
  const got = said(c.when, c.year)
  if (got !== c.want) problems.push(`said(${JSON.stringify(c.when)}) gave ${JSON.stringify(got)}, expected ${JSON.stringify(c.want)}`)
}

for (const [seconds, want] of [[5753, '96 min'], [59, '1 min'], [0, ''], [null, '']] as [number | null, string][]) {
  const got = minutes(seconds)
  if (got !== want) problems.push(`minutes(${seconds}) gave ${JSON.stringify(got)}, expected ${JSON.stringify(want)}`)
}

if (problems.length) {
  console.error('Service times are not read the way the church wrote them:\n')
  console.error(problems.map((p) => `  ${p}`).join('\n'))
  process.exit(1)
}
console.log(`${CASES.length} service times read as the church wrote them`)
