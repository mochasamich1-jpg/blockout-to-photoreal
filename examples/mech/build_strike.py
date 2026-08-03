"""
CATAPULT STRIKE - a Catapult walks up a city street and salvos a tower block.

9:16 blockout for the LTX-2.3 + 3DREAL render-to-real pipeline.

Shot:
  0.0 - 7.0s   the mech walks toward the tower, seven heavy strides
  7.0 - 7.8s   it plants into a braced split stance
  7.9s onward  LRM salvos out of both pods, arcing over and into the tower
  10.0s        the impact zone gives way
  11.5s        the top section topples

Pipeline rules this obeys (all learned the hard way, see the memory file):
  - Material colours are mandatory and must be SEPARATED. A grey blockout
    barely transforms.
  - Shape language beats detail. Angular blocks read as real machinery.
  - Do NOT model smoke, dust or fire. Modelled volumes come back as solid
    slabs; the prompt gets them for free and better.
  - Contrast by HUE, not luminance. Every hot element is saturated orange.
  - Prior strength caps the result, so the CITY carries the realism: asphalt,
    concrete, glass, cars, rebar and collapse all have huge photographic
    priors. The mech is built as industrial machinery, not smooth sci-fi.
  - Keep the WHOLE mech silhouette in frame at all times. When the legs leave
    frame the model invents running gear and returns a tracked vehicle.

Usage: blender -b -P build_strike.py -- <outdir>
       STRIKE_PROBE=1,90,200 renders stills instead of the sequence.
"""
import bpy, bmesh, math, random, sys, os
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catapult_rig as cr

random.seed(41)
rng = random.Random(41)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUTDIR = argv[0] if argv else "//"

FPS = 24
FRAMES = 361                      # 15.04 s, and 8n+1 for the LTX latent
# 9:16, both divisible by 32. NOT higher: 896x1600 was tried at sigma 0.95 and
# came back markedly worse, with the hull smoothed into a propane-tank drum and
# the legs thinned into spindly insect limbs. More pixels at a fixed sigma gave
# the model more room to invent over a 361-frame clip rather than more structure
# to preserve. The canyon's "render bigger" result does not transfer to a
# weak-prior subject at this length.
W, H = 704, 1280

# ------------------------------------------------------------------- beats
F_DECEL     = 140                 # start slowing
F_WALK_END  = 168                 # forward travel stops
F_SET       = 188                 # braced, both feet planted
F_FIRE      = 196                 # first salvo leaves the tubes
SALVO_GAP   = 27
F_IMPACT    = F_FIRE + 20         # first rounds land
F_FAIL      = 250                 # impact zone gives way
F_TOPPLE    = 276                 # top section starts to go

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
# Set the frame aspect NOW, not down in the render block. The framing assert
# uses world_to_camera_view, which reads the render resolution to work out the
# sensor fit; against Blender's default landscape 1920x1080 it reported crops
# that do not exist in the real 9:16 frame.
scene.render.resolution_x, scene.render.resolution_y = W, H

SCENE_PAL = dict(cr.PALETTE)
SCENE_PAL.update({
    "asphalt":  (0.225, 0.220, 0.215),
    "kerb":     (0.430, 0.425, 0.410),
    "line":     (0.740, 0.710, 0.530),
    "concrete": (0.680, 0.660, 0.615),
    "concrete2":(0.470, 0.458, 0.435),
    "glass":    (0.115, 0.195, 0.245),
    "glasslit": (0.500, 0.440, 0.250),
    "rebar":    (0.420, 0.190, 0.085),
    "car1":     (0.560, 0.140, 0.110),
    "car2":     (0.130, 0.180, 0.330),
    "car3":     (0.640, 0.630, 0.610),
    "car4":     (0.120, 0.125, 0.135),
    "cargl":    (0.135, 0.185, 0.215),
})
cr.PALETTE = SCENE_PAL
box, cyl, empty = cr.box, cr.cyl, cr.empty


