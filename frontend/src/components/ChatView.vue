<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { Conversation, KnowledgeBase, Message } from '../types'
import MessageBubble from './MessageBubble.vue'
import ChatInput from './ChatInput.vue'

const props = defineProps<{
  currentKb: KnowledgeBase | null
  currentConv: Conversation | null
  messages: Message[]
  streaming: boolean
  currentReasoning: string
  currentAnswer: string
  currentSources: any[]
}>()

const emit = defineEmits<{
  sendMessage: [query: string]
}>()

const messagesRef = ref<HTMLDivElement | null>(null)

watch(
  () => [props.currentAnswer, props.messages.length],
  () => {
    nextTick(() => {
      if (messagesRef.value) {
        messagesRef.value.scrollTop = messagesRef.value.scrollHeight
      }
    })
  },
  { deep: true }
)
</script>

<template>
  <main class="main">
    <div class="chat-header">
      <div v-if="currentKb" class="chat-header-row">
        <span class="kb-name">{{ currentKb.name }}</span>
        <span class="separator">/</span>
        <span class="conv-name">{{ currentConv?.title || '新对话' }}</span>
        <div class="status">
          <span class="status-dot" :class="{ online: !streaming }"/>
          {{ streaming ? '回答中...' : 'mimo-v2.5 已就绪' }}
        </div>
      </div>
      <span v-else class="conv-name">请选择或创建知识库</span>
    </div>
    <div class="messages" ref="messagesRef">
      <!-- Empty state -->
      <div v-if="messages.length === 0 && !streaming" class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5"/>
          <path d="M2 12l10 5 10-5"/>
        </svg>
        <p>向知识库提问开始对话</p>
        <p class="empty-hint">
系统将检索相关文档并生成回答
</p>
      </div>
      <MessageBubble
        v-for="msg in messages" :key="msg.id"
        :message="msg"
      />

      <!-- 流式回答中 -->
      <template v-if="streaming && (currentAnswer || currentReasoning)">
        <div class="msg ai">
          <div class="msg-avatar">AI</div>
          <div class="msg-content">
            <!-- 思考过程 -->
            <div v-if="currentReasoning" class="thinking-box">
              <div class="thinking-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M9 18l6-6-6-6"/></svg>
                <span class="thinking-label">思考过程</span>
                <span class="thinking-chars">{{ currentReasoning.length }} chars</span>
              </div>
              <div class="thinking-body-stream">{{ currentReasoning }}<span class="stream-cursor-inline">▊</span></div>
            </div>
            <!-- 回答内容 -->
            <div class="msg-bubble-ai" v-if="currentAnswer">{{ currentAnswer }}<span class="stream-cursor-inline">▊</span></div>
          </div>
        </div>
      </template>
    </div>

    <ChatInput
      :disabled="streaming || !currentKb"
      @send="emit('sendMessage', $event)"
    />
  </main>
</template>

<style scoped>
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.chat-header { padding: 14px 24px; border-bottom: 1px solid #E2E8F0; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.kb-name { font-size: 14px; font-weight: 600; color: #1E293B; }
.separator { color: #94A3B8; font-size: 12px; }
.conv-name { font-size: 13px; color: #64748B; }
.status { margin-left: auto; display: flex; align-items: center; gap: 6px; font-size: 12px; color: #94A3B8; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: #FCD34D; transition: background 300ms ease; }
.status-dot.online { background: #10B981; }
.messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 20px; }
.messages::-webkit-scrollbar { width: 4px; }
.messages::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 2px; }
.msg { display: flex; gap: 12px; max-width: 85%; }
.msg.ai { align-self: flex-start; }
.msg-avatar { width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; background: #F1F5F9; color: #64748B; }
.msg-content { min-width: 0; }
.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #94A3B8; gap: 8px; }
.empty-state p { font-size: 14px; }
.empty-hint { font-size: 12px; color: #CBD5E1; }
.thinking-header { display: flex; align-items: center; gap: 6px; padding: 6px 12px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px 8px 0 0; font-size: 12px; color: #64748B; }
.thinking-header svg { width: 14px; height: 14px; transform: rotate(90deg); flex-shrink: 0; }
.thinking-label { flex: 1; font-weight: 500; }
.thinking-chars { font-size: 11px; color: #94A3B8; }
.thinking-body-stream { padding: 8px 12px; font-size: 13px; line-height: 1.7; color: #64748B; background: #fff; border: 1px solid #E2E8F0; border-top: none; border-radius: 0 0 8px 8px; white-space: pre-wrap; }
.msg-bubble-ai { background: #F9FAFB; padding: 10px 16px; border-radius: 18px 18px 18px 4px; font-size: 14px; line-height: 1.6; border: 1px solid #F1F5F9; }
.stream-cursor-inline { animation: blink 0.8s step-end infinite; color: #6366F1; }
@keyframes blink { 50% { opacity: 0; } }
</style>