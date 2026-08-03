"""
CITY RUN - a supercar races through downtown and drifts a corner.

9:16 blockout for the LTX-2.3 + 3DREAL render-to-real pipeline.

Shot:
  0.0 - 5.0s   hard acceleration up the avenue, weaving through traffic
  5.0 - 8.3s   flat out, buildings ripping past
  8.3 - 10.4s  heavy braking into the intersection, nose diving
 10.4 - 12.5s  drifting the left-hander, opposite lock, tail out
 12.5 - 15.0s  straightening and powering away down the cross street

Why this subject works where the mech did not: a car has an enormous
photographic prior, so the model does not have to invent what it is looking
at. The whole job here is to hand it a correctly-proportioned silhouette and
believable VEHICLE DYNAMICS, then let it paint.

Everything the car does is derived from the path rather than hand-keyed:
  - heading comes from finite-differencing the racing line, so the weave and
    the corner are handled by one code path
  - body roll comes from v^2 * dtheta/ds, leaning OUT of the corner
  - body pitch comes from longitudinal acceleration, so it squats under power
    and dives under braking
  - wheel spin comes from v/r, steering from curvature plus opposite lock
The sprung body rolls and pitches; the wheels stay on the road. That
separation is most of what makes a car look driven rather than slid around.

Usage: blender -b -P build_race.py -- <outdir>
       RACE_PROBE=1,90,200 renders stills instead of the sequence.
"""
import bpy, bmesh, math, random, sys, os
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import car_rig as cr

rng = random.Random(7)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUTDIR = argv[0] if argv else "//"

FPS = 24
FRAMES = 361
W, H = 704, 1280

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.resolution_x, scene.render.resolution_y = W, H

SCENE_PAL = dict(cr.PALETTE)
SCENE_PAL.update({
    "asphalt":  (0.205, 0.202, 0.200),
    "asphalt2": (0.255, 0.250, 0.245),
    "kerb":     (0.520, 0.515, 0.500),
    "walk":     (0.430, 0.425, 0.415),
    "line":     (0.780, 0.760, 0.600),
    "linew":    (0.820, 0.820, 0.810),
    "conc":     (0.560, 0.545, 0.515),
    "conc2":    (0.390, 0.380, 0.362),
    "conc3":    (0.680, 0.665, 0.630),
    "bldgglass":(0.105, 0.170, 0.220),
    "bldgglass2":(0.150, 0.135, 0.115),
    "shop":     (0.250, 0.235, 0.220),
    "shoplit":  (0.760, 0.640, 0.330),
    "brick":    (0.380, 0.215, 0.160),
    "pole":     (0.180, 0.182, 0.190),
    "green":    (0.180, 0.260, 0.140),
    "trafg":    (0.150, 0.720, 0.280),
    "trafr":    (0.820, 0.120, 0.090),
    "t1":       (0.560, 0.140, 0.110),
    "t2":       (0.130, 0.180, 0.330),
    "t3":       (0.640, 0.635, 0.620),
    "t4":       (0.120, 0.125, 0.135),
    "t5":       (0.230, 0.280, 0.250),
})
cr.PALETTE = SCENE_PAL
box, cyl, empty = cr.box, cr.cyl, cr.empty


def key(ob, frame, loc=None, rot=None, scl=None):
    if loc is not None:
        ob.location = Vector(loc); ob.keyframe_insert("location", frame=frame)
    if rot is not None:
        ob.rotation_euler = rot; ob.keyframe_insert("rotation_euler", frame=frame)
    if scl is not None:
        ob.scale = Vector(scl); ob.keyframe_insert("scale", frame=frame)


prefs = bpy.context.preferences.edit
prefs.keyframe_new_interpolation_type = 'LINEAR'

# ============================================================ speed and path
X_LANE   = 4.0        # the racing line's x on the avenue
Y_CORNER = 0.0        # where the corner begins
R_TURN   = 20.4       # corner radius
ARC      = R_TURN * math.pi / 2
ROAD_HW  = 9.0        # road half width
WALK_W   = 4.0

SPEED_KEYS = [(1, 24.0), (120, 36.0), (200, 36.0), (250, 14.0),
              (300, 16.5), (361, 30.0)]


def speed(f):
    for i in range(len(SPEED_KEYS) - 1):
        f0, v0 = SPEED_KEYS[i]
        f1, v1 = SPEED_KEYS[i + 1]
        if f0 <= f <= f1:
            t = (f - f0) / float(f1 - f0)
            return v0 + (v1 - v0) * (t * t * (3 - 2 * t))
    return SPEED_KEYS[-1][1]


