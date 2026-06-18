# PRD - Pinia Auth Store 重构

## 需求

| ID | 需求 | 验收标准 |
|----|------|---------|
| R1 | 创建 Auth Store | 使用 Pinia 管理 isAuthenticated、currentUser、tokens |
| R2 | 迁移 Token 管理 | 从 api/index.ts 迁移到 auth store，保持 localStorage 持久化 |
| R3 | 创建 useAuth composable | 封装 login/logout/refresh 等业务逻辑，调用 store |
| R4 | 更新 App.vue | 移除认证相关 ref，改用 auth store |
| R5 | 更新 Login.vue | 使用 useAuth composable 替代直接调用 api |

## 技术栈

- 状态管理: Pinia (新增)
- 前端框架: Vue 3 + TypeScript (现有)
- 持久化: localStorage (现有)

## 非功能需求

- 兼容性: 保持现有 API 接口不变
- 测试: 前端构建通过
- 代码量: 预计修改 6 个文件，新增约 80 行代码

## 实现方案

### 新增文件
1. `frontend/src/stores/auth.ts` - Auth Store 定义
2. `frontend/src/composables/useAuth.ts` - Auth composable 封装

### 修改文件
1. `frontend/src/main.ts` - 安装 Pinia
2. `frontend/src/api/index.ts` - 移除 token 管理，改用 store
3. `frontend/src/App.vue` - 使用 auth store 替代本地 ref
4. `frontend/src/components/Login.vue` - 使用 useAuth composable

### Store 设计
```typescript
// stores/auth.ts
export const useAuthStore = defineStore('auth', () => {
  const isAuthenticated = ref(false)
  const currentUser = ref<User | null>(null)
  const accessToken = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)

  // Actions
  function setTokens(access: string, refresh: string) { ... }
  function clearTokens() { ... }
  async function checkAuth() { ... }
  async function login(username: string, password: string, rememberMe?: boolean) { ... }
  async function logout() { ... }
  async function refreshTokens() { ... }
})
```

### Composable 设计
```typescript
// composables/useAuth.ts
export function useAuth() {
  const store = useAuthStore()

  return {
    // State (readonly)
    isAuthenticated: readonly(store.isAuthenticated),
    currentUser: readonly(store.currentUser),

    // Actions
    login: store.login,
    logout: store.logout,
    checkAuth: store.checkAuth,
  }
}
```
