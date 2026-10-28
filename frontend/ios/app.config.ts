import type { ExpoConfig } from 'expo/config';
const production = process.env.EXPO_PUBLIC_APP_ENV === 'production';
if (production && !process.env.IOS_BUNDLE_IDENTIFIER)
  throw new Error('Production requires an approved IOS_BUNDLE_IDENTIFIER');
const config: ExpoConfig = {
  name: '一人有路',
  slug: 'yirenyoulu',
  version: '0.3.0',
  orientation: 'portrait',
  platforms: ['ios', 'web'],
  userInterfaceStyle: 'automatic',
  ios: {
    supportsTablet: false,
    bundleIdentifier: process.env.IOS_BUNDLE_IDENTIFIER ?? 'com.catchman1.yirenyoulu.dev',
    infoPlist: production
      ? {}
      : {
          NSAppTransportSecurity: { NSAllowsArbitraryLoads: true },
          NSLocalNetworkUsageDescription: '用于连接同一局域网内的开发后端服务。',
        },
  },
  plugins: ['expo-secure-store'],
};
export default config;
