
import os
import zipfile
from io import StringIO

# Create temporary directory structure
os.makedirs("telegram_leech_bot", exist_ok=True)

# 1. Main bot file
url_leech_bot = '''import os
import time
import aiohttp
import asyncio
import hashlib
import re
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN, MAX_FILE_SIZE, DOWNLOAD_DIR

# TMDB Configuration
TMDB_API_KEY = "77895da1c0b0f4a7a42da492eeb18444"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"

# Initialize bot
app = Client(
    "url_leech_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Create directories
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs("./thumbnails", exist_ok=True)
os.makedirs("./tmdb_cache", exist_ok=True)

# Storage dictionaries
url_storage = {}
thumbnail_storage = {}
user_preferences = {}
download_queue = {}
tmdb_cache = {}

# Extract movie/series info from filename
def extract_media_info(filename):
    """Extract movie/series name, year, season, episode from filename"""
    filename = filename.replace(".", " ").replace("_", " ")
    
    # Pattern for series: S01E01, S01, etc
    series_pattern = r'(.+?)\\s*[Ss](\\d{1,2})[Ee](\\d{1,2})'
    series_match = re.search(series_pattern, filename)
    
    if series_match:
        title = series_match.group(1).strip()
        season = int(series_match.group(2))
        episode = int(series_match.group(3))
        return {"type": "tv", "title": title, "season": season, "episode": episode}
    
    # Pattern for movies: (2024), [2024], 2024
    movie_pattern = r'(.+?)\\s*[\\(\\[]?(\\d{4})[\\)\\]]?'
    movie_match = re.search(movie_pattern, filename)
    
    if movie_match:
        title = movie_match.group(1).strip()
        year = movie_match.group(2)
        return {"type": "movie", "title": title, "year": year}
    
    # Default: treat as movie without year
    title = re.split(r'\\d{4}|720p|1080p|2160p|4K|BluRay|WEB-DL|WEBRip', filename)[0].strip()
    return {"type": "movie", "title": title, "year": None}

# Search TMDB for movie/series
async def search_tmdb(title, media_type="movie", year=None):
    """Search TMDB for movie or TV show"""
    try:
        async with aiohttp.ClientSession() as session:
            if media_type == "movie":
                url = f"{TMDB_BASE_URL}/search/movie"
                params = {"api_key": TMDB_API_KEY, "query": title}
                if year:
                    params["year"] = year
            else:
                url = f"{TMDB_BASE_URL}/search/tv"
                params = {"api_key": TMDB_API_KEY, "query": title}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("results"):
                        return data["results"][0]
        return None
    except Exception as e:
        print(f"TMDB search error: {e}")
        return None

# Get detailed info from TMDB
async def get_tmdb_details(tmdb_id, media_type="movie", season=None, episode=None):
    """Get detailed information including poster and overview"""
    try:
        async with aiohttp.ClientSession() as session:
            if media_type == "movie":
                url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
            else:
                url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
            
            params = {"api_key": TMDB_API_KEY}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Get episode details if available
                    if media_type == "tv" and season and episode:
                        ep_url = f"{TMDB_BASE_URL}/tv/{tmdb_id}/season/{season}/episode/{episode}"
                        async with session.get(ep_url, params=params) as ep_response:
                            if ep_response.status == 200:
                                ep_data = await ep_response.json()
                                data['episode_info'] = ep_data
                    
                    return data
        return None
    except Exception as e:
        print(f"TMDB details error: {e}")
        return None

# Download TMDB poster as thumbnail
async def download_tmdb_poster(poster_path, save_path):
    """Download poster from TMDB"""
    try:
        if not poster_path:
            return False
        
        url = f"{TMDB_IMAGE_BASE}{poster_path}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(save_path, 'wb') as f:
                        f.write(await response.read())
                    return True
        return False
    except Exception as e:
        print(f"Poster download error: {e}")
        return False

# Generate caption from TMDB data
def generate_tmdb_caption(filename, file_size, tmdb_data, media_info):
    """Generate formatted caption with TMDB info"""
    if not tmdb_data:
        return f"**📁 File:** `{filename}`\\n**📦 Size:** {file_size / (1024*1024):.2f} MB"
    
    if media_info["type"] == "movie":
        title = tmdb_data.get("title", filename)
        year = tmdb_data.get("release_date", "")[:4]
        rating = tmdb_data.get("vote_average", "N/A")
        overview = tmdb_data.get("overview", "No synopsis available")
        
        caption = (
            f"**🎬 {title} ({year})**\\n\\n"
            f"⭐ **Rating:** {rating}/10\\n"
            f"📦 **Size:** {file_size / (1024*1024):.2f} MB\\n\\n"
            f"**📝 Synopsis:**\\n{overview[:200]}..."
        )
    else:
        title = tmdb_data.get("name", filename)
        first_air = tmdb_data.get("first_air_date", "")[:4]
        rating = tmdb_data.get("vote_average", "N/A")
        
        caption = f"**📺 {title} ({first_air})**\\n\\n"
        
        if "episode_info" in tmdb_data:
            ep_info = tmdb_data["episode_info"]
            ep_title = ep_info.get("name", "")
            ep_overview = ep_info.get("overview", "No synopsis available")
            
            caption += (
                f"**Season {media_info['season']} Episode {media_info['episode']}**\\n"
                f"**Title:** {ep_title}\\n\\n"
                f"⭐ **Rating:** {rating}/10\\n"
                f"📦 **Size:** {file_size / (1024*1024):.2f} MB\\n\\n"
                f"**📝 Synopsis:**\\n{ep_overview[:200]}..."
            )
        else:
            overview = tmdb_data.get("overview", "No synopsis available")
            caption += (
                f"⭐ **Rating:** {rating}/10\\n"
                f"📦 **Size:** {file_size / (1024*1024):.2f} MB\\n\\n"
                f"**📝 Synopsis:**\\n{overview[:200]}..."
            )
    
    return caption

# Progress callback
async def progress_callback(current, total, message, text):
    try:
        if total == 0:
            return
        percent = current * 100 / total
        bar_length = 20
        filled_length = int(bar_length * current // total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        speed = current / ((time.time() - message.date.timestamp()) + 1)
        eta = (total - current) / speed if speed > 0 else 0
        
        await message.edit_text(
            f"{text}\\n\\n"
            f"Progress: {bar} {percent:.1f}%\\n"
            f"Size: {current / (1024*1024):.2f} MB / {total / (1024*1024):.2f} MB\\n"
            f"Speed: {speed / (1024*1024):.2f} MB/s\\n"
            f"ETA: {int(eta)}s"
        )
    except:
        pass

# Get file size from URL
async def get_file_size(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                return int(response.headers.get('content-length', 0))
    except:
        return 0

# Download file from URL
async def download_file(url, filename, message):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3600)) as response:
                if response.status not in [200, 206]:
                    return None, f"Failed to download (Status: {response.status})"
                
                total_size = int(response.headers.get('content-length', 0))
                
                if total_size > MAX_FILE_SIZE:
                    return None, f"File too large: {total_size / (1024*1024*1024):.2f} GB"
                
                downloaded = 0
                last_update = 0
                
                with open(filepath, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if downloaded - last_update >= (5 * 1024 * 1024):
                            await progress_callback(downloaded, total_size, message, "⬇️ Downloading...")
                            last_update = downloaded
        
        return filepath, None
    except Exception as e:
        return None, f"Download error: {str(e)}"

# Start command
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "**🔗 Advanced URL Leech Bot with TMDB**\\n\\n"
        "Send me a direct download link and I'll upload it with automatic TMDB info!\\n\\n"
        "**Commands:**\\n"
        "• `/help` - Show all commands\\n"
        "• `/tmdb on/off` - Toggle TMDB auto-fetch\\n"
        "• `/setthumb` - Set custom thumbnail\\n"
        "• `/showthumb` - View thumbnail\\n"
        "• `/delthumb` - Delete thumbnail\\n"
        "• `/setcaption` - Set custom caption\\n"
        "• `/fileinfo` - Get file info\\n"
        "• `/stats` - View stats\\n\\n"
        "**TMDB Features:**\\n"
        "✅ Auto-detect movie/series from filename\\n"
        "✅ Fetch poster as thumbnail\\n"
        "✅ Add synopsis & ratings\\n"
        "✅ Support for TV episodes\\n\\n"
        "**Supported:** Google Drive, Dropbox, OneDrive, any direct URL\\n"
        "**Max file size:** 2GB"
    )

# Help command
@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    await message.reply_text(
        "**📖 Bot Commands**\\n\\n"
        "**TMDB Integration:**\\n"
        "• `/tmdb on` - Enable auto TMDB fetch\\n"
        "• `/tmdb off` - Disable TMDB\\n"
        "• Automatically detects movies/series from filename\\n"
        "• Fetches poster, synopsis, ratings\\n\\n"
        "**Filename Examples:**\\n"
        "• `Deadpool 2024 1080p.mkv`\\n"
        "• `Breaking Bad S01E01.mkv`\\n"
        "• `Avengers Endgame (2019).mp4`\\n\\n"
        "**Other Commands:**\\n"
        "• `/setthumb` - Custom thumbnail\\n"
        "• `/setcaption` - Custom caption\\n"
        "• `/fileinfo <url>` - File details\\n"
        "• `/stats` - Usage statistics\\n\\n"
        "**Caption Variables:**\\n"
        "• `{filename}` - File name\\n"
        "• `{size}` - File size\\n"
        "• `{date}` - Upload date\\n"
        "• `{time}` - Upload time"
    )

# TMDB toggle command
@app.on_message(filters.command("tmdb"))
async def tmdb_toggle_command(client, message: Message):
    user_id = message.from_user.id
    
    try:
        setting = message.text.split()[1].lower()
        
        if user_id not in user_preferences:
            user_preferences[user_id] = {}
        
        if setting == "on":
            user_preferences[user_id]['tmdb_enabled'] = True
            await message.reply_text("✅ TMDB auto-fetch **ENABLED**\\n\\nMovie/series info will be fetched automatically!")
        elif setting == "off":
            user_preferences[user_id]['tmdb_enabled'] = False
            await message.reply_text("❌ TMDB auto-fetch **DISABLED**\\n\\nFiles will be uploaded with basic info only.")
        else:
            await message.reply_text("Usage: `/tmdb on` or `/tmdb off`")
    except IndexError:
        status = user_preferences.get(user_id, {}).get('tmdb_enabled', True)
        await message.reply_text(
            f"**TMDB Status:** {'✅ Enabled' if status else '❌ Disabled'}\\n\\n"
            "Usage: `/tmdb on` or `/tmdb off`"
        )

# Set thumbnail command
@app.on_message(filters.command("setthumb"))
async def set_thumb_command(client, message: Message):
    await message.reply_text(
        "📸 Send me an image to use as thumbnail.\\n\\n"
        "**Note:** When TMDB is enabled, movie posters will be used automatically. "
        "Custom thumbnail will be used as fallback."
    )

# Show thumbnail command
@app.on_message(filters.command("showthumb"))
async def show_thumb_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id in thumbnail_storage:
        thumb_path = thumbnail_storage[user_id]
        if os.path.exists(thumb_path):
            await message.reply_photo(thumb_path, caption="📸 Your current thumbnail")
        else:
            await message.reply_text("❌ Thumbnail not found.")
            del thumbnail_storage[user_id]
    else:
        await message.reply_text("📸 No custom thumbnail set.")

# Delete thumbnail command
@app.on_message(filters.command("delthumb"))
async def delete_thumb_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id in thumbnail_storage:
        thumb_path = thumbnail_storage[user_id]
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        del thumbnail_storage[user_id]
        await message.reply_text("✅ Thumbnail deleted!")
    else:
        await message.reply_text("📸 No thumbnail to delete.")

# Set caption command
@app.on_message(filters.command("setcaption"))
async def set_caption_command(client, message: Message):
    user_id = message.from_user.id
    
    try:
        caption = message.text.split(None, 1)[1]
        
        if user_id not in user_preferences:
            user_preferences[user_id] = {}
        
        user_preferences[user_id]['caption'] = caption
        
        await message.reply_text(
            f"✅ Caption saved!\\n\\n**Preview:**\\n{caption}\\n\\n"
            "**Note:** TMDB captions will override this when enabled."
        )
    except IndexError:
        await message.reply_text("Usage: `/setcaption Your caption here`")

# File info command
@app.on_message(filters.command("fileinfo"))
async def fileinfo_command(client, message: Message):
    try:
        url = message.text.split(None, 1)[1]
        
        if not url.startswith(("http://", "https://")):
            await message.reply_text("❌ Invalid URL")
            return
        
        status = await message.reply_text("🔍 Fetching info...")
        
        file_size = await get_file_size(url)
        filename = url.split("/")[-1].split("?")[0]
        
        # Try TMDB lookup
        media_info = extract_media_info(filename)
        tmdb_data = await search_tmdb(media_info["title"], media_info["type"], media_info.get("year"))
        
        info_text = f"**📊 File Information**\\n\\n**Filename:** `{filename}`\\n"
        
        if file_size > 0:
            info_text += f"**Size:** {file_size / (1024*1024):.2f} MB\\n"
        
        if tmdb_data:
            if media_info["type"] == "movie":
                info_text += f"\\n🎬 **Movie:** {tmdb_data.get('title')}\\n"
                info_text += f"📅 **Year:** {tmdb_data.get('release_date', '')[:4]}\\n"
                info_text += f"⭐ **Rating:** {tmdb_data.get('vote_average')}/10"
            else:
                info_text += f"\\n📺 **Series:** {tmdb_data.get('name')}\\n"
                info_text += f"⭐ **Rating:** {tmdb_data.get('vote_average')}/10"
        
        await status.edit_text(info_text)
    
    except IndexError:
        await message.reply_text("Usage: `/fileinfo <url>`")

# Stats command
@app.on_message(filters.command("stats"))
async def stats_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_preferences:
        user_preferences[user_id] = {'downloads': 0, 'total_size': 0}
    
    stats = user_preferences[user_id]
    tmdb_status = stats.get('tmdb_enabled', True)
    
    await message.reply_text(
        f"**📊 Your Statistics**\\n\\n"
        f"**Downloads:** {stats.get('downloads', 0)}\\n"
        f"**Total Data:** {stats.get('total_size', 0) / (1024*1024*1024):.2f} GB\\n"
        f"**TMDB:** {'✅ Enabled' if tmdb_status else '❌ Disabled'}\\n"
        f"**Thumbnail:** {'✅ Set' if user_id in thumbnail_storage else '❌ Not set'}\\n"
        f"**Caption:** {'✅ Set' if 'caption' in stats else '❌ Not set'}"
    )

# Handle thumbnail images
@app.on_message(filters.photo & filters.private)
async def handle_thumbnail(client, message: Message):
    user_id = message.from_user.id
    
    thumb_path = f"./thumbnails/{user_id}_thumb.jpg"
    await message.download(file_name=thumb_path)
    
    file_size = os.path.getsize(thumb_path)
    if file_size > 200 * 1024:
        os.remove(thumb_path)
        await message.reply_text(f"⚠️ Thumbnail too large: {file_size / 1024:.1f} KB\\nMax: 200 KB")
        return
    
    thumbnail_storage[user_id] = thumb_path
    await message.reply_text("✅ Thumbnail saved!")

# Handle URLs
@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "tmdb", "setthumb", "showthumb", "delthumb", "setcaption", "showcaption", "delcaption", "fileinfo", "stats", "queue"]))
async def handle_url(client, message: Message):
    url = message.text.strip()
    
    if not url.startswith(("http://", "https://")):
        return
    
    filename = url.split("/")[-1].split("?")[0]
    if not filename or len(filename) < 3:
        filename = f"file_{int(time.time())}"
    
    url_id = hashlib.md5(f"{url}{time.time()}".encode()).hexdigest()[:8]
    url_storage[url_id] = {"url": url, "filename": filename}
    
    user_id = message.from_user.id
    tmdb_enabled = user_preferences.get(user_id, {}).get('tmdb_enabled', True)
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Download", callback_data=f"dl_{url_id}"),
            InlineKeyboardButton("ℹ️ Info", callback_data=f"info_{url_id}")
        ],
        [
            InlineKeyboardButton("✏️ Rename", callback_data=f"rn_{url_id}")
        ]
    ])
    
    await message.reply_text(
        f"**📁 Filename:** `{filename}`\\n"
        f"**🎬 TMDB:** {'✅ Enabled' if tmdb_enabled else '❌ Disabled'}\\n\\n"
        "Choose an option:",
        reply_markup=keyboard
    )

rename_data = {}

# Handle button callbacks
@app.on_callback_query()
async def handle_callback(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data.startswith("dl_"):
        url_id = data.split("_")[1]
        
        if url_id not in url_storage:
            await callback_query.answer("⚠️ Link expired!", show_alert=True)
            return
        
        url_data = url_storage[url_id]
        await callback_query.message.delete()
        await process_download(client, callback_query.message, url_data["url"], url_data["filename"], user_id)
        del url_storage[url_id]
    
    elif data.startswith("info_"):
        url_id = data.split("_")[1]
        
        if url_id not in url_storage:
            await callback_query.answer("⚠️ Link expired!", show_alert=True)
            return
        
        url_data = url_storage[url_id]
        file_size = await get_file_size(url_data["url"])
        
        info_text = f"**File:** {url_data['filename']}\\n"
        if file_size > 0:
            info_text += f"**Size:** {file_size / (1024*1024):.2f} MB"
        
        await callback_query.answer(info_text, show_alert=True)
    
    elif data.startswith("rn_"):
        url_id = data.split("_")[1]
        
        if url_id not in url_storage:
            await callback_query.answer("⚠️ Link expired!", show_alert=True)
            return
        
        url_data = url_storage[url_id]
        rename_data[user_id] = {"url_id": url_id, "url": url_data["url"], "filename": url_data["filename"]}
        
        await callback_query.message.edit_text(f"✏️ Send new filename:\\n\\nCurrent: `{url_data['filename']}`")
        await callback_query.answer()

# Handle rename input
@app.on_message(filters.text & filters.private & filters.regex(r"^(?!http).*") & ~filters.command(["start", "help", "tmdb", "setthumb", "showthumb", "delthumb", "setcaption", "showcaption", "delcaption", "fileinfo", "stats", "queue"]))
async def handle_rename_input(client, message: Message):
    user_id = message.from_user.id
    
    if user_id in rename_data:
        new_filename = message.text.strip()
        url = rename_data[user_id]["url"]
        url_id = rename_data[user_id]["url_id"]
        
        del rename_data[user_id]
        if url_id in url_storage:
            del url_storage[url_id]
        
        await process_download(client, message, url, new_filename, user_id)

# Process download with TMDB integration
async def process_download(client, message, url, filename, user_id):
    status_msg = await message.reply_text("⬇️ Starting download...")
    
    # Check if TMDB is enabled
    tmdb_enabled = user_preferences.get(user_id, {}).get('tmdb_enabled', True)
    
    # Extract media info and fetch TMDB data
    tmdb_data = None
    tmdb_thumb_path = None
    media_info = {}
    
    if tmdb_enabled:
        await status_msg.edit_text("🎬 Fetching TMDB info...")
        media_info = extract_media_info(filename)
        search_result = await search_tmdb(media_info["title"], media_info["type"], media_info.get("year"))
        
        if search_result:
            tmdb_id = search_result.get("id")
            tmdb_data = await get_tmdb_details(
                tmdb_id, 
                media_info["type"],
                media_info.get("season"),
                media_info.get("episode")
            )
            
            # Download poster as thumbnail
            if tmdb_data and tmdb_data.get("poster_path"):
                tmdb_thumb_path = f"./tmdb_cache/{user_id}_{int(time.time())}.jpg"
                await download_tmdb_poster(tmdb_data.get("poster_path"), tmdb_thumb_path)
    
    # Download file
    filepath, error = await download_file(url, filename, status_msg)
    
    if error:
        await status_msg.edit_text(f"❌ {error}")
        return
    
    # Choose thumbnail: TMDB poster > custom thumbnail > none
    thumb_path = None
    if tmdb_thumb_path and os.path.exists(tmdb_thumb_path):
        thumb_path = tmdb_thumb_path
    elif user_id in thumbnail_storage:
        thumb_path = thumbnail_storage[user_id]
    
    try:
        await status_msg.edit_text("⬆️ Uploading to Telegram...")
        
        file_size = os.path.getsize(filepath)
        
        # Generate caption
        if tmdb_enabled and tmdb_data:
            caption = generate_tmdb_caption(filename, file_size, tmdb_data, media_info)
        elif user_id in user_preferences and 'caption' in user_preferences[user_id]:
            caption_template = user_preferences[user_id]['caption']
            caption = caption_template.format(
                filename=filename,
                size=f"{file_size / (1024*1024):.2f}",
                date=time.strftime("%Y-%m-%d"),
                time=time.strftime("%H:%M:%S")
            )
        else:
            caption = f"**📁 File:** `{filename}`\\n**📦 Size:** {file_size / (1024*1024):.2f} MB"
        
        async def upload_progress(current, total):
            await progress_callback(current, total, status_msg, "⬆️ Uploading...")
        
        await client.send_document(
            chat_id=message.chat.id,
            document=filepath,
            thumb=thumb_path,
            caption=caption,
            progress=upload_progress
        )
        
        await status_msg.delete()
        
        # Update stats
        if user_id not in user_preferences:
            user_preferences[user_id] = {'downloads': 0, 'total_size': 0}
        user_preferences[user_id]['downloads'] = user_preferences[user_id].get('downloads', 0) + 1
        user_preferences[user_id]['total_size'] = user_preferences[user_id].get('total_size', 0) + file_size
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
    
    finally:
        # Clean up
        if os.path.exists(filepath):
            os.remove(filepath)
        if tmdb_thumb_path and os.path.exists(tmdb_thumb_path):
            os.remove(tmdb_thumb_path)

print("🤖 Bot starting with TMDB integration...")
app.run()
'''