_dist = [0.0]
for f in range(2, FRAMES + 1):
    _dist.append(_dist[-1] + speed(f) / FPS)
S1 = _dist[249]                      # arc begins at frame 250
TOTAL = _dist[-1]


def path_at(s):
    """Centreline: straight up the avenue, quarter-circle left, then straight
    down the cross street. Returns (pos, yaw)."""
    if s < S1:
        return Vector((X_LANE, Y_CORNER - (S1 - s), 0.0)), 0.0
    if s < S1 + ARC:
        phi = (s - S1) / R_TURN
        c = Vector((X_LANE - R_TURN, Y_CORNER, 0.0))
        return c + Vector((R_TURN * math.cos(phi), R_TURN * math.sin(phi), 0.0)), phi
    t = s - S1 - ARC
    return (Vector((X_LANE - R_TURN, Y_CORNER + R_TURN, 0.0))
            + Vector((-t, 0.0, 0.0))), math.pi / 2


def weave(s):
    """Lane changes on the approach. Faded out before the braking zone so the
    car is settled and straight when it hits the corner."""
    fade = 1.0
    if s > S1 - 95:
        fade = max(0.0, 1.0 - (s - (S1 - 95)) / 70.0)
    return (3.1 * math.sin(s / 47.0) + 1.7 * math.sin(s / 21.5 + 1.1)) * fade


def racing_line(s):
    p, yaw = path_at(s)
    left = Vector((-math.cos(yaw), -math.sin(yaw), 0.0))
    return p + left * weave(s)


def heading_at(s):
    a = racing_line(s - 0.6)
    b = racing_line(s + 0.6)
    d = b - a
    return math.atan2(-d.x, d.y)


# ================================================================= the city
box("avenue", (0, -175, 0.0), (ROAD_HW, 190, 0.01), "asphalt")
box("cross", (-95, Y_CORNER + R_TURN, 0.0), (110, ROAD_HW, 0.01), "asphalt")
box("junction", (X_LANE - R_TURN, Y_CORNER + R_TURN, 0.005),
    (ROAD_HW + 2, ROAD_HW + 2, 0.012), "asphalt2")

# lane markings up the avenue
for i in range(150):
    y = -360 + i * 2.6
    if y > Y_CORNER + R_TURN - 12:
        continue
    for lx in (-4.5, 0.0, 4.5):
        box(f"ln_{i}_{lx}", (lx, y, 0.02), (0.09, 0.85, 0.012), "linew")
for i in range(60):
    x = -200 + i * 2.6
    if x > X_LANE - R_TURN - 12:
        continue
    for ly in (-4.5, 0.0, 4.5):
        box(f"lc_{i}_{ly}", (x, Y_CORNER + R_TURN + ly, 0.02),
            (0.85, 0.09, 0.012), "linew")

# kerbs and sidewalks
for sgn in (-1, 1):
    box(f"kerb{sgn}", (sgn * ROAD_HW, -175, 0.075), (0.22, 190, 0.075), "kerb")
    box(f"walk{sgn}", (sgn * (ROAD_HW + WALK_W / 2), -175, 0.065),
        (WALK_W / 2, 190, 0.065), "walk")
    box(f"ckerb{sgn}", (-95, Y_CORNER + R_TURN + sgn * ROAD_HW, 0.075),
        (110, 0.22, 0.075), "kerb")
    box(f"cwalk{sgn}", (-95, Y_CORNER + R_TURN + sgn * (ROAD_HW + WALK_W / 2), 0.065),
        (110, WALK_W / 2, 0.065), "walk")

# ---- The city is built as STREET FRONTAGE first, not as a culled grid. A
# grid whose spacing does not line up with the kerb leaves the nearest tower
# 20+ m back from the pavement, and a 9:16 frame down that street is then
# mostly empty sky. Frontage rows sit hard against the pavement so the avenue
# reads as a canyon; a coarse back-fill behind them supplies the skyline.
CY = Y_CORNER + R_TURN
FRONT = ROAD_HW + WALK_W          # 13.0, the pavement edge
BAND = ("bldgglass", "conc", "bldgglass2", "conc3")
nb = 0


