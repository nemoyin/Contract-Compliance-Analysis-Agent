"""测试配置管理"""
import json
import os
import tempfile
import pytest
from engine.config import ConfigManager, DEFAULT_CONFIG


class TestDefaultConfig:
    def test_has_required_sections(self):
        assert "llm" in DEFAULT_CONFIG
        assert "matching" in DEFAULT_CONFIG
        assert "thresholds" in DEFAULT_CONFIG

    def test_llm_default_provider(self):
        assert DEFAULT_CONFIG["llm"]["provider"] == "deepseek"

    def test_matching_thresholds(self):
        assert DEFAULT_CONFIG["matching"]["rule_confidence_threshold"] == 0.9
        assert DEFAULT_CONFIG["matching"]["llm_batch_size"] == 20

    def test_analysis_thresholds(self):
        assert DEFAULT_CONFIG["thresholds"]["similar_price_pct"] == 5
        assert DEFAULT_CONFIG["thresholds"]["quality_similarity"] == 0.95
        assert DEFAULT_CONFIG["thresholds"]["price_outlier_std"] == 1.5


class TestConfigManager:
    @pytest.fixture
    def temp_config_path(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b'{"test": true}')
            path = f.name
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_load_existing(self, temp_config_path):
        mgr = ConfigManager(temp_config_path)
        config = mgr.load()
        assert config["test"] is True

    def test_save_and_load(self, temp_config_path):
        mgr = ConfigManager(temp_config_path)
        mgr.save({"llm": {"provider": "openai"}, "matching": {}, "thresholds": {}})
        config = mgr.load()
        assert config["llm"]["provider"] == "openai"

    def test_get_with_default(self, temp_config_path):
        mgr = ConfigManager(temp_config_path)
        mgr.save({"a": 1})
        assert mgr.get("a") == 1
        assert mgr.get("missing", 42) == 42

    def test_get_nested_key(self, temp_config_path):
        mgr = ConfigManager(temp_config_path)
        mgr.save({"llm": {"provider": "claude", "model": "claude-sonnet-5"}})
        assert mgr.get("llm.provider") == "claude"
        assert mgr.get("llm.model") == "claude-sonnet-5"

    def test_load_nonexistent_returns_default(self, temp_config_path):
        os.unlink(temp_config_path)
        mgr = ConfigManager(temp_config_path)
        config = mgr.load()
        assert config == DEFAULT_CONFIG

    def test_update_merges(self, temp_config_path):
        mgr = ConfigManager(temp_config_path)
        mgr.save({"llm": {"provider": "deepseek"}, "matching": {}, "thresholds": {}})
        mgr.update({"llm": {"model": "gpt-4"}})
        config = mgr.load()
        assert config["llm"]["provider"] == "deepseek"  # preserved
        assert config["llm"]["model"] == "gpt-4"         # updated
