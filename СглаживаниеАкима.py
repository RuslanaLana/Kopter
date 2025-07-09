import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import Akima1DInterpolator

# Заданные точки (могут быть петлей)
points = np.array([
    [0, 0],
    [1, 2],
    [2, 1],
    [3, 3],
    [2, 4],
    [1, 3],
    [0, 5],
    [-2, 4],
    [-1, 2]
])

# Параметризация (по кумулятивному расстоянию)
def get_cumulative_distance(points):
    diff = np.diff(points, axis=0)
    dist = np.sqrt((diff ** 2).sum(axis=1))
    return np.insert(np.cumsum(dist), 0, 0)

t = get_cumulative_distance(points)

# Интерполяция Akima
akima_x = Akima1DInterpolator(t, points[:, 0])
akima_y = Akima1DInterpolator(t, points[:, 1])

# Сглаженная траектория
t_smooth = np.linspace(t.min(), t.max(), 500)
x_smooth = akima_x(t_smooth)
y_smooth = akima_y(t_smooth)

# График
plt.figure(figsize=(10, 6))
plt.plot(points[:, 0], points[:, 1], 'ro', label='Исходные точки')
plt.plot(x_smooth, y_smooth, 'b-', label='Сглаженная траектория (Akima)')
plt.axis('equal')
plt.legend()
plt.grid(True)
plt.title("Точная гладкая интерполяция через точки")
plt.show()