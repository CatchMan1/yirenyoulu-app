# FastAPI后端开发规范

与[通用工程规范](通用工程规范.md)配合使用。适用Python、FastAPI、Pydantic、SQLAlchemy与Alembic的中小型上线服务。同步或异步数据库路线应明确选择，不为“看起来并发”混用两套会话。

## 1. 工程分层

```text
backend/
  app/
    main.py                  # 应用工厂/路由装配与生命周期
    settings.py              # 显式配置校验
    db.py                    # engine与session factory
    modules/
      <domain>/              # router、schemas、service、必要的repository
    integrations/            # 模型、地图、邮件等提供方适配
    workers/                 # 持久任务执行入口
  alembic/                   # 冻结迁移版本
  tests/                     # 单测、契约、PostgreSQL集成
```

目录是扩展方向；小项目可暂时集中models.py，业务复杂后按模块拆分，不立即改已有迁移导入路径。router不直接承载复杂算法，repository不定义HTTP错误；小查询不强制为每张表建CRUD类。

## 2. Python风格与类型

Python3.11为本项目运行基线，其他工程遵循其已验证版本。采用4空格、snake_case、类型注解、显式返回类型；不以Dict[str,Any]长期代替已知schema。容器默认值用工厂，时间使用aware UTC，金额整数/Decimal转换后按最小单位持久化，不用float累计费用。

Ruff负责格式和静态检查，选一种类型检查工具（默认mypy），pytest负责行为验证。依赖声明/锁定方式与项目现状一致；不为了模板同时引入Poetry、uv和requirements三套来源。当前项目继续独立venv和固定requirements，工具补齐前不宣称对应检查已配置。

公共服务说明事务、权限和副作用；注释解释约束来源。模块导入不建立连接、不跑迁移、不创建默认用户；应用通过明确工厂或入口启动。

## 3. FastAPI与Pydantic契约

APIRouter按领域组织；依赖只解决会话/身份/受控资源获取，不在依赖中偷偷完成核心业务写入。Create/Update/Read模型分离，字段校验UUID、长度、枚举、范围和嵌套结构；写DTO禁止未知字段。Update通过exclude_unset或等效机制区分省略与显式null，不将未填写值覆盖为null。

响应声明response_model或显式等效序列化，输出允许清单；严禁把密码hash、刷新摘要、内部权限或提供方原始回包暴露。成功码与错误格式统一，错误details仅字段路径与码，不回显敏感输入。409/422等文档与真实行为一致，204无body，202仅表示受理。

Pydantic v2使用对应版本ConfigDict/model_validate/model_dump等接口；旧工程升级前核实版本，不混用v1/v2写法。OpenAPI用于契约检查，公开文档与生成schema差异应阻止不兼容发布。

## 4. 同步/异步执行

