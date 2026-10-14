# 一人有路发布基础 Implementation Plan

> 2026-10-14 iOS分支调整：当前分支前端按 React Native/iOS 方向推进，见 [iOS分支说明](../../ios-branch.md)。本文原有鸿蒙前端步骤保留为历史，业务与安全要求继续有效。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 按下列勾选项记录真实进度，不把静态检查标为联调通过。

**Goal:** 在独立 GitHub 仓库建立安全可验证的新版，先通过测试数据闭环，再决定真实采集与发布。

**Architecture:** 单仓库 ArkTS 前端与 FastAPI 模块化单体，独立构建部署。PostgreSQL 为唯一集成/生产数据库，持久化任务 worker 通过受控工具调用 AI，所有保存经过服务端验证与事务。

**Tech Stack:** ArkTS/ArkUI API21 基线，Python3.11、FastAPI、SQLAlchemy2、Alembic、PostgreSQL、pytest。

**Spec:** ../specs/2026-10-13-release-design.md；../../api-contract.md。

## Global Constraints
- 原项目代码、Git 历史、Gitee 远程配置和数据库只读；不得向 Gitee 推送。
- 独立目录、Git 历史、数据库、配置、运行环境；保留 GitHub 已有工作，不强推。
- 用户名/邮箱与密码先上线；短信后续；高德地图；AI 只用免费接口，不产生费用或接受商业协议。
- 真实行为驱动协同过滤，数据不足明确兜底；本次明确输入优先；不再依赖 TOPSIS/熵权/概率字段。
- 正式采集在测试数据闭环验收通过后进行；测试数据不可冒充真实地点或行为。
- 实施方法：当前会话直接执行；仅设计审阅按技能交给独立审阅者。用户已授权常规技术决定自行推进，不为常规步骤重复请求批准。

## Review Focus
- 事务失败、进程重启或重复生成不能返回成功或生成重复行程（任务4）。
- 任意用户提供其他用户的 UUID、子资源 ID、session_id 不能读写他人数据（任务3、4、6）。
- 未知价格、空坐标、失效地点不得转成虚假零值/可导航状态（任务2、4、5）。
- token 过期、refresh 重放、并发编辑不应丢用户数据或绕过撤销（任务3、4、7）。
- 前端 HTTP 201/202/204、离页轮询与失败重试不得误报成功（任务7）。

---

### Task 1: 隔离、审查与发布防护
**Files:** README.md、.gitignore、.env.example、scripts/check_repository.py、tests/test_repository_guard.py、.github/workflows/checks.yml、docs/source-audit.md、docs/stages/01-foundation.md。
**Interfaces:** 输入旧前后端只读源码；输出独立 GitHub 仓库和经审查文件清单。`check_repository.py [--history]` 非零表示阻断提交/发布，仅输出路径与规则。
- [x] 只读确认旧工作树、远程、HEAD，检查 GitHub 仓库无现有 refs。
- [x] 克隆到独立同级目录，不复制旧历史；写下历史取舍与审查证据。
- [x] 编写 guard 测试：禁止数据库/签名/.env、检测可疑凭据，允许空白环境样例；历史某旧提交含禁止文件也必须失败。
- [x] 运行测试确认失败；实现禁止文件名和文本凭据检查（源码迁入允许清单尚待前端阶段）；重新运行通过。
- [x] 配置 CI，并验证当前暂存及所有可达历史；创建独立阶段提交，普通 push 前重新读远端 refs。

### Task 2: 契约与数据库基础
**Files:** backend/app/settings.py、backend/app/db.py、backend/app/models.py、backend/alembic/env.py、backend/alembic/versions/0001_initial.py、backend/tests/test_schema.py、docs/database.md、compose.yaml。
**Interfaces:** `Settings` 从显式环境读取；`Base.metadata`；`make_engine(url)`；`SessionLocal`；所有 UUID 字符串遵循契约。Alembic URL 来自同一隔离配置。
- [x] 编写 PostgreSQL 迁移测试：空库 upgrade head，downgrade base，再 upgrade；非法坐标/重复来源ID/重复收藏/重复任务幂等键拒绝。
- [x] 建立独立 .venv，锁定直接依赖；实现迁移、约束和禁止连接旧数据库的环境检查。
- [x] 测试先失败、实现后通过；SQLite 快速测试独立标注，PostgreSQL CI run 38287209151通过。
- [x] 初始化仅 migrate；fixture 导入为独立显式命令，APP_ENV=production 必须拒绝。
- [x] 编写 pg_dump/pg_restore 及隔离恢复演练说明；执行本地可用验证，集成验证缺环境明确阻塞。
- [x] 提交并推送验证过的基础工作，汇报尚未验证项。

