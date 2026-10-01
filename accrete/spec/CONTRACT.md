# External contract shared by every implementation

Every application in this project, whether built with the invention (accrete) or with the
conventional baseline stack, exposes exactly this externally observable behaviour.
Acceptance checks are written only against this contract and the application requirements;
they never depend on how an implementation is built.

## Packaging

An *application instance* is a directory. It contains `app_entry.py` defining
`create_app()`, which returns a WSGI application that serves the data stored in that
directory. Test harnesses copy the directory before each test, so tests may mutate state.

## Identity and time

* `X-User: <username>` identifies the caller. Missing or unknown username -> `401`.
* `X-Now: YYYY-MM-DDTHH:MM:SS` (UTC) is the current time for the request. All time-dependent
  behaviour uses it. Without it the real UTC time is used. Tests always send it.

## Records

JSON objects with an integer `id` plus fields. A reference to another record is serialised
as that record's integer `id`. Dates are `"YYYY-MM-DD"`, datetimes `"YYYY-MM-DDTHH:MM:SS"`,
money and other decimals are JSON numbers, empty values are `null`. Derived (computed)
values appear as ordinary fields. Fields the caller may not see are omitted.

## API

| Request | Success | Meaning |
|---|---|---|
| `GET /api/{collection}` | `200 {"items": [...]}` | records the caller may read, ascending `id`. Query parameters `?field=value` filter by exact match (references by id, booleans as `true`/`false`). |
| `GET /api/{collection}/{id}` | `200 record` | |
| `POST /api/{collection}` (JSON body) | `201 record` | create |
| `PATCH /api/{collection}/{id}` (JSON body) | `200 record` | partial update |
| `DELETE /api/{collection}/{id}` | `204` | delete |
| `POST /api/{collection}/{id}/{action}` (JSON body of parameters, may be `{}`) | `200 record` | run a named action on a record; the response is that record after the action |
| `GET /api/_outbox` | `200 {"items": [...]}` | messages the application emitted to integrations, ascending `id`; each item `{"id", "channel", "payload", "created_at"}`. Any authenticated user may read it. |

Errors return JSON `{"error": code, "message": text, "fields": {field: text}}`
(`fields` may be empty):

| Status | `error` | When |
|---|---|---|
| 400 | `validation` | invalid or missing input, constraint violated |
| 401 | `unauthenticated` | missing or unknown `X-User` |
| 403 | `forbidden` | the caller is not allowed to do this |
| 404 | `not_found` | unknown collection, record or action |
| 409 | `conflict` | the action/operation is not allowed in the record's current state |

When several apply, the first in this order wins: 401, 404 (unknown collection/action/record), 403, 409, 400.
A record the caller may not read is reported as 403 on direct access and is absent from lists.

## User interface (HTML)

| Request | Contents |
|---|---|
| `GET /ui/{collection}` | `200` HTML with a `<table>` containing one `<tr data-id="{id}">` per readable record |
| `GET /ui/{collection}/{id}` | `200` HTML with one element `data-field="{field}"` per visible field (its text is the value), and one `<form data-action="{action}">` per action the caller is allowed to run on the record right now |
| `GET /ui/{collection}/new` | `200` HTML with `<form data-create="{collection}">` containing one input/select/textarea `name="{field}"` per field the caller may set when creating; `403` if the caller may not create |

The same `X-User` / `X-Now` headers apply. Error statuses as for the API.
