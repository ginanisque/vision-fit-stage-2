import type { HeightUnit } from '../types'

interface Props {
  value: string
  unit: HeightUnit
  error: string | null
  onChangeValue: (value: string) => void
  onChangeUnit: (unit: HeightUnit) => void
  onBack: () => void
  onContinue: () => void
}

export function HeightStep({
  value,
  unit,
  error,
  onChangeValue,
  onChangeUnit,
  onBack,
  onContinue,
}: Props) {
  const canContinue = Boolean(error === null && value.trim() !== '')
  return (
    <section className="step">
      <h1>Height and measurement system</h1>
      <p>Choose the units you want for your height and measurement results. Height is used to estimate scale.</p>
      <div className="field-row">
        <input
          type="number"
          inputMode="decimal"
          value={value}
          onChange={(e) => onChangeValue(e.target.value)}
          placeholder={unit === 'cm' ? 'e.g. 165' : 'e.g. 65'}
          aria-label="Height"
        />
        <select
          value={unit}
          onChange={(e) => onChangeUnit(e.target.value as HeightUnit)}
          aria-label="Measurement system"
        >
          <option value="cm">Metric (cm)</option>
          <option value="in">Imperial (inches)</option>
        </select>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button className="secondary" onClick={onBack}>
          Back
        </button>
        <button className="primary" disabled={!canContinue} onClick={onContinue}>
          Continue
        </button>
      </div>
    </section>
  )
}
