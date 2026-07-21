import os
import re
import json
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv(override=True)
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

CONFIG_FILE = 'config.json'
user_message_logs = {}
user_violation_counts = {}

def get_config():
    default_config = {
        "spam_interval": 3,
        "spam_threshold": 5,
        "account_age_days": 7,
        "check_default_avatar": True,
        "banned_words": "荒らし, たかし, test_bad_word",
        "log_channel_id": "",
        "auto_punish": "timeout", # "none", "timeout", "ban"
        "timeout_minutes": 10
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return {**default_config, **json.load(f)}
        except Exception:
            pass
    return default_config

async def send_log(guild, embed):
    config = get_config()
    log_id = config.get("log_channel_id")
    if log_id:
        try:
            channel = guild.get_channel(int(log_id))
            if channel:
                await channel.send(embed=embed)
        except ValueError:
            pass

# 処罰（タイムアウト / BAN）を実行する共通関数
async def punish_user(member, reason):
    config = get_config()
    punish_type = config.get("auto_punish", "timeout")
    timeout_mins = config.get("timeout_minutes", 10)
    now = datetime.now(timezone.utc)

    if punish_type == "timeout":
        try:
            duration = timedelta(minutes=timeout_mins)
            await member.timeout(duration, reason=reason)
            
            embed = discord.Embed(title="🔨 タイムアウト実行ログ", color=discord.Color.red(), timestamp=now)
            embed.add_field(name="対象ユーザー", value=f"{member.mention} (`{member.name}`)", inline=False)
            embed.add_field(name="期間", value=f"{timeout_mins} 分間", inline=True)
            embed.add_field(name="理由", value=reason, inline=True)
            await send_log(member.guild, embed)
        except Exception as e:
            print(f"タイムアウト失敗: {e}")

    elif punish_type == "ban":
        try:
            await member.ban(reason=reason, delete_message_seconds=3600)
            
            embed = discord.Embed(title="💥 BAN実行ログ", color=discord.Color.dark_red(), timestamp=now)
            embed.add_field(name="対象ユーザー", value=f"{member.mention} (`{member.name}`)", inline=False)
            embed.add_field(name="理由", value=reason, inline=True)
            await send_log(member.guild, embed)
        except Exception as e:
            print(f"BAN失敗: {e}")

@bot.event
async def on_ready():
    print(f'✅ ログイン成功: {bot.user.name}')
    print('🛡️ 統合管理・自動処罰システム稼働中')

@bot.event
async def on_member_join(member):
    config = get_config()
    now = datetime.now(timezone.utc)
    account_age_days = (now - member.created_at).days

    warnings = []
    limit_days = config.get("account_age_days", 7)
    
    if account_age_days < limit_days:
        warnings.append(f"⚠️ アカウント作成から **{account_age_days}日** しか経過していません")

    if config.get("check_default_avatar") and member.avatar is None:
        warnings.append("⚠️ デフォルトアイコンです")

    if warnings:
        embed = discord.Embed(title="🚨 怪しいアカウントの参加を検知", color=discord.Color.gold(), timestamp=now)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ユーザー", value=f"{member.mention} (`{member.name}`)", inline=False)
        embed.add_field(name="特徴", value="\n".join(warnings), inline=False)
        await send_log(member.guild, embed)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    config = get_config()
    user_id = message.author.id
    now = datetime.now(timezone.utc)

    # 1. 招待リンク検知
    invite_pattern = r"(discord\.gg|discord\.com/invite)/[a-zA-Z0-9]+"
    if re.search(invite_pattern, message.content):
        try:
            await message.delete()
        except discord.NotFound:
            pass
        await message.channel.send(f'⚠️ {message.author.mention} 宣伝・招待リンクの送信は禁止されています！', delete_after=5)
        await punish_user(message.author, "招待リンクの送信")
        return

    # 2. 禁止ワード検知
    banned_words_list = [w.strip() for w in config.get("banned_words", "").split(",") if w.strip()]
    for word in banned_words_list:
        if word in message.content:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            await message.channel.send(f'⚠️ {message.author.mention} 不適切なワードが含まれていたため削除しました。', delete_after=5)
            await punish_user(message.author, f"禁止ワードの使用 ({word})")
            return

    # 3. スパム検知
    spam_interval = config.get("spam_interval", 3)
    spam_threshold = config.get("spam_threshold", 5)

    if user_id not in user_message_logs:
        user_message_logs[user_id] = []

    user_message_logs[user_id] = [
        ts for ts in user_message_logs[user_id]
        if now - ts < timedelta(seconds=spam_interval)
    ]
    user_message_logs[user_id].append(now)

    if len(user_message_logs[user_id]) >= spam_threshold:
        try:
            await message.delete()
        except discord.NotFound:
            pass
        await message.channel.send(f'🚨 {message.author.mention} スパム行為（連投）を検知しました！', delete_after=7)
        user_message_logs[user_id] = []
        await punish_user(message.author, "連投・スパム行為")
        return

    await bot.process_commands(message)

if __name__ == '__main__':
    bot.run(TOKEN)