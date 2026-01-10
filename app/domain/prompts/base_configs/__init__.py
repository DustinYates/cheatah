"""Base configurations for different business types."""

from app.domain.prompts.base_configs.bss import BSSBaseConfig

# Registry of available base configs by business type
BASE_CONFIG_REGISTRY = {
    "bss": BSSBaseConfig,
}


def get_base_config(business_type: str):
    """Get the base config class for a business type."""
    if business_type not in BASE_CONFIG_REGISTRY:
        raise ValueError(f"Unknown business type: {business_type}. Available: {list(BASE_CONFIG_REGISTRY.keys())}")
    return BASE_CONFIG_REGISTRY[business_type]


__all__ = ["BSSBaseConfig", "BASE_CONFIG_REGISTRY", "get_base_config"]
