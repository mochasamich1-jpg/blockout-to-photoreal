"""
CPLT-C1 CATAPULT - parametric blockout rig for the LTX-2.3 + 3DREAL pipeline.

Reference-matched against MWO concept art, the Iron Wind miniature and the
LEGO orthographic (front view proportions). The silhouette rules that came
out of looking at those, in priority order:

  1. The PODS ARE TALL VERTICAL SLABS, not deep drums, and they sit HIGH -
     their tops are the top of the mech and they clear the body entirely.
     They hang outboard on short stub arms with a big round shoulder
     actuator at the joint. This is the single strongest identity cue.
  2. The BODY IS A LONG FORWARD WEDGE with a beak nose, not a squat cube.
     The cockpit canopy is built INTO the front-top of that wedge; there is
     no separate head on a neck.
  3. NO ARMS. The pods are the weapons.
  4. Legs are heavy reverse-joint (digitigrade): knee forward, ankle back,
     big splayed three-toe feet. Mass is preserved by the model, so every
     segment is built chunky (finding 26).
  5. A thin whip antenna above the body - it is in every single reference
     and it costs nothing.

Animation contract: everything moves on HUBS (Empties), never by editing
mesh data, so the legs can be driven with a closed-form two-link IK and the
planted foot never slides.

Frames are authored in each parent's LOCAL space, so no matrix_parent_inverse
is ever needed (finding 25).
"""
import bpy, bmesh, math, random
from mathutils import Vector, Matrix

# ----------------------------------------------------------------- proportions
# Everything derives from these. Blender units are metres.
FOOT_H      = 1.05        # top of the foot pad
ANKLE_Z     = 1.60        # ankle pivot height
L_THIGH     = 5.10        # hip -> knee
L_SHIN      = 5.10        # knee -> ankle
HIP_Z       = 10.10       # nominal hip pivot height (pelvis origin)
HIP_X       = 2.85        # half the leg stance

TORSO_DZ    = 2.00        # torso hub above the pelvis
BODY_W      = 1.95        # body half-width
BODY_BACK   = -2.85       # body extents in Y
BODY_FRONT  = 3.40        # the beak must clear the pods, or the profile dies
BODY_BOT    = -1.55       # relative to the torso hub
BODY_TOP    = 1.55

POD_X       = 4.15        # pod centre, outboard
POD_W       = 1.25        # pod half-width
POD_D       = 1.05        # pod half-depth
POD_H       = 2.85        # pod half-height - the pods ARE the silhouette
POD_Z       = 1.70        # pod centre above the torso hub

MECH_TOP    = HIP_Z + TORSO_DZ + POD_Z + POD_H     # ~17.0

# A uniform grey blockout barely transforms (finding 1), so the palette is
# deliberately spread on BOTH value and hue: olive livery panels, cool steel
# structure, near-black joints, brass hydraulics, saturated teal glass.
PALETTE = {
    "armor":    (0.430, 0.430, 0.300),   # olive drab livery, light
    "armor2":   (0.265, 0.275, 0.190),   # olive drab, dark
    "hull":     (0.330, 0.350, 0.395),   # cool steel
    "plate":    (0.590, 0.595, 0.605),   # light steel
    "joint":    (0.070, 0.070, 0.082),   # near black
    "hyd":      (0.700, 0.590, 0.310),   # brass ram
    "rust":     (0.520, 0.240, 0.100),   # burnt orange
    "warn":     (0.840, 0.650, 0.100),   # saturated hazard yellow
    "cockpit":  (0.120, 0.440, 0.480),   # saturated teal glass
    "tube":     (0.040, 0.040, 0.050),   # launch-tube bore
    "flash":    (1.000, 0.660, 0.180),
    "tracer":   (1.000, 0.480, 0.110),
}

_mats = {}


