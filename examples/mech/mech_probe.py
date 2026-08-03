"""Build the Catapult alone and render silhouette-check views.

Usage: blender -b -P mech_probe.py -- <outdir>
Renders front / front-3q / side / rear-3q / rear, plus a mid-stride pose,
in the same Workbench setup the real shot uses so what I look at is what
LTX will see.
"""
import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catapult_rig as cr

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "./probe"
POSE = os.environ.get("MECH_POSE", "stand")

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

cr.box("ground", (0, 0, -0.05), (60, 60, 0.05), "hull")
mech = cr.Catapult(loc=(0, 0, 0))

if POSE == "stride":
    # mid-stride: left foot planted forward, right foot swinging through
    mech.pelvis.location = (0, 0, cr.HIP_Z - 0.30)
    mech.pose_leg("l", (-cr.HIP_X, 3.4, 0.0))
    mech.pose_leg("r", (cr.HIP_X, -1.4, 1.0), foot_pitch=math.radians(14))
    mech.torso.rotation_euler = (math.radians(4), 0, math.radians(-3))
else:
    mech.pose_leg("l", (-cr.HIP_X, 0.4, 0.0))
    mech.pose_leg("r", (cr.HIP_X, 0.4, 0.0))

sun_data = bpy.data.lights.new("sun", type='SUN')
sun_data.energy = 3.2
sun_data.color = (1.0, 0.86, 0.70)
sun = bpy.data.objects.new("sun", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(56), 0, math.radians(38))

world = bpy.data.worlds.new("world")
scene.world = world
world.color = (0.660, 0.705, 0.775)

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 55.0
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
tgt = bpy.data.objects.new("look", None)
scene.collection.objects.link(tgt)
tgt.location = (0, 0, cr.MECH_TOP * 0.48)
con = cam.constraints.new('TRACK_TO')
con.target = tgt
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'

scene.render.resolution_x, scene.render.resolution_y = 760, 1000
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
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'

# +Y is forward, so "front" means looking from +Y back toward the mech
R, Z = 52.0, 9.5
VIEWS = {
    "front":  (0, R, Z),
    "front3q": (-R * 0.62, R * 0.78, Z),
    "side":   (-R, 0, Z),
    "rear3q": (-R * 0.62, -R * 0.78, Z),
    "rear":   (0, -R, Z),
    "low3q":  (-R * 0.50, R * 0.62, 3.0),
}
os.makedirs(OUT, exist_ok=True)
for name, loc in VIEWS.items():
    cam.location = loc
    scene.render.filepath = f"{OUT}/{POSE}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("[probe]", name)
print("[probe] DONE", cr.MECH_TOP)
