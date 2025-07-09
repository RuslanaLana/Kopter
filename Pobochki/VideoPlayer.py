import cv2
import time


class VideoPlayer:
    def __init__(self, video_path):
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        self.paused = False
        self.quit = False

        if not self.cap.isOpened():
            print("Ошибка: Не удалось открыть видео файл.")
            return

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.delay = int(1000 / self.fps) if self.fps > 0 else 30

    def run(self):
        while True:
            if not self.paused:
                ret, frame = self.cap.read()
                if not ret:
                    print("Видео закончилось или произошла ошибка чтения.")
                    break

                cv2.imshow('HEVC Video Player', frame)

            key = cv2.waitKey(self.delay) & 0xFF

            if key == ord(' '):  # Пробел для паузы/продолжения
                self.paused = not self.paused
            elif key == ord('q') or key == 27:  # 'q' или ESC для выхода
                self.quit = True
                break

        self.cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    # Укажите путь к вашему видео файлу
    video_path = r"C:\Users\Ruslana\Desktop\UAVS\MP4\DJI_20250610161607_0009_D.MP4"

    player = VideoPlayer(video_path)
    player.run()