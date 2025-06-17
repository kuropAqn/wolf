# -*- coding: utf-8 -*-
import os
import discord
from discord.ext import commands, tasks
from discord import ui
import asyncio
from datetime import datetime
import json
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- ユーザーデータ（VC連携用） ---
USERS = {}
LEVEL_XP = {i: 100 for i in range(1, 11)}
for lv in range(11, 81):
    LEVEL_XP[lv] = round(40 * (1.045 ** (lv - 10)))
for lv in range(81, 101):
    LEVEL_XP[lv] = round(668 * (1.08 ** (lv - 80)))

# --- サーバー設定ファイル ---
SETTINGS_FILE = "guild_settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

# --- 起動時処理 ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    vc_tracker.start()

    for guild in bot.guilds:
        settings = load_settings()
        guild_id = str(guild.id)
        if guild_id not in settings or not settings[guild_id].get("admin_user_ids"):
            channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
            if channel:
                view = AdminInitView(guild.id)
                await channel.send("🔧 初期管理者を設定してください：", view=view)

# --- VC参加・切断処理 ---
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

# --- 経験値加算とレベルアップ ---
async def add_xp(member, minutes):
    uid = str(member.id)
    USERS.setdefault(uid, {"xp": 0, "level": 1, "titles": [], "spas": 0})
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
        if user["level"] in [10, 15, 20]:
            await member.send("新しい称号が取得可能です！ !titles で確認して選択してね。")

# --- VCトラッカー定期実行 ---
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

# --- 稼働中のステータス確認 ---
@bot.command()
async def status(ctx):
    uid = str(ctx.author.id)
    data = USERS.get(uid)
    if not data:
        await ctx.send("データが登録されていません。VC参加後に自動で記録されます。")
    else:
        await ctx.send(f"レベル: {data['level']} | XP: {data['xp']} | SPAS$: {data['spas']}")

@bot.command()
async def titles(ctx):
    uid = str(ctx.author.id)
    titles = USERS.get(uid, {}).get("titles", [])
    if not titles:
        await ctx.send("現在称号を保有していません。")
    else:
        await ctx.send(f"保有称号: {', '.join(titles)}")

# --- 管理者初期設定専用ビュー ---
class AdminInitSelect(ui.UserSelect):
    def __init__(self, guild_id):
        super().__init__(placeholder="Bot管理者を選択", min_values=1, max_values=3)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        settings = load_settings()
        settings[str(self.guild_id)] = settings.get(str(self.guild_id), {})
        user_ids = [user.id for user in self.values]
        settings[str(self.guild_id)]["admin_user_ids"] = user_ids
        save_settings(settings)
        await interaction.response.send_message(
            f"✅ 管理者を設定しました：{', '.join(user.name for user in self.values)}", ephemeral=True
        )
        self.view.stop()

class AdminInitView(ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.add_item(AdminInitSelect(guild_id))

# --- 出力チャンネル選択 ---
class ChannelSelect(ui.ChannelSelect):
    def __init__(self, guild_id):
        super().__init__(placeholder="出力チャンネルを選択", channel_types=[discord.ChannelType.text])
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        settings = load_settings()
        settings[str(self.guild_id)] = settings.get(str(self.guild_id), {})
        admin_ids = settings[str(self.guild_id)].get("admin_user_ids", [])
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("⚠ あなたには設定権限がありません。", ephemeral=True)
            return
        settings[str(self.guild_id)]["output_channel_id"] = self.values[0].id
        save_settings(settings)
        await interaction.response.send_message(f"✅ 出力チャンネルを <#{self.values[0].id}> に設定しました。", ephemeral=True)

# --- 管理者設定メニュー ---
class AdminSelect(ui.UserSelect):
    def __init__(self, guild_id):
        super().__init__(placeholder="Bot管理者を再設定", min_values=1, max_values=3)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        settings = load_settings()
        if interaction.user.id not in settings[str(self.guild_id)].get("admin_user_ids", []):
            await interaction.response.send_message("⚠ 管理者以外は設定できません。", ephemeral=True)
            return
        user_ids = [user.id for user in self.values]
        settings[str(self.guild_id)]["admin_user_ids"] = user_ids
        save_settings(settings)
        await interaction.response.send_message(f"🔧 管理者を再設定しました：{', '.join(user.name for user in self.values)}", ephemeral=True)

# --- 管理用統合ビュー ---
class SetupView(ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.add_item(ChannelSelect(guild_id))
        self.add_item(AdminSelect(guild_id))

@bot.command()
async def setup(ctx):
    """Bot設定UIを開きます（管理者のみ）"""
    settings = load_settings()
    guild_id = str(ctx.guild.id)
    admin_ids = settings.get(guild_id, {}).get("admin_user_ids", [])
    if ctx.author.id not in admin_ids:
        await ctx.send("⚠ あなたにはこの操作を行う権限がありません。")
        return
    view = SetupView(ctx.guild.id)
    await ctx.send("管理メニュー：", view=view)

bot.run(TOKEN)
