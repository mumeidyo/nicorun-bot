import discord
from discord.ext import commands
import json
import os
import asyncio
from datetime import datetime, timedelta
import random

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.tree.copy_global_to(guild=discord.Object(id=1194344785223874590))

# Simple data storage
active_tickets = {}

@bot.event
async def on_ready():
    print(f'{bot.user} がログインしました！')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

# Nuke command (message deletion)
@bot.tree.command(name='nuke', description='指定したチャンネルのメッセージを削除')
@commands.has_permissions(manage_messages=True)
async def nuke_command(interaction: discord.Interaction, 件数: int = 100):
    """指定チャンネルのメッセージを全て削除"""
    if 件数 <= 0 or 件数 > 1000:
        await interaction.response.send_message("❌ 削除件数は1から1000までの間で指定してください。", ephemeral=True)
        return

    confirm_embed = discord.Embed(
        title="⚠️ 警告",
        description=f"このチャンネルの最新{件数}件のメッセージを削除しますか？",
        color=0xff0000
    )

    view = DeleteConfirmView(件数, interaction.user.id)
    await interaction.response.send_message(embed=confirm_embed, view=view, ephemeral=True)

# Ticket system with channel creation
@bot.tree.command(name='チケット', description='サポートチケットを作成（専用チャンネル作成）')
async def create_ticket(interaction: discord.Interaction, 問題内容: str, カテゴリid: str = None):
    """サポートチケットを作成（専用チャンネル作成）"""
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ このコマンドはサーバー内でのみ使用できます。", ephemeral=True)
        return

    # チケット番号を生成
    ticket_number = len(active_tickets) + 1
    channel_name = f"ticket-{ticket_number:04d}-{interaction.user.name}"
    
    # カテゴリを取得
    category = None
    if カテゴリid:
        try:
            category = guild.get_channel(int(カテゴリid))
            if not isinstance(category, discord.CategoryChannel):
                await interaction.response.send_message("❌ 指定されたIDはカテゴリではありません。", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ 無効なカテゴリIDです。", ephemeral=True)
            return

    try:
        # チケットチャンネルを作成
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"チケット作成者: {interaction.user.display_name} | 問題: {問題内容}"
        )

        # チケットデータを保存
        ticket_id = f"ticket_{ticket_channel.id}"
        ticket_data = {
            "id": ticket_id,
            "channel_id": ticket_channel.id,
            "user_id": interaction.user.id,
            "user_name": interaction.user.display_name,
            "issue": 問題内容,
            "status": "open",
            "created_at": datetime.now().isoformat(),
            "messages": []
        }

        active_tickets[ticket_id] = ticket_data

        # チケットチャンネルに初期メッセージを送信
        welcome_embed = discord.Embed(
            title="🎫 チケット作成完了",
            description=f"こんにちは {interaction.user.mention}！\n\nサポートチケットが作成されました。",
            color=0x0099ff
        )
        welcome_embed.add_field(name="問題内容", value=問題内容, inline=False)
        welcome_embed.add_field(name="チケット番号", value=f"#{ticket_number:04d}", inline=True)
        welcome_embed.add_field(name="作成日時", value=datetime.now().strftime("%Y-%m-%d %H:%M"), inline=True)
        welcome_embed.set_footer(text="このチャンネルでサポートスタッフとやり取りできます。チケットを閉じるには /チケット閉じる を使用してください。")

        close_view = TicketCloseView(ticket_id, interaction.user.id)
        await ticket_channel.send(embed=welcome_embed, view=close_view)

        # 元のチャンネルに確認メッセージを送信
        confirm_embed = discord.Embed(
            title="✅ チケット作成完了",
            description=f"チケットチャンネル {ticket_channel.mention} が作成されました。",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message("❌ チャンネル作成の権限がありません。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ チケット作成中にエラーが発生しました: {str(e)}", ephemeral=True)

@bot.tree.command(name='チケット閉じる', description='チケットを閉じる')
async def close_ticket(interaction: discord.Interaction):
    """チケットを閉じる"""
    channel = interaction.channel
    ticket_id = f"ticket_{channel.id}"
    
    if ticket_id not in active_tickets:
        await interaction.response.send_message("❌ このチャンネルはチケットチャンネルではありません。", ephemeral=True)
        return

    ticket = active_tickets[ticket_id]
    
    # チケット作成者またはサーバー管理者のみ閉じることができる
    if interaction.user.id != ticket["user_id"] and not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ このチケットを閉じる権限がありません。", ephemeral=True)
        return

    # チケットステータスを更新
    ticket["status"] = "closed"
    ticket["closed_at"] = datetime.now().isoformat()
    ticket["closed_by"] = interaction.user.display_name

    # 閉じる確認メッセージ
    close_embed = discord.Embed(
        title="🔒 チケットを閉じています...",
        description="このチケットは5秒後に閉じられます。",
        color=0xff9900
    )
    await interaction.response.send_message(embed=close_embed)

    # 5秒待機
    await asyncio.sleep(5)

    try:
        # チャンネルを削除
        await channel.delete(reason=f"チケット閉じる - {interaction.user.display_name}")
        # active_ticketsから削除
        del active_tickets[ticket_id]
    except discord.NotFound:
        pass
    except Exception as e:
        print(f"チケットチャンネル削除エラー: {e}")

@bot.tree.command(name='チケット一覧', description='アクティブなチケット一覧を表示')
async def list_tickets(interaction: discord.Interaction):
    """アクティブなチケット一覧を表示"""
    if not active_tickets:
        await interaction.response.send_message("現在、アクティブなチケットはありません。", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self, ticket_id: str, user_id: int):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.user_id = user_id

    @discord.ui.button(label='チケットを閉じる', style=discord.ButtonStyle.danger, emoji='🔒')
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # チケット作成者またはサーバー管理者のみ閉じることができる
        if interaction.user.id != self.user_id and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ このチケットを閉じる権限がありません。", ephemeral=True)
            return

        ticket = active_tickets.get(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("❌ チケット情報が見つかりません。", ephemeral=True)
            return

        # チケットステータスを更新
        ticket["status"] = "closed"
        ticket["closed_at"] = datetime.now().isoformat()
        ticket["closed_by"] = interaction.user.display_name

        # 閉じる確認メッセージ
        close_embed = discord.Embed(
            title="🔒 チケットを閉じています...",
            description="このチケットは5秒後に閉じられます。",
            color=0xff9900
        )
        await interaction.response.send_message(embed=close_embed)

        # 5秒待機
        await asyncio.sleep(5)

        try:
            # チャンネルを削除
            await interaction.channel.delete(reason=f"チケット閉じる - {interaction.user.display_name}")
            # active_ticketsから削除
            del active_tickets[self.ticket_id]
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"チケットチャンネル削除エラー: {e}")


        return

    embed = discord.Embed(title="🎫 アクティブなチケット一覧", color=0x0099ff)

    ticket_count = 0
    for ticket_id, ticket in active_tickets.items():
        if ticket["status"] == "open":
            ticket_count += 1
            created_date = datetime.fromisoformat(ticket["created_at"]).strftime("%Y-%m-%d %H:%M")
            channel = bot.get_channel(ticket["channel_id"])
            channel_mention = channel.mention if channel else "チャンネルが見つかりません"
            
            embed.add_field(
                name=f"チケット #{ticket_count:04d}",
                value=f"👤 作成者: {ticket['user_name']}\n📝 問題: {ticket['issue'][:50]}{'...' if len(ticket['issue']) > 50 else ''}\n📅 作成日: {created_date}\n🔗 チャンネル: {channel_mention}",
                inline=False
            )

    if ticket_count == 0:
        await interaction.response.send_message("現在、アクティブなチケットはありません。", ephemeral=True)
    else:
        embed.set_footer(text=f"合計 {ticket_count} 件のアクティブなチケット")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name='help', description='利用可能なコマンド一覧を表示')
