import discord
from discord.ext import commands
import json
import os
import asyncio
from datetime import datetime, timedelta
import random
from database import (
    init_database, add_authenticated_user, is_user_authenticated,
    get_user_achievements, add_achievement, get_user_credits, update_user_credits,
    get_vending_items, add_vending_item, update_vending_item, delete_vending_item,
    add_ticket, get_ticket, get_open_tickets, add_ticket_message, save_data,
    achievements_data, user_credits, vending_machine_items, active_tickets, authenticated_users
)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.tree.copy_global_to(guild=discord.Object(id=1194344785223874590))

@bot.event
async def on_ready():
    print(f'{bot.user} がログインしました！')
    init_database()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

# 認証システム
@bot.tree.command(name='認証', description='ユーザー認証（ボタンインタラクション）')
async def authenticate(interaction: discord.Interaction):
    """ユーザー認証（ボタンインタラクション）"""
    embed = discord.Embed(
        title="🔐 ユーザー認証",
        description="下のボタンを押して認証を完了してください。\n認証後、指定されたロールが付与されます。",
        color=0x0099ff
    )

    view = AuthenticationView()
    await interaction.response.send_message(embed=embed, view=view)

def require_auth():
    def predicate(ctx):
        return is_user_authenticated(ctx.author.id)
    return commands.check(predicate)

# 実績記入システム
@bot.command(name='実績記入')
@require_auth()
async def add_achievement(ctx, *, achievement_text: str):
    """実績を記入する"""
    user_id = str(ctx.author.id)
    if user_id not in achievements_data:
        achievements_data[user_id] = []

    achievement = {
        "text": achievement_text,
        "date": datetime.now().isoformat(),
        "user": ctx.author.display_name
    }

    achievements_data[user_id].append(achievement)
    save_data()

    embed = discord.Embed(title="実績記入完了", color=0x00ff00)
    embed.add_field(name="実績内容", value=achievement_text, inline=False)
    embed.add_field(name="記入日時", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)

    await ctx.send(embed=embed)

# 実績送信システム
@bot.command(name='実績送信')
@require_auth()
async def send_achievements(ctx, user: discord.Member = None):
    """実績を送信する"""
    target_user = user if user else ctx.author
    user_id = str(target_user.id)

    if user_id not in achievements_data or not achievements_data[user_id]:
        await ctx.send(f"{target_user.display_name} の実績はまだありません。")
        return

    embed = discord.Embed(title=f"{target_user.display_name} の実績一覧", color=0x0099ff)

    for i, achievement in enumerate(achievements_data[user_id][-10:], 1):  # 最新10件
        date = datetime.fromisoformat(achievement["date"]).strftime("%Y-%m-%d %H:%M")
        embed.add_field(
            name=f"実績 #{i}",
            value=f"{achievement['text']}\n📅 {date}",
            inline=False
        )

    await ctx.send(embed=embed)

# メッセージ全削除システム
@bot.command(name='全削除')
@require_auth()
@commands.has_permissions(manage_messages=True)
async def delete_all_messages(ctx, limit: int = 100):
    """指定チャンネルのメッセージを全て削除"""
    confirm_embed = discord.Embed(
        title="⚠️ 警告",
        description=f"このチャンネルの最新{limit}件のメッセージを削除しますか？\n✅ をクリックして確認してください。",
        color=0xff0000
    )

    confirm_msg = await ctx.send(embed=confirm_embed)
    await confirm_msg.add_reaction('✅')
    await confirm_msg.add_reaction('❌')

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ['✅', '❌'] and reaction.message.id == confirm_msg.id

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)

        if str(reaction.emoji) == '✅':
            deleted = await ctx.channel.purge(limit=limit)
            result_embed = discord.Embed(
                title="削除完了",
                description=f"{len(deleted)}件のメッセージを削除しました。",
                color=0x00ff00
            )
            await ctx.send(embed=result_embed, delete_after=5)
        else:
            await ctx.send("削除をキャンセルしました。", delete_after=5)

    except asyncio.TimeoutError:
        await ctx.send("タイムアウトしました。削除をキャンセルします。", delete_after=5)

# 新しい自販機システム

