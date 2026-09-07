import type { ReactNode } from 'react'

interface Props {
  eyebrow?: string
  title: string
  intro?: ReactNode
  className?: string
  children: ReactNode
}

/** Card with the identity's heading pattern: small gold label, heavy purple heading, short explanation. */
export default function Section({ eyebrow, title, intro, className, children }: Props) {
  return (
    <section className={`panel ${className ?? ''}`}>
      <header className="panel-head">
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
        {intro && <p className="intro">{intro}</p>}
      </header>
      {children}
    </section>
  )
}
