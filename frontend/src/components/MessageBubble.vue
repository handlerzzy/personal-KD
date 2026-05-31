<script setup lang="ts">
import type { Message } from '../types'
import ThinkingBlock from './ThinkingBlock.vue'

defineProps<{
  message: Message
  isStreaming?: boolean
}>()

const userLabel = '我'
const aiLabel = 'AI'
</script>

<template>
  <div class="msg" :class="message.role">
    <div class="msg-avatar">
{{ message.role === 'user' ? userLabel : aiLabel }}
</div>
    <div class="msg-content">
      <!-- Thinking process (AI only) -->
      <ThinkingBlock
        v-if="message.role === 'assistant' && message.reasoning_content"
        :reasoning="message.reasoning_content"
        :is-streaming="isStreaming"
      />
      <!-- Bubble -->
      <div class="msg-bubble" :class="{ 'stream-cursor': isStreaming && !message.content }">
        <div v-if="message.content" v-text="message.content"/>
        <div v-if="message.content && isStreaming" class="stream-cursor-end">
|
</div>
        <div v-else-if="!message.content && isStreaming" class="stream-cursor">
|
</div>
      </div>
      <!-- Sources -->
      <div v-if="message.role === 'assistant' && message.sources && message.sources.length > 0" class="msg-sources">
        <details>
          <summary>{{ message.sources.length }} 个引用来源</summary>
          <div v-for="(src, i) in message.sources" :key="i" class="source-item">
            <span class="source-score">[{{ (src.score || 0).toFixed(3) }}]</span>
            <span class="source-text">{{ src.text }}</span>
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

.stream-cursor { animation: blink 0.8s step-end infinite; color: #6366F1; }
.stream-cursor-end {
  display: inline; animation: blink 0.8s step-end infinite; color: #6366F1;
}
@keyframes blink { 50% { opacity: 0; } }

.msg-sources {
  margin-top: 6px; font-size: 12px;
}
.msg-sources summary {
  cursor: pointer; color: #6366F1;
  font-weight: 500; font-size: 12px;
}
.source-item {
  padding: 4px 0; display: flex; gap: 6px;
  border-bottom: 1px solid #F1F5F9;
}
.source-score { color: #10B981; font-family: 'Fira Code', monospace; flex-shrink: 0; }
.source-text { color: #64748B; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
