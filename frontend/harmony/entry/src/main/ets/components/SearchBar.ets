/**
 * 搜索栏组件
 * 功能：搜索输入、清除、搜索回调
 */
@Component
export struct SearchBar {
  @State inputText: string = '';
  placeholder: string = '搜索';
  onSearch?: (text: string) => void;

  build() {
    Row() {
      Image($r('sys.symbol.magnifyingglass'))
        .width(20)
        .height(20)
        .fillColor('#999999')
        .margin({ left: 12, right: 8 })
      
      TextInput({ placeholder: this.placeholder, text: this.inputText })
        .layoutWeight(1)
        .height(40)
        .backgroundColor(Color.Transparent)
        .placeholderColor('#CCCCCC')
        .fontSize(14)
        .onChange((value: string) => {
          this.inputText = value;
        })
        .onSubmit(() => {
          if (this.onSearch) {
            this.onSearch(this.inputText);
          }
        })
      
      if (this.inputText.length > 0) {
        Image($r('sys.symbol.xmark_circle_fill'))
          .width(16)
          .height(16)
          .fillColor('#CCCCCC')
          .margin({ right: 12 })
          .onClick(() => {
            this.inputText = '';
          })
      }
    }
    .width('100%')
    .height(40)
    .backgroundColor($r('app.color.surface_neutral'))
    .borderRadius(20)
  }
}
