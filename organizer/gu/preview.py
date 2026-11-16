"""Quick PNG previews of STL files (for inspection only, not for customers).

Uses matplotlib so it works without a graphics card. Large meshes are
simplified by sampling triangles, which is fine for a visual check.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

PALETTE = ["#d9560a", "#2f6db5", "#2f7d4f", "#8a4fb3", "#c2a20a", "#b8336a", "#3a8f8f", "#6b6b6b"]


def render_png(
    stl_paths: list[Path],
    out_png: Path,
    explode: float = 0.0,
    elev: float = 35,
    azim: float = -60,
    max_faces: int = 60000,
    title: str | None = None,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    meshes = [trimesh.load(p, force="mesh") for p in stl_paths]
    centre = np.mean([m.bounds.mean(axis=0) for m in meshes], axis=0)
    fig = plt.figure(figsize=(9, 7), dpi=110)
    ax = fig.add_subplot(111, projection="3d")
    light = np.array([0.4, -0.5, 1.0])
    light /= np.linalg.norm(light)
    lo_all, hi_all = [], []
    budget = max(2000, max_faces // max(1, len(meshes)))
    for i, m in enumerate(meshes):
        offset = np.zeros(3)
        if explode:
            d = m.bounds.mean(axis=0) - centre
            d[2] = 0
            n = np.linalg.norm(d)
            if n > 1e-6:
                offset = d / n * explode
        tris = m.triangles + offset
        normals = m.face_normals
        if len(tris) > budget:
            idx = np.random.default_rng(0).choice(len(tris), budget, replace=False)
            # keep large triangles (flat faces) so surfaces do not look broken
            areas = m.area_faces
            big = np.argsort(areas)[-budget // 2 :]
            idx = np.unique(np.concatenate([idx[: budget // 2], big]))
            tris, normals = tris[idx], normals[idx]
        shade = 0.45 + 0.55 * np.clip(normals @ light, 0, 1)
        base = np.array(matplotlib.colors.to_rgb(PALETTE[i % len(PALETTE)]))
        colours = np.clip(base[None, :] * shade[:, None] + 0.08, 0, 1)
        coll = Poly3DCollection(tris, facecolors=colours, edgecolors="none", linewidths=0)
        ax.add_collection3d(coll)
        lo_all.append(tris.reshape(-1, 3).min(axis=0))
        hi_all.append(tris.reshape(-1, 3).max(axis=0))
    lo, hi = np.min(lo_all, axis=0), np.max(hi_all, axis=0)
    span = (hi - lo).max()
    mid = (hi + lo) / 2
    for setter, c in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), mid):
        setter(c - span / 2, c + span / 2)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if title:
        ax.set_title(title)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)
    return out_png
