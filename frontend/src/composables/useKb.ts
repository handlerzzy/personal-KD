import { ref } from 'vue'
import type { KnowledgeBase } from '../types'
import * as api from '../api'

export function useKb() {
  const kbs = ref<KnowledgeBase[]>([])
  const currentKb = ref<KnowledgeBase | null>(null)
  const loading = ref(false)

  async function fetchKbs() {
    loading.value = true
    try {
      kbs.value = await api.getKnowledgeBases()
      if (!currentKb.value && kbs.value.length > 0) {
        currentKb.value = kbs.value[0]
      }
    } catch (e: any) {
      console.error('Failed to fetch knowledge bases:', e)
    } finally {
      loading.value = false
    }
  }

  async function createKb(name: string, description = '') {
    const kb = await api.createKnowledgeBase(name, description)
    kbs.value.unshift(kb)
    currentKb.value = kb
    return kb
  }

  async function deleteKb(id: string) {
    await api.deleteKnowledgeBase(id)
    kbs.value = kbs.value.filter(k => k.id !== id)
    if (currentKb.value?.id === id) {
      currentKb.value = kbs.value[0] || null
    }
  }

  function selectKb(kb: KnowledgeBase) {
    currentKb.value = kb
  }

  return { kbs, currentKb, loading, fetchKbs, createKb, deleteKb, selectKb }
}
