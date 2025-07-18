import cv2


def count_frames_hevc(video_path):
    # Открываем видеофайл
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("Ошибка: Не удалось открыть видеофайл!")
        return -1

    # Получаем общее количество кадров (метод 1: CAP_PROP_FRAME_COUNT)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Если OpenCV не смог определить количество кадров (например, для HEVC), пересчитываем вручную
    if total_frames <= 0:
        print("OpenCV не смог определить количество кадров автоматически. Пересчёт вручную...")
        total_frames = 0
        while True:
            ret, _ = cap.read()
            if not ret:
                break
            total_frames += 1

    cap.release()
    return total_frames


# Укажите путь к вашему видеофайлу
video_path = r"C:\Users\Ruslana\Desktop\UAVS\MP4\DJI_20250610152750_0001_D.MP4"
frame_count = count_frames_hevc(video_path)

if frame_count >= 0:
    print(f"Количество кадров в видео: {frame_count}")
else:
    print("Не удалось определить количество кадров.")