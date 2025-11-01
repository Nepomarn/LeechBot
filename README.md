# Telegram URL Leech Bot with TMDB Integration

A powerful Telegram bot that downloads files from URLs and uploads them to Telegram with automatic TMDB metadata (posters, synopsis, ratings).

## Features

✅ **Direct URL Downloading** - Download from any direct link (Google Drive, Dropbox, OneDrive, etc.)
✅ **TMDB Integration** - Auto-fetch movie/series info, posters, and synopsis
✅ **Custom Thumbnails** - Set custom thumbnails or use auto-fetched posters
✅ **File Renaming** - Rename files before uploading
✅ **Progress Tracking** - Real-time download/upload speed and ETA
✅ **User Statistics** - Track downloads and bandwidth usage
✅ **Multi-user Support** - Each user has their own settings

## TMDB Auto-Detection

The bot automatically detects:
- **Movies**: `Movie Name 2024.mkv`, `Movie (2024).mp4`
- **TV Series**: `Series Name S01E01.mkv`
- **Media Info**: Posters, ratings, synopsis, year, episode details

## Commands

- `/start` - Start the bot
- `/help` - Show all commands
- `/tmdb on|off` - Toggle TMDB auto-fetch
- `/setthumb` - Set custom thumbnail
- `/showthumb` - View current thumbnail
- `/delthumb` - Delete custom thumbnail
- `/setcaption` - Set custom caption
- `/fileinfo <url>` - Get file information
- `/stats` - View your statistics

## Deployment on Render

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/telegram-leech-bot.git
   git push -u origin main
   ```

2. **Deploy on Render**
   - Go to https://render.com
   - Click "New +" → "Background Worker"
   - Connect your GitHub repository
   - Set environment variables:
     - `API_ID` = Your API ID
     - `API_HASH` = Your API hash
     - `BOT_TOKEN` = Your bot token
   - Build command: `pip install -r requirements.txt`
   - Start command: Leave empty (uses Procfile)

3. **Deploy and Run**
   - Click "Create Background Worker"
   - Wait for deployment to complete

## Environment Variables

Set these in your Render dashboard:

```
API_ID = your_api_id_here
API_HASH = your_api_hash_here
BOT_TOKEN = your_bot_token_here
```

## Getting Credentials

1. **API_ID & API_HASH**: https://my.telegram.org/apps
2. **BOT_TOKEN**: Talk to @BotFather on Telegram

## Notes

- TMDB is enabled by default
- Bot stores settings in memory (resets on restart)
- Max file size: 2GB
- Render free tier: 750 hours/month
- Files are cleaned up after upload

## License

MIT