当前数据库factory使用同步SQLAlchemy：数据库为主的请求优先普通def路由/服务，由FastAPI安排同步路由执行。async def中直接调用普通辅助函数不会自动转线程，禁止把同步SQL/requests/文件阻塞调用直接放事件循环。[FastAPI并发说明](https://fastapi.tiangolo.com/async/)

需要异步HTTP编排时，数据库工作以完整同步工作单元在线程中执行，在该工作单元内创建并关闭Session，只向异步层返回DTO；不能把一个Session传到多个线程或await并发任务。FastAPI的独立同步依赖和路由不保证在同一线程执行；不要假定yield Session就能满足这个边界，身份读取和业务事务分别在自己的完整同步单元中创建并关闭Session。若确需异步ORM，整体采用AsyncSession及异步驱动，独立验证后迁移。

CPU密集推荐计算和持久长任务放worker，不靠async关键字增加算力。API/worker设置连接池、超时、并发和队列上限；模型等待期间不持有数据库行锁或长事务。

## 5. 事务与Session所有权

每个工作单元独享Session，repository负责查询/flush，不commit；应用服务或显式事务编排器唯一拥有提交。用工厂的begin上下文创建业务事务，退出成功后才产生HTTP成功；依赖清理只负责close，禁止把可能失败的commit拖到yield清理或响应发送之后。

SQLAlchemy查询可能已autobegin；不能认证依赖先查同一Session后再盲目session.begin。默认做法：身份依赖使用已关闭的短只读Session取得principal，写服务创建独立事务并再次检查账户/会话状态及资源归属；也可由统一编排器从第一次查询前拥有完整事务，不能混用隐式所有权。

事务骨架（仓储/验证函数按领域实现）：

```python
from collections.abc import Callable
from uuid import UUID
from sqlalchemy.orm import Session


def rename_resource(
    session_factory: Callable[[], Session],
    actor_id: UUID,
    resource_id: UUID,
    expected_version: int,
    title: str,
) -> dict[str, str | int]:
    with session_factory() as session:
        with session.begin():
            ensure_actor_active(session, actor_id)
            resource = get_owned_for_update(session, actor_id, resource_id)
            ensure_version(resource, expected_version)
            resource.title = title
            resource.version += 1
            session.flush()
            result = {"id": str(resource.id), "version": resource.version}
        return result
```

示例展示提交位置，不是可直接运行的业务实现；ensure/get函数需定义领域错误且查询必须含owner条件。若在途撤销要求立即生效，ensure还校验session_id与撤销状态。提交失败不会执行return；跨资源修改、事件产生与任务成功在同事务内。

IntegrityError在事务回滚后映射已知唯一/外键冲突，不能吞异常再返回成功。并发用行锁或version条件更新并检查rowcount；测试必须覆盖两个事务竞争，不用SQLite证明PostgreSQL锁行为。避免N+1，查询分页/过滤/稳定排序在数据库完成，禁止page_size无限大。

## 6. 权限与认证

认证使用不可变用户ID和可撤销会话，不依赖可改用户名作为sub。固定JWT算法、issuer/audience/有效期/签发时间，刷新轮换、令牌家族重放与会话撤销按专用服务实现。密码采用适当参数的Argon2id，令牌和找回凭据只存摘要。

私有资源查询同时过滤owner与资源ID，嵌套资源检查父关系；客户端不能指定user_id代替身份。错误资源与越权按接口策略统一404。公开入口“未带凭据”和“携带无效凭据”分别处理，不能把无效token默默降级为匿名成功。

认证后到写入间可能发生禁用/注销，事务最终检查账户有效性；需要严格竞争顺序时共享账户/会话锁并统一锁顺序。限流不靠单个进程字典作为多worker全局保障；现阶段优先入口代理或数据库受控实现，按规模再引入额外服务。

## 7. 持久任务、工具与外部调用

任务创建先持久化请求、deadline、幂等键和摘要，返回任务ID。worker用lease+generation领取，超时/取消/成功竞争同一锁；最终状态与结果原子提交。进程内dict、BackgroundTasks适合可丢失的辅助工作，不能承载需要可靠恢复的核心任务。

外部调用设置连接/读取/总deadline、有限重试、响应大小和并发限制；只对明确可重试错误重试，尊重Retry-After。不把模型调用放在持锁事务中。记录来源与provider_mode，模拟不能进入生产；费用耗尽不能未经授权付费兜底。

Agent工具参数有schema、查询有allowlist/范围/有效状态，不允许任意SQL、shell或URL；地点与费用由程序重建校验。供应商回包先验证再保存；出错保留稳定业务错误码，不泄露内部地址或原文。

## 8. 生命周期、配置与日志

engine/HTTP连接池等应用级资源在lifespan中创建/关闭，资源挂载在应用上下文或显式依赖；不要导入时开连接，也不要重复混合startup/shutdown与lifespan两套初始化。[FastAPI生命周期文档](https://fastapi.tiangolo.com/advanced/events/)

Settings显式读取新环境，缺少必需配置启动失败；秘密不在默认值兜底。生产debug关闭、CORS最小允许范围、TLS入口、DB不公网暴露；readiness验证必要依赖，liveness不执行昂贵外部调用。

结构化日志包含request_id、事件码、状态和耗时，捕获堆栈仅限受控内部日志并脱敏；关闭SQL参数输出和第三方客户端debug敏感日志。追踪上下文传入worker但不复制整份请求体。

## 9. 迁移与部署

Alembic是唯一生产建表/变更入口；已应用迁移不可改写，新增迁移审阅约束名、索引、默认值、锁表风险及数据回填。复杂改动按扩展→回填→切换→收缩分阶段，API与worker共享代码/迁移兼容范围。

空库迁移往返、metadata drift和PostgreSQL约束是基础检查；有数据迁移另测恢复副本，不能只证明空库建表。生产回滚不执行downgrade base；先备份与演练，用最小权限角色发布。

## 10. 测试与完成标准

纯规则单测，HTTP契约测试，PostgreSQL事务/并发集成，供应商适配器故障测试分层。测试库独立且显式拒绝生产；时间、随机ID和外部模型可注入，避免sleep等待和真实付费调用。真实账号/个人数据不进fixture。

关键场景：跨用户读写、子资源错配、会话撤销、提交失败、重放/异内容幂等、版本竞争、旧worker写入、取消与提交、未知事实、第三方超时、删除后恢复。以实际结果断言，不仅检查mock函数被调用。

每次合并运行改动相关检查；模型/迁移变化运行PostgreSQL迁移和无漂移检查，权限/事务变化补失败路径。部署完成还需健康检查、任务恢复和备份恢复验证；单测通过不能代替真实服务联调。
