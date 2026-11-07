# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric human base: skeleton, closed quad parts, eyes. No bpy."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

PRESETS = {
    "male": dict(height=1.78, head=1.0, shoulders=1.08, chest=1.06, waist=0.94, hips=0.96, arms=1.0, legs=1.0, bust=0.08),
    "female": dict(height=1.66, head=1.03, shoulders=0.90, chest=0.94, waist=0.74, hips=1.16, arms=0.97, legs=1.03, bust=0.72),
    "teen": dict(height=1.55, head=1.18, shoulders=0.88, chest=0.86, waist=0.80, hips=0.92, arms=0.98, legs=1.0, bust=0.16),
    "sturdy": dict(height=1.84, head=0.96, shoulders=1.20, chest=1.22, waist=1.14, hips=1.10, arms=1.0, legs=0.97, bust=0.22),
}


def defaults():
    return dict(PRESETS["male"], pose="A", fingers=True)


@dataclass
class Bone:
    name: str
    head: tuple
    tail: tuple
    parent: str | None
    roll: tuple
    connect: bool = False
    deform: bool = True


@dataclass
class Part:
    name: str
    verts: list
    faces: list


@dataclass
class Human:
    parts: list
    bones: list
    eyes: list
    height: float
    params: dict = field(default_factory=dict)


def _v(x, y, z):
    return (float(x), float(y), float(z))


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _len(a):
    return math.sqrt(_dot(a, a))


def _norm(a):
    L = _len(a)
    if L < 1e-8:
        return (0.0, 0.0, 1.0)
    return (a[0] / L, a[1] / L, a[2] / L)


def _clamp(t, a=0.0, b=1.0):
    return a if t < a else b if t > b else t


def _bump(x, center, width):
    if width <= 1e-6:
        return 0.0
    d = (x - center) / width
    return math.exp(-d * d * 1.4)


def _outward(face, verts, center):
    pts = [verts[i] for i in face]
    n = _cross(_sub(pts[1], pts[0]), _sub(pts[2], pts[0]))
    mid = (
        sum(p[0] for p in pts) / len(pts),
        sum(p[1] for p in pts) / len(pts),
        sum(p[2] for p in pts) / len(pts),
    )
    if _dot(n, _sub(mid, center)) < 0:
        return tuple(reversed(face))
    return tuple(face)


def _axes(tangent):
    t = _norm(tangent)
    up = (0.0, 0.0, 1.0)
    if abs(_dot(t, up)) > 0.86:
        side = (1.0, 0.0, 0.0)
        thick = _norm(_cross(side, t))
        if thick[1] > 0:
            thick = _mul(thick, -1.0)
            side = _mul(side, -1.0)
        return side, thick
    side = _norm(_cross(up, t))
    thick = _norm(_cross(t, side))
    return side, thick


def _frames(centers):
    frames = []
    prev_side = None
    for i in range(len(centers)):
        if i == 0:
            t = _sub(centers[1], centers[0])
        elif i == len(centers) - 1:
            t = _sub(centers[-1], centers[-2])
        else:
            t = _sub(centers[i + 1], centers[i - 1])
        t = _norm(t)
        if prev_side is None:
            side, thick = _axes(t)
        else:
            side = _sub(prev_side, _mul(t, _dot(prev_side, t)))
            if _len(side) < 1e-5:
                side, thick = _axes(t)
            else:
                side = _norm(side)
                thick = _norm(_cross(t, side))
        prev_side = side
        frames.append((t, side, thick))
    return frames


