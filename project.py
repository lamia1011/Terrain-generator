from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import math
import random

# ─────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────
WIDTH, HEIGHT  = 1000, 700
GRID_SIZE      = 80       # terrain grid resolution
TERRAIN_SCALE  = 0.25     # world unit per grid cell
HEIGHT_SCALE   = 6.0      # vertical exaggeration

# ─────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────
angle_x     = 35.0
angle_y     = -30.0
cam_drag    = False
last_mx = last_my = 0
zoom        = 1.0

wireframe   = False
show_water  = True
show_snow   = True
show_grid   = False
animate     = False
anim_offset = 0.0
seed        = 42

terrain_verts  = []   # [row][col] = (x, y, z)
terrain_colors = []   # [row][col] = (r, g, b)
water_level    = 0.5  # world-y water surface

# ─────────────────────────────────────────
#  PERLIN NOISE  (pure Python, no libs)
# ─────────────────────────────────────────
class PerlinNoise:
    def __init__(self, seed=0):
        random.seed(seed)
        self.perm = list(range(256))
        random.shuffle(self.perm)
        self.perm += self.perm

    def fade(self, t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    def lerp(self, a, b, t):
        return a + t * (b - a)

    def grad(self, h, x, y):
        h &= 3
        if h == 0: return  x + y
        if h == 1: return -x + y
        if h == 2: return  x - y
        return -x - y

    def noise(self, x, y):
        xi = int(math.floor(x)) & 255
        yi = int(math.floor(y)) & 255
        xf = x - math.floor(x)
        yf = y - math.floor(y)
        u  = self.fade(xf)
        v  = self.fade(yf)
        p  = self.perm
        aa = p[p[xi]   + yi]
        ab = p[p[xi]   + yi + 1]
        ba = p[p[xi+1] + yi]
        bb = p[p[xi+1] + yi + 1]
        x1 = self.lerp(self.grad(aa, xf,   yf),   self.grad(ba, xf-1, yf),   u)
        x2 = self.lerp(self.grad(ab, xf,   yf-1), self.grad(bb, xf-1, yf-1), u)
        return (self.lerp(x1, x2, v) + 1) / 2   # 0..1

    def octave(self, x, y, octaves=6, persistence=0.5, lacunarity=2.0):
        val, amp, freq, mx = 0, 1, 1, 0
        for _ in range(octaves):
            val  += self.noise(x * freq, y * freq) * amp
            mx   += amp
            amp  *= persistence
            freq *= lacunarity
        return val / mx

# ─────────────────────────────────────────
#  TERRAIN GENERATION
# ─────────────────────────────────────────
def height_color(h, water_y, snow_y):
    """Map height to biome color."""
    if h < water_y + 0.05:                      # Deep water
        t = max(0, h / (water_y + 0.05))
        return (0.05 + t*0.1, 0.2 + t*0.2, 0.55 + t*0.2)
    elif h < water_y + 0.3:                      # Beach / sand
        return (0.82, 0.75, 0.50)
    elif h < water_y + 1.5:                      # Lowland grass
        t = (h - water_y - 0.3) / 1.2
        return (0.2 + t*0.1, 0.55 - t*0.1, 0.15)
    elif h < water_y + 3.0:                      # Forest / highland
        t = (h - water_y - 1.5) / 1.5
        return (0.15 + t*0.2, 0.38 - t*0.12, 0.1)
    elif h < water_y + 4.2:                      # Rocky mountain
        t = (h - water_y - 3.0) / 1.2
        return (0.45 + t*0.25, 0.40 + t*0.20, 0.35 + t*0.15)
    else:                                         # Snow cap
        t = min(1.0, (h - water_y - 4.2) / 0.8)
        return (0.85 + t*0.15, 0.88 + t*0.12, 0.92 + t*0.08)

def generate_terrain(s=None):
    global terrain_verts, terrain_colors, seed, water_level
    if s is not None:
        seed = s
    pn = PerlinNoise(seed)
    N  = GRID_SIZE
    cx = N / 2.0
    cz = N / 2.0

    terrain_verts  = []
    terrain_colors = []

    raw = []
    for row in range(N + 1):
        r_row = []
        for col in range(N + 1):
            nx = col * 0.045
            ny = row * 0.045
            h  = pn.octave(nx, ny, octaves=7, persistence=0.52, lacunarity=2.1)
            r_row.append(h)
        raw.append(r_row)

    # Normalize 0..1 then scale
    flat   = [v for row in raw for v in row]
    lo, hi = min(flat), max(flat)
    rng    = hi - lo if hi != lo else 1

    water_y = lo + (hi - lo) * 0.30   # water at 30% of range
    snow_y  = lo + (hi - lo) * 0.78

    for row in range(N + 1):
        v_row = []
        c_row = []
        for col in range(N + 1):
            h_norm = (raw[row][col] - lo) / rng   # 0..1
            h_world = h_norm * HEIGHT_SCALE
            x = (col - cx) * TERRAIN_SCALE
            z = (row - cz) * TERRAIN_SCALE
            v_row.append((x, h_world, z))

            h_abs = lo + h_norm * (hi - lo)
            color = height_color(h_abs, water_y, snow_y)
            c_row.append(color)
        terrain_verts.append(v_row)
        terrain_colors.append(c_row)

    water_level = (water_y - lo) / rng * HEIGHT_SCALE
    print(f"✅ Terrain generated — seed={seed}")

# ─────────────────────────────────────────
#  NORMAL CALCULATION
# ─────────────────────────────────────────
def face_normal(v0, v1, v2):
    ax = v1[0]-v0[0]; ay = v1[1]-v0[1]; az = v1[2]-v0[2]
    bx = v2[0]-v0[0]; by = v2[1]-v0[1]; bz = v2[2]-v0[2]
    nx = ay*bz - az*by
    ny = az*bx - ax*bz
    nz = ax*by - ay*bx
    ln = math.sqrt(nx*nx + ny*ny + nz*nz) + 1e-9
    return nx/ln, ny/ln, nz/ln

# ─────────────────────────────────────────
#  DRAWING
# ─────────────────────────────────────────
def draw_terrain():
    N = GRID_SIZE
    glEnable(GL_LIGHTING)

    if wireframe:
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        glDisable(GL_LIGHTING)
    else:
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    for row in range(N):
        glBegin(GL_TRIANGLE_STRIP)
        for col in range(N + 1):
            for dr in [0, 1]:
                r = row + dr
                v  = terrain_verts[r][col]
                c  = terrain_colors[r][col]

                # Smooth normal from neighbours
                if 0 < r < N and 0 < col < N:
                    vl = terrain_verts[r][col-1]
                    vr = terrain_verts[r][col+1]
                    vu = terrain_verts[r-1][col]
                    vd = terrain_verts[r+1][col]
                    nx = -(vr[1] - vl[1])
                    nz = -(vd[1] - vu[1])
                    ny =  2.0 * TERRAIN_SCALE
                    ln = math.sqrt(nx*nx + ny*ny + nz*nz) + 1e-9
                    glNormal3f(nx/ln, ny/ln, nz/ln)
                else:
                    glNormal3f(0, 1, 0)

                if wireframe:
                    glColor3f(0.4, 0.8, 0.4)
                else:
                    glColor3f(*c)
                glVertex3f(*v)
        glEnd()

    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)


