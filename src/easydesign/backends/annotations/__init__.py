"""轻量、可审计的科学 annotation 数据源 adapter。"""

from .uniprot import FetchedUniProtRecord, UniProtAnnotationAdapter

__all__ = ["FetchedUniProtRecord", "UniProtAnnotationAdapter"]
