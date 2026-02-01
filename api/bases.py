"""
Vercel serverless API: GET /api/bases?th=9&purpose=push
Возвращает первые 5 баз с ClashCodes для выбранного TH и цели (farming / push / war).
Для push (legend) парсит /bases/legend и фильтрует карточки по TH, затем при необходимости
загружает статьи и извлекает реальные ссылки на базы (Copy Base Link).
"""
import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urljoin, urlparse, parse_qs

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

BASE_URL = "https://clashcodes.com"
REQUEST_TIMEOUT = 8
NEEDED = 5


def get_category_url(th: int, purpose: str) -> str:
    if purpose == "farming":
        return f"{BASE_URL}/bases/th{th}-farming?sort=rating"
    if purpose == "push":
        return f"{BASE_URL}/bases/legend?sort=rating"
    return f"{BASE_URL}/bases/th{th}-war?sort=rating"


def _normalize_rating(views_text: str, stars_text: str = "") -> float:
    score = 0.0
    m = re.search(r"([\d.]+)\s*k", (views_text or "").replace(",", "."), re.IGNORECASE)
    if m:
        score += float(m.group(1)) * 1000
    star_count = (stars_text or "").count("★")
    if star_count:
        score += star_count * 500
    return score


def _parse_cards(html: str, category_url: str) -> list:
    if not BeautifulSoup:
        return []
    soup = BeautifulSoup(html, "html.parser")
    parsed_base = f"{urlparse(category_url).scheme}://{urlparse(category_url).netloc}"
    results = []
    seen_links = set()

    for tag in soup.find_all(["article", "div"], class_=re.compile(r"card|post|entry|item|base|loop", re.I)):
        link_tag = tag.find("a", href=True)
        if not link_tag:
            continue
        href = (link_tag.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        full_link = href if href.startswith("http") else urljoin(parsed_base, href)
        if "clashcodes.com" not in full_link:
            continue
        path = urlparse(full_link).path.rstrip("/")
        if re.match(r"^/bases/[^/]+$", path):
            continue
        if full_link in seen_links:
            continue
        seen_links.add(full_link)
        img = tag.find("img", src=True)
        image_url = None
        if img and img.get("src"):
            src = img["src"].strip()
            image_url = src if src.startswith("http") else urljoin(parsed_base, src)
        title = (link_tag.get("title") or "").strip()
        if not title:
            h = tag.find(["h2", "h3", "h4", "h5", "strong"])
            if h:
                title = h.get_text(strip=True)[:200]
        if not title and img and img.get("alt"):
            title = (img.get("alt") or "").strip()[:200]
        block_text = tag.get_text()
        views_match = re.search(r"([\d.,]+\s*k)", block_text, re.IGNORECASE)
        rating_score = _normalize_rating(views_match.group(1) if views_match else "", block_text)
        results.append({
            "link": full_link,
            "image_url": image_url or "",
            "type": title or "Base",
            "description": title or "База с ClashCodes",
            "rating": rating_score,
            "rating_display": f"{int(min(10, max(1, rating_score / 500)))}/10" if rating_score else "—/10",
            "article_url": full_link,
        })
    if not results:
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.startswith("#"):
                continue
            full_link = href if href.startswith("http") else urljoin(parsed_base, href)
            if "clashcodes.com" not in full_link:
                continue
            path = urlparse(full_link).path.rstrip("/")
            if re.match(r"^/bases/[^/]+$", path) or len(path.split("/")) < 2:
                continue
            if full_link in seen_links:
                continue
            parent = a.parent
            img = None
            for _ in range(8):
                if not parent:
                    break
                img = parent.find("img", src=True)
                if img and img.get("src"):
                    break
                parent = getattr(parent, "parent", None)
            if not img or not img.get("src"):
                continue
            seen_links.add(full_link)
            src = img["src"].strip()
            image_url = src if src.startswith("http") else urljoin(parsed_base, src)
            title = (a.get("title") or a.get_text(strip=True) or "").strip()[:200]
            block_text = (parent.get_text() if parent else "") or ""
            views_match = re.search(r"([\d.,]+\s*k)", block_text, re.IGNORECASE)
            rating_score = _normalize_rating(views_match.group(1) if views_match else "", block_text)
            results.append({
                "link": full_link,
                "image_url": image_url or "",
                "type": title or "Base",
                "description": title or "База с ClashCodes",
                "rating": rating_score,
                "rating_display": f"{int(min(10, max(1, rating_score / 500)))}/10" if rating_score else "—/10",
                "article_url": full_link,
            })
    return results


def _filter_by_th(cards: list, th: int) -> list:
    """Оставляет карточки, где в заголовке или ссылке упоминается TH{th}."""
    th_str = f"th{th}"
    th_str_upper = f"TH{th}"
    out = []
    for c in cards:
        t = (c.get("type") or "").lower()
        link = (c.get("link") or "").lower()
        if th_str in t or th_str_upper in (c.get("type") or "") or th_str in link:
            out.append(c)
    return out


def _parse_article_bases(html: str, article_url: str) -> list:
    if not BeautifulSoup:
        return []
    soup = BeautifulSoup(html, "html.parser")
    parsed_base = f"{urlparse(article_url).scheme}://{urlparse(article_url).netloc}"
    results = []
    seen_links = set()
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip().lower()
        if "copy" not in text:
            continue
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        copy_link = href if href.startswith("http") else urljoin(parsed_base, href)
        if copy_link in seen_links:
            continue
        parent = a.parent
        img = None
        title = ""
        for _ in range(15):
            if not parent:
                break
            imgs = parent.find_all("img", src=True)
            for i in imgs:
                src = (i.get("src") or "").lower()
                if src and "logo" not in src and "icon" not in src and "avatar" not in src:
                    img = i
                    break
            if not title:
                for h in parent.find_all(["h2", "h3", "h4"]):
                    title = (h.get_text() or "").strip()[:200]
                    if title and len(title) > 4:
                        break
            if img and img.get("src"):
                break
            parent = getattr(parent, "parent", None)
        if not img or not img.get("src"):
            continue
        seen_links.add(copy_link)
        src = img["src"].strip()
        image_url = src if src.startswith("http") else urljoin(parsed_base, src)
        if not title:
            title = (img.get("alt") or "").strip() or f"База {len(results) + 1}"
        results.append({
            "link": copy_link,
            "image_url": image_url,
            "type": title[:200],
            "description": "Копируй ссылку в игру.",
            "rating": 8,
            "rating_display": f"{min(10, max(7, 10 - len(results)))}/10",
        })
        if len(results) >= NEEDED:
            break
    return results


def fetch_bases(th: int, purpose: str) -> list:
    if not requests or not BeautifulSoup:
        return []
    url = get_category_url(th, purpose)
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        html = r.text
    except Exception:
        return []
    cards = _parse_cards(html, url)
    if purpose == "push":
        cards = _filter_by_th(cards, th)
    if not cards:
        return []
    # Пытаемся получить реальные ссылки на базы из статей (первые 5 баз)
    collected = []
    for article_card in cards[:5]:
        if len(collected) >= NEEDED:
            break
        article_url = article_card.get("article_url") or article_card.get("link")
        if not article_url:
            collected.append({
                "link": article_card["link"],
                "image_url": article_card.get("image_url") or "",
                "type": article_card.get("type") or "Base",
                "description": article_card.get("description") or "Открой страницу статьи.",
                "rating": article_card.get("rating", 7),
                "rating_display": article_card.get("rating_display", "7/10"),
            })
            continue
        try:
            r2 = requests.get(article_url, timeout=REQUEST_TIMEOUT)
            if r2.status_code != 200:
                collected.append({
                    "link": article_card["link"],
                    "image_url": article_card.get("image_url") or "",
                    "type": article_card.get("type") or "Base",
                    "description": article_card.get("description") or "Открой страницу статьи.",
                    "rating": article_card.get("rating", 7),
                    "rating_display": article_card.get("rating_display", "7/10"),
                })
                continue
            bases = _parse_article_bases(r2.text, article_url)
            for b in bases:
                if len(collected) >= NEEDED:
                    break
                collected.append(b)
        except Exception:
            collected.append({
                "link": article_card["link"],
                "image_url": article_card.get("image_url") or "",
                "type": article_card.get("type") or "Base",
                "description": article_card.get("description") or "Открой страницу статьи.",
                "rating": article_card.get("rating", 7),
                "rating_display": article_card.get("rating_display", "7/10"),
            })
    if not collected:
        collected = cards[:NEEDED]
    for i, c in enumerate(collected[:NEEDED]):
        if "rating_display" not in c:
            c["rating_display"] = f"{min(10, max(1, int((c.get('rating') or 0) / 500) or 7))}/10"
    return collected[:NEEDED]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            th_str = (qs.get("th") or [None])[0]
            purpose = (qs.get("purpose") or [""])[0]
            th = None
            if th_str and th_str.isdigit():
                th = int(th_str)
            if th is None or th < 2 or th > 18:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid th"}).encode("utf-8"))
                return
            if purpose not in ("farming", "push", "war"):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid purpose"}).encode("utf-8"))
                return
            bases = fetch_bases(th, purpose)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(bases, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def log_message(self, format, *args):
        pass
