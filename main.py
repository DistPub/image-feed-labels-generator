from PIL import Image
from transformers import pipeline


def main():
    img = Image.open("test.jpg")
    classifier = pipeline("image-classification", model="Falconsai/nsfw_image_detection")
    result = classifier(img)
    nsfw_score = next((item['score'] for item in result if item['label'] == 'nsfw'), 0)
    normal_score = next((item['score'] for item in result if item['label'] == 'normal'), 1)
    print(f"图片处理完成: NSFW={nsfw_score:.3f}, Normal={normal_score:.3f}")


if __name__ == '__main__':
    main()