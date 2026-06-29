<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatView from './components/ChatView.vue'
import KbModal from './components/KbModal.vue'
import Toast from './components/Toast.vue'
import Login from './components/Login.vue'
import ChangePassword from './components/ChangePassword.vue'
import { useKb } from './composables/useKb'
import { useConversation } from './composables/useConversation'
import { useChat } from './composables/useChat'
import * as api from './api'
import { useAuth } from './composables/useAuth'

const { isAuthenticated, currentUser, checkAuth, logout: authLogout } = useAuth()
const { kbs, currentKb, fetchKbs, createKb, deleteKb, selectKb } = useKb()
const {
  conversations, currentConv, messages,
  fetchConversations, createConversation, deleteConversation,
  selectConversation, fetchMessages, renameConversation, togglePinConversation,
} = useConversation()
const { streaming, searching, currentReasoning, currentAnswer, currentSources, newTitle, sendMessage, cancelStream } = useChat()

const sidebarOpen = ref(true)
const kbDropdownOpen = ref(false)
const modalType = ref<'newKb' | 'upload' | 'deleteKb' | 'newConv' | ''>('')
const modalShow = ref(false)
const changePasswordShow = ref(false)
// 防止 handleSend 中 createConversation 触发的 watcher fetchMessages
// 与 sendMessage 的临时消息 push 产生竞态条件
const sendingNewMessage = ref(false)
const uploading = ref(false)
const uploadingFileName = ref('')
const maxUploadSizeMb = ref(200)

// Toast
const toastShow = ref(false)
const toastMsg = ref('')
const toastType = ref<'success' | 'error' | 'info'>('info')
function showToast(msg: string, type: 'success' | 'error' | 'info' = 'info') {
  toastMsg.value = msg
  toastType.value = type
  toastShow.value = true
}

// Document list refresh trigger
const docRefreshKey = ref(0)
function refreshDocs() { docRefreshKey.value++ }

// localStorage key for last selected KB
const LAST_KB_KEY = 'personalkd_last_kb_id'

async function handleLoginSuccess() {
  await checkAuth()
  await initApp()
}

async function handleLogout() {
  // Clear reactive state BEFORE flipping isAuthenticated to avoid
  // unmounting components seeing stale data
  kbs.value = []
  currentKb.value = null
  conversations.value = []
  currentConv.value = null
  messages.value.splice(0)
  await authLogout()
}

async function initApp() {
  await fetchKbs()

  const mql = window.matchMedia('(max-width: 768px)')
  sidebarOpen.value = !mql.matches
  mql.addEventListener('change', (e) => { sidebarOpen.value = !e.matches })

  // Restore last selected KB from localStorage
  const lastKbId = localStorage.getItem(LAST_KB_KEY)
  if (lastKbId && kbs.value.length > 0) {
    const savedKb = kbs.value.find(kb => kb.id === lastKbId)
    if (savedKb) {
      await selectKb(savedKb)
    }
  }

  // Fetch upload config for client-side validation
  try {
    const config = await api.getUploadConfig()
    maxUploadSizeMb.value = config.max_upload_size_mb
  } catch { /* 兜底使用默认值 */ }
}

onMounted(async () => {
  await checkAuth()
  if (isAuthenticated.value) {
    await initApp()
  }
})

// When KB changes, load conversations
watch(currentKb, async (kb) => {
  if (kb) {
    await fetchConversations(kb.id)
  } else {
    conversations.value = []
    currentConv.value = null
    messages.value.splice(0)
  }
})

// When conversation changes, load messages
// Skip fetch during streaming or when sending a new message to avoid
// race condition with temp optimistic user message
watch(currentConv, async (conv) => {
  if (conv && currentKb.value && !streaming.value && !sendingNewMessage.value) {
    await fetchMessages(currentKb.value.id, conv.id)
  } else if (!conv) {
    messages.value.splice(0)
  }
})

// When streaming ends, retry fetching messages if currentConv was skipped
// (e.g., user switched conversations while streaming was in progress)
watch(streaming, async (isStreaming, prevStreaming) => {
  if (prevStreaming && !isStreaming && currentConv.value && currentKb.value && !sendingNewMessage.value) {
    await fetchMessages(currentKb.value.id, currentConv.value.id)
  }
})

function showModal(type: typeof modalType.value) {
  modalType.value = type
  modalShow.value = true
}

function closeModal() {
  modalShow.value = false
  modalType.value = ''
}