def tube(centers, r_side, r_thick, sides=12):
    """Closed loft. r_* is a float or a list per station."""
    n = len(centers)
    if n < 2:
        return [], []

    def rs(spec, i):
        if isinstance(spec, (int, float)):
            return float(spec)
        return float(spec[i])

    frames = _frames(centers)
    verts = []
    rings = []
    for i, c in enumerate(centers):
        _, side, thick = frames[i]
        ring = []
        rx, ry = rs(r_side, i), rs(r_thick, i)
        for k in range(sides):
            ang = math.tau * k / sides
            p = _add(c, _add(_mul(side, rx * math.cos(ang)), _mul(thick, ry * math.sin(ang))))
            ring.append(len(verts))
            verts.append(p)
        rings.append(ring)
    faces = []
    for i in range(n - 1):
        guide = _mul(_add(centers[i], centers[i + 1]), 0.5)
        for k in range(sides):
            faces.append(
                _outward(
                    (rings[i][k], rings[i][(k + 1) % sides], rings[i + 1][(k + 1) % sides], rings[i + 1][k]),
                    verts,
                    guide,
                )
            )
    # caps
    for i, sign in ((0, -1), (n - 1, 1)):
        _, side, thick = frames[i]
        c = _add(centers[i], _mul(frames[i][0], sign * 0.0001))
        hub = len(verts)
        verts.append(centers[i])
        outward_pt = _add(centers[i], _mul(frames[i][0], sign))
        for k in range(sides):
            faces.append(_outward((hub, rings[i][k], rings[i][(k + 1) % sides]), verts, outward_pt if sign > 0 else _sub(centers[i], frames[i][0])))
        _ = c
    return verts, faces


def sphere(center, radius, nu=14, nv=10, warp=None):
    verts = []
    north = len(verts)
    verts.append(_add(center, (0.0, 0.0, radius if warp is None else 0.0)))
    # rebuilt below to allow warp of poles
    verts = []
    for v in range(nv + 1):
        phi = math.pi * v / nv
        for u in range(nu if 0 < v < nv else 1):
            theta = math.tau * u / nu
            x = math.sin(phi) * math.cos(theta)
            y = math.sin(phi) * math.sin(theta)
            z = math.cos(phi)
            if warp:
                p = warp(phi, theta, x, y, z)
            else:
                p = (x * radius, y * radius, z * radius)
            verts.append(_add(center, p))
    faces = []
    def idx(v, u):
        if v == 0:
            return 0
        if v == nv:
            return len(verts) - 1
        return 1 + (v - 1) * nu + (u % nu)

    for u in range(nu):
        faces.append(_outward((idx(0, 0), idx(1, u), idx(1, u + 1)), verts, center))
    for v in range(1, nv - 1):
        for u in range(nu):
            faces.append(_outward((idx(v, u), idx(v, u + 1), idx(v + 1, u + 1), idx(v + 1, u)), verts, center))
    for u in range(nu):
        faces.append(_outward((idx(nv, 0), idx(nv - 1, u + 1), idx(nv - 1, u)), verts, center))
    _ = north
    return verts, faces


def mirror_part(part: Part, suffix_from=".L", suffix_to=".R") -> Part:
    verts = [(-x, y, z) for x, y, z in part.verts]
    faces = [tuple(reversed(f)) for f in part.faces]
    return Part(part.name.replace(suffix_from, suffix_to), verts, faces)


def mirror_bone(b: Bone) -> Bone:
    def mx(p):
        return (-p[0], p[1], p[2])

    parent = b.parent.replace(".L", ".R") if b.parent and ".L" in b.parent else b.parent
    return Bone(
        b.name.replace(".L", ".R"),
        mx(b.head),
        mx(b.tail),
        parent,
        (-b.roll[0], b.roll[1], b.roll[2]),
        b.connect,
        b.deform,
    )


def _lerp(a, b, t):
    return a + (b - a) * t


