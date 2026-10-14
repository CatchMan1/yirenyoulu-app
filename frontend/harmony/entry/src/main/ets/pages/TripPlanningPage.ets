import { router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { City, Job, PageMeta } from '../models/ApiModels';
import { TravelApi } from '../services/TravelApi';
import { messageId, publicError } from '../services/ApiClient';
import { LoadState } from '../components/LoadState';

@Entry
@Component
struct TripPlanningPage {
  @State cities: City[] = [];
  @State cityId: string = '';
  @State title: string = '';
  @State start: string = '';
  @State end: string = '';
  @State budget: string = '';
  @State preferences: string = '';
  @State jobs: Job[] = [];
  @State jobsPage: number = 1;
  @State jobsMore: boolean = false;
  @State busy: boolean = false;
  @State error: string = '';
  @State notice: string = '';
  private api: TravelApi = new TravelApi();
  private key: string = '';
  private submittedBody: string = '';
  private submittedMode: boolean = false;
  private timer: number = -1;
  private generation: number = 0;
  private polling: boolean = false;
  aboutToAppear(): void { this.load(); }
  aboutToDisappear(): void { this.generation++; if (this.timer !== -1) { clearInterval(this.timer); this.timer = -1; } }
  async load(more: boolean = false): Promise<void> {
    const generation = ++this.generation; const page = more ? this.jobsPage + 1 : 1; this.busy = true; this.error = '';
    try {
      const cities = await this.api.cities(); const response = await this.api.jobs(page);
      if (generation !== this.generation) { return; }
      this.cities = cities; const jobs = response.data === null ? [] : response.data;
      this.jobs = more ? this.jobs.concat(jobs.filter((job: Job) => !this.jobs.some((item: Job) => item.id === job.id))) : jobs;
      this.jobsPage = page; this.jobsMore = (response.meta as PageMeta).has_more;
      if (!this.cityId && cities.length > 0) { this.cityId = cities[0].id; }
      if (this.timer === -1) { this.timer = setInterval(() => this.poll(), 2000); }
    } catch (error) { if (generation === this.generation) { this.error = publicError(error); } }
    finally { if (generation === this.generation) { this.busy = false; } }
  }
  async poll(): Promise<void> {
    if (this.polling || !this.jobs.some((job: Job) => job.status === 'queued' || job.status === 'running')) { return; }
    const generation = this.generation; this.polling = true;
    try {
      const jobs: Job[] = [];
      for (let i = 0; i < this.jobs.length; i++) { const job = this.jobs[i]; jobs.push(job.status === 'queued' || job.status === 'running' ? await this.api.job(job.id) : job); }
      if (generation === this.generation) { this.jobs = jobs; }
    } catch (error) { if (generation === this.generation) { this.error = publicError(error); if (this.timer !== -1) { clearInterval(this.timer); this.timer = -1; } } }
    finally { this.polling = false; }
  }
  async submit(agent: boolean, retry: boolean = false): Promise<void> {
    if (this.busy) { return; } this.busy = true; this.error = '';
    try {
      if (!retry) {
        if (!this.cityId || !/^\d{4}-\d{2}-\d{2}$/.test(this.start) || !/^\d{4}-\d{2}-\d{2}$/.test(this.end)) { throw new Error('请选择城市并填写 YYYY-MM-DD 日期'); }
        const budget = this.budget === '' ? null : Math.round(Number(this.budget) * 100);
        if (budget !== null && (!Number.isFinite(budget) || budget < 0)) { throw new Error('预算格式不正确'); }
        this.submittedMode = agent; this.key = messageId();
        this.submittedBody = agent ? JSON.stringify({ city_id: this.cityId, start_date: this.start, end_date: this.end, budget_minor: budget, request_text: this.preferences }) :
          JSON.stringify({ title: this.title, city_id: this.cityId, start_date: this.start, end_date: this.end, budget_minor: budget });
      }
      if (this.submittedMode) {
        const job = await this.api.createJob(this.submittedBody, this.key);
        this.jobs = [job].concat(this.jobs.filter((item: Job) => item.id !== job.id));
        this.notice = '规划任务已受理，尚未创建成功。等待任务完成。';
      } else {
        const trip = await this.api.mutateTrip('/trips', http.RequestMethod.POST, this.submittedBody, this.key);
        await router.replaceUrl({ url: 'pages/TripDetailPage', params: { id: trip.id } });
      }
    } catch (error) { this.error = error instanceof Error ? error.message : '操作失败，请重试'; }
    finally { this.busy = false; }
  }
  async cancel(job: Job): Promise<void> {
    try { const updated = await this.api.job(job.id, true); this.jobs = this.jobs.map((item: Job) => item.id === job.id ? updated : item); }
    catch (error) { this.error = publicError(error); }
  }
  build() {
    Scroll() {
      Column({ space: 12 }) {
        Button('返回').onClick(() => router.back())
        Text('新增行程').fontSize(24).fontColor($r('app.color.brand_primary'))
        Text('目的地城市')
        ForEach(this.cities, (city: City) => {
          Button((this.cityId === city.id ? '✓ ' : '') + city.name).onClick(() => this.cityId = city.id)
        }, (city: City) => city.id)
        TextInput({ placeholder: '行程标题（手动创建必填）', text: this.title }).onChange((value: string) => this.title = value)
        TextInput({ placeholder: '开始日期 YYYY-MM-DD', text: this.start }).onChange((value: string) => this.start = value)
        TextInput({ placeholder: '结束日期 YYYY-MM-DD', text: this.end }).onChange((value: string) => this.end = value)
        TextInput({ placeholder: '预算（人民币元，可留空）', text: this.budget }).onChange((value: string) => this.budget = value)
        TextArea({ placeholder: '本次旅行要求与偏好', text: this.preferences }).onChange((value: string) => this.preferences = value)
        Button('创建手动行程').enabled(!this.busy).onClick(() => this.submit(false))
        Button('提交 AI 规划任务').enabled(!this.busy).onClick(() => this.submit(true))
        if (this.error && this.key) { Button('重试上一次提交').enabled(!this.busy).onClick(() => this.submit(this.submittedMode, true)) }
        if (this.notice) { Text(this.notice) }
        Text('任务与恢复').fontSize(20)
        ForEach(this.jobs, (job: Job) => {
          Column({ space: 8 }) {
            Text(job.status + ' · 服务模式：' + job.provider_mode)
            if (job.error_code) { Text('失败原因：' + job.error_code).fontColor($r('app.color.status_error')) }
            if (job.status === 'queued' || job.status === 'running') { Button('取消任务').onClick(() => this.cancel(job)) }
            if (job.status === 'succeeded' && job.trip_id !== null && !job.result_deleted) {
              Button('查看已保存行程').onClick(() => router.pushUrl({ url: 'pages/TripDetailPage', params: { id: job.trip_id } }))
            }
            if (job.result_deleted) { Text('结果行程已删除；该任务不会重复创建。') }
          }.width('100%').padding(12).backgroundColor($r('app.color.surface_neutral'))
        }, (job: Job) => job.id)
        if (this.jobsMore) { Button('加载更多任务').enabled(!this.busy).onClick(() => this.load(true)) }
        LoadState({ loading: this.busy, error: this.error, onRetry: () => this.load() })
      }.width('100%').padding(20)
    }.width('100%').height('100%')
  }
}
