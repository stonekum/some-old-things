from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from ..config import Config
from ._common import download_images, make_session, read_links, sanitize_filename, save_text


def _convert_date(raw: str) -> str | None:
    try:
        return datetime.strptime(raw.strip(), "%Y年%m月%d日").strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def _extract_paragraphs(content_div) -> str:
    if not content_div:
        return ""
    chunks: list[str] = []
    for el in content_div.find_all(["p", "h1", "h2", "h3", "li"]):
        t = el.get_text(strip=True)
        if t:
            chunks.append(t)
    if not chunks:
        chunks = [content_div.get_text("\n", strip=True)]
    return "\n\n".join(chunks)


def crawl(cfg: Config) -> int:
    links = read_links(cfg.crawlers.sjtu_news.links_file)
    if not links:
        logger.warning(
            {"event": "sjtu_no_links", "file": str(cfg.crawlers.sjtu_news.links_file)}
        )
        return 0

    session = make_session(cfg.crawlers.sjtu_news.user_agent, referer="https://news.sjtu.edu.cn/")
    out_root = cfg.paths.raw / "sjtu_news"
    out_root.mkdir(parents=True, exist_ok=True)

    n = 0
    for url in links:
        try:
            r = session.get(url, timeout=30)
            r.encoding = "utf-8"
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            title_tag = soup.select_one("#ivs_title")
            content_div = soup.select_one(".Article_content")
            date_tag = soup.select_one("#ivs_date.time")

            title = title_tag.get_text(strip=True) if title_tag else "未知标题"
            pub_date = _convert_date(date_tag.get_text() if date_tag else "") or "unknown-date"
            stem = sanitize_filename(title)

            day_dir = out_root / pub_date
            body_lines = [f"标题：{title}", f"日期：{pub_date}", f"链接：{url}", ""]
            body_lines.append(_extract_paragraphs(content_div) or "未找到正文内容")
            save_text(day_dir / f"{stem}.txt", "\n".join(body_lines))

            imgs: list[str] = []
            if content_div:
                for img in content_div.find_all("img"):
                    src = img.get("src")
                    if not src:
                        continue
                    imgs.append(urljoin("https://news.sjtu.edu.cn/", src))
            if imgs:
                download_images(session, imgs, day_dir, f"{stem}_image")

            logger.info({"event": "sjtu_saved", "title": title, "date": pub_date, "url": url})
            n += 1
        except Exception as e:
            logger.error({"event": "sjtu_failed", "url": url, "error": repr(e)})

    return n