def skeleton(p):
    """Joints in meters, feet on z=0, facing -Y, character left is +X."""
    H = float(p["height"])
    head_k = float(p["head"])
    leg_k = float(p["legs"])
    arm_k = float(p["arms"])
    # Fractions of height, renormalized so sliders keep the crown at H.
    head = 0.128 * head_k
    neck = 0.042 * (0.82 + 0.18 * head_k)
    torso = 0.292
    leg = 0.538 * leg_k
    total = head + neck + torso + leg
    head, neck, torso, leg = (v / total for v in (head, neck, torso, leg))
    z_toe = 0.0
    z_ankle = H * leg * 0.085
    z_knee = H * (leg * 0.46)
    z_crotch = H * leg
    z_pelvis = z_crotch + H * torso * 0.16
    z_waist = z_crotch + H * torso * 0.42
    z_chest = z_crotch + H * torso * 0.74
    z_shoulder = z_crotch + H * torso * 0.96
    z_neck = z_shoulder + H * 0.012
    z_chin = z_neck + H * neck
    z_crown = H
    z_head = (z_chin + z_crown) * 0.5

    sh = H * 0.118 * float(p["shoulders"])
    hip_w = H * 0.092 * float(p["hips"])
    chest_w = H * 0.100 * float(p["chest"])
    waist_w = H * 0.072 * float(p["waist"])
    chest_d = H * 0.062 * (0.9 + 0.25 * (float(p["chest"]) - 1.0))
    waist_d = H * 0.050 * (0.92 + 0.2 * (float(p["waist"]) - 1.0))
    hip_d = H * 0.062 * (0.95 + 0.15 * (float(p["hips"]) - 1.0))
    hh = z_crown - z_chin
    hw = hh * 0.78
    hd = hh * 0.86

    pose = p.get("pose", "A")
    spread = math.radians(90.0 if pose == "T" else 34.0)
    elbow_bend = math.radians(6.0 if pose == "T" else 14.0)
    upper = H * 0.178 * arm_k
    fore = H * 0.152 * arm_k
    hand = H * 0.098 * (0.9 + 0.1 * arm_k)

    sx = sh * 0.98
    shoulder = (sx, -H * 0.012, z_shoulder)
    d_arm = _norm((math.sin(spread), -0.06, -math.cos(spread)))
    d_fore = _norm(_add(d_arm, (0.0, -math.sin(elbow_bend) * 0.35, -math.sin(elbow_bend))))
    elbow = _add(shoulder, _mul(d_arm, upper))
    wrist = _add(elbow, _mul(d_fore, fore))
    knuckle = _add(wrist, _mul(d_fore, hand * 0.62))
    finger_tip = _add(knuckle, _mul(d_fore, hand * 0.48))

    hip_x = hip_w * 0.46
    hip = (hip_x, -H * 0.004, z_crotch + hh * 0.08)
    knee = (hip_x * 0.96, -H * 0.018, z_knee)
    ankle = (hip_x * 0.90, H * 0.004, z_ankle)
    ball = (ankle[0] * 0.97, ankle[1] - H * 0.095, H * 0.020)
    toe = (ankle[0] * 0.97, ankle[1] - H * 0.148, H * 0.016)

    pelvis = (0.0, H * 0.004, z_pelvis)
    waist = (0.0, -H * 0.004, z_waist)
    chest = (0.0, -H * 0.012, z_chest)
    neck = (0.0, -H * 0.006, z_neck)
    head_c = (0.0, -H * 0.004, z_head + hh * 0.02)
    crown = (0.0, 0.0, z_crown)

    return {
        "H": H,
        "hh": hh,
        "hw": hw,
        "hd": hd,
        "sh": sh,
        "hip_w": hip_w,
        "chest_w": chest_w,
        "waist_w": waist_w,
        "chest_d": chest_d,
        "waist_d": waist_d,
        "hip_d": hip_d,
        "z_crotch": z_crotch,
        "z_waist": z_waist,
        "z_chest": z_chest,
        "z_shoulder": z_shoulder,
        "z_neck": z_neck,
        "z_chin": z_chin,
        "z_crown": z_crown,
        "pelvis": pelvis,
        "waist": waist,
        "chest": chest,
        "neck": neck,
        "head": head_c,
        "crown": crown,
        "chin": (0.0, head_c[1] - hd * 0.22, z_chin),
        "shoulder.L": shoulder,
        "elbow.L": elbow,
        "wrist.L": wrist,
        "knuckle.L": knuckle,
        "finger.L": finger_tip,
        "hip.L": hip,
        "knee.L": knee,
        "ankle.L": ankle,
        "ball.L": ball,
        "toe.L": toe,
        "d_fore": d_fore,
        "hand": hand,
        "z_toe": z_toe,
    }


