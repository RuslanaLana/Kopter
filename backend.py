# Импорт необходимых библиотек
import math
import threading
import time

from flask import Flask, request, jsonify, make_response, Response, render_template, send_from_directory
from flask_cors import CORS
import gpxpy
import gpxpy.gpx
import numpy as np
from scipy.interpolate import Akima1DInterpolator
import re
from typing import List
from werkzeug.exceptions import HTTPException
from MvCameraControl_class import *
import cv2
from ctypes import *# Коды ошибок
from scipy.ndimage import gaussian_filter1d

MV_E_NO_DATA = -2147483644  # 0x80000004: Нет данных
MV_OK = 0  # Успешное выполнение

# Создание экземпляра Flask приложения
app = Flask(__name__)
CORS(app)

from pydantic import BaseModel

camera_lock = threading.Lock()
camera_instance = None
camera_active = False
STOP_EVENT = threading.Event()
CAMERA_LOCK = threading.Lock()
CAMERA_INSTANCE = None
STREAM_ACTIVE = False

SRT_FILENAME = None  # Будет хранить имя файла без расширения

# Глобальные переменные для управления экспозицией
TARGET_BRIGHTNESS = 60.0           # Целевая яркость (0-255)
INITIAL_EXPOSURE = 30000.0         # Стартовая экспозиция (высокая для темноты)
MIN_EXPOSURE = 20000.0             # Минимальная экспозиция (не даём опускаться ниже уровня для темноты)
MAX_EXPOSURE = 100000.0            # Максимальная экспозиция
SMOOTHING_FACTOR_UP = 0.05         # Плавность при увеличении экспозиции (для темноты)
SMOOTHING_FACTOR_DOWN = 0.01       # Плавность при уменьшении (для света, очень медленно)

# Глобальные переменные
current_exposure = INITIAL_EXPOSURE

class Point(BaseModel):
    lat: float
    lng: float
    alt: float = 100
    type: str = "point"
    metadata: dict = None  # Добавляем поле для метаданных

class RouteRequest(BaseModel):
    points: List[Point]
    smooth: bool = True

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

def init_camera():
    global camera_instance, camera_active

    with camera_lock:
        if camera_instance is not None:
            return camera_instance

        try:
            # 1. Поиск устройств
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE, device_list)
            if ret != MV_OK or device_list.nDeviceNum == 0:
                raise RuntimeError("No cameras found")

            # 2. Создание объекта камеры
            cam = MvCamera()
            device_info = MV_CC_DEVICE_INFO()
            pointer_device_info = pointer(device_info)
            memmove(pointer_device_info, device_list.pDeviceInfo[0], sizeof(device_info))

            # 3. Создание дескриптора
            handle = c_void_p()
            ret = MvCamCtrldll.MV_CC_CreateHandle(byref(handle), byref(device_info))
            if ret != MV_OK:
                raise RuntimeError("Failed to create camera handle")

            cam.handle = handle

            # 4. Подключение к камере
            ret = cam.MV_CC_OpenDevice()
            if ret != MV_OK:
                raise RuntimeError("Failed to open camera")

            # 5. Настройка параметров
            cam.MV_CC_SetEnumValue("PixelFormat", PixelType_Gvsp_Mono8)
            cam.MV_CC_SetEnumValue("ExposureAuto", MV_EXPOSURE_AUTO_MODE_CONTINUOUS)
            cam.MV_CC_SetFloatValue("TargetBrightness", 60.0)

            # 6. Запуск захвата
            ret = cam.MV_CC_StartGrabbing()
            if ret != MV_OK:
                raise RuntimeError("Failed to start grabbing")

            camera_instance = cam
            camera_active = True
            return cam

        except Exception as e:
            close_camera()
            raise e


def close_camera():
    global camera_instance, camera_active

    with camera_lock:
        if camera_instance is not None:
            try:
                if camera_active:
                    camera_instance.MV_CC_StopGrabbing()
                if hasattr(camera_instance, 'handle'):
                    camera_instance.MV_CC_CloseDevice()
                    MvCamCtrldll.MV_CC_DestroyHandle(camera_instance.handle)
            except Exception as e:
                print(f"Error closing camera: {str(e)}")
            finally:
                camera_instance = None
                camera_active = False

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
    global SRT_FILENAME
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No selected file"}), 400

        if not file.filename.lower().endswith('.srt'):
            return jsonify({"status": "error", "message": "Only .srt files are allowed"}), 400

        # Сохраняем имя файла без расширения
        SRT_FILENAME = file.filename.rsplit('.', 1)[0]  # Удаляем расширение .srt

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

@app.route('/video_feed_sync')
def video_feed_sync():
    global SRT_FILENAME, route_points

    if not SRT_FILENAME:
        return "No SRT file selected", 404

    video_filename = f"{SRT_FILENAME}_avc.mp4"
    video_path = f"static/{video_filename}"

    def generate():
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Failed to open video file: {video_path}")
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_delay = 1 / fps if fps > 0 else 1/30  # default to 30fps if fps is 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            _, jpeg = cv2.imencode('.jpg', frame)
            frame_data = jpeg.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')

            time.sleep(frame_delay)  # Точная синхронизация по FPS

        cap.release()

    return Response(generate(),
                   mimetype='multipart/x-mixed-replace; boundary=frame',
                   headers={'Cache-Control': 'no-cache'})

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

