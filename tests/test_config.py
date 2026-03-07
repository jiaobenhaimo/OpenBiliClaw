"""Tests for configuration management."""

from pathlib import Path

from openbiliclaw.config import Config, _build_config, load_config


class TestConfigDefaults:
    """Test default configuration values."""

    def test_default_config(self) -> None:
        config = Config()
        assert config.language == "zh"
        assert config.llm.default_provider == "openai"
        assert config.bilibili.auth_method == "cookie"
        assert config.scheduler.enabled is True

    def test_build_from_empty_dict(self) -> None:
        config = _build_config({})
        assert config.language == "zh"
        assert config.llm.default_provider == "openai"

    def test_build_from_partial_dict(self) -> None:
        raw = {
            "general": {"language": "en"},
            "llm": {"default_provider": "claude"},
        }
        config = _build_config(raw)
        assert config.language == "en"
        assert config.llm.default_provider == "claude"
        # Other defaults should remain
        assert config.bilibili.auth_method == "cookie"

    def test_data_path_relative(self) -> None:
        config = Config(data_dir="data")
        # Should resolve to an absolute path
        assert config.data_path.is_absolute()

    def test_data_path_absolute(self) -> None:
        config = Config(data_dir="/tmp/openbiliclaw_test")
        assert config.data_path == Path("/tmp/openbiliclaw_test")

    def test_load_config_missing_file(self) -> None:
        """Should return defaults when no config file exists."""
        config = load_config("/nonexistent/path/config.toml")
        assert config.language == "zh"
