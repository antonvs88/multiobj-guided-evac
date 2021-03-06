import os
import numpy as np
import random

from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point
from shapely.ops import polygonize, cascaded_union

from scipy.spatial.qhull import Delaunay
from crowddynamics.core.distance import distance_circle_line

from crowddynamics.simulation.agents import Agents, AgentGroup, Circular
from crowddynamics.core.geometry import geom_to_linear_obstacles
from crowddynamics.core.sampling import triangle_area_cumsum, random_sample_triangle
from crowddynamics.core.vector2D import length
from crowddynamics.core.distance import distance_circle_line, distance_circles

from complex_variance import ComplexFloor, ComplexFloorField


# Import Finlandia Hall floor field
field = ComplexFloorField()

# Import obstacles
obstacles = field.obstacles

# Minimal radius of a leader
max_r = 0.27

# Number of guides
n_guides = 4

# Number of times spawned leaders are allowed to overlap each other before the program is
# terminated.
#overlaps = n_guides * 20
overlaps = 10000

# Bound box representing the room. Used later in making Voronoi tessalation.
width = 90
height = 90
boundbox = Polygon([(0, 0), (0, height), (width, height), (width, 0)])

# Create a grid structure over the room geometry.
# Cell size in the grid, determines the resolution of the micro-macro converted data
cell_size = 2
m = np.round(width / cell_size)
n = np.round(height / cell_size)
m = m.astype(int)
n = n.astype(int)
X = np.linspace(0, width, m + 1)
Y = np.linspace(0, height, n + 1)
hlines = [((x1, yi), (x2, yi)) for x1, x2 in zip(X[:-1], X[1:]) for yi in Y]
vlines = [((xi, y1), (xi, y2)) for y1, y2 in zip(Y[:-1], Y[1:]) for xi in X]
grids = list(polygonize(MultiLineString(hlines + vlines)))

# Number of cells
n_cells = len(grids)

# Load followers positions and radius
agents = np.load('spawn_complex.npy')
positions = agents['position']
radii = agents['radius']

# Guides' spawn areas (shapely polygons)
guide_spawns = []

# Leader's spawn points
spawn_points = []

# Guides' spawn areas (cell numbers) (that intersect with the hexagon)
cells = []

# Check which cells intersect with the hexagon
for i in range(n_cells):
    cell = i

    poly = field.domain.intersection(grids[cell])
    if isinstance(poly, Polygon):
        guide_spawns.append(poly)
        cells.append(cell)

feasible_cells = []

