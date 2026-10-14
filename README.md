# 一人有路

面向独自旅行者的行程规划与AI伴游应用，支持鸿蒙和iOS。提供景点、酒店、餐厅浏览与搜索、地点收藏、每日行程编辑、地图导航和多轮AI对话。

## 文档

- [文档目录](docs/README.md)
- [产品需求](docs/产品/02需求与体验/首版需求.md)
- [分期开发需求](docs/产品/04迭代需求/README.md)
- [页面与交互](docs/产品/02需求与体验/页面与交互.md)
- [系统架构](docs/技术开发/01架构/双端架构.md)
- [API契约](docs/技术开发/02接口与权限/API契约.md)
- [开发规范](docs/技术开发/06部署与协作/开发规范与发布准备.md)
- [数据库初始化与恢复](docs/技术开发/03数据库/迁移与备份恢复.md)

## 技术栈与开发状态

鸿蒙使用ArkTS/ArkUI，iOS使用React Native + TypeScript，后端使用Python FastAPI、PostgreSQL和Alembic。两端分别构建与发布，共用业务接口。

当前已提供数据库基础、迁移、测试数据初始化与自动检查；业务API和客户端工程待开发。接口和客户端文档为设计规范，实际可运行范围以代码与构建结果为准。

## 仓库检查

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_repository.py --history
```

开发环境从.env.example配置，数据库操作见初始化文档。密钥、签名材料、数据库文件和个人数据不得提交到仓库。
