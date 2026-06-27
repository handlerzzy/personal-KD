<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Message } from '../types'
import ThinkingBlock from './ThinkingBlock.vue'

const props = defineProps<{
  message: Message
  isStreaming?: boolean
}>()

const userLabel = '我'
const aiLabel = 'AI'

// Configure marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

/**
 * Parse <think> tags from content as a fallback for historical messages
 * that don't have a separate reasoning_content field.
 *
 * Streaming messages receive reasoning via event:reasoning and have
 * reasoning_content set — this is only needed for DB-persisted messages
 * where reasoning was embedded in content via <think> tags.
 */
const reasoningContent = computed(() => {
  if (props.message.reasoning_content) {
    return props.message.reasoning_content
  }
  const match = props.message.content.match(/<think>([\s\S]*?)<\/think>/)
  return match ? match[1].trim() : ''
})

const displayContent = computed(() => {
  // Strip <think> tags from content before markdown rendering
  return props.message.content.replace(/<think>[\s\S]*?<\/think>\n*/g, '').trim()
})

const renderedContent = computed(() => {
  if (!displayContent.value) return ''
  const raw = marked.parse(displayContent.value) as string
  return DOMPurify.sanitize(raw)
})
</script>

<template>
  <div class="msg" :class="message.role">
    <div class="msg-avatar">
{{ message.role === 'user' ? userLabel : aiLabel }}
</div>
    <div class="msg-content">
      <!-- Thinking process (AI only) -->
      <ThinkingBlock
        v-if="message.role === 'assistant' && reasoningContent"
        :reasoning="reasoningContent"
        :is-streaming="isStreaming"
      />
      <!-- Bubble -->
      <div class="msg-bubble markdown-body">
        <div v-if="displayContent" v-html="renderedContent"/>
        <div v-else-if="isStreaming" class="stream-cursor">思考中...</div>
      </div>
      <!-- Sources -->
      <div v-if="message.role === 'assistant' && message.sources && message.sources.length > 0" class="msg-sources">
        <details>
          <summary>{{ message.sources.length }} 个引用来源</summary>
          <div v-for="(src, i) in message.sources" :key="i" class="source-item">
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

<style scoped>
.msg { display: flex; gap: 12px; max-width: 85%; animation: fadeIn 0.3s ease; }
.msg.user { align-self: flex-end; flex-direction: row-reverse; }
.msg.ai { align-self: flex-start; }

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.msg-avatar {
  width: 32px; height: 32px; border-radius: 50%;
  flex-shrink: 0; display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
}
.msg.user .msg-avatar { background: #6366F1; color: white; }
.msg.ai .msg-avatar { background: #F1F5F9; color: #64748B; }

.msg-content { min-width: 0; }
.msg.user .msg-bubble {
  background: #E0E7FF; padding: 10px 16px;
  border-radius: 18px 18px 4px 18px;
  font-size: 14px; line-height: 1.6; color: #1E293B;
}
.msg.ai .msg-bubble {
  background: #F9FAFB; padding: 10px 16px;
  border-radius: 18px 18px 18px 4px;
  font-size: 14px; line-height: 1.6; color: #1E293B;
  border: 1px solid #F1F5F9;
}

/* Markdown styles */
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
.markdown-body :deep(pre code) {
  background: none; padding: 0; color: inherit; font-size: 13px;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid #6366F1; margin: 8px 0; padding: 4px 12px;
  color: #64748B; background: #F1F5F9; border-radius: 0 4px 4px 0;
}
.markdown-body :deep(table) {
  border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px;
}
.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid #E2E8F0; padding: 6px 10px; text-align: left;
}
.markdown-body :deep(th) { background: #F1F5F9; font-weight: 600; }
.markdown-body :deep(a) { color: #6366F1; text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid #E2E8F0; margin: 12px 0; }
.markdown-body :deep(strong) { font-weight: 600; }
.markdown-body :deep(em) { font-style: italic; }

.stream-cursor { color: #94A3B8; font-style: italic; }

.msg-sources {
  margin-top: 8px; font-size: 12px;
}
.msg-sources summary {
  cursor: pointer; color: #6366F1;
  font-weight: 500; font-size: 12px;
}
.source-item {
  padding: 8px 0; border-bottom: 1px solid #F1F5F9;
}
.source-item:last-child { border-bottom: none; }
.source-header {
  display: flex; align-items: center; gap: 6px; margin-bottom: 4px;
}
.source-doc {
  font-weight: 600; color: #1E293B; font-size: 12px;
}
.source-heading {
  color: #6366F1; font-size: 11px; background: #EEF2FF;
  padding: 1px 6px; border-radius: 4px;
}
.source-score {
  color: #10B981; font-family: 'Fira Code', monospace;
  font-size: 11px; margin-left: auto;
}
.source-text {
  color: #64748B; font-size: 11px; line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
