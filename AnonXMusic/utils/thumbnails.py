import os
import re
import random
import aiohttp
import aiofiles
import traceback

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from youtubesearchpython.__future__ import VideosSearch
from AnonXMusic import app  # Bot instance for dynamic watermark

# Utility Functions
def changeImageSize(maxWidth, maxHeight, image):
    ratio = min(maxWidth / image.size[0], maxHeight / image.size[1])
    newSize = (int(image.size[0] * ratio), int(image.size[1] * ratio))
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS
    return image.resize(newSize, resample)

def truncate(text, max_chars=50):
    words = text.split()
    text1, text2 = "", ""
    for word in words:
        if len(text1 + " " + word) <= max_chars and not text2:
            text1 += " " + word
        else:
            text2 += " " + word
    return [text1.strip(), text2.strip()]

def add_rounded_corners(im, radius):
    circle = Image.new('L', (radius * 2, radius * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, radius * 2, radius * 2), fill=255)
    alpha = Image.new('L', im.size, 255)
    w, h = im.size
    alpha.paste(circle.crop((0, 0, radius, radius)), (0, 0))
    alpha.paste(circle.crop((0, radius, radius, radius * 2)), (0, h - radius))
    alpha.paste(circle.crop((radius, 0, radius * 2, radius)), (w - radius, 0))
    alpha.paste(circle.crop((radius, radius, radius * 2, radius * 2)), (w - radius, h - radius))
    im.putalpha(alpha)
    return im

def fit_text(draw, text, max_width, font_path, start_size, min_size):
    size = start_size
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 1
    return ImageFont.truetype(font_path, min_size)

def create_rounded_square(image, size, radius=50):
    image = image.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
    rounded_mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(rounded_mask)
    draw.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    rounded_image = Image.new("RGBA", (size, size))
    rounded_image.paste(image, (0, 0), mask=rounded_mask)
    return rounded_image

# Main Thumbnail Function
async def get_thumb(videoid: str):
    url = f"https://www.youtube.com/watch?v={videoid}"
    try:
        results = VideosSearch(url, limit=1)
        res_data = await results.next()
        if not res_data["result"]:
            print(f"No results found for video ID: {videoid}")
            return None

        result = res_data["result"][0]
        title = re.sub(r"\W+", " ", result.get("title", "Unsupported Title")).title()
        duration = result.get("duration", "Unknown Mins")
        thumbnail = result.get("thumbnails", [{}])[0].get("url")
        views = result.get("viewCount", {}).get("short", "Unknown Views")
        channel = result.get("channel", {}).get("name", "Unknown Channel")

        if not thumbnail:
            print(f"Thumbnail URL not found for video ID: {videoid}")
            return None

        # Download Thumbnail
        os.makedirs("cache", exist_ok=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status == 200:
                    f = await aiofiles.open(f"cache/thumb{videoid}.png", mode="wb")
                    await f.write(await resp.read())
                    await f.close()
                else:
                    print(f"Failed to download thumbnail: {resp.status}")
                    return None

        youtube = Image.open(f"cache/thumb{videoid}.png")
        image1 = changeImageSize(1280, 720, youtube)
        image2 = image1.convert("RGBA")

        # Canvas-style Background
        gradient = Image.new("RGBA", image2.size, (0, 0, 0, 180))
        blurred = ImageEnhance.Brightness(image2.filter(ImageFilter.GaussianBlur(8))).enhance(0.5)
        background = Image.alpha_composite(blurred, gradient)

        # Rounded Logo Overlay
        logo = create_rounded_square(youtube, 450, radius=60)
        background.paste(logo, (100, 150), logo)

        draw = ImageDraw.Draw(background)
        font_info = ImageFont.truetype("AnonXMusic/assets/font2.ttf", 28)
        font_time = ImageFont.truetype("AnonXMusic/assets/font2.ttf", 26)
        font_path = "AnonXMusic/assets/font.ttf"

        # Title
        title_max_width = 540
        title_lines = truncate(title, 35)
        title_font1 = fit_text(draw, title_lines[0], title_max_width, font_path, 42, 28)
        draw.text((565, 180), title_lines[0], (255, 255, 255), font=title_font1)
        if title_lines[1]:
            title_font2 = fit_text(draw, title_lines[1], title_max_width, font_path, 36, 24)
            draw.text((565, 225), title_lines[1], (220, 220, 220), font=title_font2)

        # Channel & Views
        draw.text((565, 305), f"{channel} | {views}", (240, 240, 240), font=font_info)

        # Progress bar & duration
        rand = (random.randint(100, 255), random.randint(100, 255), random.randint(100, 255))
        draw.line([(565, 370), (990, 370)], fill=rand, width=6)
        draw.ellipse([(990, 362), (1010, 382)], outline=rand, fill=rand, width=12)
        draw.text((1080, 385), duration, (255, 255, 255), font=font_time)

        # Dynamic Watermark
        watermark_font = ImageFont.truetype("AnonXMusic/assets/font2.ttf", 24)
        watermark_text = f"by {app.name}"
        text_size = draw.textsize(watermark_text, font=watermark_font)
        x = background.width - text_size[0] - 25
        y = background.height - text_size[1] - 25
        glow_pos = [(x + dx, y + dy) for dx in (-1, 1) for dy in (-1, 1)]
        for pos in glow_pos:
            draw.text(pos, watermark_text, font=watermark_font, fill=(0, 0, 0, 180))
        draw.text((x, y), watermark_text, font=watermark_font, fill=(255, 255, 255, 240))

        # Final rounded corners
        background = add_rounded_corners(background, 30)

        # Cleanup temp file
        try:
            os.remove(f"cache/thumb{videoid}.png")
        except:
            pass

        tpath = f"cache/{videoid}.png"
        background.save(tpath)
        return tpath

    except Exception:
        traceback.print_exc()
        return None
