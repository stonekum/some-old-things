from __future__ import annotations

from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

from ..config import Config
from ._common import download_images, make_session, read_links, sanitize_filename, save_text


def _extract_paragraphs(soup: BeautifulSoup) -> str:
    content_div = soup.find("div", id="js_content")
    if not content_div:
        return ""
    chunks: list[str] = []
    for el in content_div.find_all(["p", "section", "h1", "h2", "h3", "li"]):
        text = el.get_text(strip=True)
        if text:
            chunks.append(text)
    if not chunks:
        chunks = [content_div.get_text("\n", strip=True)]
    return "\n\n".join(chunks)


def crawl(cfg: Config) -> int:
    links = read_links(cfg.crawlers.wechat.links_file)
    if not links:
        logger.warning({"event": "wechat_no_links", "file": str(cfg.crawlers.wechat.links_file)})
        return 0

    session = make_session(cfg.crawlers.wechat.user_agent, referer="https://mp.weixin.qq.com/")
    out_root = cfg.paths.raw / "wechat"
    out_root.mkdir(parents=True, exist_ok=True)

    n = 0
    for url in links:
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            title_tag = soup.find("h1", class_="rich_media_title")
            title = sanitize_filename(title_tag.get_text(strip=True)) if title_tag else "未命名文章"
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            stem = f"{title}_{ts}"

            body = _extract_paragraphs(soup) or "暂无正文内容"
            save_text(out_root / f"{stem}.txt", body)

            imgs: list[str] = []
            content_div = soup.find("div", id="js_content")
            if content_div:
                for img in content_div.find_all("img"):
                    src = img.get("data-src") or img.get("src")
                    if src:
                        imgs.append(src)
            if imgs:
                download_images(session, imgs, out_root / f"{stem}_images", "image")

            logger.info({"event": "wechat_saved", "title": title, "url": url, "images": len(imgs)})
            n += 1
        except Exception as e:
            logger.error({"event": "wechat_failed", "url": url, "error": repr(e)})

    return n
