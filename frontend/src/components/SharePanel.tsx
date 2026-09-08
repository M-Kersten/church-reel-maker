import { useState } from 'react'
import Section from './Section'

interface Props {
  /** File name used while there is no title; the project id, as on the server. */
  fallback: string
  title: string
  description: string
  onChange: (title: string, description: string) => void
}

const MAX = 220

/** Title (used as the file name) and the short text that goes with the post. */
export default function SharePanel({ fallback, title, description, onChange }: Props) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    const text = [title, description].filter(Boolean).join('\n\n')
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  // Mirrors brands.slug() on the server, so the shown file name matches the download.
  const slug =
    title
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || fallback

  return (
    <Section step={6} title="Titel en omschrijving" intro="De titel wordt de bestandsnaam van de download. De omschrijving plak je onder je post.">
      <div className="share">
        <label htmlFor="cliptitle">Titel</label>
        <input
          id="cliptitle"
          type="text"
          value={title}
          maxLength={80}
          placeholder="God vraagt niet dat je perfect bent"
          onChange={(e) => onChange(e.target.value, description)}
        />
        <p className="hint">Bestandsnaam wordt <code>{slug}.mp4</code></p>

        <label htmlFor="clipdesc">Omschrijving</label>
        <textarea
          id="clipdesc"
          rows={3}
          value={description}
          maxLength={MAX}
          placeholder="Een kort moment uit de dienst van zondag. #kerk #utrecht"
          onChange={(e) => onChange(title, e.target.value)}
        />
        <div className="place-row">
          <button className="small" type="button" onClick={copy} disabled={!title && !description}>
            {copied ? 'Gekopieerd' : 'Kopieer voor je post'}
          </button>
          <span className="meta">{description.length}/{MAX} tekens</span>
        </div>
      </div>
    </Section>
  )
}
