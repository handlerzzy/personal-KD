<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  disabled?: boolean
  placeholder?: string
  streaming?: boolean
  uploading?: boolean
}>()

const emit = defineEmits<{
  send: [query: string]
  stop: []
  uploadFile: [file: File]
}>()

const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

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

function handleStop() {
  emit('stop')
}

function triggerUpload() {
  fileInputRef.value?.click()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    emit('uploadFile', file)
    // Reset input so the same file can be selected again
    input.value = ''
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    if (props.streaming) {
      handleStop()
    } else {
      handleSend()
    }
  }
}
</script>

<template>
  <div class="input-area">
    <div class="input-wrapper">
      <input
        ref="fileInputRef"
        type="file"
        accept=".pdf,.txt,.md"
        class="file-input-hidden"
        @change="onFileChange"
      />
      <!-- 附件按钮 -->
      <button
        :disabled="disabled || props.uploading"
        aria-label="上传文档"
        class="attach-btn"
        @click="triggerUpload"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
        </svg>
      </button>
      <textarea
        ref="textareaRef"
        v-model="text"
        rows="1"
        :placeholder="placeholder || '向知识库提问...'"
        :disabled="disabled && !streaming"
        @input="autoResize"
        @keydown="onKeydown"
      />
      <div class="input-actions">
        <!-- 停止按钮：流式生成中显示 -->
        <button
          v-if="streaming"
          aria-label="停止生成"
          class="stop-btn"
          @click="handleStop"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="2"/>
          </svg>
        </button>
        <!-- 发送按钮：非流式时显示 -->
        <button
          v-else
          :disabled="disabled"
          aria-label="发送"
          class="send-btn"
          @click="handleSend"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
    </div>
    <div class="input-tip">
      {{ streaming ? '点击停止按钮或按 Enter 中断生成' : 'Enter 发送 · Shift+Enter 换行' }}
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
.file-input-hidden { display: none; }
.attach-btn {
  width: 36px; height: 36px;
  border: none; border-radius: 8px;
  background: transparent; color: #94A3B8;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: color 200ms ease, background 200ms ease;
  flex-shrink: 0;
}
.attach-btn:hover { color: #6366F1; background: #EEF2FF; }
.attach-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.attach-btn svg { width: 18px; height: 18px; }
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
.stop-btn {
  width: 36px; height: 36px;
  border: none; border-radius: 50%;
  background: #6366F1; color: white;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 200ms ease;
}
.stop-btn:hover { background: #4F46E5; }
.stop-btn svg { width: 16px; height: 16px; }
.input-tip {
  font-size: 11px; color: #94A3B8;
  margin-top: 6px; text-align: center;
}
</style>