@app.route('/video_feed')
def video_feed():
    def generate():
        global STREAM_ACTIVE
        with CAMERA_LOCK:
            cam = CAMERA_INSTANCE
            if not cam:
                return

            STREAM_ACTIVE = True
            try:
                while STREAM_ACTIVE:
                    stFrame = MV_FRAME_OUT()
                    memset(byref(stFrame), 0, sizeof(stFrame))

                    ret = cam.MV_CC_GetImageBuffer(stFrame, 1000)
                    if ret == MV_E_NO_DATA:
                        continue
                    elif ret != MV_OK:
                        break

                    # Обработка кадра
                    buffer = (c_ubyte * stFrame.stFrameInfo.nFrameLen).from_buffer_copy(
                        string_at(stFrame.pBufAddr, stFrame.stFrameInfo.nFrameLen))
                    img_np = np.frombuffer(buffer, dtype=np.uint8)
                    img_np = img_np.reshape((stFrame.stFrameInfo.nHeight, stFrame.stFrameInfo.nWidth))

                    # Оптимизация и кодирование
                    img_color = optimize_image(img_np)
                    _, jpeg = cv2.imencode('.jpg', img_color)
                    frame = jpeg.tobytes()

                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

                    cam.MV_CC_FreeImageBuffer(stFrame)
            finally:
                STREAM_ACTIVE = False

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/camera_status')
def camera_status():
    return jsonify({
        "active": STREAM_ACTIVE,
        "camera_initialized": CAMERA_INSTANCE is not None
    })

@app.route('/start_camera')
def start_camera():
    global CAMERA_INSTANCE
    with CAMERA_LOCK:
        if CAMERA_INSTANCE is None:
            try:
                CAMERA_INSTANCE = init_camera()
                return jsonify({"status": "success"})
            except Exception as e:
                CAMERA_INSTANCE = None
                return jsonify({"status": "error", "message": str(e)}), 500
        return jsonify({"status": "success"})

@app.route('/stop_camera')
def stop_camera():
    global CAMERA_INSTANCE, STREAM_ACTIVE
    with CAMERA_LOCK:
        STREAM_ACTIVE = False
        if CAMERA_INSTANCE:
            close_camera()
            CAMERA_INSTANCE = None
    return jsonify({"status": "success"})

def generate_frames():
    cam = init_camera()
    cam.MV_CC_SetEnumValue("ExposureAuto", MV_EXPOSURE_AUTO_MODE_OFF)  # Отключаем автоэкспозицию!
    cam.MV_CC_SetFloatValue("ExposureTime", INITIAL_EXPOSURE)

    try:
        while not STOP_EVENT.is_set():
            stFrame = MV_FRAME_OUT()
            memset(byref(stFrame), 0, sizeof(stFrame))

            ret = cam.MV_CC_GetImageBuffer(stFrame, 1000)
            if ret != MV_OK:
                continue

            # Декодируем кадр
            buffer = (c_ubyte * stFrame.stFrameInfo.nFrameLen).from_buffer_copy(
                string_at(stFrame.pBufAddr, stFrame.stFrameInfo.nFrameLen))
            img_np = np.frombuffer(buffer, dtype=np.uint8)
            img_np = img_np.reshape((stFrame.stFrameInfo.nHeight, stFrame.stFrameInfo.nWidth))

            # Оптимизируем яркость
            img_processed = optimize_image(img_np)

            # Обновляем экспозицию камеры
            cam.MV_CC_SetFloatValue("ExposureTime", current_exposure)

            # Кодируем в JPEG и отправляем
            _, jpeg = cv2.imencode('.jpg', img_processed)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

            cam.MV_CC_FreeImageBuffer(stFrame)
    finally:
        cam.MV_CC_StopGrabbing()

def optimize_image(img):
    global current_exposure
    current_brightness = np.mean(img)
    error = TARGET_BRIGHTNESS - current_brightness

    # Асимметричная регулировка:
    # - Медленно уменьшаем экспозицию при светлых кадрах (SMOOTHING_FACTOR_DOWN)
    # - Быстрее увеличиваем при тёмных (SMOOTHING_FACTOR_UP)
    smoothing_factor = SMOOTHING_FACTOR_DOWN if error < 0 else SMOOTHING_FACTOR_UP
    exposure_adjustment = error * smoothing_factor * 100

    # Запрещаем экспозиции опускаться ниже MIN_EXPOSURE
    new_exposure = max(MIN_EXPOSURE, current_exposure + exposure_adjustment)
    new_exposure = min(new_exposure, MAX_EXPOSURE)

    # Применяем новую экспозицию
    current_exposure = new_exposure

    # Лёгкая программная коррекция (без пересветов)
    gain = 1.0 + (error / 255.0) * 0.2  # Очень мягкое усиление
    img_corrected = cv2.convertScaleAbs(img, alpha=gain, beta=0)

    # Для тёмных кадров — гистограммное выравнивание
    if current_brightness < 30:
        img_corrected = cv2.equalizeHist(img_corrected)

    return cv2.cvtColor(img_corrected, cv2.COLOR_GRAY2BGR)

# Запуск сервера
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)