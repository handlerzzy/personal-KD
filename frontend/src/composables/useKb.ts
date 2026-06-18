import { ref } from 'vue'
import type { KnowledgeBase } from '../types'
import * as api from '../api'

const LAST_KB_KEY = 'personalkd_last_kb_id'

export function useKb() {
  const kbs = ref<KnowledgeBase[]>([])
  const currentKb = ref<KnowledgeBase | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchKbs() {
    loading.value = true
    error.value = null
    try {
      kbs.value = await api.getKnowledgeBases()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '获取知识库列表失败'
      error.value = msg
      console.error('Failed to fetch knowledge bases:', e)
    } finally {
      loading.value = false
    }
  }

  async function createKb(name: string, description = '') {
    const kb = await api.createKnowledgeBase(name, description)
    kbs.value.unshift(kb)
    currentKb.value = kb
    localStorage.setItem(LAST_KB_KEY, kb.id)
    return kb
  }

  async function deleteKb(id: string) {
    await api.deleteKnowledgeBase(id)
    kbs.value = kbs.value.filter(k => k.id !== id)
    if (currentKb.value?.id === id) {
      currentKb.value = kbs.value[0] || null
      if (currentKb.value) {
        localStorage.setItem(LAST_KB_KEY, currentKb.value.id)
      } else {
        localStorage.removeItem(LAST_KB_KEY)
      }
    }
  }

  function selectKb(kb: KnowledgeBase) {
    currentKb.value = kb
    localStorage.setItem(LAST_KB_KEY, kb.id)
  }

  return { kbs, currentKb, loading, error, fetchKbs, createKb, deleteKb, selectKb }
}
