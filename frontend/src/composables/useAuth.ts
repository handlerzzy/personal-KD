import { storeToRefs } from 'pinia'
import { useAuthStore } from '../stores/auth'

export function useAuth() {
  const store = useAuthStore()
  // storeToRefs 正确提取 store 中的 refs（保持响应式类型）
  const { isAuthenticated, currentUser } = storeToRefs(store)

  return {
    // State (Ref<boolean>, Ref<User | null>)
    isAuthenticated,
    currentUser,

    // Actions
    login: store.login,
    logout: store.logout,
    checkAuth: store.checkAuth,
  }
}
