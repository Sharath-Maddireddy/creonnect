# Creo Intelligence — Frontend Integration Guide

> **For:** Frontend Engineer
> **Feature:** Creo Intelligence (`brand.creonnect.com/ai-builder`)
> **Covers:** Quick-action chips UI + Backend API wiring (SSE streaming + session management)

---

## Visual Mockup

![Creo Intelligence UI Mockup](C:\Users\ASUS\.gemini\antigravity-ide\brain\06036240-92be-4553-a072-a6101083a625\creo_intelligence_mockup_1784365247113.png)

---

## Part 1 — Quick Action Chips UI

### What to build

Add **8 ChatGPT-style quick-action chips** to the Creo Intelligence empty state — the screen shown when `messages.length === 0`. Placed **between the chat input box and the existing "TRY A PROMPT" section**.

When clicked, a chip **pre-fills the textarea** with a prompt starter and **focuses it** — the user edits and hits send, exactly like ChatGPT.

---

### Layout

```
┌──────────────────────────────────────────────────────┐
│         How can I help you today?                    │
│  I can help you plan campaigns, find creators...     │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │ Message Creo...                        ⬆    │    │
│  │ 📎  ⚡ ACTIONS ▼                             │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  [🔍 Find Creators]   [📋 Plan a Campaign]    │  │  ← NEW
│  │  [📊 Review Results]  [💡 Content Ideas]      │  │  ← NEW
│  │  [👤 Analyze Creator] [✉️ Draft Outreach]     │  │  ← NEW
│  │  [📈 Benchmark]       [💰 Budget Allocation]  │  │  ← NEW
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  TRY A PROMPT                                        │
│  [Tech reviewers in India...]  [Gen Z fashion...]    │
│  [Eco-friendly lifestyle...]   [Micro-creators...]   │
└──────────────────────────────────────────────────────┘
```

---

### Step 1 — Quick Actions Data File

Create `src/data/creoQuickActions.js`:

```js
export const CREO_QUICK_ACTIONS = [
  {
    id: 'find-creators',
    icon: '🔍',
    label: 'Find Creators',
    description: 'Discover creators by niche, location, or follower range',
    prompt: 'Find creators for my brand. I\'m looking for ',
  },
  {
    id: 'plan-campaign',
    icon: '📋',
    label: 'Plan a Campaign',
    description: 'Set goals, budget, and timeline for a new campaign',
    prompt: 'Help me plan a new influencer campaign. My brand is ',
  },
  {
    id: 'review-results',
    icon: '📊',
    label: 'Review Results',
    description: 'Analyze performance of an active or past campaign',
    prompt: 'Review the results of my campaign. Here\'s what I know: ',
  },
  {
    id: 'content-ideas',
    icon: '💡',
    label: 'Content Ideas',
    description: 'Generate post ideas and hooks for a brand brief',
    prompt: 'Generate content ideas for my brand brief. My product is ',
  },
  {
    id: 'analyze-creator',
    icon: '👤',
    label: 'Analyze Creator',
    description: 'Deep-dive on a specific creator\'s metrics and brand fit',
    prompt: 'Analyze this creator profile for me: ',
  },
  {
    id: 'draft-outreach',
    icon: '✉️',
    label: 'Draft Outreach',
    description: 'Write a personalized message to a creator',
    prompt: 'Write an outreach message to a creator for my campaign. My brand is ',
  },
  {
    id: 'benchmark',
    icon: '📈',
    label: 'Benchmark Performance',
    description: 'Compare campaign metrics to industry standards',
    prompt: 'Benchmark my campaign performance. Here are my metrics: ',
  },
  {
    id: 'budget-allocation',
    icon: '💰',
    label: 'Budget Allocation',
    description: 'Recommend how to split budget across creators',
    prompt: 'Help me allocate my influencer marketing budget. My total budget is ',
  },
]
```

---

### Step 2 — React Component

Create `src/components/CreoIntelligence/CreoQuickActions.jsx`:

