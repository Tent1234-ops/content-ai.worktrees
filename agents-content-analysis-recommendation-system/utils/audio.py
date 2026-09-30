import subprocess

def extract_audio(video_path, output_audio):

    subprocess.run([
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-ar", "16000",
        "-ac", "1",
        output_audio
    ])

    return output_audio