@bot.tree.command(name='newitem', description='新しい商品を自販機に追加')
@commands.has_permissions(administrator=True)
async def add_new_item(interaction: discord.Interaction, アイテム名: str, 価格: int, 在庫: int):
    """新しい商品を自販機に追加（管理者限定）"""
    if 価格 <= 0 or 在庫 <= 0:
        await interaction.response.send_message("❌ 価格と在庫は1以上である必要があります。", ephemeral=True)
        return

    vending_machine_items[アイテム名] = {
        "price": 価格,
        "stock": 在庫,
        "serial_codes": []
    }
    save_data()

    embed = discord.Embed(title="✅ 商品追加完了", color=0x00ff00)
    embed.add_field(name="商品名", value=アイテム名, inline=True)
    embed.add_field(name="価格", value=f"{価格}コイン", inline=True)
    embed.add_field(name="在庫", value=f"{在庫}個", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='add', description='商品にシリアルコードを追加')
@commands.has_permissions(administrator=True)
async def add_serial_codes(interaction: discord.Interaction, アイテム名: str, シリアルコード: str):
    """商品にシリアルコードを追加（管理者限定）"""
    if アイテム名 not in vending_machine_items:
        await interaction.response.send_message(f"❌ 商品「{アイテム名}」が見つかりません。", ephemeral=True)
        return

    # 複数のシリアルコードを処理（1:コード1 2:コード2 形式）
    codes = []
    parts = シリアルコード.split()
    for part in parts:
        if ':' in part:
            codes.append(part.split(':', 1)[1])
        else:
            codes.append(part)

    vending_machine_items[アイテム名]["serial_codes"].extend(codes)
    save_data()

    embed = discord.Embed(title="✅ シリアルコード追加完了", color=0x00ff00)
    embed.add_field(name="商品名", value=アイテム名, inline=True)
    embed.add_field(name="追加されたコード数", value=f"{len(codes)}個", inline=True)
    embed.add_field(name="総コード数", value=f"{len(vending_machine_items[アイテム名]['serial_codes'])}個", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='addcoins', description='ユーザーにコインを追加')
@commands.has_permissions(administrator=True)
async def add_coins(interaction: discord.Interaction, メンバー: discord.Member, コイン数: int):
    """ユーザーにコインを追加（管理者限定）"""
    if コイン数 <= 0:
        await interaction.response.send_message("❌ コイン数は1以上である必要があります。", ephemeral=True)
        return

    user_id = str(メンバー.id)
    user_credits[user_id] = user_credits.get(user_id, 0) + コイン数
    save_data()

    embed = discord.Embed(title="💰 コイン追加完了", color=0x00ff00)
    embed.add_field(name="対象ユーザー", value=メンバー.display_name, inline=True)
    embed.add_field(name="追加コイン", value=f"{コイン数}コイン", inline=True)
    embed.add_field(name="現在の残高", value=f"{user_credits[user_id]}コイン", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='del', description='自販機から商品を削除')
@commands.has_permissions(administrator=True)
async def delete_item(interaction: discord.Interaction, 商品名: str):
    """自販機から商品を削除（管理者限定）"""
    if 商品名 not in vending_machine_items:
        await interaction.response.send_message(f"❌ 商品「{商品名}」が見つかりません。", ephemeral=True)
        return

    del vending_machine_items[商品名]
    save_data()

    embed = discord.Embed(title="🗑️ 商品削除完了", color=0xff0000)
    embed.add_field(name="削除された商品", value=商品名, inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='change', description='商品の価格を変更')
@commands.has_permissions(administrator=True)
async def change_price(interaction: discord.Interaction, 商品名: str, 新しい価格: int):
    """商品の価格を変更（管理者限定）"""
    if 商品名 not in vending_machine_items:
        await interaction.response.send_message(f"❌ 商品「{商品名}」が見つかりません。", ephemeral=True)
        return

    if 新しい価格 <= 0:
        await interaction.response.send_message("❌ 価格は1以上である必要があります。", ephemeral=True)
        return

    old_price = vending_machine_items[商品名]["price"]
    vending_machine_items[商品名]["price"] = 新しい価格
    save_data()

    embed = discord.Embed(title="💱 価格変更完了", color=0x00ff99)
    embed.add_field(name="商品名", value=商品名, inline=True)
    embed.add_field(name="変更前", value=f"{old_price}コイン", inline=True)
    embed.add_field(name="変更後", value=f"{新しい価格}コイン", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='help', description='コマンド一覧を表示')
