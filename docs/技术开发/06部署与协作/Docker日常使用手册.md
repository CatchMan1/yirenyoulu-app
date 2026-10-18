# Docker 日常使用手册

适用：一人有路本地开发环境，Mac + Docker Desktop + Docker Compose。命令在新版项目根目录执行；首次使用先完成[首次初始化](#首次初始化)。

```sh
cd ~/Documents/yirenyoulu-app
```

如果项目位于其他位置，将上面的路径替换为自己的项目目录。Docker Desktop 需保持运行。

## 先理解项目里运行了什么

| 名称 | 含义 | 本项目用途 |
|---|---|---|
| 镜像 Image | 包含程序、依赖及启动方式的模板 | PostgreSQL 镜像、后端镜像 |
| 容器 Container | 从镜像启动的程序实例 | 数据库、API、规划 worker |
| 数据卷 Volume | 独立保存持久数据的位置 | 保存 PostgreSQL 数据 |
| Compose | 按配置管理一组服务的工具 | 读取根目录 compose.yaml |

| 服务名 | 作用 | 从哪里访问 |
|---|---|---|
| db | PostgreSQL 开发数据库 | Mac：127.0.0.1:55432；容器内：db:5432 |
| api | FastAPI 接口服务 | http://127.0.0.1:8000 |
| planner | 后台领取、生成并保存行程的进程 | 后台服务，无独立网页 |

api 和 planner 使用同一个后端镜像。数据库使用独立命名卷 development_db；默认完整卷名为 yirenyoulu-v2-dev_development_db。DBeaver 与后端分别连接同一个数据库，关闭 DBeaver 不影响后端。

## 最常用的五组命令

### 1. 开始开发：启动服务

```sh
docker compose --env-file .env --profile backend up -d
```

**目的：** 启动 db、api、planner，已有容器通常直接复用；配置或镜像变化时可重建容器。前提是已完成配置、构建和迁移。

| 片段 | 意思 |
|---|---|
| docker compose | 使用 Compose 管理本项目 |
| --env-file .env | 读取本地配置文件中的变量 |
| --profile backend | 同时启用 api、planner 所在的后端服务组 |
| up | 创建并启动服务 |
| -d | 在后台运行，终端可以继续操作 |

启动后查看状态：

```sh
docker compose --env-file .env --profile backend ps -a
```

看到 db 为 healthy、api 和 planner 为运行状态，再访问[后端就绪检查](http://127.0.0.1:8000/api/v1/health/ready)。运行状态只表示进程存在，最终以就绪检查及实际接口结果为准。

up 的创建、重建和数据卷保留语义见 [Docker 官方说明](https://docs.docker.com/reference/cli/docker/compose/up/)。

### 2. 结束开发：停止服务

```sh
docker compose --env-file .env --profile backend stop
```

**目的：** 停止本项目的容器，释放运行资源。保留容器、镜像与数据库数据；下次继续使用 up -d 启动。关闭终端不会停止由 -d 启动的服务。

### 3. 修改后端代码：重新构建并更新

```sh
docker compose --env-file .env --profile backend up -d --build api planner
```

**目的：** 将本地 backend/ 中的新代码重新打包，然后更新 API 与规划进程。--build 表示启动前构建镜像；依赖没有变化时，构建会尽量复用缓存。

本项目在构建镜像时复制代码，尚未配置源码挂载、watch 或自动重载。本地保存代码后不会自动生效，也不用手动进入容器复制文件。直接修改容器内代码也不会更新本地源码，重建后会丢失。

这条命令不执行数据库迁移；表结构有变化时，使用下面的[数据库表结构更新](#数据库表结构更新)流程。

### 4. 排查问题：查看日志

```sh
# 最近 100 行 API 和规划进程日志。
docker compose --env-file .env --profile backend logs --tail=100 api planner

# 持续观察 API 新日志。
docker compose --env-file .env --profile backend logs -f --tail=100 api

# 查看数据库日志。
docker compose --env-file .env logs --tail=100 db
```

**目的：** 查看启动失败、连接失败、任务错误等原因。--tail 限制返回行数，-f 持续显示新日志。在 logs -f 中按 Ctrl+C，只退出日志查看，服务继续运行。日志分享前检查是否包含私人内容或连接凭据。[官方日志命令](https://docs.docker.com/reference/cli/docker/compose/logs/)

### 5. 临时异常：重启后端进程

```sh
docker compose --env-file .env --profile backend restart api planner
```

**目的：** 使用现有容器、现有镜像和现有环境变量重启进程。它适合处理临时进程异常。

restart 不会重新构建代码，也不会应用刚修改的 .env。代码变化用 up --build；容器配置变化用下面的重建命令。[官方重启说明](https://docs.docker.com/reference/cli/docker/compose/restart/)

## 修改配置后怎么做

修改 JWT_SECRET、AI_PROVIDER、MAIL_PROVIDER 或后端连接地址后，重新创建 API 与规划容器：

```sh
docker compose --env-file .env --profile backend up -d --force-recreate api planner
```

**目的：** 让新容器读取最新环境变量；--force-recreate 表示强制重新创建。若同时修改了代码，再加 --build。

数据库密码有特殊之处：PostgreSQL 容器中的 POSTGRES_PASSWORD 只在新数据目录初始化时设置账号密码。数据库已有数据后，单改 .env 不会修改库里的密码；需通过数据库账号管理流程同步变更。日常不需要随意修改密码，也不要通过删除卷来处理密码问题。

## 首次初始化

只在新电脑或新开发环境第一次配置时执行。已存在 .env、数据库和数据卷时，先确认现有配置，不覆盖。

### 1. 检查 Docker 工具

打开 Docker Desktop，完成首次设置，等待引擎运行，然后打开终端：

```sh
docker --version
docker compose version
docker info
```

分别检查 Docker 命令、Compose 工具、引擎连接。若找不到命令，先完成 Docker Desktop 的命令行工具设置，再重新打开终端。

### 2. 准备本地配置

根据根目录 [.env.example](../../../.env.example) 创建 .env，配置独立数据库密码、至少 32 字符的随机 JWT_SECRET、后端数据库地址。 .env 已被 Git 忽略。

下面的脚本使用 Python 标准库生成配置，不输出密码，不覆盖已有 .env。需要本机已有 Python 3；若本项目独立虚拟环境已存在，也可将 python3 替换为 .venv/bin/python。

```sh
python3 - <<'PY'
import os
import secrets
from urllib.parse import urlunsplit

password = secrets.token_hex(24)
def database_url(host):
    return urlunsplit(("postgresql+psycopg", f"yirenyoulu_dev:{password}@{host}",
                      "/yirenyoulu_dev", "", ""))

values = {
    "APP_ENV": "development",
    "POSTGRES_PASSWORD": password,
    "JWT_SECRET": secrets.token_hex(32),
    "DATABASE_URL": database_url("127.0.0.1:55432"),
    "CONTAINER_DATABASE_URL": database_url("db:5432"),
    "AI_PROVIDER": "mock",
    "MAIL_PROVIDER": "disabled",
}
fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as file:
    file.write("".join(f"{key}={value}\n" for key, value in values.items()))
print("本地配置已创建")
PY
```

FileExistsError 表示 .env 已存在，保留并检查原配置即可。此示例启用模拟 AI，仅验证流程；真实模型、地图、邮件需要另行接入与验证。

可先校验配置，下面的命令只报告是否有效，不展开密码：

```sh
docker compose --env-file .env --profile backend config --quiet
```

成功时通常没有输出。完整 config 和 config --environment 会展开环境变量，可能显示密码，不要把完整输出贴到公开渠道。

### 3. 启动数据库、构建镜像

```sh
docker compose --env-file .env up -d db
docker compose --env-file .env --profile backend build api
```

第一条启动 PostgreSQL；首次会下载数据库镜像并初始化数据目录。第二条安装后端依赖并复制代码，生成 API 与 planner 共用的镜像，尚未启动长期运行的后端。

### 4. 创建表，再导入可选测试数据

```sh
docker compose --env-file .env --profile backend run --rm api \
  python -m alembic -c backend/alembic.ini upgrade head

# 可选：导入 9 个虚拟地点，景点、酒店、餐厅各 3 个。
docker compose --env-file .env --profile backend run --rm api \
  python -m app.seed
```

第一条按已提交的 Alembic 迁移创建或更新表结构；第二条补充明确标记的虚拟开发数据，不创建默认账号。run --rm 会临时创建一个后端容器执行命令，结束后删除该临时容器，数据库数据卷保留。

seed 允许重复执行，已有测试地点会跳过；它不是已有数据的通用更新工具，不会因为脚本里的名称改了就覆盖原记录。

### 5. 启动并检查

```sh
docker compose --env-file .env --profile backend up -d api planner
docker compose --env-file .env --profile backend ps -a
```

访问[接口调试页](http://127.0.0.1:8000/docs)及[就绪检查](http://127.0.0.1:8000/api/v1/health/ready)。首次初始化完成后，日常只需启动，不必每天重新创建配置、迁移或导入数据。

Docker 管理数据库和后端运行环境。鸿蒙客户端需 DevEco Studio 单独构建、配置后端地址；iOS 按其独立工程接入。

## 数据库数据变动与表结构变动

| 变化 | 需要的操作 |
|---|---|
| 用户创建行程、修改资料、增删收藏 | 后端自动保存，下一次查询读取已提交数据 |
| 在 DBeaver 修改记录 | 保存并提交事务；界面可能需要刷新 |
| 修改本地 JSON、CSV 或导入脚本 | 执行经过校验的导入或更新流程，不会自动同步 |
| 增加表、字段或数据库约束 | 开发者先提交新的 Alembic 迁移，再执行升级 |
| 修改 backend/ 里的业务代码或依赖 | 重建镜像并更新 api、planner |

数据库记录变化不需要重建镜像。普通 stop、restart 或后端镜像重建保留数据卷。

### 数据库表结构更新

仅在代码已包含新的、经过验证的迁移时使用。修改 ORM 模型本身不会自动生成数据库字段。开发库有需要保留的数据时，先按运维说明备份。

```sh
# 让镜像包含新的迁移文件。
docker compose --env-file .env --profile backend build api

# 避免后端在迁移过程中继续读写。
docker compose --env-file .env --profile backend stop api planner

# 数据库保持运行；若此前已停止，先执行 up -d db。
docker compose --env-file .env --profile backend run --rm api \
  python -m alembic -c backend/alembic.ini upgrade head

# 迁移成功后再启动新版后端。
docker compose --env-file .env --profile backend up -d api planner
```

任一步失败，先排查该步，不继续启动新版后端。这是本地开发流程；生产迁移与恢复见[迁移与备份恢复](../03数据库/迁移与备份恢复.md)。

## 连接 DBeaver 和查看数据

数据库启动后，在 DBeaver 新建 PostgreSQL 连接：

| 字段 | 本项目开发环境 |
|---|---|
| 主机 | 127.0.0.1 |
| 端口 | 55432 |
| 数据库 | yirenyoulu_dev |
| 用户名 | yirenyoulu_dev |
| 密码 | 本地 .env 中 POSTGRES_PASSWORD 的值 |

连接后展开 Schemas → public → Tables。双击 places 表并选择“数据”，导入 fixture 后可看到虚拟地点。

127.0.0.1:55432 是 Mac 访问入口；后端容器通过 db:5432 访问同一数据库。专用 yirenyoulu_test 测试库属于另一环境，不与这个开发卷混用；自动化数据库测试会清理测试库内容。

也可进入正在运行的数据库容器，使用命令行查看：

```sh
docker compose --env-file .env exec db \
  psql -U yirenyoulu_dev -d yirenyoulu_dev
```

进入 psql 后，以下命令只做查看：

```sql
SELECT current_database();
SELECT COUNT(*) FROM places;
```

输入 \q 退出 psql。exec 在已经运行的容器里执行命令；run 为一次性任务新建容器。[官方 exec 说明](https://docs.docker.com/reference/cli/docker/compose/exec/)

## 常用查看与排错命令

| 命令 | 含义与目的 |
|---|---|
| docker ps | 查看整台电脑正在运行的容器 |
| docker ps -a | 连同已停止的容器一起查看 |
| docker images | 查看本地已有镜像 |
| docker volume ls | 查看持久化数据卷 |
| docker stats --no-stream | 查看容器 CPU、内存等资源的单次快照 |
| docker compose --env-file .env --profile backend config --services | 查看当前配置启用的服务名，不展开密码 |
| docker compose --env-file .env --profile backend ps -a | 查看本项目服务及其端口、运行状态 |

常见问题按下面顺序处理：

| 现象 | 优先检查 |
|---|---|
| docker 命令找不到 | Docker Desktop 是否安装并完成命令行工具设置；重新打开终端 |
| 提示无法连接 Docker daemon | Docker Desktop 是否打开、引擎是否就绪；也可能是 socket 权限或 Docker context 不匹配 |
| docker compose 不可用 | Docker Desktop 的首次设置和 Compose 插件是否就绪 |
| POSTGRES_PASSWORD 缺失 | 是否在项目根目录、是否已有正确的 .env |
| 端口已被占用 | 是否已有另一个项目使用 55432 或 8000；先识别占用进程，不直接结束未知进程 |
| 数据库密码认证失败 | .env 密码是否与数据库初始化时一致，是否误连其他实例 |
| db 运行，api 启动失败 | 查看 api 日志，检查 JWT_SECRET、CONTAINER_DATABASE_URL 和迁移 |
| 修改代码后没有变化 | 是否执行了 --build 并更新 api、planner |
| 修改 .env 后没有变化 | 是否重新创建容器；restart 不加载新环境变量 |
| DBeaver 连接失败 | db 状态、55432 端口、库名、账号及密码 |
| 数据库能连，但没有地点 | 是否已执行可选 seed；没有默认真实数据 |
| AI 或邮件提示不可用 | 检查供应商配置；mock 不是真实服务 |

排错优先用 ps、logs、config --quiet；不要先删除数据卷或重新初始化数据库。

## 停止与删除的区别

| 操作 | 容器 | 数据库数据 |
|---|---|---|
| stop | 保留但停止 | 保留 |
| restart | 使用现有配置重新启动 | 保留 |
| up -d --build api planner | 按新镜像更新后端容器 | 保留 |
| down，不加 -v | 停止并删除项目容器、网络 | 本项目命名数据卷保留 |
| down 加 -v / --volumes | 同时删除项目声明的数据卷 | 会删除开发数据库数据 |

需要移除容器和网络、但保留数据库时：

```sh
docker compose --env-file .env --profile backend down
```

以后使用 up -d 可重新创建容器并挂载原数据卷。本项目已固定项目名 yirenyoulu-v2-dev，单纯移动项目目录不会改变卷名；修改项目名（包括 -p、COMPOSE_PROJECT_NAME）或卷配置可能连接到新卷，原卷不一定已被删除。

日常停工使用 stop 即可。不要把 down -v、docker volume rm、带卷删除的清理操作用于普通重启或密码修复；这些操作可能删除数据。Docker Desktop 中手动删除数据卷也有同样影响。[官方 down 及卷删除规则](https://docs.docker.com/reference/cli/docker/compose/down/)

备份、恢复、账户注销记录重放和生产运维统一参考[迁移与备份恢复](../03数据库/迁移与备份恢复.md)。本手册的命令说明不代表本机已经启动服务或完成业务验收。
