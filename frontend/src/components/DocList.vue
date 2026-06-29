<script setup lang="ts">
import { ref, watch } from 'vue'
import type { KBDocument } from '../types'
import * as api from '../api'

const props = defineProps<{
  kbId: string | null
  refreshKey: number
}>()

const emit = defineEmits<{
  delete: [docId: string]
}>()

const docs = ref<KBDocument[]>([])
const loading = ref(false)
const expanded = ref(false)
// Track whether user has manually toggled — prevents auto-expand from overriding user choice
const userToggled = ref(false)

async function fetchDocs() {
  if (!props.kbId) { docs.value = []; return }
  loading.value = true
  try {
    docs.value = await api.getDocuments(props.kbId)
    // Auto-expand when KB has no documents, unless user manually collapsed
    if (docs.value.length === 0 && !userToggled.value) {
      expanded.value = true
    }
  } catch (e) {
    console.error('Failed to fetch docs:', e)
  } finally {
    loading.value = false
  }
}

function toggleDocs() {
  expanded.value = !expanded.value
  userToggled.value = true
}

watch(() => [props.kbId, props.refreshKey], () => {
  if (props.kbId) fetchDocs()
}, { immediate: true })

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function fileTypeIcon(type: string) {
  if (type === 'pdf') return 'PDF'
  if (type === 'md' || type === 'markdown') return 'MD'
  return 'TXT'
}
</script>

<template>
  <div class="doc-section" v-if="kbId">
    <div class="doc-header" @click="toggleDocs">
      <span>文档 ({{ docs.length }})</span>
      <svg class="arrow" :class="{ rotated: expanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </div>

    <div v-if="expanded" class="doc-list">
      <div v-if="loading" class="doc-loading">加载中...</div>

      <div v-else-if="docs.length === 0" class="doc-empty">暂无文档</div>

      <div v-else v-for="doc in docs" :key="doc.id" class="doc-item">
        <span class="doc-type" :class="doc.file_type">{{ fileTypeIcon(doc.file_type) }}</span>
        <div class="doc-info">
          <div class="doc-name" :title="doc.filename">{{ doc.filename }}</div>
          <div class="doc-meta">{{ formatSize(doc.file_size) }} · {{ doc.chunk_count }} 块</div>
        </div>
        <button class="doc-del" @click.stop="emit('delete', doc.id)" aria-label="删除文档">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.doc-section {
  border-top: 1px solid #E2E8F0;
  margin-top: 4px;
}
.doc-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 8px 4px; font-size: 12px; color: #94A3B8;
  cursor: pointer; user-select: none;
}
.doc-header:hover { color: #64748B; }
.arrow { transition: transform 200ms ease; }
.arrow.rotated { transform: rotate(180deg); }

.doc-list { padding: 0 4px 4px; }
.doc-loading, .doc-empty {
  text-align: center; font-size: 12px; color: #94A3B8; padding: 12px;
}
.doc-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 6px;
  transition: background 200ms ease;
}
.doc-item:hover { background: #F1F5F9; }
.doc-type {
  font-size: 10px; font-weight: 700; padding: 2px 5px;
  border-radius: 4px; flex-shrink: 0;
  background: #F1F5F9; color: #64748B;
}
.doc-type.pdf { background: #FEF2F2; color: #EF4444; }
.doc-type.md, .doc-type.markdown { background: #EEF2FF; color: #6366F1; }
.doc-info { flex: 1; min-width: 0; }
.doc-name {
  font-size: 12px; font-weight: 500; color: #1E293B;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.doc-meta { font-size: 11px; color: #94A3B8; }
.doc-del {
  opacity: 0; background: none; border: none;
  cursor: pointer; color: #94A3B8; padding: 2px;
  transition: all 200ms ease;
}
.doc-item:hover .doc-del { opacity: 1; }
.doc-del:hover { color: #EF4444; }
</style>
