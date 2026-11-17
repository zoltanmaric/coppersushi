import {WebhookError, readSiteChange, purgePublicHtml} from "./webhook.mjs";

function reply(status, body) {
    return new Response(body, {status, headers: {"Cache-Control": "no-store"}});
}

export default {
    async fetch(request, env) {
        if (new URL(request.url).pathname !== "/.well-known/ghost-cache-purge") {
            return reply(404, "Not found");
        }
        if (request.method !== "POST") return reply(405, "POST required");
        try {
            await readSiteChange(request, env.GHOST_WEBHOOK_SECRET);
            await purgePublicHtml(env);
            return reply(200, "Public HTML purged");
        } catch (error) {
            if (error instanceof WebhookError && error.status < 500) {
                return reply(error.status, error.message);
            }
            // No credentials, signature, request body or article content in logs.
            console.error("ghost_public_html_purge_failed");
            return reply(503, "Purge failed; inspect Worker and Ghost webhook logs");
        }
    }
};