with open("telegram_leech_bot/url_leech_bot.py", "w", encoding="utf-8") as f:
    f.write(url_leech_bot)

# 2. Config file
config_py = '''import os

# Get from https://my.telegram.org
API_ID = int(os.getenv("API_ID", "12345678"))
API_HASH = os.getenv("API_HASH", "your_api_hash")

# Get from @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")

# File size limit
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

# Download directory
DOWNLOAD_DIR = "./downloads"
'''

with open("telegram_leech_bot/config.py", "w", encoding="utf-8") as f:
    f.write(config_py)

# 3. Requirements.txt
requirements = '''pyrogram==2.0.106
tgcrypto==1.2.5
aiohttp==3.9.1
requests==2.31.0
'''

with open("telegram_leech_bot/requirements.txt", "w", encoding="utf-8") as f:
    f.write(requirements)

# 4. Procfile
procfile = '''worker: python url_leech_bot.py
'''

with open("telegram_leech_bot/Procfile", "w", encoding="utf-8") as f:
    f.write(procfile)

# 5. .gitignore
gitignore = '''*.session
*.session-journal
downloads/
thumbnails/
tmdb_cache/
__pycache__/
*.pyc
.DS_Store
config.py
.env
venv/
'''

with open("telegram_leech_bot/.gitignore", "w", encoding="utf-8") as f:
    f.write(gitignore)

# 6. README.md
readme = '''# Telegram URL Leech Bot with TMDB Integration

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
'''

with open("telegram_leech_bot/README.md", "w", encoding="utf-8") as f:
    f.write(readme)

# 7. runtime.txt for Python version
runtime = '''python-3.11.7
'''

with open("telegram_leech_bot/runtime.txt", "w", encoding="utf-8") as f:
    f.write(runtime)

# Create ZIP file
zip_filename = "telegram_leech_bot.zip"
with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk("telegram_leech_bot"):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, ".")
            zipf.write(file_path, arcname)

print(f"✅ Created {zip_filename}")
print("\nFiles included:")
print("  ✓ url_leech_bot.py (Main bot with TMDB)")
print("  ✓ config.py (Configuration with env variables)")
print("  ✓ requirements.txt (Python dependencies)")
print("  ✓ Procfile (Render worker command)")
print("  ✓ .gitignore (Git ignore rules)")
print("  ✓ runtime.txt (Python version)")
print("  ✓ README.md (Setup instructions)")
print(f"\n📦 ZIP file ready for deployment!")
