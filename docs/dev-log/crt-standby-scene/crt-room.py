"""The standby room: a blue bedroom at night, a small maroon CRT on a white stand.

Renders the plate the CRT standby screen draws (frontend/src/assets/standby/),
and writes where the TV glass lands in the picture. Runs inside Blender's
Python (bpy as a module or `blender -b -P`); see README.md beside this file.

    python crt-room.py -- <width> <samples> <out.png> [--screen on|off]
                          [--pass full|tvlight] [--covers DIR] [--frame PNG]
                          [--dust on|off]

--screen off   the glass is dark and glossy and the TV casts no light: the
               plate the interface lays the game video over.
--screen on    the validated look, with --frame as the picture on the glass.
--pass tvlight only the light the TV throws on the room (white), every other
               light and emitter off: the interface tints it with the video's
               colour and adds it over the plate.
"""
import json
import math
import os
import random
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

D = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
flags = {argv[i][2:]: argv[i + 1] for i in range(len(argv) - 1) if argv[i].startswith('--')}
args = [a for i, a in enumerate(argv) if not a.startswith('--') and not (i and argv[i - 1].startswith('--'))]
RES = int(args[0]) if args else 960
SAMPLES = int(args[1]) if len(args) > 1 else 32
OUT = args[2] if len(args) > 2 else f'{D}/room.png'
SCREEN = flags.get('screen', 'off')
PASS = flags.get('pass', 'full')
# The floor boxes are the owner's own library: covers as GameCore stores them.
C = flags.get('covers') or os.path.join(os.environ.get('GAMECORE_DATA', D), 'emu', 'covers')
FRAME = flags.get('frame') or f'{D}/frame-crt.png'
ASSETS = flags.get('assets') or f'{D}/assets'
assert SCREEN in ('on', 'off') and PASS in ('full', 'tvlight'), 'bad --screen/--pass'

R = math.radians
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

def mat(name, color, rough=0.6, emit=None, strength=0):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = color; b.inputs['Roughness'].default_value = rough
    if emit: b.inputs['Emission Color'].default_value = emit; b.inputs['Emission Strength'].default_value = strength
    return m

def box(name, size, loc, m, rot=(0, 0, 0), bevel=0.006):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=[R(a) for a in rot])
    o = bpy.context.object; o.name = name; o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        b = o.modifiers.new('b', 'BEVEL'); b.width = bevel; b.segments = 3
    o.data.materials.append(m); return o

def attach(child, parent, loc, rx=0):
    bpy.context.view_layer.update()
    child.matrix_world = parent.matrix_world @ Matrix.Translation(loc) @ Matrix.Rotation(R(rx), 4, 'X')

def img_mat(name, path, emit=0):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; b = nt.nodes['Principled BSDF']
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(path)
    nt.links.new(t.outputs['Color'], b.inputs['Base Color']); b.inputs['Roughness'].default_value = 0.35
    if emit: nt.links.new(t.outputs['Color'], b.inputs['Emission Color']); b.inputs['Emission Strength'].default_value = emit
    return m

