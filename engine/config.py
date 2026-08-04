"""配置管理模块"""
import json
import os
from copy import deepcopy
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "llm": {
        "provider": "deepseek",
        "api_key": "",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "temperature": 0.3,
    },
    "matching": {
        "rule_confidence_threshold": 0.9,
        "llm_batch_size": 20,
    },
    "thresholds": {
        "similar_price_pct": 5,
        "quality_similarity": 0.95,
        "price_outlier_std": 1.5,
    },
}


class ConfigManager:
    """JSON 配置文件管理器，支持嵌套键访问和深度合并"""

    def __init__(self, config_path: str):
        self._path = config_path

    def load(self) -> dict[str, Any]:
        """加载配置，文件不存在时返回默认配置"""
        if not os.path.exists(self._path):
            return deepcopy(DEFAULT_CONFIG)
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # 用默认值补全缺失的顶层键
            result = deepcopy(DEFAULT_CONFIG)
            for key in result:
                if key in loaded:
                    result[key].update(loaded[key])
            # 保留 loaded 中存在但 DEFAULT_CONFIG 中没有的键
            for key in loaded:
                if key not in result:
                    result[key] = loaded[key]
            return result
        except (json.JSONDecodeError, IOError):
            return deepcopy(DEFAULT_CONFIG)

    def save(self, config: dict[str, Any]) -> None:
        """保存完整配置到文件"""
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def update(self, partial: dict[str, Any]) -> None:
        """深度合并部分配置并保存"""
        current = self.load()
        _deep_merge(current, partial)
        self.save(current)

    def get(self, key: str, default: Any = None) -> Any:
        """支持点号分隔的嵌套键读取，如 'llm.provider'"""
        config = self.load()
        parts = key.split(".")
        value = config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value


def _deep_merge(base: dict, update: dict) -> None:
    """原地深度合并 update 到 base"""
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
