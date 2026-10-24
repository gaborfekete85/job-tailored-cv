import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { Item, Requirement, RoleView } from './types'

type Props = {
  jobId: number
  item: Item
  role: RoleView
  requirement: Requirement
  onClose: () => void
  onItemChange: (item: Item) => void
}

export function ClarifyModal({ jobId, item, role, requirement, onClose, onItemChange }: Props) {
  const [questions, setQuestions] = useState<string[]>(item.clarification?.questions ?? [])
  const [answers, setAnswers] = useState<Record<string, string>>(() =>
    Object.fromEntries((item.clarification?.answers ?? []).map((a) => [a.question, a.answer])),
  )
  const [busy, setBusy] = useState<'questions' | 'refine' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadQuestions = async () => {
    setBusy('questions')
    setError(null)
    try {
      const updated = await api.askQuestions(jobId, item.id)
      setQuestions(updated.clarification?.questions ?? [])
      onItemChange(updated)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  // Only on open: reuse saved questions when they exist. The ref keeps StrictMode's
  // double effect run from asking the LLM twice.
  const asked = useRef(false)
  useEffect(() => {
    if (asked.current || item.clarification) return
    asked.current = true
    void loadQuestions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && busy === null && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose])

  const refine = async () => {
    setBusy('refine')
    setError(null)
    try {
      const payload = questions.map((question) => ({ question, answer: answers[question] ?? '' }))
      onItemChange(await api.refine(jobId, item.id, payload))
      onClose()
    } catch (e) {
      setError((e as Error).message)
      setBusy(null)
    }
  }

  const answered = questions.some((q) => (answers[q] ?? '').trim())

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && !busy && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="clarify-title">
        <header className="modal-header">
          <div>
            <p className="eyebrow">
              {role.period} · {role.title}
            </p>
            <h2 id="clarify-title">
              <span className="req-id">{requirement.id}</span> {requirement.text}
            </h2>
          </div>
          <button className="icon-button" onClick={onClose} disabled={busy !== null} aria-label="Close">
            ×
          </button>
        </header>

        <div className="modal-body">
          <section className="current-bullet">
            <h3>Current bullet</h3>
            <p className={item.bullet ? '' : 'muted'}>{item.bullet ?? 'No evidence found in this role yet.'}</p>
          </section>

          {busy === 'questions' ? (
            <p className="loading">Thinking of the right questions…</p>
          ) : (
            <ol className="questions">
              {questions.map((question) => (
                <li key={question}>
                  <label>
                    <span>{question}</span>
                    <textarea
                      rows={2}
                      value={answers[question] ?? ''}
                      placeholder="Numbers, scale, outcome — leave empty if unsure. Start lines with - for separate facts."
                      onChange={(e) => setAnswers({ ...answers, [question]: e.target.value })}
                    />
                  </label>
                </li>
              ))}
            </ol>
          )}
          {error && <p className="error">{error}</p>}
        </div>

        <footer className="modal-footer">
          <button className="secondary" onClick={loadQuestions} disabled={busy !== null}>
            New questions
          </button>
          <button className="primary" onClick={refine} disabled={busy !== null || !answered}>
            {busy === 'refine' ? 'Rewriting…' : 'Rewrite bullet'}
          </button>
        </footer>
      </div>
    </div>
  )
}
