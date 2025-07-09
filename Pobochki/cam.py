from MvCameraControl_class import *
import cv2
import numpy as np
from ctypes import *
import sys
import time

# Коды ошибок
MV_E_NO_DATA = -2147483644  # 0x80000004: Нет данных
MV_OK = 0  # Успешное выполнение


def main():
    # 1. Инициализация списка устройств
    device_list = MV_CC_DEVICE_INFO_LIST()
    ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE, device_list)
    if ret != MV_OK:
        print(f"Ошибка поиска камер. Код: {ret}")
        return

    if device_list.nDeviceNum == 0:
        print("Камеры не найдены!")
        return

    # 2. Создаем объект камеры
    cam = MvCamera()

    # 3. Получаем информацию об устройстве
    device_info = MV_CC_DEVICE_INFO()
    pointer_device_info = pointer(device_info)
    memmove(pointer_device_info, device_list.pDeviceInfo[0], sizeof(device_info))

    # 4. Создаем дескриптор камеры
    handle = c_void_p()
    ret = MvCamCtrldll.MV_CC_CreateHandle(byref(handle), byref(device_info))
    if ret != MV_OK:
        print(f"Ошибка создания дескриптора. Код: {ret}")
        return

    # Присваиваем handle нашему объекту камеры
    cam.handle = handle

    # 5. Открываем устройство
    ret = cam.MV_CC_OpenDevice()
    if ret != MV_OK:
        print(f"Ошибка подключения. Код: {ret}")
        return

    # 6. Настройка параметров для ЧБ камеры
    print("Настройка параметров камеры...")

    # Установка формата пикселей (Mono8)
    ret = cam.MV_CC_SetEnumValue("PixelFormat", PixelType_Gvsp_Mono8)
    if ret != MV_OK:
        print(f"Ошибка настройки формата. Код: {ret}")

    # Включение автоматической экспозиции
    ret = cam.MV_CC_SetEnumValue("ExposureAuto", MV_EXPOSURE_AUTO_MODE_CONTINUOUS)
    if ret != MV_OK:
        print(f"Ошибка настройки автоэкспозиции. Код: {ret}")

    # Установка целевой яркости (рекомендуется 50-70 для ЧБ камер)
    ret = cam.MV_CC_SetFloatValue("TargetBrightness", 60.0)
    if ret != MV_OK:
        print(f"Ошибка настройки яркости. Код: {ret}")

    # Максимальная выдержка (в микросекундах)
    ret = cam.MV_CC_SetFloatValue("ExposureTimeMax", 50000.0)
    if ret != MV_OK:
        print(f"Ошибка настройки экспозиции. Код: {ret}")

    # Минимальная выдержка
    ret = cam.MV_CC_SetFloatValue("ExposureTimeMin", 50.0)
    if ret != MV_OK:
        print(f"Ошибка настройки экспозиции. Код: {ret}")

    # Включение автоматического усиления
    ret = cam.MV_CC_SetEnumValue("GainAuto", MV_GAIN_MODE_CONTINUOUS)
    if ret != MV_OK:
        print(f"Ошибка настройки автоусиления. Код: {ret}")

    # Максимальное усиление (dB)
    ret = cam.MV_CC_SetFloatValue("GainMax", 12.0)
    if ret != MV_OK:
        print(f"Ошибка настройки усиления. Код: {ret}")

    # 7. Запуск захвата
    ret = cam.MV_CC_StartGrabbing()
    if ret != MV_OK:
        print(f"Ошибка старта захвата. Код: {ret}")
        return

    try:
        frame_count = 0
        start_time = time.time()

        while True:
            # 8. Получение кадра
            stFrame = MV_FRAME_OUT()
            memset(byref(stFrame), 0, sizeof(stFrame))

            ret = cam.MV_CC_GetImageBuffer(stFrame, 1000)
            if ret != MV_OK:
                if ret == MV_E_NO_DATA:
                    continue
                print(f"Ошибка получения кадра. Код: {ret}")
                continue

            # 9. Создаем numpy массив для ЧБ изображения
            if not stFrame.pBufAddr:
                print("Ошибка: пустой указатель на буфер")
                continue

            buffer = (c_ubyte * stFrame.stFrameInfo.nFrameLen).from_buffer_copy(
                string_at(stFrame.pBufAddr, stFrame.stFrameInfo.nFrameLen))
            img_np = np.frombuffer(buffer, dtype=np.uint8)
            img_np = img_np.reshape((stFrame.stFrameInfo.nHeight, stFrame.stFrameInfo.nWidth))

            # 10. Оптимизация яркости ЧБ изображения
            current_mean = np.mean(img_np)

            # Автоматическая коррекция контраста
            if current_mean < 30:  # Если изображение слишком темное
                # Автоматическое выравнивание гистограммы
                img_np = cv2.equalizeHist(img_np)
            elif current_mean > 200:  # Если изображение переэкспонировано
                # Уменьшение яркости
                img_np = cv2.convertScaleAbs(img_np, alpha=0.7, beta=0)
            else:
                # Легкое повышение контраста
                img_np = cv2.convertScaleAbs(img_np, alpha=1.2, beta=10)

            # 11. Отображение информации о кадре
            frame_count += 1
            if frame_count % 10 == 0:
                fps = frame_count / (time.time() - start_time)
                print(f"FPS: {fps:.1f} | Brightness: {current_mean:.1f}")
                frame_count = 0
                start_time = time.time()

            # 12. Отображение изображения
            cv2.putText(img_np, f"Brightness: {current_mean:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow("Hikrobot Mono Camera", img_np)

            # 13. Освобождаем буфер
            cam.MV_CC_FreeImageBuffer(stFrame)

            # Выход по нажатию 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        # 14. Остановка
        print("Остановка камеры...")
        cam.MV_CC_StopGrabbing()
        cam.MV_CC_CloseDevice()
        if hasattr(cam, 'handle'):
            MvCamCtrldll.MV_CC_DestroyHandle(cam.handle)
        cv2.destroyAllWindows()
        print("Камера отключена.")


if __name__ == "__main__":
    main()