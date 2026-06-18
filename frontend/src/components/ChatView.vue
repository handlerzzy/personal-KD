<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Conversation, KnowledgeBase, Message, Source } from '../types'
import MessageBubble from './MessageBubble.vue'
import ChatInput from './ChatInput.vue'

const props = defineProps<{
  currentKb: KnowledgeBase | null
  currentConv: Conversation | null
  messages: Message[]
  streaming: boolean
  searching: boolean
  uploading: boolean
  currentReasoning: string
  currentAnswer: string
  currentSources: Source[]
}>()

const emit = defineEmits<{
  sendMessage: [query: string]
  stop: []
  uploadFile: [file: File]
  createKb: []
  uploadDoc: []
}>()

const messagesRef = ref<HTMLDivElement | null>(null)

// Configure marked
marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(text: string): string {
  if (!text) return ''
  const raw = marked.parse(text) as string
  return DOMPurify.sanitize(raw)
}

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
      <!-- Welcome state (no conversation yet) -->
      <div v-if="!currentConv && !streaming && currentKb" class="welcome-state">
        <div class="welcome-logo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="64" height="64">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <h2 class="welcome-title">开始新对话</h2>
        <p class="welcome-hint">向「{{ currentKb.name }}」知识库提问</p>
      </div>

      <!-- Empty state (conversation exists but no messages) -->
      <div v-else-if="messages.length === 0 && !streaming && currentConv" class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5"/>
          <path d="M2 12l10 5 10-5"/>
        </svg>
        <p>向知识库提问开始对话</p>
        <p class="empty-hint">系统将检索相关文档并生成回答</p>
      </div>

      <!-- No KB selected — 引导创建知识库 -->
      <div v-else-if="!currentKb" class="guide-state">
        <div class="guide-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" width="56" height="56">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <h2 class="guide-title">欢迎使用知识库问答</h2>
        <p class="guide-desc">上传文档，构建你的专属知识库，开始智能问答</p>
        <div class="guide-actions">
          <button class="guide-btn primary" @click="emit('createKb')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            新建知识库
          </button>
          <button class="guide-btn secondary" @click="emit('uploadDoc')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            上传文档
          </button>
        </div>
        <p class="guide-hint">支持 PDF / TXT / MD 格式文档</p>
      </div>
      <MessageBubble
        v-for="msg in messages" :key="msg.id"
        :message="msg"
      />

      <!-- Searching state -->
      <div v-if="searching" class="searching-state">
        <div class="searching-spinner"></div>
        <span>正在检索知识库...</span>
      </div>

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
              <div class="thinking-body-stream">{{ currentReasoning }}<span v-if="searching" class="stream-cursor-inline">▊</span></div>
            </div>
            <!-- 回答内容 -->
            <div class="msg-bubble-ai markdown-body" v-if="currentAnswer">
              <span v-html="renderMarkdown(currentAnswer)"></span><span v-if="streaming && !searching" class="stream-cursor-inline">▊</span>
            </div>
            <!-- 来源 -->
            <div v-if="currentSources && currentSources.length > 0" class="msg-sources-stream">
              <details>
                <summary>{{ currentSources.length }} 个引用来源</summary>
                <div v-for="(src, i) in currentSources" :key="i" class="source-item">
                  <div class="source-header">
                    <span class="source-doc">{{ src.filename || '未知文档' }}</span>
                    <span v-if="src.heading" class="source-heading">{{ src.heading }}</span>
                    <span class="source-score">{{ (src.score || 0).toFixed(3) }}</span>
                  </div>
                  <div class="source-text">{{ src.text }}</div>
                </div>
              </details>
            </div>
          </div>
        </div>
      </template>
    </div>

    <ChatInput
      v-if="currentKb"
      :disabled="streaming || props.uploading"
      :streaming="streaming"
      :uploading="props.uploading"
      placeholder="输入问题开始对话..."
      @send="emit('sendMessage', $event)"
      @stop="emit('stop')"
      @upload-file="emit('uploadFile', $event)"
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
.welcome-state {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: #64748B; gap: 16px;
}
.welcome-logo {
  width: 96px; height: 96px; border-radius: 50%;
  background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%);
  display: flex; align-items: center; justify-content: center;
}
.welcome-logo svg { width: 48px; height: 48px; color: #6366F1; }
.welcome-title { font-size: 24px; font-weight: 600; color: #1E293B; margin: 0; }
.welcome-hint { font-size: 14px; color: #94A3B8; margin: 0; }
.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #94A3B8; gap: 8px; }
.empty-state p { font-size: 14px; }
.empty-hint { font-size: 12px; color: #CBD5E1; }

/* Guide state — no KB selected */
.guide-state {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 16px; padding: 32px;
}
.guide-icon {
  width: 112px; height: 112px; border-radius: 24px;
  background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%);
  display: flex; align-items: center; justify-content: center;
}
.guide-icon svg { color: #6366F1; }
.guide-title {
  font-size: 22px; font-weight: 600; color: #1E293B; margin: 0;
}
.guide-desc {
  font-size: 14px; color: #64748B; margin: 0; text-align: center; max-width: 360px;
}
.guide-actions {
  display: flex; gap: 12px; margin-top: 8px;
}
.guide-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 20px; border-radius: 10px;
  font-size: 14px; font-weight: 500; cursor: pointer;
  transition: background 200ms ease, box-shadow 200ms ease, transform 100ms ease;
  border: none;
}
.guide-btn:active { transform: scale(0.97); }
.guide-btn.primary {
  background: #6366F1; color: #fff;
}
.guide-btn.primary:hover { background: #4F46E5; box-shadow: 0 2px 8px rgba(99,102,241,0.3); }
.guide-btn.secondary {
  background: #F1F5F9; color: #475569; border: 1px solid #E2E8F0;
}
.guide-btn.secondary:hover { background: #E2E8F0; }
.guide-hint {
  font-size: 12px; color: #CBD5E1; margin: 0; margin-top: 4px;
}
.thinking-header { display: flex; align-items: center; gap: 6px; padding: 6px 12px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px 8px 0 0; font-size: 12px; color: #64748B; }
.thinking-header svg { width: 14px; height: 14px; transform: rotate(90deg); flex-shrink: 0; }
.thinking-label { flex: 1; font-weight: 500; }
.thinking-chars { font-size: 11px; color: #94A3B8; }
.thinking-body-stream { padding: 8px 12px; font-size: 13px; line-height: 1.7; color: #64748B; background: #fff; border: 1px solid #E2E8F0; border-top: none; border-radius: 0 0 8px 8px; white-space: pre-wrap; }
.msg-bubble-ai { background: #F9FAFB; padding: 10px 16px; border-radius: 18px 18px 18px 4px; font-size: 14px; line-height: 1.6; border: 1px solid #F1F5F9; }
.stream-cursor-inline { animation: blink 0.8s step-end infinite; color: #6366F1; }
@keyframes blink { 50% { opacity: 0; } }

.searching-state {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; color: #6366F1;
  font-size: 14px; font-weight: 500;
}
.searching-spinner {
  width: 20px; height: 20px;
  border: 2px solid #E0E7FF;
  border-top-color: #6366F1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Markdown styles for streaming answer */
.markdown-body :deep(p) { margin: 0 0 8px; }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: 4px 0 8px; padding-left: 20px; }
.markdown-body :deep(li) { margin: 2px 0; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3),
.markdown-body :deep(h4), .markdown-body :deep(h5), .markdown-body :deep(h6) {
  margin: 12px 0 6px; font-weight: 600; line-height: 1.4;
}
.markdown-body :deep(h1) { font-size: 1.3em; }
.markdown-body :deep(h2) { font-size: 1.2em; }
.markdown-body :deep(h3) { font-size: 1.1em; }
.markdown-body :deep(code) {
  background: #E2E8F0; padding: 1px 5px; border-radius: 4px;
  font-family: 'Fira Code', 'Consolas', monospace; font-size: 0.9em;
}
.markdown-body :deep(pre) {
  background: #1E293B; color: #E2E8F0; padding: 12px 16px;
  border-radius: 8px; overflow-x: auto; margin: 8px 0;
}
.markdown-body :deep(pre code) { background: none; padding: 0; color: inherit; font-size: 13px; }
.markdown-body :deep(blockquote) {
  border-left: 3px solid #6366F1; margin: 8px 0; padding: 4px 12px;
  color: #64748B; background: #F1F5F9; border-radius: 0 4px 4px 0;
}
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid #E2E8F0; padding: 6px 10px; text-align: left; }
.markdown-body :deep(th) { background: #F1F5F9; font-weight: 600; }
.markdown-body :deep(a) { color: #6366F1; text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
.markdown-body :deep(strong) { font-weight: 600; }

/* Sources styles for streaming */
.msg-sources-stream { margin-top: 8px; font-size: 12px; }
.msg-sources-stream summary { cursor: pointer; color: #6366F1; font-weight: 500; font-size: 12px; }
.source-item { padding: 8px 0; border-bottom: 1px solid #F1F5F9; }
.source-item:last-child { border-bottom: none; }
.source-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.source-doc { font-weight: 600; color: #1E293B; font-size: 12px; }
.source-heading { color: #6366F1; font-size: 11px; background: #EEF2FF; padding: 1px 6px; border-radius: 4px; }
.source-score { color: #10B981; font-family: 'Fira Code', monospace; font-size: 11px; margin-left: auto; }
.source-text { color: #64748B; font-size: 11px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>