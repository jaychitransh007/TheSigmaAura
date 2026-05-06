"""Phase 2 caching layer.

See docs/phase_2_cache_design.md for the design rationale.

Public surface so far:
  ProfileCluster, cluster_for(user) — 36-bucket cache-key clustering
"""
from .profile_cluster import ProfileCluster, cluster_for

__all__ = ["ProfileCluster", "cluster_for"]
