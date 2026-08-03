"""
Mid-engine supercar - parametric blockout rig for the LTX-2.3 + 3DREAL pipeline.

Unlike the Catapult, this subject has an ENORMOUS photographic prior, so the
job is the opposite one: give the model a clean, correctly-proportioned
silhouette and then get out of its way. Real dimensions (metres), taken from
the C8 Z06 / Senna class of car:

    length 4.60   width 2.00   height 1.22   wheelbase 2.72   wheel dia 0.72

The proportions that actually say "supercar" rather than "coupe":
  1. The WHEELS ARE HUGE against the body - 0.72 m against a 1.22 m roof, so
     the wheel is nearly 60% of total height. Get this wrong and it reads as
     a hatchback no matter what else is right.
  2. CAB-FORWARD greenhouse. The screen base sits barely behind the front
     axle and the roof peak is ahead of centre, leaving a long rear deck.
  3. A SIDE INTAKE scooped into the flank ahead of the rear wheel. This is
     the single clearest mid-engine cue in the reference.
  4. Rear haunches wider than the front, with a visible shoulder line.
  5. Everything below the sill line is black - splitter, skirts, diffuser.
     That dark band is what makes the body look like it is hovering.

Sprung vs unsprung mass is modelled properly: the wheels stay on the road and
the BODY rolls, pitches and squats on top of them. That separation is most of
what makes a car look driven rather than slid around.
"""
import bpy, bmesh, math
from mathutils import Vector

# ------------------------------------------------------------------ geometry
L_HALF   = 2.30          # 4.60 m long
W_HALF   = 1.00          # 2.00 m wide
H_TOP    = 1.22
WB_HALF  = 1.36          # 2.72 m wheelbase
WR       = 0.36          # wheel radius, 0.72 m diameter
# Half-tracks chosen so the tyre's OUTER face sits flush with the widest
# bodywork (1.00). Wheels tucked inside the body read as a saloon; wheels
# flush with the arch lip read as a supercar.
TR_F     = 0.83          # front half-track  (outer face 0.98)
TR_R     = 0.82          # rear half-track   (outer face 1.005)
TYRE_F   = 0.15          # half tyre width
TYRE_R   = 0.185

PALETTE = {
    # A saturated papaya orange. Strong hue separation from a grey wet city,
    # and it reads unambiguously as automotive paint rather than bare metal.
    "paint":    (0.860, 0.290, 0.040),
    "paint2":   (0.430, 0.130, 0.020),
    "carbon":   (0.075, 0.078, 0.085),
    "carbon2":  (0.150, 0.152, 0.160),
    "glass":    (0.095, 0.150, 0.205),
    "tyre":     (0.055, 0.055, 0.060),
    "rim":      (0.620, 0.630, 0.650),
    "rimdark":  (0.270, 0.280, 0.300),
    "brake":    (0.880, 0.360, 0.060),   # hot disc: contrast by HUE, not value
    "caliper":  (0.800, 0.110, 0.070),
    "light":    (0.940, 0.930, 0.870),
    "tail":     (0.900, 0.090, 0.060),
    "chrome":   (0.700, 0.720, 0.750),
    "mesh":     (0.110, 0.115, 0.125),
}

_mats = {}


def mat(name):
    if name not in _mats:
        m = bpy.data.materials.new(name)
        m.use_nodes = False
        m.diffuse_color = (*PALETTE[name], 1.0)
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
        ob.parent = parent
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


def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = loc
    if parent is not None:
        e.parent = parent
    return e


def hull(name, sections, m, parent=None, loc=(0, 0, 0)):
    """Lofted body panel. `sections` is a list of (y, x_half, z_low, z_high);
    consecutive sections are bridged into a quad tube and capped. This is how
    the tapered nose, the cab-forward greenhouse and the rear deck get built
    without stacking visible steps - a car silhouette is the one place where
    stepped cubes really do read as a toy."""
    verts, faces = [], []
    for (y, xh, z0, z1) in sections:
        i = len(verts)
        verts += [(-xh, y, z0), (xh, y, z0), (xh, y, z1), (-xh, y, z1)]
        if i >= 4:
            j = i - 4
            faces += [(j, i, i + 1, j + 1),           # bottom
                      (j + 1, i + 1, i + 2, j + 2),   # right
                      (j + 2, i + 2, i + 3, j + 3),   # top
                      (j + 3, i + 3, i, j)]           # left
    faces.append((0, 3, 2, 1))
    n = len(verts) - 4
    faces.append((n, n + 1, n + 2, n + 3))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
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


