# 一人有路 · 新版

ArkTS/ArkUI + Python FastAPI。面向正式上架的独立新版本，当前处于基础建设，**尚未达到生产或上架标准**。

- [设计与范围](docs/superpowers/specs/2026-10-13-release-design.md)
- [分阶段实施计划](docs/superpowers/plans/2026-10-13-release-foundation.md)
- [旧代码审查](docs/source-audit.md)
- [接口契约基线](docs/api-contract.md)（设计状态，尚未导出可验收 OpenAPI）
- [阶段记录](docs/stages/01-foundation.md)

## 隔离原则
原项目及其两个 Gitee 仓库只读。新仓库不继承旧 Git 历史，不迁入旧环境、数据库、签名、依赖或数据集。前后端将在 `frontend/` 与 `backend/` 分别构建部署。

首版以用户名/邮箱与密码登录；高德地图；AI 仅允许免费接口，不自动购买或转付费。测试数据闭环通过之前禁止正式批量采集。

## 当前可执行检查
```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_repository.py --history
```
检查包含工作树、暂存区、可达历史的禁止文件和常见凭据模式。它不等同于完整隐私审查，不能证明资源商用权；每次上传仍需人工审查拟提交文件及历史。

不要从旧项目复制 `.env`。在新环境从 `.env.example` 填写独立配置；敏感字段样例必须为空。尚未提供可启动的新版业务服务，启动与部署操作会随对应阶段实现交付。
