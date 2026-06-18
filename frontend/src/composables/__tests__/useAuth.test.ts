import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuth } from '../useAuth'
import type { Ref } from 'vue'

describe('useAuth Composable', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('returns isAuthenticated as a ref-like object', () => {
    const { isAuthenticated } = useAuth()
    // storeToRefs returns Ref<boolean> — check .value is accessible
    expect(typeof isAuthenticated.value).toBe('boolean')
  })

  it('returns currentUser as a ref-like object', () => {
    const { currentUser } = useAuth()
    expect(currentUser.value).toBeNull()
  })

  it('exposes login action from store', () => {
    const { login } = useAuth()
    expect(typeof login).toBe('function')
  })

  it('exposes logout action from store', () => {
    const { logout } = useAuth()
    expect(typeof logout).toBe('function')
  })

  it('exposes checkAuth action from store', () => {
    const { checkAuth } = useAuth()
    expect(typeof checkAuth).toBe('function')
  })

  it('multiple calls return the same store state (singleton)', () => {
    const auth1 = useAuth()
    const auth2 = useAuth()
    // storeToRefs on same store returns same underlying refs
    expect(auth1.isAuthenticated.value).toBe(auth2.isAuthenticated.value)
  })
})
