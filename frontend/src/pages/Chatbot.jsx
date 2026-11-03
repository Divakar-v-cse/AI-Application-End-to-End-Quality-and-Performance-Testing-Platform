import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { useFetch } from '../hooks.js'
import {
  Card,
  DataTable,
  ErrorBanner,
  Kpi,
  PageHeader,
  Spinner,
  StatusPill,
  fmtMs,
  fmtNum,
  fmtPct
} from '../components/ui.jsx'

const MODELS = [
  { value: 'accio-mini', label: 'accio-mini — fast default' },
  { value: 'accio-pro', label: 'accio-pro — deeper reasoning' },
  { value: 'quality-rag', label: 'quality-rag — retrieval over test docs' }
]

const PROMPTS = [
  'What is the current API p95 latency?',
  'Which suite covers database integrity?',
  'Summarise the last load test',
  'How do quality gates block a release?'
]

/**
 * The demo AI application under test. Chat is persisted server-side, so the
 * transcript survives a reload and the SQL integrity checks have real rows.
 */
export default function Chatbot() {
  const overview = useFetch(() => api('/api/demo/overview'))
  const evaluations = useFetch(() => api('/api/demo/evaluations?limit=8'))

  const [model, setModel] = useState('accio-mini')
  const [conversationId, setConversationId] = useState('')
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [lastLatency, setLastLatency] = useState(null)

  const windowRef = useRef(null)

  useEffect(() => {
    const node = windowRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages])

  async function send(text) {
    const content = (text ?? draft).trim()
    if (!content || sending) return
    setSending(true)
    setError('')
    const optimistic = {
      id: `local-${Date.now()}`,
      role: 'user',
      content,
      model,
      latency_ms: 0,
      flagged: false,
      created_at: new Date().toISOString()
    }
    setMessages((prev) => [...prev, optimistic])
    setDraft('')
    try {
      const reply = await api('/api/chat', {
        method: 'POST',
        body: { message: content, model, conversation_id: conversationId }
      })
      setConversationId(reply.conversation_id)
      setMessages(reply.messages)
      setLastLatency(reply.latency_ms)
      overview.reload()
      evaluations.reload()
    } catch (err) {
      setError(err.message)
      setMessages((prev) => prev.filter((item) => item.id !== optimistic.id))
    } finally {
      setSending(false)
    }
  }

  async function score(message, value) {
    setError('')
    try {
      await api('/api/demo/evaluations', {
        method: 'POST',
        body: {
          prompt: message.content.slice(0, 2000),
          score: value,
          model: message.model || model,
          conversation_id: conversationId,
          reviewer: 'qa@example.com'
        }
      })
      evaluations.reload()
      overview.reload()
    } catch (err) {
      setError(err.message)
    }
  }

  function reset() {
    setConversationId('')
    setMessages([])
    setLastLatency(null)
    setError('')
  }

  if (overview.loading && !overview.data) return <Spinner label="Loading demo AI application…" />

  const data = overview.data || {}
  const evals = evaluations.data || []

  const evalColumns = [
    { key: 'prompt', header: 'Prompt', render: (row) => <span className="truncate">{row.prompt}</span> },
    { key: 'model', header: 'Model' },
    { key: 'score', header: 'Score', align: 'right', render: (row) => `${row.score}/100` },
    { key: 'verdict', header: 'Verdict', render: (row) => <StatusPill status={row.verdict} /> },
    { key: 'reviewer', header: 'Reviewer' }
  ]

  return (
    <>
      <PageHeader
        title="Demo AI application"
        subtitle="The application under test: guard-railed assistant with persisted conversations, latency telemetry and human evaluation scores."
        actions={
          <>
            <button type="button" className="btn btn-ghost" onClick={reset} data-testid="chat-reset">
              New conversation
            </button>
            <button type="button" className="btn btn-ghost" onClick={overview.reload}>
              Refresh
            </button>
          </>
        }
      />

      <ErrorBanner error={overview.error} onRetry={overview.reload} />

      <div className="kpi-grid">
        <Kpi label="Conversations" value={fmtNum(data.total_conversations ?? 0)} sub={`${fmtNum(data.total_messages ?? 0)} messages`} />
        <Kpi label="Avg response" value={fmtMs(data.avg_latency_ms ?? 0)} sub="Assistant latency" tone="violet" />
        <Kpi
          label="Guardrail success"
          value={fmtPct(data.success_rate ?? 100, 2)}
          sub={`${fmtNum(data.flagged_messages ?? 0)} flagged`}
          tone={(data.flagged_messages ?? 0) > 0 ? 'amber' : 'green'}
        />
        <Kpi label="Avg eval score" value={Number(data.avg_eval_score ?? 0).toFixed(0)} sub={`${fmtNum(data.evaluations ?? 0)} evaluations`} />
      </div>

      <div className="chat-shell">
        <Card
          title="Chat with the assistant"
          subtitle="Try the guardrail: ask it to reveal its system prompt and watch the response get flagged."
          actions={
            <select
              aria-label="Model"
              data-testid="chat-model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              style={{ width: 210 }}
            >
              {MODELS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          }
        >
          <div className="chat-window" ref={windowRef} data-testid="chat-window">
            {messages.length === 0 && (
              <p className="empty">
                No messages yet in this conversation. Pick a suggested prompt below or type your own.
              </p>
            )}
            {messages.map((message) => {
              const isUser = message.role === 'user'
              return (
                <div
                  key={message.id}
                  className={`bubble ${isUser ? 'bubble-user' : 'bubble-bot'}`}
                  data-testid={isUser ? 'chat-user-message' : 'chat-bot-message'}
                >
                  {message.content}
                  <div className="bubble-meta">
                    {isUser ? 'you' : message.model || 'assistant'}
                    {!isUser && message.latency_ms ? ` · ${message.latency_ms} ms` : ''}
                    {message.flagged && (
                      <>
                        {' · '}
                        <span className="pill pill-amber" data-testid="guardrail-flag">
                          guardrail
                        </span>
                      </>
                    )}
                  </div>
                  {!isUser && conversationId && (
                    <div className="inline" style={{ marginTop: 6 }}>
                      <button type="button" className="btn btn-sm btn-ghost" onClick={() => score(message, 90)}>
                        Score 90
                      </button>
                      <button type="button" className="btn btn-sm btn-ghost" onClick={() => score(message, 60)}>
                        Score 60
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
            {sending && <p className="dim small">Assistant is thinking…</p>}
          </div>

          <ErrorBanner error={error} />

          <div className="inline" style={{ marginTop: 10 }}>
            {PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => send(prompt)}
                disabled={sending}
              >
                {prompt}
              </button>
            ))}
          </div>

          <form
            className="chat-input"
            onSubmit={(event) => {
              event.preventDefault()
              send()
            }}
          >
            <textarea
              data-testid="chat-input"
              placeholder="Ask about tests, gates, latency or data validation…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  send()
                }
              }}
            />
            <button className="btn btn-primary" type="submit" data-testid="chat-send" disabled={sending || !draft.trim()}>
              {sending ? 'Sending…' : 'Send'}
            </button>
          </form>
          <p className="small dim" style={{ marginTop: 8 }}>
            {conversationId ? `conversation_id: ${conversationId}` : 'A new conversation_id is created on the first message.'}
            {lastLatency !== null ? ` · last reply ${lastLatency} ms` : ''}
          </p>
        </Card>

        <div className="stack">
          <Card title="Recent conversations" subtitle="Persisted in SQLite — the SQL integrity checks read these rows.">
            {(data.conversations || []).length === 0 ? (
              <p className="empty">No conversations yet.</p>
            ) : (
              <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {(data.conversations || []).map((conv) => (
                  <li key={conv.conversation_id}>
                    <button
                      type="button"
                      className="btn btn-ghost btn-block"
                      style={{ textAlign: 'left' }}
                      onClick={async () => {
                        try {
                          const detail = await api(`/api/chat/${encodeURIComponent(conv.conversation_id)}`)
                          setConversationId(detail.conversation_id)
                          setMessages(detail.messages)
                        } catch (err) {
                          setError(err.message)
                        }
                      }}
                    >
                      <span className="mono-sm">{conv.conversation_id}</span>
                      <span className="dim small" style={{ display: 'block' }}>
                        {conv.preview}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <Card
        title="Human evaluation scores"
        subtitle="Feeds `db.eval.score_range` and the integrity checks on the data-quality page."
        padded={false}
      >
        <DataTable
          columns={evalColumns}
          rows={evals}
          rowKey={(row) => row.id}
          empty="No evaluations recorded."
          dense
        />
      </Card>
    </>
  )
}
