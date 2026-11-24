"""Server configuration. Everything is read from environment variables so the
model and its parameters can be changed in deploy/.env without touching code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    data_dir: str = field(default_factory=lambda: _env("DATA_DIR", "/data"))

    # --- LLM (Ollama) ---
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://ollama:11434"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "qwen2.5:0.5b"))
    llm_num_ctx: int = field(default_factory=lambda: _int("LLM_NUM_CTX", 2048))
    llm_num_predict: int = field(default_factory=lambda: _int("LLM_NUM_PREDICT", 220))
    llm_temperature: float = field(default_factory=lambda: _float("LLM_TEMPERATURE", 0.7))
    llm_top_p: float = field(default_factory=lambda: _float("LLM_TOP_P", 0.9))
    llm_repeat_penalty: float = field(default_factory=lambda: _float("LLM_REPEAT_PENALTY", 1.15))
    llm_num_thread: int = field(default_factory=lambda: _int("LLM_NUM_THREAD", 0))  # 0 = Ollama decides
    llm_timeout_s: int = field(default_factory=lambda: _int("LLM_TIMEOUT_S", 300))
    llm_keep_alive: str = field(default_factory=lambda: _env("LLM_KEEP_ALIVE", "-1"))
    # how many recent messages go to the model verbatim; older ones are summarised
    ctx_recent_messages: int = field(default_factory=lambda: _int("CTX_RECENT_MESSAGES", 10))
    summary_batch: int = field(default_factory=lambda: _int("SUMMARY_BATCH", 8))
    summary_max_chars: int = field(default_factory=lambda: _int("SUMMARY_MAX_CHARS", 900))
    # debounce before a reply starts, so two simultaneous player turns get one reaction
    reply_debounce_ms: int = field(default_factory=lambda: _int("REPLY_DEBOUNCE_MS", 1200))
    # "fake" = deterministic offline generator used only by automated tests
    llm_backend: str = field(default_factory=lambda: _env("LLM_BACKEND", "ollama"))

    # --- cloud AI (OpenRouter). The key lives only on the server, never in the APK. ---
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY", "").strip())
    openrouter_base_url: str = field(default_factory=lambda: _env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
    cloud_text_model: str = field(default_factory=lambda: _env("CLOUD_TEXT_MODEL", "deepseek/deepseek-v4.1-flash"))
    cloud_image_model: str = field(default_factory=lambda: _env("CLOUD_IMAGE_MODEL", "google/gemini-3.1-flash-lite-image"))
    cloud_ctx_tokens: int = field(default_factory=lambda: _int("CLOUD_CTX_TOKENS", 16000))
    cloud_max_tokens: int = field(default_factory=lambda: _int("CLOUD_MAX_TOKENS", 700))
    cloud_temperature: float = field(default_factory=lambda: _float("CLOUD_TEMPERATURE", 0.9))
    cloud_recent_messages: int = field(default_factory=lambda: _int("CLOUD_RECENT_MESSAGES", 40))
    cloud_timeout_s: int = field(default_factory=lambda: _int("CLOUD_TIMEOUT_S", 120))
    cloud_reasoning: str = field(default_factory=lambda: _env("CLOUD_REASONING", "off"))  # off | low | medium | high
    # mode for new scenes: auto = cloud when a key is configured, else local
    default_ai_mode: str = field(default_factory=lambda: _env("DEFAULT_AI_MODE", "auto"))
    rl_images_per_day: int = field(default_factory=lambda: _int("RL_IMAGES_PER_DAY", 30))

    # --- limits ---
    max_characters: int = 10
    max_image_bytes: int = field(default_factory=lambda: _int("MAX_IMAGE_BYTES", 6 * 1024 * 1024))
    rl_register_per_hour: int = field(default_factory=lambda: _int("RL_REGISTER_PER_HOUR", 10))
    rl_search_per_min: int = field(default_factory=lambda: _int("RL_SEARCH_PER_MIN", 20))
    rl_search_per_day: int = field(default_factory=lambda: _int("RL_SEARCH_PER_DAY", 300))
    rl_friend_req_per_hour: int = field(default_factory=lambda: _int("RL_FRIEND_REQ_PER_HOUR", 20))
    rl_messages_per_min: int = field(default_factory=lambda: _int("RL_MESSAGES_PER_MIN", 30))
    rl_uploads_per_hour: int = field(default_factory=lambda: _int("RL_UPLOADS_PER_HOUR", 60))
    sync_wait_max_s: int = 25

    @property
    def cloud_available(self) -> bool:
        return bool(self.openrouter_api_key) or self.llm_backend == "fake"

    def new_room_ai_mode(self) -> str:
        if self.default_ai_mode in ("local", "cloud"):
            return "cloud" if (self.default_ai_mode == "cloud" and self.cloud_available) else "local"
        return "cloud" if self.cloud_available else "local"

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "fonar.sqlite3")

    @property
    def images_dir(self) -> str:
        return os.path.join(self.data_dir, "images")


settings = Settings()


def reload_settings() -> Settings:
    global settings
    settings = Settings()
    return settings
