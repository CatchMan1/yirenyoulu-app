# /api/v1 契约基线
状态：设计，不表示已实现。实现后以 Pydantic 导出的 OpenAPI 为机器校验基线；前端不得使用 ESObject 掩盖契约分歧。

## 通用
UUID 用字符串；日期 YYYY-MM-DD；UTC timestamp 带 Z；金额整数分；未知字段 null。所有写请求拒绝未知字段。成功 `{"data": ..., "meta": null, "request_id": "uuid"}`；列表 data 数组，meta={page,page_size,total}。错误 `{"error":{"code":"...","message":"用户可理解内容","details":[]},"request_id":"uuid"}`。204 无 body。验证 details 只含字段路径与错误码，不回显密码或输入。服务端生成 request_id。Authorization Bearer；资源归属绝不信任客户端 user_id。

## 路由
| 方法/路径 | 输入与成功响应 | 身份及失败 |
|---|---|---|
| POST /auth/register | username(3..50), email, password(12..128), nickname? → 201 User | 匿名；409 ACCOUNT_CONFLICT，422 INVALID_INPUT；注册不等于邮箱已验证 |
| POST /auth/login | identifier(用户名/邮箱), password → 200 TokenPair+User | 匿名；401 INVALID_CREDENTIALS；429 RATE_LIMITED |
| POST /auth/refresh | refresh_token → 200 TokenPair | 轮换；401 SESSION_INVALID；重放撤销会话 |
| POST /auth/logout | 无 → 204 | 当前会话撤销；过期令牌 401 |
| GET /me | → User | 本人 |
| PATCH /me | nickname?, signature?, preferences? → User | 本人；禁止改权限/状态 |
| POST /me/password | current_password,new_password → 204 | 本人，撤销所有会话 |
| DELETE /me | current_password → 204 | 本人；注销删除/匿名化策略有文档并撤销会话 |
| GET /cities, /categories, /tags | → 分页目录 | 匿名 |
| GET /places | q?, city_id?, kind?, category_id?, tag?, price_max_minor?, price_unit?, page,page_size → Place[] | 匿名仅 active；未知价格不谎称满足价格上限 |
| GET /places/{id} | → PlaceDetail | 匿名；404 PLACE_NOT_FOUND |
| GET /places/{id}/navigation | → {status,crs,destination,url?,reason?} | 匿名；无坐标返回 unavailable，前端保留地址 |
| GET /favorites | → Place[] | 本人 |
| PUT /favorites/{place_id} | 无 → 204 | 本人，幂等；必须有效地点 |
| DELETE /favorites/{place_id} | 无 → 204 | 本人，幂等 |
| POST /trips | Idempotency-Key；title,city_id,start_date,end_date,budget_minor?,preferences → 201 Trip | 本人手动建草稿 |
| GET /trips | q?（标题关键词≤100）,分页 → TripSummary[] | 本人 |
| GET /trips/{id} | → Trip，items 按日期/顺序，快照与当前有效状态 | 本人；跨用户404 |
| PATCH /trips/{id} | version,title?,start_date?,end_date?,budget_minor? → Trip | 本人；409 VERSION_CONFLICT；缩短日期不得留下越界 items |
| DELETE /trips/{id} | query version → 204 | 本人；级联处理 items、会话可选关联置空 |
| POST /trips/{id}/items | version,place_id,date,start_minute,end_minute,note? → 201 Trip | 本人；全行程校验/快照/版本增长 |
| PATCH /trips/{id}/items/{item_id} | version,place_id?,date?,start_minute?,end_minute?,note? → Trip | 本人；验证 item 的 trip_id |
| DELETE /trips/{id}/items/{item_id} | query version → Trip | 本人；版本增长 |
| POST /planning-jobs | Idempotency-Key header；city_id,start_date,end_date,budget_minor?,preferences,explicit_tags?,request_text → 202 Job | 本人；同键同输入复用任务，不同输入409 |
| GET /planning-jobs | status?（可重复传值）,page,page_size → Job[] | 本人；按created_at/id倒序；恢复未终态任务 |
| GET /planning-jobs/{id} | → Job(status,trip_id?,error_code?,warnings[]) | 本人；成功表示行程曾完整提交；主动删除后result_deleted=true，不重建 |
| DELETE /planning-jobs/{id} | → Job | 本人；未终态可取消，终态409 |
| GET/POST /chat-sessions | 分页；创建 title?,trip_id? → 201 Session | 本人；绑定行程须属于本人 |
| PATCH/DELETE /chat-sessions/{id} | title / 无 → Session / 204 | 本人 |
| GET /chat-sessions/{id}/messages | before_sequence?,limit<=50 → Message[] | 本人 |
| POST /chat-sessions/{id}/messages | message_id(UUID),content(1..4000) → 201 MessageTurn | 本人；请求幂等；provider失败503/超时504，历史保留可重试状态 |
| POST /behavior-events | event_id,place_id,type(view),occurred_at → 202 | 本人；事件去重；favorite/unfavorite/trip_add由服务端成功写入触发 |
| GET /recommendations | city_id?,kind?,limit<=20,explicit_tags?,preferred_tags?,price_max_minor?,price_unit? → {items,reason,algorithm_version} | 匿名基础兜底，登录可协同；硬约束优先 |
| GET /health/live,/health/ready | → 存活/依赖就绪 | 无敏感配置输出；DB未就绪503 |

User 不返回 hash、权限内部字段或 token。TokenPair 为 access_token,refresh_token,token_type=Bearer,expires_in=900；仅认证响应返回。Place 包含 id/kind/name/city/category/tags/address/coordinates{longitude,latitude,crs}|null/price事实或null/estimate或null/status/provenance/is_test。Job 状态与设计文档相同。

## 跨模块不变量
- 端到端 201/202/204 与错误码均需鸿蒙和 React Native 两端契约测试；分页总数来自相同过滤条件。
- 任务 request_text 是本次明确要求；历史推荐仅为候选排序，不作为硬约束覆盖当前输入。
- day/date/时间范围、重复地点、费用未知与越界、destination 等规则使用同一验证器。
- 公共地点管理不开放普通用户写接口；数据导入由受限离线命令和专用账号完成。
- 模拟服务响应包含 provider_mode=mock，fixture 仅存在开发/测试库；production 启动检查拒绝 mock。

## 字段规范与价格过滤

字段定义、快照、费用、任务结果删除、手动创建幂等和DELETE版本参数以[数据传输结构](数据传输结构.md)为准。GET /favorites保留失效地点摘要（status=inactive）供查看与取消收藏；不开放其新加入行程能力。

价格过滤：GET /places与GET /recommendations提交price_max_minor时必须同时提交price_unit=entry/night/person，否则422；过滤只匹配同单位已知价格，不跨单位比较。price_unit单独提交可筛同单位，未知价格不进入硬上限结果。