# ==================================================================== wheels
def build_wheel(root, tag, cx, cy, tw, steerable):
    """steer hub -> spin hub -> meshes, so steering and rotation never fight.
    The rim gets 10 spokes: at speed the exact angle is unresolvable anyway,
    and a near-rotationally-symmetric wheel looks right at any keyed angle
    instead of strobing between obviously different poses."""
    steer = empty(f"steer_{tag}", (cx, cy, WR), parent=root)
    spin = empty(f"spin_{tag}", (0, 0, 0), parent=steer)

    cyl(f"tyre_{tag}", (0, 0, 0), (WR, WR, tw), "tyre",
        rot=(0, math.radians(90), 0), parent=spin, verts=28)
    cyl(f"shoulder_{tag}", (0, 0, 0), (WR * 0.995, WR * 0.995, tw * 0.82), "carbon2",
        rot=(0, math.radians(90), 0), parent=spin, verts=28)
    # rim face, set in from the tyre shoulder
    for sgn in (-1, 1):
        cyl(f"rim_{tag}{sgn}", (sgn * tw * 0.52, 0, 0),
            (WR * 0.70, WR * 0.70, tw * 0.30), "rim",
            rot=(0, math.radians(90), 0), parent=spin, verts=24)
    cyl(f"barrel_{tag}", (0, 0, 0), (WR * 0.71, WR * 0.71, tw * 0.86), "rimdark",
        rot=(0, math.radians(90), 0), parent=spin, verts=24)
    for i in range(10):
        a = i * math.pi / 5.0
        box(f"spoke_{tag}_{i}",
            (tw * 0.56, math.sin(a) * WR * 0.38, math.cos(a) * WR * 0.38),
            (tw * 0.10, 0.032, WR * 0.36), "rim",
            rot=(a, 0, 0), parent=spin)
    cyl(f"nut_{tag}", (tw * 0.66, 0, 0), (0.075, 0.075, tw * 0.16), "chrome",
        rot=(0, math.radians(90), 0), parent=spin, verts=8)

    # brake disc + caliper live on the STEER hub, not the spin hub: a disc that
    # visibly rotates with the wheel reads as a fan
    cyl(f"disc_{tag}", (0, 0, 0), (WR * 0.62, WR * 0.62, tw * 0.10), "brake",
        rot=(0, math.radians(90), 0), parent=steer, verts=22)
    box(f"cal_{tag}", (0, -WR * 0.10, WR * 0.50), (tw * 0.20, 0.12, 0.10),
        "caliper", parent=steer)
    return steer, spin