def _head_warp(hh, hw, hd):
    def warp(phi, theta, x, y, z):
        # phi 0 crown → pi chin. theta 0 = +X, pi/2 = +Y (back).
        px = x * hw * 0.5
        py = y * hd * 0.5
        pz = z * hh * 0.5
        st = math.sin(theta)  # + back, - front
        front = max(0.0, -st)
        side = abs(math.cos(theta))
        if st > 0:
            py *= 1.08
        else:
            py *= 0.70
            px *= 0.97
        chin = _clamp((phi - 0.72) / 0.28)
        chin = chin * chin
        px *= 1.0 - 0.42 * chin
        py += chin * front * hd * 0.05  # chin sits, nose owns the forward push
        pz -= chin * hh * 0.05
        nose = _bump(phi, 0.66, 0.11) * (front ** 2.4)
        py -= nose * hd * 0.18
        brow = _bump(phi, 0.46, 0.07) * (front ** 1.6)
        py -= brow * hd * 0.07
        jaw = _bump(phi, 0.78, 0.08)
        px *= 1.0 + jaw * 0.06 * (1.0 - chin)
        return (px, py, pz)

    return warp


def _torso(sk, bust):
    H = sk["H"]
    stations = [
        (sk["z_crotch"] + H * 0.01, sk["hip_w"] * 0.34, sk["hip_d"] * 0.42, H * 0.006),
        (sk["z_crotch"] + H * 0.045, sk["hip_w"] * 0.78, sk["hip_d"] * 0.95, H * 0.012),
        (sk["pelvis"][2], sk["hip_w"] * 1.02, sk["hip_d"] * 1.12, H * 0.016),
        (_lerp(sk["pelvis"][2], sk["z_waist"], 0.55), sk["waist_w"] * 1.08, sk["waist_d"] * 1.05, H * 0.006),
        (sk["z_waist"], sk["waist_w"], sk["waist_d"] * 0.96, -H * 0.004),
        (_lerp(sk["z_waist"], sk["z_chest"], 0.48), _lerp(sk["waist_w"], sk["chest_w"], 0.55), _lerp(sk["waist_d"], sk["chest_d"], 0.6), -H * 0.016),
        (sk["z_chest"], sk["chest_w"] * 1.02, sk["chest_d"] * 1.05, -H * 0.026),
        (_lerp(sk["z_chest"], sk["z_shoulder"], 0.45), sk["chest_w"] * 0.96, sk["chest_d"] * 0.90, -H * 0.016),
        (sk["z_shoulder"] - H * 0.012, sk["sh"] * 0.46, sk["chest_d"] * 0.62, -H * 0.006),
        (sk["z_neck"] - H * 0.004, H * 0.046, H * 0.040, -H * 0.002),
    ]
    centers, rx, ry = [], [], []
    for z, a, b, y in stations:
        centers.append((0.0, y, z))
        rx.append(a)
        ry.append(b)
    verts, faces = tube(centers, rx, ry, sides=16)
    parts = [Part("torso", verts, faces)]
    if bust > 0.2:
        r = H * (0.028 + 0.035 * bust)
        cz = sk["z_chest"] + H * 0.01
        cy = -sk["chest_d"] * 0.72
        cx = sk["chest_w"] * 0.42
        ev, ef = sphere((cx, cy, cz), r, nu=10, nv=8)
        parts.append(Part("bust.L", ev, ef))
    return parts


