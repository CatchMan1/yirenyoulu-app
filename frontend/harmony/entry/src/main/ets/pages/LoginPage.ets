import { router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { ApiClient, publicError } from '../services/ApiClient';

@Entry
@Component
struct LoginPage {
  @State identifier: string = '';
  @State email: string = '';
  @State password: string = '';
  @State nickname: string = '';
  @State resetToken: string = '';
  @State mode: number = 0;
  @State busy: boolean = false;
  @State error: string = '';
  @State notice: string = '';
  private client: ApiClient = ApiClient.get();

  async submit(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true; this.error = ''; this.notice = '';
    try {
      if (this.mode === 0) {
        await this.client.login(this.identifier, this.password);
        this.password = '';
        await router.replaceUrl({ url: 'pages/MainPage' });
      } else if (this.mode === 1) {
        await this.client.send<null>('/auth/register', http.RequestMethod.POST,
          JSON.stringify({ username: this.identifier, email: this.email, password: this.password, nickname: this.nickname }), false);
        this.mode = 0; this.password = ''; this.notice = '注册成功，请登录';
      } else if (this.resetToken) {
        await this.client.send<null>('/auth/password-reset/confirm', http.RequestMethod.POST,
          JSON.stringify({ token: this.resetToken, new_password: this.password }), false);
        this.resetToken = ''; this.password = ''; this.mode = 0; this.notice = '密码已更新，请重新登录';
      } else {
        await this.client.send<null>('/auth/password-reset/request', http.RequestMethod.POST,
          JSON.stringify({ email: this.email }), false);
        this.notice = '请求已受理；如账户存在且邮件服务可用，请查看邮件';
      }
    } catch (error) { this.error = publicError(error); }
    finally { this.busy = false; }
  }

  build() {
    Scroll() {
      Column({ space: 16 }) {
        Text('一人有路').fontSize(32).fontColor($r('app.color.brand_primary')).margin({ top: 48 })
        Text(this.mode === 0 ? '用户名 / 邮箱登录' : this.mode === 1 ? '创建账户' : '找回密码').fontSize(20)
        if (this.mode !== 2) {
          TextInput({ placeholder: this.mode === 1 ? '用户名：3–50位字母数字下划线' : '用户名或邮箱', text: this.identifier }).onChange((value: string) => this.identifier = value)
        }
        if (this.mode !== 0) {
          TextInput({ placeholder: '邮箱', text: this.email }).onChange((value: string) => this.email = value)
        }
        if (this.mode === 1) {
          TextInput({ placeholder: '昵称（可选）', text: this.nickname }).onChange((value: string) => this.nickname = value)
        }
        if (this.mode === 2) {
          TextInput({ placeholder: '邮件中的一次性令牌（收到后填写）', text: this.resetToken }).onChange((value: string) => this.resetToken = value)
        }
        TextInput({ placeholder: this.mode === 0 ? '密码' : '密码：12–128字符', text: this.password }).type(InputType.Password).onChange((value: string) => this.password = value)
        if (this.error) { Text(this.error).fontColor($r('app.color.status_error')) }
        if (this.notice) { Text(this.notice).fontColor('#286B38') }
        Button(this.busy ? '处理中…' : this.mode === 0 ? '登录' : this.mode === 1 ? '注册' : this.resetToken ? '设置新密码' : '发送找回邮件')
          .enabled(!this.busy).width('100%').onClick(() => this.submit())
        Row({ space: 16 }) {
          Button(this.mode === 0 ? '注册账户' : '返回登录').onClick(() => { this.mode = this.mode === 0 ? 1 : 0; this.error = ''; this.password = ''; })
          Button('忘记密码').onClick(() => { this.mode = 2; this.error = ''; this.password = ''; })
        }
        Text('开发测试版本；不含真实地点数据。').fontColor($r('app.color.text_secondary'))
      }.padding(24).width('100%')
    }.width('100%').height('100%')
  }
}
