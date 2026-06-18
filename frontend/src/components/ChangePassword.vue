<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="modal-overlay" @click.self="$emit('close')">
        <div class="modal-content">
          <div class="modal-header">
            <h3>修改密码</h3>
            <button class="close-btn" @click="$emit('close')" aria-label="关闭">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <form @submit.prevent="handleSubmit" class="modal-form">
            <div class="form-group">
              <label for="oldPassword">当前密码</label>
              <input
                id="oldPassword"
                v-model="oldPassword"
                type="password"
                placeholder="请输入当前密码"
                required
                :disabled="loading"
                autocomplete="current-password"
              >
            </div>

            <div class="form-group">
              <label for="newPassword">新密码</label>
              <input
                id="newPassword"
                v-model="newPassword"
                type="password"
                placeholder="8-20个字符，字母和数字"
                required
                :disabled="loading"
                autocomplete="new-password"
              >
              <div
                v-if="newPassword && !isNewPasswordValid"
                class="field-hint error"
              >
                密码格式无效：需要8-20个字符，必须包含字母和数字
              </div>
            </div>

            <div class="form-group">
              <label for="confirmPassword">确认新密码</label>
              <input
                id="confirmPassword"
                v-model="confirmPassword"
                type="password"
                placeholder="请再次输入新密码"
                required
                :disabled="loading"
                autocomplete="new-password"
              >
              <div
                v-if="confirmPassword && newPassword !== confirmPassword"
                class="field-hint error"
              >
                两次输入的密码不一致
              </div>
            </div>

            <div v-if="error" class="error-message">
              {{ error }}
            </div>
            <div v-if="success" class="success-message">
              {{ success }}
            </div>

            <div class="modal-actions">
              <button type="button" class="btn-cancel" @click="$emit('close')" :disabled="loading">
                取消
              </button>
              <button
                type="submit"
                class="btn-confirm"
                :disabled="loading || !canSubmit"
              >
                {{ loading ? '修改中...' : '确认修改' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { changePassword } from '../api'

defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  close: []
  success: []
}>()

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')
const success = ref('')

// Password validation: 8-20 chars, must contain letter and digit
const isNewPasswordValid = computed(() => {
  return /^(?=.*[a-zA-Z])(?=.*\d).{8,20}$/.test(newPassword.value)
})

const canSubmit = computed(() => {
  return (
    oldPassword.value.length > 0 &&
    isNewPasswordValid.value &&
    newPassword.value === confirmPassword.value
  )
})

async function handleSubmit() {
  if (!canSubmit.value) return

  error.value = ''
  success.value = ''
  loading.value = true

  try {
    await changePassword(oldPassword.value, newPassword.value)
    success.value = '密码修改成功，即将重新登录...'

    // Clear form
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''

    // Notify parent to handle logout
    setTimeout(() => {
      emit('success')
      emit('close')
    }, 1500)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '修改失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-content {
  background: white;
  border-radius: 16px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid #E2E8F0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1E293B;
}

.close-btn {
  background: none;
  border: none;
  padding: 4px;
  cursor: pointer;
  color: #64748B;
  border-radius: 6px;
  transition: all 200ms ease;
}

.close-btn:hover {
  background: #F1F5F9;
  color: #1E293B;
}

.close-btn svg {
  width: 20px;
  height: 20px;
}

.modal-form {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 14px;
  font-weight: 600;
  color: #1E293B;
}

.form-group input {
  padding: 12px 16px;
  border: 2px solid #E2E8F0;
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 200ms ease;
}

.form-group input:focus {
  outline: none;
  border-color: #6366F1;
}

.form-group input:disabled {
  background: #F8FAFC;
  cursor: not-allowed;
}

.field-hint {
  font-size: 12px;
  color: #64748B;
}

.field-hint.error {
  color: #EF4444;
}

.error-message {
  color: #EF4444;
  font-size: 14px;
  text-align: center;
  padding: 12px;
  background: #FEF2F2;
  border-radius: 8px;
}

.success-message {
  color: #10B981;
  font-size: 14px;
  text-align: center;
  padding: 12px;
  background: #ECFDF5;
  border-radius: 8px;
}

.modal-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.btn-cancel {
  flex: 1;
  padding: 12px;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #64748B;
  cursor: pointer;
  transition: all 200ms ease;
}

.btn-cancel:hover:not(:disabled) {
  background: #F1F5F9;
}

.btn-cancel:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-confirm {
  flex: 1;
  padding: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  color: white;
  cursor: pointer;
  transition: all 200ms ease;
}

.btn-confirm:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-confirm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

/* Modal transition */
.modal-enter-active {
  transition: all 0.3s ease;
}

.modal-leave-active {
  transition: all 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .modal-content,
.modal-leave-to .modal-content {
  transform: scale(0.95);
}
</style>
