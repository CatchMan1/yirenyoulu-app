import { router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { Trip, TripItem, Place, RouteId } from '../models/ApiModels';
import { TravelApi } from '../services/TravelApi';
import { publicError } from '../services/ApiClient';
import { validId, priceText } from '../services/DataGuard';
import { LoadState } from '../components/LoadState';

@Entry
@Component
struct TripDetailPage {
  @State trip: Trip | null = null;
  @State days: string[] = [];
  @State day: string = '';
  @State items: TripItem[] = [];
  @State places: Place[] = [];
  @State selectedPlace: string = '';
  @State editingItem: string = '';
  @State minutesStart: string = '600';
  @State minutesEnd: string = '660';
  @State note: string = '';
  @State title: string = '';
  @State start: string = '';
  @State end: string = '';
  @State budget: string = '';
  @State busy: boolean = false;
  @State error: string = '';
  @State notice: string = '';
  @State confirmDelete: boolean = false;
  private id: string = '';
  private api: TravelApi = new TravelApi();
  private generation: number = 0;
  aboutToAppear(): void {
    const params = router.getParams() as RouteId;
    if (!params || !validId(params.id)) { this.error = '行程参数无效'; return; }
    this.id = params.id; this.load();
  }
  aboutToDisappear(): void { this.generation++; }
  apply(trip: Trip): void {
    this.trip = trip; this.title = trip.title; this.start = trip.start_date; this.end = trip.end_date;
    this.budget = trip.budget_minor === null ? '' : (trip.budget_minor / 100).toFixed(2);
    const days: string[] = [];
    for (let time = Date.parse(trip.start_date + 'T00:00:00Z'); time <= Date.parse(trip.end_date + 'T00:00:00Z'); time += 86400000) {
      days.push(new Date(time).toISOString().slice(0,10));
    }
    this.days = days; if (!days.includes(this.day)) { this.day = days[0]; }
    this.showDay();
  }
  showDay(): void {
    this.items = this.trip === null ? [] : this.trip.items.filter((item: TripItem) => item.date === this.day)
      .sort((left: TripItem, right: TripItem) => (left.start_minute === null ? 1440 : left.start_minute) - (right.start_minute === null ? 1440 : right.start_minute));
  }
  async load(): Promise<void> {
    const generation = ++this.generation; this.busy = true; this.error = '';
    try {
      const trip = await this.api.trip(this.id);
      const response = await this.api.places('city_id=' + trip.city_id + '&page_size=50');
      if (generation !== this.generation) { return; }
      this.apply(trip); this.places = response.data === null ? [] : response.data;
    } catch (error) { if (generation === this.generation) { this.error = publicError(error); } }
    finally { if (generation === this.generation) { this.busy = false; } }
  }
  edit(item: TripItem): void {
    this.editingItem = item.id; this.selectedPlace = item.place_id; this.day = item.date; this.note = item.note;
    this.minutesStart = item.start_minute === null ? '' : item.start_minute.toString();
    this.minutesEnd = item.end_minute === null ? '' : item.end_minute.toString();
  }
  async saveItem(): Promise<void> {
    if (this.busy || this.trip === null) { return; } this.busy = true; this.error = '';
    try {
      const place = this.places.find((place: Place) => place.id === this.selectedPlace);
      if (!place) { throw new Error('请选择有效地点'); }
      const body = JSON.stringify({ version: this.trip.version, place_id: place.id, date: this.day,
        start_minute: place.kind === 'hotel' ? null : Number(this.minutesStart),
        end_minute: place.kind === 'hotel' ? null : Number(this.minutesEnd), note: this.note });
      const trip = await this.api.mutateTrip('/trips/' + this.id + '/items' + (this.editingItem ? '/' + this.editingItem : ''),
        this.editingItem ? http.RequestMethod.PATCH : http.RequestMethod.POST, body);
      this.apply(trip); this.editingItem = ''; this.note = ''; this.notice = '地点已保存';
    } catch (error) { this.error = error instanceof Error ? error.message : '保存失败'; }
    finally { this.busy = false; }
  }
  async removeItem(item: TripItem): Promise<void> {
    if (this.busy || this.trip === null) { return; } this.busy = true; this.error = '';
    try { this.apply(await this.api.mutateTrip('/trips/' + this.id + '/items/' + item.id + '?version=' + this.trip.version, http.RequestMethod.DELETE, '')); }
    catch (error) { this.error = publicError(error); } finally { this.busy = false; }
  }
  async saveTrip(): Promise<void> {
    if (this.busy || this.trip === null) { return; } this.busy = true; this.error = '';
    try {
      const budget = this.budget === '' ? null : Math.round(Number(this.budget) * 100);
      this.apply(await this.api.mutateTrip('/trips/' + this.id, http.RequestMethod.PATCH,
        JSON.stringify({ version: this.trip.version, title: this.title, start_date: this.start, end_date: this.end, budget_minor: budget })));
      this.notice = '行程已保存';
    } catch (error) { this.error = publicError(error); } finally { this.busy = false; }
  }
  async removeTrip(): Promise<void> {
    if (this.busy || this.trip === null) { return; } this.busy = true; this.error = '';
    try {
      await this.api.client.request<null>('/trips/' + this.id + '?version=' + this.trip.version, http.RequestMethod.DELETE);
      this.trip = null; await router.replaceUrl({ url: 'pages/MainPage' });
    } catch (error) { this.error = publicError(error); } finally { this.busy = false; }
  }
  build() {
    Scroll() {
      Column({ space: 12 }) {
        Button('返回').onClick(() => router.back())
        if (this.trip !== null) {
          Text(this.trip.title).fontSize(24).fontColor($r('app.color.brand_primary'))
          Text('版本 ' + this.trip.version + ' · ' + this.trip.start_date + ' 至 ' + this.trip.end_date)
          Text('已知费用 ¥' + (this.trip.cost_summary.known_cost_minor / 100).toFixed(2) + '；未知地点费用 ' + this.trip.cost_summary.unknown_item_count + '项')
          if (!this.trip.cost_summary.complete) { Text('费用不完整，交通等未知项目不按0元计算。').fontColor($r('app.color.status_error')) }
          ForEach(this.trip.warnings, warning => { Text(warning.message).fontColor($r('app.color.status_error')) }, warning => warning.code + (warning.place_id === null ? '' : warning.place_id))
          ForEach(this.days, (date: string) => { Button((this.day === date ? '✓ ' : '') + date).onClick(() => { this.day = date; this.showDay(); }) }, (date: string) => date)
          ForEach(this.items, (item: TripItem) => {
            Column({ space: 8 }) {
              Text(item.snapshot.name + (item.snapshot.kind === 'hotel' ? ' · 住宿一晚' : ' · ' + item.start_minute + '–' + item.end_minute + '分钟'))
              Text(item.note)
              if (item.current_status === 'inactive') { Text('基础地点已失效；此处保留保存时快照。').fontColor($r('app.color.status_error')) }
              Row({ space: 8 }) { Button('编辑地点').enabled(!this.busy).onClick(() => this.edit(item)); Button('移除').enabled(!this.busy).onClick(() => this.removeItem(item)) }
            }.width('100%').padding(12).backgroundColor($r('app.color.surface_neutral'))
          }, (item: TripItem) => item.id)
          if (this.items.length === 0) { Text('当天暂无安排') }
          Text(this.editingItem ? '编辑地点' : '添加地点到 ' + this.day).fontSize(20)
          ForEach(this.places, (place: Place) => {
            Button((this.selectedPlace === place.id ? '✓ ' : '') + place.name + ' · ' + priceText(place)).onClick(() => this.selectedPlace = place.id)
          }, (place: Place) => place.id)
          TextInput({ placeholder: '开始分钟（0–1439；住宿留空）', text: this.minutesStart }).onChange((value: string) => this.minutesStart = value)
          TextInput({ placeholder: '结束分钟（1–1440；住宿留空）', text: this.minutesEnd }).onChange((value: string) => this.minutesEnd = value)
          TextInput({ placeholder: '地点备注', text: this.note }).onChange((value: string) => this.note = value)
          Button('保存地点').enabled(!this.busy).onClick(() => this.saveItem())
          if (this.editingItem) { Button('取消地点编辑').onClick(() => { this.editingItem = ''; this.note = ''; }) }
          Text('编辑行程').fontSize(20)
          TextInput({ text: this.title }).onChange((value: string) => this.title = value)
          TextInput({ placeholder: '开始日期 YYYY-MM-DD', text: this.start }).onChange((value: string) => this.start = value)
          TextInput({ placeholder: '结束日期 YYYY-MM-DD', text: this.end }).onChange((value: string) => this.end = value)
          TextInput({ placeholder: '预算（人民币元）', text: this.budget }).onChange((value: string) => this.budget = value)
          Button('保存行程').enabled(!this.busy).onClick(() => this.saveTrip())
          Button('绑定行程的 AI 伴游').onClick(() => router.pushUrl({ url: 'pages/AiAssistantPage', params: { tripId: this.id } }))
          if (this.confirmDelete) {
            Button('确认删除此行程').backgroundColor($r('app.color.status_error')).enabled(!this.busy).onClick(() => this.removeTrip())
            Button('取消删除').onClick(() => this.confirmDelete = false)
          } else { Button('删除行程').onClick(() => this.confirmDelete = true) }
        }
        if (this.notice) { Text(this.notice) }
        LoadState({ loading: this.busy, error: this.error, onRetry: () => this.load() })
      }.width('100%').padding(20)
    }.width('100%').height('100%')
  }
}
