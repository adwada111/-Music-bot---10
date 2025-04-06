import os
import discord
from discord.ext import commands
from discord import ui, ButtonStyle
import yt_dlp
from collections import deque
import asyncio
import re
import logging

# إعداد التسجيل لتتبع الأخطاء
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# التوكن مضاف مباشرة (استبدل هذا بالتوكن الحقيقي الخاص بك)
TOKEN = "MTM1ODMwNzMwNjAyMTg1MTM2Mg.GU2c8h.Ne8usHumJLVvbmm918A9Rg7KQh57PqKylo-gcw"  # ضع توكن البوت الحقيقي هنا

# التحقق من وجود FFmpeg
FFMPEG_PATH = os.path.join(os.path.dirname(__file__), "bin", "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
if not os.path.exists(FFMPEG_PATH):
    logging.error("FFmpeg غير موجود في مجلد bin!")
    exit()

# معرف الروم الصوتي الخاص بهذا البوت (غيّره لكل نسخة)
ALLOWED_VOICE_CHANNEL_ID = 1341677527952785458  # استبدل هذا بمعرف الروم الخاص بكل بوت

# المتغيرات
SONG_QUEUES = {}
CURRENT_SONG = {}
VOICE_CLIENTS = {}
CURRENT_VOLUME = {}

# إعدادات yt-dlp
ydl_opts = {
    "format": "bestaudio",
    "noplaylist": True,
    "quiet": True,
}

# إعداد البوت
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# حدث جاهزية البوت
@bot.event
async def on_ready():
    logging.info(f"{bot.user} متصل الآن!")
    voice_channel = bot.get_channel(ALLOWED_VOICE_CHANNEL_ID)
    if voice_channel and isinstance(voice_channel, discord.VoiceChannel):
        try:
            voice_client = await voice_channel.connect()
            channel_id = str(voice_channel.guild.id) + str(voice_channel.id)
            VOICE_CLIENTS[channel_id] = voice_client
            CURRENT_VOLUME[channel_id] = 0.5  # مستوى الصوت الافتراضي
            logging.info(f"اتصلت بالروم: {voice_channel.name}")
        except Exception as e:
            logging.error(f"فشل الاتصال بالروم الصوتي: {e}")
    else:
        logging.error("الروم غير موجود أو ليس رومًا صوتيًا!")

# التحقق من الرابط
def is_valid_url(url):
    youtube_regex = r"(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})"
    tiktok_regex = r"(https?://)?(www\.)?tiktok\.com/@[^/]+/video/(\d+)"
    return re.match(youtube_regex, url) or re.match(tiktok_regex, url)

# تحويل المدة إلى تنسيق mm:ss
def format_duration(seconds):
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"

# تشغيل الأغنية التالية
async def play_next_song(voice_client, channel_id, text_channel):
    if not voice_client or not voice_client.is_connected():
        logging.warning("البوت غير متصل بأي قناة صوتية!")
        return
    if SONG_QUEUES.get(channel_id):
        audio_url, title, duration = SONG_QUEUES[channel_id].popleft()
        CURRENT_SONG[channel_id] = (audio_url, title, duration)
        try:
            source = discord.FFmpegPCMAudio(audio_url, executable=FFMPEG_PATH)
            source = discord.PCMVolumeTransformer(source, volume=CURRENT_VOLUME.get(channel_id, 0.5))
            voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(voice_client, channel_id, text_channel), bot.loop))
            await text_channel.send(f"🎵 يشتغل الآن: **{title}** (المدة: {format_duration(duration)})")
            await send_control_panel(text_channel, voice_client.guild)
        except Exception as e:
            await text_channel.send(f"❌ خطأ في تشغيل الأغنية: {str(e)}")
            logging.error(f"خطأ في تشغيل الأغنية: {e}")