def _neck_head(sk):
    H = sk["H"]
    hh, hw, hd = sk["hh"], sk["hw"], sk["hd"]
    neck_c = [
        (0.0, -H * 0.004, sk["z_neck"] - H * 0.01),
        (0.0, -H * 0.008, _lerp(sk["z_neck"], sk["z_chin"], 0.45)),
        (0.0, -H * 0.010, sk["z_chin"] - hh * 0.05),
    ]
    nv, nf = tube(neck_c, H * 0.038, H * 0.034, sides=12)
    center = sk["head"]
    # sphere() adds `center` to warp offsets, and warp already returns local offsets.
    hv, hf = sphere(center, 1.0, nu=18, nv=14, warp=_head_warp(hh, hw, hd))
    ear_phi_z = center[2] + hh * 0.01
    ear_y = center[1] + hd * 0.04
    ear_x = hw * 0.46 + hh * 0.06
    ear_r = hh * 0.11
    # flattened ear: scale a sphere by post-process
    ev, ef = sphere((0.0, 0.0, 0.0), 1.0, nu=8, nv=6)
    ev = [(x * ear_r * 0.45, y * ear_r * 0.22, z * ear_r * 0.72) for x, y, z in ev]
    ev = [(x + ear_x, y + ear_y, z + ear_phi_z) for x, y, z in ev]
    # Nose is its own volume so it reads from the front, not only in profile.
    nose_c = (center[0], center[1] - hd * 0.40, center[2] - hh * 0.06)
    nv_nose, nf_nose = sphere((0.0, 0.0, 0.0), 1.0, nu=8, nv=6)
    nv_nose = [(x * hh * 0.038, y * hh * 0.07, z * hh * 0.05) for x, y, z in nv_nose]
    nv_nose = [(x + nose_c[0], y + nose_c[1], z + nose_c[2]) for x, y, z in nv_nose]
    return [
        Part("neck", nv, nf),
        Part("head", hv, hf),
        Part("nose", nv_nose, nf_nose),
        Part("ear.L", ev, ef),
    ]


def _arm(sk):
    H = sk["H"]
    sh, el, wr, kn = sk["shoulder.L"], sk["elbow.L"], sk["wrist.L"], sk["knuckle.L"]
    # start inside the shoulder mass
    root = (
        sk["chest"][0] + (sh[0] - sk["chest"][0]) * 0.22,
        sh[1],
        sh[2] - H * 0.01,
    )
    centers = [root, sh, _lerp3(sh, el, 0.45), el, _lerp3(el, wr, 0.55), wr]
    thick = H * 0.046
    r = [
        thick * 1.55,
        thick * 1.45,
        thick * 0.98,
        thick * 0.80,
        thick * 0.90,
        thick * 0.64,
    ]
    verts, faces = tube(centers, r, [v * 0.92 for v in r], sides=12)
    parts = [Part("arm.L", verts, faces)]
    parts.append(_hand(sk))
    return parts


def _lerp3(a, b, t):
    return (
        _lerp(a[0], b[0], t),
        _lerp(a[1], b[1], t),
        _lerp(a[2], b[2], t),
    )


def _hand_axes(along):
    along = _norm(along)
    down = (0.0, 0.0, -1.0)
    normal = _sub(down, _mul(along, _dot(down, along)))
    if _len(normal) < 0.25:
        normal = (0.0, -1.0, 0.0)
    normal = _norm(normal)
    across = _norm(_cross(normal, along))
    return across, normal


def _hand(sk):
    H = sk["H"]
    wr, kn = sk["wrist.L"], sk["knuckle.L"]
    along = _norm(_sub(kn, wr))
    across, normal = _hand_axes(along)
    palm_len = _len(_sub(kn, wr))
    centers = [wr, _lerp3(wr, kn, 0.5), kn]
    rx = [H * 0.016, H * 0.020, H * 0.018]
    ry = [H * 0.013, H * 0.011, H * 0.010]
    verts, faces = _tube_frame(centers, across, normal, rx, ry, sides=10)
    parts = [Part("hand.L", verts, faces)]
    if sk.get("_fingers", True):
        parts.extend(_fingers(sk, kn, along, across, normal))
    else:
        tip = _add(kn, _mul(along, palm_len * 0.7))
        mv, mf = _tube_frame(
            [kn, _lerp3(kn, tip, 0.5), tip],
            across,
            normal,
            [H * 0.022, H * 0.018, H * 0.011],
            [H * 0.010, H * 0.008, H * 0.006],
            sides=8,
        )
        parts.append(Part("mitt.L", mv, mf))
    return _join_named(parts)


def _join_named(parts):
    """Merge a list of parts into one, keeping the first name."""
    verts = []
    faces = []
    for part in parts:
        shift = len(verts)
        verts.extend(part.verts)
        faces.extend(tuple(i + shift for i in f) for f in part.faces)
    return Part(parts[0].name if len(parts) == 1 else "hand.L", verts, faces)


