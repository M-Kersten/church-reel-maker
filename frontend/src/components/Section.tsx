import type { ReactNode } from 'react'

interface Props {
  /** Step number shown in front of the title, for sections that follow a fixed order. */
  step?: number
  title: string
  intro?: ReactNode
  aside?: ReactNode
  className?: string
  children: ReactNode
}

export default function Section({ step, title, intro, aside, className, children }: Props) {
  return (
    <section className={`card ${className ?? ''}`}>
      <header>
        {step !== undefined && <span className="step">{step}</span>}
        <div style={{ flex: 1 }}>
          <h2>{title}</h2>
          {intro && <p className="intro">{intro}</p>}
        </div>
        {aside}
      </header>
      {children}
    </section>
  )
}