def mat(name, palette=None):
    pal = palette or PALETTE
    if name not in _mats:
        m = bpy.data.materials.new(name)
        m.use_nodes = False
        m.diffuse_color = (*pal[name], 1.0)
        _mats[name] = m
    return _mats[name]


def _finish(ob, m):
    ob.data.materials.append(mat(m))
    for p in ob.data.polygons:
        p.use_smooth = False
    return ob


def box(name, loc, scale, m, rot=(0, 0, 0), parent=None):
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0), rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    ob.location = loc
    if parent is not None:
        ob.parent = parent          # local coords, identity parent inverse
    return _finish(ob, m)


def cyl(name, loc, scale, m, rot=(0, 0, 0), parent=None, verts=16):
    bpy.ops.mesh.primitive_cylinder_add(location=(0, 0, 0), rotation=rot,
                                        vertices=verts, radius=1, depth=2)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    ob.location = loc
    if parent is not None:
        ob.parent = parent
    return _finish(ob, m)


def wedge(name, loc, x0, x1, y0, y1, z0, z1, m, parent=None,
          front_top=None, front_bot=None, front_x=None, back_top=None):
    """Axis-aligned box mesh with the +Y face independently retargetable, so a
    real tapered beak comes out instead of a stack of stepped cubes. All
    arguments are mesh-space extents; the object keeps scale (1,1,1)."""
    me = bpy.data.meshes.new(name)
    ft = front_top if front_top is not None else z1
    fb = front_bot if front_bot is not None else z0
    fx = front_x if front_x is not None else x1
    bt = back_top if back_top is not None else z1
    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y0, bt), (x0, y0, bt),        # back
        (-fx, y1, fb), (fx, y1, fb), (fx, y1, ft), (-fx, y1, ft),      # front
    ]
    faces = [(0, 1, 2, 3), (5, 4, 7, 6), (1, 0, 4, 5),
             (2, 1, 5, 6), (3, 2, 6, 7), (0, 3, 7, 4)]
    me.from_pydata(verts, [], faces)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    if parent is not None:
        ob.parent = parent
    return _finish(ob, m)


