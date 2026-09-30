import cv2

def extract_frames(video_path, scenes):

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)

    frames = []

    for scene in scenes:

        start = scene[0]
        frame_number = int(start.get_seconds() * fps)

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

        ret, frame = cap.read()

        if ret:
            frames.append(frame)

    cap.release()

    return frames