def draw_water():
    if not show_water:
        return
    N  = GRID_SIZE
    cx = N / 2.0
    x0 = -cx * TERRAIN_SCALE
    x1 =  cx * TERRAIN_SCALE
    z0 =  x0
    z1 =  x1
    wy = water_level + (0.04 * math.sin(anim_offset) if animate else 0)

    glDisable(GL_LIGHTING)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glColor4f(0.1, 0.35, 0.75, 0.45)
    glNormal3f(0, 1, 0)
    glBegin(GL_QUADS)
    glVertex3f(x0, wy, z0)
    glVertex3f(x1, wy, z0)
    glVertex3f(x1, wy, z1)
    glVertex3f(x0, wy, z1)
    glEnd()
    glDisable(GL_BLEND)
    glEnable(GL_LIGHTING)


def draw_grid_overlay():
    if not show_grid:
        return
    N  = GRID_SIZE
    cx = N / 2.0
    glDisable(GL_LIGHTING)
    glColor4f(0.0, 0.0, 0.0, 0.25)
    glLineWidth(0.5)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    for row in range(0, N+1, 5):
        glBegin(GL_LINE_STRIP)
        for col in range(N+1):
            v = terrain_verts[row][col]
            glVertex3f(v[0], v[1]+0.01, v[2])
        glEnd()
    for col in range(0, N+1, 5):
        glBegin(GL_LINE_STRIP)
        for row in range(N+1):
            v = terrain_verts[row][col]
            glVertex3f(v[0], v[1]+0.01, v[2])
        glEnd()
    glDisable(GL_BLEND)
    glEnable(GL_LIGHTING)


