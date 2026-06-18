<script setup lang="ts">
import { ref } from 'vue'
import type { KnowledgeBase, Conversation } from '../types'
import DocList from './DocList.vue'

const props = defineProps<{
  kbs: KnowledgeBase[]
  currentKb: KnowledgeBase | null
  conversations: Conversation[]
  currentConv: Conversation | null
  sidebarOpen: boolean
  docRefreshKey: number
}>()

const emit = defineEmits<{
  selectKb: [kb: KnowledgeBase]
  createKb: []
  uploadDoc: []
  deleteKb: []
  selectConv: [conv: Conversation]
  createConv: []
  deleteConv: [id: string]
  renameConv: [id: string, title: string]
  togglePin: [id: string]
  deleteDoc: [docId: string]
  toggleSidebar: []
}>()

const kbDropdownOpen = defineModel<boolean>('kbDropdownOpen', { default: false })

// Context menu state
const contextMenu = ref({ show: false, x: 0, y: 0, convId: '', convTitle: '' })
const renamingConvId = ref<string | null>(null)
const renameValue = ref('')

function showContextMenu(e: MouseEvent, conv: Conversation) {
  e.preventDefault()
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, convId: conv.id, convTitle: conv.title }
}

function hideContextMenu() {
  contextMenu.value.show = false
}

function startRename() {
  renamingConvId.value = contextMenu.value.convId
  renameValue.value = contextMenu.value.convTitle
  hideContextMenu()
}

function confirmRename() {
  if (renamingConvId.value && renameValue.value.trim()) {
    emit('renameConv', renamingConvId.value, renameValue.value.trim())
  }
  renamingConvId.value = null
}

function cancelRename() {
  renamingConvId.value = null
}

function handlePin() {
  emit('togglePin', contextMenu.value.convId)
  hideContextMenu()
}

function handleDelete() {
  emit('deleteConv', contextMenu.value.convId)
  hideContextMenu()
}

function groupConversations(convs: Conversation[]) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const sevenDaysAgo = new Date(today)
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7)
  const thirtyDaysAgo = new Date(today)
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30)

  const groups: { label: string; items: Conversation[] }[] = []
  const pinned: Conversation[] = []
  const todayList: Conversation[] = []
  const yesterdayList: Conversation[] = []
  const weekList: Conversation[] = []
  const monthList: Conversation[] = []
  const olderMap = new Map<string, Conversation[]>()

  for (const conv of convs) {
    if (conv.is_pinned) {
      pinned.push(conv)
      continue
    }
    const d = new Date(conv.updated_at)
    if (d >= today) {
      todayList.push(conv)
    } else if (d >= yesterday) {
      yesterdayList.push(conv)
    } else if (d >= sevenDaysAgo) {
      weekList.push(conv)
    } else if (d >= thirtyDaysAgo) {
      monthList.push(conv)
    } else {
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      if (!olderMap.has(key)) olderMap.set(key, [])
      olderMap.get(key)!.push(conv)
    }
  }

  if (pinned.length) groups.push({ label: '置顶', items: pinned })
  if (todayList.length) groups.push({ label: '今天', items: todayList })
  if (yesterdayList.length) groups.push({ label: '昨天', items: yesterdayList })
  if (weekList.length) groups.push({ label: '7天内', items: weekList })
  if (monthList.length) groups.push({ label: '30天内', items: monthList })
  for (const [key, items] of olderMap) {
    groups.push({ label: key, items })
  }
  return groups
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

    <DocList
      :kb-id="currentKb?.id || null"
      :refresh-key="docRefreshKey"
      @delete="(id) => emit('deleteDoc', id)"
    />

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
        <template v-if="conversations.length > 0">
          <div v-for="group in groupConversations(conversations)" :key="group.label" class="conv-group">
            <div class="conv-group-label">{{ group.label }}</div>
            <div
              v-for="conv in group.items" :key="conv.id"
              class="conv-item"
              :class="{ active: currentConv?.id === conv.id }"
              @click="emit('selectConv', conv)"
              @contextmenu="showContextMenu($event, conv)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              <div class="conv-info">
                <div class="conv-title">
                  <template v-if="renamingConvId === conv.id">
                    <input
                      v-model="renameValue"
                      class="rename-input"
                      @keyup.enter="confirmRename"
                      @keyup.escape="cancelRename"
                      @blur="confirmRename"
                      @click.stop
                    />
                  </template>
                  <template v-else>
                    {{ conv.title }}
                  </template>
                </div>
              </div>
              <button class="more-btn" @click.stop="showContextMenu($event, conv)" aria-label="更多操作">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>
                </svg>
              </button>
            </div>
          </div>
        </template>

        <div v-if="conversations.length === 0" class="conv-empty">
          暂无对话，新建一个开始吧
        </div>
      </div>
    </div>

    <!-- Context Menu -->
    <Teleport to="body">
      <div
        v-if="contextMenu.show"
        class="context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      >
        <button class="context-menu-item" @click="startRename">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
          </svg>
          重命名
        </button>
        <button class="context-menu-item" @click="handlePin">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
          </svg>
          置顶
        </button>
        <div class="context-menu-divider"></div>
        <button class="context-menu-item danger" @click="handleDelete">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          </svg>
          删除
        </button>
      </div>
      <div v-if="contextMenu.show" class="context-menu-overlay" @click="hideContextMenu"></div>
    </Teleport>
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

.conv-group { margin-bottom: 8px; }
.conv-group-label {
  font-size: 11px; font-weight: 500; color: #94A3B8;
  padding: 4px 12px; text-transform: uppercase;
}

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
.more-btn {
  opacity: 0; transition: opacity 200ms ease;
  background: none; border: none; cursor: pointer;
  color: #94A3B8; padding: 2px;
}
.conv-item:hover .more-btn { opacity: 1; }
.more-btn:hover { color: #1E293B; }
.more-btn svg { width: 14px; height: 14px; }
.pin-icon { font-size: 10px; margin-right: 4px; }
.rename-input {
  width: 100%; border: 1px solid #6366F1; border-radius: 4px;
  padding: 2px 4px; font-size: 13px; font-family: inherit;
  outline: none; background: #fff;
}
.conv-empty {
  text-align: center; color: #94A3B8;
  font-size: 13px; padding: 32px 16px;
}

/* Context Menu */
.context-menu {
  position: fixed; z-index: 100;
  background: #fff; border: 1px solid #E2E8F0;
  border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  padding: 4px; min-width: 120px;
}
.context-menu-item {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 12px; border: none;
  background: none; font-size: 13px; color: #1E293B;
  cursor: pointer; border-radius: 4px; font-family: inherit;
  transition: background 150ms ease;
}
.context-menu-item:hover { background: #F1F5F9; }
.context-menu-item.danger { color: #EF4444; }
.context-menu-item.danger:hover { background: #FEF2F2; }
.context-menu-divider { height: 1px; background: #E2E8F0; margin: 4px 0; }
.context-menu-overlay {
  position: fixed; inset: 0; z-index: 99;
}
</style>