def plane(size, m, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=[R(a) for a in rot])
    o = bpy.context.object; o.scale = (size[0], size[1], 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(m); return o

# ── room ───────────────────────────────────────────────────────────────────
carpet = mat('carpet', (0.2, 0.17, 0.34, 1), 1.0)
nt = carpet.node_tree; cb = nt.nodes['Principled BSDF']
nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 1500; nz.inputs['Detail'].default_value = 4
bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.08
nt.links.new(nz.outputs['Fac'], bp.inputs['Height']); nt.links.new(bp.outputs['Normal'], cb.inputs['Normal'])
plane((10, 10), carpet, (0, 0, 0))
wall = mat('wall', (0.12, 0.22, 0.6, 1), 0.85)
# back wall at y=1, with a window hole x∈[0.85, 2.6], z∈[0.55, 2.0]
box('wl', (4.8, 0.05, 3), (0.8 - 2.4, 1.0, 1.5), wall, bevel=0)
box('wr', (3, 0.05, 3), (2.6 + 1.5, 1.0, 1.5), wall, bevel=0)
box('wb', (1.8, 0.05, 0.45), (1.7, 1.0, 0.225), wall, bevel=0)
box('wt', (1.8, 0.05, 1.0), (1.7, 1.0, 2.5), wall, bevel=0)
skirt = mat('skirt', (0.4, 0.5, 0.85, 1), 0.5)
box('sk', (8, 0.02, 0.08), (0, 0.97, 0.04), skirt, bevel=0)
# outside: a cold night glow behind the blinds
sky = mat('sky', (0, 0, 0, 1), 1, emit=(0.35, 0.45, 1.0, 1), strength=0.5)
skyo = plane((3, 2.5), sky, (1.7, 1.5, 1.3), (90, 0, 0)); skyo.visible_shadow = False
slat = mat('slat', (0.62, 0.7, 1.0, 1), 0.55, emit=(0.5, 0.6, 1.0, 1), strength=0.05)
for i in range(32):
    box(f'slat{i}', (1.82, 0.045, 0.004), (1.7, 0.965, 0.49 + i * 0.049), slat, rot=(55, 0, 0), bevel=0)
moon = bpy.data.lights.new('moon', 'SPOT'); moon.spot_size = R(30); moon.spot_blend = 0.6; moon.energy = 250; moon.color = (0.62, 0.64, 1.0); moon.shadow_soft_size = 0.07
mo = bpy.data.objects.new('moon', moon); sc.collection.objects.link(mo); mo.location = (2.1, 2.4, 3.2)
mo.rotation_euler = (Vector((0.7, 0.68, 0.46)) - mo.location).to_track_quat('-Z', 'Y').to_euler()

# ── stand: white, low, one shelf, open bottom ──────────────────────────────
white = mat('white', (0.85, 0.87, 0.95, 1), 0.4)
SX, SY, W, Dp, H = 0.4, 0.72, 0.9, 0.42, 0.46
box('top', (W, Dp, 0.03), (SX, SY, H), white)
box('shelf', (W - 0.06, Dp, 0.025), (SX, SY, 0.235), white)
box('sL', (0.03, Dp, H), (SX - W / 2 + 0.015, SY, H / 2), white)
box('sR', (0.03, Dp, H), (SX + W / 2 - 0.015, SY, H / 2), white)
black = mat('black', (0.025, 0.025, 0.03, 1), 0.35)
lab = mat('lab', (0.88, 0.88, 0.86, 1), 0.6)
box('t1', (0.2, 0.11, 0.028), (SX - 0.2, SY - 0.05, 0.263), black, rot=(0, 0, 6))
box('t2', (0.2, 0.11, 0.028), (SX + 0.08, SY - 0.06, 0.263), black, rot=(0, 0, -3))
box('t3', (0.2, 0.11, 0.028), (SX + 0.07, SY - 0.05, 0.291), black, rot=(0, 0, 4))
for k, (path, rot) in enumerate([(f'{C}/gba/Advance Wars (Europe).png', 8), (f'{C}/gba/Fire Emblem (Europe).webp', -5), (f'{C}/azahar/Pokemon X (Europe).png', 3)]):
    z = 0.255 + k * 0.014
    box(f'st{k}', (0.15, 0.17, 0.012), (SX + 0.3, SY - 0.02, z), black, rot=(0, 0, rot), bevel=0.002)
    plane((0.14, 0.16), img_mat(f'stc{k}', path), (SX + 0.3, SY - 0.02, z + 0.0065), (0, 0, rot))
box('l3', (0.13, 0.002, 0.016), (SX + 0.07, SY - 0.106, 0.291), lab, rot=(0, 0, 4), bevel=0)

# ── the CRT ────────────────────────────────────────────────────────────────
maroon = mat('maroon', (0.13, 0.025, 0.05, 1), 0.45)
tv = box('tv', (0.42, 0.4, 0.34), (SX - 0.1, SY + 0.0, H + 0.015 + 0.17), maroon, rot=(0, 0, -22), bevel=0.018)
bez = mat('bez', (0.015, 0.012, 0.015, 1), 0.3)
bz = plane((0.36, 0.29), bez, (0, 0, 0)); attach(bz, tv, (-0.02, -0.2015, 0.015), 90)
bpy.ops.mesh.primitive_plane_add(size=1); scr = bpy.context.object; scr.scale = (0.3, 0.235, 1)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
if SCREEN == 'on':
    scr.data.materials.append(img_mat('screen', FRAME, emit=0.55))
elif PASS == 'tvlight':
    # A flat white picture: the light pass is tinted by the UI, not here.
    scr.data.materials.append(mat('screen', (0, 0, 0, 1), 1, emit=(1, 1, 1, 1), strength=0.55))
    scr.visible_camera = False   # the video covers the glass; only its light is wanted
else:
    # Dark glass: no emission, glossy, so it only shows a faint reflection of the room.
    scr.data.materials.append(mat('screen', (0.012, 0.013, 0.016, 1), 0.07))
attach(scr, tv, (-0.02, -0.203, 0.02), 90)
led = mat('led', (1, 0.1, 0.1, 1), 0.3, emit=(1, 0.08, 0.06, 1), strength=10)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.007); l = bpy.context.object; l.data.materials.append(led); attach(l, tv, (0.16, -0.203, -0.13))
tl = bpy.data.lights.new('tvl', 'AREA'); tl.size = 0.3; tl.energy = 10; tl.color = (1, 1, 1) if PASS == 'tvlight' else (0.55, 0.7, 1.0)
to = bpy.data.objects.new('tvl', tl); sc.collection.objects.link(to); attach(to, tv, (-0.02, -0.25, 0.02), 90)
to.hide_render = SCREEN == 'off' and PASS == 'full'   # the TV is off: no glow

