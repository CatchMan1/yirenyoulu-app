# API契约

适用鸿蒙与iOS，共用 `/api/v1`。协议版本：1.0.0-draft.1；已有共用后端实现，验证范围见[第01期验收](../07测试与交付/第01期验收.md)与[第02期验收](../07测试与交付/第02期验收.md)。客户端按各期范围独立联调与验收。

字段、必填/可空、枚举和各响应结构以 [OpenAPI](openapi.json) 为机器定义；跨字段和事务语义见 [数据传输结构](数据传输结构.md) 与 [联调与兼容规范](联调与兼容规范.md)。虚拟样例见 [协议样例](contract-examples.json)。

## 协议概要

- HTTPS为生产要求；环境域名注入，接口路径不随平台改变。JSON使用UTF-8和snake_case，写请求拒绝未知字段。
- 成功体为`{data,meta,request_id}`；单对象meta=null，分页/游标使用对应meta。204无body；所有响应含X-Request-ID。
- 错误体为`{error:{code,message,details:[{path,code}]},request_id}`，非2xx不伪装成功；details不回显输入。
- UUID字符串、UTC时间以Z结尾、YYYY-MM-DD日历日期、CNY整数分；未知事实为null，单项/预算范围0..100000000，费用汇总上限为JavaScript最大安全整数。
- 私有接口Bearer身份，user_id不接受客户端指定；资源归属错误404。可选身份仅推荐接口：无token可匿名，有无效token返回401。
- 列表page=1起，page_size默认20上限50、page≤10000；消息使用before_sequence排他游标。数组参数重复键编码。

## 接口索引

| 方法/路径 | 功能 | 请求体 | 成功结果 | 身份 |
|---|---|---|---|---|
| POST /auth/register | 注册账户 | RegisterRequest | 201 UserResponse | 公开/凭据端点 |
| POST /auth/login | 用户名或邮箱登录 | LoginRequest | 200 LoginResultResponse | 公开/凭据端点 |
| POST /auth/refresh | 轮换刷新凭据 | RefreshRequest | 200 TokenPairResponse | 公开/凭据端点 |
| POST /auth/logout | 撤销当前会话 | — | 204 无body | 本人 |
| POST /auth/password-reset/request | 请求密码找回邮件 | RecoveryRequest | 202 DeliveryReceiptResponse | 公开/凭据端点 |
| POST /auth/password-reset/confirm | 以单次凭据重置密码 | RecoveryConfirm | 204 无body | 公开/凭据端点 |
| POST /auth/email-verification/request | 请求本人邮箱验证邮件 | — | 202 DeliveryReceiptResponse | 本人 |
| POST /auth/email-verification/confirm | 确认本人邮箱验证 | VerificationConfirm | 204 无body | 本人 |
| GET /me | 读取本人资料 | — | 200 UserResponse | 本人 |
| PATCH /me | 更新本人资料 | ProfileUpdate | 200 UserResponse | 本人 |
| POST /me/password | 修改密码并撤销所有会话 | PasswordChange | 204 无body | 本人 |
| DELETE /me | 注销账户及私有内容 | AccountDelete | 204 无body | 本人 |
| GET /cities | 浏览cities | — | 200 CityPageResponse | 公开/凭据端点 |
| GET /categories | 浏览categories | — | 200 NamedEntryPageResponse | 公开/凭据端点 |
| GET /tags | 浏览tags | — | 200 NamedEntryPageResponse | 公开/凭据端点 |
| GET /places | 搜索和筛选有效地点 | — | 200 PlacePageResponse | 公开/凭据端点 |
| GET /places/{place_id} | 读取有效地点详情 | — | 200 PlaceDetailResponse | 公开/凭据端点 |
| GET /places/{place_id}/navigation | 获取受限供应商导航链接 | — | 200 NavigationResultResponse | 公开/凭据端点 |
| GET /favorites | 浏览本人收藏 | — | 200 PlacePageResponse | 本人 |
| PUT /favorites/{place_id} | 幂等收藏有效地点 | — | 204 无body | 本人 |
| DELETE /favorites/{place_id} | 幂等取消收藏 | — | 204 无body | 本人 |
| GET /trips | 浏览本人行程 | — | 200 TripSummaryPageResponse | 本人 |
| POST /trips | 手动创建空行程；Idempotency-Key必填 | TripCreate | 201 TripResponse | 本人 |
| GET /trips/{trip_id} | 读取本人每日行程 | — | 200 TripResponse | 本人 |
| PATCH /trips/{trip_id} | 按版本编辑本人行程 | TripUpdate | 200 TripResponse | 本人 |
| DELETE /trips/{trip_id} | 按版本删除本人行程 | — | 204 无body | 本人 |
| POST /trips/{trip_id}/items | 添加目录地点并返回完整行程 | TripItemCreate | 201 TripResponse | 本人 |
| PATCH /trips/{trip_id}/items/{item_id} | 编辑地点、日期、时间或备注 | TripItemUpdate | 200 TripResponse | 本人 |
| DELETE /trips/{trip_id}/items/{item_id} | 删除地点并返回新版本行程 | — | 200 TripResponse | 本人 |
| POST /planning-jobs | 创建可恢复的Agent规划任务；Idempotency-Key必填 | PlanningRequest | 202 JobResponse | 本人 |
| GET /planning-jobs | 恢复本人规划任务 | — | 200 JobPageResponse | 本人 |
| GET /planning-jobs/{job_id} | 读取本人任务结果 | — | 200 JobResponse | 本人 |
| DELETE /planning-jobs/{job_id} | 取消未完成任务 | — | 200 JobResponse | 本人 |
| POST /chat-sessions | 新建会话并可绑定本人行程 | ChatSessionCreate | 201 ChatSessionResponse | 本人 |
| GET /chat-sessions | 浏览本人会话 | — | 200 ChatSessionPageResponse | 本人 |
| GET /chat-sessions/{session_id} | 读取本人会话信息 | — | 200 ChatSessionResponse | 本人 |
| PATCH /chat-sessions/{session_id} | 重命名本人会话 | ChatSessionUpdate | 200 ChatSessionResponse | 本人 |
| DELETE /chat-sessions/{session_id} | 删除会话及消息 | — | 204 无body | 本人 |
| GET /chat-sessions/{session_id}/messages | 读取消息并恢复失败或处理中轮次 | — | 200 MessageHistoryResponse | 本人 |
| POST /chat-sessions/{session_id}/messages | 幂等发送一轮消息并返回完整轮次 | MessageCreate | 201 MessageTurnResponse | 本人 |
| POST /behavior-events | 去重接收本人浏览行为 | BehaviorCreate | 202 BehaviorReceiptResponse | 本人 |
| GET /recommendations | 协同或明确偏好/基础推荐 | — | 200 RecommendationResultResponse | 可匿名 |
| GET /health/live | 存活检查 | — | 200 HealthResponse | 公开/凭据端点 |
| GET /health/ready | 必要依赖就绪检查 | — | 200 HealthResponse | 公开/凭据端点 |

