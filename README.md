# Personal Shorts Auto-Uploader

This repo posts the next queued vertical video from Google Drive to both YouTube Shorts and Instagram Reels on a free GitHub Actions schedule.

It is built for one person, one Google Drive folder, one Google Sheet, one YouTube channel, and one Instagram Business or Creator account.

## What It Does

- Reads `.mp4` videos from one Google Drive folder.
- Reads captions and status from one Google Sheet.
- Posts the next due video every 2 days.
- Uploads to YouTube with the YouTube Data API.
- Publishes to Instagram Reels through the Instagram Graph API.
- Updates the Sheet so videos are not repeated.
- Sends Telegram notifications for success, failure, validation issues, empty queue, and low queue.

## Sheet Format

Create a Google Sheet with this exact header row:

```text
filename | caption | status | posted_at | platform_ids | title
```

`title` is optional but useful. If it is blank, the YouTube title is generated from the filename.

Example:

```text
filename,caption,status,posted_at,platform_ids,title
video-001.mp4,"Your caption here #reels",pending,,,"My Short Title"
```

Allowed statuses:

- `pending`: not posted anywhere yet.
- `posted_yt_only`: YouTube succeeded, Instagram still needs to run.
- `posted_ig_only`: Instagram succeeded, YouTube still needs to run.
- `posted`: both platforms succeeded.

## Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project.
3. Enable these APIs:
   - Google Drive API
   - Google Sheets API
   - YouTube Data API v3
4. Go to **APIs & Services > OAuth consent screen**.
5. Choose **External** unless you have a Workspace organization.
6. Fill in the required app name, support email, and developer contact fields.
7. Add yourself as a test user.
8. Go to **Credentials > Create Credentials > OAuth client ID**.
9. Choose **Desktop app**.
10. Copy the client ID and client secret.

Install dependencies locally and generate the refresh token:

```bash
pip install -r requirements.txt
python generate_tokens.py
```

The script opens a browser. Log in with the Google account that owns the Drive folder, Sheet, and YouTube channel. Copy the printed refresh token into your GitHub secret named `GOOGLE_REFRESH_TOKEN`.

The Google token must include Drive read access plus `drive.file`, because large Instagram videos are compressed, uploaded as temporary Drive files, made public, and deleted after publishing.

## Google Drive Setup

1. Create one Drive folder for your monthly video batch.
2. Put your vertical `.mp4` files there.
3. Copy the folder ID from the URL.
   - In `https://drive.google.com/drive/folders/abc123`, the folder ID is `abc123`.
4. Share the folder or each video as **Anyone with the link can view**.

Instagram needs a public URL to fetch the video. This code uses:

```text
https://drive.google.com/uc?export=download&id=FILE_ID
```

Drive can occasionally throttle very large files, so keep videos short and compressed.

## Instagram Compression

YouTube always receives the original downloaded video. Instagram uses the original Drive URL only when the original file is 60 MB or smaller.

If the original file is larger than 60 MB, the workflow:

1. Compresses a temporary MP4 locally with FFmpeg using H.264, AAC 128k audio, CRF 23, `medium` preset, and `+faststart`.
2. Uploads that compressed copy to the same Google Drive folder.
3. Makes the temporary Drive file public.
4. Sends the temporary Drive URL to Instagram.
5. Deletes the temporary Drive file and local compressed file in cleanup.

FFmpeg must be installed and available on `PATH` wherever the workflow runs.

## Instagram / Meta Setup

This project uses the Facebook Graph API Instagram Graph API Content Publishing flow.