def slab(name, loc, w, d, h, cham, outer, m, parent=None):
    """Box with the TOP-OUTER corner cut away. The reference pod has material
    removed there; adding a rotated box instead grows a fin off the shoulder,
    which is what the first pass did and it read as a wing."""
    s = 1.0 if outer > 0 else -1.0
    xo, xi = s * w, -s * w                       # outer / inner x
    xc = s * (w - cham)
    v = [(xi, -d, -h), (xo, -d, -h), (xo, d, -h), (xi, d, -h),      # 0-3 bottom
         (xi, -d, h), (xc, -d, h), (xc, d, h), (xi, d, h),          # 4-7 top
         (xo, -d, h - cham), (xo, d, h - cham)]                     # 8-9 cut edge
    f = [(3, 2, 1, 0), (4, 5, 6, 7), (5, 8, 9, 6),
         (1, 2, 9, 8), (0, 4, 7, 3),
         (0, 1, 8, 5, 4), (3, 7, 6, 9, 2)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(v, [], f)
    me.validate()
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    if parent is not None:
        ob.parent = parent
    return _finish(ob, m)


def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = loc
    if parent is not None:
        e.parent = parent
    return e


# =============================================================== the launcher pod
def build_pod(torso, side, sx, rng):
    """A tall vertical slab with a chamfered top-outer corner, a forward tube
    grid and a round shoulder actuator. Held on a short stub arm - never a
    barrel, which reads as a Marauder."""
    sgn = 1 if sx > 0 else -1
    parts = []

    # stub arm out of the shoulder, and the big actuator disc at the joint.
    # The disc is deliberately large: it is the reference's clearest cue that
    # the pod is a mounted assembly rather than part of the hull.
    parts.append(box(f"podarm_{side}", (sx * 0.52, 0.10, POD_Z * 0.16),
                     (abs(sx) * 0.30, 0.80, 0.80), "hull", parent=torso))
    # Faceted and armour-coloured on purpose: a smooth black disc reads as a
    # rubber wheel, and "tracked vehicle" is the exact attractor this subject
    # collapses into (finding 24). Ten sides says machined joint instead.
    parts.append(cyl(f"shoulder_{side}", (sx * 0.72, 0.35, POD_Z * 0.16),
                     (1.10, 1.10, 0.74), "armor2",
                     rot=(0, math.radians(90), 0), parent=torso, verts=10))
    parts.append(cyl(f"shoulderhub_{side}", (sx * 0.72 + sgn * 0.40, 0.35, POD_Z * 0.16),
                     (0.52, 0.52, 0.34), "hyd",
                     rot=(0, math.radians(90), 0), parent=torso, verts=8))

    # pod hub so the whole slab can pitch as one when it fires. The small
    # outboard lean at the top is in the reference and reads immediately.
    hub = empty(f"podhub_{side}", (sx, -0.10, POD_Z), parent=torso)
    hub.rotation_euler = (0, math.radians(sgn * 5.0), 0)

    # Main slab in COOL STEEL, not the olive livery. A tan slab this size with
    # horizontal seams came back from the model as a wooden ammo crate, because
    # that is the nearest real thing to a big tan panelled box.
    parts.append(slab(f"pod_{side}", (0, 0, 0), POD_W, POD_D, POD_H,
                      POD_W * 1.05, sgn, "hull", parent=hub))
    # cap and heel plates
    parts.append(box(f"podcap_{side}", (-sgn * POD_W * 0.28, 0, POD_H * 1.0),
                     (POD_W * 0.70, POD_D * 1.02, 0.14), "armor2", parent=hub))
    parts.append(box(f"podfoot_{side}", (0, 0, -POD_H * 1.0),
                     (POD_W * 0.98, POD_D * 1.03, 0.16), "armor2", parent=hub))
    # outboard rib and a hanger bracket, both flush
    parts.append(box(f"podrib_{side}", (sgn * POD_W * 1.02, 0, -POD_H * 0.30),
                     (0.10, POD_D * 0.86, POD_H * 0.56), "plate", parent=hub))
    parts.append(box(f"podbrk_{side}", (-sgn * POD_W * 1.03, -0.10, 0),
                     (0.16, POD_D * 0.66, POD_H * 0.44), "armor2", parent=hub))

    # ---- REAR reload backplate. This is the fix that matters: the camera
    # lives on a rear quarter, so the launcher face is permanently hidden and
    # the model had no evidence the pod was a weapon at all. Putting a matching
    # grid of tube ends on the BACK gives it the launcher cue from the only
    # angle it can actually see.
    by = -POD_D * 0.99
    parts.append(box(f"podback_{side}", (0, by, -POD_H * 0.06),
                     (POD_W * 0.99, 0.12, POD_H * 0.86), "armor2", parent=hub))
    for r in range(5):
        for c in range(3):
            parts.append(cyl(f"btube_{side}_{r}_{c}",
                             (-0.72 + c * 0.72, by - 0.11, -1.86 + r * 0.93),
                             (0.285, 0.285, 0.14), "tube",
                             rot=(math.radians(90), 0, 0), parent=hub, verts=12))
    parts.append(box(f"podbstripe_{side}", (0, by - 0.13, POD_H * 0.86),
                     (POD_W * 0.84, 0.05, 0.18), "warn", parent=hub))
    # heavy corner frame around the backplate, so it reads as a bolted hatch
    for zz in (-POD_H * 0.92, POD_H * 0.74):
        parts.append(box(f"podbf_{side}_{zz:.0f}", (0, by - 0.10, zz),
                         (POD_W * 0.99, 0.08, 0.12), "plate", parent=hub))
    for xx in (-POD_W * 0.93, POD_W * 0.93):
        parts.append(box(f"podbv_{side}_{xx:.0f}", (xx, by - 0.10, -POD_H * 0.06),
                         (0.10, 0.08, POD_H * 0.84), "plate", parent=hub))

    # ---- the launcher face: recessed frame plus a 3x5 grid of deep bores
    fy = POD_D * 0.99
    parts.append(box(f"podface_{side}", (0, fy, -POD_H * 0.06),
                     (POD_W * 0.99, 0.12, POD_H * 0.86), "hull", parent=hub))
    for r in range(5):
        for c in range(3):
            parts.append(cyl(f"tube_{side}_{r}_{c}",
                             (-0.72 + c * 0.72, fy + 0.13, -1.86 + r * 0.93),
                             (0.305, 0.305, 0.17), "tube",
                             rot=(math.radians(90), 0, 0), parent=hub, verts=12))
    # warning stripe across the top of the face
    parts.append(box(f"podstripe_{side}", (0, fy + 0.13, POD_H * 0.86),
                     (POD_W * 0.84, 0.05, 0.18), "warn", parent=hub))
    # VERTICAL ribs down the outboard face. The first pass used horizontal
    # seams, which is exactly plank geometry and fed the wooden-crate read.
    for i in range(3):
        parts.append(box(f"podpl_{side}_{i}",
                         (sgn * POD_W * 1.005, -0.62 + i * 0.62, -POD_H * 0.10),
                         (0.04, 0.07, POD_H * 0.74), "joint", parent=hub))
    parts.append(box(f"podlug_{side}", (sgn * POD_W * 1.02, 0.0, POD_H * 0.62),
                     (0.09, POD_D * 0.72, 0.16), "plate", parent=hub))
    # muzzle position for the salvo
    muzzle = empty(f"podmuzzle_{side}", (0, fy + 0.5, 0.2), parent=hub)
    return hub, muzzle, parts


# ================================================================== the body
def build_body(torso, rng):
    parts = []
    # main hull: a long wedge that tapers and drops toward the beak. This is
    # the biggest single mass on the mech, not a filler block between pods.
    parts.append(wedge("body", (0, 0, 0),
                       -BODY_W, BODY_W, BODY_BACK, BODY_FRONT,
                       BODY_BOT, BODY_TOP, "armor", parent=torso,
                       front_top=0.70, front_bot=-0.86, front_x=BODY_W * 0.66))
    # shoulder blocks: mass out to meet the pod arms so the gap reads solid
    for sgn in (-1, 1):
        parts.append(box(f"shldr{sgn}", (sgn * BODY_W * 0.94, -0.55, 0.10),
                         (0.52, 1.45, BODY_TOP * 0.86), "hull", parent=torso))
    # Dorsal spine, stepped. From the rear quarter the hull presents almost no
    # angular information and came back as a smooth rounded turret, so the
    # surfaces the camera actually sees get hard steps and a chine line.
    parts.append(box("spine", (0, -0.50, BODY_TOP + 0.14),
                     (BODY_W * 0.62, 1.70, 0.28), "armor2", parent=torso))
    parts.append(box("spine2", (0, -1.55, BODY_TOP + 0.42),
                     (BODY_W * 0.44, 0.80, 0.30), "plate", parent=torso))
    # hard chine down each flank, plus an inset lower skirt
    for sgn in (-1, 1):
        parts.append(box(f"chine{sgn}", (sgn * BODY_W * 0.97, -0.20, 0.42),
                         (0.16, 2.30, 0.20), "plate", parent=torso))
        parts.append(box(f"skirt{sgn}", (sgn * BODY_W * 0.90, -0.30, BODY_BOT + 0.34),
                         (0.22, 2.05, 0.42), "armor2",
                         rot=(0, math.radians(sgn * 12), 0), parent=torso))
    # angled rear quarter plates
    for sgn in (-1, 1):
        parts.append(box(f"rearq{sgn}", (sgn * BODY_W * 0.72, BODY_BACK + 0.18, 0.30),
                         (0.62, 0.34, 0.94), "plate",
                         rot=(0, 0, math.radians(sgn * 26)), parent=torso))
    parts.append(box("backpack", (0, BODY_BACK - 0.48, 0.00),
                     (BODY_W * 0.84, 0.58, 1.00), "armor", parent=torso))
    for i in range(4):
        parts.append(box(f"fin_{i}", (0, BODY_BACK - 0.34 - i * 0.30, 0.62),
                         (BODY_W * 0.80, 0.06, 0.34), "joint", parent=torso))
    # Jump-jet exhausts as rectangular louvred vents, not round nozzles. A
    # symmetric pair of dark circles centred on the back reads unmistakably as
    # a face, and it is the rear three-quarter the camera lives on.
    # Pushed out to the flanks and down low. Anything symmetric and dark near
    # the centre of the back reads as a pair of eyes from the rear quarter the
    # camera lives on, whatever shape it is.
    for i, jx in enumerate((-1.62, 1.62)):
        parts.append(box(f"jetbox_{i}", (jx, BODY_BACK - 0.72, -0.86),
                         (0.34, 0.42, 0.44), "hull",
                         rot=(math.radians(-18), 0, 0), parent=torso))
        for k in range(3):
            parts.append(box(f"jetsl_{i}_{k}", (jx, BODY_BACK - 1.06, -1.04 + k * 0.22),
                             (0.28, 0.06, 0.05), "tube",
                             rot=(math.radians(-18), 0, 0), parent=torso))

    # ---- cockpit built INTO the front-top of the wedge, no neck
    parts.append(wedge("canopy", (0, 0, 0),
                       -BODY_W * 0.66, BODY_W * 0.66, 0.40, BODY_FRONT + 0.30,
                       0.34, BODY_TOP * 0.98, "armor2", parent=torso,
                       front_top=0.76, front_bot=0.06, front_x=BODY_W * 0.42))
    # Raised brow over the canopy. It breaks the roofline, so the cockpit is
    # still readable in silhouette from behind, where the beak itself is hidden.
    parts.append(box("brow", (0, BODY_FRONT - 0.30, BODY_TOP * 0.92),
                     (BODY_W * 0.60, 0.62, 0.30), "plate",
                     rot=(math.radians(-12), 0, 0), parent=torso))
    parts.append(box("browfin", (0, BODY_FRONT - 0.95, BODY_TOP * 1.12),
                     (BODY_W * 0.34, 0.30, 0.26), "armor2", parent=torso))
    # glass: saturated teal, contrast by HUE not luminance (finding 20)
    parts.append(box("glass_f", (0, BODY_FRONT + 0.23, 0.50),
                     (BODY_W * 0.38, 0.10, 0.28), "cockpit", parent=torso))
    for sgn in (-1, 1):
        parts.append(box(f"glass_s{sgn}", (sgn * BODY_W * 0.53, BODY_FRONT - 0.52, 0.58),
                         (0.10, 0.60, 0.24), "cockpit",
                         rot=(0, math.radians(sgn * -12), 0), parent=torso))
    # chin block under the beak carrying the medium-laser ports
    parts.append(box("chin", (0, BODY_FRONT - 0.30, -1.05),
                     (BODY_W * 0.58, 0.72, 0.40), "hull", parent=torso))
    for i, lx in enumerate((-0.66, -0.22, 0.22, 0.66)):
        parts.append(cyl(f"laser_{i}", (lx, BODY_FRONT + 0.36, -1.05),
                         (0.12, 0.12, 0.26), "tube",
                         rot=(math.radians(90), 0, 0), parent=torso, verts=10))
    # whip antenna - in every reference, and it costs nothing
    parts.append(cyl("antenna", (0.52, -0.80, BODY_TOP + 1.70),
                     (0.045, 0.045, 1.56), "joint", parent=torso, verts=6))
    parts.append(cyl("antbase", (0.52, -0.80, BODY_TOP + 0.26),
                     (0.14, 0.14, 0.22), "plate", parent=torso, verts=8))

    # flank panel lines: horizontal seams read as welded armour plating
    for sgn in (-1, 1):
        for i in range(3):
            parts.append(box(f"seam{sgn}_{i}", (sgn * BODY_W * 1.01, 0.10, -0.80 + i * 0.80),
                             (0.03, 1.75, 0.07), "joint", parent=torso))
    # hatches and greebles: the cheapest "real machinery" cue there is
    for i in range(14):
        sgn = rng.choice((-1, 1))
        parts.append(box(f"greeb_{i}",
                         (sgn * rng.uniform(0.5, BODY_W * 0.96),
                          rng.uniform(BODY_BACK + 0.4, BODY_FRONT - 0.9),
                          rng.uniform(BODY_BOT + 0.3, BODY_TOP - 0.2)),
                         (rng.uniform(0.05, 0.14), rng.uniform(0.14, 0.42),
                          rng.uniform(0.06, 0.20)),
                         rng.choice(("hull", "joint", "rust", "plate")), parent=torso))
    return parts


# =================================================================== the leg
def build_leg(pelvis, side, sx):
    """Returns the hub chain. Reverse-joint: knee forward, ankle back, and a
    big splayed three-toe foot. Every segment is deliberately chunky - thin
    blockout limbs come back as insect legs (finding 26)."""
    sgn = 1 if sx > 0 else -1
    hip = empty(f"hip_{side}", (sx, 0, 0), parent=pelvis)
    knee = empty(f"knee_{side}", (0, 0, -L_THIGH), parent=hip)
    ankle = empty(f"ankle_{side}", (0, 0, -L_SHIN), parent=knee)

    # hip actuator - faceted, not a smooth disc (see the shoulder note)
    cyl(f"hipcyl_{side}", (0, 0, 0), (1.04, 1.04, 1.06), "armor2",
        rot=(0, math.radians(90), 0), parent=hip, verts=10)

    # thigh: fat armoured block. Chunky on purpose - thin blockout limbs come
    # back as spindly insect legs no matter what the prompt says (finding 26).
    # tapered: broad at the hip, narrowing into the knee, like the reference
    box(f"thigh_{side}", (0, 0.10, -L_THIGH * 0.34),
        (1.40, 1.50, L_THIGH * 0.34), "armor", parent=hip)
    box(f"thighlo_{side}", (0, 0.06, -L_THIGH * 0.78),
        (1.14, 1.26, L_THIGH * 0.24), "armor", parent=hip)
    box(f"thighout_{side}", (sgn * 1.16, 0.02, -L_THIGH * 0.40),
        (0.34, 1.20, L_THIGH * 0.30), "armor2", parent=hip)
    box(f"thighin_{side}", (-sgn * 1.22, 0.02, -L_THIGH * 0.46),
        (0.26, 0.98, L_THIGH * 0.26), "hull", parent=hip)
    for i in range(3):
        box(f"thighpl_{side}_{i}", (0, 1.52, -1.10 - i * 1.05),
            (1.04, 0.06, 0.12), "joint", parent=hip)
    # ram tucked hard against the segment; standing it off reads as an extra limb
    cyl(f"thighram_{side}", (sgn * 0.72, -1.16, -L_THIGH * 0.52),
        (0.22, 0.22, L_THIGH * 0.40), "hyd", parent=hip, verts=10)

    # knee: the reference's most legible joint cue, but ARMOURED and faceted.
    # A big smooth black cylinder here is the strongest wheel cue on the mech.
    cyl(f"kneedisc_{side}", (0, 0, 0), (1.30, 1.30, 1.22), "armor2",
        rot=(0, math.radians(90), 0), parent=knee, verts=10)
    cyl(f"kneering_{side}", (sgn * 1.24, 0, 0), (0.92, 0.92, 0.16), "joint",
        rot=(0, math.radians(90), 0), parent=knee, verts=10)
    cyl(f"kneehub_{side}", (sgn * 1.36, 0, 0), (0.50, 0.50, 0.22), "hyd",
        rot=(0, math.radians(90), 0), parent=knee, verts=8)
    box(f"kneecap_{side}", (0, 1.04, 0.10), (0.94, 0.50, 0.82), "plate", parent=knee)

    # shin
    box(f"shin_{side}", (0, -0.06, -L_SHIN * 0.50),
        (1.24, 1.32, L_SHIN * 0.46), "hull", parent=knee)
    box(f"shinplate_{side}", (0, 1.20, -L_SHIN * 0.44),
        (1.04, 0.22, L_SHIN * 0.34), "armor", parent=knee)
    for i in range(3):
        box(f"shinpl_{side}_{i}", (0, 1.44, -1.40 - i * 1.10),
            (0.84, 0.06, 0.11), "joint", parent=knee)
    cyl(f"shinram_{side}", (sgn * 0.96, -0.98, -L_SHIN * 0.46),
        (0.21, 0.21, L_SHIN * 0.38), "hyd", parent=knee, verts=10)

    # ankle + BIG splayed three-toe foot, clearly wider than the shin
    cyl(f"anklecyl_{side}", (0, 0, 0), (0.92, 0.92, 0.98), "armor2",
        rot=(0, math.radians(90), 0), parent=ankle, verts=10)
    box(f"anklebox_{side}", (0, 0.26, -0.44), (0.96, 0.90, 0.50), "armor2", parent=ankle)
    fz = -(ANKLE_Z - FOOT_H * 0.5)
    # one continuous pad that widens and flattens toward the toes, so the
    # three toes read as claws grown out of the foot, not three loose cubes
    wedge(f"foot_{side}", (0, 0, fz), -1.62, 1.62, -1.55, 2.30,
          -FOOT_H * 0.50, FOOT_H * 0.62, "plate", parent=ankle,
          front_top=-FOOT_H * 0.06, front_x=1.78, back_top=FOOT_H * 0.62)
    box(f"heel_{side}", (0, -1.72, fz + 0.16), (1.16, 0.42, FOOT_H * 0.62),
        "armor2", parent=ankle)
    for i, tx in enumerate((-1.14, 0.0, 1.14)):
        wedge(f"toe_{side}_{i}", (tx, 0, fz), -0.52, 0.52, 2.24, 3.16,
              -FOOT_H * 0.50, -FOOT_H * 0.04, "hull", parent=ankle,
              front_top=-FOOT_H * 0.24, front_x=0.40)
    box(f"instep_{side}", (0, 0.30, fz + FOOT_H * 0.62),
        (1.32, 1.36, 0.20), "armor", parent=ankle)
    for i in range(2):
        box(f"footpl_{side}_{i}", (0, 0.10 + i * 0.85, fz + FOOT_H * 0.60),
            (1.56, 0.06, 0.10), "joint", parent=ankle)
    return hip, knee, ankle


# ============================================================== assemble + IK
class Catapult:
    def __init__(self, name="cat", loc=(0, 0, 0), yaw=0.0, seed=7):
        rng = random.Random(seed)
        self.root = empty(f"{name}_root", loc)
        self.root.rotation_euler = (0, 0, yaw)
        self.pelvis = empty(f"{name}_pelvis", (0, 0, HIP_Z), parent=self.root)
        self.torso = empty(f"{name}_torso", (0, 0, TORSO_DZ), parent=self.pelvis)

        # pelvis structure
        box("pelvis", (0, 0.10, 0.30), (2.30, 1.42, 0.92), "hull", parent=self.pelvis)
        box("pelvisdeck", (0, 0.05, 1.10), (1.90, 1.18, 0.26), "armor", parent=self.pelvis)
        box("groin", (0, 1.20, -0.44), (0.96, 0.56, 0.66), "armor2", parent=self.pelvis)
        for sgn in (-1, 1):
            box(f"hipskirt{sgn}", (sgn * 2.10, -0.10, -0.30),
                (0.60, 1.05, 0.72), "armor", parent=self.pelvis)

        self.legs = {}
        for side, sx in (("l", -HIP_X), ("r", HIP_X)):
            self.legs[side] = build_leg(self.pelvis, side, sx)

        build_body(self.torso, rng)
        self.pods, self.muzzles, self.pod_roll = {}, {}, {}
        for side, sx in (("l", -POD_X), ("r", POD_X)):
            hub, muzzle, _ = build_pod(self.torso, side, sx, rng)
            self.pods[side] = hub
            self.muzzles[side] = muzzle
            self.pod_roll[side] = hub.rotation_euler.y   # keep the base lean

    def pitch_pod(self, side, x):
        """Pitch a pod about its mount, preserving the base outboard lean."""
        self.pods[side].rotation_euler = (x, self.pod_roll[side], 0)

    # ---------------------------------------------------------------- posing
    def pelvis_matrix(self):
        bpy.context.view_layer.update()      # matrix_world is stale otherwise
        return self.pelvis.matrix_world.copy()

    def solve_leg(self, side, foot_world, foot_pitch=0.0):
        """Closed-form two-link IK in the pelvis-local sagittal plane, picking
        the knee-FORWARD branch so the leg reads as a reverse joint. Returns
        (a_hip, a_knee, a_ankle) about local X."""
        hip, knee, ankle = self.legs[side]
        M = self.pelvis_matrix()
        # target is the ANKLE pivot; the foot pad hangs below it
        tgt = M.inverted() @ Vector((foot_world[0], foot_world[1],
                                     foot_world[2] + ANKLE_Z))
        sx = hip.location.x
        dy, dz = tgt.y - 0.0, tgt.z - 0.0
        dist = math.hypot(dy, dz)
        lo, hi = abs(L_THIGH - L_SHIN) + 0.05, L_THIGH + L_SHIN - 0.06
        dist = max(lo, min(hi, dist))
        phi = math.atan2(dy, -dz)
        ca = (L_THIGH * L_THIGH + dist * dist - L_SHIN * L_SHIN) / (2 * L_THIGH * dist)
        cb = (L_THIGH * L_THIGH + L_SHIN * L_SHIN - dist * dist) / (2 * L_THIGH * L_SHIN)
        alpha = math.acos(max(-1.0, min(1.0, ca)))
        beta = math.acos(max(-1.0, min(1.0, cb)))
        a_hip = phi + alpha                       # knee-forward branch
        a_knee = -(math.pi - beta)
        # keep the foot level in WORLD, then add the requested pitch
        pel_pitch = self.pelvis.matrix_world.to_euler().x
        a_ankle = -pel_pitch - a_hip - a_knee + foot_pitch
        return a_hip, a_knee, a_ankle

    def pose_leg(self, side, foot_world, foot_pitch=0.0):
        hip, knee, ankle = self.legs[side]
        a1, a2, a3 = self.solve_leg(side, foot_world, foot_pitch)
        hip.rotation_euler = (a1, 0, 0)
        knee.rotation_euler = (a2, 0, 0)
        ankle.rotation_euler = (a3, 0, 0)

    def key_all(self, frame):
        for ob in (self.root, self.pelvis, self.torso):
            ob.keyframe_insert("location", frame=frame)
            ob.keyframe_insert("rotation_euler", frame=frame)
        for side in ("l", "r"):
            for h in self.legs[side]:
                h.keyframe_insert("rotation_euler", frame=frame)
            self.pods[side].keyframe_insert("rotation_euler", frame=frame)
