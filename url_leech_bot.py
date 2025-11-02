import os
import time
import aiohttp
import asyncio
import hashlib
import re
import threading
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN, MAX_FILE_SIZE, DOWNLOAD_DIR

# TMDB Configuration
TMDB_API_KEY = "77895da1c0b0f4a7a42da492eeb18444"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"

# Video file extensions
VIDEO_EXTENSIONS = {
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
    '.mpeg', '.mpg', '.3gp', '.3g2', '.ogv', '.ts', '.m2ts', '.mts',
    '.vob', '.rm', '.rmvb', '.asf', '.divx', '.xvid', '.f4v', '.hevc',
    '.h264', '.h265', '.m2v', '.dat', '.swf', '.qt', '.dv', '.mxf'
}

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

# ===== HTTP SERVER FOR RENDER =====
async def health_check(request):
    return web.Response(text="✅ Telegram Bot is running!\n🤖 Bot Status: Active\n⏰ Uptime: OK")

def run_web_server():
    """Run web server in separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    port = int(os.environ.get('PORT', 10000))
    
    async def start():
        app_web = web.Application()
        app_web.router.add_get('/', health_check)
        app_web.router.add_get('/health', health_check)
        
        runner = web.AppRunner(app_web)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"🌐 Web server started on port {port}")
    
    loop.run_until_complete(start())
    loop.run_forever()

# ===== HELPER FUNCTIONS =====

def is_video_file(filename):
    """Check if file is a video based on extension"""
    ext = os.path.splitext(filename.lower())[1]
    return ext in VIDEO_EXTENSIONS

def extract_media_info(filename):
    """Extract movie/series name, year, season, episode from filename"""
    filename = filename.replace(".", " ").replace("_", " ")
    
    series_pattern = r'(.+?)\s*[Ss](\d{1,2})[Ee](\d{1,2})'
    series_match = re.search(series_pattern, filename)
    
    if series_match:
        title = series_match.group(1).strip()
        season = int(series_match.group(2))
        episode = int(series_match.group(3))
        return {"type": "tv", "title": title, "season": season, "episode": episode}
    
    movie_pattern = r'(.+?)\s*[\(\[]?(\d{4})[\)\]]?'
    movie_match = re.search(movie_pattern, filename)
    
    if movie_match:
        title = movie_match.group(1).strip()
        year = movie_match.group(2)
        return {"type": "movie", "title": title, "year": year}
    
    title = re.split(r'\d{4}|720p|1080p|2160p|4K|BluRay|WEB-DL|WEBRip', filename)[0].strip()
    return {"type": "movie", "title": title, "year": None}

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

def generate_tmdb_caption(filename, file_size, tmdb_data, media_info):
    """Generate formatted caption with TMDB info"""
    if not tmdb_data:
        return f"**📁 File:** `{filename}`\n**📦 Size:** {file_size / (1024*1024):.2f} MB"
    
    if media_info["type"] == "movie":
        title = tmdb_data.get("title", filename)
        year = tmdb_data.get("release_date", "")[:4]
        rating = tmdb_data.get("vote_average", "N/A")
        overview = tmdb_data.get("overview", "No synopsis available")
        
        caption = (
            f"**🎬 {title} ({year})**\n\n"
            f"⭐ **Rating:** {rating}/10\n"
            f"📦 **Size:** {file_size / (1024*1024):.2f} MB\n\n"
            f"**📝 Synopsis:**\n{overview[:200]}..."
        )
    else:
        title = tmdb_data.get("name", filename)
        first_air = tmdb_data.get("first_air_date", "")[:4]
        rating = tmdb_data.get("vote_average", "N/A")
        
        caption = f"**📺 {title} ({first_air})**\n\n"
        
        if "episode_info" in tmdb_data:
            ep_info = tmdb_data["episode_info"]
            ep_title = ep_info.get("name", "")
            ep_overview = ep_info.get("overview", "No synopsis available")
            
            caption += (
                f"**Season {media_info['season']} Episode {media_info['episode']}**\n"
                f"**Title:** {ep_title}\n\n"
                f"⭐ **Rating:** {rating}/10\n"
                f"📦 **Size:** {file_size / (1024*1024):.2f} MB\n\n"
                f"**📝 Synopsis:**\n{ep_overview[:200]}..."
            )
        else:
            overview = tmdb_data.get("overview", "No synopsis available")
            caption += (
                f"⭐ **Rating:** {rating}/10\n"
                f"📦 **Size:** {file_size / (1024*1024):.2f} MB\n\n"
                f"**📝 Synopsis:**\n{overview[:200]}..."
            )
    
    return caption

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
            f"{text}\n\n"
            f"Progress: {bar} {percent:.1f}%\n"
            f"Size: {current / (1024*1024):.2f} MB / {total / (1024*1024):.2f} MB\n"
            f"Speed: {speed / (1024*1024):.2f} MB/s\n"
            f"ETA: {int(eta)}s"
        )
    except:
        pass

async def get_file_size(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                return int(response.headers.get('content-length', 0))
    except:
        return 0

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

# ===== BOT COMMANDS =====

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text(
        "**🔗 Advanced URL Leech Bot with TMDB**\n\n"
        "Send me a direct download link and I'll upload it with automatic TMDB info!\n\n"
        "**Commands:**\n"
        "• `/help` - Show all commands\n"
        "• `/mode video|file|auto` - Upload mode\n"
        "• `/tmdb on/off` - Toggle TMDB\n"
        "• `/setthumb` - Custom thumbnail\n"
        "• `/setcaption` - Custom caption\n"
        "• `/fileinfo` - Get file info\n"
        "• `/stats` - View stats\n\n"
        "**Upload Modes:**\n"
        "🎬 **Video** - Always upload as video\n"
        "📄 **File** - Always upload as document\n"
        "🤖 **Auto** - Detect video files (default)\n\n"
        "**TMDB Features:**\n"
        "✅ Auto-detect movie/series\n"
        "✅ Fetch poster & synopsis\n"
        "✅ Support for TV episodes\n\n"
        "**Supported Video Formats:**\n"
        "MP4, MKV, AVI, MOV, WMV, FLV, WEBM, M4V, MPEG, 3GP, and 20+ more\n\n"
        "**Max file size:** 2GB"
    )

@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    await message.reply_text(
        "**📖 Bot Commands & Features**\n\n"
        "**Upload Mode:**\n"
        "• `/mode video` - Always upload as video\n"
        "• `/mode file` - Always upload as document\n"
        "• `/mode auto` - Auto-detect (default)\n"
        "• `/mode` - Check current mode\n\n"
        "**TMDB Integration:**\n"
        "• `/tmdb on` - Enable TMDB\n"
        "• `/tmdb off` - Disable TMDB\n\n"
        "**Customization:**\n"
        "• `/setthumb` - Upload thumbnail image\n"
        "• `/showthumb` - View thumbnail\n"
        "• `/delthumb` - Delete thumbnail\n"
        "• `/setcaption` - Custom caption\n\n"
        "**Info & Stats:**\n"
        "• `/fileinfo <url>` - Get file details\n"
        "• `/stats` - View statistics\n\n"
        "**Supported Video Formats:**\n"
        "MP4, MKV, AVI, MOV, WMV, FLV, WEBM, M4V, MPEG, MPG, 3GP, OGV, "
        "TS, M2TS, VOB, RM, RMVB, ASF, DIVX, XVID, F4V, HEVC, H264, H265, and more!"
    )

@app.on_message(filters.command("mode"))
async def mode_toggle_command(client, message: Message):
    user_id = message.from_user.id
    
    try:
        setting = message.text.split()[1].lower()
        
        if user_id not in user_preferences:
            user_preferences[user_id] = {}
        
        if setting == "video":
            user_preferences[user_id]['upload_mode'] = 'video'
            await message.reply_text(
                "✅ Upload mode: **VIDEO**\n\n"
                "🎬 All files will be uploaded as videos.\n"
                "Best for: Movies, TV shows, video content"
            )
        elif setting == "file" or setting == "document":
            user_preferences[user_id]['upload_mode'] = 'document'
            await message.reply_text(
                "✅ Upload mode: **DOCUMENT/FILE**\n\n"
                "📄 All files will be uploaded as documents.\n"
                "Best for: Any file type, non-videos"
            )
        elif setting == "auto":
            user_preferences[user_id]['upload_mode'] = 'auto'
            await message.reply_text(
                "✅ Upload mode: **AUTO**\n\n"
                "🤖 Videos will be uploaded as videos, others as documents.\n"
                "Supports 30+ video formats automatically!"
            )
        else:
            await message.reply_text(
                "❌ Invalid mode!\n\n"
                "**Usage:**\n"
                "• `/mode video` - Always video\n"
                "• `/mode file` - Always document\n"
                "• `/mode auto` - Auto-detect (default)"
            )
    except IndexError:
        current_mode = user_preferences.get(user_id, {}).get('upload_mode', 'auto')
        mode_emoji = {'video': '🎬', 'document': '📄', 'auto': '🤖'}
        
        await message.reply_text(
            f"**Current Mode:** {current_mode.upper()} {mode_emoji.get(current_mode, '🤖')}\n\n"
            "**Available Modes:**\n"
            "• `/mode video` - Always video\n"
            "• `/mode file` - Always document\n"
            "• `/mode auto` - Auto-detect (default)"
        )

@app.on_message(filters.command("tmdb"))
async def tmdb_toggle_command(client, message: Message):
    user_id = message.from_user.id
    
    try:
        setting = message.text.split()[1].lower()
        
        if user_id not in user_preferences:
            user_preferences[user_id] = {}
        
        if setting == "on":
            user_preferences[user_id]['tmdb_enabled'] = True
            await message.reply_text("✅ TMDB auto-fetch **ENABLED**\n\nMovie/series info will be fetched automatically!")
        elif setting == "off":
            user_preferences[user_id]['tmdb_enabled'] = False
            await message.reply_text("❌ TMDB auto-fetch **DISABLED**\n\nFiles will be uploaded with basic info only.")
        else:
            await message.reply_text("Usage: `/tmdb on` or `/tmdb off`")
    except IndexError:
        status = user_preferences.get(user_id, {}).get('tmdb_enabled', True)
        await message.reply_text(
            f"**TMDB Status:** {'✅ Enabled' if status else '❌ Disabled'}\n\n"
            "Usage: `/tmdb on` or `/tmdb off`"
        )

@app.on_message(filters.command("setthumb"))
async def set_thumb_command(client, message: Message):
    await message.reply_text(
        "📸 Send me an image to use as thumbnail.\n\n"
        "**Requirements:**\n"
        "• JPEG/PNG format\n"
        "• Less than 200 KB\n"
        "• Max 320x320 pixels\n\n"
        "**Note:** TMDB posters are used automatically when enabled."
    )

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
        await message.reply_text("📸 No custom thumbnail set. Use /setthumb to add one.")

@app.on_message(filters.command("delthumb"))
async def delete_thumb_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id in thumbnail_storage:
        thumb_path = thumbnail_storage[user_id]
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        del thumbnail_storage[user_id]
        await message.reply_text("✅ Thumbnail deleted successfully!")
    else:
        await message.reply_text("📸 No thumbnail to delete.")

@app.on_message(filters.command("setcaption"))
async def set_caption_command(client, message: Message):
    user_id = message.from_user.id
    
    try:
        caption = message.text.split(None, 1)[1]
        
        if user_id not in user_preferences:
            user_preferences[user_id] = {}
        
        user_preferences[user_id]['caption'] = caption
        
        await message.reply_text(
            f"✅ Caption saved!\n\n**Preview:**\n{caption}\n\n"
            "**Variables:** `{filename}`, `{size}`, `{date}`, `{time}`\n\n"
            "**Note:** TMDB captions override this when enabled."
        )
    except IndexError:
        await message.reply_text(
            "**Usage:** `/setcaption Your caption here`\n\n"
            "**Example:**\n"
            "`/setcaption 📁 {filename}\n📦 {size} MB\n📅 {date}`"
        )

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
        is_video = is_video_file(filename)
        
        media_info = extract_media_info(filename)
        tmdb_data = await search_tmdb(media_info["title"], media_info["type"], media_info.get("year"))
        
        info_text = f"**📊 File Information**\n\n"
        info_text += f"**Filename:** `{filename}`\n"
        info_text += f"**Type:** {'🎬 Video' if is_video else '📄 Document'}\n"
        
        if file_size > 0:
            info_text += f"**Size:** {file_size / (1024*1024):.2f} MB\n"
        
        if tmdb_data:
            if media_info["type"] == "movie":
                info_text += f"\n🎬 **Movie:** {tmdb_data.get('title')}\n"
                info_text += f"📅 **Year:** {tmdb_data.get('release_date', '')[:4]}\n"
                info_text += f"⭐ **Rating:** {tmdb_data.get('vote_average')}/10"
            else:
                info_text += f"\n📺 **Series:** {tmdb_data.get('name')}\n"
                info_text += f"⭐ **Rating:** {tmdb_data.get('vote_average')}/10"
        
        await status.edit_text(info_text)
    
    except IndexError:
        await message.reply_text("**Usage:** `/fileinfo <url>`")

@app.on_message(filters.command("stats"))
async def stats_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_preferences:
        user_preferences[user_id] = {'downloads': 0, 'total_size': 0}
    
    stats = user_preferences[user_id]
    tmdb_status = stats.get('tmdb_enabled', True)
    upload_mode = stats.get('upload_mode', 'auto')
    
    mode_emoji = {'video': '🎬', 'document': '📄', 'auto': '🤖'}
    
    await message.reply_text(
        f"**📊 Your Statistics**\n\n"
        f"**Downloads:** {stats.get('downloads', 0)}\n"
        f"**Total Data:** {stats.get('total_size', 0) / (1024*1024*1024):.2f} GB\n\n"
        f"**Settings:**\n"
        f"• **Upload Mode:** {upload_mode.upper()} {mode_emoji.get(upload_mode, '🤖')}\n"
        f"• **TMDB:** {'✅ Enabled' if tmdb_status else '❌ Disabled'}\n"
        f"• **Thumbnail:** {'✅ Set' if user_id in thumbnail_storage else '❌ Not set'}\n"
        f"• **Caption:** {'✅ Set' if 'caption' in stats else '❌ Not set'}"
    )

@app.on_message(filters.photo & filters.private)
async def handle_thumbnail(client, message: Message):
    user_id = message.from_user.id
    
    thumb_path = f"./thumbnails/{user_id}_thumb.jpg"
    await message.download(file_name=thumb_path)
    
    file_size = os.path.getsize(thumb_path)
    if file_size > 200 * 1024:
        os.remove(thumb_path)
        await message.reply_text(f"⚠️ Thumbnail too large: {file_size / 1024:.1f} KB\nMax: 200 KB")
        return
    
    thumbnail_storage[user_id] = thumb_path
    await message.reply_text("✅ Thumbnail saved successfully!")

@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "mode", "tmdb", "setthumb", "showthumb", "delthumb", "setcaption", "showcaption", "delcaption", "fileinfo", "stats", "queue"]))
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
    upload_mode = user_preferences.get(user_id, {}).get('upload_mode', 'auto')
    is_video = is_video_file(filename)
    
    # Determine upload type
    if upload_mode == 'auto':
        upload_type = "🎬 Video" if is_video else "📄 Document"
    elif upload_mode == 'video':
        upload_type = "🎬 Video (Forced)"
    else:
        upload_type = "📄 Document (Forced)"
    
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
        f"**📁 Filename:** `{filename}`\n"
        f"**📤 Upload as:** {upload_type}\n"
        f"**🎬 TMDB:** {'✅ On' if tmdb_enabled else '❌ Off'}\n\n"
        "Choose an option:",
        reply_markup=keyboard
    )

rename_data = {}

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
        is_video = is_video_file(url_data["filename"])
        
        info_text = f"**File:** {url_data['filename']}\n"
        info_text += f"**Type:** {'🎬 Video' if is_video else '📄 Document'}\n"
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
        
        await callback_query.message.edit_text(f"✏️ Send new filename:\n\nCurrent: `{url_data['filename']}`")
        await callback_query.answer()

@app.on_message(filters.text & filters.private & filters.regex(r"^(?!http).*") & ~filters.command(["start", "help", "mode", "tmdb", "setthumb", "showthumb", "delthumb", "setcaption", "showcaption", "delcaption", "fileinfo", "stats", "queue"]))
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

async def process_download(client, message, url, filename, user_id):
    status_msg = await message.reply_text("⬇️ Starting download...")
    
    tmdb_enabled = user_preferences.get(user_id, {}).get('tmdb_enabled', True)
    upload_mode = user_preferences.get(user_id, {}).get('upload_mode', 'auto')
    
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
            
            if tmdb_data and tmdb_data.get("poster_path"):
                tmdb_thumb_path = f"./tmdb_cache/{user_id}_{int(time.time())}.jpg"
                await download_tmdb_poster(tmdb_data.get("poster_path"), tmdb_thumb_path)
    
    filepath, error = await download_file(url, filename, status_msg)
    
    if error:
        await status_msg.edit_text(f"❌ {error}")
        return
    
    thumb_path = None
    if tmdb_thumb_path and os.path.exists(tmdb_thumb_path):
        thumb_path = tmdb_thumb_path
    elif user_id in thumbnail_storage:
        thumb_path = thumbnail_storage[user_id]
    
    try:
        await status_msg.edit_text("⬆️ Uploading to Telegram...")
        
        file_size = os.path.getsize(filepath)
        
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
            caption = f"**📁 File:** `{filename}`\n**📦 Size:** {file_size / (1024*1024):.2f} MB"
        
        async def upload_progress(current, total):
            await progress_callback(current, total, status_msg, "⬆️ Uploading...")
        
        # Determine upload type based on mode and file type
        should_upload_as_video = False
        
        if upload_mode == 'video':
            should_upload_as_video = True
        elif upload_mode == 'auto':
            should_upload_as_video = is_video_file(filename)
        # If mode is 'document', keep should_upload_as_video = False
        
        # Upload based on determined type
        if should_upload_as_video:
            await client.send_video(
                chat_id=message.chat.id,
                video=filepath,
                thumb=thumb_path,
                caption=caption,
                supports_streaming=True,
                progress=upload_progress
            )
        else:
            await client.send_document(
                chat_id=message.chat.id,
                document=filepath,
                thumb=thumb_path,
                caption=caption,
                progress=upload_progress
            )
        
        await status_msg.delete()
        
        if user_id not in user_preferences:
            user_preferences[user_id] = {'downloads': 0, 'total_size': 0}
        user_preferences[user_id]['downloads'] = user_preferences[user_id].get('downloads', 0) + 1
        user_preferences[user_id]['total_size'] = user_preferences[user_id].get('total_size', 0) + file_size
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
    
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
        if tmdb_thumb_path and os.path.exists(tmdb_thumb_path):
            os.remove(tmdb_thumb_path)

# ===== MAIN FUNCTION =====
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 STARTING TELEGRAM LEECH BOT")
    print("=" * 50)
    
    # Start web server in background thread
    print("📡 Starting web server...")
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # Give web server a moment to start
    time.sleep(2)
    print("✅ Web server running")
    
    # Start Telegram bot (this blocks and keeps running)
    print("🤖 Starting Telegram bot...")
    print("⏳ Connecting to Telegram...")
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