def tower(cx, cy, w, d, h, face_y=True, face_sgn=-1):
    global nb
    nb += 1
    floors = max(3, int(h / 4.0))
    box(f"gf_{nb}", (cx, cy, 2.6), (w, d, 2.6), "shop")
    # lit shopfronts on the street-facing side only
    for k in range(6):
        if face_y:
            box(f"win_{nb}_{k}", (cx - w + 0.9 + k * (w / 3.0),
                                  cy + face_sgn * d * 1.002, 2.35),
                (w / 8.0, 0.10, 1.35), "shoplit")
        else:
            box(f"win_{nb}_{k}", (cx + face_sgn * w * 1.002,
                                  cy - d + 0.9 + k * (d / 3.0), 2.35),
                (0.10, d / 8.0, 1.35), "shoplit")
    base = rng.choice(BAND)
    alt = "conc2" if base.startswith("bldg") else "bldgglass"
    for fz in range(1, floors):
        m = base if fz % 2 else alt
        if fz % 6 == 0:
            m = "conc2"
        box(f"b_{nb}_{fz}", (cx, cy, 2.6 + fz * 4.0), (w, d, 1.95), m)
    box(f"cap_{nb}", (cx, cy, 2.6 + floors * 4.0), (w + 0.4, d + 0.4, 0.5), "conc2")
    if rng.random() < 0.55:
        box(f"pl_{nb}", (cx + rng.uniform(-3, 3), cy + rng.uniform(-3, 3),
                         2.6 + floors * 4.0 + 1.7), (2.4, 2.0, 1.3), "conc2")


HEIGHTS = (24, 30, 36, 44, 52, 60, 68, 76)
# avenue frontage, both sides
y = -368.0
while y < CY - 16.0:
    d = rng.uniform(9.0, 14.0)
    for sgn in (-1, 1):
        w = rng.uniform(9.0, 13.0)
        setback = rng.uniform(0.0, 2.5)
        tower(sgn * (FRONT + setback + w), y + d, w, d,
              rng.choice(HEIGHTS), face_y=False, face_sgn=-sgn)
    y += d * 2.0 + rng.uniform(1.0, 4.0)

# cross-street frontage, both sides
x = -186.0
while x < X_LANE - R_TURN - 16.0:
    w = rng.uniform(9.0, 14.0)
    for sgn in (-1, 1):
        d = rng.uniform(9.0, 13.0)
        setback = rng.uniform(0.0, 2.5)
        tower(x + w, CY + sgn * (FRONT + setback + d), w, d,
              rng.choice(HEIGHTS), face_y=True, face_sgn=-sgn)
    x += w * 2.0 + rng.uniform(1.0, 4.0)

# coarse back-fill for skyline depth, well behind the frontage rows
for gx in range(-6, 3):
    for gy in range(-11, 2):
        cx = gx * 46.0 + 20.0
        cy = gy * 46.0 + 20.0 + CY
        if abs(cx) < 58 or abs(cy - CY) < 58:
            continue
        tower(cx, cy, rng.uniform(11, 17), rng.uniform(11, 17),
              rng.choice(HEIGHTS))

# ---- street furniture: enormous prior value for very little geometry
for i in range(46):
    y = -330 + i * 8.0
    if y > CY - 12:
        continue
    for sgn in (-1, 1):
        x = sgn * (ROAD_HW + 1.1)
        if i % 3 == 0:
            cyl(f"lamp_{i}{sgn}", (x, y, 4.4), (0.09, 0.09, 4.4), "pole", verts=8)
            box(f"lampa_{i}{sgn}", (x - sgn * 1.1, y, 8.7), (1.2, 0.10, 0.09), "pole")
            box(f"lamph_{i}{sgn}", (x - sgn * 2.1, y, 8.6), (0.36, 0.16, 0.09), "shoplit")
        if i % 5 == 2:
            cyl(f"hyd_{i}{sgn}", (sgn * (ROAD_HW + 2.4), y, 0.48),
                (0.16, 0.16, 0.42), "trafr", verts=8)
        if i % 7 == 3:
            box(f"bin_{i}{sgn}", (sgn * (ROAD_HW + 2.6), y, 0.62),
                (0.34, 0.34, 0.55), "pole")
            cyl(f"tree_{i}{sgn}", (sgn * (ROAD_HW + 2.9), y + 4, 1.6),
                (0.14, 0.14, 1.6), "brick", verts=6)
            box(f"leaf_{i}{sgn}", (sgn * (ROAD_HW + 2.9), y + 4, 4.2),
                (1.5, 1.5, 1.6), "green")

