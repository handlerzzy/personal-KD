<template>
  <div class="login-container">
    <div class="login-card">
      <h1 class="login-title">知识库问答系统</h1>
      <p class="login-subtitle">{{ isLogin ? '登录' : '注册' }}</p>

      <form @submit.prevent="handleSubmit" class="login-form">
        <div class="form-group">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="username"
            type="text"
            placeholder="3-20个字符，字母、数字或下划线"
            required
            :disabled="loading"
          />
        </div>

        <div class="form-group">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="8-20个字符，字母和数字"
            required
            :disabled="loading"
          />
        </div>

        <div v-if="!isLogin" class="form-group">
          <label for="confirmPassword">确认密码</label>
          <input
            id="confirmPassword"
            v-model="confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            required
            :disabled="loading"
          />
        </div>

        <div v-if="isLogin" class="remember-me">
          <label class="checkbox-label">
            <input
              v-model="rememberMe"
              type="checkbox"
              :disabled="loading"
            />
            <span>记住密码</span>
          </label>
        </div>

        <div v-if="error" class="error-message">{{ error }}</div>

        <button type="submit" class="submit-btn" :disabled="loading">
          {{ loading ? '处理中...' : (isLogin ? '登录' : '注册') }}
        </button>
      </form>

      <div class="toggle-mode">
        <span>{{ isLogin ? '没有账号？' : '已有账号？' }}</span>
        <button @click="toggleMode" class="toggle-btn">
          {{ isLogin ? '立即注册' : '立即登录' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { register } from '../api'
import { useAuth } from '../composables/useAuth'

const emit = defineEmits<{
  (e: 'login-success'): void
}>()

const { login } = useAuth()

const isLogin = ref(true)
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')
const rememberMe = ref(localStorage.getItem('remember_me') === 'true')

function toggleMode() {
  isLogin.value = !isLogin.value
  error.value = ''
  confirmPassword.value = ''
}

async function handleSubmit() {
  error.value = ''
  loading.value = true

  try {
    if (isLogin.value) {
      await login(username.value, password.value, rememberMe.value)
      emit('login-success')
    } else {
      if (password.value !== confirmPassword.value) {
        error.value = '两次输入的密码不一致'
        loading.value = false
        return
      }
      await register(username.value, password.value)
      // Auto login after register
      await login(username.value, password.value)
      emit('login-success')
    }
  } catch (e: any) {
    error.value = e.message || '操作失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-card {
  background: white;
  border-radius: 16px;
  padding: 40px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.login-title {
  text-align: center;
  color: #333;
  margin: 0 0 8px 0;
  font-size: 28px;
  font-weight: 700;
}

.login-subtitle {
  text-align: center;
  color: #666;
  margin: 0 0 32px 0;
  font-size: 16px;
}

.login-form {
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
  color: #333;
}

.form-group input {
  padding: 12px 16px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 0.2s;
}

.form-group input:focus {
  outline: none;
  border-color: #667eea;
}

.form-group input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.error-message {
  color: #e74c3c;
  font-size: 14px;
  text-align: center;
  padding: 8px;
  background: #fdf2f2;
  border-radius: 6px;
}

.submit-btn {
  padding: 14px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.toggle-mode {
  text-align: center;
  margin-top: 24px;
  font-size: 14px;
  color: #666;
}

.toggle-btn {
  background: none;
  border: none;
  color: #667eea;
  font-weight: 600;
  cursor: pointer;
  padding: 0;
  margin-left: 4px;
}

.toggle-btn:hover {
  text-decoration: underline;
}

.remember-me {
  margin-top: -8px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #666;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #667eea;
  cursor: pointer;
}
</style>
