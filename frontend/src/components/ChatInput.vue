<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  send: [query: string]
}>()

const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

function autoResize() {
  const el = textareaRef.value
  if (el) {
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }
}

function handleSend() {
  const q = text.value.trim()
  if (!q || props.disabled) return
  emit('send', q)
  text.value = ''
  autoResize()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}
</script>

<template>
  <div class="input-area">
    <div class="input-wrapper">
      <textarea
        ref="textareaRef"
        v-model="text"
        rows="1"
        placeholder="向知识库提问..."
        :disabled="disabled"
        @input="autoResize"
        @keydown="onKeydown"
      />
      <div class="input-actions">
        <button :disabled="disabled" aria-label="发送" class="send-btn" @click="handleSend">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
    </div>
    <div class="input-tip">
Enter 发送 · Shift+Enter 换行
</div>
  </div>
</template>

<style scoped>
.input-area {
  padding: 16px 24px 20px;
  border-top: 1px solid #E2E8F0;
  flex-shrink: 0;
}
.input-wrapper {
  display: flex; align-items: flex-end; gap: 8px;
  background: #fff;
  border: 1px solid #CBD5E1;
  border-radius: 12px;
  padding: 8px 8px 8px 16px;
  transition: border-color 200ms ease, box-shadow 200ms ease;
}
.input-wrapper:focus-within {
  border-color: #6366F1;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
}
textarea {
  flex: 1; border: none; outline: none;
  font-family: inherit; font-size: 14px; line-height: 1.5;
  resize: none; max-height: 120px;
  min-height: 24px; padding: 4px 0;
  color: #1E293B; background: transparent;
}
textarea::placeholder { color: #94A3B8; }
.input-actions { display: flex; gap: 4px; align-items: flex-end; }
.send-btn {
  width: 36px; height: 36px;
  border: none; border-radius: 8px;
  background: #6366F1; color: white;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 200ms ease;
}
.send-btn:hover { background: #4F46E5; }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.send-btn svg { width: 18px; height: 18px; }
.input-tip {
  font-size: 11px; color: #94A3B8;
  margin-top: 6px; text-align: center;
}
</style>