def draw_sky():
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glOrtho(-1, 1, -1, 1, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glBegin(GL_QUADS)
    glColor3f(0.42, 0.65, 0.95)   # top sky blue
    glVertex2f(-1,  1)
    glVertex2f( 1,  1)
    glColor3f(0.75, 0.88, 1.0)    # horizon lighter
    glVertex2f( 1, -1)
    glVertex2f(-1, -1)
    glEnd()

    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)


def draw_hud():
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glOrtho(0, WIDTH, 0, HEIGHT, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    def text(s, x, y, color=(1,1,1)):
        glColor3f(*color)
        glRasterPos2f(x, y)
        for ch in s:
            glutBitmapCharacter(GLUT_BITMAP_HELVETICA_12, ord(ch))

    text(f"Seed: {seed}", 12, HEIGHT-20, (1.0, 0.9, 0.3))
    text(f"Grid: {GRID_SIZE}x{GRID_SIZE}", 12, HEIGHT-38)
    text(f"Water: {'ON' if show_water else 'OFF'}", 12, HEIGHT-56)
    text(f"Wireframe: {'ON' if wireframe else 'OFF'}", 12, HEIGHT-74)
    text(f"Animate: {'ON' if animate else 'OFF'}", 12, HEIGHT-92)

    # Legend
    legend = [
        ("Snow",        (0.95, 0.97, 1.0)),
        ("Rock",        (0.65, 0.58, 0.52)),
        ("Forest",      (0.22, 0.35, 0.12)),
        ("Grass",       (0.25, 0.52, 0.18)),
        ("Sand",        (0.82, 0.75, 0.50)),
        ("Water",       (0.15, 0.38, 0.72)),
    ]
    lx, ly = 12, 130
    text("Biomes:", lx, ly, (1,1,1))
    for i, (name, col) in enumerate(legend):
        glColor3f(*col)
        glBegin(GL_QUADS)
        glVertex2f(lx,      ly - 16 - i*16)
        glVertex2f(lx + 12, ly - 16 - i*16)
        glVertex2f(lx + 12, ly - 4  - i*16)
        glVertex2f(lx,      ly - 4  - i*16)
        glEnd()
        text(name, lx + 16, ly - 15 - i*16, (0.85, 0.85, 0.85))

    # Controls
    controls = [
        "N         : New random terrain",
        "0-9       : Preset seed",
        "W         : Toggle wireframe",
        "Q         : Toggle water",
        "A         : Animate water",
        "G         : Grid overlay",
        "RIGHT-DRAG: Rotate camera",
        "SCROLL    : Zoom",
        "R         : Reset camera",
        "ESC / X   : Quit",
    ]
    for i, line in enumerate(controls):
        text(line, WIDTH - 230, HEIGHT - 20 - i * 16, (0.75, 0.75, 0.75))

    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)

# ─────────────────────────────────────────
#  GLUT CALLBACKS
# ─────────────────────────────────────────
def display():
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    draw_sky()

    glLoadIdentity()
    eye_dist = 14.0 / zoom
    eye_x = eye_dist * math.sin(math.radians(angle_y)) * math.cos(math.radians(angle_x))
    eye_y = eye_dist * math.sin(math.radians(angle_x))
    eye_z = eye_dist * math.cos(math.radians(angle_y)) * math.cos(math.radians(angle_x))
    gluLookAt(eye_x, eye_y, eye_z,  0, HEIGHT_SCALE*0.4, 0,  0, 1, 0)

    glLightfv(GL_LIGHT0, GL_POSITION, [8, 20, 10, 1])

    draw_terrain()
    draw_grid_overlay()
    draw_water()
    draw_hud()

    glutSwapBuffers()


