"""多云检索平台包入口。"""

from .engine import (  # noqa: F401
    DATA_DIR,
    compare_ecs_price,
    find_equivalents,
    get_dataset,
    list_products,
    list_regions,
    list_specs,
    meta,
    search_docs,
)

__version__ = "1.0.0"
