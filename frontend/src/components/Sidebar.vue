<script setup lang="ts">
import type { KnowledgeBase, Conversation } from '../types'

defineProps<{
  kbs: KnowledgeBase[]
  currentKb: KnowledgeBase | null
  conversations: Conversation[]
  currentConv: Conversation | null
  sidebarOpen: boolean
}>()

const emit = defineEmits<{
  selectKb: [kb: KnowledgeBase]
  createKb: []
  uploadDoc: []
  deleteKb: []
  selectConv: [conv: Conversation]
  createConv: []
  deleteConv: [id: string]
  toggleSidebar: []
}>()

const kbDropdownOpen = defineModel<boolean>('kbDropdownOpen', { default: false })

function formatTime(dateStr: string) {
  const d = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}天前`
  return d.toLocaleDateString('zh-CN')
}
</script>

<template>
  <aside class="sidebar" :class="{ open: sidebarOpen }">
    <div class="sidebar-header">
      <h1>知识库</h1>
      <div class="kb-selector" @click="kbDropdownOpen = !kbDropdownOpen">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>
        </svg>
        <span>{{ currentKb?.name || '选择知识库' }}</span>
        <svg class="arrow" :class="{ rotated: kbDropdownOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>

      <div v-if="kbDropdownOpen" class="kb-dropdown">
        <div
          v-for="kb in kbs" :key="kb.id"
          class="kb-dropdown-item"
          :class="{ active: currentKb?.id === kb.id }"
          @click="emit('selectKb', kb); kbDropdownOpen = false"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>
          </svg>
          {{ kb.name }}
          <span class="badge">{{ kb.conv_count }} 对话</span>
        </div>
      </div>

      <div class="kb-actions">
        <button @click="emit('createKb')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          新建
        </button>
        <button @click="emit('uploadDoc')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          上传
        </button>
      </div>
    </div>

    <div class="conv-section">
      <div class="conv-header">
        <span>对话历史</span>
        <button class="delete-kb-btn" @click="emit('deleteKb')">
删除知识库
</button>
      </div>

      <div class="conv-new" @click="emit('createConv')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新建对话
      </div>

      <div class="conv-list">
        <div
          v-for="conv in conversations" :key="conv.id"
          class="conv-item"
          :class="{ active: currentConv?.id === conv.id }"
          @click="emit('selectConv', conv)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          <div class="conv-info">
            <div class="conv-title">
{{ conv.title }}
</div>
            <div class="conv-meta">
{{ formatTime(conv.updated_at) }} · {{ conv.message_count }}条消息
</div>
          </div>
          <button class="del-btn" @click.stop="emit('deleteConv', conv.id)" aria-label="删除对话">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>

        <div v-if="conversations.length === 0" class="conv-empty">
          暂无对话，新建一个开始吧
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 300px; min-width: 300px;
  background: #F8FAFC;
  border-right: 1px solid #E2E8F0;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.sidebar-header {
  padding: 20px 16px 12px;
  border-bottom: 1px solid #E2E8F0;
}
.sidebar-header h1 {
  font-size: 16px; font-weight: 600;
  color: #1E293B; letter-spacing: -0.02em;
}
.kb-selector {
  display: flex; align-items: center; gap: 8px;
  margin-top: 12px; padding: 8px 12px;
  background: #fff; border: 1px solid #CBD5E1;
  border-radius: 8px; cursor: pointer;
  font-size: 13px; color: #1E293B;
  transition: border-color 200ms ease;
}
.kb-selector:hover { border-color: #6366F1; }
.kb-selector svg { width: 16px; height: 16px; color: #64748B; flex-shrink: 0; }
.kb-selector span { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.arrow { transition: transform 200ms ease; }
.arrow.rotated { transform: rotate(180deg); }

.kb-dropdown {
  margin-top: 4px; background: #fff;
  border: 1px solid #E2E8F0; border-radius: 8px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.08);
  overflow: hidden;
}
.kb-dropdown-item {
  padding: 8px 12px; font-size: 13px;
  cursor: pointer; transition: background 200ms ease;
  display: flex; align-items: center; gap: 8px;
}
.kb-dropdown-item:hover { background: #F1F5F9; }
.kb-dropdown-item.active { color: #6366F1; font-weight: 500; }
.kb-dropdown-item svg { width: 14px; height: 14px; color: #94A3B8; flex-shrink: 0; }
.badge {
  margin-left: auto; font-size: 11px;
  background: #F1F5F9; color: #64748B;
  padding: 1px 6px; border-radius: 10px;
  white-space: nowrap;
}

.kb-actions { display: flex; gap: 4px; margin-top: 8px; }
.kb-actions button {
  flex: 1; padding: 6px 8px; font-size: 12px;
  background: #fff; border: 1px solid #CBD5E1;
  border-radius: 8px; cursor: pointer;
  color: #64748B; font-family: inherit;
  transition: all 200ms ease;
  display: flex; align-items: center; justify-content: center; gap: 4px;
}
.kb-actions button:hover { border-color: #6366F1; color: #6366F1; }
.kb-actions svg { width: 14px; height: 14px; }

.conv-section { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 8px; }
.conv-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 4px 8px; font-size: 12px; color: #94A3B8;
}
.delete-kb-btn {
  background: none; border: none; font-size: 11px;
  color: #EF4444; cursor: pointer; font-family: inherit;
  opacity: 0; transition: opacity 200ms ease;
}
.conv-header:hover .delete-kb-btn { opacity: 1; }
.conv-new {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; margin-bottom: 4px;
  font-size: 13px; color: #6366F1;
  cursor: pointer; border-radius: 8px;
  transition: background 200ms ease;
  border: 1px dashed #CBD5E1;
}
.conv-new:hover { background: #EEF2FF; border-color: #6366F1; }
.conv-new svg { width: 14px; height: 14px; }
.conv-list { flex: 1; overflow-y: auto; }
.conv-list::-webkit-scrollbar { width: 4px; }
.conv-list::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 2px; }

.conv-item {
  padding: 10px 12px; margin-bottom: 2px;
  border-radius: 8px; cursor: pointer;
  transition: background 200ms ease;
  display: flex; align-items: center; gap: 10px;
}
.conv-item:hover { background: #F1F5F9; }
.conv-item.active { background: #EEF2FF; }
.conv-item svg { width: 16px; height: 16px; color: #94A3B8; flex-shrink: 0; }
.conv-info { flex: 1; min-width: 0; }
.conv-title { font-size: 13px; font-weight: 500; color: #1E293B; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv-meta { font-size: 11px; color: #94A3B8; margin-top: 2px; }
.del-btn {
  opacity: 0; transition: opacity 200ms ease;
  background: none; border: none; cursor: pointer;
  color: #94A3B8; padding: 2px;
}
.conv-item:hover .del-btn { opacity: 1; }
.del-btn:hover { color: #EF4444; }
.del-btn svg { width: 14px; height: 14px; }
.conv-empty {
  text-align: center; color: #94A3B8;
  font-size: 13px; padding: 32px 16px;
}
</style>