```jsx
import { useState } from 'react'
import { CREO_QUICK_ACTIONS } from '../../data/creoQuickActions'
import './creo-quick-actions.css'

/**
 * ChatGPT-style quick action chips for Creo Intelligence.
 *
 * Props:
 *   onSelect(prompt: string) — called when a chip is clicked.
 *                              Parent should set this as the chat input value
 *                              and focus the textarea.
 */
export function CreoQuickActions({ onSelect }) {
  const [hoveredId, setHoveredId] = useState(null)

  return (
    <div className="creo-quick-actions">
      <div className="creo-quick-actions__grid">
        {CREO_QUICK_ACTIONS.map((action) => (
          <button
            key={action.id}
            id={`quick-action-${action.id}`}
            className={`creo-quick-action-chip${hoveredId === action.id ? ' creo-quick-action-chip--hovered' : ''}`}
            onClick={() => onSelect(action.prompt)}
            onMouseEnter={() => setHoveredId(action.id)}
            onMouseLeave={() => setHoveredId(null)}
            type="button"
            aria-label={action.description}
            title={action.description}
          >
            <span className="creo-quick-action-chip__icon" aria-hidden="true">
              {action.icon}
            </span>
            <span className="creo-quick-action-chip__label">{action.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
```

---

### Step 3 — CSS Styles

Create `src/components/CreoIntelligence/creo-quick-actions.css`:

```css
/* ── Creo Quick Actions ──────────────────────────────────────── */

.creo-quick-actions {
  width: 100%;
  max-width: 680px;
  margin: 16px auto 8px;
}

.creo-quick-actions__grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

@media (max-width: 768px) {
  .creo-quick-actions__grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .creo-quick-actions__grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
  }
}

.creo-quick-action-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  cursor: pointer;
  text-align: left;
  transition:
    background 0.18s ease,
    border-color 0.18s ease,
    transform 0.15s ease,
    box-shadow 0.18s ease;
  font-family: inherit;
  white-space: nowrap;
  overflow: hidden;
}

.creo-quick-action-chip:hover,
.creo-quick-action-chip--hovered {
  background: rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.45);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.18);
}

.creo-quick-action-chip:active {
  transform: translateY(0);
  box-shadow: none;
}

.creo-quick-action-chip__icon {
  font-size: 15px;
  flex-shrink: 0;
  line-height: 1;
}

.creo-quick-action-chip__label {
  font-size: 13px;
  font-weight: 500;
  color: #d1d5db;
  overflow: hidden;
  text-overflow: ellipsis;
}

.creo-quick-action-chip:hover .creo-quick-action-chip__label,
.creo-quick-action-chip--hovered .creo-quick-action-chip__label {
  color: #ffffff;
}

/* Light mode */
.light-theme .creo-quick-action-chip {
  background: rgba(0, 0, 0, 0.04);
  border-color: rgba(0, 0, 0, 0.1);
}
.light-theme .creo-quick-action-chip:hover {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.35);
}
.light-theme .creo-quick-action-chip__label {
  color: #374151;
}
.light-theme .creo-quick-action-chip:hover .creo-quick-action-chip__label {
  color: #111827;
}
```

---

### Step 4 — Integrate into the Creo Intelligence Page

In your existing Creo Intelligence page (the one with `"Message Creo..."` input), make these changes:

#### 4a. Add a ref + handler

```jsx
import { useRef } from 'react'
import { CreoQuickActions } from '../components/CreoIntelligence/CreoQuickActions'

// Inside your component:
const textareaRef = useRef(null)

// Called when user clicks a quick-action chip
const handleQuickActionSelect = (prompt) => {
  setInputValue(prompt)           // your existing state setter for the textarea
  textareaRef.current?.focus()

  // Move cursor to end so user can type right after the prompt
  requestAnimationFrame(() => {
    const el = textareaRef.current
    if (el) {
      el.selectionStart = el.value.length
      el.selectionEnd = el.value.length
    }
  })
}
```

> **Note:** Replace `setInputValue` / `inputValue` with your actual state variable name (could be `message`, `query`, `userInput`, etc.)

#### 4b. Add `ref` to your textarea

```jsx
<textarea
  ref={textareaRef}
  value={inputValue}
  onChange={(e) => setInputValue(e.target.value)}
  placeholder="Message Creo..."
  // ... your existing props
/>
```

#### 4c. Add the chips + wire the API in the empty state JSX

```jsx
{messages.length === 0 && (
  <>
    {/* Quick action chips — above TRY A PROMPT */}
    <CreoQuickActions onSelect={handleQuickActionSelect} />
  </>
)}
```

---

---

## Part 2 — Backend API Integration

### Base URL

```
https://api.creonnect.com   (production)
http://localhost:8000        (local dev)
```

### Authentication

All endpoints require the header:

```
X-API-Key: <your BRAND_API_KEY>
```

---

### Endpoint 1 — Chat (SSE Streaming)

