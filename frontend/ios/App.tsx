import { Platform, Text, View } from 'react-native';
import { NavigationContainer, DarkTheme, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { AppProvider, appEnvironment, useApp } from './src/app-context';
import { useTheme } from './src/ui';
import type { RootRoutes } from './src/navigation';
import {
  ExploreScreen,
  CityPickerScreen,
  CatalogScreen,
  PlaceScreen,
  FavoritesScreen,
} from './src/features/catalog';
import {
  TripsScreen,
  TripScreen,
  TripFormScreen,
  ItemFormScreen,
  ChooseTripScreen,
} from './src/features/trips';
import {
  LoginScreen,
  RegisterScreen,
  MeScreen,
  ProfileScreen,
  AccountScreen,
} from './src/features/account';
const Stack = createNativeStackNavigator<RootRoutes>();
const Tabs = createBottomTabNavigator<{ Explore: undefined; Trips: undefined; Me: undefined }>();
function Main() {
  const c = useTheme();
  return (
    <Tabs.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: c.primary,
        tabBarInactiveTintColor: c.muted,
        tabBarStyle: { backgroundColor: c.card, borderTopColor: c.border },
        tabBarLabelStyle: { fontSize: 12 },
        tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 18 }}>○</Text>,
      }}
    >
      <Tabs.Screen
        name="Explore"
        component={ExploreScreen}
        options={{
          title: '探索',
          tabBarAccessibilityLabel: '探索',
          tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 22 }}>⌁</Text>,
        }}
      />
      <Tabs.Screen
        name="Trips"
        component={TripsScreen}
        options={{
          title: '行程',
          tabBarAccessibilityLabel: '行程',
          tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 20 }}>▤</Text>,
        }}
      />
      <Tabs.Screen
        name="Me"
        component={MeScreen}
        options={{
          title: '我的',
          tabBarAccessibilityLabel: '我的',
          tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 18 }}>◉</Text>,
        }}
      />
    </Tabs.Navigator>
  );
}
function Navigation() {
  const c = useTheme();
  const { state } = useApp();
  const theme = {
    ...(c.bg === '#111A16' ? DarkTheme : DefaultTheme),
    colors: {
      ...(c.bg === '#111A16' ? DarkTheme : DefaultTheme).colors,
      primary: c.primary,
      background: c.bg,
      card: c.card,
      text: c.text,
      border: c.border,
    },
  };
  return (
    <View
      style={{
        flex: 1,
        backgroundColor: c.bg,
        width: '100%',
        maxWidth: Platform.OS === 'web' ? 480 : undefined,
        alignSelf: 'center',
      }}
    >
      {appEnvironment !== 'production' ? (
        <View
          style={{
            paddingHorizontal: 20,
            paddingTop: Platform.OS === 'ios' ? 48 : 12,
            paddingBottom: 8,
            backgroundColor: c.tint,
          }}
        >
          <Text style={{ fontSize: 12, color: c.muted }}>
            {appEnvironment === 'test' ? '测试环境' : '开发环境'}
            {Platform.OS === 'web' ? ' · 浏览器预览，凭据仅本次会话有效' : ''}
            {state.status === 'bootstrapping' ? ' · 正在恢复登录' : ''}
          </Text>
        </View>
      ) : null}
      <>
        {state.notice ? (
          <Text accessibilityLiveRegion="polite" style={{ padding: 12, color: c.danger }}>
            {state.notice}
          </Text>
        ) : null}
        <NavigationContainer theme={theme}>
          <Stack.Navigator
            screenOptions={{
              headerBackTitle: '返回',
              headerShadowVisible: false,
              headerStyle: { backgroundColor: c.bg },
              headerTintColor: c.text,
              contentStyle: { backgroundColor: c.bg },
            }}
          >
            <Stack.Screen name="Main" component={Main} options={{ headerShown: false }} />
            <Stack.Screen
              name="CityPicker"
              component={CityPickerScreen}
              options={{ title: '选择城市' }}
            />
            <Stack.Screen
              name="Catalog"
              component={CatalogScreen}
              options={{ title: '发现地点' }}
            />
            <Stack.Screen name="Place" component={PlaceScreen} options={{ title: '地点详情' }} />
            <Stack.Screen
              name="Favorites"
              component={FavoritesScreen}
              options={{ title: '我的收藏' }}
            />
            <Stack.Screen name="Trip" component={TripScreen} options={{ title: '每日行程' }} />
            <Stack.Screen
              name="TripForm"
              component={TripFormScreen}
              options={{ title: '行程安排' }}
            />
            <Stack.Screen
              name="ItemForm"
              component={ItemFormScreen}
              options={{ title: '安排地点' }}
            />
            <Stack.Screen
              name="ChooseTrip"
              component={ChooseTripScreen}
              options={{ title: '选择行程' }}
            />
            <Stack.Screen name="Login" component={LoginScreen} options={{ title: '登录' }} />
            <Stack.Screen name="Register" component={RegisterScreen} options={{ title: '注册' }} />
            <Stack.Screen
              name="Profile"
              component={ProfileScreen}
              options={{ title: '编辑资料' }}
            />
            <Stack.Screen
              name="Account"
              component={AccountScreen}
              options={{ title: '账户与隐私' }}
            />
          </Stack.Navigator>
        </NavigationContainer>
      </>
      <StatusBar style={c.bg === '#111A16' ? 'light' : 'dark'} />
    </View>
  );
}
export default function App() {
  return (
    <SafeAreaProvider>
      <AppProvider>
        <Navigation />
      </AppProvider>
    </SafeAreaProvider>
  );
}
