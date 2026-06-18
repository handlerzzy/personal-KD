import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../auth'
import * as api from '../../api'

// Mock the api module
vi.mock('../../api', () => ({
  login: vi.fn(),
  logout: vi.fn(),
  getCurrentUser: vi.fn(),
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  getAccessToken: vi.fn(),
}))

describe('Auth Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('checkAuth', () => {
    it('returns false when no token exists', async () => {
      vi.mocked(api.getAccessToken).mockReturnValue(null)
      const store = useAuthStore()

      const result = await store.checkAuth()

      expect(result).toBe(false)
      expect(store.isAuthenticated).toBe(false)
      expect(store.currentUser).toBeNull()
    })

    it('returns true and sets user when token is valid', async () => {
      vi.mocked(api.getAccessToken).mockReturnValue('valid-token')
      vi.mocked(api.getCurrentUser).mockResolvedValue({
        id: '1', username: 'testuser', email: undefined,
        is_active: 1, created_at: '2026-01-01', updated_at: '2026-01-01',
      })
      const store = useAuthStore()

      const result = await store.checkAuth()

      expect(result).toBe(true)
      expect(store.isAuthenticated).toBe(true)
      expect(store.currentUser?.username).toBe('testuser')
    })

    it('clears tokens and returns false when API call fails', async () => {
      vi.mocked(api.getAccessToken).mockReturnValue('invalid-token')
      vi.mocked(api.getCurrentUser).mockRejectedValue(new Error('401'))
      const store = useAuthStore()

      const result = await store.checkAuth()

      expect(result).toBe(false)
      expect(store.isAuthenticated).toBe(false)
      expect(api.clearTokens).toHaveBeenCalled()
    })
  })

  describe('login', () => {
    it('sets tokens and authenticates on success', async () => {
      vi.mocked(api.login).mockResolvedValue({
        access_token: 'new-access',
        refresh_token: 'new-refresh',
        token_type: 'bearer',
      })
      vi.mocked(api.getAccessToken).mockReturnValue('new-access')
      vi.mocked(api.getCurrentUser).mockResolvedValue({
        id: '1', username: 'testuser', email: undefined,
        is_active: 1, created_at: '2026-01-01', updated_at: '2026-01-01',
      })
      const store = useAuthStore()

      await store.login('testuser', 'password123', false)

      expect(api.setTokens).toHaveBeenCalledWith('new-access', 'new-refresh')
      expect(store.isAuthenticated).toBe(true)
    })

    it('persists remember_me in localStorage', async () => {
      vi.mocked(api.login).mockResolvedValue({
        access_token: 'a', refresh_token: 'r', token_type: 'bearer',
      })
      vi.mocked(api.getAccessToken).mockReturnValue('a')
      vi.mocked(api.getCurrentUser).mockResolvedValue({
        id: '1', username: 'test', email: undefined,
        is_active: 1, created_at: '', updated_at: '',
      })
      const store = useAuthStore()

      await store.login('test', 'pass1234', true)
      expect(localStorage.getItem('remember_me')).toBe('true')

      await store.login('test', 'pass1234', false)
      expect(localStorage.getItem('remember_me')).toBeNull()
    })

    it('throws when API login fails', async () => {
      vi.mocked(api.login).mockRejectedValue(new Error('用户名或密码错误'))
      const store = useAuthStore()

      await expect(store.login('wrong', 'wrong', false)).rejects.toThrow('用户名或密码错误')
      expect(store.isAuthenticated).toBe(false)
    })
  })

  describe('logout', () => {
    it('clears tokens and resets state', async () => {
      vi.mocked(api.logout).mockResolvedValue()
      const store = useAuthStore()
      store.isAuthenticated = true
      store.currentUser = { id: '1', username: 'test', email: undefined, is_active: 1, created_at: '', updated_at: '' }

      await store.logout()

      expect(api.clearTokens).toHaveBeenCalled()
      expect(store.isAuthenticated).toBe(false)
      expect(store.currentUser).toBeNull()
    })

    it('clears state even when logout API fails', async () => {
      vi.mocked(api.logout).mockRejectedValue(new Error('network error'))
      const store = useAuthStore()
      store.isAuthenticated = true

      await store.logout()

      expect(store.isAuthenticated).toBe(false)
      expect(api.clearTokens).toHaveBeenCalled()
    })
  })
})
