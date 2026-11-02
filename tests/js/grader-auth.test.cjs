const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function browser(tokens, fetch) {
  const storage = new Map([
    ['grader.auth', JSON.stringify(tokens)], ['grader.device_id', 'browser-test'],
  ]);
  const context = {
    window: {}, navigator: {}, document: {}, fetch,
    localStorage: {
      getItem: key => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key),
    },
  };
  vm.runInNewContext(readFileSync(path.join(__dirname, '../../static/js/grader-auth.js'), 'utf8'), context);
  return context.window.GraderAuth;
}

test('concurrent expired-token requests share one refresh and use the new token', async () => {
  let calls = 0;
  const auth = browser({access_token: 'expired', refresh_token: 'refresh', expires_at: Date.now() - 1},
    async (url, options) => {
      calls++;
      assert.equal(url, '/api/mobile/v1/auth/refresh');
      assert.equal(JSON.parse(options.body).device_id, 'browser-test');
      return {ok: true, json: async () => ({access_token: 'fresh', refresh_token: 'rotated', expires_in: 900})};
    });
  await Promise.all([auth.ensureFresh(), auth.ensureFresh()]);
  assert.equal(calls, 1);
  assert.equal(auth.headers().Authorization, 'Bearer fresh');
  assert.equal(auth.read().refresh_token, 'rotated');
  await auth.ensureFresh();
  assert.equal(calls, 1);
});

test('cookie-only workbench does not attempt mobile refresh', async () => {
  const auth = browser(null, async () => assert.fail('unexpected refresh'));
  await auth.ensureFresh();
  assert.equal(auth.headers().Authorization, undefined);
});

test('failed refresh propagates and does not replace tokens with invalid data', async () => {
  const auth = browser({access_token: 'expired', refresh_token: 'refresh', expires_at: 1},
    async () => ({ok: false, status: 503, json: async () => ({message: 'Unavailable'})}));
  await assert.rejects(auth.ensureFresh(), /Unavailable/);
  assert.equal(auth.read().refresh_token, 'refresh');
});

test('revoked refresh credentials clear bearer credentials and require sign-in', async () => {
  const auth = browser({access_token: 'expired', refresh_token: 'revoked', expires_at: 1},
    async () => ({ok: false, status: 401, json: async () => ({error: 'invalid_refresh_token'})}));
  await assert.rejects(auth.ensureFresh(), error => error.status === 401);
  assert.equal(auth.isSignedIn(), false);
  assert.equal(auth.headers().Authorization, undefined);
});
