# T020：身份与项目最小闭环

执行者：DeepSeek/GPT5.6。前置：T010 accepted，状态blocked。使用feature-delivery。

目标：真实账号/会话、管理员初始化和普通账号管理、项目所有权、归档、最小相关页面。复用骨架Schema与服务，不引入第三方登录、JWT双轨、邮件验证码或注册流程。

允许：auth/project服务与路由、必要DB查询、对应前端与测试。公共Schema更改先走arch-spec。

验收：正确/错误密码、过期/撤销/禁用、修改密码撤销会话、CSRF、重复用户名、普通用户不能访问/修改他人项目，归档不删历史且禁止新任务。初始化密码不写源码与日志。

证据：pytest、相关前端测试与最小浏览器操作；A05先覆盖已有资源，后续任务持续补齐派生资源权限。输出docs/evidence/T020-report.md，标review_required。
