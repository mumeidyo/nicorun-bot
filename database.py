import json
import os
from datetime import datetime

# メモリベースのデータストレージ
achievements_data = {}
user_credits = {}
vending_machine_items = {}
active_tickets = {}
authenticated_users = set()

def init_database():
    """データベースの初期化 - メモリベース"""
    global achievements_data, user_credits, vending_machine_items, active_tickets, authenticated_users
    print("メモリベースデータベースを初期化しました")

def get_user_achievements(user_id):
    """ユーザーの実績を取得"""
    return achievements_data.get(str(user_id), [])

def add_achievement(user_id, text, user_name):
    """実績を追加"""
    user_id = str(user_id)
    if user_id not in achievements_data:
        achievements_data[user_id] = []

    achievement = {
        "text": text,
        "date": datetime.now().isoformat(),
        "user": user_name
    }
    achievements_data[user_id].append(achievement)

def get_user_credits(user_id):
    """ユーザーのクレジットを取得"""
    return user_credits.get(str(user_id), 0)

def update_user_credits(user_id, credits):
    """ユーザーのクレジットを更新"""
    user_credits[str(user_id)] = credits

def get_vending_items():
    """自販機アイテムを取得"""
    return vending_machine_items.copy()

def add_vending_item(item_name, price, stock):
    """自販機アイテムを追加"""
    vending_machine_items[item_name] = {
        "price": price,
        "stock": stock,
        "serial_codes": []
    }

def update_vending_item(item_name, price=None, stock=None, serial_codes=None):
    """自販機アイテムを更新"""
    if item_name in vending_machine_items:
        if price is not None:
            vending_machine_items[item_name]["price"] = price
        if stock is not None:
            vending_machine_items[item_name]["stock"] = stock
        if serial_codes is not None:
            vending_machine_items[item_name]["serial_codes"] = serial_codes

def delete_vending_item(item_name):
    """自販機アイテムを削除"""
    if item_name in vending_machine_items:
        del vending_machine_items[item_name]

def add_authenticated_user(user_id):
    """認証済みユーザーを追加"""
    authenticated_users.add(user_id)

def is_user_authenticated(user_id):
    """ユーザーが認証済みかチェック"""
    return user_id in authenticated_users

def add_ticket(ticket_id, user_id, user_name, issue):
    """チケットを追加"""
    active_tickets[ticket_id] = {
        "id": ticket_id,
        "user_id": user_id,
        "user_name": user_name,
        "issue": issue,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "messages": []
    }

def get_ticket(ticket_id):
    """チケットを取得"""
    return active_tickets.get(ticket_id)

def get_open_tickets():
    """オープンなチケットを取得"""
    return {tid: ticket for tid, ticket in active_tickets.items() if ticket["status"] == "open"}

def add_ticket_message(ticket_id, author_id, author_name, message):
    """チケットにメッセージを追加"""
    if ticket_id in active_tickets:
        active_tickets[ticket_id]["messages"].append({
            "author_id": author_id,
            "author_name": author_name,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })

# 後方互換性のための関数
def save_data():
    """データ保存（メモリベースでは何もしない）"""
    pass