def chunk(name, loc, scale, m, rough=0.30):
    """Irregular angular block. These read as real quarried rubble; smooth
    displaced spheres dissolve into mush and visible triangles read as CG."""
    bpy.ops.mesh.primitive_cube_add(location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
    for v in bm.verts:
        v.co += Vector((rng.uniform(-rough, rough), rng.uniform(-rough, rough),
                        rng.uniform(-rough, rough)))
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = False
    ob.data.materials.append(cr.mat(m))
    return ob


def key(ob, frame, loc=None, rot=None, scl=None):
    if loc is not None:
        ob.location = Vector(loc); ob.keyframe_insert("location", frame=frame)
    if rot is not None:
        ob.rotation_euler = rot; ob.keyframe_insert("rotation_euler", frame=frame)
    if scl is not None:
        ob.scale = Vector(scl); ob.keyframe_insert("scale", frame=frame)


prefs = bpy.context.preferences.edit
prefs.keyframe_new_interpolation_type = 'LINEAR'

# ========================================================== street and ground
box("road", (0, -62, -0.02), (34, 92, 0.02), "asphalt")
box("plaza", (0, 6, -0.02), (54, 26, 0.02), "asphalt")
for i in range(26):
    box(f"lane_{i}", (0, -150 + i * 7.4, 0.015), (0.42, 2.6, 0.015), "line")
box("kerb_l", (-34, -62, 0.36), (1.3, 92, 0.36), "kerb")
box("kerb_r", (34, -62, 0.36), (1.3, 92, 0.36), "kerb")
box("walk_l", (-42, -62, 0.30), (8, 92, 0.30), "concrete2")
box("walk_r", (42, -62, 0.30), (8, 92, 0.30), "concrete2")

# Parked cars: cheap, and they carry an enormous photographic prior, which is
# what actually sells the scale of the mech next to them.
for i in range(16):
    side = -1 if i % 2 else 1
    cx = side * rng.uniform(29.5, 31.5)
    cy = -142 + i * 9.6 + rng.uniform(-1.4, 1.4)
    if -66 < cy < -38:
        continue                          # keep the mech's path clear
    body = rng.choice(("car1", "car2", "car3", "car4"))
    yaw = rng.uniform(-0.05, 0.05)
    box(f"car_{i}", (cx, cy, 0.78), (1.02, 2.35, 0.52), body, rot=(0, 0, yaw))
    box(f"carcab_{i}", (cx, cy - 0.15, 1.42), (0.94, 1.25, 0.42), body, rot=(0, 0, yaw))
    box(f"cargl_{i}", (cx, cy - 0.15, 1.50), (0.96, 1.10, 0.30), "cargl", rot=(0, 0, yaw))
    for wy in (-1.55, 1.55):
        for wx in (-1.0, 1.0):
            cyl(f"cw_{i}_{wx}_{wy}", (cx + wx, cy + wy, 0.40),
                (0.40, 0.40, 0.18), "car4", rot=(0, math.radians(90), 0), verts=8)

# ============================================================ target building
BW, BD = 5, 5                 # blocks per side
BS = 4.6                      # block size
# 13 floors, not 17. A 70 m tower cannot share a 9:16 frame with a 16 m mech
# without tilting the camera up far enough to drop the mech's feet out of
# frame, and a cropped mech is the one failure that ruins the whole render.
# The shorter tower also makes the mech read as a mass rather than a detail.
FLOORS = 13
FH = 4.0
BX0 = -(BW - 1) * BS / 2
BY0 = -(BD - 1) * BS / 2      # -9.2; the near face sits at BY0 - BS/2

blocks = []
for fz in range(FLOORS):
    z = 2.0 + fz * FH
    band = "glass" if fz % 2 else "concrete"
    for ix in range(BW):
        for iy in range(BD):
            if not (ix in (0, BW - 1) or iy in (0, BD - 1)):
                continue      # shell only, so it can come apart
            m = "concrete2" if fz % 6 == 0 else band
            ob = box(f"blk_{fz}_{ix}_{iy}",
                     (BX0 + ix * BS, BY0 + iy * BS, z),
                     (BS / 2 * 0.98, BS / 2 * 0.98, FH / 2 * 0.98), m)
            blocks.append((ob, ix, iy, fz))

box("podium", (0, 0, 1.0), (BW * BS / 2 + 1.6, BD * BS / 2 + 1.6, 1.0), "concrete2")
# Dark core inside the shell. Without it, blowing the facade open just reveals
# sky through the far wall and the wound never reads as a wound; with it the
# hole opens onto a gutted, shadowed interior with floor slabs in it.
box("core", (0, 0, 2.0 + FLOORS * FH * 0.5),
    (BW * BS / 2 - BS * 0.9, BD * BS / 2 - BS * 0.9, FLOORS * FH * 0.5), "joint")
for fz in range(FLOORS):
    box(f"slab_{fz}", (0, 0, 2.0 + fz * FH - FH / 2),
        (BW * BS / 2 - BS * 0.55, BD * BS / 2 - BS * 0.55, 0.22), "concrete2")
# The roof needs a parapet and real plant. A bare slab, once the top section
# tips, presents one enormous flat quad to camera and reads as a sheet of card.
ROOF_Z = 2.0 + FLOORS * FH
box("roofslab", (0, 0, ROOF_Z), (BW * BS / 2, BD * BS / 2, 0.7), "concrete2")
for sgn in (-1, 1):
    box(f"parapetx{sgn}", (sgn * (BW * BS / 2 - 0.4), 0, ROOF_Z + 1.3),
        (0.4, BD * BS / 2, 0.9), "concrete")
    box(f"parapety{sgn}", (0, sgn * (BD * BS / 2 - 0.4), ROOF_Z + 1.3),
        (BW * BS / 2, 0.4, 0.9), "concrete")
box("plant", (3.5, 2.0, ROOF_Z + 2.6), (3.4, 3.0, 1.9), "concrete2")
box("plant2", (-4.2, 3.4, ROOF_Z + 1.9), (2.0, 1.7, 1.2), "kerb")
for i in range(3):
    cyl(f"vent_{i}", (-5.0 + i * 2.2, -3.6, ROOF_Z + 1.9),
        (0.62, 0.62, 1.1), "kerb", verts=10)
cyl("mast", (-4.0, -2.0, ROOF_Z + 5.2), (0.16, 0.16, 4.0), "rebar", verts=6)

# neighbouring towers for depth, plain and unanimated
for nx, ny, nh, nw in ((-52, 30, 74, 10), (54, 40, 92, 11), (-58, -26, 50, 9),
                       (60, -14, 62, 10), (-48, -78, 44, 9), (52, -86, 56, 10)):
    for fz in range(int(nh / 5)):
        band = "glass" if fz % 2 else "concrete2"
        box(f"nb_{nx}_{ny}_{fz}", (nx, ny, 3 + fz * 5), (nw, nw, 2.4), band)

# ================================================================= the mech
# +Y is FORWARD. Aim arithmetic: rotating +Y by theta gives (-sin t, cos t),
# so hitting a target offset (dx, dy) needs theta = atan2(-dx, dy). Getting
# this sign wrong fires the salvo 15 degrees wide and it is invisible in a
# blockout (finding 27).
MX_END, MY_END = 7.0, -52.0
TOWER_Y = BY0 - BS / 2                    # -11.5, the near face
YAW = math.atan2(-(0.0 - MX_END), TOWER_Y - MY_END)
FWD = Vector((-math.sin(YAW), math.cos(YAW), 0.0))

mech = cr.Catapult(name="cat", loc=(MX_END, MY_END, 0), yaw=YAW)

# ---- gait, driven by DISTANCE so a planted foot can never slide -----------
# A 4.2 reach put the trailing leg at near-full extension every step, which
# renders as a lunge rather than a walk. Shorter reach plus less total travel
# keeps the cadence at ~0.87 s per step, which is where a 65-tonne machine
# should sit.
STRIDE_A  = 3.40                          # foot reach ahead of the hip
DUTY      = 0.62                          # fraction of the cycle in stance
D_CYCLE   = 2 * STRIDE_A / DUTY           # ground covered per leg cycle
LIFT      = 1.65
DIST_TOT  = 40.0

_ramp = (F_WALK_END - F_DECEL)
V0 = DIST_TOT / ((F_DECEL - 1) + _ramp * 0.5)


def speed(f):
    if f <= F_DECEL:
        return V0
    if f >= F_WALK_END:
        return 0.0
    return V0 * (1.0 - (f - F_DECEL) / _ramp)


_dist = [0.0]
for f in range(2, FRAMES + 1):
    _dist.append(_dist[-1] + speed(f))
TRAVELLED = _dist[-1]
START = Vector((MX_END, MY_END, 0)) - FWD * TRAVELLED


def root_pos(f):
    return START + FWD * _dist[f - 1]


def ease(t):
    return t * t * (3.0 - 2.0 * t)


def foot_state(leg_phase, d):
    """World-space foot target for one leg at travelled distance d.
    Returns (offset_along_forward, lift, pitch). Stance holds the plant
    position exactly, which is what keeps the contact from sliding."""
    ph = d / D_CYCLE + leg_phase
    k = math.floor(ph)
    u = ph - k
    d_plant = (k - leg_phase) * D_CYCLE
    y_plant = d_plant + STRIDE_A
    if u < DUTY:
        return y_plant, 0.0, 0.0
    s = (u - DUTY) / (1.0 - DUTY)
    y_next = y_plant + D_CYCLE
    y = y_plant + (y_next - y_plant) * ease(s)
    lift = LIFT * math.sin(math.pi * s) ** 0.85
    pitch = math.radians(16.0) * math.sin(math.pi * s * 1.1)
    return y, lift, pitch


# Final braced split stance: one foot forward, one back, ready to eat recoil.
# Letting each leg simply finish its natural step leaves the feet a full
# 2*STRIDE_A apart, which renders as a strained lunge rather than a firing
# platform, so the split is closed to a deliberate BRACE either side of the hip.
BRACE = 2.9
FINAL = {}
_lead = {}
for side, phase in (("l", 0.0), ("r", 0.5)):
    y, _, _ = foot_state(phase, TRAVELLED)
    ph = TRAVELLED / D_CYCLE + phase
    if (ph - math.floor(ph)) >= DUTY:                  # caught mid-swing
        y = (math.floor(ph) - phase) * D_CYCLE + STRIDE_A + D_CYCLE
    _lead[side] = y
for side in ("l", "r"):
    other = "r" if side == "l" else "l"
    FINAL[side] = TRAVELLED + (BRACE if _lead[side] > _lead[other] else -BRACE)

FIRE_FRAMES = list(range(F_FIRE, FRAMES - 24, SALVO_GAP))


def torso_state(f):
    """Lean into the walk, brace on planting, then kick back on every salvo."""
    pitch = math.radians(5.0)
    yawr = 0.0
    if f < F_WALK_END:
        pitch += math.radians(1.6) * math.sin(2 * math.pi * _dist[f - 1] / D_CYCLE)
        yawr = math.radians(2.2) * math.sin(2 * math.pi * _dist[f - 1] / D_CYCLE)
    elif f < F_FIRE:
        t = min(1.0, (f - F_WALK_END) / float(F_FIRE - F_WALK_END))
        pitch += math.radians(-3.0) * ease(t)          # settle back, anticipation
    else:
        pitch += math.radians(-3.0)
        for ff in FIRE_FRAMES:
            dt = f - ff
            if 0 <= dt < 16:
                pitch += math.radians(-4.6) * math.exp(-dt / 4.0) * math.cos(dt * 0.55)
    return pitch, yawr


for f in range(1, FRAMES + 1):
    d = _dist[f - 1]
    p = root_pos(f)
    mech.root.location = p
    mech.root.rotation_euler = (0, 0, YAW)

    blend = 0.0
    if f > F_WALK_END:
        blend = min(1.0, (f - F_WALK_END) / float(F_SET - F_WALK_END))

    # pelvis: bob twice per cycle, sway toward the stance leg, settle on planting
    bob = -0.30 * abs(math.sin(math.pi * d / D_CYCLE))
    sway = 0.16 * math.sin(2 * math.pi * d / D_CYCLE)
    if f > F_WALK_END:
        bob = bob * (1 - blend) - 0.34 * blend
        sway *= (1 - blend)
    for ff in FIRE_FRAMES:
        dt = f - ff
        if 0 <= dt < 18:
            bob += -0.26 * math.exp(-dt / 5.0)
    mech.pelvis.location = (0, 0, cr.HIP_Z + bob)
    mech.pelvis.rotation_euler = (0, 0, 0)

    tp, ty = torso_state(f)
    mech.torso.location = (sway, 0, cr.TORSO_DZ)
    mech.torso.rotation_euler = (tp, 0, ty)

    bpy.context.view_layer.update()
    hip_world_d = d
    for side, phase in (("l", 0.0), ("r", 0.5)):
        y, lift, pitch = foot_state(phase, d)
        if blend > 0.0:
            e = ease(blend)
            y = y * (1 - e) + FINAL[side] * e
            lift *= (1 - e)
            pitch *= (1 - e)
        # foot_state works in travel-distance space; convert to world
        along = y - hip_world_d
        base = p + FWD * along
        sx = -cr.HIP_X if side == "l" else cr.HIP_X
        lat = Vector((-FWD.y, FWD.x, 0.0)) * sx
        mech.pose_leg(side, (base.x - lat.x, base.y - lat.y, lift), foot_pitch=pitch)

    for side in ("l", "r"):
        rec = 0.0
        for ff in FIRE_FRAMES:
            dt = f - ff
            if 0 <= dt < 14:
                rec += math.radians(-7.0) * math.exp(-dt / 3.5)
        mech.pitch_pod(side, rec)

    mech.key_all(f)

# ============================================= muzzle flash, missiles, impacts
bpy.context.scene.frame_set(F_FIRE)
bpy.context.view_layer.update()
MUZZLE = {s: mech.muzzles[s].matrix_world.translation.copy() for s in ("l", "r")}

def blob(name, m):
    """Small faceted sphere. Used for every hot element: a flat disc seen
    face-on renders as a solid gold coin, and a wide cylinder seen end-on
    renders as a scalloped yellow cloud. Both happened."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.0,
                                          location=(0, 0, -200))
    ob = bpy.context.active_object
    ob.name = name
    for p in ob.data.polygons:
        p.use_smooth = False
    ob.data.materials.append(cr.mat(m))
    return ob


# Flash sits at the TOP-FRONT lip of each pod. The camera lives on a rear
# quarter, so anything placed squarely on the launcher face is occluded by
# the pod itself and the firing beat reads as nothing happening.
flashes = []
LAT = Vector((-FWD.y, FWD.x, 0.0))
for side in ("l", "r"):
    m = MUZZLE[side]
    for k, off in enumerate((-0.75, 0.0, 0.75)):
        fl = blob(f"flash_{side}{k}", "flash")
        fl.location = (m.x + LAT.x * off + FWD.x * 0.55,
                       m.y + LAT.y * off + FWD.y * 0.55, m.z + 1.75)
        flashes.append(fl)
for fl in flashes:
    key(fl, 1, scl=(0.001, 0.001, 0.001))
    for ff in FIRE_FRAMES:
        key(fl, ff - 1, scl=(0.001, 0.001, 0.001))
        key(fl, ff + 1, scl=(0.95, 0.95, 0.95))
        key(fl, ff + 5, scl=(0.001, 0.001, 0.001))

IMPACT_LO, IMPACT_HI = 3, 9


def impact_point(i):
    return Vector((rng.uniform(BX0 - 1.2, -BX0 + 1.2), TOWER_Y + 0.4,
                   2.0 + rng.uniform(IMPACT_LO + 0.2, IMPACT_HI - 0.4) * FH))


# A pool of missile bodies reused across salvos. Only the bodies are modelled:
# a modelled exhaust trail always comes back as a solid plank (finding 7).
POOL = 20
# Long axis on +Y to match the aiming convention used for the flight keys.
# Kept short: at 2.6 units the first pass read as a flying brown plank.
missiles = [box(f"msl_{i}", (0, 0, -200), (0.22, 0.75, 0.22), "tracer")
            for i in range(POOL)]
for m in missiles:
    key(m, 1, loc=(0, 0, -200))

impacts = []
for i in range(len(FIRE_FRAMES) * 6):
    impacts.append(blob(f"imp_{i}", "flash"))
    key(impacts[-1], 1, scl=(0.001, 0.001, 0.001))

imp_i = 0
for si, ff in enumerate(FIRE_FRAMES):
    for k in range(POOL):
        side = "l" if k < POOL // 2 else "r"
        src = MUZZLE[side].copy()
        lat = Vector((-FWD.y, FWD.x, 0.0)) * rng.uniform(-0.9, 0.9)
        src += lat + Vector((0, 0, rng.uniform(-1.7, 1.7)))
        tgt = impact_point(k)
        t0 = ff + (k % 10) * 2 + rng.randint(0, 2)
        flight = 20 + rng.randint(-2, 4)
        if t0 + flight > FRAMES:
            continue
        m = missiles[k]
        apex = max(src.z, tgt.z) + rng.uniform(4.0, 8.5)
        key(m, t0 - 1, loc=(src.x, src.y, -200))
        prev = src
        for st in range(0, 7):
            u = st / 6.0
            pt = src.lerp(tgt, u)
            pt.z = (1 - u) ** 2 * src.z + 2 * (1 - u) * u * apex + u * u * tgt.z
            d = (pt - prev) if st else (tgt - src)
            yaw = math.atan2(-d.x, d.y)
            pitchr = -math.atan2(d.z, math.hypot(d.x, d.y))
            key(m, int(t0 + flight * u), loc=pt, rot=(pitchr, 0, yaw))
            prev = pt
        key(m, int(t0 + flight) + 1, loc=(tgt.x, tgt.y, -200))
        if k % 5 == 0 and imp_i < len(impacts):
            imp = impacts[imp_i]; imp_i += 1
            key(imp, int(t0 + flight) - 1, loc=(tgt.x, TOWER_Y - 1.1, tgt.z),
                scl=(0.001, 0.001, 0.001))
            key(imp, int(t0 + flight) + 1, scl=(0.90, 0.80, 0.90))
            key(imp, int(t0 + flight) + 6, scl=(0.001, 0.001, 0.001))

# ================================================================ destruction
blown = [b for b in blocks if b[3] in range(IMPACT_LO, IMPACT_HI) and b[2] == 0]
for i, (ob, ix, iy, fz) in enumerate(blown):
    t0 = F_IMPACT + i * 4 + rng.randint(0, 14)
    if t0 > FRAMES - 20:
        continue
    p0 = ob.location.copy()
    key(ob, min(t0, FRAMES), loc=p0, rot=(0, 0, 0))
    # Thrown SHORT. The first pass used -9..-22 with a 2.4x tail, which put
    # rubble at y=-64 while the mech stands at -52, so the debris landed on
    # top of the hero and buried the silhouette the model needs to see.
    out = Vector((rng.uniform(-5, 5), -rng.uniform(3, 9), rng.uniform(0, 4)))
    key(ob, min(t0 + 26, FRAMES), loc=p0 + out,
        rot=(rng.uniform(-1.4, 1.4), rng.uniform(-1.4, 1.4), rng.uniform(-1.4, 1.4)))
    key(ob, min(t0 + 78, FRAMES), loc=(p0.x + out.x * 1.7, p0.y + out.y * 1.6, 0.7),
        rot=(rng.uniform(-3, 3), rng.uniform(-3, 3), rng.uniform(-3, 3)))

for i in range(26):
    fz = rng.randint(IMPACT_LO, IMPACT_HI - 1)
    cyl(f"rebar_{i}",
        (rng.uniform(BX0, -BX0), TOWER_Y + 0.4, 2.0 + fz * FH + rng.uniform(-1.4, 1.4)),
        (0.055, 0.055, rng.uniform(1.0, 2.4)), "rebar",
        rot=(math.radians(90 + rng.uniform(-26, 26)), 0, rng.uniform(-0.5, 0.5)),
        verts=6)

top_hub = empty("top_hub", (0, BY0 + BS * 0.5, 2.0 + IMPACT_HI * FH))
bpy.context.view_layer.update()      # matrix_world is stale until this runs
for ob, ix, iy, fz in blocks:
    if fz >= IMPACT_HI:
        ob.parent = top_hub
        ob.matrix_parent_inverse = top_hub.matrix_world.inverted()
ROOF_PARTS = ["roofslab", "plant", "plant2", "mast"] + \
             [f"parapetx{s}" for s in (-1, 1)] + \
             [f"parapety{s}" for s in (-1, 1)] + \
             [f"vent_{i}" for i in range(3)]
for nm in ROOF_PARTS:
    o = bpy.data.objects[nm]
    o.parent = top_hub
    o.matrix_parent_inverse = top_hub.matrix_world.inverted()

# Topples DIAGONALLY, not straight toward camera. A pure -X pitch swings the
# roof plane flat into the lens; adding roll keeps an edge to camera so it
# reads as a building coming apart instead of a falling slab.
key(top_hub, 1, rot=(0, 0, 0))
key(top_hub, F_FAIL, rot=(0, 0, 0))
key(top_hub, F_TOPPLE, rot=(math.radians(-1.2), math.radians(0.8), 0))
key(top_hub, F_TOPPLE + 46, rot=(math.radians(-7.5), math.radians(6.0), 0))
key(top_hub, FRAMES, rot=(math.radians(-22.0), math.radians(15.0), math.radians(2.0)))

for i in range(34):
    s = rng.uniform(0.30, 1.15)
    d = chunk(f"deb_{i}", (0, 0, 0), (s, s, s * rng.uniform(0.6, 1.3)), "concrete2")
    t0 = F_IMPACT + rng.randint(0, 130)
    src = Vector((rng.uniform(BX0 - 2, -BX0 + 2), TOWER_Y,
                  2.0 + rng.uniform(IMPACT_LO, IMPACT_HI) * FH))
    vel = Vector((rng.uniform(-9, 9), -rng.uniform(3, 12), rng.uniform(3, 14)))
    key(d, max(1, t0 - 1), loc=(src.x, src.y, -200), scl=(s, s, s))
    key(d, t0, loc=src)
    for step in range(1, 5):
        t = step * 0.55
        key(d, min(int(t0 + step * 13), FRAMES),
            loc=(src.x + vel.x * t, src.y + vel.y * t,
                 max(0.5, src.z + vel.z * t - 9.2 * t * t)),
            rot=(rng.uniform(-4, 4), rng.uniform(-4, 4), rng.uniform(-4, 4)))

# ==================================================================== lighting
sun_data = bpy.data.lights.new("sun", type='SUN')
sun_data.energy = 3.2
sun_data.color = (1.0, 0.86, 0.70)
sun = bpy.data.objects.new("sun", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(56), 0, math.radians(34))

world = bpy.data.worlds.new("world")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.66, 0.70, 0.76, 1.0)
world.color = (0.660, 0.705, 0.775)   # Workbench reads THIS, not the node tree

# ====================================================================== camera
prefs.keyframe_new_interpolation_type = 'BEZIER'
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 20.0        # 9:16 gives only ~53 deg horizontally even here
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
target = bpy.data.objects.new("look_at", None)
scene.collection.objects.link(target)
con = cam.constraints.new('TRACK_TO')
con.target = target
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'

TOWER_PT = Vector((0.0, TOWER_Y, 0.0))


def cam_at(f, ang, dist, up):
    """Rear-quarter rig that RIDES the mech: it sits behind the mech on the
    mech->tower axis, swung `ang` degrees off it, so the mech holds its size
    and screen position while the tower grows beyond it.

    The first attempt orbited to the mech's left, which is the same side the
    tower is on, so the camera ended up BETWEEN them and cropped the mech at
    the frame edge by the firing beat. Behind-and-outboard is the only
    arrangement that fits a 16 m mech and a 70 m tower in one 9:16 frame with
    the full silhouette intact."""
    a = math.radians(ang)
    bx, by = -FWD.x, -FWD.y
    rx = bx * math.cos(a) - by * math.sin(a)
    ry = bx * math.sin(a) + by * math.cos(a)
    return root_pos(f) + Vector((rx, ry, 0.0)) * dist + Vector((0, 0, up))


def aim_at(f, mix, z):
    """Blend from the mech toward the tower along the same axis, so both stay
    inside the horizontal FOV (45 deg on this 9:16 frame) the whole shot."""
    aim = root_pos(f).lerp(TOWER_PT, mix)
    return (aim.x, aim.y, z)


#     frame          angle  dist   up   |  aim mix   aim z
# 50 deg off the axis on a 20 mm lens is the widest flank that still fits the
# tower in the horizontal FOV. Straight-behind hides the launcher pods, which
# are the entire Catapult identity, so the angle is worth the tight fit.
SHOT = [
    (1,             40.0, 26.5,  5.8,      0.12,      9.5),
    (F_WALK_END,    39.0, 25.5,  6.3,      0.14,     10.5),
    (F_FIRE,        38.0, 25.0,  6.9,      0.15,     11.5),
    (F_FAIL,        37.0, 25.0,  7.7,      0.16,     12.5),
    (FRAMES,        36.0, 25.5,  8.5,      0.17,     13.5),
]
for f, ang, dist, up, mix, z in SHOT:
    key(cam, f, loc=cam_at(f, ang, dist, up))
    key(target, f, loc=aim_at(f, mix, z))


# ---- framing assert: the whole mech silhouette must stay in frame ----------
# Not a nicety. When the legs leave frame the model cannot preserve them and
# substitutes running gear, which is how an earlier pass came back as a
# tracked armoured vehicle (finding 24). Checked, not hoped for.
from bpy_extras.object_utils import world_to_camera_view

def check_framing(f, margin=0.03):
    scene.frame_set(f)
    bpy.context.view_layer.update()
    p = root_pos(f)
    lat = Vector((-FWD.y, FWD.x, 0.0))
    pts = []
    for sx in (-cr.POD_X - cr.POD_W, cr.POD_X + cr.POD_W):
        for fy in (-3.5, 4.0):
            for z in (0.0, cr.MECH_TOP):
                pts.append(p + lat * sx + FWD * fy + Vector((0, 0, z)))
    bad = []
    for q in pts:
        c = world_to_camera_view(scene, cam, q)
        if not (margin < c.x < 1 - margin and margin < c.y < 1 - margin and c.z > 0):
            bad.append((round(c.x, 3), round(c.y, 3)))
    if bad:
        print(f"[strike] FRAMING WARNING f{f}: {len(bad)}/{len(pts)} corners "
              f"outside safe area -> {bad[:4]}")
    return not bad


_ok = all([check_framing(f) for f in
           (1, 40, 90, 140, F_WALK_END, F_SET, F_FIRE, 240, F_FAIL, 300, FRAMES)])
print("[strike] framing", "OK" if _ok else "HAS WARNINGS")

# ====================================================================== render
scene.frame_start, scene.frame_end = 1, FRAMES
scene.render.fps = FPS
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.resolution_percentage = 100
scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading
sh.light = 'STUDIO'
sh.studio_light = 'Default'
sh.color_type = 'MATERIAL'
sh.show_shadows = True
sh.shadow_intensity = 0.55
sh.show_cavity = True
sh.background_type = 'WORLD'
sh.background_color = (0.640, 0.685, 0.750)
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.filepath = f"{OUTDIR}/bl_"

_probe = os.environ.get("STRIKE_PROBE", "")
if _probe:
    base = scene.render.filepath
    for fr in [int(x) for x in _probe.split(",")]:
        scene.frame_set(fr)
        scene.render.filepath = f"{base}{fr:04d}"
        bpy.ops.render.render(write_still=True)
        print("[strike] probe", fr)
else:
    print(f"[strike] {FRAMES}f {W}x{H} -> {scene.render.filepath}")
    bpy.ops.render.render(animation=True)
    print("[strike] DONE")
