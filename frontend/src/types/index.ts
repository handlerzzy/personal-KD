export interface KnowledgeBase {
  id: string
  name: string
  description: string
  created_at: string
  doc_count: number
  conv_count: number
}

export interface KBDocument {
  id: string
  kb_id: string
  filename: string
  file_type: string
  file_size: number
  chunk_count: number
  created_at: string
}

export interface Conversation {
  id: string
  kb_id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface Message {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  reasoning_content?: string
  sources?: Source[]
  created_at: string
}

export interface Source {
  chunk_id: string
  text: string
  score: number
  doc_id?: string
}
