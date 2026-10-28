# 一人有路 · iOS客户端

React Native + TypeScript，Expo SDK 57。采用自然青绿与暖白主题，随系统切换深色。探索、行程、我的三个入口覆盖注册登录、资料和账户、城市及三类地点、收藏、推荐依据、手动行程及地点编辑。地图、真实AI、邮件投递与应用商店发布不在当前交付范围。

[第三期需求](../../docs/产品/04迭代需求/第03期-iOS客户端设计与核心业务联调.md) · [第三期验收](../../docs/技术开发/07测试与交付/第03期验收.md)

## 环境

Node.js 24（>=24.3）、npm、Python 3.11后端开发环境。依赖以package-lock.json为准，用`npm ci`恢复。本机使用Expo 57.0.31、React Native 0.86.3、React 19.2.3、TypeScript 5.9.3验证；TypeScript按OpenAPI生成工具的受支持peer范围锁定，Expo建议的6.0尚未升级，不用强制忽略peer冲突。

## 一条命令预览

首次检出时在仓库根目录准备后端环境，已有`.venv`可直接安装所需开发依赖：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
cd frontend/ios
npm ci
npm run preview
```

打开终端提示的本机8081地址。命令启动回环地址18000上的**内存测试API**和同一套React Native页面，不使用Docker、不读取`.env`连接、不创建数据库文件、不改现有数据库。所有地点标为测试资料；可自行注册临时账户体验，停止后账户、收藏、行程全部消失，不发送邮件。退出预览用Ctrl+C；端口占用时先停止之前的预览，不自动终止其他进程。

Windows的首次准备命令为`py -3.11 -m venv .venv`、`.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt`，随后进入frontend/ios执行相同npm命令；Windows实际运行尚未验证。

浏览器凭据只存内存，刷新页面后重新登录；iOS适配Expo SecureStore/Keychain，原生安全存储仍需Xcode与设备验收。预览成功不代表iOS原生编译、签名或真机通过。

## 连接真实开发后端

在frontend/ios复制`.env.example`为`.env`，配置公开参数：

```dotenv
EXPO_PUBLIC_APP_ENV=development
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
```

启动现有后端，执行`npm run web`，不要同时启动同端口的隔离预览。浏览器需后端显式设置`CORS_ORIGINS=["http://localhost:8081","http://127.0.0.1:8081"]`并重启API；默认不开放跨域，不使用通配符。这个变量位于后端运行环境，不是客户端密钥。

手机访问时API地址须改为可达的Mac局域网地址或开发域名；手机的localhost指手机本身。只开放需要的API，不把PostgreSQL端口暴露给手机或公网。真实开发库上的注册、收藏和行程会真实保存，只有标注“测试环境”的隔离预览会自动丢弃数据。

## 检查与回归

```sh
npm run contract:check
npm run typecheck
npm run lint
npm run format:check
npm test
npm run export:web
npm run export:ios
```

契约来自仓库OpenAPI；协议变更后执行`npm run generate`，提交生成的类型和运行时JSON Schema。请求成功体在边界校验，204不解JSON；错误保留类别、字段与请求ID，不记录密码、令牌或完整载荷。

另开终端并保持`npm run preview`运行，可执行`npm run smoke`。默认使用已安装Google Chrome；没有Chrome时先`npx playwright install chromium`，以`PLAYWRIGHT_CHANNEL=chromium npm run smoke`运行。该回归只接受本机测试预览，不连接任意外部环境，涵盖注册、收藏、响应丢失的幂等重试、行程及地点修改删除、来源撤回刷新、资料改密和注销。可设置`PREVIEW_ARTIFACTS`为受控本地目录保存测试截图，不提交账户或真实数据截图。

## 原生构建与后续发布

完整Xcode与匹配的iOS SDK安装后，按锁定Expo版本核对兼容性，可运行`npx expo run:ios`生成并构建本地原生工程。生成的ios目录不提交，原生配置由app.config.ts管理；第三方原生依赖变化须重新构建。当前开发Bundle ID仅为`com.catchman1.yirenyoulu.dev`示例，不代表已注册开发者主体；正式标识通过`IOS_BUNDLE_IDENTIFIER`确定，签名材料不入库。不自动调用EAS云构建、注册账号或产生付费。

`export:ios`只验证Hermes/JavaScript资源打包，不产生已签名IPA。Release须配置production环境、HTTPS API、正式Bundle ID并关闭开发HTTP例外，完成实际设备、Keychain、权限、字体缩放及恢复验收。

## 当前依赖限制

npm审计报告Expo CLI/config链上的zod与deepmerge间接风险（3高、5低）；上游当前兼容范围尚无直接安全修复，未强制跨主版本覆盖或按audit建议退回旧Expo。开发预览仅回环地址，工具链不对公网提供服务。升级后须复核生成、构建和回归；此项与Xcode/真机验证一起阻止将本次交付视为生产或上架通过。