# ====================================================================== body
def build_body(body):
    # ---- Main bodywork. Each section carries its own FLOOR height, and that
    # is the whole trick: over the two axles the floor jumps up to 0.72 (the
    # top of the tyre) so the loft arches OVER the wheel and leaves it in an
    # open wheel well, while between and outside the axles the floor drops to
    # sill height. A single full-height loft, as in the first pass, covers the
    # wheels completely and buries the greenhouse inside the shell - the car
    # came out as an orange slab with no visible wheels at all.
    hull("shell", [
        (-2.30, 0.86, 0.30, 0.86),      # tail
        (-2.05, 0.94, 0.26, 0.92),
        (-1.88, 0.99, 0.72, 0.96),      # rear arch opens
        (-1.36, 1.00, 0.74, 1.00),      # rear axle, widest point
        (-0.92, 0.99, 0.72, 1.00),      # rear arch closes
        (-0.82, 0.92, 0.22, 0.99),      # sill line through the doors
        (0.58, 0.92, 0.22, 0.90),
        (0.80, 0.96, 0.70, 0.86),       # front arch opens
        (1.36, 0.99, 0.72, 0.78),       # front axle
        (1.86, 0.96, 0.70, 0.64),       # front arch closes
        (2.06, 0.90, 0.20, 0.52),
        (2.30, 0.66, 0.18, 0.40),       # nose tip
    ], "paint", parent=body)
    # narrow underbody tub, tucked inboard of both tyres
    hull("tub", [
        (-2.00, 0.64, 0.16, 0.80),
        (-1.30, 0.66, 0.16, 0.86),
        (0.00, 0.66, 0.16, 0.86),
        (1.30, 0.66, 0.16, 0.78),
        (1.95, 0.62, 0.16, 0.62),
    ], "paint2", parent=body)

    # ---- greenhouse, sitting ON the beltline rather than inside it
    hull("cabin", [
        (-1.16, 0.56, 0.98, 1.02),
        (-0.72, 0.68, 1.00, 1.16),
        (-0.28, 0.70, 1.00, 1.24),      # roof peak, ahead of centre
        (0.22, 0.68, 0.96, 1.20),
        (0.62, 0.62, 0.90, 1.06),
        (0.86, 0.54, 0.86, 0.94),       # screen base, just behind the front axle
    ], "glass", parent=body)
    # roof panel and the A/B pillars, so the glass is framed rather than a blob
    box("roof", (0, -0.34, 1.245), (0.58, 0.44, 0.030), "paint", parent=body)
    for sgn in (-1, 1):
        box(f"apil{sgn}", (sgn * 0.60, 0.42, 1.06),
            (0.065, 0.36, 0.085), "paint",
            rot=(math.radians(-30), 0, 0), parent=body)
        box(f"bpil{sgn}", (sgn * 0.58, -0.90, 1.03),
            (0.075, 0.20, 0.10), "paint",
            rot=(math.radians(34), 0, 0), parent=body)
        # flying buttress down to the rear deck - a mid-engine signature
        box(f"butt{sgn}", (sgn * 0.72, -1.05, 0.99),
            (0.075, 0.44, 0.055), "paint",
            rot=(math.radians(16), 0, 0), parent=body)

    # ---- shoulder line: the crease that separates upper from lower body
    for sgn in (-1, 1):
        box(f"shoulder{sgn}", (sgn * 1.005, -0.20, 0.86),
            (0.030, 1.15, 0.035), "paint2", parent=body)

    # ---- SIDE INTAKE ahead of the rear wheel: the mid-engine tell
    for sgn in (-1, 1):
        box(f"intake{sgn}", (sgn * 0.955, -0.68, 0.72),
            (0.10, 0.32, 0.16), "carbon",
            rot=(0, 0, math.radians(-sgn * 5)), parent=body)
        box(f"intakelip{sgn}", (sgn * 1.00, -0.36, 0.74),
            (0.050, 0.09, 0.20), "paint2", parent=body)
        for k in range(3):
            box(f"intakefin{sgn}_{k}", (sgn * 0.93, -0.80 + k * 0.14, 0.72),
                (0.070, 0.018, 0.13), "carbon2", parent=body)

    # ---- arch lips, sitting proud of the openings
    for sgn in (-1, 1):
        box(f"archF{sgn}", (sgn * 1.00, WB_HALF, 0.755),
            (0.045, 0.52, 0.045), "paint2", parent=body)
        box(f"archR{sgn}", (sgn * 1.01, -WB_HALF, 0.775),
            (0.045, 0.58, 0.045), "paint2", parent=body)

    # ---- everything below the sill is black. This dark band is what makes the
    #      body look like it is floating rather than sitting on a slab.
    for sgn in (-1, 1):
        box(f"skirt{sgn}", (sgn * 0.955, -0.12, 0.21),
            (0.075, 1.30, 0.075), "carbon", parent=body)
    box("splitter", (0, 2.24, 0.115), (1.00, 0.30, 0.030), "carbon", parent=body)
    box("splitter2", (0, 2.06, 0.20), (0.94, 0.16, 0.075), "carbon", parent=body)
    box("floorpan", (0, 0.10, 0.150), (0.68, 1.90, 0.025), "carbon", parent=body)

    # ---- front end: intakes, splitter blades, slim headlights
    box("grille", (0, 2.16, 0.34), (0.62, 0.12, 0.115), "mesh", parent=body)
    for sgn in (-1, 1):
        box(f"ductF{sgn}", (sgn * 0.70, 2.10, 0.32), (0.22, 0.14, 0.13),
            "mesh", parent=body)
        box(f"blade{sgn}", (sgn * 0.86, 2.14, 0.22), (0.10, 0.22, 0.055),
            "carbon", parent=body)
        # set INTO the front clam, not perched on top of it
        box(f"head{sgn}", (sgn * 0.68, 1.92, 0.505), (0.24, 0.085, 0.042),
            "light", rot=(0, 0, math.radians(sgn * 7)), parent=body)
        box(f"headin{sgn}", (sgn * 0.38, 1.98, 0.475), (0.095, 0.07, 0.032),
            "light", parent=body)
    box("bonnet", (0, 1.55, 0.735), (0.62, 0.42, 0.030), "paint2", parent=body)
    for sgn in (-1, 1):
        box(f"louvre{sgn}", (sgn * 0.34, 1.50, 0.755), (0.20, 0.30, 0.020),
            "carbon2", parent=body)

    # ---- rear: engine deck vents, light bar, diffuser, quad pipes
    for k in range(4):
        box(f"deckvent_{k}", (0, -1.30 - k * 0.13, 0.945 - k * 0.035),
            (0.60, 0.045, 0.030), "carbon2", parent=body)
    box("tailbar", (0, -2.30, 0.72), (0.80, 0.055, 0.055), "tail", parent=body)
    for sgn in (-1, 1):
        box(f"tail{sgn}", (sgn * 0.62, -2.30, 0.72), (0.22, 0.06, 0.075),
            "tail", parent=body)
    box("diffuser", (0, -2.22, 0.24), (0.88, 0.24, 0.14), "carbon", parent=body)
    for i in range(5):
        box(f"fin_{i}", (-0.72 + i * 0.36, -2.22, 0.22),
            (0.030, 0.24, 0.13), "carbon2", parent=body)
    for sgn in (-1, 1):
        for k in (0, 1):
            cyl(f"pipe{sgn}_{k}", (sgn * (0.26 + k * 0.20), -2.34, 0.50),
                (0.055, 0.055, 0.075), "chrome",
                rot=(math.radians(90), 0, 0), parent=body, verts=10)

    # ---- rear wing on twin swan-neck pylons
    box("wing", (0, -2.06, 1.16), (0.88, 0.17, 0.022), "carbon",
        rot=(math.radians(9), 0, 0), parent=body)
    box("wingflap", (0, -2.20, 1.21), (0.86, 0.055, 0.018), "carbon",
        rot=(math.radians(22), 0, 0), parent=body)
    for sgn in (-1, 1):
        box(f"pylon{sgn}", (sgn * 0.62, -1.98, 1.02), (0.035, 0.055, 0.16),
            "carbon", parent=body)
        box(f"endplate{sgn}", (sgn * 0.88, -2.08, 1.14), (0.020, 0.20, 0.085),
            "carbon", parent=body)

    # ---- mirrors on stalks
    for sgn in (-1, 1):
        box(f"mstalk{sgn}", (sgn * 1.00, 0.72, 0.90), (0.10, 0.030, 0.020),
            "carbon", parent=body)
        box(f"mirror{sgn}", (sgn * 1.10, 0.70, 0.94), (0.055, 0.085, 0.055),
            "paint", rot=(0, math.radians(sgn * -12), 0), parent=body)


