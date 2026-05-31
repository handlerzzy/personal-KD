import { ref } from 'vue'
import type { Conversation, Message } from '../types'
import * as api from '../api'

export function useConversation() {
  const conversations = ref<Conversation[]>([])
  const currentConv = ref<Conversation | null>(null)
  const messages = ref<Message[]>([])
  const loading = ref(false)

  async function fetchConversations(kbId: string) {
    if (!kbId) return
    loading.value = true
    try {
      conversations.value = await api.getConversations(kbId)
    } catch (e: any) {
      console.error('Failed to fetch conversations:', e)
    } finally {
      loading.value = false
    }
  }

  async function createConversation(kbId: string, title = '新对话') {
    const conv = await api.createConversation(kbId, title)
    conversations.value.unshift(conv)
    currentConv.value = conv
    messages.value = []
    return conv
  }

  async function deleteConversation(kbId: string, convId: string) {
    await api.deleteConversation(kbId, convId)
    conversations.value = conversations.value.filter(c => c.id !== convId)
    if (currentConv.value?.id === convId) {
      currentConv.value = conversations.value[0] || null
      if (currentConv.value) {
        await fetchMessages(kbId, currentConv.value.id)
      } else {
        messages.value = []
      }
    }
  }

  function selectConversation(conv: Conversation) {
    currentConv.value = conv
  }

  async function fetchMessages(kbId: string, convId: string) {
    if (!kbId || !convId) return
    loading.value = true
    try {
      messages.value = await api.getMessages(kbId, convId)
    } catch (e: any) {
      console.error('Failed to fetch messages:', e)
    } finally {
      loading.value = false
    }
  }

  return {
    conversations, currentConv, messages, loading,
    fetchConversations, createConversation, deleteConversation,
    selectConversation, fetchMessages,
  }
}