def _tube_frame(centers, across0, thick0, r_side, r_thick, sides=10):
    frames_side = []
    frames_thick = []
    prev_a = across0
    prev_n = thick0
    for i in range(len(centers)):
        if i == 0:
            t = _sub(centers[min(1, len(centers) - 1)], centers[0])
        elif i == len(centers) - 1:
            t = _sub(centers[-1], centers[-2])
        else:
            t = _sub(centers[i + 1], centers[i - 1])
        t = _norm(t)
        a = _sub(prev_a, _mul(t, _dot(prev_a, t)))
        if _len(a) < 1e-5:
            a = prev_a
        a = _norm(a)
        n = _norm(_cross(t, a))
        if _dot(n, prev_n) < 0:
            n = _mul(n, -1.0)
            a = _mul(a, -1.0)
        prev_a, prev_n = a, n
        frames_side.append(a)
        frames_thick.append(n)
    verts, rings = [], []
    for i, c in enumerate(centers):
        ring = []
        for k in range(sides):
            ang = math.tau * k / sides
            p = _add(
                c,
                _add(
                    _mul(frames_side[i], r_side[i] * math.cos(ang)),
                    _mul(frames_thick[i], r_thick[i] * math.sin(ang)),
                ),
            )
            ring.append(len(verts))
            verts.append(p)
        rings.append(ring)
    faces = []
    for i in range(len(centers) - 1):
        guide = _mul(_add(centers[i], centers[i + 1]), 0.5)
        for k in range(sides):
            faces.append(
                _outward(
                    (rings[i][k], rings[i][(k + 1) % sides], rings[i + 1][(k + 1) % sides], rings[i + 1][k]),
                    verts,
                    guide,
                )
            )
    for i, sign in ((0, -1), (len(centers) - 1, 1)):
        hub = len(verts)
        verts.append(centers[i])
        t = _norm(_sub(centers[min(i + 1, len(centers) - 1)], centers[max(i - 1, 0)]))
        outward_pt = _add(centers[i], _mul(t, sign))
        for k in range(sides):
            faces.append(_outward((hub, rings[i][k], rings[i][(k + 1) % sides]), verts, outward_pt))
    return verts, faces


def _fingers(sk, knuckle, along, across, normal):
    H = sk["H"]
    # four fingers across `across`, thumb angled off the index side (toward -Y / front, which is one end of across)
    spreads = (-1.15, -0.38, 0.38, 1.15)
    names = ("f_index", "f_middle", "f_ring", "f_pinky")
    lengths = (0.050, 0.056, 0.052, 0.040)
    radii = (0.0064, 0.0068, 0.0064, 0.0056)
    parts = []
    for name, spread, length, radius in zip(names, spreads, lengths, radii):
        base = _add(knuckle, _mul(across, H * 0.020 * spread))
        base = _add(base, _mul(along, H * 0.010))
        direction = _norm(_add(along, _mul(across, 0.08 * spread)))
        mid = _add(base, _mul(direction, H * length * 0.55))
        # slight curl toward the palm normal (negative normal is into the palm if normal points out the back)
        mid = _add(mid, _mul(normal, H * 0.004))
        tip = _add(base, _mul(direction, H * length))
        tip = _add(tip, _mul(normal, H * 0.010))
        r = H * radius
        v, f = tube([_add(base, _mul(direction, -H * 0.006)), mid, tip], [r * 1.15, r * 0.95, r * 0.62], [r * 0.9, r * 0.75, r * 0.5], sides=7)
        parts.append(Part(f"{name}.L", v, f))
    # thumb
    thumb_dir = _norm(_add(_add(_mul(along, 0.35), _mul(across, -1.1)), _mul(normal, 0.45)))
    root = _add(knuckle, _add(_mul(across, -H * 0.02), _mul(along, -H * 0.02)))
    t1 = _add(root, _mul(thumb_dir, H * 0.028))
    t2 = _add(t1, _mul(thumb_dir, H * 0.026))
    r = H * 0.009
    v, f = tube([root, t1, t2], [r * 1.2, r, r * 0.7], [r, r * 0.8, r * 0.55], sides=7)
    parts.append(Part("thumb.L", v, f))
    return parts


