import type { RenderStatus } from '../api'
import ProgressIndicator from './ProgressIndicator'
import Section from './Section'

interface Props {
  hasAudio: boolean
  hasSubtitles: boolean
  transcribing: boolean
  canRender: boolean
  renderStatus: RenderStatus
  outputUrl: string | null
  onTranscribe: () => void
  onRender: () => void
}

export default function RenderControls(props: Props) {
  const rendering = props.renderStatus.status === 'running'
  const busy = rendering || props.transcribing
  return (
    <Section
      eyebrow="Laatste stap"
      title="Video maken"
      intro="Klaar met nakijken? Klik op Video maken. Het maken duurt ongeveer een minuut; daarna verschijnt hier een downloadknop. De video is meteen geschikt voor Instagram Reels en YouTube Shorts."
    >
      <div className="render-actions">
        <button onClick={props.onTranscribe} disabled={!props.hasAudio || busy}>
          {props.transcribing ? 'Bezig met uitschrijven…' : props.hasSubtitles ? 'Ondertitels opnieuw maken' : 'Ondertitels maken'}
        </button>
        <button className="primary" onClick={props.onRender} disabled={!props.canRender || busy}>
          {rendering ? 'Video wordt gemaakt…' : 'Video maken'}
        </button>
        {props.outputUrl && props.renderStatus.status === 'done' && (
          <a href={props.outputUrl} download>
            Download de video (mp4)
          </a>
        )}
      </div>
      {!props.hasAudio && <p className="hint">Deze video heeft geen geluid, dus ondertitels kunnen niet automatisch gemaakt worden. Je kunt ze wel zelf typen.</p>}
      {props.hasAudio && !props.hasSubtitles && !props.transcribing && (
        <p className="hint">Tip: klik eerst op Ondertitels maken. De gesproken tekst wordt dan automatisch uitgeschreven; dat duurt ongeveer een minuut.</p>
      )}
      <ProgressIndicator status={props.renderStatus} />
    </Section>
  )
}
