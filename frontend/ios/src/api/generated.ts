export interface paths {
    "/auth/email-verification/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 确认本人邮箱验证
         * @description 令牌归属当前账户，有效期30分钟，错误统一422 VERIFICATION_TOKEN_INVALID。
         */
        post: operations["confirmVerification"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/email-verification/request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 请求本人邮箱验证邮件
         * @description 邮箱已验证也返回accepted；发送频率受限。
         */
        post: operations["requestVerification"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 用户名或邮箱登录
         * @description 拒绝无效凭据统一INVALID_CREDENTIALS；认证响应no-store。
         */
        post: operations["login"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 撤销当前会话
         * @description 撤销当前会话
         */
        post: operations["logout"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/password-reset/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 以单次凭据重置密码
         * @description 有效期15分钟，成功后撤销全部会话；过期、无效、已使用均422 RECOVERY_TOKEN_INVALID。
         */
        post: operations["confirmPasswordReset"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/password-reset/request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 请求密码找回邮件
         * @description 启用邮件时始终202，不暴露邮箱是否存在；未配置提供方对所有邮箱统一503。
         */
        post: operations["requestPasswordReset"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 轮换刷新凭据
         * @description 不自动重试；旧令牌重放撤销其会话。网络丢失旋转结果时重新登录。
         */
        post: operations["refresh"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 注册账户
         * @description 注册账户
         */
        post: operations["register"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/behavior-events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 去重接收本人浏览行为
         * @description 只接受view；相同event_id和输入重放duplicate，异输入409；occurred_at最大偏差5分钟。 先匹配已有事件及摘要，重复/冲突判断早于时间窗口；5分钟限制仅首次接收。
         */
        post: operations["recordBehavior"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/categories": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 浏览categories
         * @description 浏览categories
         */
        get: operations["listCategories"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/chat-sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 浏览本人会话
         * @description 浏览本人会话
         */
        get: operations["listChatSessions"];
        put?: never;
        /**
         * 新建会话并可绑定本人行程
         * @description 空对象{}合法；不自动重试创建，首版会话新建不承诺幂等。
         */
        post: operations["createChatSession"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/chat-sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 读取本人会话信息
         * @description 读取本人会话信息
         */
        get: operations["getChatSession"];
        put?: never;
        post?: never;
        /**
         * 删除会话及消息
         * @description 处理中回复不得在会话删除后重新写入。
         */
        delete: operations["deleteChatSession"];
        options?: never;
        head?: never;
        /**
         * 重命名本人会话
         * @description 重命名本人会话
         */
        patch: operations["updateChatSession"];
        trace?: never;
    };
    "/chat-sessions/{session_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 读取消息并恢复失败或处理中轮次
         * @description 读取消息并恢复失败或处理中轮次
         */
        get: operations["listMessages"];
        put?: never;
        /**
         * 幂等发送一轮消息并返回完整轮次
         * @description message_id绑定会话/内容；同成功请求重放201，不同内容409；本轮处理中返回409 MESSAGE_IN_PROGRESS；失败可同键重试，最多一轮运行。 仅最后一轮失败消息可原位重试；存在更晚用户轮次时409 MESSAGE_RETRY_EXPIRED。上下文仅使用当前轮之前的成功完整轮次。
         */
        post: operations["sendMessage"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/cities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 浏览cities
         * @description 浏览cities
         */
        get: operations["listCities"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/favorites": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 浏览本人收藏
         * @description 包括inactive摘要；按收藏时间/id倒序。
         */
        get: operations["listFavorites"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/favorites/{place_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 读取本人单地点收藏状态
         * @description 仅查询当前用户的收藏关系，不检查地点是否存在或可展示；合法UUID没有本人收藏时返回false，已有失效或来源撤回的本人收藏仍返回true。不暴露其他用户收藏，不产生行为事件。
         */
        get: operations["getFavoriteStatus"];
        /**
         * 幂等收藏有效地点
         * @description 已收藏返回204不新增行为；未收藏但地点失效404。
         */
        put: operations["addFavorite"];
        post?: never;
        /**
         * 幂等取消收藏
         * @description 本人没有此收藏也204，不改变其他用户收藏。
         */
        delete: operations["removeFavorite"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 存活检查
         * @description 存活检查
         */
        get: operations["liveness"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 必要依赖就绪检查
         * @description 必需数据库不可用返回503统一错误体；可选地图/模型未启用不假装已经完成真实服务验收。
         */
        get: operations["readiness"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 读取本人资料
         * @description 读取本人资料
         */
        get: operations["getMe"];
        put?: never;
        post?: never;
        /**
         * 注销账户及私有内容
         * @description JSON body含当前密码，不能放query；成功撤销所有会话并取消任务。
         */
        delete: operations["deleteAccount"];
        options?: never;
        head?: never;
        /**
         * 更新本人资料
         * @description preferences提供时整体替换；用户名/邮箱/权限不可修改。
         */
        patch: operations["updateMe"];
        trace?: never;
    };
    "/me/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 修改密码并撤销所有会话
         * @description 旧密码错误401 CURRENT_PASSWORD_INVALID，不能触发自动刷新；成功后客户端清理身份。
         */
        post: operations["changePassword"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/places": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 搜索和筛选有效地点
         * @description explicit_tags为all匹配；价格上限须带price_unit；未知价不满足硬上限。
         */
        get: operations["listPlaces"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/places/{place_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 读取有效地点详情
         * @description 失效地点公开详情404 PLACE_NOT_FOUND；本人收藏/行程仍可读取失效摘要。
         */
        get: operations["getPlace"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/places/{place_id}/navigation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 获取受限供应商导航链接
         * @description 供应商未启用、缺坐标、不支持CRS等返回200 unavailable，不生成假链接或假时长。
         */
        get: operations["getNavigation"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/planning-jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 恢复本人规划任务
         * @description 恢复本人规划任务
         */
        get: operations["listPlanningJobs"];
        put?: never;
        /**
         * 创建可恢复的Agent规划任务
         * @description 查询既有幂等结果优先于提供方可用性检查；有效请求/依赖就绪后持久化queued。
         */
        post: operations["createPlanningJob"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/planning-jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 读取本人任务结果
         * @description 读取本人任务结果
         */
        get: operations["getPlanningJob"];
        put?: never;
        post?: never;
        /**
         * 取消未完成任务
         * @description 只允许queued/running，取消提交后返回cancelled；终态409 JOB_TERMINAL。
         */
        delete: operations["cancelPlanningJob"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/recommendations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 协同或明确偏好/基础推荐
         * @description 无凭据基础兜底；携带无效凭据401，不能默默降级。硬标签all匹配，历史仅排序。
         */
        get: operations["getRecommendations"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/tags": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 浏览tags
         * @description 浏览tags
         */
        get: operations["listTags"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/trips": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 浏览本人行程
         * @description 浏览本人行程
         */
        get: operations["listTrips"];
        put?: never;
        /**
         * 手动创建空行程
         * @description 同键同输入重放201，同键异输入409；原结果已删410；空行程不代表已完成规划。
         */
        post: operations["createTrip"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/trips/{trip_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 读取本人每日行程
         * @description 读取本人每日行程
         */
        get: operations["getTrip"];
        put?: never;
        post?: never;
        /**
         * 按版本删除本人行程
         * @description 删除关联地点，聊天行程关联置空；生成任务保留结果删除墓碑。
         */
        delete: operations["deleteTrip"];
        options?: never;
        head?: never;
        /**
         * 按版本编辑本人行程
         * @description 城市不可修改；日期变更不能留下越界地点或退房日。
         */
        patch: operations["updateTrip"];
        trace?: never;
    };
    "/trips/{trip_id}/items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 添加目录地点并返回完整行程
         * @description 地点kind由目录判断，住宿分钟均null；禁止传快照/坐标/费用事实。
         */
        post: operations["addTripItem"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/trips/{trip_id}/items/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * 删除地点并返回新版本行程
         * @description 删除地点并返回新版本行程
         */
        delete: operations["deleteTripItem"];
        options?: never;
        head?: never;
        /**
         * 编辑地点、日期、时间或备注
         * @description 编辑地点、日期、时间或备注
         */
        patch: operations["updateTripItem"];
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        AccountDelete: {
            current_password: string;
        };
        BehaviorCreate: {
            /** Format: uuid */
            event_id: string;
            /** Format: date-time */
            occurred_at: string;
            /** Format: uuid */
            place_id: string;
            /** @enum {string} */
            type: "view";
        };
        BehaviorReceipt: {
            /** Format: uuid */
            event_id: string;
            /** @enum {string} */
            status: "accepted" | "duplicate";
        } & {
            [key: string]: unknown;
        };
        BehaviorReceiptResponse: {
            data: components["schemas"]["BehaviorReceipt"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        ChatSession: {
            /** Format: date-time */
            created_at: string;
            /** Format: uuid */
            id: string;
            title: string;
            trip_id: string | null;
            /** Format: date-time */
            updated_at: string;
        } & {
            [key: string]: unknown;
        };
        ChatSessionCreate: {
            /** @default 新对话 */
            title: string;
            trip_id?: string | null;
        };
        ChatSessionPageResponse: {
            data: components["schemas"]["ChatSession"][];
            meta: components["schemas"]["PageMeta"];
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        ChatSessionResponse: {
            data: components["schemas"]["ChatSession"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        ChatSessionUpdate: {
            title: string;
        };
        City: {
            code: string;
            /** Format: uuid */
            id: string;
            name: string;
            /** @enum {string} */
            timezone: "Asia/Shanghai";
        } & {
            [key: string]: unknown;
        };
        CityPageResponse: {
            data: components["schemas"]["City"][];
            meta: components["schemas"]["PageMeta"];
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        Coordinates: {
            /** @enum {string} */
            crs: "GCJ-02" | "WGS84" | "BD09";
            latitude: number;
            longitude: number;
        } & {
            [key: string]: unknown;
        };
        CostSummary: ({
            complete: boolean;
            /** @enum {string} */
            currency: "CNY";
            estimated_cost_minor: number | null;
            known_cost_minor: number;
            unknown_item_count: number;
        } & {
            [key: string]: unknown;
        }) & (unknown & unknown);
        CursorMeta: {
            has_more: boolean;
            next_before_sequence: number | null;
        } & {
            [key: string]: unknown;
        };
        /** @description 不证明邮箱存在或邮件已送达。 */
        DeliveryReceipt: {
            /** @enum {string} */
            status: "accepted";
        } & {
            [key: string]: unknown;
        };
        DeliveryReceiptResponse: {
            data: components["schemas"]["DeliveryReceipt"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        ErrorBody: {
            code: string;
            details: components["schemas"]["FieldError"][];
            message: string;
        } & {
            [key: string]: unknown;
        };
        ErrorResponse: {
            error: components["schemas"]["ErrorBody"];
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        Estimate: {
            amount_minor: number;
            reason: string;
            source: string | null;
        } & {
            [key: string]: unknown;
        };
        FavoriteStatus: {
            is_favorited: boolean;
            /** Format: uuid */
            place_id: string;
        } & {
            [key: string]: unknown;
        };
        FavoriteStatusResponse: {
            data: components["schemas"]["FavoriteStatus"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        FieldError: {
            /** @enum {string} */
            code: "REQUIRED" | "UNKNOWN_FIELD" | "INVALID_TYPE" | "INVALID_FORMAT" | "OUT_OF_RANGE" | "INVALID_ENUM" | "INVALID_COMBINATION";
            path: string;
        } & {
            [key: string]: unknown;
        };
        Health: {
            /** @enum {string} */
            status: "ok" | "not_ready";
        } & {
            [key: string]: unknown;
        };
        HealthResponse: {
            data: components["schemas"]["Health"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        Job: ({
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            deadline: string;
            error_code: ("JOB_TIMEOUT" | "NO_CANDIDATES" | "PLAN_INVALID" | "BUDGET_EXCEEDED" | "PROVIDER_UNAVAILABLE" | "PROVIDER_TIMEOUT" | "INTERNAL_ERROR") | null;
            /** Format: uuid */
            id: string;
            /** @enum {string} */
            provider_mode: "disabled" | "mock" | "real";
            result_deleted: boolean;
            /** @enum {string} */
            status: "queued" | "running" | "succeeded" | "failed" | "timed_out" | "cancelled";
            trip_id: string | null;
            /** Format: date-time */
            updated_at: string;
            warnings: components["schemas"]["Warning"][];
        } & {
            [key: string]: unknown;
        }) & (unknown & unknown & unknown & unknown);
        JobPageResponse: {
            data: components["schemas"]["Job"][];
            meta: components["schemas"]["PageMeta"];
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        JobResponse: {
            data: components["schemas"]["Job"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        LoginRequest: {
            identifier: string;
            password: string;
        };
        LoginResult: {
            tokens: components["schemas"]["TokenPair"];
            user: components["schemas"]["User"];
        } & {
            [key: string]: unknown;
        };
        LoginResultResponse: {
            data: components["schemas"]["LoginResult"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        Message: ({
            content: string;
            /** Format: date-time */
            created_at: string;
            error_code: ("PROVIDER_UNAVAILABLE" | "PROVIDER_TIMEOUT" | "INTERNAL_ERROR" | "SESSION_BUSY") | null;
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            message_id: string;
            /** @enum {string} */
            role: "user" | "assistant";
            sequence: number;
            /** @enum {string} */
            status: "pending" | "running" | "succeeded" | "failed";
        } & {
            [key: string]: unknown;
        }) & (unknown & unknown & unknown);
        MessageCreate: {
            content: string;
            /** Format: uuid */
            message_id: string;
        };
        MessageHistoryResponse: {
            data: components["schemas"]["Message"][];
            meta: components["schemas"]["CursorMeta"];
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        MessageTurn: {
            assistant_message: components["schemas"]["Message"];
            /** @enum {string} */
            provider_mode: "disabled" | "mock" | "real";
            user_message: components["schemas"]["Message"];
        } & {
            [key: string]: unknown;
        };
        MessageTurnResponse: {
            data: components["schemas"]["MessageTurn"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        NamedEntry: {
            code: string;
            /** Format: uuid */
            id: string;
            name: string;
        } & {
            [key: string]: unknown;
        };
        NamedEntryPageResponse: {
            data: components["schemas"]["NamedEntry"][];
            meta: components["schemas"]["PageMeta"];
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        NavigationDestination: {
            address: string | null;
            coordinates: components["schemas"]["Coordinates"] | null;
            name: string;
            /** Format: uuid */
            place_id: string;
        } & {
            [key: string]: unknown;
        };
        NavigationResult: ({
            destination: components["schemas"]["NavigationDestination"];
            /** @enum {string} */
            mode: "walking" | "driving" | "transit" | "cycling";
            /** @enum {string} */
            provider: "amap" | "google" | "none";
            reason: ("NO_COORDINATES" | "UNSUPPORTED_CRS" | "PROVIDER_DISABLED" | "PROVIDER_ERROR") | null;
            /** @enum {string} */
            status: "available" | "unavailable";
            url: string | null;
        } & {
            [key: string]: unknown;
        }) & (unknown & unknown);
        NavigationResultResponse: {
            data: components["schemas"]["NavigationResult"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        /** @description parsed时weekly非空；unparsed时weekly为空，不推断是否营业。节假日以原文提示为准。 */
        OpeningHours: ({
            observed_at: string | null;
            /** @enum {string} */
            parse_status: "unparsed" | "parsed";
            raw_text: string;
            /** @enum {string} */
            timezone: "Asia/Shanghai";
            weekly: components["schemas"]["OpeningInterval"][];
        } & {
            [key: string]: unknown;
        }) & (unknown & unknown);
        /** @description 本地时间，opens<closes；跨午夜拆段。 */
        OpeningInterval: {
            closes_minute: number;
            opens_minute: number;
            weekday: number;
        } & {
            [key: string]: unknown;
        };
        PageMeta: {
            has_more: boolean;
            page: number;
            page_size: number;
            total: number;
        } & {
            [key: string]: unknown;
        };
        PasswordChange: {
            current_password: string;
            new_password: string;
        };
        Place: {
            address: string | null;
            category: components["schemas"]["NamedEntry"] | null;
            city: components["schemas"]["City"];
            coordinates: components["schemas"]["Coordinates"] | null;
            estimate: components["schemas"]["Estimate"] | null;
            /** Format: uuid */
            id: string;
            is_test: boolean;
            /** @enum {string} */
            kind: "attraction" | "hotel" | "restaurant";
            name: string;
            price: components["schemas"]["PriceFact"] | null;
            provenance: components["schemas"]["Provenance"];
            /** @enum {string} */
            status: "active" | "inactive";
            tags: components["schemas"]["NamedEntry"][];
        } & {
            [key: string]: unknown;
        };
        PlaceDetail: {
            address: string | null;
            category: components["schemas"]["NamedEntry"] | null;
            city: components["schemas"]["City"];
            coordinates: components["schemas"]["Coordinates"] | null;
            cuisine: string | null;
            description: string | null;
            estimate: components["schemas"]["Estimate"] | null;
            hotel_stars: number | null;
            /** Format: uuid */
            id: string;
            images: components["schemas"]["PlaceImage"][];
            is_test: boolean;
            /** @enum {string} */
            kind: "attraction" | "hotel" | "restaurant";
            name: string;
            opening_hours: components["schemas"]["OpeningHours"] | null;
            price: components["schemas"]["PriceFact"] | null;
            provenance: components["schemas"]["Provenance"];
            rating: components["schemas"]["Rating"] | null;
            /** @enum {string} */
            status: "active" | "inactive";
            tags: components["schemas"]["NamedEntry"][];
        } & {
            [key: string]: unknown;
        };
        PlaceDetailResponse: {
            data: components["schemas"]["PlaceDetail"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        PlaceImage: {
            source_name: string;
            /** Format: uri */
            url: string;
        } & {
            [key: string]: unknown;
        };
        PlacePageResponse: {
            data: components["schemas"]["Place"][];
            meta: components["schemas"]["PageMeta"];
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        PlanningRequest: {
            budget_minor?: number | null;
            /** Format: uuid */
            city_id: string;
            /** Format: date */
            end_date: string;
            /** @default [] */
            explicit_tags: string[];
            preferences?: components["schemas"]["PreferencesInput"];
            /** @default  */
            request_text: string;
            /** Format: date */
            start_date: string;
        };
        Preferences: {
            /**
             * @default normal
             * @enum {string}
             */
            pace: "relaxed" | "normal" | "fast";
            /** @default [] */
            tags: string[];
        } & {
            [key: string]: unknown;
        };
        PreferencesInput: {
            /**
             * @default normal
             * @enum {string}
             */
            pace: "relaxed" | "normal" | "fast";
            /** @default [] */
            tags: string[];
        };
        PriceFact: {
            amount_minor: number;
            /**
             * @description 来源已确认的价格适用条件；旧快照可缺失。
             * @default null
             */
            conditions: string | null;
            /** @enum {string} */
            currency: "CNY";
            observed_at: string | null;
            /** @enum {string} */
            unit: "entry" | "night" | "person";
        } & {
            [key: string]: unknown;
        };
        ProfileUpdate: {
            nickname?: string;
            preferences?: components["schemas"]["PreferencesInput"];
            signature?: string;
        };
        Provenance: {
            checked_at: string | null;
            source_name: string;
            source_url: string | null;
        } & {
            [key: string]: unknown;
        };
        /** @description 必须value≤scale；不比较不同来源量表。 */
        Rating: {
            scale: number;
            value: number;
        } & {
            [key: string]: unknown;
        };
        RecommendationResult: {
            algorithm_version: string;
            items: components["schemas"]["Place"][];
            /** @enum {string} */
            reason: "collaborative" | "fallback_preferences" | "fallback_catalog";
        } & {
            [key: string]: unknown;
        };
        RecommendationResultResponse: {
            data: components["schemas"]["RecommendationResult"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        RecoveryConfirm: {
            new_password: string;
            token: string;
        };
        RecoveryRequest: {
            /** Format: email */
            email: string;
        };
        RefreshRequest: {
            refresh_token: string;
        };
        RegisterRequest: {
            /** Format: email */
            email: string;
            /** @default  */
            nickname: string;
            password: string;
            username: string;
        };
        Snapshot: {
            address: string | null;
            /** Format: date-time */
            captured_at: string;
            coordinates: components["schemas"]["Coordinates"] | null;
            /** @enum {string} */
            kind: "attraction" | "hotel" | "restaurant";
            name: string;
            price: components["schemas"]["PriceFact"] | null;
            provenance: components["schemas"]["Provenance"];
            schema_version: number;
        } & {
            [key: string]: unknown;
        };
        TokenPair: {
            access_token: string;
            expires_in: number;
            /** Format: date-time */
            refresh_expires_at: string;
            refresh_token: string;
            /** @enum {string} */
            token_type: "Bearer";
        } & {
            [key: string]: unknown;
        };
        TokenPairResponse: {
            data: components["schemas"]["TokenPair"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        Trip: {
            budget_minor: number | null;
            /** Format: uuid */
            city_id: string;
            cost_summary: components["schemas"]["CostSummary"];
            /** Format: date-time */
            created_at: string;
            /** Format: date */
            end_date: string;
            /** Format: uuid */
            id: string;
            items: components["schemas"]["TripItem"][];
            preferences: components["schemas"]["Preferences"];
            /** Format: date */
            start_date: string;
            title: string;
            /** Format: date-time */
            updated_at: string;
            version: number;
            warnings: components["schemas"]["Warning"][];
        } & {
            [key: string]: unknown;
        };
        TripCreate: {
            budget_minor?: number | null;
            /** Format: uuid */
            city_id: string;
            /** Format: date */
            end_date: string;
            preferences?: components["schemas"]["PreferencesInput"];
            /** Format: date */
            start_date: string;
            title: string;
        };
        TripItem: ({
            /** @enum {string} */
            current_status: "active" | "inactive";
            /** Format: date */
            date: string;
            end_minute: number | null;
            estimate_reason: string | null;
            estimated_cost_minor: number | null;
            /** Format: uuid */
            id: string;
            note: string;
            /** Format: uuid */
            place_id: string;
            snapshot: components["schemas"]["Snapshot"];
            start_minute: number | null;
        } & {
            [key: string]: unknown;
        }) & unknown;
        TripItemCreate: {
            /** Format: date */
            date: string;
            end_minute: number | null;
            /** @default  */
            note: string;
            /** Format: uuid */
            place_id: string;
            start_minute: number | null;
            version: number;
        };
        TripItemUpdate: {
            /** Format: date */
            date?: string;
            end_minute?: number | null;
            /** @default  */
            note: string;
            /** Format: uuid */
            place_id?: string;
            start_minute?: number | null;
            version: number;
        };
        TripResponse: {
            data: components["schemas"]["Trip"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        TripSummary: {
            budget_minor: number | null;
            /** Format: uuid */
            city_id: string;
            /** Format: date-time */
            created_at: string;
            /** Format: date */
            end_date: string;
            /** Format: uuid */
            id: string;
            /** Format: date */
            start_date: string;
            title: string;
            /** Format: date-time */
            updated_at: string;
            version: number;
        } & {
            [key: string]: unknown;
        };
        TripSummaryPageResponse: {
            data: components["schemas"]["TripSummary"][];
            meta: components["schemas"]["PageMeta"];
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        TripUpdate: {
            budget_minor?: number | null;
            /** Format: date */
            end_date?: string;
            preferences?: components["schemas"]["PreferencesInput"];
            /** Format: date */
            start_date?: string;
            title?: string;
            version: number;
        };
        User: {
            /** Format: email */
            email: string;
            email_verified: boolean;
            /** Format: uuid */
            id: string;
            nickname: string;
            preferences: components["schemas"]["Preferences"];
            signature: string;
            username: string;
        } & {
            [key: string]: unknown;
        };
        UserResponse: {
            data: components["schemas"]["User"];
            meta: null;
            /** Format: uuid */
            request_id: string;
        } & {
            [key: string]: unknown;
        };
        VerificationConfirm: {
            token: string;
        };
        Warning: {
            /** @enum {string} */
            code: "PRICE_UNKNOWN" | "OPENING_HOURS_UNKNOWN" | "TRAVEL_TIME_UNKNOWN" | "COST_INCOMPLETE" | "ESTIMATE_OVER_BUDGET" | "PLACE_INACTIVE" | "SNAPSHOT_MAY_BE_OUTDATED" | "PREFERENCE_UNSATISFIED";
            message: string;
            place_id: string | null;
        } & {
            [key: string]: unknown;
        };
    };
    responses: {
        /** @description 请求语法或协议非法 */
        Error400: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 未登录或会话失效 */
        Error401: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "WWW-Authenticate": components["headers"]["Authenticate"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 账户不可用 */
        Error403: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 资源不存在或不可访问 */
        Error404: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 版本、幂等或处理中冲突 */
        Error409: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 原创建结果已删除 */
        Error410: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 请求超过64KiB */
        Error413: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 要求application/json */
        Error415: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 字段或组合校验失败 */
        Error422: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 请求过于频繁 */
        Error429: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "Retry-After": components["headers"]["RetryAfter"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 内部失败，凭request_id排查 */
        Error500: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 必要依赖不可用 */
        Error503: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
        /** @description 外部服务超时 */
        Error504: {
            headers: {
                "Cache-Control": components["headers"]["CacheControl"];
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["ErrorResponse"];
            };
        };
    };
    parameters: never;
    requestBodies: never;
    headers: {
        Authenticate: "Bearer";
        /** @description 私有/认证响应no-store。 */
        CacheControl: string;
        /** @description 服务端生成；与JSON request_id一致。 */
        RequestId: string;
        /** @description 整数秒。 */
        RetryAfter: number;
    };
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    confirmVerification: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VerificationConfirm"];
            };
        };
        responses: {
            /** @description 成功，无响应体。 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    requestVerification: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            202: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeliveryReceiptResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    login: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResultResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    logout: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功，无响应体。 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    confirmPasswordReset: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RecoveryConfirm"];
            };
        };
        responses: {
            /** @description 成功，无响应体。 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["Error400"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    requestPasswordReset: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RecoveryRequest"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            202: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeliveryReceiptResponse"];
                };
            };
            400: components["responses"]["Error400"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    refresh: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RefreshRequest"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenPairResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    register: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterRequest"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            201: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            400: components["responses"]["Error400"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    recordBehavior: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BehaviorCreate"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            202: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BehaviorReceiptResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    listCategories: {
        parameters: {
            query?: {
                page?: number;
                page_size?: number;
                q?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NamedEntryPageResponse"];
                };
            };
            400: components["responses"]["Error400"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    listChatSessions: {
        parameters: {
            query?: {
                page?: number;
                page_size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatSessionPageResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    createChatSession: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatSessionCreate"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            201: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatSessionResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    getChatSession: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatSessionResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    deleteChatSession: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功，无响应体。 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    updateChatSession: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatSessionUpdate"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatSessionResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    listMessages: {
        parameters: {
            query?: {
                before_sequence?: number;
                limit?: number;
            };
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageHistoryResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    sendMessage: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageCreate"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            201: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageTurnResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
            504: components["responses"]["Error504"];
        };
    };
    listCities: {
        parameters: {
            query?: {
                page?: number;
                page_size?: number;
                q?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CityPageResponse"];
                };
            };
            400: components["responses"]["Error400"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    listFavorites: {
        parameters: {
            query?: {
                kind?: "attraction" | "hotel" | "restaurant";
                page?: number;
                page_size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlacePageResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    getFavoriteStatus: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                place_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FavoriteStatusResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    addFavorite: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                place_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功，无响应体。 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    removeFavorite: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                place_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功，无响应体。 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    liveness: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
            400: components["responses"]["Error400"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    readiness: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
            400: components["responses"]["Error400"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    getMe: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    deleteAccount: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AccountDelete"];
            };
        };
        responses: {
            /** @description 成功，无响应体。 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    updateMe: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileUpdate"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    changePassword: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordChange"];
            };
        };
        responses: {
            /** @description 成功，无响应体。 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    listPlaces: {
        parameters: {
            query?: {
                category_id?: string;
                city_id?: string;
                explicit_tags?: string[];
                kind?: "attraction" | "hotel" | "restaurant";
                page?: number;
                page_size?: number;
                price_max_minor?: number;
                price_unit?: "entry" | "night" | "person";
                q?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlacePageResponse"];
                };
            };
            400: components["responses"]["Error400"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    getPlace: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                place_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlaceDetailResponse"];
                };
            };
            400: components["responses"]["Error400"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    getNavigation: {
        parameters: {
            query?: {
                mode?: "walking" | "driving" | "transit" | "cycling";
                provider?: "amap" | "google";
            };
            header?: never;
            path: {
                place_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NavigationResultResponse"];
                };
            };
            400: components["responses"]["Error400"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    listPlanningJobs: {
        parameters: {
            query?: {
                page?: number;
                page_size?: number;
                status?: ("queued" | "running" | "succeeded" | "failed" | "timed_out" | "cancelled")[];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobPageResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    createPlanningJob: {
        parameters: {
            query?: never;
            header: {
                /** @description 同一创建意图复用，建议UUID；不可含个人信息。 */
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlanningRequest"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            202: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    getPlanningJob: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    cancelPlanningJob: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    getRecommendations: {
        parameters: {
            query?: {
                city_id?: string;
                explicit_tags?: string[];
                kind?: "attraction" | "hotel" | "restaurant";
                limit?: number;
                preferred_tags?: string[];
                price_max_minor?: number;
                price_unit?: "entry" | "night" | "person";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationResultResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    listTags: {
        parameters: {
            query?: {
                page?: number;
                page_size?: number;
                q?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NamedEntryPageResponse"];
                };
            };
            400: components["responses"]["Error400"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    listTrips: {
        parameters: {
            query?: {
                page?: number;
                page_size?: number;
                q?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TripSummaryPageResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    createTrip: {
        parameters: {
            query?: never;
            header: {
                /** @description 同一创建意图复用，建议UUID；不可含个人信息。 */
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TripCreate"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            201: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TripResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            410: components["responses"]["Error410"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    getTrip: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                trip_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TripResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    deleteTrip: {
        parameters: {
            query: {
                version: number;
            };
            header?: never;
            path: {
                trip_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功，无响应体。 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    updateTrip: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                trip_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TripUpdate"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TripResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    addTripItem: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                trip_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TripItemCreate"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            201: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TripResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    deleteTripItem: {
        parameters: {
            query: {
                version: number;
            };
            header?: never;
            path: {
                item_id: string;
                trip_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TripResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
    updateTripItem: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: string;
                trip_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TripItemUpdate"];
            };
        };
        responses: {
            /** @description 成功；含响应体时使用统一包装。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["CacheControl"];
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TripResponse"];
                };
            };
            400: components["responses"]["Error400"];
            401: components["responses"]["Error401"];
            403: components["responses"]["Error403"];
            404: components["responses"]["Error404"];
            409: components["responses"]["Error409"];
            413: components["responses"]["Error413"];
            415: components["responses"]["Error415"];
            422: components["responses"]["Error422"];
            429: components["responses"]["Error429"];
            500: components["responses"]["Error500"];
            503: components["responses"]["Error503"];
        };
    };
}
