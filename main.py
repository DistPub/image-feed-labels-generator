from PIL import Image
from transformers import pipeline
from argparse import ArgumentParser
import io

import requests


def main(mod_api, nsfw_api, report_api, dev):
    response = requests.get(mod_api)
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

    response = requests.post(nsfw_api, json={'categories': did_categories, 'move': True})
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
    args = parser.parse_args()
    main(args.get_mod_api, args.update_nsfw_api, args.get_report_nsfw_api, args.dev)