```
POST /api/creo-intelligence/chat
Content-Type: application/json
X-API-Key: <key>
Accept: text/event-stream
```

#### Request Body

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Find tech creators in Mumbai with 50k+ followers",
  "brand_name": "MyBrand"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `session_id` | string | ✅ | Generate a UUID on the frontend. Persists across messages in the same conversation. |
| `message` | string | ✅ | Min 2 chars, max 2000 chars |
| `brand_name` | string | ❌ | Prepended as context for the AI. Pass your brand name here. |

#### SSE Event Types

The response is a **Server-Sent Events stream**. Events arrive in this order:

```
event: tool_call
data: {"tool": "search_creator_pool", "args": {"niche": "tech", "min_followers": 50000}}

event: tool_call
data: {"tool": "score_creator_brand_fit", "args": {"account_id": "techguru_india", "brand_niche": "tech"}}

event: token
data: {"token": "Based"}

event: token
data: {"token": " on"}

event: token
data: {"token": " your"}

... (one event per token)

event: done
data: {"tool_calls_made": [...], "session_id": "550e8400-...", "latency_ms": 3241.5}
```

| Event | When emitted | Payload |
|-------|-------------|---------|
| `tool_call` | Each time AI uses a tool (0 or more) | `{tool, args}` |
| `token` | Each streamed response token | `{token}` |
| `done` | After last token | `{tool_calls_made, session_id, latency_ms}` |
| `error` | On failure | `{detail}` — stream closes after this |

#### Rate Limit

**20 requests per minute** per API key. Returns `429` when exceeded.

---

#### Complete Implementation Example

```jsx
// creoIntelligenceApi.js

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000'
const API_KEY  = process.env.REACT_APP_BRAND_API_KEY

/**
 * Send a message to Creo Intelligence and stream the response.
 *
 * @param {object}   opts
 * @param {string}   opts.sessionId        - UUID for this conversation
 * @param {string}   opts.message          - User's message text
 * @param {string}   [opts.brandName]      - Optional brand name
 * @param {Function} opts.onToken          - Called with each streamed token string
 * @param {Function} opts.onToolCall       - Called with { tool, args } for each tool used
 * @param {Function} opts.onDone           - Called with { tool_calls_made, latency_ms } when complete
 * @param {Function} opts.onError          - Called with error detail string
 */
export async function sendCreoMessage({
  sessionId,
  message,
  brandName,
  onToken,
  onToolCall,
  onDone,
  onError,
}) {
  let response
  try {
    response = await fetch(`${API_BASE}/api/creo-intelligence/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        brand_name: brandName || undefined,
      }),
    })
  } catch (err) {
    onError?.('Network error. Please check your connection.')
    return
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    onError?.(`Request failed (${response.status}): ${text}`)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''   // keep the incomplete last chunk

    for (const part of parts) {
      if (!part.trim()) continue

      // Parse SSE event
      const eventMatch = part.match(/^event: (.+)$/m)
      const dataMatch  = part.match(/^data: (.+)$/ms)

      const eventType = eventMatch?.[1]?.trim()
      const rawData   = dataMatch?.[1]?.trim()
      if (!eventType || !rawData) continue

      let payload
      try {
        payload = JSON.parse(rawData)
      } catch {
        continue
      }

      if (eventType === 'token')     onToken?.(payload.token)
      if (eventType === 'tool_call') onToolCall?.(payload)
      if (eventType === 'done')      onDone?.(payload)
      if (eventType === 'error')     onError?.(payload.detail)
    }
  }
}
```

#### Usage in Your Component

```jsx
import { useState, useRef } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { sendCreoMessage } from '../api/creoIntelligenceApi'

