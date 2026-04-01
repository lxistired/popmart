import json
import os
import pytest


# INFRA-06: load_config() parses amazon/instagram/tiktok targets correctly
def test_load_all_configs(tmp_path):
    """Config files must be parseable JSON with expected top-level keys."""
    # Create minimal test config files
    amazon_cfg = {
        "since_date": "2024-01-01",
        "max_pages": 10,
        "skus": [{"asin": "B0DT44TSM2", "ip": "Labubu", "title": "Test", "since_date": None}]
    }
    ig_cfg = {
        "since_date": "2024-01-01",
        "max_posts_per_account": 50,
        "max_comments_per_post": 500,
        "accounts": [{"username": "popmart", "label": "official"}]
    }
    tt_cfg = {
        "since_date": "2024-01-01",
        "max_videos_per_query": 50,
        "queries": [{"keyword": "labubu", "filter_brand": True}],
        "accounts": [{"username": "popmartglobal", "label": "official"}]
    }
    for name, cfg in [("amazon_targets.json", amazon_cfg),
                      ("instagram_targets.json", ig_cfg),
                      ("tiktok_targets.json", tt_cfg)]:
        (tmp_path / name).write_text(json.dumps(cfg), encoding='utf-8')

    # Verify all three parse correctly
    for name in ["amazon_targets.json", "instagram_targets.json", "tiktok_targets.json"]:
        data = json.loads((tmp_path / name).read_text(encoding='utf-8'))
        assert "since_date" in data

    # Amazon: skus list, each with asin and ip
    amazon = json.loads((tmp_path / "amazon_targets.json").read_text())
    assert len(amazon["skus"]) >= 1
    assert "asin" in amazon["skus"][0]
    assert "ip" in amazon["skus"][0]

    # Instagram: accounts list with username
    ig = json.loads((tmp_path / "instagram_targets.json").read_text())
    assert any(a["username"] == "popmart" for a in ig["accounts"])
    assert not any(a["username"] == "popmart_global" for a in ig["accounts"]), \
        "@popmart_global is fake — must not appear in targets"

    # TikTok: no standalone #molly keyword
    tt = json.loads((tmp_path / "tiktok_targets.json").read_text())
    query_keywords = [q["keyword"] for q in tt.get("queries", [])]
    assert "molly" not in query_keywords, \
        "#molly is polluted by drug content — must not be a standalone keyword"

    # INFRA-06: Real config directory must exist (created by Plan 02)
    # This assertion fails in RED state — Plan 02 creates phase2_overseas/config/
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
    assert os.path.isdir(config_dir), \
        f"Config directory not found at {config_dir} — run Plan 02 to create shared infrastructure"