class Car:
    """root carries world position + heading; body carries roll/pitch/heave."""

    def __init__(self, name="car", loc=(0, 0, 0), yaw=0.0):
        self.root = empty(f"{name}_root", loc)
        self.root.rotation_euler = (0, 0, yaw)
        self.body = empty(f"{name}_body", (0, 0, 0), parent=self.root)
        build_body(self.body)
        self.steer, self.spin = {}, {}
        for tag, cx, cy, tw, st in (("fl", -TR_F, WB_HALF, TYRE_F, True),
                                    ("fr", TR_F, WB_HALF, TYRE_F, True),
                                    ("rl", -TR_R, -WB_HALF, TYRE_R, False),
                                    ("rr", TR_R, -WB_HALF, TYRE_R, False)):
            s, sp = build_wheel(self.root, tag, cx, cy, tw, st)
            self.steer[tag] = s
            self.spin[tag] = sp

    def key(self, frame):
        self.root.keyframe_insert("location", frame=frame)
        self.root.keyframe_insert("rotation_euler", frame=frame)
        self.body.keyframe_insert("location", frame=frame)
        self.body.keyframe_insert("rotation_euler", frame=frame)
        for tag in self.steer:
            self.steer[tag].keyframe_insert("rotation_euler", frame=frame)
            self.spin[tag].keyframe_insert("rotation_euler", frame=frame)
