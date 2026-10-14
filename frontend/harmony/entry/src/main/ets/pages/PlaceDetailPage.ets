import { router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { PlaceDetail, NavigationResult, RouteId } from '../models/ApiModels';
import { TravelApi } from '../services/TravelApi';
import { publicError, messageId } from '../services/ApiClient';
import { priceText, validId } from '../services/DataGuard';
import { LoadState } from '../components/LoadState';

@Entry
@Component
struct PlaceDetailPage {
  @State place: PlaceDetail | null = null;
  @State busy: boolean = false;
  @State error: string = '';
  @State notice: string = '';
  private id: string = '';
  private generation: number = 0;
  private api: TravelApi = new TravelApi();
  aboutToAppear(): void {
    const params = router.getParams() as RouteId;
    if (!params || !validId(params.id)) { this.error = '地点参数无效'; return; }
    this.id = params.id; this.load();
  }
  aboutToDisappear(): void { this.generation++; }
  async load(): Promise<void> {
    const generation = ++this.generation; this.busy = true; this.error = '';
    try {
      const place = await this.api.place(this.id);
      if (generation !== this.generation) { return; } this.place = place;
      // Only authenticated views are recorded. Events are marked test outside production.
      if (this.api.client.isAuthenticated()) {
        try { await this.api.client.request<null>('/behavior-events', http.RequestMethod.POST,
          JSON.stringify({ event_id: messageId(), place_id: this.id, type: 'view', occurred_at: new Date().toISOString() })); } catch (error) { /* Browsing remains available. */ }
      }
    } catch (error) { if (generation === this.generation) { this.error = publicError(error); } }
    finally { if (generation === this.generation) { this.busy = false; } }
  }
  async favorite(add: boolean): Promise<void> {
    if (this.busy) { return; } this.busy = true; this.error = '';
    try { await this.api.favorite(this.id, add); this.notice = add ? '已收藏' : '已取消收藏'; }
    catch (error) { this.error = publicError(error); } finally { this.busy = false; }
  }
  async navigation(): Promise<void> {
    this.error = ''; this.notice = '';
    try {
      const navigation = await this.api.data<NavigationResult>('/places/' + this.id + '/navigation?mode=walking');
      this.notice = navigation.status === 'unavailable' ? '地图暂不可用，请参考地址。原因：' + navigation.reason : '导航服务已返回路线；外部地图启动能力尚未验证。';
    } catch (error) { this.error = publicError(error); }
  }
  build() {
    Scroll() {
      Column({ space: 16 }) {
        Button('返回').onClick(() => router.back())
        if (this.place !== null) {
          Text(this.place.name).fontSize(26).fontColor($r('app.color.brand_primary'))
          if (this.place.is_test) { Text('虚拟测试地点，不代表真实资料').fontColor($r('app.color.status_error')) }
          Text(this.place.description === null ? '暂无介绍' : this.place.description)
          Text(this.place.city.name)
          Text(this.place.address === null ? '地址未知' : this.place.address)
          Text(priceText(this.place))
          Text(this.place.rating === null ? '评分未知' : '评分 ' + this.place.rating.value + ' / ' + this.place.rating.scale)
          Text(this.place.opening_hours === null ? '营业时间未知' : this.place.opening_hours.raw_text)
          Text('数据来源：' + this.place.provenance.source_name)
          Text(this.place.provenance.checked_at === null ? '更新时间未知' : '资料核对时间：' + this.place.provenance.checked_at)
          if (this.place.coordinates !== null) {
            Text('坐标：' + this.place.coordinates.longitude + ', ' + this.place.coordinates.latitude + '（' + this.place.coordinates.crs + '）')
          } else { Text('坐标缺失，地图无法定位') }
          Row({ space: 12 }) {
            Button('收藏').enabled(!this.busy).onClick(() => this.favorite(true))
            Button('取消收藏').enabled(!this.busy).onClick(() => this.favorite(false))
          }
          Button('地图与步行导航').enabled(!this.busy).onClick(() => this.navigation())
        }
        if (this.notice) { Text(this.notice) }
        LoadState({ loading: this.busy, error: this.error, empty: this.place === null, onRetry: () => this.load() })
      }.width('100%').padding(20)
    }.width('100%').height('100%')
  }
}
