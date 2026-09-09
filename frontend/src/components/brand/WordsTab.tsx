import { Fragment } from 'react'
import type { Vocabulary } from '../../api'

export type WordGroup = 'preachers' | 'series' | 'songbooks' | 'places' | 'extra'

const GROUPS: { key: WordGroup; id: string; label: string; placeholder: string }[] = [
  { key: 'preachers', id: 'vpreach', label: 'Voorgangers', placeholder: 'Dirk de Bree, Hanneke Ouwerkerk' },
  { key: 'series', id: 'vseries', label: 'Series', placeholder: 'Onderweg, Het gaat om liefde' },
  { key: 'songbooks', id: 'vsongs', label: 'Liedbundels', placeholder: 'Opwekking, Psalmen voor Nu' },
  { key: 'places', id: 'vplaces', label: 'Locaties', placeholder: 'Wittevrouwen, Wilhelminapark' },
  { key: 'extra', id: 'vextra', label: 'Overig', placeholder: 'andere woorden die vaak misgaan' },
]

interface Props {
  vocabulary: Vocabulary
  onChange: (group: WordGroup, value: string) => void
  onForget: (heard: string) => void
}

/**
 * Names a speech model cannot guess. Everything here is handed to the transcription before
 * it starts listening, so the better this list is, the less there is to correct afterwards.
 */
export default function WordsTab({ vocabulary, onChange, onForget }: Props) {
  const corrections = Object.entries(vocabulary.corrections)
  return (
    <>
      <p className="tab-intro">
        Eigennamen die de computer niet kan raden. Ze gaan mee naar het uitschrijven, dus hoe
        meer hiervan klopt, hoe minder je in de ondertitels hoeft te verbeteren. Scheid ze met
        komma&rsquo;s.
      </p>
      <div className="fields wide-labels">
        {GROUPS.map((g) => (
          <Fragment key={g.key}>
            <label htmlFor={g.id}>{g.label}</label>
            <input
              id={g.id}
              value={vocabulary[g.key].join(', ')}
              onChange={(e) => onChange(g.key, e.target.value)}
              placeholder={g.placeholder}
            />
          </Fragment>
        ))}
      </div>

      <div className="group">
        <h3>Zelf geleerd</h3>
        {corrections.length === 0 ? (
          <p className="hint">
            Nog niets. Verbeter je een naam in de ondertitels, dan wordt die verbetering hier
            onthouden en de volgende keer meteen toegepast.
          </p>
        ) : (
          <>
            <p className="hint">
              {corrections.length} verbetering{corrections.length === 1 ? '' : 'en'} uit eerdere
              diensten. Deze worden na het uitschrijven automatisch toegepast.
            </p>
            <div className="fixes">
              {corrections.map(([heard, meant]) => (
                <span key={heard} className="fix">
                  <span className="was">{heard}</span> → <strong>{meant}</strong>
                  <button className="bare" title={`"${heard}" niet meer verbeteren`} onClick={() => onForget(heard)}>✕</button>
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  )
}