1. Your Instagram account must be **Business** or **Creator**.
2. Connect that Instagram account to a Facebook Page you own.
3. Go to [Meta for Developers](https://developers.facebook.com/).
4. Create or open your Meta app.
5. Add the **Instagram Graph API** product.
6. Add yourself as an app role, tester, or admin if the app is not public/live for this use.
7. Generate a Page Access Token with Instagram publishing permissions.
8. Exchange it for a long-lived token.
9. Find your Instagram Business Account ID.

Save these as GitHub secrets:

```text
IG_ACCESS_TOKEN
IG_BUSINESS_ACCOUNT_ID
```

Long-lived Meta tokens normally expire after about 60 days. Before expiry, generate a fresh long-lived token and update `IG_ACCESS_TOKEN` in GitHub secrets.

### Instagram API Endpoints Used

The uploader uses the Facebook Graph API Instagram publishing endpoints:

```text
POST https://graph.facebook.com/v20.0/{ig-business-account-id}/media
GET  https://graph.facebook.com/v20.0/{ig-container-id}?fields=status_code,status
POST https://graph.facebook.com/v20.0/{ig-business-account-id}/media_publish
```

It sends `media_type=REELS`, `video_url`, `caption`, and `access_token` when creating the container.

### Instagram Graph API Notes

- Only Instagram professional accounts, meaning Business or Creator accounts, can publish this way.
- The video must be reachable by Meta from a public URL.
- Page Access Tokens expire and must be refreshed before expiry.
- The Instagram account must be connected to a Facebook Page.
- App mode, roles, and permission access still matter. If users outside your app roles need to use it, your app may need Meta review.

## Telegram Bot Setup

1. Open Telegram and message `@BotFather`.
2. Run `/newbot`.
3. Copy the bot token.
4. Send one message to your new bot.
5. Visit this URL in your browser, replacing `BOT_TOKEN`:

```text
https://api.telegram.org/botBOT_TOKEN/getUpdates
```

6. Find your `chat.id`.
7. Save both as GitHub secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

## GitHub Secrets Checklist

In your GitHub repo, go to **Settings > Secrets and variables > Actions > New repository secret**.

Add:

```text
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REFRESH_TOKEN
GOOGLE_DRIVE_FOLDER_ID
GOOGLE_SHEET_ID
IG_ACCESS_TOKEN
IG_BUSINESS_ACCOUNT_ID
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Optional secrets or workflow env values:

```text
POST_INTERVAL_DAYS=2
YOUTUBE_PRIVACY_STATUS=public
YOUTUBE_CATEGORY_ID=24
LOW_QUEUE_THRESHOLD=2
TIMEZONE=Asia/Kolkata
```

## Monthly Workflow

1. Add your new `.mp4` files to the Drive folder.
2. Add matching rows in the Google Sheet.
3. Make sure each `filename` exactly matches the Drive filename.
4. Add each caption.
5. Set each new row status to `pending`.
6. Leave `posted_at` and `platform_ids` blank.

That is it. GitHub Actions will post the next due video.

## Manual Test Run

1. Push this repo to GitHub.
2. Add all secrets.
3. Open the **Actions** tab.
4. Select **Post Shorts And Reels**.
5. Click **Run workflow**.
6. Set `force_post` to `true` only when you want to post immediately even if the 2-day interval has not elapsed.

The workflow checks every 6 hours. The script only posts when the last successful post was at least 2 days ago, unless `force_post` is set to `true` for a manual run.

## Local Dry Run Notes

You can run the uploader locally if your environment variables are set:

```bash
python -m src.main
```

This is not a dry run. It will upload if a post is due.

## Validation Rules

Before upload, the video is downloaded and checked:

- Duration must be 180 seconds or less.
- Height must be greater than width.

If validation fails, the script sends a Telegram error and does not mark the row as posted.

## Partial Upload Safety

If YouTube succeeds and Instagram fails, the Sheet is updated to:

```text
posted_yt_only
```

The next run will skip YouTube and only retry Instagram.

If Instagram succeeds and YouTube fails, the Sheet is updated to:

```text
posted_ig_only
```

The next run will skip Instagram and only retry YouTube.

## One-Time Setup Summary

Plan for about 30 to 45 minutes:

1. Google Cloud project, APIs, OAuth client, and refresh token: 10 to 15 minutes.
2. Google Sheet and Drive folder: 5 minutes.
3. Meta app, Instagram Business or Creator connection, and long-lived Page token: 15 to 25 minutes.
4. Telegram bot and chat ID: 2 to 5 minutes.
5. GitHub secrets and first manual workflow run: 5 minutes.