function CreoIntelligencePage() {
  // Generate once per page load / "New Chat" click
  const sessionIdRef = useRef(uuidv4())

  const [messages, setMessages]       = useState([])
  const [inputValue, setInputValue]   = useState('')
  const [isStreaming, setIsStreaming]  = useState(false)
  const [activeTools, setActiveTools] = useState([])
  const textareaRef = useRef(null)

  const handleSend = async () => {
    if (!inputValue.trim() || isStreaming) return

    const userMessage = inputValue.trim()
    setInputValue('')
    setIsStreaming(true)
    setActiveTools([])

    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])

    // Add empty assistant message that we'll fill in
    let assistantContent = ''
    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

    await sendCreoMessage({
      sessionId:  sessionIdRef.current,
      message:    userMessage,
      brandName:  'YourBrand',   // pass from context/props

      onToken: (token) => {
        assistantContent += token
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'assistant', content: assistantContent }
          return updated
        })
      },

      onToolCall: ({ tool, args }) => {
        setActiveTools(prev => [...prev, { tool, args }])
      },

      onDone: ({ latency_ms }) => {
        setIsStreaming(false)
        setActiveTools([])
        console.log(`Response completed in ${latency_ms}ms`)
      },

      onError: (detail) => {
        setIsStreaming(false)
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `Sorry, something went wrong: ${detail}`,
          isError: true,
        }])
      },
    })
  }

  // Quick action chip handler
  const handleQuickActionSelect = (prompt) => {
    setInputValue(prompt)
    textareaRef.current?.focus()
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (el) {
        el.selectionStart = el.value.length
        el.selectionEnd = el.value.length
      }
    })
  }

  // ... render
}
```

---

### Endpoint 2 — Clear Session (New Chat)

```
DELETE /api/creo-intelligence/session/{session_id}
X-API-Key: <key>
```

Call this when the user clicks **"New Chat"** to wipe the conversation history from Redis. Then generate a fresh `session_id` on the frontend.

#### Response

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "deleted": true,
  "detail": "Session cleared."
}
```

#### Implementation

```js
export async function clearCreoSession(sessionId) {
  await fetch(`${API_BASE}/api/creo-intelligence/session/${sessionId}`, {
    method: 'DELETE',
    headers: { 'X-API-Key': API_KEY },
  })
}

// Usage — "New Chat" button handler:
const handleNewChat = async () => {
  await clearCreoSession(sessionIdRef.current)
  sessionIdRef.current = uuidv4()   // generate fresh session ID
  setMessages([])
  setInputValue('')
}
```

---

### Showing Tool Activity (Optional but Recommended)

While the AI is using tools (between first `tool_call` and first `token`), show a loading indicator. This bridges the ~2–4 second gap while the AI runs searches.

```jsx
// Show which tools are being used
{isStreaming && activeTools.length > 0 && (
  <div className="creo-tool-activity">
    {activeTools.map((tc, i) => (
      <span key={i} className="creo-tool-badge">
        🔧 {tc.tool.replace(/_/g, ' ')}
      </span>
    ))}
  </div>
)}

// Or a simple "Thinking..." indicator
{isStreaming && activeTools.length === 0 && (
  <div className="creo-thinking">
    <span className="creo-thinking-dot" />
    <span className="creo-thinking-dot" />
    <span className="creo-thinking-dot" />
  </div>
)}
```

---

## Part 3 — File Structure

```
src/
  data/
    creoQuickActions.js              ← [NEW] Quick action data array
  components/
    CreoIntelligence/
      CreoQuickActions.jsx           ← [NEW] Chip grid component
      creo-quick-actions.css         ← [NEW] Chip styles
  api/
    creoIntelligenceApi.js           ← [NEW] sendCreoMessage + clearCreoSession
  pages/
    CreoIntelligence.jsx             ← [EDIT] Add ref, handler, chips, API wiring
```

---

## Part 4 — Environment Variables

Add to your `.env`:

```env
REACT_APP_API_URL=https://api.creonnect.com
REACT_APP_BRAND_API_KEY=<your key from backend team>
```

---

## Part 5 — Behaviour Summary

| Action | Behaviour |
|--------|-----------|
| Empty state (`messages.length === 0`) | Show quick-action chips + "TRY A PROMPT" |
| Click a chip | Pre-fills textarea with prompt starter, focuses input |
| User edits + sends | Normal send flow — same as typing manually |
| Conversation active | Chips and "TRY A PROMPT" hide |
| AI uses tools | Show `tool_call` events as loading badge (optional) |
| AI responds | Stream `token` events into the last message bubble |
| `done` event | Hide loading, store `latency_ms` for analytics if needed |
| `error` event | Show error message in chat, re-enable input |
| "New Chat" click | `DELETE /session/{id}` → generate new UUID → reset state |
| Page reload | Frontend generates new `session_id` automatically |

---

## Part 6 — Session Rules

| Rule | Value |
|------|-------|
| Session TTL | **4 hours** from last message (sliding) |
| Max messages stored | **50** (oldest trimmed automatically) |
| Cross-device / load-balancer | ✅ Redis-backed, works across server instances |
| Session format | Any string ≤ 128 chars, no spaces/newlines. Use UUID v4. |
