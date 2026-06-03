import { ref } from 'vue'
import type { Source } from '../types'
import * as api from '../api'

export function useChat() {
  const streaming = ref(false)
  const currentReasoning = ref('')
  const currentAnswer = ref('')
  const currentSources = ref<Source[]>([])
  let abortController: AbortController | null = null
  let streamResolve: (() => void) | null = null

  async function sendMessage(kbId: string, convId: string, query: string, messages: any[]) {
    streaming.value = true
    currentReasoning.value = ''
    currentAnswer.value = ''
    currentSources.value = []

    // 立即显示用户消息（乐观更新）
    messages.push({
      id: 'temp-' + Date.now(),
      conversation_id: convId,
      role: 'user',
      content: query,
      reasoning_content: '',
      created_at: new Date().toISOString(),
    })

    return new Promise<void>((resolve) => {
      streamResolve = resolve
      abortController = api.chatStream(
        kbId,
        convId,
        query,
        (event, data) => {
          const parsed = JSON.parse(data)
          switch (event) {
            case 'reasoning':
              currentReasoning.value += parsed.token || ''
              break
            case 'answer':
              currentAnswer.value += parsed.token || ''
              break
            case 'sources':
              currentSources.value = parsed.sources || []
              break
            case 'error':
              console.error('Server error:', parsed.message)
              streaming.value = false
              streamResolve?.()
              break
          }
        },
        (err) => {
          console.error('Chat error:', err)
          streaming.value = false
          streamResolve?.()
        },
        () => {
          streaming.value = false
          streamResolve?.()
        },
      )
    })
  }

  function cancelStream() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    streaming.value = false
  }

  return {
    streaming, currentReasoning, currentAnswer, currentSources,
    sendMessage, cancelStream,
  }
}