# traffic lights on the junction
for sgn in (-1, 1):
    px, py = X_LANE - R_TURN + sgn * (ROAD_HW + 1.2), CY - ROAD_HW - 1.2
    cyl(f"tl_{sgn}", (px, py, 3.2), (0.11, 0.11, 3.2), "pole", verts=8)
    box(f"tlarm_{sgn}", (px - sgn * 2.2, py, 6.3), (2.2, 0.10, 0.10), "pole")
    box(f"tlbox_{sgn}", (px - sgn * 4.2, py, 5.9), (0.24, 0.20, 0.55), "pole")
    box(f"tlg_{sgn}", (px - sgn * 4.2, py - 0.22, 5.6), (0.16, 0.05, 0.15), "trafg")


def simple_car(name, loc, m, yaw=0.0):
    """Three-box traffic car. Cars carry a huge photographic prior and are what
    actually sells the hero's scale and speed, so there are a lot of them."""
    g = empty(name, loc)
    g.rotation_euler = (0, 0, yaw)
    box(f"{name}_b", (0, 0, 0.62), (0.88, 2.20, 0.34), m, parent=g)
    box(f"{name}_c", (0, -0.20, 1.12), (0.80, 1.20, 0.30), m, parent=g)
    box(f"{name}_g", (0, -0.20, 1.16), (0.82, 1.05, 0.24), "glass", parent=g)
    box(f"{name}_lo", (0, 0, 0.36), (0.90, 2.24, 0.14), "carbon", parent=g)
    box(f"{name}_hl", (0, 2.22, 0.62), (0.66, 0.05, 0.11), "light", parent=g)
    box(f"{name}_tl", (0, -2.22, 0.66), (0.68, 0.05, 0.10), "tail", parent=g)
    for wy in (-1.42, 1.42):
        for wx in (-0.86, 0.86):
            cyl(f"{name}_w{wx}{wy}", (wx, wy, 0.33), (0.33, 0.33, 0.13), "tyre",
                rot=(0, math.radians(90), 0), parent=g, verts=12)
    return g


# ============================================== hero car, path-driven motion
car = cr.Car(name="hero", loc=(X_LANE, -100, 0))

# back / side / height. Sitting closer than this looks better on paper but the
# car's NEAR REAR CORNER is only (back - 2.3) m away, so at a 6.5 m follow with
# a 2.5 m side offset that one corner subtends ~40 degrees and hangs off the
# edge of frame in every single shot. Further back on a longer lens keeps the
# car the same size on screen with far more margin.
CAM_KEYS = [
    (1,    9.2, 1.8, 1.05),
    (120,  8.6, 1.9, 0.95),
    (200,  8.2, 2.0, 0.90),
    (250,  9.4, 1.8, 1.00),
    (272, 11.8, 1.5, 1.35),   # drift: back off and straighten up, because the
    (296, 12.6, 1.9, 1.60),   # car's 31 deg of yaw swings its corners wide
    (330, 10.4, 2.1, 1.35),
    (361,  9.0, 1.9, 1.05),
]


def rig_params(f):
    for i in range(len(CAM_KEYS) - 1):
        f0, b0, s0, u0 = CAM_KEYS[i]
        f1, b1, s1_, u1 = CAM_KEYS[i + 1]
        if f0 <= f <= f1:
            t = (f - f0) / float(f1 - f0)
            t = t * t * (3 - 2 * t)
            return (b0 + (b1 - b0) * t, s0 + (s1_ - s0) * t, u0 + (u1 - u0) * t)
    return CAM_KEYS[-1][1:]


def cam_pos(f):
    """Anchored to the RACING LINE a fixed distance back, not to the street
    centreline - the camera car drives the same line the hero does.

    Anchoring to the centreline meant the hero swung +/-4.8 m laterally
    relative to the camera as it weaved, which at a 7 m follow distance threw
    it clean off the edge of the frame. Following the line instead keeps the
    car centred, and because the camera's own weave lags by the follow
    distance the lane changes still read as movement."""
    s = _dist[f - 1]
    back, side, up = rig_params(f)
    sa = s - back
    yaw = heading_at(sa)
    left = Vector((-math.cos(yaw), -math.sin(yaw), 0.0))
    fwd = Vector((-math.sin(yaw), math.cos(yaw), 0.0))
    return racing_line(sa) + left * side + Vector((0, 0, up)), fwd, s


TCOL = ("t1", "t2", "t3", "t4", "t5")
hero_xy = [(racing_line(_dist[f - 1]).x, racing_line(_dist[f - 1]).y)
           for f in range(1, FRAMES + 1)]
cam_xy = [(cam_pos(f)[0].x, cam_pos(f)[0].y) for f in range(1, FRAMES + 1)]

