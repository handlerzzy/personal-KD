import { ref } from 'vue'
import type { Conversation, Message } from '../types'
import * as api from '../api'

export function useConversation() {
  const conversations = ref<Conversation[]>([])
  const currentConv = ref<Conversation | null>(null)
  const messages = ref<Message[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchConversations(kbId: string) {
    if (!kbId) return
    loading.value = true
    error.value = null
    try {
      conversations.value = await api.getConversations(kbId)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '获取对话列表失败'
      error.value = msg
      console.error('Failed to fetch conversations:', e)
    } finally {
      loading.value = false
    }
  }

  async function createConversation(kbId: string, title = '新对话') {
    const conv = await api.createConversation(kbId, title)
    conversations.value.unshift(conv)
    currentConv.value = conv
    messages.value.splice(0)  // Clear array in-place to preserve reference
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
        messages.value.splice(0)  // Clear in-place to preserve reference
      }
    }
  }

  async function renameConversation(kbId: string, convId: string, title: string) {
    const updated = await api.updateConversationTitle(kbId, convId, title)
    const conv = conversations.value.find(c => c.id === convId)
    if (conv) {
      conv.title = updated.title
    }
    if (currentConv.value?.id === convId) {
      currentConv.value.title = updated.title
    }
  }

  async function togglePinConversation(kbId: string, convId: string) {
    const updated = await api.togglePinConversation(kbId, convId)
    const conv = conversations.value.find(c => c.id === convId)
    if (conv) {
      conv.is_pinned = updated.is_pinned
      conv.updated_at = updated.updated_at
    }
    // Re-sort conversations: pinned first, then by updated_at
    conversations.value.sort((a, b) => {
      if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    })
  }

  function selectConversation(conv: Conversation) {
    currentConv.value = conv
  }

  async function fetchMessages(kbId: string, convId: string) {
    if (!kbId || !convId) return
    loading.value = true
    try {
      const newMessages = await api.getMessages(kbId, convId)
      // Use splice to replace array contents in-place (preserves reference for reactive consumers)
      messages.value.splice(0, messages.value.length, ...newMessages)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '获取消息失败'
      error.value = msg
      console.error('Failed to fetch messages:', e)
    } finally {
      loading.value = false
    }
  }

  return {
    conversations, currentConv, messages, loading, error,
    fetchConversations, createConversation, deleteConversation,
    selectConversation, fetchMessages, renameConversation, togglePinConversation,
  }
}
