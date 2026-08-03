from dataclasses import dataclass
import os
import tempfile


@dataclass
class RuntimeContext:
    work_dir: str
    temp_video_path: str
    temp_audio_path: str


def create_runtime_context() -> RuntimeContext:
    work_dir = tempfile.mkdtemp(prefix='ytrd-')
    return RuntimeContext(
        work_dir=work_dir,
        temp_video_path=os.path.join(work_dir, 'temp_video.mp4'),
        temp_audio_path=os.path.join(work_dir, 'temp_audio.mp3'),
    )
