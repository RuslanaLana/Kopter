# Импорт необходимых библиотек
import math
import warnings

from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import gpxpy
import gpxpy.gpx
import numpy as np
from scipy.interpolate import Akima1DInterpolator
import re
from typing import List
from werkzeug.exceptions import HTTPException
# Создание экземпляра Flask приложения
app = Flask(__name__)
CORS(app)

from pydantic import BaseModel

class Point(BaseModel):
    lat: float
    lng: float
    alt: float = 100
    type: str = "point"
    metadata: dict = None  # Добавляем поле для метаданных

class RouteRequest(BaseModel):
    points: List[Point]
    smooth: bool = True

# Настройка CORS (используйте flask-cors для более полной реализации)
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', '*')
    response.headers.add('Access-Control-Allow-Methods', '*')
    return response

# Вспомогательная функция для обработки ошибок
def handle_error(message, status_code):
    response = jsonify({"status": "error", "message": message})
    response.status_code = status_code
    return response

# Функция сглаживания маршрута (остается без изменений)
def smooth_route(points):
    """Сглаживание маршрута с использованием интерполяции Akima"""
    try:
        coords = np.array([[p['lng'], p['lat']] for p in points])
        alts = np.array([p['alt'] for p in points])

        def get_cumulative_distance(points):
            diff = np.diff(points, axis=0)
            dist = np.sqrt((diff ** 2).sum(axis=1))
            return np.insert(np.cumsum(dist), 0, 0)

        t = get_cumulative_distance(coords)

        akima_x = Akima1DInterpolator(t, coords[:, 0])
        akima_y = Akima1DInterpolator(t, coords[:, 1])
        akima_alt = Akima1DInterpolator(t, alts)

        t_smooth = np.linspace(t.min(), t.max(), 100)
        x_smooth = akima_x(t_smooth)
        y_smooth = akima_y(t_smooth)
        alt_smooth = akima_alt(t_smooth)

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

# Эндпоинт для импорта SRT файлов
@app.post("/api/import-srt")
def import_srt():
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No selected file"}), 400

        if not file.filename.lower().endswith('.srt'):
            return jsonify({"status": "error", "message": "Only .srt files are allowed"}), 400

        srt_content = file.read().decode('utf-8')
        points = []

        for block in srt_content.split('\n\n'):
            if not block.strip():
                continue

            lines = [line.strip() for line in block.split('\n') if line.strip()]
            if len(lines) < 2:
                continue

            coord_line = next((line for line in lines if '[latitude:' in line), None)
            if not coord_line:
                continue

            try:
                lat = float(re.search(r'latitude:\s*([\d.]+)', coord_line).group(1))
                lng = float(re.search(r'longitude:\s*([\d.]+)', coord_line).group(1))
                alt = float(re.search(r'abs_alt:\s*([\d.]+)', coord_line).group(1)) if re.search(r'abs_alt:\s*([\d.]+)', coord_line) else 100.0

                metadata = {}
                # ... (извлечение метаданных)

                points.append({
                    "lat": lat,
                    "lng": lng,
                    "alt": alt,
                    "type": "point",
                    "metadata": metadata
                })
            except Exception as e:
                continue

        if not points:
            return jsonify({"status": "error", "message": "No valid points found in SRT file"}), 400

        return jsonify({
            "status": "success",
            "points": points,
            "count": len(points)
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"SRT processing error: {str(e)}"}), 500

# Эндпоинт для экспорта в GPX формат
@app.route('/api/export-gpx', methods=['POST'])
def export_gpx():
    try:
        data = request.get_json()
        if not data or 'points' not in data:
            return handle_error("Invalid request data", 400)

        points = data['points']
        gpx = gpxpy.gpx.GPX()
        track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(track)

        segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(segment)

        for point in points:
            segment.points.append(
                gpxpy.gpx.GPXTrackPoint(
                    latitude=point['lat'],
                    longitude=point['lng'],
                    elevation=point.get('alt', 100.0)
                )
            )

        response = make_response(gpx.to_xml())
        response.headers['Content-Type'] = 'application/xml'
        response.headers['Content-Disposition'] = 'attachment; filename=route.gpx'
        return response

    except Exception as e:
        return handle_error(str(e), 500)


@app.route('/api/calculate-route', methods=['POST'])
def calculate_route():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        # Валидация данных с помощью Pydantic
        try:
            route_request = RouteRequest(**data)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Invalid data format: {str(e)}"}), 400

        if len(route_request.points) < 2:
            return jsonify({"status": "error", "message": "Need at least 2 points"}), 400

        # Проверка и сортировка точек
        start_points = [p for p in route_request.points if p.type == "start"]
        end_points = [p for p in route_request.points if p.type == "end"]
        mid_points = [p for p in route_request.points if p.type == "point"]

        if not start_points or not end_points:
            return jsonify({"status": "error", "message": "Start and end points required"}), 400

        sorted_points = start_points + mid_points + end_points

        if route_request.smooth:
            points_dict = [p.dict() for p in sorted_points]
            smoothed = smooth_route(points_dict)
            return jsonify({"status": "success", "points": smoothed})
        else:
            sharp_points = []

            for i in range(len(sorted_points) - 1):
                start = sorted_points[i]
                end = sorted_points[i + 1]

                sharp_points.append(start.dict())

                distance = calculate_geo_distance(
                    start.lat, start.lng,
                    end.lat, end.lng
                )
                num_points = max(3, min(50, int(distance * 2000)))

                for j in range(1, num_points):
                    t = j / num_points
                    alt = start.alt + (end.alt - start.alt) * t
                    sharp_points.append({
                        "lat": start.lat + (end.lat - start.lat) * t,
                        "lng": start.lng + (end.lng - start.lng) * t,
                        "alt": alt,
                        "type": "point"
                    })

            sharp_points.append(end_points[-1].dict())
            return jsonify({"status": "success", "points": sharp_points})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def calculate_geo_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points in kilometers using Haversine formula
    """
    R = 6371  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat/2) * math.sin(d_lat/2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon/2) * math.sin(d_lon/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# Обработчик ошибок
@app.errorhandler(HTTPException)
def handle_exception(e):
    return jsonify({
        "status": "error",
        "message": e.description
    }), e.code

# Запуск сервера
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)