async def help_command(interaction: discord.Interaction):
    """コマンド一覧を表示"""
    embed = discord.Embed(title="🤖 Bot コマンド一覧", color=0x9932cc)

    embed.add_field(
        name="🗑️ メッセージ削除",
        value="`/nuke [件数]` - 指定した件数のメッセージを削除（管理者限定）",
        inline=False
    )

    embed.add_field(
        name="🎫 チケットシステム",
        value="`/チケット [問題内容] [カテゴリID]` - サポートチケット作成（専用チャンネル作成）\n`/チケット閉じる` - チケットを閉じる\n`/チケット一覧` - アクティブなチケット一覧表示",
        inline=False
    )

    embed.set_footer(text="カテゴリIDはオプションです。指定しない場合はサーバーのトップレベルに作成されます。")

    await interaction.response.send_message(embed=embed)

# Error handling
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ エラーが発生しました: {str(error)}", ephemeral=True)

class DeleteConfirmView(discord.ui.View):
    def __init__(self, limit: int, user_id: int):
        super().__init__(timeout=30)
        self.limit = limit
        self.user_id = user_id

    @discord.ui.button(label='削除実行', style=discord.ButtonStyle.danger, emoji='✅')
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ あなたはこの操作を実行できません。", ephemeral=True)
            return

        try:
            deleted = await interaction.channel.purge(limit=self.limit)
            result_embed = discord.Embed(
                title="削除完了",
                description=f"{len(deleted)}件のメッセージを削除しました。",
                color=0x00ff00
            )
            await interaction.response.edit_message(embed=result_embed, view=None)
        except discord.Forbidden:
            await interaction.response.edit_message(content="❌ メッセージ削除の権限がありません。", view=None)

    @discord.ui.button(label='キャンセル', style=discord.ButtonStyle.secondary, emoji='❌')
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ あなたはこの操作を実行できません。", ephemeral=True)
            return

        embed = discord.Embed(
            title="❌ 削除キャンセル",
            description="メッセージ削除をキャンセルしました。",
            color=0xff0000
        )
        await interaction.response.edit_message(embed=embed, view=None)

# Web サーバー用の追加インポート（Render用）
from threading import Thread
import time

# Render用の簡易Webサーバー（Keep-alive用）
def keep_alive():
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Discord Bot is running!')

        def log_message(self, format, *args):
            pass  # ログを無効化

    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"Web server started on port {port}")
    server.serve_forever()

# Bot起動
if __name__ == "__main__":
    # Discord botトークンを設定してください
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    if not TOKEN:
        print("エラー: DISCORD_BOT_TOKEN環境変数が設定されていません。")
        print("環境変数でDISCORD_BOT_TOKENを設定してください。")
    else:
        # Render用のWebサーバーを別スレッドで起動
        if os.getenv('RENDER'):
            Thread(target=keep_alive, daemon=True).start()

        print("Discord Bot を起動しています...")
        bot.run(TOKEN)
