import { createContext, useContext } from 'react';
import type { PropsWithChildren, ReactNode } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useColorScheme,
  View,
} from 'react-native';
import type { TextInputProps } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { Model } from './api/types';
import { ApiError } from './api/client';
import { moneyText } from './utils';
const light = {
  bg: '#F7F8F5',
  card: '#FFFFFF',
  text: '#1F2A25',
  muted: '#5E6B63',
  primary: '#246B5A',
  onPrimary: '#FFFFFF',
  tint: '#E8F0EC',
  border: '#DCE4DE',
  warning: '#8A520E',
  danger: '#B42318',
  accent: '#C49A58',
};
const dark = {
  bg: '#111A16',
  card: '#1B2721',
  text: '#F1F5F1',
  muted: '#ACB9AF',
  primary: '#7BC4A3',
  onPrimary: '#10251B',
  tint: '#20392D',
  border: '#34483C',
  warning: '#E5BD76',
  danger: '#FFB4AB',
  accent: '#D8B67C',
};
export function useTheme() {
  return useColorScheme() === 'dark' ? dark : light;
}
export function Screen({
  children,
  scroll = true,
  refreshing = false,
  onRefresh,
}: PropsWithChildren<{ scroll?: boolean; refreshing?: boolean; onRefresh?: () => void }>) {
  const c = useTheme();
  return (
    <SafeAreaView
      edges={['left', 'right', 'bottom']}
      style={[styles.safe, { backgroundColor: c.bg }]}
    >
      <KeyboardAvoidingView
        style={styles.safe}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {scroll ? (
          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={styles.content}
            refreshControl={
              onRefresh ? (
                <RefreshControl
                  refreshing={refreshing}
                  onRefresh={onRefresh}
                  tintColor={c.primary}
                />
              ) : undefined
            }
          >
            {children}
          </ScrollView>
        ) : (
          <View style={[styles.content, styles.safe]}>{children}</View>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
const CardContext = createContext(false);
export function Heading({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  const c = useTheme();
  const compact = useContext(CardContext);
  return (
    <View style={styles.heading}>
      <View style={{ flex: 1, gap: 8 }}>
        <Text
          accessibilityRole="header"
          style={{
            color: c.text,
            fontSize: compact ? 18 : 22,
            fontWeight: '700',
            letterSpacing: -0.5,
          }}
        >
          {title}
        </Text>
        {subtitle ? (
          <Text style={{ color: c.muted, fontSize: 14, lineHeight: 21 }}>{subtitle}</Text>
        ) : null}
      </View>
      {action}
    </View>
  );
}
export function Card({ children }: PropsWithChildren) {
  const c = useTheme();
  return (
    <CardContext.Provider value={true}>
      <View style={[styles.card, { backgroundColor: c.card, borderColor: c.border }]}>
        {children}
      </View>
    </CardContext.Provider>
  );
}
export function Button({
  label,
  onPress,
  disabled = false,
  busy = false,
  secondary = false,
  danger = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  secondary?: boolean;
  danger?: boolean;
}) {
  const c = useTheme();
  const color = danger ? c.danger : secondary ? c.primary : c.onPrimary;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || busy, busy }}
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [
        styles.button,
        {
          backgroundColor: secondary || danger ? c.card : c.primary,
          borderColor: danger ? c.danger : c.primary,
          opacity: disabled || busy ? 0.5 : pressed ? 0.8 : 1,
        },
      ]}
    >
      {busy ? <ActivityIndicator color={color} /> : null}
      <Text style={{ color, fontSize: 16, fontWeight: '600', textAlign: 'center' }}>{label}</Text>
    </Pressable>
  );
}
export function Field({
  label,
  error,
  ...input
}: TextInputProps & { label: string; error?: string }) {
  const c = useTheme();
  return (
    <View style={{ gap: 8 }}>
      <Text style={{ color: c.text, fontSize: 14, fontWeight: '600' }}>{label}</Text>
      <TextInput
        {...input}
        accessibilityLabel={label}
        placeholderTextColor={c.muted}
        autoCapitalize={input.autoCapitalize ?? 'none'}
        style={[
          styles.input,
          {
            borderColor: error ? c.danger : c.border,
            backgroundColor: c.card,
            color: c.text,
            minHeight: input.multiline ? 96 : 48,
          },
        ]}
      />
      {error ? (
        <Text accessibilityLiveRegion="polite" style={{ color: c.danger, fontSize: 14 }}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}
export function Notice({
  children,
  tone = 'info',
}: PropsWithChildren<{ tone?: 'error' | 'warning' | 'info' }>) {
  const c = useTheme();
  return (
    <View style={[styles.notice, { backgroundColor: c.tint, borderColor: c.border }]}>
      <Text
        accessibilityLiveRegion="polite"
        style={{
          color: tone === 'error' ? c.danger : tone === 'warning' ? c.warning : c.muted,
          fontSize: 14,
          lineHeight: 22,
        }}
      >
        {children}
      </Text>
    </View>
  );
}
export function Empty({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  const c = useTheme();
  return (
    <View style={{ gap: 16, paddingVertical: 32 }}>
      <Text accessibilityRole="header" style={{ color: c.text, fontSize: 20, fontWeight: '600' }}>
        {title}
      </Text>
      {description ? (
        <Text style={{ color: c.muted, fontSize: 16, lineHeight: 24 }}>{description}</Text>
      ) : null}
      {action}
    </View>
  );
}
export function Chip({
  label,
  selected = false,
  onPress,
}: {
  label: string;
  selected?: boolean;
  onPress: () => void;
}) {
  const c = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.chip,
        {
          backgroundColor: selected ? c.tint : c.card,
          borderColor: selected ? c.primary : c.border,
        },
      ]}
    >
      <Text
        style={{
          color: selected ? c.primary : c.text,
          fontSize: 14,
          fontWeight: selected ? '600' : '400',
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}
export function PlaceRow({ place, onPress }: { place: Model<'Place'>; onPress: () => void }) {
  const c = useTheme();
  const label = { attraction: '景', hotel: '宿', restaurant: '食' }[place.kind];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={place.name}
      onPress={onPress}
      style={[styles.row, { backgroundColor: c.card, borderColor: c.border }]}
    >
      <View style={[styles.placeholder, { backgroundColor: c.tint }]}>
        <View
          style={{
            position: 'absolute',
            height: 60,
            width: 60,
            borderRadius: 30,
            borderWidth: 1,
            borderColor: c.primary,
            transform: [{ translateX: 22 }, { translateY: 24 }],
          }}
        />
        <Text style={{ color: c.primary, fontSize: 23, fontWeight: '500' }}>{label}</Text>
      </View>
      <View style={{ flex: 1, gap: 6 }}>
        <Text style={{ color: c.text, fontSize: 18, fontWeight: '600' }}>{place.name}</Text>
        <Text style={{ color: c.muted, fontSize: 14 }}>
          {place.city.name} ·{' '}
          {place.price
            ? `${moneyText(place.price.amount_minor)}/${{ entry: '次', night: '晚', person: '人' }[place.price.unit]}`
            : '价格暂无资料'}
        </Text>
        {place.status === 'inactive' ? <Text style={{ color: c.warning }}>资料已失效</Text> : null}
        {place.is_test ? <Text style={{ color: c.warning }}>测试数据 · 非真实地点</Text> : null}
      </View>
      <Text accessibilityElementsHidden style={{ color: c.muted, fontSize: 22 }}>
        ›
      </Text>
    </Pressable>
  );
}
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.kind === 'cancelled') return '';
    const extra = error.retryAfter ? `，请等待 ${error.retryAfter} 秒后重试` : '';
    const labels: Record<string, string> = {
      username: '用户名',
      identifier: '用户名/邮箱',
      email: '邮箱',
      password: '密码',
      current_password: '当前密码',
      new_password: '新密码',
      title: '标题',
      start_date: '开始日期',
      end_date: '结束日期',
      date: '日期',
      start_minute: '开始时间',
      end_minute: '结束时间',
      budget_minor: '预算',
      nickname: '昵称',
      signature: '签名',
      preferences: '偏好',
      note: '备注',
    };
    const fields = [
      ...new Set(error.details.map((d) => labels[d.path.split('.').pop() ?? '']).filter(Boolean)),
    ];
    return error.message + (fields.length ? '（请检查' + fields.join('、') + '）' : '') + extra;
  }
  return error instanceof Error ? error.message : '暂时无法完成，请重试';
}
const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: 20, gap: 16, flexGrow: 1 },
  heading: { flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 8 },
  card: { padding: 16, gap: 12, borderRadius: 16, borderWidth: 1 },
  button: {
    minHeight: 48,
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  input: { padding: 12, borderRadius: 12, borderWidth: 1, fontSize: 16 },
  notice: { padding: 14, borderRadius: 12, borderWidth: 1 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 24,
    borderWidth: 1,
    minHeight: 44,
    justifyContent: 'center',
  },
  row: {
    padding: 12,
    gap: 14,
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  placeholder: {
    height: 72,
    width: 64,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
});
