/**
 * 应用常量配置类
 * 功能：统一管理应用中的常量配置
 */
export class AppConstants {
  static readonly API_BASE_URL: string = 'https://api.example.invalid/api/v1';
  static readonly API_TIMEOUT: number = 20000;

  // ==================== 颜色配置 ====================
  static readonly COLOR_PRIMARY: string = '#FF6B35';
  static readonly COLOR_BACKGROUND: string = '#F5F5F5';
  static readonly COLOR_TEXT_PRIMARY: string = '#333333';
  static readonly COLOR_TEXT_SECONDARY: string = '#666666';
  static readonly COLOR_TEXT_HINT: string = '#999999';
  static readonly COLOR_DIVIDER: string = '#F0F0F0';
  static readonly COLOR_WHITE: string = '#FFFFFF';
  
  // ==================== 尺寸配置 ====================
  static readonly BORDER_RADIUS_SMALL: number = 8;
  static readonly BORDER_RADIUS_MEDIUM: number = 12;
  static readonly BORDER_RADIUS_LARGE: number = 16;
  
  static readonly PADDING_SMALL: number = 8;
  static readonly PADDING_MEDIUM: number = 12;
  static readonly PADDING_LARGE: number = 16;
  
  // ==================== 页面配置 ====================
  static readonly PAGE_SIZE: number = 20;
  static readonly MAX_IMAGE_SIZE: number = 5 * 1024 * 1024; // 5MB
  
  // ==================== 缓存配置 ====================
  static readonly CACHE_EXPIRE_TIME: number = 3600000; // 1小时
  
  // ==================== 业务配置 ====================
  static readonly DEFAULT_AVATAR: string = '';
  static readonly DEFAULT_USER_LEVEL: string = 'Lv.1';
}
