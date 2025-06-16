import discord
from discord.ext import commands, tasks
from discord.utils import get
import asyncio
from datetime import datetime
import os
import json

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- データベース（仮） ---
USERS = {}  # user_id: {"xp": int, "level": int, "titles": [], "spas": int, "active_vc": timestamp}
LEVEL_XP = {i: 100 for i in range(1, 11)}
for lv in range(11, 81):
    LEVEL_XP[lv] = round(40 * (1.045 ** (lv - 10)))
for lv in range(81, 101):
    LEVEL_XP[lv] = round(668 * (1.08 ** (lv - 80)))

# --- イベントハンドラ ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    vc_tracker.start()

@bot.event
async def on_voice_state_update(member, before, after):
    uid = str(member.id)
    now = datetime.utcnow()
    if before.channel is None and after.channel is not None:
        USERS.setdefault(uid, {"xp": 0, "level": 1, "titles": [], "spas": 0})
        USERS[uid]["active_vc"] = now.timestamp()
    elif before.channel is not None and after.channel is None:
        if uid in USERS and USERS[uid].get("active_vc"):
            duration = now.timestamp() - USERS[uid]["active_vc"]
            if duration >= 60:
                minutes = int(duration // 60)
                await add_xp(member, minutes)
            USERS[uid]["active_vc"] = None

# --- XP加算とレベルアップ処理 ---
async def add_xp(member, minutes):
    uid = str(member.id)
    USERS[uid]["xp"] += minutes
    await check_level_up(member)

async def check_level_up(member):
    uid = str(member.id)
    user = USERS[uid]
    while user["level"] in LEVEL_XP and user["xp"] >= LEVEL_XP[user["level"]]:
        user["xp"] -= LEVEL_XP[user["level"]]
        user["level"] += 1
        user["spas"] += 10
        await member.send(f"🎉 レベル{user['level']}にアップ！SPAS$を10獲得しました。")
        if user["level"] in [10, 15, 20]:  # 称号取得通知（仮）
            await member.send("新しい称号が取得可能です！ !titles で確認して選択してね。")

# --- VCトラッキング確認（定期チェック） ---
@tasks.loop(minutes=1)
async def vc_tracker():
    now = datetime.utcnow()
    for uid, data in USERS.items():
        if data.get("active_vc"):
            duration = now.timestamp() - data["active_vc"]
            if duration >= 60:
                member = await bot.fetch_user(int(uid))
                minutes = int(duration // 60)
                await add_xp(member, minutes)
                USERS[uid]["active_vc"] = now.timestamp()

# --- コマンド：称号一覧表示（仮） ---
@bot.command()
async def titles(ctx):
    uid = str(ctx.author.id)
    titles = USERS.get(uid, {}).get("titles", [])
    if not titles:
        await ctx.send("現在称号を保有していません。")
    else:
        await ctx.send(f"保有称号: {', '.join(titles)}")

# --- コマンド：現在XPとレベル表示 ---
@bot.command()
async def status(ctx):
    uid = str(ctx.author.id)
    data = USERS.get(uid)
    if not data:
        await ctx.send("データが登録されていません。VC参加後に自動で記録されます。")
    else:
        await ctx.send(f"レベル: {data['level']} | XP: {data['xp']} | SPAS$: {data['spas']}")

# --- 起動 ---
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
bot.run(TOKEN)

