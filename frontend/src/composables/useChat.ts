import { ref } from 'vue'
import type { Message, Source } from '../types'
import * as api from '../api'

export function useChat() {
  const streaming = ref(false)
  const searching = ref(false)
  const currentReasoning = ref('')
  const currentAnswer = ref('')
  const currentSources = ref<Source[]>([])
  const newTitle = ref<string | null>(null)
  let abortController: AbortController | null = null
  let streamResolve: (() => void) | null = null

  async function sendMessage(kbId: string, convId: string, query: string, messages: Message[]) {
    streaming.value = true
    searching.value = false  // 不立即显示检索状态，等待后端事件
    currentReasoning.value = ''
    currentAnswer.value = ''
    currentSources.value = []
    newTitle.value = null

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
              searching.value = false
              currentReasoning.value += parsed.token || ''
              break
            case 'answer':
              searching.value = false
              currentAnswer.value += parsed.token || ''
              break
            case 'user_message':
              // User message echoed from backend for immediate display
              break
            case 'sources':
              currentSources.value = parsed.sources || []
              break
            case 'searching':
              // 后端明确通知检索开始
              searching.value = true
              break
            case 'title_update':
              newTitle.value = parsed.title || null
              break
            case 'error':
              console.error('Server error:', parsed.message)
              streaming.value = false
              searching.value = false
              streamResolve?.()
              break
          }
        },
        (err) => {
          console.error('Chat error:', err)
          streaming.value = false
          searching.value = false
          streamResolve?.()
        },
        () => {
          streaming.value = false
          searching.value = false
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
    searching.value = false
    newTitle.value = null  // 防止旧标题泄露到新对话
    streamResolve?.()
  }

  return {
    streaming, searching, currentReasoning, currentAnswer, currentSources, newTitle,
    sendMessage, cancelStream,
  }
}
