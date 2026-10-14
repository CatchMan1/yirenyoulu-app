import { router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { Place, TripSummary, User, PageMeta, NamedEntry as Tag } from '../models/ApiModels';
import { ApiClient, publicError } from '../services/ApiClient';
import { TravelApi } from '../services/TravelApi';
import { priceText } from '../services/DataGuard';
import { BottomNavigation } from '../components/BottomNavigation';
import { SearchBar } from '../components/SearchBar';
import { LoadState } from '../components/LoadState';

@Entry
@Component
struct MainPage {
  @State tab: number = 0;
  @State places: Place[] = [];
  @State trips: TripSummary[] = [];
  @State busy: boolean = false;
  @State error: string = '';
  @State notice: string = '';
  @State kind: string = '';
  @State search: string = '';
  @State favoritesOnly: boolean = false;
  @State page: number = 1;
  @State hasMore: boolean = false;
  @State reason: string = '';
  @State nickname: string = '';
  @State signature: string = '';
  @State tags: Tag[] = [];
  @State selectedTags: string[] = [];
  @State currentPassword: string = '';
  @State newPassword: string = '';
  @State verified: boolean = false;
  @State verifyToken: string = '';
  @State confirmDelete: boolean = false;
  private api: TravelApi = new TravelApi();
  private generation: number = 0;
  private pace: string = 'normal';

  aboutToAppear(): void {
    this.api.client.onExpired = () => { router.replaceUrl({ url: 'pages/LoginPage' }); };
    if (!this.api.client.isAuthenticated()) { router.replaceUrl({ url: 'pages/LoginPage' }); return; }
    this.load();
  }
  aboutToDisappear(): void { this.generation++; }
  async load(more: boolean = false): Promise<void> {
    const generation = ++this.generation;
    const page = more ? this.page + 1 : 1;
    this.busy = true; this.error = '';
    try {
      if (this.tab === 0) {
        let places: Place[] = []; let hasMore = false; let reason = '';
        if (this.favoritesOnly) {
          const response = await this.api.favorites(page); places = response.data === null ? [] : response.data;
          hasMore = (response.meta as PageMeta).has_more;
        }
        else if (!this.search && !this.kind && !more) {
          const recommendation = await this.api.recommendations(); places = recommendation.items; reason = recommendation.reason;
        } else {
          const response = await this.api.places('page=' + page + '&page_size=20' + (this.search ? '&q=' + encodeURIComponent(this.search) : '') + (this.kind ? '&kind=' + this.kind : ''));
          places = response.data === null ? [] : response.data;
          const meta = response.meta as PageMeta;
          hasMore = meta !== null && meta.has_more;
        }
        if (generation !== this.generation) { return; }
        this.places = more ? this.places.concat(places.filter((place: Place) => !this.places.some((item: Place) => item.id === place.id))) : places; this.page = page; this.hasMore = hasMore; this.reason = reason;
      } else if (this.tab === 1) {
        const response = await this.api.trips(page); if (generation !== this.generation) { return; }
        const trips = response.data === null ? [] : response.data;
        this.trips = more ? this.trips.concat(trips.filter((trip: TripSummary) => !this.trips.some((item: TripSummary) => item.id === trip.id))) : trips;
        this.page = page; this.hasMore = (response.meta as PageMeta).has_more;
      } else {
        const user = await this.api.me(); const tags = await this.api.tags();
        if (generation !== this.generation) { return; }
        this.nickname = user.nickname; this.signature = user.signature; this.selectedTags = user.preferences.tags; this.tags = tags; this.verified = user.email_verified; this.pace = user.preferences.pace;
      }
    } catch (error) { if (generation === this.generation) { this.error = publicError(error); } }
    finally { if (generation === this.generation) { this.busy = false; } }
  }
  async removeFavorite(id: string): Promise<void> {
    if (this.busy) { return; } const generation = ++this.generation; this.busy = true; this.error = '';
    try {
      await this.api.favorite(id, false);
      if (generation === this.generation) { await this.load(); }
    } catch (error) { if (generation === this.generation) { this.error = publicError(error); } }
    finally { if (generation === this.generation) { this.busy = false; } }
  }
  async accountAction(action: string): Promise<void> {
    if (this.busy) { return; } this.busy = true; this.error = ''; this.notice = '';
    try {
      if (action === 'profile') {
        await this.api.data<User>('/me', http.RequestMethod.PATCH, JSON.stringify({ nickname: this.nickname, signature: this.signature, preferences: { tags: this.selectedTags, pace: this.pace } })); this.notice = '资料已保存';
      } else if (action === 'verify') {
        await this.api.client.request<null>('/auth/email-verification/request', http.RequestMethod.POST); this.notice = '邮箱验证请求已受理';
      } else if (action === 'confirmVerify') {
        await this.api.client.request<null>('/auth/email-verification/confirm', http.RequestMethod.POST, JSON.stringify({ token: this.verifyToken })); this.verifyToken = ''; this.verified = true;
      } else if (action === 'password') {
        await this.api.client.request<null>('/me/password', http.RequestMethod.POST, JSON.stringify({ current_password: this.currentPassword, new_password: this.newPassword }));
        this.api.client.clear(); this.currentPassword = ''; this.newPassword = ''; await router.replaceUrl({ url: 'pages/LoginPage' });
      } else if (action === 'delete') {
        await this.api.client.request<null>('/me', http.RequestMethod.DELETE, JSON.stringify({ current_password: this.currentPassword }));
        this.api.client.clear(); this.currentPassword = ''; await router.replaceUrl({ url: 'pages/LoginPage' });
      } else {
        try { await this.api.client.request<null>('/auth/logout', http.RequestMethod.POST); }
        finally { this.api.client.clear(); this.currentPassword = ''; this.newPassword = ''; await router.replaceUrl({ url: 'pages/LoginPage' }); }
      }
    } catch (error) { this.error = publicError(error); }
    finally { this.busy = false; }
  }
  changeTab(index: number): void { this.tab = index; this.notice = ''; this.load(); }
  @Builder
  catalog() {
    Column({ space: 12 }) {
      SearchBar({ placeholder: '搜索景点、酒店、餐厅', onSearch: (text: string) => { this.search = text; this.load(); } })
      Row({ space: 8 }) {
        Button('推荐').onClick(() => { this.kind = ''; this.search = ''; this.favoritesOnly = false; this.load(); })
        Button('景点').onClick(() => { this.kind = 'attraction'; this.favoritesOnly = false; this.load(); })
        Button('酒店').onClick(() => { this.kind = 'hotel'; this.favoritesOnly = false; this.load(); })
        Button('餐厅').onClick(() => { this.kind = 'restaurant'; this.favoritesOnly = false; this.load(); })
      }
      Button('我的收藏').onClick(() => { this.favoritesOnly = true; this.load(); })
      if (this.reason) { Text(this.reason === 'collaborative' ? '根据行为推荐' : this.reason === 'fallback_preferences' ? '根据明确偏好推荐' : '基础推荐：行为不足').fontColor($r('app.color.text_secondary')) }
      ForEach(this.places, (place: Place) => {
        Column({ space: 6 }) {
          Text(place.name).fontSize(18)
          Text(place.city.name + ' · ' + priceText(place)).fontColor($r('app.color.text_secondary'))
          if (place.is_test) { Text('虚拟测试地点，不可据此出行').fontColor($r('app.color.status_error')) }
          if (this.favoritesOnly) { Button('取消收藏').enabled(!this.busy).onClick(() => this.removeFavorite(place.id)) }
          Button('查看详情').onClick(() => router.pushUrl({ url: 'pages/PlaceDetailPage', params: { id: place.id } }))
        }.width('100%').padding(12).backgroundColor($r('app.color.surface_neutral')).borderRadius(8)
      }, (place: Place) => place.id)
      if (this.hasMore) { Button('加载更多').enabled(!this.busy).onClick(() => this.load(true)) }
      LoadState({ loading: this.busy, error: this.error, empty: this.places.length === 0, onRetry: () => this.load() })
    }
  }
  @Builder
  tripList() {
    Column({ space: 12 }) {
      Button('新增行程 / AI规划任务').onClick(() => router.pushUrl({ url: 'pages/TripPlanningPage' }))
      ForEach(this.trips, (trip: TripSummary) => {
        Column({ space: 8 }) {
          Text(trip.title).fontSize(18)
          Text(trip.start_date + ' 至 ' + trip.end_date)
          Button('每日安排与编辑').onClick(() => router.pushUrl({ url: 'pages/TripDetailPage', params: { id: trip.id } }))
        }.width('100%').padding(12).backgroundColor($r('app.color.surface_neutral')).borderRadius(8)
      }, (trip: TripSummary) => trip.id)
      if (this.hasMore) { Button('加载更多行程').enabled(!this.busy).onClick(() => this.load(true)) }
      LoadState({ loading: this.busy, error: this.error, empty: this.trips.length === 0, onRetry: () => this.load() })
    }
  }
  @Builder
  profile() {
    Column({ space: 12 }) {
      TextInput({ placeholder: '昵称', text: this.nickname }).onChange((value: string) => this.nickname = value)
      TextInput({ placeholder: '个人签名', text: this.signature }).onChange((value: string) => this.signature = value)
      Text('偏好标签（可多选）')
      ForEach(this.tags, (tag: Tag) => {
        Button((this.selectedTags.includes(tag.id) ? '✓ ' : '') + tag.name).onClick(() => {
          this.selectedTags = this.selectedTags.includes(tag.id) ? this.selectedTags.filter((id: string) => id !== tag.id) : this.selectedTags.concat(tag.id);
        })
      }, (tag: Tag) => tag.id)
      Button('保存资料与偏好').enabled(!this.busy).onClick(() => this.accountAction('profile'))
      Text(this.verified ? '邮箱已验证' : '邮箱未验证')
      if (!this.verified) {
        Button('发送验证邮件').enabled(!this.busy).onClick(() => this.accountAction('verify'))
        TextInput({ placeholder: '邮件中的验证令牌', text: this.verifyToken }).onChange((value: string) => this.verifyToken = value)
        Button('确认邮箱验证').enabled(!this.busy).onClick(() => this.accountAction('confirmVerify'))
      }
      TextInput({ placeholder: '当前密码（改密或注销时填写）', text: this.currentPassword }).type(InputType.Password).onChange((value: string) => this.currentPassword = value)
      TextInput({ placeholder: '新密码：12–128字符', text: this.newPassword }).type(InputType.Password).onChange((value: string) => this.newPassword = value)
      Button('修改密码并重新登录').enabled(!this.busy).onClick(() => this.accountAction('password'))
      Button('退出登录').enabled(!this.busy).onClick(() => this.accountAction('logout'))
      if (this.confirmDelete) {
        Text('注销将清除个人资料、收藏、行程与会话，无法恢复。请填写当前密码后确认。').fontColor($r('app.color.status_error'))
        Button('确认永久注销账户').backgroundColor($r('app.color.status_error')).enabled(!this.busy && this.currentPassword.length > 0).onClick(() => this.accountAction('delete'))
        Button('取消注销').onClick(() => this.confirmDelete = false)
      } else { Button('注销账户').onClick(() => this.confirmDelete = true) }
      if (this.notice) { Text(this.notice) }
      LoadState({ loading: this.busy, error: this.error, onRetry: () => this.load() })
    }
  }
  build() {
    Column() {
      Row({ space: 12 }) {
        Text('一人有路').fontSize(24).fontColor($r('app.color.brand_primary')).layoutWeight(1)
        Button('AI伴游').onClick(() => router.pushUrl({ url: 'pages/AiAssistantPage' }))
        Button('刷新').enabled(!this.busy).onClick(() => this.load())
      }.padding(16)
      Scroll() {
        Column() {
          if (this.tab === 0) { this.catalog() } else if (this.tab === 1) { this.tripList() } else { this.profile() }
        }.width('100%').padding(16)
      }.layoutWeight(1)
      BottomNavigation({ currentIndex: $tab, onTabChange: (index: number) => this.changeTab(index) })
    }.width('100%').height('100%')
  }
}
