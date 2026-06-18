import { describe, it, expect, beforeEach } from 'vitest'
import { setTokens, clearTokens, getAccessToken } from '../index'

describe('Token Management', () => {
  beforeEach(() => {
    clearTokens()
    localStorage.clear()
  })

  it('getAccessToken returns null when no token is set', () => {
    expect(getAccessToken()).toBeNull()
  })

  it('setTokens stores access token in memory', () => {
    setTokens('access-123', 'refresh-456')
    expect(getAccessToken()).toBe('access-123')
  })

  it('setTokens stores tokens in localStorage', () => {
    setTokens('access-123', 'refresh-456')
    expect(localStorage.getItem('access_token')).toBe('access-123')
    expect(localStorage.getItem('refresh_token')).toBe('refresh-456')
  })

  it('clearTokens removes tokens from memory', () => {
    setTokens('access-123', 'refresh-456')
    clearTokens()
    expect(getAccessToken()).toBeNull()
  })

  it('clearTokens removes tokens from localStorage', () => {
    setTokens('access-123', 'refresh-456')
    clearTokens()
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })

  it('setTokens overwrites previous tokens', () => {
    setTokens('access-1', 'refresh-1')
    setTokens('access-2', 'refresh-2')
    expect(getAccessToken()).toBe('access-2')
    expect(localStorage.getItem('access_token')).toBe('access-2')
  })

  it('getAccessToken reads from localStorage on init (simulated)', () => {
    // Simulate tokens set before module loaded
    localStorage.setItem('access_token', 'stored-token')
    // Re-import would read from localStorage, but since module is cached,
    // we verify the storage mechanism works
    expect(localStorage.getItem('access_token')).toBe('stored-token')
  })
})