# ---- Traffic, collision-culled against BOTH the hero's line and the CAMERA's.
# Culling only against the hero left the chase camera driving straight through
# a saloon at frame 180 - the frame was the inside of a red door.
# Same-direction traffic is kept to the outer lane so the hero has something to
# overtake; the near lanes run oncoming, which whips past and sells the speed.
traffic = []
cand = []
for i in range(46):
    lane, sign = rng.choice(((6.4, 1), (-2.2, -1), (-6.4, -1), (6.4, 1)))
    y0 = -330 + i * 7.6 + rng.uniform(-2.2, 2.2)
    v = sign * rng.uniform(9.0, 16.0)
    cand.append((lane, y0, v))
for i, (lane, y0, v) in enumerate(cand):
    ok = True
    for f in range(1, FRAMES + 1):
        ty = y0 + v * (f - 1) / FPS
        hx, hy = hero_xy[f - 1]
        cx_, cy_ = cam_xy[f - 1]
        if (hx - lane) ** 2 + (hy - ty) ** 2 < 5.0 ** 2:
            ok = False
            break
        if (cx_ - lane) ** 2 + (cy_ - ty) ** 2 < 4.5 ** 2:
            ok = False
            break
    if not ok:
        continue
    yaw = 0.0 if v > 0 else math.pi
    g = simple_car(f"tr_{i}", (lane, y0, 0), rng.choice(TCOL), yaw=yaw)
    key(g, 1, loc=(lane, y0, 0))
    key(g, FRAMES, loc=(lane, y0 + v * (FRAMES - 1) / FPS, 0))
    traffic.append(g)

# parked cars on the cross street, so the exit is not a bare road
for i in range(12):
    x = -150 + i * 12.0
    if x > X_LANE - R_TURN - 14:
        continue
    simple_car(f"pk_{i}", (x, CY - ROAD_HW + 1.9, 0), rng.choice(TCOL),
               yaw=math.radians(90))

# ---- drift: yaw the car further into the corner than its velocity, and
# apply opposite lock at the front wheels. Ramped in and out over the arc.
def drift_at(s):
    if s < S1 - 8 or s > S1 + ARC + 26:
        return 0.0
    t = (s - (S1 - 8)) / (ARC + 34)
    t = max(0.0, min(1.0, t))
    return math.radians(31.0) * math.sin(math.pi * t) ** 0.75


spin_angle = 0.0
prev_head = heading_at(0.0)
for f in range(1, FRAMES + 1):
    s = _dist[f - 1]
    v = speed(f)
    p = racing_line(s)
    head = heading_at(s)
    drift = drift_at(s)

    car.root.location = (p.x, p.y, 0.0)
    car.root.rotation_euler = (0, 0, head + drift)

    # --- lateral load from the curvature of the ACTUAL line, so the weave
    #     rolls the body too, not just the corner
    ds = 1.2
    dtheta = heading_at(s + ds) - heading_at(s - ds)
    while dtheta > math.pi:
        dtheta -= 2 * math.pi
    while dtheta < -math.pi:
        dtheta += 2 * math.pi
    curv = dtheta / (2 * ds)
    a_lat = v * v * curv                      # +ve for a left turn
    a_lon = (speed(min(FRAMES, f + 1)) - speed(max(1, f - 1))) * FPS / 2.0

    roll = max(-0.11, min(0.11, a_lat * 0.0042))     # leans OUT of the turn
    pitch = max(-0.055, min(0.045, -a_lon * 0.0060)) # dives on the brakes
    heave = -abs(a_lat) * 0.0012 - max(0.0, -a_lon) * 0.0035
    # road texture: small, smooth, never random - jitter reads as a glitch
    shake = 0.010 * math.sin(f * 0.9) + 0.006 * math.sin(f * 2.3 + 1.0)
    car.body.location = (0, 0, heave + shake)
    car.body.rotation_euler = (pitch + shake * 0.35, roll, 0)

    # --- steering: geometric angle for the corner, minus opposite lock
    steer = math.atan(2 * cr.WB_HALF * curv) - drift * 0.85
    steer = max(-0.62, min(0.62, steer))
    for tag in ("fl", "fr"):
        car.steer[tag].rotation_euler = (0, 0, steer)
    for tag in ("rl", "rr"):
        car.steer[tag].rotation_euler = (0, 0, 0)

    spin_angle += (v / cr.WR) / FPS
    for tag in car.spin:
        car.spin[tag].rotation_euler = (spin_angle, 0, 0)

    car.key(f)
    prev_head = head

