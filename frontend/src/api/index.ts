import type { KnowledgeBase, KBDocument, Conversation, Message } from '../types'

const BASE = '/api'

async function requestJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`)
  }
  return res.json()
}

async function requestRaw(url: string, opts?: RequestInit): Promise<Response> {
  const res = await fetch(`${BASE}${url}`, opts)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`)
  }
  return res
}

// Knowledge Bases
export function getKnowledgeBases(): Promise<KnowledgeBase[]> {
  return requestJson('/knowledge-bases')
}

export function createKnowledgeBase(name: string, description = ''): Promise<KnowledgeBase> {
  return requestJson('/knowledge-bases', {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  })
}

export function deleteKnowledgeBase(id: string): Promise<void> {
  return requestJson(`/knowledge-bases/${id}`, { method: 'DELETE' })
}

// Documents
export function getDocuments(kbId: string): Promise<KBDocument[]> {
  return requestJson(`/knowledge-bases/${kbId}/documents`)
}

export function uploadDocument(kbId: string, file: File): Promise<KBDocument> {
  const form = new FormData()
  form.append('file', file)
  return requestRaw(`/knowledge-bases/${kbId}/documents`, {
    method: 'POST',
    body: form,
  }).then(r => r.json())
}

export function deleteDocument(kbId: string, docId: string): Promise<void> {
  return requestJson(`/knowledge-bases/${kbId}/documents/${docId}`, { method: 'DELETE' })
}

// Conversations
export function getConversations(kbId: string): Promise<Conversation[]> {
  return requestJson(`/knowledge-bases/${kbId}/conversations`)
}

export function createConversation(kbId: string, title = '新对话'): Promise<Conversation> {
  return requestJson(`/knowledge-bases/${kbId}/conversations`, {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export function deleteConversation(kbId: string, convId: string): Promise<void> {
  return requestJson(`/knowledge-bases/${kbId}/conversations/${convId}`, { method: 'DELETE' })
}

// Messages
export function getMessages(kbId: string, convId: string): Promise<Message[]> {
  return requestJson(`/knowledge-bases/${kbId}/conversations/${convId}/messages`)
}

// Chat (SSE streaming via POST)
export function chatStream(
  kbId: string,
  convId: string,
  query: string,
  onEvent: (event: string, data: string) => void,
  onError: (err: Error) => void,
  onDone: () => void,
): AbortController {
  const controller = new AbortController()

  fetch(`${BASE}/knowledge-bases/${kbId}/conversations/${convId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      onError(new Error(`HTTP ${res.status}: ${text}`))
      return
    }

    const reader = res.body?.getReader()
    if (!reader) {
      onError(new Error('No response body'))
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let eventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const data = line.slice(6).trim()
          if (eventType) {
            onEvent(eventType, data)
            if (eventType === 'done') onDone()
          }
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') onError(err)
  })

  return controller
}