# Loop through all the feasible cells and check if 10 guides can be positioned to them.
for i in range(len(guide_spawns)):
    seed = 0
    spawn_points = []
    # guide counter that checks if all guides are spawned in the cell
    guide_counter = 0
    for j in range(n_guides):
         n_spawnpoints = len(spawn_points)
         geom = guide_spawns[i] - obstacles.buffer(max_r)
         k = 0  # set overlaps counter to zero (the total number of overlaps, when positioning all guides)
         if isinstance(geom, MultiPolygon):
             n_polygons = len(geom)
             for l in range(n_polygons):
                 vertices = np.asarray(geom[l].convex_hull.exterior)
                 delaunay = Delaunay(vertices)
                 mesh = vertices[delaunay.simplices]
                 if l == 0:
                     meshes = mesh
                 else:
                     meshes = np.concatenate((mesh, meshes), axis=0)
             # Computes cumulative sum of the areas of the triangle mesh.
             weights = triangle_area_cumsum(meshes)
             weights /= weights[-1]

             while k < overlaps:
                 seed += 1
                 distances = []  # temporarily store distances from the spawned point to the previously spawned
                 # During a single spawn, the number of times the guide overlaps with an obstacle/guide
                 n_overlaps = 0
                 # Spawn a random point for the guide.
                 x = np.random.random(seed)
                 rand_triangle = np.searchsorted(weights, x)
                 a, b, c = meshes[rand_triangle]
                 spawn_point = random_sample_triangle(a, b, c)
                 #print(spawn_point)
                 if n_spawnpoints != 0:  # if there are no other spawned guides skip this step
                     for l in range(0, n_spawnpoints):
                         d = length(spawn_point - spawn_points[l])
                         h = d - 2 * max_r
                         distances.append(h)
                     distances_array = distances
                     distances_array = np.asarray(distances_array)
                     n_overlaps += len(np.where(distances_array < 0)[0])
                 for obstacle in obstacles:
                     obstacle = list(obstacle.coords)
                     n_obstacle_points = len(obstacle)
                     for l in range(0, n_obstacle_points):
                         if l == n_obstacle_points - 1:
                             h, _ = distance_circle_line(spawn_point, max_r, np.asarray(obstacle[l]),
                                                         np.asarray(obstacle[0]))
                         else:
                             h, _ = distance_circle_line(spawn_point, max_r, np.asarray(obstacle[l]),
                                                         np.asarray(obstacle[l + 1]))
                         if h < 0.0:
                             n_overlaps += 1

                 for agent in range(len(radii)):
                     #print(positions[agent])
                     #print(radii[agent])
                     #print(spawn_point)
                     #print(max_r)
                     h, _ = distance_circles(positions[agent], radii[agent], spawn_point, max_r)
                     if h < 0.0:
                         n_overlaps += 1

                 if n_overlaps == 0:
                     # Append the point to spawn points
                     #print("{}{}{}".format('Leader number ', j+1, ' fits in the cell'))
                     spawn_points.append([spawn_point[0], spawn_point[1]])
                     guide_counter += 1
                     if guide_counter == n_guides:
                         feasible_cells.append(cells[i])
                     break
                 k += 1
                 if k == overlaps:
                     #print("{}{}{}".format('Leader number ', j+1, ' does not fit in the cell'))
                     break
         else:
             #print(geom)
             #print(np.asarray(geom.convex_hull.exterior))
             vertices = np.asarray(geom.convex_hull.exterior)
             delaunay = Delaunay(vertices)
             #print(delaunay)
             mesh = vertices[delaunay.simplices]
             #print(mesh)
             weights = triangle_area_cumsum(mesh)
             #print(weights)
             weights /= weights[-1]
             #print(weights)

             while k < overlaps:
                 seed += 1
                 distances = []  # temporarily store distances from the spawned point to the previously spawned
                 n_overlaps = 0  # for each attempt to position the guide, set number of overlaps to zero
                 # Spawn a random point for the guide
                 x = np.random.random(seed)
                 #print(x)
                 rand_triangle = np.searchsorted(weights, x)[0]
                 #print(rand_triangle)
                 #print(mesh[rand_triangle])
                 #mesh_rand_triangle = mesh[rand_triangle]
                 #print(mesh_rand_triangle[0])
                 #print(mesh_rand_triangle[1])
                 #print(mesh_rand_triangle[2])
                 a, b, c = mesh[rand_triangle]
                 spawn_point = random_sample_triangle(a, b, c)
                 #print(spawn_point)
                 if n_spawnpoints != 0:
                     for l in range(0, n_spawnpoints):
                         d = length(spawn_point - spawn_points[l])
                         h = d - 2 * max_r
                         distances.append(h)
                     distances_array = distances
                     distances_array = np.asarray(distances_array)
                     n_overlaps += len(np.where(distances_array < 0)[0])
                 for obstacle in obstacles:
                     obstacle = list(obstacle.coords)
                     n_obstacle_points = len(obstacle)
                     for l in range(0, n_obstacle_points):
                         if l == n_obstacle_points - 1:
                             h, _ = distance_circle_line(spawn_point, max_r, np.asarray(obstacle[l]),
                                                         np.asarray(obstacle[0]))
                         else:
                             h, _ = distance_circle_line(spawn_point, max_r, np.asarray(obstacle[l]),
                                                         np.asarray(obstacle[l + 1]))
                         if h < 0.0:
                             n_overlaps += 1

                 for agent in range(len(radii)):
                     #print(positions[agent])
                     #print(radii[agent])
                     #print(spawn_point)
                     #print(max_r)
                     h, _ = distance_circles(positions[agent], radii[agent], spawn_point, max_r)
                     if h < 0.0:
                         n_overlaps += 1

                 if n_overlaps == 0:
                     # Append the point to spawn points
                     #print("{}{}{}".format('Leader number ', j+1, ' fits in the cell'))
                     spawn_points.append([spawn_point[0], spawn_point[1]])
                     guide_counter += 1
                     if guide_counter == n_guides:
                         feasible_cells.append(cells[i])
                     break
                 k += 1
                 if k == overlaps:
                     #print("{}{}{}".format('Leader number ', j+1, ' does not fit in the cell'))
                     break

# Save the feasible cells
print(feasible_cells)
np.save("feasible_cells_complex.npy", feasible_cells)