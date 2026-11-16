"""Deterministic spatial sampling of a triangle.

Each triangle is split 1-to-4 at edge midpoints until every leaf edge is at most
the requested length. Leaf centroids are the sample points; their barycentric
coordinates are kept so a sample can be rebuilt on the source triangle."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
Vec3 = Tuple[float, float, float]
Bary = Tuple[float, float, float]
MAX_SUBDIVISION_DEPTH = 10
DEGENERATE_AREA = 1e-14

def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

def _length(a: Vec3) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])

def _mid(a: Vec3, b: Vec3) -> Vec3:
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)

def _mid_bary(a: Bary, b: Bary) -> Bary:
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)

def triangle_area(a: Vec3, b: Vec3, c: Vec3) -> float:
    return 0.5 * _length(_cross(_sub(b, a), _sub(c, a)))

def geometric_normal(a: Vec3, b: Vec3, c: Vec3) -> Optional[Vec3]:
    n = _cross(_sub(b, a), _sub(c, a))
    length = _length(n)
    if length < 1e-12:
        return None
    return (n[0] / length, n[1] / length, n[2] / length)

@dataclass(frozen=True)
class SpatialProbe:
    position: Vec3
    barycentric: Bary
    leaf_max_edge: float
    probe_radius: float
    corner_barycentrics: Tuple[Bary, Bary, Bary] = ()

    def to_dict(self) -> Dict[str, object]:
        return {'position': [round(v, 9) for v in self.position], 'barycentric': [round(v, 9) for v in self.barycentric], 'leaf_max_edge': round(self.leaf_max_edge, 9), 'probe_radius': round(self.probe_radius, 9)}

@dataclass
class TriangleCover:
    probes: List[SpatialProbe] = field(default_factory=list)
    realized_max_leaf_edge: float = 0.0
    realized_max_probe_radius: float = 0.0
    depth_reached: int = 0
    degenerate: bool = False
    depth_exceeded: bool = False

    @property
    def usable(self) -> bool:
        return not self.degenerate and (not self.depth_exceeded) and bool(self.probes)

def cover_triangle(a: Vec3, b: Vec3, c: Vec3, r_requested: float, barycentrics: Tuple[Bary, Bary, Bary]=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), max_depth: int=MAX_SUBDIVISION_DEPTH) -> TriangleCover:
    if r_requested <= 0.0:
        raise ValueError('r_requested must be positive')
    cover = TriangleCover()
    if triangle_area(a, b, c) <= DEGENERATE_AREA:
        cover.degenerate = True
        return cover
    stack: List[Tuple[Vec3, Vec3, Vec3, Bary, Bary, Bary, int]] = [(a, b, c, barycentrics[0], barycentrics[1], barycentrics[2], 0)]
    while stack:
        pa, pb, pc, ba, bb, bc, depth = stack.pop()
        edges = (_length(_sub(pb, pa)), _length(_sub(pc, pb)), _length(_sub(pa, pc)))
        longest = max(edges)
        if longest > r_requested:
            if depth >= max_depth:
                cover.depth_exceeded = True
                continue
            mab, mbc, mca = (_mid(pa, pb), _mid(pb, pc), _mid(pc, pa))
            qab, qbc, qca = (_mid_bary(ba, bb), _mid_bary(bb, bc), _mid_bary(bc, ba))
            stack.extend([(mab, mbc, mca, qab, qbc, qca, depth + 1), (mca, mbc, pc, qca, qbc, bc, depth + 1), (mab, pb, mbc, qab, bb, qbc, depth + 1), (pa, mab, mca, ba, qab, qca, depth + 1)])
            continue
        centroid = ((pa[0] + pb[0] + pc[0]) / 3.0, (pa[1] + pb[1] + pc[1]) / 3.0, (pa[2] + pb[2] + pc[2]) / 3.0)
        bary = ((ba[0] + bb[0] + bc[0]) / 3.0, (ba[1] + bb[1] + bc[1]) / 3.0, (ba[2] + bb[2] + bc[2]) / 3.0)
        radius = max((_length(_sub(corner, centroid)) for corner in (pa, pb, pc)))
        cover.probes.append(SpatialProbe(centroid, bary, longest, radius, (ba, bb, bc)))
        cover.realized_max_leaf_edge = max(cover.realized_max_leaf_edge, longest)
        cover.realized_max_probe_radius = max(cover.realized_max_probe_radius, radius)
        cover.depth_reached = max(cover.depth_reached, depth)
    return cover

def barycentric_position(a: Vec3, b: Vec3, c: Vec3, bary: Bary) -> Vec3:
    return (a[0] * bary[0] + b[0] * bary[1] + c[0] * bary[2], a[1] * bary[0] + b[1] * bary[1] + c[1] * bary[2], a[2] * bary[0] + b[2] * bary[1] + c[2] * bary[2])