async function handleCreateKb(name: string, desc: string) {
  await createKb(name, desc)
  showToast(`知识库「${name}」已创建，请上传文档以构建知识库`, 'info')
}

async function handleUpload(file: File) {
  if (!currentKb.value || uploading.value) return
  const maxSize = maxUploadSizeMb.value * 1024 * 1024
  if (file.size > maxSize) {
    showToast(`文件过大（${(file.size / 1024 / 1024).toFixed(1)}MB），最大允许 ${maxUploadSizeMb.value}MB`, 'error')
    return
  }
  uploading.value = true
  uploadingFileName.value = file.name
  try {
    await api.uploadDocument(currentKb.value.id, file)
    showToast(`"${file.name}" 上传成功`, 'success')
    await fetchKbs()
    refreshDocs()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '上传失败'
    showToast(`上传失败: ${msg}`, 'error')
  } finally {
    uploading.value = false
    uploadingFileName.value = ''
  }
}

async function handleDeleteDoc(docId: string) {
  if (!currentKb.value) return
  try {
    await api.deleteDocument(currentKb.value.id, docId)
    showToast('文档已删除', 'success')
    await fetchKbs()
    refreshDocs()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '删除失败'
    showToast(`删除失败: ${msg}`, 'error')
  }
}

async function handleDeleteKb() {
  if (!currentKb.value) return
  await deleteKb(currentKb.value.id)
}

async function handleNewConv() {
  // Clear current conversation to show welcome page
  // Actual conversation will be created when user sends first message
  currentConv.value = null
  messages.value.splice(0)
}

function handleGuideUpload() {
  // No KB selected — open new KB modal first (KB required for upload)
  showModal('newKb')
}

async function handleChangePasswordSuccess() {
  // Password changed successfully, logout and show login page
  await handleLogout()
}

async function handleDeleteConv(convId: string) {
  if (!currentKb.value) return
  await deleteConversation(currentKb.value.id, convId)
}

async function handleRenameConv(convId: string, newTitle: string) {
  if (!currentKb.value) return
  await renameConversation(currentKb.value.id, convId, newTitle)
}

async function handleTogglePin(convId: string) {
  if (!currentKb.value) return
  await togglePinConversation(currentKb.value.id, convId)
}

async function handleSend(query: string) {
  if (!currentKb.value || streaming.value) return

  sendingNewMessage.value = true

  try {
    // If no conversation exists, create one first
    if (!currentConv.value) {
      await createConversation(currentKb.value.id)
    }

    if (!currentConv.value) return

    await sendMessage(currentKb.value.id, currentConv.value.id, query, messages.value)
    // Stream finished — refresh messages from server (remove temp user message)
    if (currentKb.value && currentConv.value) {
      // Remove temp messages in-place to preserve array reference
      for (let i = messages.value.length - 1; i >= 0; i--) {
        if (messages.value[i].id.startsWith('temp-')) {
          messages.value.splice(i, 1)
        }
      }
      await fetchMessages(currentKb.value.id, currentConv.value.id)
    }

    // Update conversation title if generated via SSE
    if (newTitle.value && currentConv.value) {
      currentConv.value.title = newTitle.value
      // Update in conversations list
      const conv = conversations.value.find(c => c.id === currentConv.value!.id)
      if (conv) {
        conv.title = newTitle.value
      }
      newTitle.value = null
    } else if (currentConv.value && currentConv.value.title === '新对话' && currentKb.value) {
      // Title generation may have timed out (>2s) — refetch from DB
      const savedConvId = currentConv.value.id
      await fetchConversations(currentKb.value.id)
      // Restore currentConv reference after refetch
      const updated = conversations.value.find(c => c.id === savedConvId)
      if (updated) currentConv.value = updated
    }
  } finally {
    sendingNewMessage.value = false
  }
}
</script>

