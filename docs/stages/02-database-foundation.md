# 阶段2进行中：数据库基础
日期：2026-10-13。

## 实现内容
- 新仓库独立 Python3.11 .venv；固定依赖快照，不安装到旧环境。
- SQLAlchemy 新模型，涵盖用户/会话、城市/分类/标签、统一地点/来源/外部ID/图片、收藏、行程/快照、生成任务、AI会话/消息、行为。
- 冻结的 Alembic 0001_initial 迁移；环境限制只接受对应新项目 PostgreSQL 库。
- 显式、幂等、禁止生产运行的9地点fixture导入；不创建用户或模拟真实行为，不编造价格/评分/坐标。
- 开发 Compose、迁移/备份/恢复说明，CI PostgreSQL迁移往返和约束验证。

## 本地验证
`PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q`：22通过、1跳过（PostgreSQL环境未配置）。另发布防护7项通过。
`alembic upgrade head --sql`：成功生成339行PostgreSQL SQL；只证明离线编译，不代表已在PostgreSQL运行。
CI执行结果在真实运行后补充。

## 未完成/未验证
- 完整DTO/OpenAPI、业务路由、权限、认证、worker、协同推荐、前端迁入与联调仍未完成；表结构不等于闭环。
- PostgreSQL迁移以CI实际结果为准；备份恢复尚未演练。
- DevEco/SDK/模拟器未配置；地图、免费AI真实接口未验证。
- 未执行正式采集；上架闸门保持关闭。

## 技术裁决
- 只复用已有 py311_env 的解释器创建新venv，不共享依赖和配置。
- 本机无Docker，使用GitHub临时PostgreSQL服务验证数据库；不安装/启动或接触原有数据库。
- 当前使用单体和持久任务表，不引入Redis/Kafka。
- 新空仓库阶段提交直接在main；Git仅配置新仓库的Codex代理身份与noreply邮箱，未修改全局身份。
