# iOS 开发分支说明

日期：2026-10-14。

## 用户决定与本次范围
用户要求保留现有鸿蒙版，并建立独立的 iOS 新开发分支。本次创建 `feat/ios-react-native`，记录 iOS 开发方向；尚未创建 React Native 工程、安装前端依赖或接入地图。

## 保留关系
- 原鸿蒙项目：`/Users/Admin/Documents/yirenyoulu`，前后端各自的 Gitee 仓库继续保留，代码、HEAD、远程与数据库均不修改。
- 新仓库：`/Users/Admin/Documents/yirenyoulu-app`，远端仅指向 `https://github.com/CatchMan1/yirenyoulu-app.git`。
- `main` 保留已有新版后端基础；iOS 分支从 `b4e0bf78386bcd4b4da67bcf4c2589923dfd50b8` 建立，后续前端调整只在 iOS 分支推进。
- 新仓库目前不包含鸿蒙前端源码；保留鸿蒙版是保留原目录与 Gitee 仓库，不意味着新仓库中已存在完整鸿蒙版本。
- Git 分支隔离源码，不自动隔离配置、运行进程或数据库。iOS 后续使用新仓库独立环境，禁止复用旧鸿蒙项目的数据库或配置。

## iOS 技术方向
结合前面的讨论，分支按 React Native + TypeScript 方向命名和规划；FastAPI、PostgreSQL、Alembic 与已建立的权限/事务设计继续沿用。具体 React Native/Expo 工作流和版本在前端工程建立前确定并验证，当前不宣称已完成兼容测试。

高德和 Google Maps 均为候选；用户尚未最终选定 iOS 地图服务商，也未授权开通计费或接受商业协议。`com.catchman1.yirenyoulu` 仅是此前讨论的 Bundle ID 示例，尚未注册、绑定或配置到工程。

## 后续实施顺序
1. 补齐后端 DTO/OpenAPI，继续认证、目录/收藏、行程与持久任务、AI历史及推荐行为链路。
2. 在本分支创建 iOS 前端工程，验证本地构建、模拟器/真机与后端连接。
3. 确定地图服务商及应用标识后验证地图标记、导航、权限和异常降级。
4. 逐页完成登录资料、浏览搜索收藏、行程编辑与生成、AI伴游；以标记测试数据完成端到端验收。
5. 测试数据闭环通过后才进入真实数据来源/费用/授权决策及采集阶段。

原设计与实施计划中的业务、安全、数据真实性和采集闸门继续有效；其中 ArkTS/ArkUI 前端实施与 DevEco 验收步骤在本分支由 React Native/iOS 构建与验收替代。旧设计保留作历史记录，不将其旧平台描述当作本分支继续迁入鸿蒙代码的指令。

## 当前未验证
React Native 工程、Xcode工具链、iOS签名、地图SDK和免费AI真实服务均未验证。创建分支不代表 iOS App 已经实现或可安装。