def update(v):
    global anim_offset
    if animate:
        anim_offset += 0.04
        glutPostRedisplay()
    glutTimerFunc(30, update, 0)


def reshape(w, h):
    global WIDTH, HEIGHT
    WIDTH, HEIGHT = w, max(h, 1)
    glViewport(0, 0, w, h)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(50, w / h, 0.1, 300)
    glMatrixMode(GL_MODELVIEW)


def mouse_btn(btn, state, x, y):
    global cam_drag, last_mx, last_my, zoom
    if btn == GLUT_RIGHT_BUTTON:
        cam_drag = (state == GLUT_DOWN)
        last_mx, last_my = x, y
    if btn == 3:
        zoom = min(zoom * 1.1, 10.0); glutPostRedisplay()
    if btn == 4:
        zoom = max(zoom / 1.1, 0.1);  glutPostRedisplay()


def motion(x, y):
    global angle_x, angle_y, last_mx, last_my
    if cam_drag:
        angle_y += (x - last_mx) * 0.4
        angle_x += (y - last_my) * 0.4
        angle_x = max(-89, min(89, angle_x))
        last_mx, last_my = x, y
        glutPostRedisplay()


def keyboard(key, x, y):
    global wireframe, show_water, show_snow, show_grid, animate
    global angle_x, angle_y, zoom, seed

    k = key.decode("utf-8").lower()

    if k == 'n':
        generate_terrain(random.randint(0, 99999))
        glutPostRedisplay()
    elif k.isdigit():
        presets = [42, 137, 256, 512, 1024, 7, 999, 31415, 2718, 8888]
        generate_terrain(presets[int(k)])
        glutPostRedisplay()
    elif k == 'w':
        wireframe = not wireframe
        glutPostRedisplay()
    elif k == 'q':
        show_water = not show_water
        glutPostRedisplay()
    elif k == 'a':
        animate = not animate
        if animate:
            glutTimerFunc(30, update, 0)
        glutPostRedisplay()
    elif k == 'g':
        show_grid = not show_grid
        glutPostRedisplay()
    elif k == 'r':
        angle_x, angle_y, zoom = 35.0, -30.0, 1.0
        glutPostRedisplay()
    elif k == 'z':
        zoom = min(zoom * 1.2, 10.0); glutPostRedisplay()
    elif k == 'x':
        import sys; sys.exit(0)
    elif key == b'\x1b':
        import sys; sys.exit(0)


def print_help():
    print("=" * 52)
    print("  🏔  3D Terrain Generator — Python OpenGL")
    print("=" * 52)
    print("  N           : New random terrain")
    print("  0-9         : Load preset seed terrain")
    print("  W           : Toggle wireframe")
    print("  Q           : Toggle water")
    print("  A           : Animate water waves")
    print("  G           : Grid overlay")
    print("  RIGHT-DRAG  : Rotate camera")
    print("  SCROLL / Z  : Zoom")
    print("  R           : Reset camera")
    print("  ESC / X     : Quit")
    print("=" * 52)
    print("  Biomes: Snow | Rock | Forest | Grass | Sand | Water")
    print("=" * 52)


def init():
    glClearColor(0.42, 0.65, 0.95, 1.0)
    glEnable(GL_DEPTH_TEST)
    glShadeModel(GL_SMOOTH)

    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.30, 0.30, 0.32, 1])
    glLightfv(GL_LIGHT0, GL_DIFFUSE,  [1.00, 0.97, 0.90, 1])
    glLightfv(GL_LIGHT0, GL_SPECULAR, [0.30, 0.30, 0.30, 1])

    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)


def main():
    print_help()
    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(WIDTH, HEIGHT)
    glutCreateWindow(b"3D Terrain Generator - Python OpenGL")

    init()
    generate_terrain(seed)

    glutDisplayFunc(display)
    glutReshapeFunc(reshape)
    glutMouseFunc(mouse_btn)
    glutMotionFunc(motion)
    glutKeyboardFunc(keyboard)
    glutTimerFunc(30, update, 0)

    glutMainLoop()


main()