## 返回与资源规则

201表示已提交的新资源或幂等重放；202表示已持久化任务/事件或接受送信请求，不表示行程或邮件已完成。所有写入先提交再成功。日期/备注/预算编辑使用相同领域验证器。

行程PATCH及地点POST/PATCH在JSON带version；行程及地点DELETE用query version，不带JSON body。账户DELETE的密码仅在JSON body传递并需网关验证。地点新增201返回完整Trip而不是单个item，客户端以返回version和items整体更新。

公共地点只显示active；失效地点保留在本人收藏和行程快照中并警示，不能新加入行程。收藏幂等返回204；取消不存在的收藏也204。普通用户无目录写接口。

地点搜索与推荐统一explicit_tags（all匹配），不使用tag别名。最高价格必须同时带price_unit，未知价格不满足硬上限；单位不能跨类混比。首版地点估算为null，行程估算单独记录；不从模型伪造地点事实。

## 错误码

| HTTP | code | 处理 |
|---|---|---|
| 400 | BAD_REQUEST | JSON/协议语法非法 |
| 401 | INVALID_CREDENTIALS / SESSION_INVALID / CURRENT_PASSWORD_INVALID | 只有SESSION_INVALID进入会话恢复；凭据或当前密码错误不自动刷新 |
| 403 | ACCOUNT_DISABLED | 清理该账户会话并说明不可用 |
| 404 | NOT_FOUND / PLACE_NOT_FOUND | 资源缺失或不属于本人 |
| 409 | VERSION_CONFLICT / IDEMPOTENCY_CONFLICT / IDEMPOTENCY_KEY_EXPIRED | 拉取最新版本或使用新的明确操作意图 |
| 409 | MESSAGE_IN_PROGRESS / SESSION_BUSY / MESSAGE_RETRY_EXPIRED / JOB_TERMINAL | 读取消息/任务，不并发追加或取消终态 |
| 410 | RESOURCE_DELETED | 原创建结果已删除，不重新生成 |
| 413 | PAYLOAD_TOO_LARGE | 请求体超过64KiB |
| 415 | UNSUPPORTED_MEDIA_TYPE | JSON写请求须application/json |
| 422 | INVALID_INPUT / PLAN_INVALID / BUDGET_EXCEEDED | 修正字段/业务组合 |
| 422 | RECOVERY_TOKEN_INVALID / VERIFICATION_TOKEN_INVALID | 凭据无效/过期/已使用，不暴露细节 |
| 429 | RATE_LIMITED | 按Retry-After整数秒等待 |
| 500 | INTERNAL_ERROR | 保留request_id，不能假装成功 |
| 503 | PROVIDER_UNAVAILABLE | 依赖未配置、失效或免费额度耗尽 |
| 504 | PROVIDER_TIMEOUT | 会话回复外部超时，按消息状态恢复 |

字段错误码为REQUIRED/UNKNOWN_FIELD/INVALID_TYPE/INVALID_FORMAT/OUT_OF_RANGE/INVALID_ENUM/INVALID_COMBINATION，path使用body.version、query.price_unit等稳定字段路径。错误枚举新增应向后兼容，客户端未知码按HTTP类别降级。任务失败error_code与HTTP错误不同：查询已失败任务仍返回200 Job。

## 账户恢复的发布条件

密码找回与邮箱验证契约已经定义；真实送信渠道与应用回链方式待配置。未启用发送服务统一503，不能返回已发送；启用后请求找回对存在/不存在邮箱均202 accepted，避免枚举。重置凭据15分钟、验证凭据30分钟、单次使用且只存摘要。找回成功撤销全部会话，验证凭据必须属于当前登录账户。

短信、微信、订单、支付、预订与数据管理API不属于首版。地图提供方、免费模型和邮箱服务的选择不改变公共协议；未验证的真实服务独立列为发布依赖。

## 实现一致性

实施后从FastAPI/Pydantic导出OpenAPI，与本设计按operationId、路径、字段、必填性、空值、枚举、状态码和鉴权做语义比较；差异先修改契约并审阅，不靠忽略字段或手工强制转换兼容。OpenAPI遵循[官方3.1规范](https://spec.openapis.org/oas/v3.1.0.html)，输出模型按[FastAPI响应模型](https://fastapi.tiangolo.com/tutorial/response-model/)限制公开字段。