async def help_command_en(interaction: discord.Interaction):
    """コマンド一覧を表示（英語版）"""
    embed = discord.Embed(title="🤖 Bot コマンド一覧", color=0x9932cc)

    embed.add_field(
        name="🔐 認証システム",
        value="`/auth` - ボタンを押してユーザー認証とロール付与",
        inline=False
    )

    embed.add_field(
        name="🏆 実績システム",
        value="`/transaction` - 購入実績を指定チャンネルに送信",
        inline=False
    )

    embed.add_field(
        name="🗑️ 管理機能",
        value="`/nuke [件数]` - メッセージを一括削除",
        inline=False
    )

    embed.add_field(
        name="🥤 自販機システム",
        value="`/show` - 自販機を表示\n`/newitem` - 新商品追加（管理者）\n`/add` - シリアルコード追加（管理者）\n`/addcoins` - コイン追加（管理者）\n`/del` - 商品削除（管理者）\n`/change` - 価格変更（管理者）",
        inline=False
    )

    embed.add_field(
        name="🎫 チケットシステム",
        value="`/チケット [問題内容]` - サポートチケット作成\n`/返信 [チケットID] [メッセージ]` - チケットに返信\n`/チケット一覧` - チケット一覧表示",
        inline=False
    )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='transaction', description='購入実績をチャンネルに送信')
async def transaction_record(interaction: discord.Interaction, チャンネル: discord.TextChannel):
    """購入実績をチャンネルに送信"""
    embed = discord.Embed(
        title="🛒 購入実績記録",
        description="購入した商品の実績を記録してください",
        color=0x0099ff
    )

    view = TransactionView(チャンネル, interaction.user)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name='show', description='自販機を表示')
async def show_vending_machine(interaction: discord.Interaction):
    """自販機を表示"""
    if not vending_machine_items:
        await interaction.response.send_message("❌ 現在、販売中の商品はありません。", ephemeral=True)
        return

    embed = discord.Embed(title="🥤 自動販売機", description="購入したい商品のボタンを押してください", color=0x00ff99)

    user_id = str(interaction.user.id)
    balance = user_credits.get(user_id, 0)

    for item_name, item_info in vending_machine_items.items():
        available_codes = len(item_info.get("serial_codes", []))
        embed.add_field(
            name=f"{item_name}",
            value=f"💰 価格: {item_info['price']}コイン\n📦 在庫: {item_info['stock']}個\n🎫 利用可能コード: {available_codes}個",
            inline=True
        )

    embed.add_field(name="💰 あなたの残高", value=f"{balance}コイン", inline=False)

    view = VendingMachineView()
    await interaction.response.send_message(embed=embed, view=view)