# استقبال الرسائل
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # التحقق من أن المستخدم في نفس الروم الصوتي الخاص بهذا البوت
    if not message.author.voice or message.author.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
        # لا نرسل أي رسالة إذا لم يكن المستخدم في الروم الخاص بالبوت
        return

    query = message.content.strip()
    url = next((word for word in query.split() if is_valid_url(word)), None)
    if url:
        await message.channel.send("⏳ جاري تحميل الأغنية...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                audio_url = info["url"]
                title = info.get("title", "بدون عنوان")
                duration = info.get("duration", 0)
                channel_id = str(message.guild.id) + str(ALLOWED_VOICE_CHANNEL_ID)
                if channel_id not in SONG_QUEUES:
                    SONG_QUEUES[channel_id] = deque()
                SONG_QUEUES[channel_id].append((audio_url, title, duration))
                voice_client = VOICE_CLIENTS.get(channel_id)
                if voice_client and not voice_client.is_playing() and not voice_client.is_paused():
                    await play_next_song(voice_client, channel_id, message.channel)
                else:
                    await message.channel.send(f"✅ تمت الإضافة للقائمة: **{title}** (المدة: {format_duration(duration)})")
                    await send_control_panel(message.channel, message.guild)
            except Exception as e:
                await message.channel.send("❌ ما قدرت أشغل الأغنية!")
                logging.error(f"خطأ في تحميل الأغنية: {e}")
    await bot.process_commands(message)

# واجهة التحكم المحسنة
async def send_control_panel(channel, guild):
    embed = discord.Embed(
        title="🎧 مركز التحكم الموسيقي",
        description="🎵 استمتع بالتحكم بأناقة وراحة!",
        color=0x1E90FF
    )
    embed.set_author(name=f"{guild.name} Music", icon_url=guild.icon.url if guild.icon else "https://imgur.com/uidOSka.png")
    embed.set_thumbnail(url="https://imgur.com/a/RX8EYpj.png")

    # الأغنية الحالية مع المدة
    current_song_data = CURRENT_SONG.get(str(guild.id) + str(ALLOWED_VOICE_CHANNEL_ID), ('', 'لا شيء يشتغل', 0))
    current_title, current_duration = current_song_data[1], current_song_data[2]
    embed.add_field(
        name="🎵 الأغنية الحالية",
        value=f"**{current_title}** (المدة: {format_duration(current_duration)})",
        inline=False
    )

    # قائمة الانتظار مع المدة
    queue_list = SONG_QUEUES.get(str(guild.id) + str(ALLOWED_VOICE_CHANNEL_ID), [])
    if queue_list:
        queue_text = "\n".join([f"{i+1}. {title} ({format_duration(duration)})" for i, (_, title, duration) in enumerate(list(queue_list)[:5])])
        if len(queue_list) > 5:
            queue_text += f"\n+{len(queue_list) - 5} أغنية أخرى..."
    else:
        queue_text = "لا توجد أغاني في الانتظار!"
    embed.add_field(
        name="📋 قائمة الانتظار",
        value=queue_text,
        inline=False
    )

    # مستوى الصوت
    channel_id = str(guild.id) + str(ALLOWED_VOICE_CHANNEL_ID)
    volume = int(CURRENT_VOLUME.get(channel_id, 0.5) * 100)
    volume_bar = "🔈" + ("█" * (volume // 10)) + ("▁" * (10 - volume // 10)) + "🔊"
    embed.add_field(
        name="🔊 مستوى الصوت",
        value=f"{volume}% | {volume_bar}",
        inline=False
    )

    embed.set_footer(text="Powered by xAI | استمتع بالموسيقى بأسلوب مميز!", icon_url="https://imgur.com/a/RX8EYpj.png")

    view = ui.View(timeout=None)

    # زر التشغيل
    play_button = ui.Button(label="▶️ تشغيل", style=ButtonStyle.green, custom_id="play")
    async def play_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
        voice_client = VOICE_CLIENTS.get(channel_id)
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.edit_message(content="▶️ تم استئناف الأغنية!", embed=embed, view=view)
        else:
            await interaction.response.send_message("ما فيه أغنية موقفة لتشغيلها!", ephemeral=True)
    play_button.callback = play_callback
    view.add_item(play_button)

    # زر الإيقاف المؤقت
    pause_button = ui.Button(label="⏸ إيقاف مؤقت", style=ButtonStyle.grey, custom_id="pause")
    async def pause_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
        voice_client = VOICE_CLIENTS.get(channel_id)
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.edit_message(content="⏸ تم إيقاف الأغنية مؤقتًا!", embed=embed, view=view)
        else:
            await interaction.response.send_message("ما فيه أغنية تشتغل!", ephemeral=True)
    pause_button.callback = pause_callback
    view.add_item(pause_button)

    # زر الإيقاف
    stop_button = ui.Button(label="⏹ إيقاف", style=ButtonStyle.red, custom_id="stop")
    async def stop_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
        voice_client = VOICE_CLIENTS.get(channel_id)
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.edit_message(content="⏹ تم إيقاف الأغنية!", embed=embed, view=view)
        else:
            await interaction.response.send_message("ما فيه أغنية تشتغل!", ephemeral=True)
    stop_button.callback = stop_callback
    view.add_item(stop_button)

    # زر التالي (تخطي)
    next_button = ui.Button(label="⏭ التالي", style=ButtonStyle.blurple, custom_id="next")
    async def next_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
        voice_client = VOICE_CLIENTS.get(channel_id)
        if voice_client and SONG_QUEUES.get(channel_id):
            voice_client.stop()
            await play_next_song(voice_client, channel_id, channel)
            await interaction.response.edit_message(content="⏭ تم تخطي الأغنية!", embed=embed, view=view)
        else:
            await interaction.response.send_message("ما فيه أغاني في القائمة للتخطي!", ephemeral=True)
    next_button.callback = next_callback
    view.add_item(next_button)

    # زر إعادة من البداية
    restart_button = ui.Button(label="🔄 إعادة", style=ButtonStyle.grey, custom_id="restart")
    async def restart_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
        voice_client = VOICE_CLIENTS.get(channel_id)
        if voice_client and voice_client.is_playing() and channel_id in CURRENT_SONG:
            audio_url, title, duration = CURRENT_SONG[channel_id]
            voice_client.stop()
            source = discord.FFmpegPCMAudio(audio_url, executable=FFMPEG_PATH)
            source = discord.PCMVolumeTransformer(source, volume=CURRENT_VOLUME.get(channel_id, 0.5))
            voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(voice_client, channel_id, channel), bot.loop))
            await interaction.response.edit_message(content="🔄 تم إعادة الأغنية من البداية!", embed=embed, view=view)
        else:
            await interaction.response.send_message("ما فيه أغنية تشتغل!", ephemeral=True)
    restart_button.callback = restart_callback
    view.add_item(restart_button)

    # زر تقديم (Fast Forward)
    forward_button = ui.Button(label="⏩ تقديم", style=ButtonStyle.blurple, custom_id="forward")
    async def forward_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
        voice_client = VOICE_CLIENTS.get(channel_id)
        if voice_client and voice_client.is_playing() and channel_id in CURRENT_SONG:
            audio_url, title, duration = CURRENT_SONG[channel_id]
            voice_client.stop()
            source = discord.FFmpegPCMAudio(audio_url, executable=FFMPEG_PATH, options="-ss 10")
            source = discord.PCMVolumeTransformer(source, volume=CURRENT_VOLUME.get(channel_id, 0.5))
            voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(voice_client, channel_id, channel), bot.loop))
            await interaction.response.edit_message(content="⏩ تم تقديم الأغنية 10 ثواني!", embed=embed, view=view)
        else:
            await interaction.response.send_message("ما فيه أغنية تشتغل!", ephemeral=True)
    forward_button.callback = forward_callback
    view.add_item(forward_button)

    # زر تأخير (Rewind)
    rewind_button = ui.Button(label="⏪ تأخير", style=ButtonStyle.blurple, custom_id="rewind")
    async def rewind_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
        voice_client = VOICE_CLIENTS.get(channel_id)
        if voice_client and voice_client.is_playing() and channel_id in CURRENT_SONG:
            audio_url, title, duration = CURRENT_SONG[channel_id]
            voice_client.stop()
            source = discord.FFmpegPCMAudio(audio_url, executable=FFMPEG_PATH)
            source = discord.PCMVolumeTransformer(source, volume=CURRENT_VOLUME.get(channel_id, 0.5))
            voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(voice_client, channel_id, channel), bot.loop))
            await interaction.response.edit_message(content="⏪ تم إرجاع الأغنية للبداية!", embed=embed, view=view)
        else:
            await interaction.response.send_message("ما فيه أغنية تشتغل!", ephemeral=True)
    rewind_button.callback = rewind_callback
    view.add_item(rewind_button)

    # زر رفع الصوت
    volume_up_button = ui.Button(label="🔊 رفع", style=ButtonStyle.green, custom_id="vol_up")
    async def volume_up_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
        voice_client = VOICE_CLIENTS.get(channel_id)
        if voice_client and voice_client.source:
            current_volume = CURRENT_VOLUME.get(channel_id, 0.5)
            new_volume = min(current_volume + 0.1, 1.0)
            CURRENT_VOLUME[channel_id] = new_volume
            voice_client.source.volume = new_volume
            embed.set_field_at(2, name="🔊 مستوى الصوت", value=f"{int(new_volume * 100)}% | {'🔈' + ('█' * (int(new_volume * 10))) + ('▁' * (10 - int(new_volume * 10))) + '🔊'}", inline=False)
            await interaction.response.edit_message(content=f"🔊 الصوت: {int(new_volume * 100)}%", embed=embed, view=view)
        else:
            await interaction.response.send_message("ما فيه أغنية تشتغل لتغيير الصوت!", ephemeral=True)
    volume_up_button.callback = volume_up_callback
    view.add_item(volume_up_button)

    # زر خفض الصوت
    volume_down_button = ui.Button(label="🔉 خفض", style=ButtonStyle.red, custom_id="vol_down")
    async def volume_down_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
        voice_client = VOICE_CLIENTS.get(channel_id)
        if voice_client and voice_client.source:
            current_volume = CURRENT_VOLUME.get(channel_id, 0.5)
            new_volume = max(current_volume - 0.1, 0.0)
            CURRENT_VOLUME[channel_id] = new_volume
            voice_client.source.volume = new_volume
            embed.set_field_at(2, name="🔊 مستوى الصوت", value=f"{int(new_volume * 100)}% | {'🔈' + ('█' * (int(new_volume * 10))) + ('▁' * (10 - int(new_volume * 10))) + '🔊'}", inline=False)
            await interaction.response.edit_message(content=f"🔉 الصوت: {int(new_volume * 100)}%", embed=embed, view=view)
        else:
            await interaction.response.send_message("ما فيه أغنية تشتغل لتغيير الصوت!", ephemeral=True)
    volume_down_button.callback = volume_down_callback
    view.add_item(volume_down_button)

    # زر التكرار
    repeat_button = ui.Button(label="🔁 تكرار", style=ButtonStyle.green, custom_id="repeat")
    async def repeat_callback(interaction):
        if interaction.user.voice.channel.id != ALLOWED_VOICE_CHANNEL_ID:
            return
        await interaction.response.send_message("كم مرة تبي تكرر الأغنية؟ (اكتب رقم)", ephemeral=True)
        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel and m.content.isdigit()
        try:
            msg = await bot.wait_for("message", check=check, timeout=30)
            times = int(msg.content)
            channel_id = str(interaction.guild_id) + str(ALLOWED_VOICE_CHANNEL_ID)
            if channel_id in CURRENT_SONG:
                audio_url, title, duration = CURRENT_SONG[channel_id]
                for _ in range(times):
                    SONG_QUEUES[channel_id].append((audio_url, title, duration))
                await interaction.followup.send(f"🔁 تم تكرار **{title}** {times} مرة!", ephemeral=True)
                await send_control_panel(channel, guild)
            else:
                await interaction.followup.send("ما فيه أغنية تشتغل حاليًا!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("ما كتبت شيء، تم إلغاء التكرار.", ephemeral=True)
    repeat_button.callback = repeat_callback
    view.add_item(repeat_button)

    try:
        await channel.send(embed=embed, view=view)
    except Exception as e:
        logging.error(f"فشل إرسال واجهة التحكم: {e}")

# تشغيل البوت
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logging.error(f"فشل تشغيل البوت: {e}")