def _leg(sk):
    H = sk["H"]
    hip, knee, ankle = sk["hip.L"], sk["knee.L"], sk["ankle.L"]
    root = (hip[0] * 0.72, hip[1] + H * 0.005, hip[2] + H * 0.02)
    thigh_r = H * 0.058 * (0.92 + 0.1 * (sk["hip_w"] / (H * 0.092)))
    knee_r = H * 0.040
    calf_r = H * 0.046
    ankle_r = H * 0.028
    mid_thigh = _lerp3(root, knee, 0.42)
    # calf sits back (+Y)
    calf = _lerp3(knee, ankle, 0.42)
    calf = (calf[0], calf[1] + H * 0.012, calf[2])
    centers = [root, mid_thigh, knee, calf, ankle]
    rx = [thigh_r, thigh_r * 0.92, knee_r, calf_r * 0.86, ankle_r]
    ry = [thigh_r * 0.96, thigh_r * 0.9, knee_r * 1.05, calf_r * 1.15, ankle_r]
    v, f = tube(centers, rx, ry, sides=12)
    parts = [Part("leg.L", v, f)]
    parts.append(_foot(sk))
    return parts


def _foot(sk):
    H = sk["H"]
    ankle, ball, toe = sk["ankle.L"], sk["ball.L"], sk["toe.L"]
    # Flat shoe-like foot: width on X, height on Z, path runs back-to-front.
    sole = H * 0.018
    heel = (ankle[0], ankle[1] + H * 0.028, sole)
    arch = (ankle[0] * 0.98, ankle[1] - H * 0.04, sole * 0.92)
    ball_c = (ankle[0] * 0.97, ankle[1] - H * 0.095, sole * 1.05)
    toe_c = (ankle[0] * 0.97, ankle[1] - H * 0.148, sole * 0.95)
    w = H * 0.034
    centers = [ankle, heel, arch, ball_c, toe_c]
    v, f = _tube_frame(
        centers,
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        [H * 0.024, w * 0.82, w * 0.92, w, w * 0.78],
        [H * 0.022, sole * 0.95, sole * 0.85, sole * 1.05, sole * 0.72],
        sides=10,
    )
    _ = (ball, toe)
    return Part("foot.L", v, f)


