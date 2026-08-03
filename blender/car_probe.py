"""Build the car alone and render silhouette-check views.
Usage: blender -b -P car_probe.py -- <outdir>
"""
import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import car_rig as cr

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "./probe"

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

cr.box("ground", (0, 0, -0.05), (40, 40, 0.05), "carbon2")
car = cr.Car(loc=(0, 0, 0))

sun_data = bpy.data.lights.new("sun", type='SUN')
sun_data.energy = 3.2
sun_data.color = (1.0, 0.88, 0.74)
sun = bpy.data.objects.new("sun", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(54), 0, math.radians(40))

world = bpy.data.worlds.new("world")
scene.world = world
world.color = (0.660, 0.705, 0.775)

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 85.0
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
tgt = bpy.data.objects.new("look", None)
scene.collection.objects.link(tgt)
tgt.location = (0, 0, 0.62)
con = cam.constraints.new('TRACK_TO')
con.target = tgt
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'

scene.render.resolution_x, scene.render.resolution_y = 1100, 720
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

R = 22.0
VIEWS = {
    "side":    (-R, 0, 1.4),
    "front3q": (-R * 0.66, R * 0.72, 2.2),
    "front":   (0, R, 1.5),
    "rear3q":  (-R * 0.66, -R * 0.72, 2.4),
    "low3q":   (-R * 0.55, R * 0.60, 0.75),
    "top":     (0.01, -0.01, R),
}
os.makedirs(OUT, exist_ok=True)
for name, loc in VIEWS.items():
    cam.location = loc
    scene.render.filepath = f"{OUT}/car_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("[probe]", name)
print("[probe] DONE")
