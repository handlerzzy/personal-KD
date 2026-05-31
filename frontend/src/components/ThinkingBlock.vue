<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  reasoning: string
  isStreaming?: boolean
}>()

const expanded = ref(true)

watch(() => props.isStreaming, (val) => {
  if (val) expanded.value = true
})

function toggle() {
  expanded.value = !expanded.value
}
</script>

<template>
  <div class="thinking" v-if="reasoning">
    <button class="thinking-toggle" :class="{ open: expanded }" @click="toggle">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="9 18 15 12 9 6"/>
      </svg>
      <span class="label">思考过程</span>
      <span class="tokens">{{ reasoning.length }} chars</span>
    </button>
    <div class="thinking-body" :class="{ open: expanded }">
      {{ reasoning }}
      <span v-if="isStreaming" class="stream-cursor">|</span>
    </div>
  </div>
</template>

<style scoped>
.thinking {
  margin-bottom: 8px;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  overflow: hidden;
}
.thinking-toggle {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  background: #F8FAFC;
  border: none; width: 100%; cursor: pointer;
  font-size: 12px; color: #64748B;
  font-family: inherit; text-align: left;
  transition: background 200ms ease;
}
.thinking-toggle:hover { background: #F1F5F9; }
.thinking-toggle svg {
  width: 14px; height: 14px;
  transition: transform 200ms ease;
}
.thinking-toggle.open svg { transform: rotate(90deg); }
.label { flex: 1; font-weight: 500; }
.tokens { font-size: 11px; color: #94A3B8; }
.thinking-body {
  display: none;
  padding: 8px 12px;
  font-size: 13px; line-height: 1.7;
  color: #64748B;
  background: #fff;
  border-top: 1px solid #E2E8F0;
  white-space: pre-wrap;
}
.thinking-body.open { display: block; }
.stream-cursor {
  animation: blink 0.8s step-end infinite;
  color: #6366F1;
}
@keyframes blink { 50% { opacity: 0; } }
</style>
