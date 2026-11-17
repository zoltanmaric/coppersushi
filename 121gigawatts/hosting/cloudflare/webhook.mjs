const encoder = new TextEncoder();
const MAX_BODY_BYTES = 16384;

export class WebhookError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}

// Ghost signs the exact body followed by a millisecond timestamp.
export async function readSiteChange(request, secret, now = Date.now()) {
    if (typeof secret !== "string" || secret.length < 32) {
        throw new WebhookError(503, "Webhook is not configured");
    }
    const match = /^sha256=([a-f0-9]{64}), t=(\d{13})$/.exec(request.headers.get("X-Ghost-Signature") || "");
    if (!match || Math.abs(now - Number(match[2])) > 300000) {
        throw new WebhookError(401, "Unauthorized");
    }
    if (!request.body) throw new WebhookError(400, "Missing body");
    const reader = request.body.getReader();
    const chunks = [];
    let size = 0;
    try {
        while (true) {
            const {value, done} = await reader.read();
            if (done) break;
            size += value.byteLength;
            if (size > MAX_BODY_BYTES) {
                await reader.cancel();
                throw new WebhookError(413, "Webhook body too large");
            }
            chunks.push(value);
        }
    } finally {
        reader.releaseLock();
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
    }
    const signed = new Uint8Array(size + match[2].length);
    signed.set(bytes);
    signed.set(encoder.encode(match[2]), size);
    const signature = Uint8Array.from(match[1].match(/../g), byte => Number.parseInt(byte, 16));
    const key = await crypto.subtle.importKey("raw", encoder.encode(secret), {name: "HMAC", hash: "SHA-256"}, false, ["verify"]);
    if (!await crypto.subtle.verify("HMAC", key, signature, signed)) {
        throw new WebhookError(401, "Unauthorized");
    }
    let payload;
    try {
        payload = JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(bytes));
    } catch {
        throw new WebhookError(400, "Invalid JSON");
    }
    if (payload === null || typeof payload !== "object" || Array.isArray(payload) || payload.event !== "site.changed") {
        throw new WebhookError(400, "Expected site.changed");
    }
    // No post content or caller-selected purge targets leave this boundary.
    return {event: "site.changed"};
}

export async function purgePublicHtml(env) {
    if (!/^[a-f0-9]{32}$/.test(env.CLOUDFLARE_ZONE_ID || "") || typeof env.CLOUDFLARE_PURGE_TOKEN !== "string" || !env.CLOUDFLARE_PURGE_TOKEN) {
        throw new Error("Purge service is not configured");
    }
    const response = await fetch(`https://api.cloudflare.com/client/v4/zones/${env.CLOUDFLARE_ZONE_ID}/purge_cache`, {
        method: "POST",
        headers: {"Authorization": `Bearer ${env.CLOUDFLARE_PURGE_TOKEN}`, "Content-Type": "application/json"},
        body: JSON.stringify({tags: ["ghost-public-html"]}),
        signal: AbortSignal.timeout(1500)
    });
    if (!response.ok) throw new Error(`Cloudflare purge failed (${response.status})`);
    const result = await response.json();
    if (result?.success !== true) throw new Error("Cloudflare did not confirm the purge");
}
