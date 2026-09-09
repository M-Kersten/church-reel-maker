const DAYS = ['zondag', 'maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag']
const MONTHS = ['januari', 'februari', 'maart', 'april', 'mei', 'juni',
  'juli', 'augustus', 'september', 'oktober', 'november', 'december']

const WHEN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/

/**
 * "zondag 30 augustus · 10:00", the way you would say it out loud.
 *
 * The stamp already carries the church's own offset, so it is read as written rather than
 * handed to Date: a service at ten o'clock says ten o'clock, whatever the clock of the
 * computer looking at it is set to. The weekday is worked out in UTC for the same reason.
 */
export function said(when: string, thisYear = new Date().getFullYear()): string {
  const found = WHEN.exec(when)
  if (!found) return when
  const [, year, month, day, hour, minute] = found
  const weekday = DAYS[new Date(Date.UTC(+year, +month - 1, +day)).getUTCDay()]
  const saidYear = +year === thisYear ? '' : ` ${year}`
  return `${weekday} ${+day} ${MONTHS[+month - 1]}${saidYear} · ${hour}:${minute}`
}

export const minutes = (seconds: number | null) => (seconds ? `${Math.round(seconds / 60)} min` : '')
