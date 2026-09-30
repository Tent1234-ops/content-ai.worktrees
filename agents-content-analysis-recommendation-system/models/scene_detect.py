from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector

def detect_scenes(video):

    video_manager = VideoManager([video])
    scene_manager = SceneManager()

    scene_manager.add_detector(ContentDetector())

    video_manager.start()

    scene_manager.detect_scenes(frame_source=video_manager)

    scenes = scene_manager.get_scene_list()

    return scenes