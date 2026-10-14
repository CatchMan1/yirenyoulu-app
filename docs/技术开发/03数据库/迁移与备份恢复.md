# 独立数据库、迁移与恢复

当前为数据库基础实现，不是业务闭环。运行前确认数据库为本新项目专用；禁止使用旧项目 `.env`、数据库文件或连接。

## 选择与边界
采用 PostgreSQL 16（部署时选用经验证的当前16.x安全补丁镜像并锁 digest）。数据库保留外键、检查约束、唯一约束与事务；任务租约和版本冲突将在业务层实现。SQLite仅用于快速约束测试，不能证明 PostgreSQL 并发/锁行为。

开发 `yirenyoulu_dev`，测试 `yirenyoulu_test`，生产 `yirenyoulu_prod`，各自独立实例/凭据/卷。Settings 要求 URL driver 为 `postgresql+psycopg` 且库名匹配 APP_ENV；这不是绝对安全边界，部署还必须用不同主机/账号权限与网络隔离。配置不自动读取旧目录或工作目录 `.env`，由运行环境显式注入。

## 开发初始化
需要 Python3.11 与 Docker Compose。已存在独立 `.venv` 时不要重复创建；依赖只装新环境。

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example .env
# 编辑 .env，使用密码管理器生成独立 POSTGRES_PASSWORD。
docker compose --env-file .env up -d db
```

将 APP_ENV=development、DATABASE_URL 注入新终端进程（推荐 IDE 环境变量或私有环境管理器），URL指向 localhost:55432 的 yirenyoulu_dev，驱动 postgresql+psycopg，不复用旧账号。不要在共享日志或聊天中粘贴 URL。

```sh
.venv/bin/alembic -c backend/alembic.ini upgrade head
# 可选：导入9个明显标记的虚拟地点；不创建默认账号或用户行为。
PYTHONPATH=backend .venv/bin/python -m app.seed
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
```

初始化只跑 Alembic。应用启动不得调用 create_all 或补列脚本。fixture 导入为独立显式命令，production被拒绝；真实数据采集尚未开始。fixture名字以【测试】开头，价格、评分、营业时间、坐标均未知，不构造真实事实。测试坐标/有效价格边界只存在单测事务。

## 迁移验证
CI 创建空的 PostgreSQL yirenyoulu_test，依次 upgrade→metadata drift check→downgrade→upgrade，并对 PostgreSQL 实际运行唯一性、外键、字段检查、回滚、快照不随目录改变的测试。

本地执行必须设置 APP_ENV=test、DATABASE_URL 指向全新专用空库：
```sh
PYTHONPATH=backend RUN_POSTGRES_TESTS=1 .venv/bin/python -m pytest backend/tests/test_postgres.py -q
PYTHONPATH=backend RUN_POSTGRES_TESTS=1 .venv/bin/python -m pytest backend/tests/test_schema.py -q
```
测试拒绝非test环境及非空库。迁移往返测试会删除其新建表，禁止对有业务数据的库执行。生产迁移先备份、在恢复副本演练，再用专用迁移角色执行。运行角色仅有业务DML，不应有建表/删表权限。`downgrade base` 是破坏性操作，只用于空测试库；生产回滚优先兼容旧版本应用或经审查的前向修复。

## 数据保护与恢复操作说明（尚需演练）
使用 PostgreSQL service 配置及权限0600的 passfile 管理连接，下面的 PGSERVICE 名称必须由部署人员指向本项目独立环境。不要把密码写进命令、版本库或日志。备份包含个人数据，必须加密、限制访问、设置保留期且不提交GitHub；生产库备份不可用于开发。

```sh
# 权限最小化；目录应位于本项目以外的受控加密备份位置。
umask 077
PGSERVICE=yirenyoulu_backup pg_dump --format=custom --file="$BACKUP_PATH"
# 先在新的隔离恢复库演练，不覆盖线上库；不使用 --clean。
PGSERVICE=yirenyoulu_restore pg_restore --no-owner --no-acl --exit-on-error "$BACKUP_PATH"
```
恢复后检查 Alembic revision、关键表行数/抽样关联和应用只读健康，再执行恢复环境的业务验收；恢复前阻断外部模型/短信，重放备份之后的账户删除记录后才允许开放。当前未实现删除审计/重放程序，故不能声称已满足注销后的恢复要求；这是认证/运维阶段的发布阻塞项。

备份频率、RPO/RTO、30天上限与外部法律要求需在正式部署前结合业务确定并演练。当前没有创建生产数据库，没有连接旧库，没有执行生产备份或恢复。

## 模型说明
地点统一 UUID，与来源+外部ID绑定；旧整数三表ID不迁入。未知事实保持NULL；图片许可默认不展示。行程地点保存快照，与基础地点外键关联，目录变化不改快照。task→trip 由 trips.generation_job_id 唯一关联，API成功结果通过该关联查询；状态成功与行程保存的原子性将在任务服务测试中验收，数据库表存在不代表该业务已实现。
