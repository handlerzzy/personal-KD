import { ref } from 'vue'
import type { Source } from '../types'
import * as api from '../api'

export function useChat() {
  const streaming = ref(false)
  const currentReasoning = ref('')
  const currentAnswer = ref('')
  const currentSources = ref<Source[]>([])
  let abortController: AbortController | null = null

  async function sendMessage(kbId: string, convId: string, query: string) {
    streaming.value = true
    currentReasoning.value = ''
    currentAnswer.value = ''
    currentSources.value = []

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
        }
      },
      (err) => {
        console.error('Chat error:', err)
        streaming.value = false
      },
      () => {
        streaming.value = false
      },
    )
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
