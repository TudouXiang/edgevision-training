# ADR 0007：T020 服务端会话与浏览器防护

状态：proposed / `review_required`（2026-11-04）

## 问题与既有约束

T010 已冻结 `users`、`sessions`、`projects` 表和身份/项目 DTO。架构要求服务端会话、HttpOnly + SameSite=Lax Cookie、修改请求 CSRF、防止默认账号，并由服务端核对角色和 owner。T020 需要落地这些语义，但不应新增 JWT 双轨、注册流程或迁移。

## 最小方案

- 复用 `0002_foundation`，不扩表。随机 session 与 CSRF 原文只发给浏览器，数据库只保存 SHA-256；每次请求重新联表核对撤销、到期和 `users.is_active`。
- 密码使用项目级依赖 `argon2-cffi` 的 Argon2id。未选择标准库 scrypt，是因为既有 schema/任务已明确 Argon2id；未选择 Passlib 是为避免额外包装和过时后端组合。
- 登录签发 HttpOnly `edgevision_session` 和非 HttpOnly、仅供同源前端读取的 `edgevision_csrf`，均为 SameSite=Lax。修改请求同时验证明确 Origin、CSRF Cookie、`X-CSRF-Token` 和数据库哈希。
- 缺失或 `null` Origin 一律拒绝。默认允许列表仅包含 127.0.0.1/localhost 的 5173、8000 开发 Origin。自定义非本机 Origin 必须 HTTPS；HTTPS Origin 必须显式启用 Secure Cookie；非法配置返回 503，不降级为宽松模式。
- 修改密码在同一写事务撤销该用户全部旧会话并签发新 session/CSRF。禁用用户同时撤销其会话；最后一个启用管理员不能被禁用。
- 所有业务写入先 `BEGIN IMMEDIATE`，随后在同一事务重新鉴权并写入。普通用户访问他人对象统一 404；管理员可跨项目；归档保留记录并拒绝新上传/新任务。
- 首个启用管理员只由显式、交互式 CLI 创建。密码不接受命令行参数、不写日志；已有启用管理员时 CLI 拒绝继续，后续账号通过已认证管理接口创建。

## 公共契约与兼容性

请求/成功 DTO 和数据库结构不变。OpenAPI 只补充实际 401/403/409/501 响应元数据，并把 API 版本标为 0.2.0。旧客户端若未发送 Origin/CSRF，将被安全拒绝；正式浏览器前端已同步读取 CSRF Cookie。开发默认 Origin 保持 Vite 5173 → API 8000 流程可用。

## 未选方案

- JWT：会造成撤销/禁用的第二套状态和更复杂的轮换，不符合现有 Session 表。
- 只依赖 SameSite：不能替代显式 CSRF 和 Origin 检查。
- 自动生成管理员或从源码/固定环境值读取默认密码：会产生真实默认凭据，明确禁止。
- 为配置增加数据库字段：环境边界不需要迁移，增加了不必要的恢复成本。

## 失败、回退与验证

代码回退不需要数据库降级；`argon2id` 密码哈希若已有真实用户，不得在未迁移密码前回退到不识别该格式的版本。验证覆盖正确/错误密码、Origin/CSRF、Cookie 属性、到期/撤销/禁用、改密轮换、最后管理员、owner 404、归档 409、CLI 无默认账号和契约漂移。真实浏览器在当前执行环境不可达，保持 NOT_RUN，见 T020 报告。
