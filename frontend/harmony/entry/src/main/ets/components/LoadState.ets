@Component
export struct LoadState {
  loading: boolean = false;
  error: string = '';
  empty: boolean = false;
  onRetry: () => void = () => {};
  build() {
    Column({ space: 12 }) {
      if (this.loading) { LoadingProgress().width(32).height(32) }
      if (this.error) {
        Text(this.error).fontColor($r('app.color.status_error'))
        Button('重试').onClick(() => this.onRetry())
      } else if (!this.loading && this.empty) { Text('暂无数据').fontColor($r('app.color.text_secondary')) }
    }.width('100%').padding(12)
  }
}
