import { Dialog as Alert } from '../platform/dialog';
import { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useApp } from '../app-context';
import { usePage, useResource } from '../hooks';
import type { Model } from '../api/types';
import { ApiError } from '../api/client';
import type { RootRoutes, ScreenProps } from '../navigation';
import {
  Button,
  Card,
  Chip,
  Empty,
  Field,
  Heading,
  Notice,
  Screen,
  errorMessage,
  useTheme,
} from '../ui';

function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [seconds, setSeconds] = useState(0);
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  useEffect(() => {
    if (seconds <= 0) return;
    const timer = setTimeout(() => setSeconds((v) => v - 1), 1000);
    return () => clearTimeout(timer);
  }, [seconds]);
  const run = async (task: () => Promise<void>) => {
    if (lock.current || seconds > 0) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (e) {
      if (e instanceof ApiError && e.kind === 'cancelled') return;
      if (mounted.current) {
        setError(e);
        if (e instanceof ApiError && e.retryAfter) setSeconds(e.retryAfter);
      }
    } finally {
      lock.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  return { busy, error, seconds, run };
}
function Feedback({ error, seconds }: { error: unknown; seconds: number }) {
  return error ? (
    <Notice tone="error">
      {errorMessage(error)}
      {seconds > 0 ? `（${seconds} 秒后可重试）` : ''}
    </Notice>
  ) : null;
}
export function LoginScreen({ navigation }: ScreenProps<'Login'>) {
  const { session } = useApp();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const submit = useSubmit();
  const c = useTheme();
  return (
    <Screen>
      <Heading title="欢迎回来" subtitle="登录后，收藏与每日安排都会为你保留。" />
      <View style={{ paddingVertical: 12 }}>
        <Text style={{ fontSize: 40, color: c.primary }}>一路，慢慢走。</Text>
      </View>
      <Field
        label="用户名或邮箱"
        value={identifier}
        onChangeText={setIdentifier}
        autoComplete="username"
      />
      <Field
        label="密码"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="current-password"
      />
      <Feedback {...submit} />
      <Button
        label="登录"
        busy={submit.busy}
        disabled={!identifier.trim() || !password || submit.seconds > 0}
        onPress={() =>
          void submit.run(async () => {
            await session.signIn(identifier.trim(), password);
            setPassword('');
            navigation.goBack();
          })
        }
      />
      <Button secondary label="还没有账户？注册" onPress={() => navigation.navigate('Register')} />
      <Notice>用户名或邮箱与密码登录。邮箱找回服务本期尚未接入。</Notice>
    </Screen>
  );
}
export function RegisterScreen({ navigation }: ScreenProps<'Register'>) {
  const { api } = useApp();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [done, setDone] = useState(false);
  const submit = useSubmit();
  return (
    <Screen>
      <Heading title="开启一人旅程" subtitle="先注册账户，再登录保存你的安排。" />
      {done ? (
        <Empty
          title="注册成功"
          description="邮箱尚未验证，请使用刚才的用户名或邮箱登录。"
          action={<Button label="返回登录" onPress={() => navigation.goBack()} />}
        />
      ) : (
        <>
          <Field
            label="用户名（3—50位小写字母、数字或下划线）"
            value={username}
            onChangeText={setUsername}
          />
          <Field
            label="邮箱"
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoComplete="email"
          />
          <Field
            label="密码（12—128位，按服务校验）"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="new-password"
          />
          <Feedback {...submit} />
          <Button
            label="创建账户"
            busy={submit.busy}
            disabled={
              !/^[a-z0-9_]{3,50}$/.test(username) ||
              !email.includes('@') ||
              password.length < 12 ||
              submit.seconds > 0
            }
            onPress={() =>
              void submit.run(async () => {
                await api.send('POST', '/auth/register', 'UserResponse', {
                  username,
                  email: email.trim(),
                  password,
                });
                setPassword('');
                setDone(true);
              })
            }
          />
        </>
      )}
    </Screen>
  );
}
export function MeScreen() {
  const { state, session, invalidate } = useApp();
  const nav = useNavigation<NativeStackNavigationProp<RootRoutes>>();
  const c = useTheme();
  const submit = useSubmit();
  return (
    <Screen>
      <Heading title="我的" subtitle="把旅途安排好，也为自己留一点余地。" />
      {state.user ? (
        <>
          <Card>
            <View
              style={{
                width: 64,
                height: 64,
                borderRadius: 32,
                backgroundColor: c.tint,
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ color: c.primary, fontSize: 28 }}>路</Text>
            </View>
            <Text style={{ color: c.text, fontSize: 22, fontWeight: '600' }}>
              {state.user.nickname || state.user.username}
            </Text>
            <Text style={{ color: c.muted }}>{state.user.signature || '下一站，由自己决定。'}</Text>
            <Text style={{ color: c.muted }}>
              {state.user.email} · {state.user.email_verified ? '邮箱已验证' : '邮箱未验证'}
            </Text>
          </Card>
          <Button secondary label="编辑资料与偏好" onPress={() => nav.navigate('Profile')} />
          <Button secondary label="我的收藏" onPress={() => nav.navigate('Favorites')} />
          <Button secondary label="账户与隐私" onPress={() => nav.navigate('Account')} />
          <Feedback {...submit} />
          <Button
            secondary
            label="退出当前账户"
            busy={submit.busy}
            onPress={() =>
              void submit.run(async () => {
                try {
                  await session.logout();
                } finally {
                  invalidate();
                }
              })
            }
          />
        </>
      ) : (
        <Empty
          title="旅程，从这里开始"
          description="不登录也可以探索地点；登录后保存收藏和行程。"
          action={<Button label="登录 / 注册" onPress={() => nav.navigate('Login')} />}
        />
      )}
    </Screen>
  );
}
export function ProfileScreen(props: ScreenProps<'Profile'>) {
  const { state } = useApp();
  return <ProfileEditor key={state.epoch} {...props} />;
}
function ProfileEditor({ navigation }: ScreenProps<'Profile'>) {
  const c = useTheme();
  const { state, session, api, invalidate, revision } = useApp();
  const [nickname, setNickname] = useState(state.user?.nickname ?? '');
  const [signature, setSignature] = useState(state.user?.signature ?? '');
  const [tags, setTags] = useState<string[]>(state.user?.preferences.tags ?? []);
  const [pace, setPace] = useState<Model<'Preferences'>['pace']>(
    state.user?.preferences.pace ?? 'normal',
  );
  const submit = useSubmit();
  const choices = usePage<Model<'NamedEntry'>>('profile-tags:' + revision, (page, signal) =>
    api.get('/tags', 'NamedEntryPageResponse', { page }, { signal }),
  );
  if (!state.user)
    return (
      <Screen>
        <Empty
          title="请先登录"
          action={<Button label="登录" onPress={() => navigation.navigate('Login')} />}
        />
      </Screen>
    );
  return (
    <Screen>
      <Heading title="资料与偏好" />
      <Field label="昵称" value={nickname} onChangeText={setNickname} maxLength={50} />
      <Field label="签名" value={signature} onChangeText={setSignature} multiline maxLength={200} />
      <Card>
        <Text style={{ color: c.text }}>旅行节奏</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {(['relaxed', 'normal', 'fast'] as const).map((v) => (
            <Chip
              key={v}
              label={{ relaxed: '慢慢逛', normal: '适中', fast: '紧凑' }[v]}
              selected={pace === v}
              onPress={() => setPace(v)}
            />
          ))}
        </View>
      </Card>
      <Card>
        <Text style={{ color: c.text }}>偏好标签（最多20个）</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {choices.items.map((t) => (
            <Chip
              key={t.id}
              label={t.name}
              selected={tags.includes(t.id)}
              onPress={() =>
                setTags((old) =>
                  old.includes(t.id)
                    ? old.filter((id) => id !== t.id)
                    : old.length < 20
                      ? [...old, t.id]
                      : old,
                )
              }
            />
          ))}
        </View>
        {choices.error ? <Notice tone="error">{errorMessage(choices.error)}</Notice> : null}
        {choices.hasMore ? <Button secondary label="更多标签" onPress={choices.loadMore} /> : null}
      </Card>
      <Feedback {...submit} />
      <Button
        label="保存资料"
        busy={submit.busy}
        disabled={submit.seconds > 0}
        onPress={() =>
          void submit.run(async () => {
            const user = await api.send(
              'PATCH',
              '/me',
              'UserResponse',
              { nickname, signature, preferences: { tags, pace } },
              { auth: true },
            );
            session.replaceUser(user.data);
            invalidate();
            navigation.goBack();
          })
        }
      />
    </Screen>
  );
}
export function AccountScreen(props: ScreenProps<'Account'>) {
  const { state } = useApp();
  return <AccountEditor key={state.epoch} {...props} />;
}
function AccountEditor({ navigation }: ScreenProps<'Account'>) {
  const { state, api, session, invalidate } = useApp();
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [deleting, setDeleting] = useState(false);
  const submit = useSubmit();
  const profile = useResource(
    'account',
    (signal) => api.get('/me', 'UserResponse', undefined, { auth: true, signal }),
    !!state.user,
  );
  if (!state.user)
    return (
      <Screen>
        <Empty
          title="请先登录"
          action={<Button label="登录" onPress={() => navigation.navigate('Login')} />}
        />
      </Screen>
    );
  const remove = () => {
    if (!current) return;
    Alert.alert(
      '永久注销账户',
      '将删除本人资料、收藏、行程与会话等私有内容，无法撤销。公共地点资料不受影响。',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确认注销',
          style: 'destructive',
          onPress: () =>
            void submit.run(async () => {
              const body: Model<'AccountDelete'> = { current_password: current };
              await api.send('DELETE', '/me', null, body, { auth: true });
              await session.logout(true).catch(() => {});
              invalidate();
              navigation.goBack();
            }),
        },
      ],
    );
  };
  return (
    <Screen>
      <Heading title="账户与隐私" />
      <Notice>
        邮箱状态：{(profile.data?.data ?? state.user).email_verified ? '已验证' : '未验证'}
        。邮箱验证与找回服务尚未接入。头像使用内置图形，无需相册或定位权限。
      </Notice>
      <Field label="当前密码" value={current} onChangeText={setCurrent} secureTextEntry />
      <Field label="新密码" value={password} onChangeText={setPassword} secureTextEntry />
      <Feedback {...submit} />
      <Button
        label="修改密码并重新登录"
        busy={submit.busy}
        disabled={!current || password.length < 12 || submit.seconds > 0}
        onPress={() =>
          void submit.run(async () => {
            await api.send(
              'POST',
              '/me/password',
              null,
              { current_password: current, new_password: password },
              { auth: true },
            );
            await session.logout(true).catch(() => {});
            invalidate();
            navigation.replace('Login');
          })
        }
      />
      <Button
        danger
        label={deleting ? '取消注销' : '注销账户…'}
        onPress={() => setDeleting((v) => !v)}
      />
      {deleting ? (
        <Card>
          <Notice tone="warning">请确认你已了解删除范围。输入当前密码后再次确认注销。</Notice>
          <Button
            danger
            label="永久删除我的账户"
            disabled={!current || submit.seconds > 0}
            busy={submit.busy}
            onPress={remove}
          />
        </Card>
      ) : null}
    </Screen>
  );
}
