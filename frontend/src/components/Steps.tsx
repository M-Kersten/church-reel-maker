interface Props {
  steps: string[]
  /** Index of the step the user is on; earlier steps are done. Use steps.length when everything is finished. */
  current: number
}

export default function Steps({ steps, current }: Props) {
  return (
    <ol className="track" aria-label="Voortgang">
      {steps.map((label, i) => (
        <li key={label} className={i < current ? 'done' : i === current ? 'current' : ''}>
          <span className="dot">{i < current ? '✓' : i + 1}</span>
          {label}
        </li>
      ))}
    </ol>
  )
}
