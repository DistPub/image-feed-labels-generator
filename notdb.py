import sqlite3

import requests


def fetch_list(aturl, cursor = None):
    url = f'https://public.api.bsky.app/xrpc/app.bsky.graph.getList'
    response = requests.get(url, params={'list': aturl, 'limit': 100, 'cursor': cursor})
    data = response.json()
    dids = [item['subject']['did'] for item in data['items']]
    cursor = data.get('cursor')
    if cursor:
        dids.extend(fetch_list(aturl, cursor))

    return dids


def main():
    # 连接到数据库（如果不存在则创建）
    conn = sqlite3.connect("not.db")

    # 创建一个游标对象，用于执行 SQL 语句
    cursor = conn.cursor()
    cursor.execute('''DROP TABLE IF EXISTS not_chinese_website''')
    cursor.execute('''DROP TABLE IF EXISTS not_good_user''')
    # 创建一个表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS not_chinese_website (
        hostname STRING PRIMARY KEY
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS not_good_user (
        did STRING PRIMARY KEY
    )
    ''')

    # fetch pastebin for not chinese website
    response = requests.get('https://pastebin.smitechow.com/~notcnweb')
    data = response.json()
    cursor.executemany('''INSERT INTO not_chinese_website (hostname) VALUES (?)''', [(item,) for item in data])
    conn.commit()

    # fetch @smitechow.com list for not good user
    list_keys = [
        'at://did:web:smite.hukoubook.com/app.bsky.graph.list/3li4glzdchy2r', # 成功暴富爱好者
        'at://did:web:smite.hukoubook.com/app.bsky.graph.list/3li4d2wvyny2r', # 黄赌毒从业者
        'at://did:web:smite.hukoubook.com/app.bsky.graph.list/3li4bgpci5i2r', # 玄学爱好者
        'at://did:web:smite.hukoubook.com/app.bsky.graph.list/3li4b326e5y2r', # 键政爱好者
        'at://did:web:smite.hukoubook.com/app.bsky.graph.list/3lbfa5esptk2s', # 高音喇叭
    ]

    not_good_users = []
    for list_key in list_keys:
        not_good_users.extend(fetch_list(list_key))

    cursor.executemany('''INSERT INTO not_good_user (did) VALUES (?)''', [(item,) for item in not_good_users])
    
    # 关闭数据库
    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
