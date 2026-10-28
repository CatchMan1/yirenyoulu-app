import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import net from 'node:net';
const root = fileURLToPath(new URL('../../../', import.meta.url));
const client = path.join(root, 'frontend/ios');
const python = path.join(
  root,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
for (const port of [18000, 8081]) {
  await new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once('error', () =>
      reject(new Error(`端口 ${port} 已被占用，请先停止旧预览；不会终止其他进程。`)),
    );
    probe.listen(port, '127.0.0.1', () => probe.close(resolve));
  });
}
const children = [];
let closing = false;
function stop(code = 0) {
  if (closing) return;
  closing = true;
  for (const child of children) child.kill('SIGTERM');
  process.exitCode = code;
}
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => stop());
const api = spawn(python, [path.join(root, 'scripts/preview_ios.py')], {
  cwd: root,
  stdio: 'inherit',
  env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
});
children.push(api);
api.on('error', () => {
  console.error('请先按 README 创建项目根目录 .venv 并安装后端开发依赖。');
  stop(1);
});
api.on('exit', (code) => {
  if (!closing) stop(code || 1);
});
let ready = false;
for (let i = 0; i < 60 && !closing; i++) {
  try {
    ready = (await fetch('http://127.0.0.1:18000/api/v1/health/live')).ok;
  } catch {
    /* The isolated API may still be starting. */
  }
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 250));
}
if (!ready) {
  console.error('预览 API 启动失败，请检查端口 18000。');
  stop(1);
} else if (!closing) {
  const expo = spawn(
    process.execPath,
    [
      path.join(client, 'node_modules/expo/bin/cli'),
      'start',
      '--web',
      '--localhost',
      '--port',
      '8081',
    ],
    {
      cwd: client,
      stdio: 'inherit',
      env: {
        ...process.env,
        EXPO_NO_TELEMETRY: '1',
        EXPO_PUBLIC_APP_ENV: 'test',
        EXPO_PUBLIC_API_URL: 'http://127.0.0.1:18000/api/v1',
      },
    },
  );
  children.push(expo);
  expo.on('error', () => stop(1));
  expo.on('exit', (code) => {
    if (!closing) stop(code || 0);
  });
}
