from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import gpxpy
import gpxpy.gpx
import numpy as np
from scipy.interpolate import Akima1DInterpolator

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Point(BaseModel):
    lat: float
    lng: float
    alt: float = 100
    type: str = "point"  # Добавляем тип точки


class RouteRequest(BaseModel):
    points: List[Point]
    smooth: bool = True

def smooth_route(points):
    """Сглаживание маршрута с использованием интерполяции Akima"""
    try:
        # Преобразуем точки в массив numpy
        coords = np.array([[p.lng, p.lat] for p in points])
        alts = np.array([p.alt for p in points])

        # Параметризация по кумулятивному расстоянию
        def get_cumulative_distance(points):
            diff = np.diff(points, axis=0)
            dist = np.sqrt((diff ** 2).sum(axis=1))
            return np.insert(np.cumsum(dist), 0, 0)

        t = get_cumulative_distance(coords)

        # Интерполяция Akima для координат
        akima_x = Akima1DInterpolator(t, coords[:, 0])
        akima_y = Akima1DInterpolator(t, coords[:, 1])

        # Интерполяция для высоты (линейная, чтобы избежать колебаний)
        akima_alt = Akima1DInterpolator(t, alts)

        # Генерация сглаженной траектории
        t_smooth = np.linspace(t.min(), t.max(), 100)
        x_smooth = akima_x(t_smooth)
        y_smooth = akima_y(t_smooth)
        alt_smooth = akima_alt(t_smooth)

        # Собираем результат
        smoothed_points = []
        for i in range(len(t_smooth)):
            smoothed_points.append({
                "lat": y_smooth[i],
                "lng": x_smooth[i],
                "alt": alt_smooth[i]
            })

        return smoothed_points
    except Exception as e:
        raise ValueError(f"Smoothing error: {str(e)}")


@app.post("/api/calculate-route")
async def calculate_route(route: RouteRequest):
    try:
        if len(route.points) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 points")

        # Проверяем наличие начальной и конечной точек
        types = [p.type for p in route.points]
        if "start" not in types or "end" not in types:
            raise HTTPException(status_code=400, detail="Start and end points required")

        # Сортируем точки: start -> points -> end
        sorted_points = (
            [p for p in route.points if p.type == "start"] +
            [p for p in route.points if p.type == "point"] +
            [p for p in route.points if p.type == "end"]
        )

        if route.smooth:
            smoothed = smooth_route(sorted_points)
            return {"status": "success", "points": [
                {"lat": p["lat"], "lng": p["lng"], "alt": p["alt"]}
                for p in smoothed
            ]}

        return {"status": "success", "points": [
            {"lat": p.lat, "lng": p.lng, "alt": p.alt}
            for p in sorted_points
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/export-gpx")
async def export_gpx(route: RouteRequest):
    try:
        gpx = gpxpy.gpx.GPX()
        track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(track)

        segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(segment)

        for point in route.points:
            segment.points.append(
                gpxpy.gpx.GPXTrackPoint(
                    latitude=point.lat,
                    longitude=point.lng,
                    elevation=point.alt
                )
            )

        return {"gpx": gpx.to_xml()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)