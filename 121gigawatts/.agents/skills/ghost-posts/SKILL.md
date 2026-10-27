---
name: ghost-posts
description: Previews and updates Ghost post content through the Admin API, including text, links, images, and iframe destinations. Use for content edits rather than theme or server changes.
---

# Ghost posts

Read `.secrets/ghost-admin.json` with nonempty `url` and `key` fields. Keep it
ignored and mode `0600`. Never print credentials. Keep credentials, private
snapshots, draft content and preview URLs out of Git. If credentials are missing or rejected, ask the
user to correct this private file. Use the [Admin API](https://docs.ghost.org/admin-api)
or its [JavaScript client](https://docs.ghost.org/admin-api/javascript).

## Prepare

- Fetch the target with
  `GET /ghost/api/admin/posts/slug/{slug}/?formats=lexical,html`.
  Confirm its identity and status; save the original response privately.
- Parse its `lexical` JSON string and edit only the intended nodes. For an iframe
  in an HTML card (`type: "html"`), change only the intended `src` in that card's
  `html`, preserving its other attributes and surrounding markup.
- Match replacements exactly; stop if the target is absent or ambiguous. If it
  is already correct, do not save. Preserve editor structure instead of
  round-tripping rendered HTML through `source=html`.

## Preview

- Create a temporary draft with the proposed content using
  `POST /ghost/api/admin/posts/`. Copy the writable fields that affect rendering:
  title, editor content, feature image/alt/caption, authors, tags, excerpt,
  template, visibility, post code injection, and publication date where present.
  Omit the original ID, UUID and slug; set `status: "draft"` and omit email options.
  Leave the original post untouched, including when it is already a draft.
- Use the saved draft's UUID to provide `<site-url>/p/<uuid>/`. Open it to check
  the proposed change. A published post's `/p/` URL redirects to its live page.
- Return that Ghost preview link and a short change summary. Wait for explicit
  approval before applying the change to the original post.

## Apply

- After approval, re-fetch the original and compare it with the saved snapshot.
  If concurrent edits change the proposal, update the preview and seek approval
  again; do not overwrite them with an old document.
- Update the original, not the preview copy, with
  `PUT /ghost/api/admin/posts/{id}/?save_revision=true`. Send only changed fields
  and the checked `updated_at`. For body edits, send
  `posts: [{lexical: JSON.stringify(editedDocument), updated_at: checked.updated_at}]`.
  Preserve unrelated metadata, status and publication date; omit email options.
- On a collision, re-fetch and reconcile before retrying. After an uncertain
  response, read the post to determine whether the edit already succeeded.

## Verify

Re-fetch and confirm the intended change and preserved metadata. Check the public
page for published posts, or the original post’s Ghost preview for drafts. Verify
the affected image, link or embed in a browser; an HTTP 200 alone does not verify
an interactive embed. After a successful update, remove only the temporary
preview draft created for this edit and report the result.

See Ghost's [post format](https://docs.ghost.org/admin-api/posts/overview) and
[update contract](https://docs.ghost.org/admin-api/posts/updating-a-post).