# ── white console on the floor, front-left of the stand ───────────────────
# (no console under the stand: its white shell caught the light)
cab = bpy.data.curves.new('cab', 'CURVE'); cab.dimensions = '3D'; cab.bevel_depth = 0.0045; cab.bevel_resolution = 3
s = cab.splines.new('BEZIER'); pts = [(SX - 0.35, SY - 0.26, 0.012), (SX - 0.6, SY - 0.42, 0.006), (SX - 0.95, SY - 0.38, 0.006),
                                      (SX - 1.05, SY - 0.6, 0.006), (SX - 0.9, SY - 0.78, 0.006), (SX - 0.98, SY - 0.92, 0.006)]
s.bezier_points.add(len(pts) - 1)
for p, c in zip(s.bezier_points, pts): p.co = c; p.handle_left_type = p.handle_right_type = 'AUTO'
# (the console's own white cable was dropped: it read as clutter)

# ── on the carpet: game boxes, the ball under the stand ───────────────────
for i, (path, loc, rot) in enumerate([
        (f'{C}/duckstation/Crash Bandicoot (Europe).png', (SX - 0.72, SY - 0.12), 12),
        (f'{C}/gba/Golden Sun (Europe).webp', (SX - 0.38, SY - 0.62), -6),
        (f'{C}/azahar/Mario Kart 7 (Europe).png', (SX - 0.08, SY - 0.66), 18),
        (f'{C}/duckstation/Final Fantasy VII (Europe) (Disc 1).png', (SX - 0.62, SY - 0.42), -22),
        (f'{C}/gopher64/Super Mario 64 (Europe).webp', (SX + 0.25, SY - 0.48), -10),
        (f'{C}/snes9x/Chrono Trigger (USA).png', (SX - 0.9, SY - 0.55), 35),
        (f'{C}/megadrive/Sonic the Hedgehog (Europe).webp', (SX + 0.05, SY - 0.95), -28),
        (f'{C}/gba/Metroid Fusion (Europe).webp', (SX - 0.55, SY - 0.85), 8)]):
    box(f'case{i}', (0.15, 0.17, 0.012), (loc[0], loc[1], 0.006), black, rot=(0, 0, rot), bevel=0.002)
    plane((0.14, 0.16), img_mat(f'cov{i}', path), (loc[0], loc[1], 0.0125), (0, 0, rot))
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.065, location=(SX + 0.22, SY - 0.05, 0.065))
ball = bpy.context.object; bpy.ops.object.shade_smooth()
bm = mat('ball', (0.95, 0.62, 0.1, 1), 0.3); ball.data.materials.append(bm)
# wall socket, two plugs, leads to the floor
plate = mat('plate', (0.9, 0.9, 0.93, 1), 0.4)
box('sock', (0.09, 0.012, 0.15), (SX + 0.6, 0.97, 0.22), plate, bevel=0.004)
for z in (0.26, 0.19): box('plug', (0.035, 0.035, 0.035), (SX + 0.6, 0.945, z), black)
for k, z in enumerate((0.26, 0.19)):
    c2 = bpy.data.curves.new('lead', 'CURVE'); c2.dimensions = '3D'; c2.bevel_depth = 0.0035
    sp2 = c2.splines.new('BEZIER'); pp = [(SX + 0.6 - 0.01 * k, 0.93, z - 0.02), (SX + 0.58 - 0.03 * k, 0.9, 0.08), (SX + 0.5, 0.85, 0.005)]
    sp2.bezier_points.add(2)
    for p, c in zip(sp2.bezier_points, pp): p.co = c; p.handle_left_type = p.handle_right_type = 'AUTO'
    o2 = bpy.data.objects.new('lead', c2); sc.collection.objects.link(o2); o2.data.materials.append(black if k == 0 else mat('lw', (0.9, 0.9, 0.9, 1), 0.4))

# the pad at the end of its cable
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=f'{ASSETS}/gamepad/gamepad_1k.gltf')
pad = bpy.data.objects.new('pad', None); sc.collection.objects.link(pad)
for o in set(bpy.data.objects) - before - {pad}:
    if o.parent is None: o.parent = pad
