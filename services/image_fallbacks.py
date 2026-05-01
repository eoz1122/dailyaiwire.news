"""
Curated article fallback images for onsite thumbnails.
"""
from __future__ import annotations

import hashlib
import os
import random
from typing import Optional


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FALLBACK_IMAGES = {
    "LLMs": (
        "/static/fallbacks/llms_0.jpg",
        "/static/fallbacks/llms_1.jpg",
        "/static/fallbacks/llms_2.jpg",
        "/static/fallbacks/llms_3.jpg",
    ),
    "Robotics": (
        "/static/fallbacks/robotics_0.jpg",
        "/static/fallbacks/robotics_1.jpg",
        "/static/fallbacks/robotics_2.jpg",
        "/static/fallbacks/robotics_3.jpg",
        "/static/fallbacks/robotics_4.jpg",
        "/static/fallbacks/robotics_5.jpg",
        "/static/fallbacks/robotics_6.jpg",
        "/static/fallbacks/robotics_7.jpg",
    ),
    "Business": (
        "/static/fallbacks/business_0.jpg",
        "/static/fallbacks/business_1.jpg",
        "/static/fallbacks/business_2.jpg",
        "/static/fallbacks/business_3.jpg",
        "/static/fallbacks/business_4.jpg",
        "/static/fallbacks/business_5.jpg",
        "/static/fallbacks/business_6.jpg",
        "/static/fallbacks/business_7.jpg",
        "/static/fallbacks/business_8.jpg",
    ),
    "Tools": (
        "/static/fallbacks/tools_0.jpg",
        "/static/fallbacks/tools_1.jpg",
        "/static/fallbacks/tools_2.jpg",
    ),
    "Policy": (
        "/static/fallbacks/policy_0.jpg",
        "/static/fallbacks/policy_1.jpg",
        "/static/fallbacks/policy_2.jpg",
        "/static/fallbacks/policy_3.jpg",
        "/static/fallbacks/policy_4.jpg",
        "/static/fallbacks/policy_5.jpg",
        "/static/fallbacks/policy_6.jpg",
        "/static/fallbacks/policy_7.jpg",
    ),
    "Science": (
        "/static/fallbacks/science_0.jpg",
        "/static/fallbacks/science_2.jpg",
        "/static/fallbacks/science_4.jpg",
        "/static/fallbacks/science_5.jpg",
        "/static/fallbacks/science_6.jpg",
        "/static/fallbacks/science_7.jpg",
    ),
    "Security": (
        "/static/fallbacks/security_0.jpg",
        "/static/fallbacks/security_1.jpg",
        "/static/fallbacks/security_2.jpg",
        "/static/fallbacks/security_3.jpg",
    ),
    "Society": (
        "/static/fallbacks/society_0.jpg",
        "/static/fallbacks/society_1.jpg",
        "/static/fallbacks/society_2.jpg",
        "/static/fallbacks/society_3.jpg",
        "/static/fallbacks/society_4.jpg",
    ),
    "Ethics": (
        "/static/fallbacks/society_0.jpg",
        "/static/fallbacks/society_2.jpg",
        "/static/fallbacks/policy_2.jpg",
        "/static/fallbacks/security_1.jpg",
    ),
    "AI Agents": (
        "/static/fallbacks/tools_0.jpg",
        "/static/fallbacks/tools_1.jpg",
        "/static/fallbacks/tools_2.jpg",
        "/static/fallbacks/llms_0.jpg",
        "/static/fallbacks/llms_2.jpg",
        "/static/fallbacks/security_2.jpg",
    ),
}

DISALLOWED_FALLBACK_IMAGES = frozenset(
    {
        "/static/fallbacks/science_1.jpg",
    }
)


def category_fallback_images(category: Optional[str]):
    return FALLBACK_IMAGES.get(category or "", FALLBACK_IMAGES["Tools"])


def select_category_fallback(category: Optional[str], avoid: Optional[str] = None) -> str:
    images = category_fallback_images(category)
    available_images = [image for image in images if image != avoid]
    if not available_images:
        available_images = list(images)
    return random.choice(available_images)


def deterministic_fallback(slug: Optional[str], category: Optional[str]) -> str:
    images = category_fallback_images(category)
    key = slug or category or "dailyaiwire"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(images)
    return images[index]


def fallback_asset_path(image: Optional[str], root_dir: str = ROOT_DIR) -> Optional[str]:
    image_text = str(image or "")
    if not image_text.startswith("/static/fallbacks/"):
        return None
    return os.path.join(root_dir, image_text.lstrip("/"))


def fallback_asset_exists(image: Optional[str], root_dir: str = ROOT_DIR) -> bool:
    path = fallback_asset_path(image, root_dir)
    return bool(path and os.path.exists(path))


def needs_fallback_repair(image: Optional[str], root_dir: str = ROOT_DIR) -> bool:
    image_text = str(image or "")
    if not image_text.startswith("/static/fallbacks/"):
        return False
    return image_text in DISALLOWED_FALLBACK_IMAGES or not fallback_asset_exists(image_text, root_dir)
