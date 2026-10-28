import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
(async () => {
  const b = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL ?? 'chrome',
    headless: true,
  });
  const p = await b.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  p.on('pageerror', (e) => errors.push(e.message));
  p.on('dialog', (d) => d.accept());
  async function capture(name) {
    if (process.env.PREVIEW_ARTIFACTS) {
      await fs.mkdir(process.env.PREVIEW_ARTIFACTS, { recursive: true });
      await p.screenshot({
        path: path.join(process.env.PREVIEW_ARTIFACTS, name + '.png'),
        fullPage: true,
      });
    }
  }
  try {
    await p.goto('http://localhost:8081', { waitUntil: 'domcontentloaded' });
    await p.getByText(/测试环境/).waitFor();
    await p.getByText('【测试】虚拟城市', { exact: true }).click();
    await p.getByRole('button', { name: '浏览景点', exact: true }).click();
    await p.getByRole('button', { name: '【测试】虚拟景点1', exact: true }).click();
    await p.getByRole('button', { name: '登录后收藏', exact: true }).click();
    await p.getByRole('button', { name: '还没有账户？注册', exact: true }).click();
    const name = 'test_ios_' + Date.now();
    const password = 'TestOnly!Password12';
    await p.getByLabel('用户名（3—50位小写字母、数字或下划线）', { exact: true }).fill(name);
    await p.getByLabel('邮箱', { exact: true }).fill(name + '@example.com');
    await p.getByLabel('密码（12—128位，按服务校验）', { exact: true }).fill(password);
    await p.getByRole('button', { name: '创建账户', exact: true }).click();
    await p.getByRole('button', { name: '返回登录', exact: true }).click();
    await p.getByLabel('用户名或邮箱', { exact: true }).fill(name);
    await p.getByLabel('密码', { exact: true }).fill(password);
    await p.getByRole('button', { name: '登录', exact: true }).click();
    await p.getByRole('button', { name: '收藏地点', exact: true }).click();
    await p.getByRole('button', { name: '已收藏 · 取消收藏', exact: true }).waitFor();
    await capture('detail');
    await p.getByRole('button', { name: '加入行程', exact: true }).click();
    await p.getByRole('button', { name: '新建同城行程', exact: true }).click();
    await p.getByLabel('行程标题', { exact: true }).fill('TEST iOS 两日安排');
    await p.getByLabel('开始日期 YYYY-MM-DD', { exact: true }).fill('2027-01-01');
    await p.getByLabel('结束日期 YYYY-MM-DD', { exact: true }).fill('2027-01-02');
    let firstCreate = true;
    const keys = [];
    const created = [];
    await p.route('**/api/v1/trips', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      keys.push(route.request().headers()['idempotency-key']);
      if (firstCreate) {
        firstCreate = false;
        const response = await route.fetch();
        created.push((await response.json()).data.id);
        await route.abort();
      } else {
        await route.continue();
      }
    });
    await p.getByRole('button', { name: '创建空行程', exact: true }).click();
    await p.getByText('连接失败，请检查网络和服务地址', { exact: true }).waitFor();
    await p.getByRole('button', { name: '创建空行程', exact: true }).click();
    if (keys.length !== 2 || keys[0] !== keys[1])
      throw new Error('Creation retry did not preserve idempotency key');
    await p.getByRole('button', { name: '确认保存地点', exact: true }).waitFor();

    await p.getByRole('button', { name: '确认保存地点', exact: true }).click();
    await p.getByText('当晚住宿', { exact: true }).waitFor();

    await capture('trip');
    await p.route('**/api/v1/trips/*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue();
        return;
      }
      const response = await route.fetch();
      const json = await response.json();
      if (json.data?.items) {
        json.data.items = json.data.items.map((item) => ({
          ...item,
          current_status: 'inactive',
          snapshot: {
            ...item.snapshot,
            name: '地点资料暂不可用',
            price: null,
            coordinates: null,
            address: null,
          },
        }));
        await route.fulfill({ response, json });
      } else await route.fulfill({ response });
    });
    await p.getByRole('button', { name: '刷新行程资料', exact: true }).click();
    await p.getByText('地点资料暂不可用', { exact: true }).waitFor();
    await p.unroute('**/api/v1/trips/*');
    await p.getByRole('button', { name: '刷新行程资料', exact: true }).click();
    await p.getByText('【测试】虚拟景点1', { exact: true }).last().waitFor();
    console.log('PASS: same-version source redaction replaces old snapshot');

    await p.getByRole('button', { name: '编辑地点安排', exact: true }).first().click();
    await p.getByLabel('备注（可选）', { exact: true }).fill('TEST 编辑后备注');
    await p.getByRole('button', { name: '确认保存地点', exact: true }).click();
    await p.getByText('TEST 编辑后备注', { exact: true }).waitFor();
    await p.getByRole('button', { name: '编辑地点安排', exact: true }).first().click();
    await p.getByRole('button', { name: '删除这项安排', exact: true }).click();
    await p.getByRole('button', { name: '删除行程', exact: true }).waitFor();
    await p.getByRole('button', { name: '删除行程', exact: true }).click();
    await p.getByRole('tab', { name: '我的', exact: true }).click();
    await p.getByRole('button', { name: '我的收藏', exact: true }).click();
    await p.getByRole('button', { name: '取消收藏', exact: true }).click();
    await p.getByRole('button', { name: '去探索', exact: true }).waitFor();
    console.log(
      'PASS: lost response retry uses same key; item edit/delete, trip delete, favorite removal',
    );
    await p
      .getByLabel(/back|返回/i)
      .first()
      .click();
    await p.getByRole('button', { name: '编辑资料与偏好', exact: true }).click();
    await p.getByLabel('昵称', { exact: true }).fill('TEST 旅行者');
    await p.getByRole('button', { name: '保存资料', exact: true }).click();
    await p.getByText('TEST 旅行者', { exact: true }).waitFor();
    await p.getByRole('button', { name: '账户与隐私', exact: true }).click();
    await p.getByLabel('当前密码', { exact: true }).fill(password);
    const nextPassword = 'TestOnly!NextPassword34';
    await p.getByLabel('新密码', { exact: true }).fill(nextPassword);
    await p.getByRole('button', { name: '修改密码并重新登录', exact: true }).click();
    await p.getByLabel('用户名或邮箱', { exact: true }).fill(name);
    await p.getByLabel('密码', { exact: true }).fill(nextPassword);
    await p.getByRole('button', { name: '登录', exact: true }).click();
    await p.getByRole('button', { name: '账户与隐私', exact: true }).click();
    await p.getByLabel('当前密码', { exact: true }).fill(nextPassword);
    await p.getByRole('button', { name: '注销账户…', exact: true }).click();
    await p.getByRole('button', { name: '永久删除我的账户', exact: true }).click();
    await p.getByRole('button', { name: '登录 / 注册', exact: true }).waitFor();
    console.log('PASS: profile edit, password rotation and account deletion');
    if (errors.length) throw new Error(errors.join(';'));
    console.log('PASS: register/login/favorite/manual trip/item saved; no page errors');
  } catch (e) {
    console.log('FAIL', e.message);
    await capture('failed');
    process.exitCode = 1;
  } finally {
    await b.close();
  }
})();
