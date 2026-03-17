from .config_registry import load_garment_attributes


ENUM_ATTRIBUTES, TEXT_ATTRIBUTES = load_garment_attributes()
ATTRIBUTE_NAMES = list(ENUM_ATTRIBUTES.keys()) + TEXT_ATTRIBUTES