# ==================================================================== lighting
sun_data = bpy.data.lights.new("sun", type='SUN')
sun_data.energy = 3.0
sun_data.color = (1.0, 0.87, 0.72)
sun = bpy.data.objects.new("sun", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(52), 0, math.radians(-38))

world = bpy.data.worlds.new("world")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.66, 0.70, 0.76, 1.0)
world.color = (0.655, 0.700, 0.770)   # Workbench reads THIS, not the node tree

# ====================================================================== camera
prefs.keyframe_new_interpolation_type = 'BEZIER'
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 32.0
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
target = bpy.data.objects.new("look_at", None)
scene.collection.objects.link(target)
con = cam.constraints.new('TRACK_TO')
con.target = target
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'

# Chase rig anchored to the ROAD, not to the car's yaw. During the drift the
# car swings ~31 degrees across its own velocity; a camera bolted to the body
# would swing with it and the slide would be invisible. Following the racing
# line instead lets the car visibly step sideways in frame, which is the shot.
# Keyed EVERY frame. The rig offsets interpolate smoothly, but the anchor has
# to be re-evaluated per frame: the car moves on a smoothstepped speed profile,
# so keying the camera at only the seven rig changes let Blender interpolate
# its position in a straight line between them while the car accelerated away
# underneath. The car left frame entirely in the gaps.
# Aim sits ABOVE the car (1.45 vs a ~0.95 camera) so the lens tilts up a few
# degrees; aiming level with the bodywork filled the bottom 40% of a 9:16
# frame with bare tarmac.
prefs.keyframe_new_interpolation_type = 'LINEAR'
for f in range(1, FRAMES + 1):
    c, _f, s = cam_pos(f)
    hy = heading_at(s)
    fwd = Vector((-math.sin(hy), math.cos(hy), 0.0))
    key(cam, f, loc=c)
    aim = racing_line(s) + fwd * 2.4
    key(target, f, loc=(aim.x, aim.y, 2.30))


# ---- framing assert: the whole car must stay in frame
from bpy_extras.object_utils import world_to_camera_view

def check_framing(f, margin=0.02):
    scene.frame_set(f)
    bpy.context.view_layer.update()
    s = _dist[f - 1]
    p = racing_line(s)
    th = heading_at(s) + drift_at(s)
    fwd = Vector((-math.sin(th), math.cos(th), 0.0))
    lat = Vector((-math.cos(th), -math.sin(th), 0.0))
    bad = []
    for sy in (-cr.L_HALF, cr.L_HALF):
        for sx in (-cr.W_HALF, cr.W_HALF):
            for z in (0.0, cr.H_TOP):
                q = p + fwd * sy + lat * sx + Vector((0, 0, z))
                c = world_to_camera_view(scene, cam, q)
                if not (margin < c.x < 1 - margin and margin < c.y < 1 - margin
                        and c.z > 0):
                    bad.append((round(c.x, 3), round(c.y, 3)))
    if bad:
        print(f"[race] FRAMING WARNING f{f}: {len(bad)}/8 corners out -> {bad[:4]}")
    return not bad


_ok = all([check_framing(f) for f in
           (1, 60, 120, 180, 220, 250, 270, 296, 320, 340, FRAMES)])
print("[race] framing", "OK" if _ok else "HAS WARNINGS")

# ====================================================================== render
scene.frame_start, scene.frame_end = 1, FRAMES
scene.render.fps = FPS
scene.render.resolution_percentage = 100
scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading
sh.light = 'STUDIO'
sh.studio_light = 'Default'
sh.color_type = 'MATERIAL'
sh.show_shadows = True
sh.shadow_intensity = 0.50
sh.show_cavity = True
sh.background_type = 'WORLD'
sh.background_color = (0.640, 0.685, 0.750)
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.filepath = f"{OUTDIR}/bl_"

print(f"[race] S1={S1:.1f} total={TOTAL:.1f} buildings={nb} traffic={len(traffic)}")

_probe = os.environ.get("RACE_PROBE", "")
if _probe:
    base = scene.render.filepath
    for fr in [int(x) for x in _probe.split(",")]:
        scene.frame_set(fr)
        scene.render.filepath = f"{base}{fr:04d}"
        bpy.ops.render.render(write_still=True)
        print("[race] probe", fr)
else:
    print(f"[race] {FRAMES}f {W}x{H} -> {scene.render.filepath}")
    bpy.ops.render.render(animation=True)
    print("[race] DONE")