def _bones(sk, fingers):
    up = (0.0, 0.0, 1.0)
    back = (0.0, 1.0, 0.0)
    bones = [
        Bone("root", (0.0, 0.0, 0.0), sk["pelvis"], None, up, False, False),
        Bone("hips", sk["pelvis"], sk["waist"], "root", (0.0, -1.0, 0.0), False, True),
        Bone("spine", sk["waist"], _lerp3(sk["waist"], sk["chest"], 0.55), "hips", (0.0, -1.0, 0.0), True, True),
        Bone("chest", _lerp3(sk["waist"], sk["chest"], 0.55), sk["neck"], "spine", (0.0, -1.0, 0.0), True, True),
        Bone("neck", sk["neck"], (sk["head"][0], sk["head"][1], sk["z_chin"]), "chest", (0.0, -1.0, 0.0), True, True),
        Bone("head", (sk["head"][0], sk["head"][1], sk["z_chin"]), sk["crown"], "neck", (0.0, -1.0, 0.0), True, True),
    ]
    shoulder_head = (sk["neck"][0] + sk["shoulder.L"][0] * 0.15, sk["neck"][1], sk["z_shoulder"])
    bones.append(Bone("shoulder.L", shoulder_head, sk["shoulder.L"], "chest", up, False, True))
    bones.append(Bone("upper_arm.L", sk["shoulder.L"], sk["elbow.L"], "shoulder.L", up, True, True))
    bones.append(Bone("forearm.L", sk["elbow.L"], sk["wrist.L"], "upper_arm.L", up, True, True))
    bones.append(Bone("hand.L", sk["wrist.L"], sk["knuckle.L"], "forearm.L", up, True, True))
    if fingers:
        along = sk["d_fore"]
        across, _normal = _hand_axes(along)
        spreads = {"f_index": -1.15, "f_middle": -0.38, "f_ring": 0.38, "f_pinky": 1.15}
        lengths = {"f_index": 0.050, "f_middle": 0.056, "f_ring": 0.052, "f_pinky": 0.040}
        for name in ("f_index", "f_middle", "f_ring", "f_pinky"):
            base = _add(sk["knuckle.L"], _mul(across, sk["H"] * 0.020 * spreads[name]))
            base = _add(base, _mul(along, sk["H"] * 0.010))
            direction = _norm(_add(along, _mul(across, 0.08 * spreads[name])))
            tip = _add(base, _mul(direction, sk["H"] * lengths[name]))
            mid = _lerp3(base, tip, 0.5)
            bones.append(Bone(f"{name}.01.L", base, mid, "hand.L", up, False, True))
            bones.append(Bone(f"{name}.02.L", mid, tip, f"{name}.01.L", up, True, True))
        thumb_dir = _norm(_add(_add(_mul(along, 0.35), _mul(across, -1.1)), (0.0, 0.0, 0.35)))
        root = _add(sk["knuckle.L"], _add(_mul(across, -sk["H"] * 0.02), _mul(along, -sk["H"] * 0.02)))
        t1 = _add(root, _mul(thumb_dir, sk["H"] * 0.028))
        t2 = _add(t1, _mul(thumb_dir, sk["H"] * 0.026))
        bones.append(Bone("thumb.01.L", root, t1, "hand.L", up, False, True))
        bones.append(Bone("thumb.02.L", t1, t2, "thumb.01.L", up, True, True))
    bones.append(Bone("thigh.L", sk["hip.L"], sk["knee.L"], "hips", back, False, True))
    bones.append(Bone("shin.L", sk["knee.L"], sk["ankle.L"], "thigh.L", back, True, True))
    bones.append(Bone("foot.L", sk["ankle.L"], sk["ball.L"], "shin.L", up, True, True))
    bones.append(Bone("toe.L", sk["ball.L"], sk["toe.L"], "foot.L", up, True, True))
    return bones


def _eyes(sk):
    hh = sk["hh"]
    center = sk["head"]
    z = center[2] - hh * 0.02
    y = center[1] - sk["hd"] * 0.34
    x = sk["hw"] * 0.23
    r = hh * 0.075
    return [((x, y, z), r), ((-x, y, z), r)]


def build_human(params=None) -> Human:
    p = defaults()
    if params:
        p.update({k: v for k, v in params.items() if v is not None})
    p["fingers"] = bool(p.get("fingers", True))
    p["pose"] = "T" if p.get("pose") == "T" else "A"
    sk = skeleton(p)
    sk["_fingers"] = p["fingers"]
    parts = []
    parts.extend(_torso(sk, float(p.get("bust", 0.0))))
    parts.extend(_neck_head(sk))
    arm_bits = _arm(sk)
    # _arm returns [arm, hand-joined]
    parts.extend(arm_bits)
    parts.extend(_leg(sk))
    mirrored = []
    for part in parts:
        if part.name.endswith(".L"):
            mirrored.append(mirror_part(part))
    parts.extend(mirrored)
    if float(p.get("bust", 0.0)) > 0.2:
        # bust.L already in parts; mirror_part handles it
        pass
    bones = _bones(sk, p["fingers"])
    bones.extend(mirror_bone(b) for b in bones if b.name.endswith(".L"))
    return Human(parts=parts, bones=bones, eyes=_eyes(sk), height=p["height"], params=p)


def edge_report(part: Part):
    from collections import Counter

    c = Counter()
    for f in part.faces:
        idx = list(f)
        for i in range(len(idx)):
            a, b = idx[i], idx[(i + 1) % len(idx)]
            c[tuple(sorted((a, b)))] += 1
    bad = sum(1 for n in c.values() if n != 2)
    return len(part.verts), len(part.faces), bad


def bounds(human: Human):
    xs, ys, zs = [], [], []
    for part in human.parts:
        for x, y, z in part.verts:
            xs.append(x)
            ys.append(y)
            zs.append(z)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)
