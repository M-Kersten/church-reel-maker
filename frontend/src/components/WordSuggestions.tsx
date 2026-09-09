import { useEffect, useState } from 'react'
import { api } from '../api'

interface Props {
  projectId: string
  /** Bumped whenever the subtitles were saved, so we look again. */
  savedAt: number
}

/**
 * The speech model gets the same names wrong every week. When someone fixes one here,
 * this offers to remember it for the church, so next Sunday it comes out right.
 */
export default function WordSuggestions({ projectId, savedAt }: Props) {
  const [found, setFound] = useState<Record<string, string>>({})
  const [learned, setLearned] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!savedAt) return
    api.wordSuggestions(projectId).then((r) => setFound(r.suggestions)).catch(() => undefined)
  }, [projectId, savedAt])

  const remember = async (words: Record<string, string>) => {
    setBusy(true)
    try {
      await api.learnWords(projectId, words)
      setLearned((was) => [...was, ...Object.values(words)])
      setFound((was) => Object.fromEntries(Object.entries(was).filter(([k]) => !(k in words))))
    } catch {
      /* not being able to remember a word is not worth interrupting the edit for */
    } finally {
      setBusy(false)
    }
  }

  const pairs = Object.entries(found)
  if (pairs.length === 0 && learned.length === 0) return null

  return (
    <div className="learn">
      {pairs.length > 0 && (
        <>
          <p>
            <strong>Zal ik dit onthouden?</strong> Dan schrijft de computer het volgende keer meteen goed.
          </p>
          <ul>
            {pairs.map(([heard, meant]) => (
              <li key={heard}>
                <span><span className="was">{heard}</span> → <strong>{meant}</strong></span>
                <button className="small" disabled={busy} onClick={() => remember({ [heard]: meant })}>Onthouden</button>
              </li>
            ))}
          </ul>
          {pairs.length > 1 && (
            <button className="small" disabled={busy} onClick={() => remember(found)}>Alles onthouden</button>
          )}
        </>
      )}
      {learned.length > 0 && (
        <p className="meta">Onthouden voor deze kerk: {learned.join(', ')}.</p>
      )}
    </div>
  )
}
