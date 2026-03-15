"""
Fetcher — Content Extraction
URL content extraction with SSRF protection and image fallback logic.
"""
import logging

import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger('fetcher.content')


def extract_content(url: str):
    """
    Extracts text content, social image, and author from a URL.
    Returns (content, image_url, author) tuple.
    Includes SSRF protection to block requests to internal networks.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

    # --- SSRF Protection ---
    import socket
    from urllib.parse import urlparse
    import ipaddress

    def is_safe_url(target_url):
        try:
            parsed = urlparse(target_url)
            if parsed.scheme not in ('http', 'https'):
                return False

            hostname = parsed.hostname
            if not hostname:
                return False

            # Resolve IP
            addr_info = socket.getaddrinfo(hostname, None)
            for family, socktype, proto, canonname, sockaddr in addr_info:
                ip = sockaddr[0]
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                    logger.warning("🚫 Blocked SSRF Attempt: %s resolves to %s", target_url, ip)
                    return False
            return True
        except Exception:
            return False

    if not is_safe_url(url):
        logger.warning("⚠️ Unsafe URL blocked: %s", url)
        return None, None

    downloaded = trafilatura.fetch_url(url)

    if not downloaded:
        # Fallback to Requests
        import requests
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            downloaded = response.text
        except Exception as e:
            logger.warning("⚠️ Request failed for %s: %s", url, e)
            downloaded = None

    if downloaded:
        content = trafilatura.extract(downloaded)

        # Extract Image with multiple fallbacks
        soup = BeautifulSoup(downloaded, 'html.parser')
        og_image = ""

        # 1. Try OG:Image
        img_tag = soup.find("meta", property="og:image")
        if img_tag:
            og_image = img_tag.get("content", "")

        # 2. Try Twitter:Image
        if not og_image:
            twitter_tag = soup.find("meta", attrs={"name": "twitter:image"})
            if twitter_tag:
                og_image = twitter_tag.get("content", "")

        # 3. Try broad image search if metadata failed
        if not og_image:
            for img in soup.find_all('img', src=True):
                src = img['src']
                if src.startswith('http') and not any(x in src.lower() for x in ['pixel', 'logo', 'icon', 'sprite', 'ad']):
                    og_image = src
                    break

        # 4. Defensive check: Avoid small icons or tracking pixels
        if og_image and any(x in og_image.lower() for x in ['pixel', 'logo', 'icon', 'sprite', '1x1', 'tracking']):
            og_image = ""

        # 5. Resolve relative URLs
        if og_image and not og_image.startswith('http'):
            from urllib.parse import urljoin
            og_image = urljoin(url, og_image)

        # 6. Extract Metadata (Author)
        metadata = trafilatura.extract_metadata(downloaded)
        author = metadata.author if metadata else None

        return (content if content else ""), og_image, (author if author else "")
    return "", "", ""
