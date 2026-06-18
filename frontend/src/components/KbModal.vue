<script setup lang="ts">
import { ref, watch } from 'vue'
import type { KnowledgeBase } from '../types'

const props = defineProps<{
  show: boolean
  type: 'newKb' | 'upload' | 'deleteKb' | 'newConv' | ''
  currentKb: KnowledgeBase | null
}>()

const emit = defineEmits<{
  close: []
  confirmNewKb: [name: string, desc: string]
  confirmUpload: [file: File]
  confirmDeleteKb: []
  confirmNewConv: [title: string]
}>()

const newKbName = ref('')
const newKbDesc = ref('')
const newConvTitle = ref('')
const selectedFile = ref<File | null>(null)
const uploadFileName = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

watch(() => props.show, (val) => {
  if (val) {
    newKbName.value = ''
    newKbDesc.value = ''
    newConvTitle.value = ''
    selectedFile.value = null
    uploadFileName.value = ''
  }
})

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files && input.files[0]) {
    selectedFile.value = input.files[0]
    uploadFileName.value = input.files[0].name
  }
}

function confirmNewKb() {
  if (newKbName.value.trim()) {
    emit('confirmNewKb', newKbName.value.trim(), newKbDesc.value.trim())
    emit('close')
  }
}

function confirmUpload() {
  if (selectedFile.value) {
    emit('confirmUpload', selectedFile.value)
    emit('close')
  }
}

function confirmDeleteKb() {
  emit('confirmDeleteKb')
  emit('close')
}

function confirmNewConv() {
  const title = newConvTitle.value.trim() || '新对话'
  emit('confirmNewConv', title)
  emit('close')
}

function close() {
  emit('close')
}
</script>

<template>
  <div class="modal-overlay" :class="{ open: show && type }" @click.self="close">
<!-- New KB -->
    <div v-if="type === 'newKb'" class="modal">
      <h2>新建知识库</h2>
      <input v-model="newKbName" type="text" placeholder="知识库名称" @keydown.enter="confirmNewKb">
      <input v-model="newKbDesc" type="text" placeholder="描述（可选）" @keydown.enter="confirmNewKb">
      <div class="modal-actions">
        <button @click="close">
取消
</button>
        <button class="primary" @click="confirmNewKb">
创建
</button>
      </div>
    </div>

    <!-- Upload -->
    <div v-if="type === 'upload'" class="modal">
      <h2>上传文档</h2>
      <div class="upload-area" @click="fileInputRef?.click()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:24px;height:24px;display:block;margin:0 auto 8px;">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <p v-if="!uploadFileName">
点击选择文件
</p>
        <p v-else style="color:#6366F1;">
已选择: {{ uploadFileName }}
</p>
        <p class="hint">
支持 PDF, TXT, Markdown
</p>
      </div>
      <input ref="fileInputRef" type="file" accept=".pdf,.txt,.md" style="display:none" @change="onFileChange">
      <div class="modal-actions">
        <button @click="close">
取消
</button>
        <button class="primary" :disabled="!selectedFile" @click="confirmUpload">
上传
</button>
      </div>
    </div>

    <!-- Delete KB -->
    <div v-if="type === 'deleteKb'" class="modal">
      <h2 style="color:#EF4444;">
删除知识库
</h2>
      <p class="confirm-text">
确定删除「{{ currentKb?.name }}」？<br>所有文档和对话将被永久删除。
</p>
      <div class="modal-actions">
        <button @click="close">
取消
</button>
        <button class="danger" @click="confirmDeleteKb">
确认删除
</button>
      </div>
    </div>

    <!-- New Conversation -->
    <div v-if="type === 'newConv'" class="modal">
      <h2>新建对话</h2>
      <input v-model="newConvTitle" type="text" placeholder="对话标题" @keydown.enter="confirmNewConv">
      <div class="modal-actions">
        <button @click="close">
取消
</button>
        <button class="primary" @click="confirmNewConv">
创建
</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,0.3);
  z-index: 100;
  align-items: center; justify-content: center;
}
.modal-overlay.open { display: flex; }
.modal {
  background: #fff; border-radius: 12px;
  padding: 24px; width: 400px; max-width: 90vw;
  box-shadow: 0 4px 24px rgba(0,0,0,0.08);
  animation: fadeIn 0.2s ease;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
.modal h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #1E293B; }
.modal input {
  width: 100%; padding: 8px 12px;
  border: 1px solid #CBD5E1; border-radius: 8px;
  font-family: inherit; font-size: 14px;
  margin-bottom: 12px; outline: none;
  transition: border-color 200ms ease;
}
.modal input:focus { border-color: #6366F1; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; }
.modal-actions button {
  padding: 8px 16px; border-radius: 8px;
  font-family: inherit; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all 200ms ease;
  border: 1px solid #CBD5E1;
  background: #fff; color: #1E293B;
}
.modal-actions button:hover { background: #F1F5F9; }
.modal-actions button.primary { background: #6366F1; color: white; border-color: #6366F1; }
.modal-actions button.primary:hover { background: #4F46E5; }
.modal-actions button.primary:disabled { opacity: 0.5; cursor: not-allowed; }
.modal-actions button.danger { background: #EF4444; color: white; border-color: #EF4444; }
.modal-actions button.danger:hover { background: #DC2626; }

.upload-area {
  border: 2px dashed #CBD5E1; border-radius: 8px;
  padding: 24px; text-align: center; cursor: pointer;
  transition: all 200ms ease; margin-bottom: 12px;
}
.upload-area:hover { border-color: #6366F1; background: #F8FAFC; }
.upload-area p { font-size: 13px; color: #64748B; }
.upload-area .hint { font-size: 11px; color: #94A3B8; margin-top: 4px; }
.confirm-text { font-size: 14px; color: #64748B; margin-bottom: 16px; line-height: 1.6; }
</style>
