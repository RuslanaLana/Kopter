from flask import Flask, Response, render_template
from MvCameraControl_class import *
import cv2
import numpy as np
from ctypes import *
import sys
import time
import threading

app = Flask(__name__)

# Коды ошибок
MV_E_NO_DATA = -2147483644  # 0x80000004: Нет данных
MV_OK = 0  # Успешное выполнение

# Глобальные переменные для управления камерой
camera = None
camera_thread = None
streaming = False
frame = None
lock = threading.Lock()


class CameraThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop_event = threading.Event()

    def run(self):
        global camera, frame, streaming

        # Инициализация камеры
        device_list = MV_CC_DEVICE_INFO_LIST()
        ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE, device_list)
        if ret != MV_OK or device_list.nDeviceNum == 0:
            print("Камера не найдена!")
            return

        # Создаем объект камеры
        cam = MvCamera()
        device_info = MV_CC_DEVICE_INFO()
        pointer_device_info = pointer(device_info)
        memmove(pointer_device_info, device_list.pDeviceInfo[0], sizeof(device_info))

        # Создаем дескриптор камеры
        handle = c_void_p()
        ret = MvCamCtrldll.MV_CC_CreateHandle(byref(handle), byref(device_info))
        if ret != MV_OK:
            print(f"Ошибка создания дескриптора. Код: {ret}")
            return

        cam.handle = handle

        # Открываем устройство
        ret = cam.MV_CC_OpenDevice()
        if ret != MV_OK:
            print(f"Ошибка подключения. Код: {ret}")
            return

        # Настройка параметров
        ret = cam.MV_CC_SetEnumValue("PixelFormat", PixelType_Gvsp_Mono8)
        ret = cam.MV_CC_SetEnumValue("ExposureAuto", MV_EXPOSURE_AUTO_MODE_CONTINUOUS)
        ret = cam.MV_CC_SetFloatValue("TargetBrightness", 60.0)
        ret = cam.MV_CC_SetFloatValue("ExposureTimeMax", 50000.0)
        ret = cam.MV_CC_SetFloatValue("ExposureTimeMin", 50.0)
        ret = cam.MV_CC_SetEnumValue("GainAuto", MV_GAIN_MODE_CONTINUOUS)
        ret = cam.MV_CC_SetFloatValue("GainMax", 12.0)

        # Запуск захвата
        ret = cam.MV_CC_StartGrabbing()
        if ret != MV_OK:
            print(f"Ошибка старта захвата. Код: {ret}")
            return

        camera = cam
        streaming = True

        try:
            while not self.stop_event.is_set():
                # Получение кадра
                stFrame = MV_FRAME_OUT()
                memset(byref(stFrame), 0, sizeof(stFrame))

                ret = cam.MV_CC_GetImageBuffer(stFrame, 1000)
                if ret != MV_OK:
                    if ret == MV_E_NO_DATA:
                        continue
                    print(f"Ошибка получения кадра. Код: {ret}")
                    continue

                if not stFrame.pBufAddr:
                    continue

                # Преобразование в numpy массив
                buffer = (c_ubyte * stFrame.stFrameInfo.nFrameLen).from_buffer_copy(
                    string_at(stFrame.pBufAddr, stFrame.stFrameInfo.nFrameLen))
                img_np = np.frombuffer(buffer, dtype=np.uint8)
                img_np = img_np.reshape((stFrame.stFrameInfo.nHeight, stFrame.stFrameInfo.nWidth))

                # Оптимизация изображения
                current_mean = np.mean(img_np)
                if current_mean < 30:
                    img_np = cv2.equalizeHist(img_np)
                elif current_mean > 200:
                    img_np = cv2.convertScaleAbs(img_np, alpha=0.7, beta=0)
                else:
                    img_np = cv2.convertScaleAbs(img_np, alpha=1.2, beta=10)

                # Кодирование в JPEG
                ret, jpeg = cv2.imencode('.jpg', img_np)
                if ret:
                    with lock:
                        frame = jpeg.tobytes()

                # Освобождаем буфер
                cam.MV_CC_FreeImageBuffer(stFrame)

        finally:
            # Остановка камеры
            print("Остановка камеры...")
            cam.MV_CC_StopGrabbing()
            cam.MV_CC_CloseDevice()
            if hasattr(cam, 'handle'):
                MvCamCtrldll.MV_CC_DestroyHandle(cam.handle)
            streaming = False
            camera = None


def generate_frames():
    global frame
    while True:
        with lock:
            if frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                time.sleep(0.1)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/start_stream')
def start_stream():
    global camera_thread
    if not streaming and (camera_thread is None or not camera_thread.is_alive()):
        camera_thread = CameraThread()
        camera_thread.daemon = True
        camera_thread.start()
        return {'status': 'started'}
    return {'status': 'already running'}


@app.route('/stop_stream')
def stop_stream():
    global camera_thread, streaming
    if streaming and camera_thread is not None and camera_thread.is_alive():
        camera_thread.stop_event.set()
        camera_thread.join()
        streaming = False
        return {'status': 'stopped'}
    return {'status': 'not running'}


@app.route('/stream_status')
def stream_status():
    return {'streaming': streaming}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)