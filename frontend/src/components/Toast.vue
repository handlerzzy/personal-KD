<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  message: string
  type: 'success' | 'error' | 'info'
  show: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const visible = ref(false)

watch(() => props.show, (val) => {
  if (val) {
    visible.value = true
    setTimeout(() => {
      visible.value = false
      emit('close')
    }, 3000)
  }
})
</script>

<template>
  <Transition name="toast">
    <div v-if="visible" class="toast" :class="type">
      <svg v-if="type === 'success'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
        <polyline points="22 4 12 14.01 9 11.01"/>
      </svg>
      <svg v-else-if="type === 'error'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
        <circle cx="12" cy="12" r="10"/>
        <line x1="15" y1="9" x2="9" y2="15"/>
        <line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="16" x2="12" y2="12"/>
        <line x1="12" y1="8" x2="12.01" y2="8"/>
      </svg>
      <span>{{ message }}</span>
    </div>
  </Transition>
</template>

<style scoped>
.toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 8px;
  padding: 10px 20px; border-radius: 8px;
  font-size: 13px; font-weight: 500;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  z-index: 1000;
  transition: all 300ms ease;
}
.toast.success { background: #10B981; color: #fff; }
.toast.error { background: #EF4444; color: #fff; }
.toast.info { background: #6366F1; color: #fff; }
.toast-enter-active { opacity: 0; transform: translateX(-50%) translateY(20px); }
.toast-enter-to { opacity: 1; transform: translateX(-50%) translateY(0); }
.toast-leave-active { opacity: 0; transform: translateX(-50%) translateY(20px); }
</style>
