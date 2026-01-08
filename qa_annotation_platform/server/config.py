"""
QA Annotation Platform Configuration

Independent configuration system, using config.json file
"""
import os
import json
import sys
from typing import Optional, List
from pydantic import BaseModel


# Config file path - look in the same directory as this file
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


class ESConfig(BaseModel):
    """ES Configuration"""
    hosts: List[str] = ["http://localhost:9200"]
    user: Optional[str] = None
    password: Optional[str] = None
    index_prefix: str = "qa_annotation_platform"
    local_data_dir: Optional[str] = None


class KBConfig(BaseModel):
    """Knowledge Base Ingestion Configuration"""
    enabled: bool = False
    endpoint: str = ""
    kb_id: str = ""
    auto_ingest: bool = False
    timeout: int = 30
    retry_times: int = 3
    retry_interval: int = 5


class AppConfig(BaseModel):
    """Application Configuration"""
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    es: ESConfig = ESConfig()
    kb: KBConfig = KBConfig()
    cors_origins: List[str] = ["*"]
    
    # Task Configuration
    task_expire_hours: int = 24
    dedup_enabled: bool = True
    min_question_length: int = 2
    batch_size: int = 100


def load_config_from_file() -> Optional[dict]:
    """Load configuration from config.json file"""
    if not os.path.exists(CONFIG_FILE):
        print("=" * 60)
        print("ERROR: Configuration file not found!")
        print("=" * 60)
        print(f"\nPlease create a config.json file at:")
        print(f"  {CONFIG_FILE}")
        print("\nExample config.json content:")
        print("-" * 60)
        print("""{
    "app": {
        "host": "0.0.0.0",
        "port": 8001,
        "debug": false,
        "cors_origins": ["*"]
    },
    "es": {
        "hosts": ["http://localhost:9200"],
        "user": null,
        "password": null,
        "index_prefix": "qa_annotation_platform",
        "local_data_dir": null
    },
    "kb": {
        "enabled": false,
        "endpoint": "",
        "kb_id": "",
        "auto_ingest": false,
        "timeout": 30,
        "retry_times": 3,
        "retry_interval": 5
    },
    "task": {
        "expire_hours": 24,
        "dedup_enabled": true,
        "min_question_length": 2,
        "batch_size": 100
    }
}""")
        print("-" * 60)
        print("\nExiting...")
        sys.exit(1)
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in config file: {e}")
        print(f"File: {CONFIG_FILE}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to load config file: {e}")
        sys.exit(1)


def get_config() -> AppConfig:
    """Read configuration from config.json file"""
    config_data = load_config_from_file()
    
    # Parse App config
    app_config = config_data.get("app", {})
    host = app_config.get("host", "0.0.0.0")
    port = int(app_config.get("port", 8001))
    debug = app_config.get("debug", False)
    cors_origins = app_config.get("cors_origins", ["*"])
    
    # Parse ES config
    es_config = config_data.get("es", {})
    es = ESConfig(
        hosts=es_config.get("hosts", ["http://localhost:9200"]),
        user=es_config.get("user"),
        password=es_config.get("password"),
        index_prefix=es_config.get("index_prefix", "qa_annotation_platform"),
        local_data_dir=es_config.get("local_data_dir")
    )
    
    # Parse KB config
    kb_config = config_data.get("kb", {})
    kb = KBConfig(
        enabled=kb_config.get("enabled", False),
        endpoint=kb_config.get("endpoint", ""),
        kb_id=kb_config.get("kb_id", ""),
        auto_ingest=kb_config.get("auto_ingest", False),
        timeout=int(kb_config.get("timeout", 30)),
        retry_times=int(kb_config.get("retry_times", 3)),
        retry_interval=int(kb_config.get("retry_interval", 5))
    )
    
    # Parse Task config
    task_config = config_data.get("task", {})
    task_expire_hours = int(task_config.get("expire_hours", 24))
    dedup_enabled = task_config.get("dedup_enabled", True)
    min_question_length = int(task_config.get("min_question_length", 2))
    batch_size = int(task_config.get("batch_size", 100))
    
    return AppConfig(
        host=host,
        port=port,
        debug=debug,
        cors_origins=cors_origins,
        es=es,
        kb=kb,
        task_expire_hours=task_expire_hours,
        dedup_enabled=dedup_enabled,
        min_question_length=min_question_length,
        batch_size=batch_size
    )


# Global Configuration Instance
_config: Optional[AppConfig] = None


def get_app_config() -> AppConfig:
    """Get application configuration (singleton)"""
    global _config
    if _config is None:
        _config = get_config()
    return _config


def reset_config():
    """Reset configuration (for testing)"""
    global _config
    _config = None
