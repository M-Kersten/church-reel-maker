import type { RenderStatus } from '../api'
import ProgressIndicator from './ProgressIndicator'

interface Props {
  hasAudio: boolean
  hasSubtitles: boolean
  transcribeStatus: RenderStatus
  canRender: boolean
  renderStatus: RenderStatus
  outputUrl: string | null
  onTranscribe: () => void
  onRender: () => void
  onStop: () => void
  onStopTranscribe: () => void
}

/** The two actions that finish the job, right under the preview so they are always in view. */
export default function RenderControls(props: Props) {
  const rendering = props.renderStatus.status === 'running'
  const transcribing = props.transcribeStatus.status === 'running'
  const busy = rendering || transcribing
  const stopping = (s: RenderStatus) => s.message.startsWith('Bezig met stoppen')
  return (
    <div className="go">
      <div className="row">
        <button className="primary" onClick={props.onRender} disabled={!props.canRender || busy}>
          {rendering ? 'Bezig met maken…' : 'Video maken'}
        </button>
        {rendering ? (
          <button onClick={props.onStop} disabled={stopping(props.renderStatus)}>Stoppen</button>
        ) : transcribing ? (
          <button onClick={props.onStopTranscribe} disabled={stopping(props.transcribeStatus)}>Stoppen</button>
        ) : (
          <button onClick={props.onTranscribe} disabled={!props.hasAudio}>
            {props.hasSubtitles ? 'Opnieuw uitschrijven' : 'Ondertitels maken'}
          </button>
        )}
      </div>
      {props.outputUrl && props.renderStatus.status === 'done' && !transcribing && (
        <p className="hint"><a href={props.outputUrl} download>Download de video (mp4)</a></p>
      )}
      {!props.hasAudio && <p className="hint">Deze video heeft geen geluid. Typ de ondertitels zelf, of ga direct door.</p>}
      {props.hasAudio && !props.hasSubtitles && !busy && props.transcribeStatus.status === 'idle' && (
        <p className="hint">Begin met Ondertitels maken. Dat duurt ongeveer een minuut.</p>
      )}
      {transcribing && stopping(props.transcribeStatus) && (
        <p className="hint">Stoppen kan een halve minuut duren; het uitschrijven stopt tussen twee zinnen.</p>
      )}
      {!rendering && <ProgressIndicator status={props.transcribeStatus} />}
      {!transcribing && <ProgressIndicator status={props.renderStatus} />}
    </div>
  )
}
