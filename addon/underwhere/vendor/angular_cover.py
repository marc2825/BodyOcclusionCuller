"""Deterministic direction sampling over a hemisphere.

An octahedral hemisphere is subdivided until every great-circle edge is at most
the requested angle; the vertices are the sample directions, rotated onto a
surface normal when used."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
Vec3 = Tuple[float, float, float]
MAX_SUBDIVISION_LEVEL = 8

def _normalize(v: Vec3) -> Vec3:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length < 1e-15:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)

def great_circle_angle(a: Vec3, b: Vec3) -> float:
    dot = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))
    cross = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    norm = math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2)
    return math.atan2(norm, dot)

def _spherical_circumcentre(a: Vec3, b: Vec3, c: Vec3) -> Optional[Vec3]:
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    n = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
    length = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    if length < 1e-15:
        return None
    centre = (n[0] / length, n[1] / length, n[2] / length)
    centroid = _normalize((a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2]))
    if sum((x * y for x, y in zip(centre, centroid))) < 0.0:
        centre = (-centre[0], -centre[1], -centre[2])
    return centre

def _inside_spherical_triangle(x: Vec3, a: Vec3, b: Vec3, c: Vec3) -> bool:
    centroid = _normalize((a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2]))
    for p, q in ((a, b), (b, c), (c, a)):
        n = (p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0])
        reference = sum((u * v for u, v in zip(n, centroid)))
        candidate = sum((u * v for u, v in zip(n, x)))
        if reference * candidate < -1e-12:
            return False
    return True

def cell_cover_radius(a: Vec3, b: Vec3, c: Vec3) -> float:
    centre = _spherical_circumcentre(a, b, c)
    if centre is None:
        return 0.0
    if _inside_spherical_triangle(centre, a, b, c):
        return great_circle_angle(centre, a)
    return 0.5 * max(great_circle_angle(a, b), great_circle_angle(b, c), great_circle_angle(c, a))

def spherical_circumradius(a: Vec3, b: Vec3, c: Vec3) -> float:
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    n = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
    length = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    if length < 1e-15:
        return 0.0
    centre = (n[0] / length, n[1] / length, n[2] / length)
    centroid = _normalize((a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2]))
    if sum((x * y for x, y in zip(centre, centroid))) < 0.0:
        centre = (-centre[0], -centre[1], -centre[2])
    return great_circle_angle(centre, a)

@dataclass(frozen=True)
class AngularCover:
    epsilon_requested: float
    subdivision_level: int
    directions: Tuple[Vec3, ...]
    triangles: Tuple[Tuple[int, int, int], ...]
    realized_max_edge: float
    realized_covering_radius: float
    equator_direction_count: int
    cells_using_edge_fallback: int = 0

    @property
    def direction_count(self) -> int:
        return len(self.directions)

    def to_dict(self) -> Dict[str, object]:
        return {'epsilon_requested_rad': round(self.epsilon_requested, 12), 'epsilon_requested_deg': round(math.degrees(self.epsilon_requested), 9), 'subdivision_level': self.subdivision_level, 'direction_count': self.direction_count, 'triangle_count': len(self.triangles), 'realized_max_spherical_edge_rad': round(self.realized_max_edge, 12), 'realized_max_spherical_edge_deg': round(math.degrees(self.realized_max_edge), 9), 'realized_covering_radius_rad': round(self.realized_covering_radius, 12), 'realized_covering_radius_deg': round(math.degrees(self.realized_covering_radius), 9), 'covering_radius_is_upper_bound': True, 'cells_using_edge_fallback': self.cells_using_edge_fallback, 'equator_direction_count': self.equator_direction_count, 'bound_satisfied': self.realized_max_edge <= self.epsilon_requested + 1e-12}

def _initial_hemisphere() -> Tuple[List[Vec3], List[Tuple[int, int, int]]]:
    vertices: List[Vec3] = [(0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)]
    triangles = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1)]
    return (vertices, triangles)

def _subdivide(vertices: List[Vec3], triangles: List[Tuple[int, int, int]]) -> Tuple[List[Vec3], List[Tuple[int, int, int]]]:
    midpoint_cache: Dict[Tuple[int, int], int] = {}

    def midpoint(i: int, j: int) -> int:
        key = (i, j) if i < j else (j, i)
        if key in midpoint_cache:
            return midpoint_cache[key]
        a, b = (vertices[i], vertices[j])
        vertices.append(_normalize((a[0] + b[0], a[1] + b[1], a[2] + b[2])))
        midpoint_cache[key] = len(vertices) - 1
        return midpoint_cache[key]
    out: List[Tuple[int, int, int]] = []
    for a, b, c in triangles:
        ab, bc, ca = (midpoint(a, b), midpoint(b, c), midpoint(c, a))
        out.extend([(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)])
    return (vertices, out)

def _max_edge(vertices: Sequence[Vec3], triangles: Sequence[Tuple[int, int, int]]) -> float:
    worst = 0.0
    for a, b, c in triangles:
        for i, j in ((a, b), (b, c), (c, a)):
            worst = max(worst, great_circle_angle(vertices[i], vertices[j]))
    return worst

def build_hemisphere_cover(epsilon_requested: float, max_level: int=MAX_SUBDIVISION_LEVEL) -> AngularCover:
    if epsilon_requested <= 0.0:
        raise ValueError('epsilon_requested must be positive')
    vertices, triangles = _initial_hemisphere()
    level = 0
    realized = _max_edge(vertices, triangles)
    while realized > epsilon_requested and level < max_level:
        vertices, triangles = _subdivide(vertices, triangles)
        level += 1
        realized = _max_edge(vertices, triangles)
    equator = sum((1 for v in vertices if abs(v[2]) < 1e-12))
    covering = 0.0
    fallback = 0
    for a, b, c in triangles:
        va, vb, vc = (vertices[a], vertices[b], vertices[c])
        centre = _spherical_circumcentre(va, vb, vc)
        if centre is not None and (not _inside_spherical_triangle(centre, va, vb, vc)):
            fallback += 1
        covering = max(covering, cell_cover_radius(va, vb, vc))
    return AngularCover(epsilon_requested=epsilon_requested, subdivision_level=level, directions=tuple(vertices), triangles=tuple(triangles), realized_max_edge=realized, realized_covering_radius=covering, cells_using_edge_fallback=fallback, equator_direction_count=equator)
_CACHE: Dict[Tuple[float, int], AngularCover] = {}

def hemisphere_cover(epsilon_requested: float, max_level: int=MAX_SUBDIVISION_LEVEL) -> AngularCover:
    key = (float(epsilon_requested), int(max_level))
    if key not in _CACHE:
        _CACHE[key] = build_hemisphere_cover(epsilon_requested, max_level)
    return _CACHE[key]

def rotation_to_normal(normal: Vec3) -> Tuple[Vec3, Vec3, Vec3]:
    n = _normalize(normal)
    z = (0.0, 0.0, 1.0)
    dot = n[2]
    if dot > 1.0 - 1e-12:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    if dot < -1.0 + 1e-12:
        return ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0))
    axis = (z[1] * n[2] - z[2] * n[1], z[2] * n[0] - z[0] * n[2], z[0] * n[1] - z[1] * n[0])
    axis = _normalize(axis)
    c, s, t = (dot, math.sqrt(max(0.0, 1.0 - dot * dot)), 1.0 - dot)
    x, y, zz = axis
    return ((t * x * x + c, t * x * y - s * zz, t * x * zz + s * y), (t * x * y + s * zz, t * y * y + c, t * y * zz - s * x), (t * x * zz - s * y, t * y * zz + s * x, t * zz * zz + c))

def oriented_directions(cover: AngularCover, normal: Vec3) -> List[Vec3]:
    r0, r1, r2 = rotation_to_normal(normal)
    return [(r0[0] * d[0] + r0[1] * d[1] + r0[2] * d[2], r1[0] * d[0] + r1[1] * d[1] + r1[2] * d[2], r2[0] * d[0] + r2[1] * d[1] + r2[2] * d[2]) for d in cover.directions]
