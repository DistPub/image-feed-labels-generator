import os
import sqlite3
from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


def action_in_progress(token):
    url = (
        "https://api.github.com/repos/DistPub/image-feed-labels-generator/actions/runs"
    )
    path = "notdb_gen.yml"
    response = requests.get(
        url,
        headers={"Authorization": f"token {token}"},
        params={"status": "in_progress"},
    )
    data = response.json()
    status_mismatch_ids = [
        13811086833,
        13810761455,
    ]
    runs = [
        item
        for item in data["workflow_runs"]
        if item["path"].endswith(path) and item["id"] not in status_mismatch_ids
    ]
    if len(runs) < 2:
        return False

    return True


def chunked(data, size):
    for start in range(0, len(data), size):
        yield data[start : min(start + size, len(data))]


@retry(
    stop=stop_after_attempt(3),                    # Stop after 3 attempts
    wait=wait_exponential(multiplier=1, min=2, max=10),  # Exponential backoff: 2s, 4s, 8s...
    retry=retry_if_exception_type(requests.exceptions.JSONDecodeError),  # Only retry on JSON decode errors
    reraise=True                                   # Raise the original exception after retries exhausted
)
def fetch_profiles(dids):
    response = requests.get(
        "https://fatesky.hukoubook.com/xrpc/app.bsky.actor.getProfiles",
        params={"actors": dids},
        headers={"atproto-accept-labelers": "did:web:cgv.hukoubook.com"},
        timeout=(30, 120),
    )
    data = response.json()
    return data["profiles"]


def compute_deactive_label(dt):
    now_utc = datetime.now(timezone.utc)
    delta = timedelta(days=30)
    if (now_utc - dt) > delta:
        return "30d-deactive"
    return "active"


def get_rkey(fs):
    rs = fs.split("app.bsky.graph.listitem/")
    return rs[-1]


