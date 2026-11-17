import {test} from "node:test";
import assert from "node:assert/strict";
import {createHmac} from "node:crypto";
import {readSiteChange, purgePublicHtml} from "./webhook.mjs";
import worker from "./worker.mjs";

const secret = "public-test-fixture-secret-not-a-real-key";
const now = 1794900000000;
function request(body = '{"event":"site.changed"}', timestamp = now, key = secret) {
    const hash = createHmac("sha256", key).update(body + timestamp).digest("hex");
    return new Request("https://blog.example.org/.well-known/ghost-cache-purge", {
        method: "POST", headers: {"X-Ghost-Signature": `sha256=${hash}, t=${timestamp}`}, body
    });
}

test("accepts the exact Ghost signature and discards caller-selected targets", async () => {
    assert.deepEqual(await readSiteChange(request('{"event":"site.changed","tags":["other-app"]}'), secret, now), {event: "site.changed"});
});

test("rejects forged, expired, unsigned, malformed and oversized hooks", async () => {
    const unsigned = new Request("https://blog.example.org/", {method: "POST", body: '{}'});
    const cases = [
        [request(undefined, now, "wrong-key"), 401],
        [request(undefined, now - 300001), 401],
        [request(undefined, now + 300001), 401],
        [unsigned, 401],
        [request('{"event":"post.edited"}'), 400],
        [request('null'), 400],
        [request('broken JSON'), 400],
        [request('x'.repeat(16385)), 413]
    ];
    for (const [hook, status] of cases) {
        await assert.rejects(readSiteChange(hook, secret, now), error => error.status === status);
    }
});

test("requires an explicit webhook secret", async () => {
    await assert.rejects(readSiteChange(request(), undefined, now), error => error.status === 503);
});

const env = {CLOUDFLARE_ZONE_ID: "0".repeat(32), CLOUDFLARE_PURGE_TOKEN: "test-fixture"};
test("purges only the public HTML tag in the configured zone", async t => {
    t.mock.method(globalThis, "fetch", async (url, options) => {
        assert.equal(url, `https://api.cloudflare.com/client/v4/zones/${env.CLOUDFLARE_ZONE_ID}/purge_cache`);
        assert.equal(options.method, "POST");
        assert.equal(options.headers.Authorization, "Bearer test-fixture");
        assert.deepEqual(JSON.parse(options.body), {tags: ["ghost-public-html"]});
        return Response.json({success: true});
    });
    await purgePublicHtml(env);
});

test("does not report a failed purge as success", async t => {
    for (const [status, result] of [[429, {}], [503, {}], [200, {success: false}]]) {
        t.mock.method(globalThis, "fetch", async () => Response.json(result, {status}));
        await assert.rejects(purgePublicHtml(env));
        t.mock.restoreAll();
    }
});

test("validates the purge configuration before sending credentials", async t => {
    t.mock.method(globalThis, "fetch", () => { throw new Error("Must not fetch"); });
    await assert.rejects(purgePublicHtml({...env, CLOUDFLARE_ZONE_ID: "bad/zone"}), /not configured/);
});

const workerEnv = {...env, GHOST_WEBHOOK_SECRET: secret};
function liveRequest() {
    return request('{"event":"site.changed"}', Date.now());
}
test("acknowledges a webhook only after Cloudflare confirms its purge", async t => {
    t.mock.method(globalThis, "fetch", async () => Response.json({success: true}));
    const response = await worker.fetch(liveRequest(), workerEnv);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
});

test("failed purges return failure to Ghost and leave a log without secrets", async t => {
    t.mock.method(globalThis, "fetch", async () => Response.json({}, {status: 429}));
    const logs = [];
    t.mock.method(console, "error", message => logs.push(message));
    const response = await worker.fetch(liveRequest(), workerEnv);
    assert.equal(response.status, 503);
    assert.deepEqual(logs, ["ghost_public_html_purge_failed"]);
});

test("does not purge for unsigned hooks or unrelated paths and methods", async t => {
    t.mock.method(globalThis, "fetch", () => { throw new Error("Must not fetch"); });
    for (const [url, method, expected] of [
        ["https://blog.example.org/", "POST", 404],
        ["https://blog.example.org/.well-known/ghost-cache-purge", "GET", 405],
        ["https://blog.example.org/.well-known/ghost-cache-purge", "POST", 401]
    ]) {
        const response = await worker.fetch(new Request(url, {method}), workerEnv);
        assert.equal(response.status, expected);
    }
});

test("a purge timeout leaves failure evidence rather than a successful acknowledgement", async t => {
    t.mock.method(globalThis, "fetch", async () => { throw new DOMException("Timeout", "TimeoutError"); });
    const logs = [];
    t.mock.method(console, "error", message => logs.push(message));
    const response = await worker.fetch(liveRequest(), workerEnv);
    assert.equal(response.status, 503);
    assert.deepEqual(logs, ["ghost_public_html_purge_failed"]);
});
