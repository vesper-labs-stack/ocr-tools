"""Generate a deterministic synthetic screenshot without user data."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def generate(output=Path('qa-output/screenshot-sample.png'), second=False):
    output = Path(output)
    output.parent.mkdir(exist_ok=True, parents=True)
    image = Image.new('RGB', (1100, 430), '#ffffff')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 32)
    small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 23)
    for y, text in [(32, ('第二张截图测试 67890' if second else '本地截图文字识别')), (105, '这是一个离线 OCR 工具，无需上传图片。'), (175, 'Hello World 12345'), (245, '支持中文、English 和数字 2026。')]:
        draw.text((42, y), text, font=font, fill='#263449')
    draw.text((42, 330), '小字测试：项目路径 C:/ocr-tools，金额 128.50 元', font=small, fill='#4d596c')
    image.save(output)
    return output


if __name__ == '__main__':
    generate()
