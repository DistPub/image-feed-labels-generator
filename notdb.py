import sqlite3
from argparse import ArgumentParser
import os

import requests


def action_in_progress(token):
    url = 'https://api.github.com/repos/DistPub/image-feed-labels-generator/actions/runs'
    path = 'notdb_gen.yml'
    response = requests.get(url, headers={
        'Authorization': f'token {token}'
    }, params={'status': 'in_progress'})
    data = response.json()
    status_mismatch_ids = [
        13811086833,
        13810761455,
    ]
    runs = [item for item in data['workflow_runs'] if item['path'].endswith(path) and item['id'] not in status_mismatch_ids]
    if len(runs) < 2:
        return False

    return True


def fetch_list(cursor = None):
    """
    smite's list now only contains the not-good user, so direct scan all records
    """
    url = f'https://network.hukoubook.com/xrpc/com.atproto.repo.listRecords'
    response = requests.get(url, params={'repo': 'did:web:smite.hukoubook.com', 'collection': 'app.bsky.graph.listitem', 'limit': 100, 'cursor': cursor})
    data = response.json()
    dids = [item['value']['subject'] for item in data['records']]
    cursor = data.get('cursor')
    if cursor:
        dids.extend(fetch_list(cursor))

    return dids


def git_commit():
    os.system('git config --global user.email "xiaopengyou@live.com"')
    os.system('git config --global user.name "robot auto"')
    os.system('git add .')
    os.system('git commit -m "update not.db"')


def git_push():
    os.system('git push')


def main(dev, token):
    if not dev and action_in_progress(token):
        print(f'action in progress, skip')
        return

    # 连接到数据库（如果不存在则创建）
    conn = sqlite3.connect("not.db")

    # 创建一个游标对象，用于执行 SQL 语句
    cursor = conn.cursor()

    # get old
    cursor.execute("SELECT did FROM not_good_user")
    did_rows = cursor.fetchall()
    cursor.execute("SELECT hostname FROM not_chinese_website")
    hostname_rows = cursor.fetchall()

    # fetch pastebin for not chinese website
    response = requests.get('https://pastebin.smitechow.com/~notcnweb')
    data = response.json()
    new_hostname_rows = [(x,) for x in data]

    add_hostname = set(new_hostname_rows) - set(hostname_rows)
    removed_hostname = set(hostname_rows) - set(new_hostname_rows)

    # fetch @smitechow.com list for not good user
    not_good_users = fetch_list()
    new_did_rows = [(x,) for x in not_good_users]

    add_did = set(new_did_rows) - set(did_rows)
    removed_did = set(did_rows) - set(new_did_rows)

    if not add_hostname and not removed_hostname and not add_did and not removed_did:
        print(f'not changed, skip update not.db')
        cursor.close()
        conn.close()
        return

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
    print(f'update not chinese website {len(data)}')
    cursor.executemany('''INSERT INTO not_chinese_website (hostname) VALUES (?)''', new_hostname_rows)
    conn.commit()

    print(f'update not good user {len(not_good_users)}')
    cursor.executemany('''INSERT INTO not_good_user (did) VALUES (?)''', new_did_rows)
    conn.commit()

    # 关闭数据库
    cursor.close()
    conn.close()
    print(f'not.db updated')

    if not dev:
        git_commit()
        git_push()


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--gh-token", help="gh token")
    args = parser.parse_args()
    main(args.dev, args.gh_token)