### Task 3: 认证、目录、收藏
**Files:** backend/app/auth.py、backend/app/catalog.py、backend/app/favorites.py、backend/app/main.py、backend/tests/test_auth.py、test_catalog.py、test_permissions.py。
**Interfaces:** `current_user(credentials, db)->User`；`register/login/refresh` 使用契约；目录 PlaceView 仅返回 public 字段；统一 error handler。
- [ ] 写测试：注册201；错误登录401；hash不出现在响应；改密/登出后旧会话失败；refresh重放撤销；A无法操作B收藏。
- [ ] 实现认证轮换、Argon2、限流与错误处理；可选邮件恢复未接入时明确禁用。
- [ ] 写测试：三类地点搜索/过滤/分页、无效类型422、未知价格不伪造、无坐标导航降级；实现参数化查询与来源标签。
- [ ] 收藏唯一约束和幂等；成功事务内发行为事件；回滚不留事件。
- [ ] 运行 pytest 和 OpenAPI 契约快照检查，通过后提交。

### Task 4: 行程 CRUD、校验和 Agent 任务
**Files:** backend/app/trips.py、backend/app/planning/{service,tools,worker,providers}.py、backend/tests/test_trips.py、test_planning.py。
**Interfaces:** `validate_items(trip, items, places)->ValidationResult`；`Planner.plan(input, tools)->PlanDraft`；`run_job(job_id)->None`；`search_places(city_id,kind,tags,limit)` 只返回有效目录事实。
- [ ] 写双用户行程/子资源权限、版本冲突、日期收缩、地点失效、跨城市、重叠、重复、预算缺失与不足的失败测试。
- [ ] 实现单事务 CRUD 与快照；受控 allowlist 工具；MockPlanner 只在开发/测试可启用。
- [ ] 写任务重复键同输入复用/不同输入409、并发领取、deadline、取消、worker重启/lease回收测试；保存注入失败后无残留行程且不成功。
- [ ] 实现持久任务状态与原子保存，禁止无限重试和隐式付费 provider。
- [ ] PostgreSQL 集成通过后提交；没有模型凭据时报告工具链模拟通过、真实模型未验证。

### Task 5: 行为与协同推荐
**Files:** backend/app/recommendations.py、backend/tests/test_recommendations.py。
**Interfaces:** `recommend(user_id, explicit_filters)->RecommendationResult`；result 含 reason/algorithm_version，候选使用 PlaceView。
- [ ] 写稀疏已知矩阵计算断言、重复事件去重、test事件隔离、阈值不足、已失效/跨城市过滤测试。
- [ ] 实现有界窗口、item-item 相似度及基础/偏好兜底；本次过滤在排序前后均保证。
- [ ] 验证无需旧算法字段，不记录个性化有效性结论；提交。

### Task 6: AI 历史与免费 provider 边界
**Files:** backend/app/chat.py、backend/app/planning/providers.py、backend/tests/test_chat.py、docs/providers.md。
**Interfaces:** `ChatProvider.reply(messages, tools)->Reply`，messages 来自本人 session 最近20条，有大小上限；服务端验证 trip 归属。
- [ ] 写会话越权、不同会话历史隔离、重发 message_id、连续两轮 context、超时/缺配置/免费额度耗尽测试。
- [ ] 实现有界历史、消息状态与重试幂等，失败不保存伪造正常答复。
- [ ] 调研免费API官方条款、地域/商业限制/工具调用/额度；没有可确认方案不启用真实 provider，不接受协议。
- [ ] 模拟通过后提交；真实模型验证需配置和免费使用授权，独立记录。

### Task 7: ArkTS 迁入与端到端闭环验收
**Files:** frontend/entry/src/main/ets/{services/ApiService.ets,models/*,pages/*,common/*}、frontend/build-profile.json5、frontend/entry/src/ohosTest/ets/test/*、docs/stages/04-acceptance.md。
**Interfaces:** 仅 `/api/v1`，统一 typed ApiResult、UUID、JobState；前端页面消费新契约，移除短信/订单/支付入口。
- [ ] 允许清单迁入现有页面/组件，移除签名、硬编码地址、敏感日志与未经授权远程资源。
- [ ] 写状态/HTTP201/202/204/401/重试保留幂等键测试；改造网络层 finally.destroy、取消和会话失效。
- [ ] 分页完成登录资料、目录搜索详情、收藏、行程及地点编辑、任务轮询、地图文本降级、AI历史；统一空/失败/重试状态。
- [ ] 用标记测试数据执行注册→浏览→收藏→生成→编辑→地图→连续对话→退出/注销，两个用户分别验证隔离。
- [ ] DevEco 编译、模拟器或真机录制证据；高德/真实免费AI独立标注是否验证；未通过不得进入任务8。

### Task 8: 后续受门控阶段
**Files:** docs/data-sources.md、backend/app/imports/*、docs/deployment.md、docs/release-checklist.md。
- [ ] D验收后集中确认首批城市/数量、数据源商用/存储/更新/图片范围、免费额度和费用。
- [ ] 仅少量真实样本导入，外部ID去重、校验、重试/检查点/增量/失效；未知事实保持未知。
- [ ] 样本业务回归后扩大；移除fixture后的全回归。
- [ ] 部署环境TLS/备份恢复/限流/监控/迁移/回滚，正式签名在本地安全配置；核查当时上架条款、隐私和账户删除。

## 推进记录
当前具体完成/验证见 `docs/stages/`。任务未勾选即未完成，外部依赖不得用文档代替执行证据。每个阶段普通 push 到指定 GitHub，失败保留本地提交和真实错误，不向 Gitee 或其他仓库推送。
