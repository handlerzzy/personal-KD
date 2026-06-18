import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { User, TokenResponse } from '../types'
import * as api from '../api'

export const useAuthStore = defineStore('auth', () => {
  // State
  const isAuthenticated = ref(false)
  const currentUser = ref<User | null>(null)

  // Actions
  async function checkAuth(): Promise<boolean> {
    const token = api.getAccessToken()
    if (!token) {
      isAuthenticated.value = false
      return false
    }

    try {
      const user = await api.getCurrentUser()
      currentUser.value = user
      isAuthenticated.value = true
      return true
    } catch {
      api.clearTokens()
      isAuthenticated.value = false
      return false
    }
  }

  async function login(username: string, password: string, rememberMe = false): Promise<void> {
    const tokens: TokenResponse = await api.login(username, password, rememberMe)
    api.setTokens(tokens.access_token, tokens.refresh_token)

    // 持久化记住密码状态
    if (rememberMe) {
      localStorage.setItem('remember_me', 'true')
    } else {
      localStorage.removeItem('remember_me')
    }

    // 获取用户信息
    await checkAuth()
  }

  async function logout(): Promise<void> {
    try {
      await api.logout()
    } catch {
      // 忽略登出 API 错误
    }
    api.clearTokens()
    isAuthenticated.value = false
    currentUser.value = null
  }

  return {
    // State
    isAuthenticated,
    currentUser,

    // Actions
    checkAuth,
    login,
    logout,
  }
})
