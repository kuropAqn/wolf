import sqlite3
import datetime
import discord
from discord.ext import commands

bot = commands.Bot(command_prefix="!")

def get_db_connection():
    return sqlite3.connect('bot.db')

@bot.event
async def on_voice_state_update(member, before, after):
    user_id = member.id
    now = datetime.datetime.now().timestamp()
    conn = get_db_connection()
    c = conn.cursor()

    # VC入室
    if not before.channel and after.channel:
        c.execute('REPLACE INTO vc_entries (user_id, entry_time) VALUES (?, ?)', (user_id, now))
        conn.commit()
    # VC退出
    elif before.channel and not after.channel:
        c.execute('SELECT entry_time FROM vc_entries WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        if row:
            entry_time = row[0]
            duration = int(now - entry_time)
            exp_gain = duration // 60  # 1分ごとに1exp
            if exp_gain > 0:
                # ユーザーがいなければ作成
                c.execute('INSERT OR IGNORE INTO users (user_id, exp) VALUES (?, 0)', (user_id,))
                c.execute('UPDATE users SET exp = exp + ? WHERE user_id = ?', (exp_gain, user_id))
                await member.send(f"VC滞在{duration}秒で{exp_gain}EXPを獲得しました！")
            c.execute('DELETE FROM vc_entries WHERE user_id = ?', (user_id,))
            conn.commit()
    conn.close()

# 経験値確認コマンド
@bot.command()
async def exp(ctx):
    user_id = ctx.author.id
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT exp FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    exp = row[0] if row else 0
    await ctx.send(f"{ctx.author.display_name}のEXPは{exp}だ！")
    conn.close()

bot.run('YOUR_TOKEN')