class VendingMachineView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for item_name, item_info in list(vending_machine_items.items())[:20]:  # 最大20個のボタン
            button = discord.ui.Button(
                label=f"{item_name} ({item_info['price']}コイン)",
                style=discord.ButtonStyle.primary if item_info['stock'] > 0 else discord.ButtonStyle.secondary,
                disabled=item_info['stock'] <= 0,
                custom_id=f"buy_{item_name}"
            )
            button.callback = self.create_buy_callback(item_name)
            self.add_item(button)

    def create_buy_callback(self, item_name):
        async def buy_callback(interaction: discord.Interaction):
            await self.buy_item(interaction, item_name)
        return buy_callback

    async def buy_item(self, interaction: discord.Interaction, item_name: str):
        user_id = str(interaction.user.id)

        if item_name not in vending_machine_items:
            await interaction.response.send_message("❌ その商品は存在しません。", ephemeral=True)
            return

        item = vending_machine_items[item_name]
        user_balance = user_credits.get(user_id, 0)

        if item["stock"] <= 0:
            await interaction.response.send_message(f"❌ {item_name} は在庫切れです。", ephemeral=True)
            return

        if user_balance < item["price"]:
            await interaction.response.send_message(
                f"❌ 残高が不足しています。\n必要: {item['price']}コイン\n現在: {user_balance}コイン", 
                ephemeral=True
            )
            return

        # シリアルコードがある場合の処理
        serial_code = None
        if item.get("serial_codes") and len(item["serial_codes"]) > 0:
            serial_code = item["serial_codes"].pop(0)  # 最初のコードを取得して削除

        # 購入処理
        user_credits[user_id] = user_balance - item["price"]
        vending_machine_items[item_name]["stock"] -= 1
        save_data()

        # 購入完了メッセージ
        embed = discord.Embed(title="🎉 購入完了", color=0x00ff00)
        embed.add_field(name="商品", value=item_name, inline=True)
        embed.add_field(name="価格", value=f"{item['price']}コイン", inline=True)
        embed.add_field(name="残高", value=f"{user_credits[user_id]}コイン", inline=True)

        if serial_code:
            embed.add_field(name="📨 シリアルコード", value="DMで送信しました", inline=False)

            # DMでシリアルコードを送信
            try:
                dm_embed = discord.Embed(title="🎫 シリアルコード", color=0x00ff99)
                dm_embed.add_field(name="商品名", value=item_name, inline=True)
                dm_embed.add_field(name="シリアルコード", value=f"```{serial_code}```", inline=False)
                dm_embed.set_footer(text="このコードは一度のみ使用可能です。大切に保管してください。")

                await interaction.user.send(embed=dm_embed)
            except discord.Forbidden:
                embed.add_field(name="⚠️ 注意", value="DMの送信に失敗しました。DMを有効にしてください。", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # 自販機の表示を更新
        self.update_buttons()

        # 元のメッセージを更新
        updated_embed = discord.Embed(title="🥤 自動販売機", description="購入したい商品のボタンを押してください", color=0x00ff99)
        user_balance_updated = user_credits.get(user_id, 0)

        for item_name_display, item_info in vending_machine_items.items():
            available_codes = len(item_info.get("serial_codes", []))
            updated_embed.add_field(
                name=f"{item_name_display}",
                value=f"💰 価格: {item_info['price']}コイン\n📦 在庫: {item_info['stock']}個\n🎫 利用可能コード: {available_codes}個",
                inline=True
            )

        updated_embed.add_field(name="💰 あなたの残高", value=f"{user_balance_updated}コイン", inline=False)

        try:
            await interaction.edit_original_response(embed=updated_embed, view=self)
        except:
            pass  # メッセージ更新に失敗した場合は無視

# チケットシステム
@bot.command(name='チケット')
async def create_ticket(ctx, *, issue: str):
    """サポートチケットを作成"""
    ticket_id = f"ticket_{ctx.author.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    ticket_data = {
        "id": ticket_id,
        "user_id": ctx.author.id,
        "user_name": ctx.author.display_name,
        "issue": issue,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "messages": []
    }

    active_tickets[ticket_id] = ticket_data
    save_data()

    embed = discord.Embed(title="🎫 チケット作成完了", color=0x0099ff)
    embed.add_field(name="チケットID", value=ticket_id, inline=False)
    embed.add_field(name="問題内容", value=issue, inline=False)
    embed.add_field(name="ステータス", value="開いています", inline=True)
    embed.set_footer(text="チケットに返信するには: !返信 [チケットID] [メッセージ]")

    await ctx.send(embed=embed)

@bot.command(name='返信')
async def reply_ticket(ctx, ticket_id: str, *, message: str):
    """チケットに返信"""
    if ticket_id not in active_tickets:
        await ctx.send("指定されたチケットが見つかりません。")
        return

    ticket = active_tickets[ticket_id]

    reply_data = {
        "author_id": ctx.author.id,
        "author_name": ctx.author.display_name,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }

    ticket["messages"].append(reply_data)
    save_data()

    embed = discord.Embed(title="📝 チケット返信", color=0x00ff00)
    embed.add_field(name="チケットID", value=ticket_id, inline=False)
    embed.add_field(name="返信者", value=ctx.author.display_name, inline=True)
    embed.add_field(name="メッセージ", value=message, inline=False)

    await ctx.send(embed=embed)

@bot.command(name='チケット一覧')
@require_auth()
async def list_tickets(ctx):
    """チケット一覧を表示"""
    if not active_tickets:
        await ctx.send("現在、アクティブなチケットはありません。")
        return

    embed = discord.Embed(title="🎫 アクティブなチケット一覧", color=0x0099ff)

    for ticket_id, ticket in active_tickets.items():
        if ticket["status"] == "open":
            created_date = datetime.fromisoformat(ticket["created_at"]).strftime("%Y-%m-%d %H:%M")
            embed.add_field(
                name=ticket_id,
                value=f"作成者: {ticket['user_name']}\n問題: {ticket['issue'][:50]}...\n作成日: {created_date}",
                inline=False
            )

    await ctx.send(embed=embed)

