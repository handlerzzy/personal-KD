<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatView from './components/ChatView.vue'
import KbModal from './components/KbModal.vue'
import Toast from './components/Toast.vue'
import { useKb } from './composables/useKb'
import { useConversation } from './composables/useConversation'
import { useChat } from './composables/useChat'
import * as api from './api'

const { kbs, currentKb, fetchKbs, createKb, deleteKb, selectKb } = useKb()
const {
  conversations, currentConv, messages,
  fetchConversations, createConversation, deleteConversation,
  selectConversation, fetchMessages,
} = useConversation()
const { streaming, currentReasoning, currentAnswer, currentSources, sendMessage } = useChat()

const sidebarOpen = ref(true)
const kbDropdownOpen = ref(false)
const modalType = ref<'newKb' | 'upload' | 'deleteKb' | 'newConv' | ''>('')
const modalShow = ref(false)

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

onMounted(() => {
  fetchKbs()

  const mql = window.matchMedia('(max-width: 768px)')
  sidebarOpen.value = !mql.matches
  mql.addEventListener('change', (e) => { sidebarOpen.value = !e.matches })
})

// When KB changes, load conversations
watch(currentKb, async (kb) => {
  if (kb) {
    await fetchConversations(kb.id)
  } else {
    conversations.value = []
    currentConv.value = null
    messages.value = []
  }
})

// When conversation changes, load messages
watch(currentConv, async (conv) => {
  if (conv && currentKb.value) {
    await fetchMessages(currentKb.value.id, conv.id)
  } else {
    messages.value = []
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
}

async function handleUpload(file: File) {
  if (!currentKb.value) return
  try {
    await api.uploadDocument(currentKb.value.id, file)
    showToast(`"${file.name}" 上传成功`, 'success')
    await fetchKbs()
    refreshDocs()
  } catch (e: any) {
    const msg = e.message || '上传失败'
    showToast(`上传失败: ${msg}`, 'error')
  }
}

async function handleDeleteDoc(docId: string) {
  if (!currentKb.value) return
  try {
    await api.deleteDocument(currentKb.value.id, docId)
    showToast('文档已删除', 'success')
    await fetchKbs()
    refreshDocs()
  } catch (e: any) {
    showToast(`删除失败: ${e.message}`, 'error')
  }
}

async function handleDeleteKb() {
  if (!currentKb.value) return
  await deleteKb(currentKb.value.id)
}

async function handleNewConv(title: string) {
  if (!currentKb.value) return
  await createConversation(currentKb.value.id, title)
}

async function handleDeleteConv(convId: string) {
  if (!currentKb.value) return
  await deleteConversation(currentKb.value.id, convId)
}

async function handleSend(query: string) {
  if (!currentKb.value || !currentConv.value || streaming.value) return
  await sendMessage(currentKb.value.id, currentConv.value.id, query, messages.value)
  // Stream finished — refresh messages from server (remove temp user message)
  if (currentKb.value && currentConv.value) {
    messages.value = messages.value.filter(m => !m.id.startsWith('temp-'))
    await fetchMessages(currentKb.value.id, currentConv.value.id)
  }
}
</script>

<template>
  <div class="app">
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
      @upload-doc="showModal('upload')"
      @delete-kb="showModal('deleteKb')"
      @select-conv="selectConversation"
      @create-conv="showModal('newConv')"
      @delete-conv="handleDeleteConv"
      @delete-doc="handleDeleteDoc"
      @toggle-sidebar="sidebarOpen = !sidebarOpen"
    />

    <ChatView
      :current-kb="currentKb"
      :current-conv="currentConv"
      :messages="messages"
      :streaming="streaming"
      :current-reasoning="currentReasoning"
      :current-answer="currentAnswer"
      :current-sources="currentSources"
      @send-message="handleSend"
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
.app { display: flex; height: 100vh; width: 100vw; }
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
</style>
