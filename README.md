# 一人有路 · 鸿蒙与iOS新版

保留鸿蒙ArkTS/ArkUI，新增React Native + TypeScript iOS，共用Python FastAPI后端。本轮完成开发前文档整理与设计草案；当前只有数据库基础，尚无新版业务API和客户端工程，不具备生产或上架验收结论。

## 开始阅读

- [完整文档导航](docs/README.md)
- [首版需求](docs/产品/02需求与体验/首版需求.md)
- [双端技术架构](docs/技术开发/01架构/双端架构.md)
- [待确认决策与阶段闸门](docs/产品/03范围与决策/决策与阶段闸门.md)
- [原资料分类清单](docs/原资料分类与处理清单.md)
- [数据库初始化与恢复](docs/技术开发/03数据库/迁移与备份恢复.md)

原项目及两个Gitee仓库只读，新仓库独立环境/数据库/历史。前端目标目录frontend/harmony与frontend/ios，分别构建发布；本轮不创建工程。用户名/邮箱密码先行，AI仅使用免费服务，iOS地图供应商待定。测试数据闭环前不正式批量采集。

## 已有检查

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_repository.py --history
```

检查包括工作树、暂存区和可达历史，但不能代替人工隐私及资源授权审查。本地90历史资料不上传，禁止强制添加。配置从.env.example设置独立环境，敏感值不得写入文档。当前数据库基础的启动说明不等于新版业务服务已经可启动。
