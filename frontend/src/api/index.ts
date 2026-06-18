import type { KnowledgeBase, KBDocument, Conversation, Message, User, TokenResponse } from '../types'

const BASE = '/api'

// Token management
let accessToken: string | null = localStorage.getItem('access_token')
let refreshToken: string | null = localStorage.getItem('refresh_token')

export function setTokens(access: string, refresh: string) {
  accessToken = access
  refreshToken = refresh
  localStorage.setItem('access_token', access)
  localStorage.setItem('refresh_token', refresh)
}

export function clearTokens() {
  accessToken = null
  refreshToken = null
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export function getAccessToken(): string | null {
  return accessToken
}

async function requestJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...opts?.headers as Record<string, string>,
  }

  // Add Authorization header if token exists
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`
  }

  const fetchOpts: RequestInit = {
    ...opts,
    headers,
  }

  const res = await fetch(`${BASE}${url}`, fetchOpts)

  // Handle 401 - try to refresh token
  if (res.status === 401 && refreshToken) {
    const refreshed = await tryRefreshToken()
    if (refreshed) {
      // Retry original request with new token
      headers['Authorization'] = `Bearer ${accessToken}`
      const retryRes = await fetch(`${BASE}${url}`, { ...fetchOpts, headers })
      if (!retryRes.ok) {
        const text = await retryRes.text().catch(() => '')
        throw new Error(`HTTP ${retryRes.status}: ${text || retryRes.statusText}`)
      }
      return retryRes.json()
    }
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`)
  }
  return res.json()
}

let refreshPromise: Promise<boolean> | null = null

async function tryRefreshToken(): Promise<boolean> {
  if (!refreshToken) return false

  // If a refresh is already in flight, reuse it (prevents concurrent refresh races)
  if (refreshPromise) return refreshPromise

  refreshPromise = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })

      if (res.ok) {
        const data: TokenResponse = await res.json()
        setTokens(data.access_token, data.refresh_token)
        return true
      } else {
        clearTokens()
        return false
      }
    } catch {
      clearTokens()
      return false
    }
  })()

  const result = await refreshPromise
  refreshPromise = null
  return result
}

async function requestRaw(url: string, opts?: RequestInit): Promise<Response> {
  // Don't set Content-Type for FormData - browser sets it automatically with boundary
  const isFormData = opts?.body instanceof FormData
  const headers: Record<string, string> = isFormData
    ? {}
    : { ...(opts?.headers as Record<string, string>) }

  // Add Authorization header if token exists
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`
  }

  const fetchOpts: RequestInit = {
    ...opts,
    headers,
  }

  const res = await fetch(`${BASE}${url}`, fetchOpts)

  // Handle 401 - try to refresh token
  if (res.status === 401 && refreshToken) {
    const refreshed = await tryRefreshToken()
    if (refreshed) {
      // Retry original request with new token
      headers['Authorization'] = `Bearer ${accessToken}`
      const retryRes = await fetch(`${BASE}${url}`, { ...fetchOpts, headers })
      if (!retryRes.ok) {
        const text = await retryRes.text().catch(() => '')
        throw new Error(`HTTP ${retryRes.status}: ${text || retryRes.statusText}`)
      }
      return retryRes
    }
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`)
  }
  return res
}

// Auth
export function register(username: string, password: string): Promise<User> {
  return requestJson('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function login(username: string, password: string, rememberMe = false): Promise<TokenResponse> {
  return requestJson('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password, remember_me: rememberMe }),
  })
}

export function logout(): Promise<void> {
  return requestJson('/auth/logout', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
}

export function getCurrentUser(): Promise<User> {
  return requestJson('/auth/me')
}

export function updateCurrentUser(email?: string): Promise<User> {
  return requestJson('/auth/me', {
    method: 'PUT',
    body: JSON.stringify({ email }),
  })
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await requestJson('/auth/password', {
    method: 'PUT',
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  })
  // Password change invalidates all tokens (token_version incremented on server)
  clearTokens()
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

export function updateConversationTitle(kbId: string, convId: string, title: string): Promise<Conversation> {
  return requestJson(`/knowledge-bases/${kbId}/conversations/${convId}`, {
    method: 'PUT',
    body: JSON.stringify({ title }),
  })
}

export function togglePinConversation(kbId: string, convId: string): Promise<Conversation> {
  return requestJson(`/knowledge-bases/${kbId}/conversations/${convId}/pin`, {
    method: 'PATCH',
  })
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

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`
  }

  fetch(`${BASE}/knowledge-bases/${kbId}/conversations/${convId}/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query }),
    signal: controller.signal,
  }).then(async (initialRes) => {
    let res = initialRes
    // Handle 401 - try to refresh token and retry once
    if (res.status === 401 && refreshToken) {
      const refreshed = await tryRefreshToken()
      if (refreshed) {
        headers['Authorization'] = `Bearer ${accessToken}`
        res = await fetch(`${BASE}/knowledge-bases/${kbId}/conversations/${convId}/chat`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ query }),
          signal: controller.signal,
        })
      }
    }
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
            let parsed: any
            try {
              parsed = JSON.parse(data)
            } catch (e) {
              console.warn('SSE JSON parse error:', data)
              continue
            }
            onEvent(eventType, data)
          }
          eventType = ''
        }
      }
    }

    // Stream fully consumed - call onDone() here so title_update events are processed
    onDone()
  }).catch((err) => {
    if (err.name === 'AbortError') {
      // User cancelled — resolve cleanly so useChat Promise settles
      onDone()
    } else {
      onError(err)
    }
  })

  return controller
}
