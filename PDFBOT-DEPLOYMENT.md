# PDF-BOT unified Render deployment

This repository is the complete deployment for the PDF bot. It runs the Telegram Local Bot API server, the local PDF classifier worker, and the compiled webhook application in one new Render Web Service. The existing shared Render Bot API service is not modified.

## Public routing

| Public path | Component | Purpose |
|---|---|---|
| `/bot<TOKEN>/<method>` | Telegram Local Bot API | Telegram API methods such as `getMe`, `getFile`, `copyMessage`, and webhook registration. |
| `/file/bot<TOKEN>/<path>` | Telegram Local Bot API file handler | Local Bot API file access. |
| `/pdfbot/health` | PDF classifier worker | Worker health check. |
| `/pdfbot/classify` | PDF classifier worker | Asynchronous local-file classification endpoint. |
| `/api/webhook` | Node webhook application | Telegram webhook endpoint. |
| `/api/worker-callback` | Node webhook application | Authenticated worker progress and completion callback. |
| `/health` | Node webhook application | Unified application health check. |

## Render environment variables

| Variable | Required | Value |
|---|---:|---|
| `PDFBOT_WORKER_ENABLED` | Yes | `true` |
| `TELEGRAM_API_ID` | Yes | Telegram API ID used by the Local Bot API server. |
| `TELEGRAM_API_HASH` | Yes | Telegram API hash used by the Local Bot API server. |
| `TELEGRAM_LOCAL` | Yes | `true` |
| `TELEGRAM_WORK_DIR` | Yes | `/var/lib/telegram-bot-api` |
| `TELEGRAM_TEMP_DIR` | Yes | `/tmp/telegram-bot-api` |
| `TELEGRAM_BOT_TOKEN` | Yes | The bot token used by the webhook application. |
| `TELEGRAM_CHANNEL_ID` | Yes | Destination channel ID. |
| `TELEGRAM_CHANNEL_USERNAME` | Recommended | Public channel username without `@`; leave empty for private channels. |
| `TELEGRAM_WEBHOOK_SECRET` | Recommended | Secret used to authenticate Telegram webhook requests. |
| `TELEGRAM_API_BASE` | Yes | `https://YOUR-RENDER-SERVICE.onrender.com/bot` |
| `TELEGRAM_FILE_BASE_URL` | Yes | `https://YOUR-RENDER-SERVICE.onrender.com/file` |
| `PDFBOT_WORKER_URL` | Yes | `https://YOUR-RENDER-SERVICE.onrender.com` |
| `PDFBOT_WORKER_SECRET` | Yes | Long random secret used for Vercel-style application to worker requests. |
| `PDFBOT_CALLBACK_URL` | Yes | `https://YOUR-RENDER-SERVICE.onrender.com/api/worker-callback` |
| `PDFBOT_CALLBACK_SECRET` | Yes | Long random secret used for worker callbacks. |
| `PARADOX_GATEWAY_URL` | Yes if Paradox-DB is enabled | Normally `https://paradoxdb.onrender.com/v1`. |
| `PARADOX_API_KEY` | Yes if Paradox-DB is enabled | Paradox-DB API key. |
| `PARADOX_PASSPHRASE` | Yes if Paradox-DB is enabled | Paradox-DB encryption passphrase. |
| `PARADOX_PROJECT` | Recommended | `telegram-pdf-bot` |
| `PARADOX_DATABASE` | Recommended | `pdf-records` |
| `PORT` | No manual value | Render supplies this automatically. |
| `TELEGRAM_HTTP_PORT` | No | Leave unset; unified entrypoint defaults the Bot API to internal port `8081`. |
| `PDFBOT_WORKER_PORT` | No | Leave unset; defaults to internal port `8090`. |
| `PDFBOT_APP_PORT` | No | Leave unset; defaults to internal port `3000`. |

## Migration sequence

Create a new Render Web Service from this repository using the Dockerfile. Do not edit, redeploy, or repoint the existing shared Render service. After the new service is healthy, register the Telegram webhook against the new service:

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://YOUR-RENDER-SERVICE.onrender.com/api/webhook&secret_token=<TELEGRAM_WEBHOOK_SECRET>
```

Then verify `https://YOUR-RENDER-SERVICE.onrender.com/health`, `https://YOUR-RENDER-SERVICE.onrender.com/pdfbot/health`, and the Bot API `getMe` endpoint. Finally send a PDF to the bot and confirm that the bot reports progress before it forwards the PDF and records the metadata.
