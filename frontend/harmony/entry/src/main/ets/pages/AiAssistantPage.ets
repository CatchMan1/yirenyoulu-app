import { router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { ChatSession, Message, CursorMeta, PageMeta } from '../models/ApiModels';
import { TravelApi } from '../services/TravelApi';
import { messageId, publicError } from '../services/ApiClient';
import { validId } from '../services/DataGuard';
import { LoadState } from '../components/LoadState';

interface ChatRoute { tripId?: string; }

@Entry
@Component
struct AiAssistantPage {
  @State sessions: ChatSession[] = [];
  @State sessionsPage: number = 1;
  @State sessionsMore: boolean = false;
  @State messages: Message[] = [];
  @State sessionId: string = '';
  @State text: string = '';
  @State title: string = '';
  @State busy: boolean = false;
  @State error: string = '';
  @State providerMode: string = '';
  @State before: number | null = null;
  @State hasMore: boolean = false;
  @State retryAvailable: boolean = false;
  private tripId: string | null = null;
  private api: TravelApi = new TravelApi();
  private generation: number = 0;
  private pendingId: string = '';
  private pendingText: string = '';
  aboutToAppear(): void {
    const params = router.getParams() as ChatRoute;
    if (params && params.tripId && validId(params.tripId)) { this.tripId = params.tripId; }
    this.load();
  }
  aboutToDisappear(): void { this.generation++; }
  async load(more: boolean = false): Promise<void> {
    const generation = ++this.generation; const page = more ? this.sessionsPage + 1 : 1; this.busy = true; this.error = '';
    try {
      const response = await this.api.sessions(page);
      if (generation === this.generation) {
        const sessions = response.data === null ? [] : response.data;
        this.sessions = more ? this.sessions.concat(sessions.filter((session: ChatSession) => !this.sessions.some((item: ChatSession) => item.id === session.id))) : sessions;
        this.sessionsPage = page; this.sessionsMore = (response.meta as PageMeta).has_more;
      }
    }
    catch (error) { if (generation === this.generation) { this.error = publicError(error); } }
    finally { if (generation === this.generation) { this.busy = false; } }
  }
  async select(session: ChatSession, older: boolean = false): Promise<void> {
    const generation = ++this.generation; this.busy = true; this.error = '';
    try {
      const response = await this.api.messages(session.id, older ? this.before : null);
      if (generation !== this.generation) { return; }
      const messages = response.data === null ? [] : response.data;
      this.messages = older ? messages.concat(this.messages) : messages;
      this.sessionId = session.id; this.title = session.title;
      const meta = response.meta as CursorMeta; this.before = meta.next_before_sequence; this.hasMore = meta.has_more;
      if (!older) {
        this.pendingId = ''; this.pendingText = ''; this.retryAvailable = false;
        const failed = messages.length > 0 ? messages[messages.length - 1] : null;
        if (failed !== null && failed.role === 'assistant' && failed.status === 'failed') {
          const user = messages.find((message: Message) => message.message_id === failed.message_id && message.role === 'user');
          if (user) { this.pendingId = user.message_id; this.pendingText = user.content; this.retryAvailable = true; }
        }
      }
    } catch (error) { if (generation === this.generation) { this.error = publicError(error); } }
    finally { if (generation === this.generation) { this.busy = false; } }
  }
  async create(): Promise<void> {
    if (this.busy) { return; } this.busy = true; this.error = '';
    try {
      const session = await this.api.createSession(JSON.stringify({ title: this.title || '新对话', trip_id: this.tripId }));
      this.sessions = [session].concat(this.sessions); this.sessionId = session.id; this.messages = []; this.hasMore = false; this.retryAvailable = false; this.pendingId = ''; this.pendingText = '';
    } catch (error) { this.error = publicError(error); } finally { this.busy = false; }
  }
  async send(retry: boolean = false): Promise<void> {
    if (this.busy || !this.sessionId || (!retry && !this.text.trim())) { return; }
    const generation = this.generation; const sessionId = this.sessionId; this.busy = true; this.error = '';
    if (!retry) { this.pendingId = messageId(); this.pendingText = this.text; }
    try {
      const turn = await this.api.send(sessionId, JSON.stringify({ message_id: this.pendingId, content: this.pendingText }));
      if (generation !== this.generation || sessionId !== this.sessionId) { return; }
      this.messages = this.messages.filter((message: Message) => message.message_id !== this.pendingId).concat([turn.user_message, turn.assistant_message]);
      this.providerMode = turn.provider_mode; this.retryAvailable = false; this.text = ''; this.pendingId = ''; this.pendingText = '';
    } catch (error) { if (generation === this.generation) { this.error = publicError(error); this.retryAvailable = true; } }
    finally { if (generation === this.generation) { this.busy = false; } }
  }
  async manage(remove: boolean): Promise<void> {
    if (this.busy || !this.sessionId) { return; } this.busy = true; this.error = '';
    try {
      if (remove) {
        await this.api.client.request<null>('/chat-sessions/' + this.sessionId, http.RequestMethod.DELETE);
        this.sessions = this.sessions.filter((session: ChatSession) => session.id !== this.sessionId); this.sessionId = ''; this.messages = []; this.retryAvailable = false;
      } else {
        const session = await this.api.data<ChatSession>('/chat-sessions/' + this.sessionId, http.RequestMethod.PATCH, JSON.stringify({ title: this.title }));
        this.sessions = this.sessions.map((item: ChatSession) => item.id === session.id ? session : item);
      }
    } catch (error) { this.error = publicError(error); } finally { this.busy = false; }
  }
  build() {
    Scroll() {
      Column({ space: 12 }) {
        Button('返回').onClick(() => router.back())
        Text('AI伴游与历史会话').fontSize(24).fontColor($r('app.color.brand_primary'))
        Text(this.tripId === null ? '通用旅行对话' : '新对话将绑定当前行程')
        TextInput({ placeholder: '会话标题', text: this.title }).onChange((value: string) => this.title = value)
        Button('创建新会话').enabled(!this.busy).onClick(() => this.create())
        ForEach(this.sessions, (session: ChatSession) => {
          Button((this.sessionId === session.id ? '✓ ' : '') + session.title).enabled(!this.busy).onClick(() => this.select(session))
        }, (session: ChatSession) => session.id)
        if (this.sessionsMore) { Button('加载更多会话').enabled(!this.busy).onClick(() => this.load(true)) }
        if (this.sessionId) {
          Row({ space: 8 }) { Button('重命名').enabled(!this.busy).onClick(() => this.manage(false)); Button('删除会话及消息').enabled(!this.busy).onClick(() => this.manage(true)) }
          if (this.hasMore) { Button('加载更早消息').enabled(!this.busy).onClick(() => { const session = this.sessions.find((session: ChatSession) => session.id === this.sessionId); if (session) { this.select(session, true); } }) }
          ForEach(this.messages, (message: Message) => {
            Column({ space: 6 }) {
              Text(message.role === 'user' ? '我' : '伴游助手').fontColor($r('app.color.text_secondary'))
              Text(message.status === 'failed' ? '回复失败：' + message.error_code : message.content)
              if (message.status === 'pending' || message.status === 'running') { Text('处理中；请刷新历史查看状态') }
            }.width('100%').padding(12).backgroundColor(message.role === 'user' ? $r('app.color.surface_user') : $r('app.color.surface_neutral'))
          }, (message: Message) => message.id)
          if (this.messages.length === 0) { Text('暂无消息') }
          if (this.providerMode) { Text('服务模式：' + this.providerMode) }
          TextArea({ placeholder: '输入本次问题', text: this.text }).onChange((value: string) => this.text = value)
          Button('发送新消息').enabled(!this.busy).onClick(() => this.send())
          Button('刷新当前会话历史').enabled(!this.busy).onClick(() => { const session = this.sessions.find((item: ChatSession) => item.id === this.sessionId); if (session) { this.select(session); } })
          if (this.retryAvailable) { Button('原位重试上一条消息').enabled(!this.busy).onClick(() => this.send(true)) }
        }
        LoadState({ loading: this.busy, error: this.error, onRetry: () => this.load() })
      }.width('100%').padding(20)
    }.width('100%').height('100%')
  }
}