pad.location = (SX + 0.33, SY - 0.78, 0.004); pad.rotation_euler = (0, 0, R(15)); pad.scale = (1.6, 1.6, 1.6)

# ── side table and lamp, back left ────────────────────────────────────────
wood = mat('wood', (0.6, 0.32, 0.12, 1), 0.45)
TX, TY = -0.85, 0.7
box('tt', (0.5, 0.42, 0.03), (TX, TY, 0.56), wood)
for dx in (-0.22, 0.22):
    for dy in (-0.18, 0.18): box('leg', (0.035, 0.035, 0.55), (TX + dx, TY + dy, 0.275), wood)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.085, location=(TX, TY, 0.66)); bs = bpy.context.object; bs.scale = (1, 1, 1.15)
bs.data.materials.append(mat('lb', (0.92, 0.9, 0.88, 1), 0.3)); bpy.ops.object.shade_smooth()
bpy.ops.mesh.primitive_cone_add(radius1=0.21, radius2=0.11, depth=0.2, end_fill_type='NOTHING', location=(TX, TY, 0.88))
sh = bpy.context.object; sh.data.materials.append(mat('sh', (0.95, 0.5, 0.42, 1), 0.7, emit=(1, 0.52, 0.4, 1), strength=0.9))
sh.modifiers.new('t', 'SOLIDIFY').thickness = 0.004
box('book', (0.16, 0.11, 0.02), (TX + 0.12, TY - 0.08, 0.585), mat('bk', (0.15, 0.3, 0.6, 1), 0.5), rot=(0, 0, 12))
lp = bpy.data.lights.new('lamp', 'POINT'); lp.energy = 30; lp.color = (1, 0.58, 0.38); lp.shadow_soft_size = 0.05
lo = bpy.data.objects.new('lamp', lp); sc.collection.objects.link(lo); lo.location = (TX, TY, 0.86)

# ── dust ──────────────────────────────────────────────────────────────────
# Off by default: a mote baked into the plate cannot move, and still dust in
# the air reads as dead pixels. The interface draws falling dust on top
# (CrtStandby/DustMotes.tsx). `--dust on` restores the validated stills.
random.seed(7)
dust = mat('dust', (1, 1, 1, 1), 0.5, emit=(0.85, 0.85, 1, 1), strength=1.0)
for i in range(45 if flags.get('dust', 'off') == 'on' else 0):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=0.0016, subdivisions=1,
        location=(random.uniform(-1.2, 1.5), random.uniform(-0.6, 0.9), random.uniform(0.05, 1.3)))
    bpy.context.object.data.materials.append(dust)

# ── world, camera ─────────────────────────────────────────────────────────
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.09, 0.07, 0.2, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 0.5
fl = bpy.data.lights.new('fill', 'AREA'); fl.size = 3; fl.energy = 18; fl.color = (0.55, 0.45, 1.0)
fo = bpy.data.objects.new('fill', fl); sc.collection.objects.link(fo); fo.location = (-0.6, -2.0, 2.2)
fo.rotation_euler = (Vector((0.2, 0.6, 0.2)) - fo.location).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (-1.2, -1.95, 1.8); target = Vector((0.05, 0.45, 0.42))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 41; cam.data.dof.use_dof = True
cam.data.dof.focus_distance = (Vector((SX - 0.1, SY, 0.6)) - cam.location).length; cam.data.dof.aperture_fstop = 1.4

r = sc.render; r.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
r.resolution_x = RES; r.resolution_y = RES * 9 // 16
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast'; sc.view_settings.exposure = -0.2
if PASS == 'tvlight':
    # Only the TV: every other light, emitter and the sky go dark. Standard view
    # transform, so the pass adds over the plate without AgX's tone curve twice.
    for o in sc.objects:
        if o.type == 'LIGHT' and o.name != 'tvl':
            o.hide_render = True
    for m in bpy.data.materials:
        b = m.node_tree.nodes.get('Principled BSDF') if m.use_nodes else None
        if b and m.name != 'screen':
            b.inputs['Emission Strength'].default_value = 0
    w.node_tree.nodes['Background'].inputs[1].default_value = 0
    sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'
r.filepath = OUT
bpy.ops.render.render(write_still=True)

# Where the screen lands in the picture: four corners in 0..1 image space, for
# the interface to lay the game video over the glass with a CSS matrix3d.
bpy.context.view_layer.update()
corners = [scr.matrix_world @ Vector(v.co) for v in scr.data.vertices]
pts = [world_to_camera_view(sc, cam, c) for c in corners]
json.dump([[round(p.x, 5), round(1 - p.y, 5)] for p in pts], open(os.path.splitext(OUT)[0] + '-screen.json', 'w'))
