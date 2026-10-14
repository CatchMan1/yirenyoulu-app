/**
 * 底部导航栏组件
 * 包含主页、行程管理、个人中心三个按钮
 */
@Component
export struct BottomNavigation {
  @Link currentIndex: number;
  onTabChange?: (index: number) => void;

  /**
   * 构建导航项
   */
  @Builder
  private buildNavItem(icon: string, label: string, index: number) {
    Column() {
      Text(icon)
        .fontSize(24)
        .margin({ bottom: 4 })

      Text(label)
        .fontSize(12)
        .fontColor(this.currentIndex === index ? $r('app.color.brand_primary') : '#999999')
        .fontWeight(this.currentIndex === index ? FontWeight.Medium : FontWeight.Normal)
    }
    .width('33.33%')
    .height('100%')
    .justifyContent(FlexAlign.Center)
    .onClick(() => {
      this.currentIndex = index;
      if (this.onTabChange) {
        this.onTabChange(index);
      }
    })
  }

  build() {
    Row() {
      // 主页
      this.buildNavItem('🏠', '主页', 0)

      // 行程管理
      this.buildNavItem('📅', '行程管理', 1)

      // 个人中心
      this.buildNavItem('👤', '个人中心', 2)
    }
    .width('100%')
    .height(60)
    .backgroundColor('#FFFFFF')
    .shadow({
      radius: 8,
      color: 'rgba(0, 0, 0, 0.08)',
      offsetY: -2
    })
  }
}
