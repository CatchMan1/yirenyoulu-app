# iOS前端开发规范 · React Native

适用React Native + TypeScript。与[通用工程规范](通用工程规范.md)配合使用；具体路由与数据字段遵循项目契约。Expo为可选工程工作流，不自动等同于必须采用的依赖。

## 1. 工程结构

```text
frontend/ios/
  src/
    features/           # 业务页面、专属组件、hooks和mapper
    api/                # HTTP实例、错误映射、业务请求、DTO
    components/         # 跨业务复用UI
    store/              # 少量全局客户端状态
    platform/           # 安全存储、地图、导航等原生适配
    theme/              # 颜色、间距、字体等tokens
  app/                  # 仅采用Expo Router时存在，路由入口保持轻量
  ios/                  # 仅工程工作流实际管理原生目录时存在
```

已有小项目可以保留api/components/hooks/interfaces等平铺结构；不为模板强行迁移目录。全局状态目录统一用store，避免store与stores分裂。路由入口组合业务页面，复杂逻辑放对应feature；共享层不能反向导入业务页面。

## 2. TypeScript与组件

启用strict，禁止隐式any和未经说明的ts-ignore；外部输入使用unknown并校验。对象和数组类型明确，状态用可区分联合类型表达互斥状态，避免loading/error/data三者组合出不可能状态。DTO字段沿用协议，视图模型通过集中mapper转换。

函数组件为默认；Props显式定义，只读输入，不原地修改父组件对象。列表key用稳定ID，不用index替代可变记录标识。Hook遵循调用规则，依赖声明完整，不用禁用lint来掩盖闭包问题。

useMemo/useCallback仅用于明确的引用稳定或计算成本，不能默认包裹所有函数。页面文件按导入、类型/常量、组件、样式组织；页面组件PascalCase，Hook为useXxx，业务API采用verb+对象命名。

## 3. API返回与运行时校验

全工程一个HTTP实例负责环境、凭据、超时、取消和错误标准化。本项目JSON服务统一返回ApiResult<T>，含已解码data、meta和requestId；列表data保留协议数组结构，meta保留分页总数。页面不重复解包，不能丢失total/request_id。生成类型不是运行时校验，schema不匹配抛contract错误并保留请求ID。

数据边界的最小示例（类型校验与SDK选择无关）：

```typescript
interface VersionedResource {
  id: string;
  version: number;
}

export function decodeResource(input: unknown): VersionedResource {
  if (typeof input !== 'object' || input === null) {
    throw new Error('INVALID_RESPONSE');
  }
  const value = input as Record<string, unknown>;
  if (typeof value.id !== 'string' ||
      typeof value.version !== 'number' ||
      !Number.isInteger(value.version) || value.version < 1) {
    throw new Error('INVALID_RESPONSE');
  }
  return { id: value.id, version: value.version };
}
```

示例是最小形状校验；UUID、长度和业务字段仍按具体DTO验证。不得把它直接当作完整行程解码器。标准错误包装在请求层完成，不在页面反复解析Axios错误。响应request_id缺失按契约错误处理，网络错误没有响应ID时允许requestId为空。

## 4. 状态与生命周期

页面短期UI状态放组件/Hook；跨页面登录和偏好等客户端状态可用Zustand。服务器数据由一种统一查询/缓存方案管理；规模较小时业务Hook足够，需要缓存失效、分页去重时再引入专用库，不将同一数据同时复制到多个store。

每个查询具有query key（身份、条件、页码）与取消或request generation。搜索条件变化清空旧分页进度，忽略迟到响应；加载更多与刷新分别控制，不重复拼接记录。演示数据只能在明确mock环境显示，不与真实列表合并成生产结果。

Effect创建的订阅、计时器、请求、动画与原生监听器必须返回清理。清理要能承受开发环境重复挂载；异步回调写状态前检查请求和会话代次。AppState回前台查询服务器状态，后台暂停不必要轮询；组件卸载不意味着服务端任务已取消。

## 5. 认证与安全存储

认证状态明确bootstrapping/anonymous/authenticated/refreshing。启动hydrate完成前不发送私有请求；hydrate与退出并发时，会话epoch校验阻止旧token回写。安全存储的写入/删除串行化，退出增加epoch并让后续删除覆盖迟到写入，不能只做set({token:null})。

持久刷新凭据使用Keychain适配；Expo项目可采用SecureStore，原生工程选择兼容安全存储实现。访问token优先短时内存。安全存储拒绝/不可用时给出可恢复登录状态，不退回AsyncStorage存密钥。凭据恢复需服务端确认有效性，不能只判断“有字符串”。[React Native安全文档](https://reactnative.dev/docs/security)

收到401先比较请求捕获的session epoch；已切换身份则丢弃响应，不清理新会话、不用新账户重放。没有刷新协议时仅当前epoch的401触发清理并重新登录，不自行设计客户端伪刷新。存在刷新协议时采用单个共享Promise：同批401等待，成功后更新并重放合规请求一次；失败清理。每个请求记录发送时session epoch与token generation；只在epoch相同且generation更新时，迟到401才可用当前token合规重放，避免再次旋转；禁止刷新端点递归和无限循环。上传/流/非幂等写入不自动重放。

## 6. 原生能力与构建

地图、定位、安全存储、分享和外部导航放platform适配。SDK初始化遵循隐私同意要求；定位只在用户动作需要时请求，拒绝/受限/永久拒绝分别处理。导航链接验证scheme与参数，App未安装提供已验证的网页或地址降级。

iOS按工作流管理Info.plist、权限用途说明、entitlement、Pod依赖及隐私清单。权限不能用全局关闭ATS等方式“修复”；仅开发必要的网络例外需要限定目标且不进入发布配置。

Expo自定义原生能力使用开发构建；原生模块或插件变更后重新生成/构建，不把JS热更新当原生升级。prebuild生成目录与手动管理原生目录二选一地明确责任，避免下次生成覆盖手工修改。版本兼容性在锁定React Native/Expo/Xcode后验证。

前端环境变量只能放公开配置；EXPO_PUBLIC变量会进入JavaScript包，不能保存服务端秘密。[Expo环境变量文档](https://docs.expo.dev/guides/environment-variables/)

## 7. UI、性能与可访问性

统一主题tokens和StyleSheet；业务状态用稳定枚举，显示文案本地化。提供加载/空/错误/重试；适配安全区域、键盘遮挡、字体缩放、深色主题与VoiceOver标签。破坏性操作有明确确认，按钮触达区域和颜色对比满足平台可用性。

大列表使用虚拟化组件、稳定key和适当图片尺寸；先测量再优化。禁止在render执行网络调用、持久写入、密集JSON解析或大数组排序；CPU密集工作交给合适的原生/后台边界。图片/位置/请求缓存设置容量和过期条件。

## 8. 检查与测试

工程建立时配置lint、format:check、typecheck、test和构建脚本，命令以实际package.json为准。默认采用项目锁文件对应的冻结安装，不随意混用npm/yarn/pnpm。

关键测试覆盖：解码不匹配、204无body、并发401、迟到401、hydrate/退出/刷新竞争、搜索竞态、失败重试和卸载清理。组件测试按用户行为断言，原生能力另做模拟器/真机与Release构建验证，JS单测不证明SDK集成成功。[React Native测试文档](https://reactnative.dev/docs/testing-overview)

合并前运行相关静态和测试检查；原生依赖或配置变更必须构建。发布包核对环境、Bundle ID、签名、权限用途、URL scheme与真实服务，私有数据和凭据不得打入测试快照。
