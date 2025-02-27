from PIL import Image
from transformers import pipeline
from argparse import ArgumentParser
import io

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


s = requests.Session()
retries = Retry(
    total=3,  # 总重试次数
    backoff_factor=1,  # 间隔时间因子，用于计算重试间隔时间
    status_forcelist=[502],
    allowed_methods=["GET", "POST"]  # 允许重试的方法
)
s.mount('http://', HTTPAdapter(max_retries=retries))


def action_in_progress(token):
    url = 'https://api.github.com/repos/DistPub/image-feed-labels-generator/actions/runs'
    path = 'mod.yml'
    response = requests.get(url, headers={
        'Authorization': f'token {token}'
    }, params={'status': 'in_progress'})
    data = response.json()
    if data['total_count'] < 2:
        return False

    runs = [item for item in data['workflow_runs'] if item['path'].endswith(path)]
    if len(runs) < 2:
        return False

    return True


def main(mod_api, nsfw_api, report_api, dev, token):
    if not dev and action_in_progress(token):
        print(f'action in progress, skip')
        return

    response = s.get(mod_api)
    response.raise_for_status()
    posts = response.json()

    if not posts['mod']:
        print(f'no post mod')
        return

    did_images = {}
    for post in posts['mod']:
        # only handle 3 author when dev
        if dev and len(did_images) >=3:
            break
        author = post['author']
        did_images.setdefault(author, [])
        did_images[author].extend(post['imgUrls'].split(','))

    did_categories = []
    for did, imgs in did_images.items():
        print(f'category did: {did} by analysis {len(imgs)} images')
        category = 0

        for img in imgs:
            try:
                if dev:
                    img = img.replace('://', '://go.smitechow.com/')
                response = requests.get(img)
                response.raise_for_status()

                image_data = io.BytesIO(response.content)
                nsfw = check_nsfw(image_data)

                if nsfw:
                    category = 1
                    break
            except Exception as error:
                print(f'fail to category img: {img} error: {error}')
                continue

        did_categories.append({'category': category, 'did': did})

    response = s.post(nsfw_api, json={'categories': did_categories, 'move': True})
    response.raise_for_status()
    data = response.json()
    print(f'send mod result, {data["message"]}')


def check_nsfw(data):
    img = Image.open(data)
    classifier = pipeline("image-classification", model="Falconsai/nsfw_image_detection")
    result = classifier(img)
    nsfw_score = next((item['score'] for item in result if item['label'] == 'nsfw'), 0)
    normal_score = next((item['score'] for item in result if item['label'] == 'normal'), 1)
    return nsfw_score >= normal_score


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("--get-mod-api", help="get mod endpoint", default='http://localhost:3000/xrpc/com.hukoubook.fg.getModImagePosts')
    parser.add_argument("--update-nsfw-api", help="update nsfw category endpoint", default='http://localhost:3000/xrpc/com.hukoubook.fg.updateNSFW')
    parser.add_argument("--get-report-nsfw-api", help="get report nsfw endpoint", default='n/a')
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--gh-token", help="gh token")
    args = parser.parse_args()
    main(args.get_mod_api, args.update_nsfw_api, args.get_report_nsfw_api, args.dev, args.gh_token)