@bot.tree.command(name='ヘルプ', description='コマンド一覧を表示')
async def help_command(interaction: discord.Interaction):
    """コマンド一覧を表示"""
    embed = discord.Embed(title="🤖 Bot コマンド一覧", color=0x9932cc)

    embed.add_field(
        name="🔐 認証システム",
        value="`/auth` - ボタンを押してユーザー認証とロール付与",
        inline=False
    )

    embed.add_field(
        name="🏆 実績システム",
        value="`/transaction` - 購入実績を指定チャンネルに送信",
        inline=False
    )

    embed.add_field(
        name="🗑️ 管理機能",
        value="`/nuke [件数]` - メッセージを一括削除",
        inline=False
    )

    embed.add_field(
        name="🥤 自販機システム",
        value="`/show` - 自販機を表示\n`/newitem` - 新商品追加（管理者）\n`/add` - シリアルコード追加（管理者）\n`/addcoins` - コイン追加（管理者）\n`/del` - 商品削除（管理者）\n`/change` - 価格変更（管理者）",
        inline=False
    )

    embed.add_field(
        name="🎫 チケットシステム",
        value="`/チケット [問題内容]` - サポートチケット作成\n`/返信 [チケットID] [メッセージ]` - チケットに返信\n`/チケット一覧` - チケット一覧表示",
        inline=False
    )

    await interaction.response.send_message(embed=embed)

# エラーハンドリング
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ このコマンドを使用するには認証が必要です。`/認証` で認証してください。")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ このコマンドを実行する権限がありません。")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ 必要な引数が不足しています。`/ヘルプ` でコマンドの使い方を確認してください。")
    else:
        await ctx.send(f"❌ エラーが発生しました: {str(error)}")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ エラーが発生しました: {str(error)}", ephemeral=True)

class AuthenticationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)  # 5分でタイムアウト

    @discord.ui.button(label='認証する', style=discord.ButtonStyle.green, emoji='✅')
    async def authenticate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 認証処理
        authenticated_users.add(interaction.user.id)

        # ロール付与（ここでロール名を指定）
        role_name = "認証済みユーザー"  # 付与したいロール名
        guild = interaction.guild
        role = discord.utils.get(guild.roles, name=role_name)

        if role:
            try:
                await interaction.user.add_roles(role)
                role_message = f"\n🎭 ロール「{role_name}」を付与しました。"
            except discord.Forbidden:
                role_message = f"\n⚠️ ロール「{role_name}」の付与に失敗しました（権限不足）。"
        else:
            role_message = f"\n⚠️ ロール「{role_name}」が見つかりません。"

        embed = discord.Embed(
            title="✅ 認証完了",
            description=f"{interaction.user.mention} の認証が完了しました！{role_message}",
            color=0x00ff00
        )

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label='キャンセル', style=discord.ButtonStyle.red, emoji='❌')
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ 認証キャンセル",
            description="認証がキャンセルされました。",
            color=0xff0000
        )

        await interaction.response.edit_message(embed=embed, view=None)

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

class TransactionView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, user: discord.User):
        super().__init__(timeout=300)
        self.channel = channel
        self.user = user

    @discord.ui.button(label='実績を記録', style=discord.ButtonStyle.primary, emoji='📝')
    async def record_transaction(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ あなたはこの操作を実行できません。", ephemeral=True)
            return

        modal = TransactionModal(self.channel)
        await interaction.response.send_modal(modal)

class TransactionModal(discord.ui.Modal):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(title="購入実績記録")
        self.channel = channel

    商品名 = discord.ui.TextInput(
        label="購入した商品名",
        placeholder="例: プレミアムアカウント",
        required=True,
        max_length=100
    )

    価格 = discord.ui.TextInput(
        label="購入価格",
        placeholder="例: 1000コイン",
        required=True,
        max_length=50
    )

    詳細 = discord.ui.TextInput(
        label="購入詳細・感想",
        placeholder="例: とても満足しています",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 購入実績",
            color=0x00ff99,
            timestamp=datetime.now()
        )

        embed.add_field(name="👤 購入者", value=interaction.user.mention, inline=True)
        embed.add_field(name="🛍️ 商品名", value=self.商品名.value, inline=True)
        embed.add_field(name="💰 価格", value=self.価格.value, inline=True)

        if self.詳細.value:
            embed.add_field(name="📝 詳細・感想", value=self.詳細.value, inline=False)

        embed.set_footer(text="購入実績システム", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

        try:
            await self.channel.send(embed=embed)
            await interaction.response.send_message(
                f"✅ 購入実績を {self.channel.mention} に送信しました！",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ {self.channel.mention} への送信権限がありません。",
                ephemeral=True
            )

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