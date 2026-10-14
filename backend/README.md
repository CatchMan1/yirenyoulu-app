# 后端开发与运行

Python3.11、FastAPI、SQLAlchemy同步事务、PostgreSQL16、Alembic。业务按账户、目录、行程、规划、聊天、推荐分模块；请求DTO与ORM分离，响应类型从已审核的OpenAPI生成。

## 本地启动

在仓库根目录使用独立虚拟环境，配置方式见[数据库初始化](../docs/技术开发/03数据库/迁移与备份恢复.md)。环境变量由IDE或私有环境管理器注入；应用不会自动读取.env，也不会启动时创建表。

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/alembic -c backend/alembic.ini upgrade head
PYTHONPATH=backend .venv/bin/python -m app.seed
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:create_application --factory --host 127.0.0.1 --port 8000 --no-access-log --limit-concurrency 64
```

必须提供匹配APP_ENV的独立DATABASE_URL及至少32字符的随机JWT_SECRET。开发数据库使用yirenyoulu_dev，测试yirenyoulu_test，生产yirenyoulu_prod。fixture命令仅允许开发/测试，包含9个明确标记的虚拟地点，不含用户或行为。

另一个同环境进程运行持久规划worker：

```sh
PYTHONPATH=backend .venv/bin/python -m app.worker
# 执行一轮后退出，适用于操作验证。
PYTHONPATH=backend .venv/bin/python -m app.worker --once
# 定时任务入口，原子发布相似度模型；不在HTTP请求中计算全站两两相似度。
PYTHONPATH=backend .venv/bin/python -m app.recommendation_batch
```

推荐批处理上限为10万条行为、10万条当前收藏及2000个有效地点，超出时拒绝发布，需按真实规模调整实现后验证。每地点保留20个相似地点，模型24小时失效；API候选检索上限1000、个人历史上限1万，超限或无模型走明确偏好/基础推荐。所有阈值均待真实行为评估；测试数据不会证明个性化效果。生产部署由受控定时任务每日或更频繁执行，并监测模型年龄。

AI_PROVIDER、MAIL_PROVIDER默认为disabled：缺配置返回明确不可用，不伪装发送或生成。development/test可设mock，FakePlanner仅验证受控查库、任务与保存链路，不理解自由文本，也不保证路线可达；FakeChat仅验证有界多轮上下文。邮件mock仅在进程内投递测试回链，不提供对外取令牌接口。production拒绝mock。尚未接入真实免费模型、真实邮件和地图SDK。

## 接口与错误

服务根路径/api/v1；/docs及/openapi.json来自真实路由。成功使用data/meta/request_id，204无body，202仅受理。服务端生成请求ID；敏感输入不写日志。认证会话可撤销，刷新重放撤销整条会话，刷新请求结果不明确时重新登录。错误密码CURRENT_PASSWORD_INVALID不触发刷新。

写事务提交后才返回成功；所有私有资源限定用户。行程编辑需version；同键重放查回同结果，删除或过期不能重新建行程。任务最终保存检查租约、generation、deadline及账户状态，旧worker无法覆盖终态。

## 检查

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
.venv/bin/ruff check --config backend/pyproject.toml backend/app backend/tests
.venv/bin/mypy --config-file backend/pyproject.toml backend/app
.venv/bin/python scripts/generate_response_models.py --check
.venv/bin/python scripts/generate_harmony_models.py --check
PYTHONPATH=backend .venv/bin/python scripts/generate_data_dictionary.py --check
```

PostgreSQL迁移往返必须从新的空测试库开始；HTTP与并发测试另设ITERATION_HTTP_DATABASE_URL，必须指向专用yirenyoulu_test，测试会清空其业务表。不要在有业务数据的库运行。备份演练另需PG_DUMP_PATH、PG_RESTORE_PATH及测试库；详见数据库运维说明。SQLite与跳过的集成项不作为PostgreSQL证据。

## 容器与部署

Dockerfile采用非root用户10001，API与worker分别启动；当前Compose仅用于独立开发环境。填写.env中的CONTAINER_DATABASE_URL，主机使用db、库名yirenyoulu_dev，与宿主机DATABASE_URL区分。先初始化迁移再启动业务：

```sh
docker compose --env-file .env up -d db
docker compose --env-file .env --profile backend build api
docker compose --env-file .env --profile backend run --rm api python -m alembic -c backend/alembic.ini upgrade head
docker compose --env-file .env --profile backend up -d api planner
```

生产需锁定经验证的Python/数据库镜像digest，独立迁移角色与仅DML运行角色，私密环境注入、TLS反向代理、连接/并发限制、监控、备份及恢复演练。代理可信IP按部署拓扑明确设置，不接受任意转发来源；公网不直接暴露数据库。数据库迁移版本不就绪时readiness返回503。此开发配置不是已完成的生产部署。