<template>
  <!-- Login page (outside .app to avoid flex constraints) -->
  <Login v-if="!isAuthenticated" @login-success="handleLoginSuccess" />

  <!-- Main app -->
  <div v-else class="app">
      <!-- User info bar -->
      <div class="user-bar">
        <div class="user-info">
          <span class="user-name">{{ currentUser?.username }}</span>
          <span class="user-email" v-if="currentUser?.email">{{ currentUser.email }}</span>
        </div>
        <div class="user-actions">
          <button class="action-btn" @click="changePasswordShow = true" title="修改密码">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
          </button>
          <button class="action-btn logout-btn" @click="handleLogout" title="退出登录">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Mobile sidebar toggle -->
      <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen" aria-label="切换侧栏">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>

      <Sidebar
        :kbs="kbs"
        :current-kb="currentKb"
        :conversations="conversations"
        :current-conv="currentConv"
        :sidebar-open="sidebarOpen"
        :doc-refresh-key="docRefreshKey"
        v-model:kb-dropdown-open="kbDropdownOpen"
        @select-kb="selectKb"
        @create-kb="showModal('newKb')"
        @upload-doc="currentKb ? showModal('upload') : handleGuideUpload()"
        @delete-kb="showModal('deleteKb')"
        @select-conv="selectConversation"
        @create-conv="handleNewConv"
        @delete-conv="handleDeleteConv"
        @rename-conv="handleRenameConv"
        @toggle-pin="handleTogglePin"
        @delete-doc="handleDeleteDoc"
        @toggle-sidebar="sidebarOpen = !sidebarOpen"
      />

      <ChatView
        :current-kb="currentKb"
        :current-conv="currentConv"
        :messages="messages"
        :streaming="streaming"
        :searching="searching"
        :uploading="uploading"
        :current-reasoning="currentReasoning"
        :current-answer="currentAnswer"
        :current-sources="currentSources"
        @send-message="handleSend"
        @stop="cancelStream"
        @upload-file="handleUpload"
        @create-kb="showModal('newKb')"
        @upload-doc="handleGuideUpload"
      />

      <KbModal
        :show="modalShow"
        :type="modalType"
        :current-kb="currentKb"
        @close="closeModal"
        @confirm-new-kb="handleCreateKb"
        @confirm-upload="handleUpload"
        @confirm-delete-kb="handleDeleteKb"
        @confirm-new-conv="handleNewConv"
      />

      <Toast :show="toastShow" :message="toastMsg" :type="toastType" @close="toastShow = false" />

      <ChangePassword
        :show="changePasswordShow"
        @close="changePasswordShow = false"
        @success="handleChangePasswordSuccess"
      />

      <!-- Upload indicator -->
      <Transition name="upload-indicator">
        <div v-if="uploading" class="upload-indicator">
          <svg class="upload-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <span class="upload-text">正在上传 {{ uploadingFileName }}...</span>
        </div>
      </Transition>
  </div>
</template>

<style>
/* Global styles */
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  font-family: 'Fira Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  background: #FFFFFF;
  color: #1E293B;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
code, pre { font-family: 'Fira Code', monospace; }
#app { height: 100%; }
</style>

<style scoped>
.app { display: flex; height: 100vh; width: 100vw; padding-top: 48px; }
.sidebar-toggle {
  display: none; position: fixed; top: 12px; left: 12px; z-index: 60;
  background: #fff; border: 1px solid #E2E8F0;
  border-radius: 8px; padding: 8px;
  cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.sidebar-toggle svg { width: 20px; height: 20px; color: #64748B; }

@media (max-width: 768px) {
  .sidebar-toggle { display: flex !important; }
  .app :deep(.sidebar) {
    position: fixed; inset: 0; z-index: 50;
    transform: translateX(-100%);
    transition: transform 200ms ease;
    width: 100%; min-width: 0;
  }
  .app :deep(.sidebar.open) { transform: translateX(0); }
}

/* Upload indicator */
.upload-indicator {
  position: fixed; bottom: 24px; right: 24px; z-index: 200;
  display: flex; align-items: center; gap: 10px;
  background: rgba(99, 102, 241, 0.95);
  color: #fff;
  padding: 12px 20px; border-radius: 12px;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.3);
  font-size: 13px; font-weight: 500;
  pointer-events: none;
}
.upload-spinner {
  width: 18px; height: 18px; flex-shrink: 0;
  animation: spin 1s linear infinite;
}
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.upload-text { white-space: nowrap; }

/* Upload indicator transition */
.upload-indicator-enter-active { transition: all 0.25s ease; }
.upload-indicator-leave-active { transition: all 0.2s ease; }
.upload-indicator-enter-from { opacity: 0; transform: translateY(12px); }
.upload-indicator-leave-to { opacity: 0; transform: translateY(12px); }

/* User bar */
.user-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 48px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  color: white;
}

.user-name {
  font-weight: 600;
  font-size: 14px;
}

.user-email {
  font-size: 12px;
  opacity: 0.8;
}

.user-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-btn {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: white;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.3);
}

.action-btn svg {
  width: 18px;
  height: 18px;
}
</style>