@retry(
    stop=stop_after_attempt(3),                    # Stop after 3 attempts
    wait=wait_exponential(multiplier=1, min=2, max=10),  # Exponential backoff: 2s, 4s, 8s...
    retry=retry_if_exception_type(requests.exceptions.JSONDecodeError),  # Only retry on JSON decode errors
    reraise=True                                   # Raise the original exception after retries exhausted
)
def fetch_list(cursor=None):
    """
    smite's list now only contains the not-good user, so direct scan all records
    """
    url = f"https://network.hukoubook.com/xrpc/com.atproto.repo.listRecords"
    response = requests.get(
        url,
        params={
            "repo": "did:web:smite.hukoubook.com",
            "collection": "app.bsky.graph.listitem",
            "limit": 100,
            "cursor": cursor,
        },
    )
    data = response.json()
    dids = []
    rkeys = {}
    for item in data["records"]:
        did = item["value"]["subject"]
        dids.append(did)
        rkeys[did] = get_rkey(item["uri"])

    profiles = []
    for pdids in chunked(dids, 25):
        profiles.extend(fetch_profiles(pdids))

    labels = {}
    for profile in profiles:
        # make no sens, at least should conatin not-good label
        # can be error when fatesky query label
        # refetch
        thelabels = profile["labels"]
        if not labels:
            refetch = requests.get(
                "https://fatesky.hukoubook.com/xrpc/app.bsky.actor.getProfile",
                params={"actor": profile["did"]},
                headers={"atproto-accept-labelers": "did:web:cgv.hukoubook.com"},
                timeout=(30, 120),
            )
            refetchdata = refetch.json()
            thelabels = refetchdata["labels"]
        labels[profile["did"]] = [item["val"] for item in thelabels]

        label_time = [
            datetime.strptime(item["cts"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=timezone.utc
            )
            for item in thelabels
        ]

        # still no label, ignore compute deactive label
        if label_time:
            labels[profile["did"]].append(compute_deactive_label(max(label_time)))

    cursor = data.get("cursor")
    if cursor:
        rs = fetch_list(cursor)
        dids.extend(rs[0])
        labels.update(rs[1])
        rkeys.update(rs[2])

    return dids, labels, rkeys


def git_commit():
    os.system('git config --global user.email "xiaopengyou@live.com"')
    os.system('git config --global user.name "robot auto"')
    os.system("git add .")
    os.system('git commit -m "update not.db"')


def git_push():
    os.system("git push")


def main(dev, token, password):
    if not dev and action_in_progress(token):
        print(f"action in progress, skip")
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
    cursor.execute("SELECT topic FROM not_good_topic")
    topic_rows = cursor.fetchall()

    # fetch pastebin for not chinese website
    response = requests.get("https://pastebin.smitechow.com/~notcnweb")
    data = response.json()
    data = list(set(data))
    new_hostname_rows = [(x,) for x in data]

    add_hostname = set(new_hostname_rows) - set(hostname_rows)
    removed_hostname = set(hostname_rows) - set(new_hostname_rows)

    # fetch not good topic
    response = requests.get("https://pastebin.smitechow.com/~not_good_topics")
    data = response.text
    rows = data.split("\n")
    rows = [x for x in rows if x.strip()]
    rows = list(set(rows))
    new_topic_rows = [(x.strip(),) for x in rows]
    add_topic = set(new_topic_rows) - set(topic_rows)
    removed_topic = set(topic_rows) - set(new_topic_rows)

    if add_topic:
        print("new topics added, remove related post")
        response = requests.post(
            "https://feedg.hukoubook.com/xrpc/com.hukoubook.fg.removeTopicPosts",
            json={"topics": [x for (x,) in list(add_topic)]},
        )
        data = response.json()
        print(data)

    # fetch @smitechow.com list for not good user
    not_good_users, user_labels, user_records = fetch_list()
    print(f"there are {len(user_records)} not good user")
    remove_records = []
    cleaned_users = []
    for did in not_good_users:
        need_remove = False

        if did not in user_labels:
            print(f"missing {did}")
            need_remove = True

        elif "nsfw" in user_labels[did] or "30d-deactive" in user_labels[did]:
            print(f"nsfw or 30d-deactive {did}")
            need_remove = True

        if need_remove:
            remove_records.append(
                {
                    "$type": "com.atproto.repo.applyWrites#delete",
                    "collection": "app.bsky.graph.listitem",
                    "rkey": user_records[did],
                }
            )
        else:
            cleaned_users.append(did)
    if remove_records:
        print(f"need remove {len(remove_records)} did from list")
        response = requests.post(
            "https://network.hukoubook.com/xrpc/com.atproto.server.createSession",
            json={"identifier": "did:web:smite.hukoubook.com", "password": password},
        )
        data = response.json()
        for writes in chunked(remove_records, 200):
            print(f"remove writes {writes}")
            requests.post(
                "https://network.hukoubook.com/xrpc/com.atproto.repo.applyWrites",
                json={"repo": "did:web:smite.hukoubook.com", "writes": writes},
                headers={"Authorization": f"Bearer {data['accessJwt']}"},
            )

    new_did_rows = [(x,) for x in list(set(cleaned_users))]

    add_did = set(new_did_rows) - set(did_rows)
    removed_did = set(did_rows) - set(new_did_rows)

    if (
        not add_hostname
        and not removed_hostname
        and not add_did
        and not removed_did
        and not add_topic
        and not removed_topic
    ):
        print(f"not changed, skip update not.db")
        cursor.close()
        conn.close()
        return

    cursor.execute("""DROP TABLE IF EXISTS not_chinese_website""")
    cursor.execute("""DROP TABLE IF EXISTS not_good_user""")
    cursor.execute("""DROP TABLE IF EXISTS not_good_topic""")
    # 创建一个表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS not_chinese_website (
        hostname STRING PRIMARY KEY
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS not_good_user (
        did STRING PRIMARY KEY
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS not_good_topic (
        topic STRING PRIMARY KEY
    )
    """)
    print(f"update not chinese website {len(new_hostname_rows)}")
    cursor.executemany(
        """INSERT INTO not_chinese_website (hostname) VALUES (?)""", new_hostname_rows
    )
    conn.commit()

    print(f"update not good user {len(new_did_rows)}")
    cursor.executemany("""INSERT INTO not_good_user (did) VALUES (?)""", new_did_rows)
    conn.commit()

    print(f"update not good topic {len(new_topic_rows)}")
    cursor.executemany(
        """INSERT INTO not_good_topic (topic) VALUES (?)""", new_topic_rows
    )
    conn.commit()

    # 关闭数据库
    cursor.close()
    conn.close()
    print(f"not.db updated")

    if not dev:
        git_commit()
        git_push()


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--gh-token", help="gh token")
    parser.add_argument("--password", help="password")
    args = parser.parse_args()
    main(args.dev, args.gh_token, args.password)
