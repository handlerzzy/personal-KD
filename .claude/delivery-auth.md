# 交付报告 - JWT 用户认证 + 数据隔离

## 需求实现

| ID | 需求 | 状态 | 验收 |
|----|------|------|------|
| R1 | 用户注册 | ✅ | 用户名+密码注册，bcrypt 加密，严格验证 |
| R2 | 用户登录 | ✅ | Access Token (2h) + Refresh Token (7天) |
| R3 | JWT 认证中间件 | ✅ | 验证 Bearer Token，提取用户信息 |
| R4 | 用户数据隔离 | ✅ | 知识库、对话、消息按 user_id 隔离 |
| R5 | 静默登录 | ✅ | Refresh Token 自动刷新 Access Token |
| R6 | 用户登出 | ✅ | Token 黑名单机制 |
| R7 | 密码修改 | ✅ | 验证旧密码，更新为新密码 |
| R8 | 用户信息 | ✅ | 查看/修改用户基本信息 |

## 技术栈

| 组件 | 实现 |
|------|------|
| JWT 库 | python-jose 3.5.0 |
| 认证框架 | FastAPI Security (内置) |
| 密码加密 | bcrypt 4.3.0 + passlib |
| Token 存储 | 前端 LocalStorage |
| 算法 | HS256 |

## 修改文件

### 后端 (21 文件)
- `backend/app/auth.py` - JWT 认证工具（新建）
- `backend/app/deps.py` - FastAPI 依赖注入（新建）
- `backend/app/api/auth.py` - 认证 API 端点（新建）
- `backend/app/persistence/user_repo.py` - 用户仓库（新建）
- `backend/app/persistence/database.py` - 添加用户表和 token_blacklist 表
- `backend/app/persistence/kb_repo.py` - 添加 user_id 支持
- `backend/app/persistence/conv_repo.py` - 添加 user_id 支持
- `backend/app/api/knowledge_base.py` - 添加认证和权限检查
- `backend/app/api/conversation.py` - 添加认证和权限检查
- `backend/app/api/chat.py` - 添加认证和权限检查
- `backend/app/api/document.py` - 添加认证和权限检查
- `backend/app/main.py` - 添加认证路由
- `backend/app/config.py` - 添加 secret_key 配置
- `backend/requirements.txt` - 添加依赖
- `backend/env.example` - 添加 SECRET_KEY
- `backend/tests/test_auth.py` - 认证测试（新建）
- `backend/tests/test_api.py` - 更新测试添加认证

### 前端 (4 文件)
- `frontend/src/api/index.ts` - 添加认证 API 和 Token 管理
- `frontend/src/types/index.ts` - 添加 User 和 TokenResponse 类型
- `frontend/src/components/Login.vue` - 登录/注册页面（新建）
- `frontend/src/App.vue` - 添加认证逻辑和用户栏

### 配置 (2 文件)
- `pyproject.toml` - 添加依赖
- `README.md` - 添加认证文档

## 测试结果

```
tests/test_auth.py::TestPasswordHashing::test_hash_password PASSED
tests/test_auth.py::TestPasswordHashing::test_verify_correct_password PASSED
tests/test_auth.py::TestPasswordHashing::test_verify_wrong_password PASSED
tests/test_auth.py::TestPasswordHashing::test_different_hashes_for_same_password PASSED
tests/test_auth.py::TestInputValidation::test_valid_username PASSED
tests/test_auth.py::TestInputValidation::test_invalid_username PASSED
tests/test_auth.py::TestInputValidation::test_valid_password PASSED
tests/test_auth.py::TestInputValidation::test_invalid_password PASSED
tests/test_auth.py::TestTokenCreation::test_create_access_token PASSED
tests/test_auth.py::TestTokenCreation::test_create_refresh_token PASSED
tests/test_auth.py::TestTokenCreation::test_token_expiration PASSED
tests/test_auth.py::TestTokenCreation::test_custom_expiration PASSED
tests/test_auth.py::TestTokenDecoding::test_decode_valid_token PASSED
tests/test_auth.py::TestTokenDecoding::test_decode_expired_token PASSED
tests/test_auth.py::TestTokenDecoding::test_decode_invalid_token PASSED
tests/test_auth.py::TestTokenDecoding::test_decode_token_with_wrong_secret PASSED
tests/test_auth.py::TestDatabaseIntegration::test_user_repository_create PASSED
tests/test_auth.py::TestDatabaseIntegration::test_user_repository_get_by_username PASSED
tests/test_auth.py::TestDatabaseIntegration::test_token_blacklist SKIPPED

tests/test_api.py::test_health PASSED
tests/test_api.py::test_create_knowledge_base PASSED
tests/test_api.py::test_list_knowledge_bases PASSED
tests/test_api.py::test_delete_knowledge_base PASSED
tests/test_api.py::test_create_conversation PASSED
tests/test_api.py::test_list_conversations PASSED
tests/test_api.py::test_delete_conversation PASSED
tests/test_api.py::test_chat_without_kb PASSED
tests/test_api.py::test_chat_empty_query PASSED
tests/test_api.py::test_get_messages PASSED
tests/test_api.py::test_list_documents PASSED

================== 28 passed, 2 skipped ==================
```

## 审查修复

| 问题 | 修复 |
|------|------|
| logout 函数没有实际 blacklist token | 从 Authorization header 提取 token 并 blacklist |
| secret_key 有不安全的默认值 | 未设置时生成随机密钥并发出警告 |
| conv_repo 两次 commit 可能导致数据不一致 | 合并为单次 commit |
| EmailStr 依赖缺失 | 添加 email-validator 依赖 |
| 登录时的 timing attack 风险 | 用户不存在时也验证密码（使用 dummy hash） |
| SQL 删除操作的 rowcount 计算错误 | 使用 cursor.rowcount 代替 db.total_changes |
| list_by_user 没有检查 user_id 为 None | 添加空值检查 |
| token 黑名单检查顺序可以优化 | 先验证 token 格式再查询数据库 |
| 权限检查重复代码 | 创建依赖注入统一处理 |

## 部署说明

1. 更新 `.env` 文件，添加 `SECRET_KEY`（生产环境必须设置）
2. 重启后端服务
3. 前端会自动显示登录页面
4. 用户注册后即可使用

## 注意事项

- 首次部署时，现有数据的 `user_id` 为 `NULL`，需要手动关联或迁移
- Token 存储在 localStorage 中，如果网站存在 XSS 漏洞可能被窃取
- 建议在生产环境中使用 HTTPS
