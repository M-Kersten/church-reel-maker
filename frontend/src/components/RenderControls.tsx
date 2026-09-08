import type { RenderStatus } from '../api'
import ProgressIndicator from './ProgressIndicator'

interface Props {
  hasAudio: boolean
  hasSubtitles: boolean
  transcribing: boolean
  canRender: boolean
  renderStatus: RenderStatus
  outputUrl: string | null
  onTranscribe: () => void
  onRender: () => void
  onStop: () => void
}

/** The two actions that finish the job, right under the preview so they are always in view. */
export default function RenderControls(props: Props) {
  const rendering = props.renderStatus.status === 'running'
  const busy = rendering || props.transcribing
  return (
    <div className="go">
      <div className="row">
        <button className="primary" onClick={props.onRender} disabled={!props.canRender || busy}>
          {rendering ? 'Bezig met maken…' : 'Video maken'}
        </button>
        {rendering ? (
          <button onClick={props.onStop} disabled={props.renderStatus.message.startsWith('Bezig met stoppen')}>Stoppen</button>
        ) : (
          <button onClick={props.onTranscribe} disabled={!props.hasAudio || busy}>
            {props.transcribing ? 'Uitschrijven…' : props.hasSubtitles ? 'Opnieuw uitschrijven' : 'Ondertitels maken'}
          </button>
        )}
      </div>
      {props.outputUrl && props.renderStatus.status === 'done' && (
        <p className="hint"><a href={props.outputUrl} download>Download de video (mp4)</a></p>
      )}
      {!props.hasAudio && <p className="hint">Deze video heeft geen geluid. Typ de ondertitels zelf, of ga direct door.</p>}
      {props.hasAudio && !props.hasSubtitles && !props.transcribing && (
        <p className="hint">Begin met Ondertitels maken. Dat duurt ongeveer een minuut.</p>
      )}
      <ProgressIndicator status={props.renderStatus} />
    </div>
  )
}
