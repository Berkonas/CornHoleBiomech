"""Non-destructive frame-indexed trim, pixel crop and clockwise rotation."""
from pathlib import Path
import json
import cv2
from .video import read_video_metadata


def prepare_video(source, output, start_frame=0, end_frame=None, crop=None, rotation=0):
    source, output = Path(source).resolve(), Path(output).resolve()
    metadata = read_video_metadata(source)
    if output == source or output.exists() or output.with_suffix('.preparation.json').exists():
        raise ValueError('Choose a new output path; existing files cannot be overwritten.')
    end_frame = metadata.frame_count if end_frame is None else end_frame
    if not (isinstance(start_frame, int) and isinstance(end_frame, int)
            and 0 <= start_frame < end_frame <= metadata.frame_count):
        raise ValueError('Trim bounds must be whole frame indices within the recording.')
    if rotation not in (0, 90, 180, 270):
        raise ValueError('Rotation must be 0, 90, 180, or 270 degrees clockwise.')
    x, y, width, height = crop or (0, 0, metadata.width, metadata.height)
    if any(not isinstance(v, int) for v in (x, y, width, height)) or not (
        x >= 0 and y >= 0 and width >= 16 and height >= 16
        and x + width <= metadata.width and y + height <= metadata.height
    ):
        raise ValueError('Crop must lie inside the source and be at least 16 × 16 pixels.')
    if width % 2 or height % 2:
        raise ValueError('Crop width and height must be even; pixels will not be stretched.')
    output.parent.mkdir(parents=True, exist_ok=True)
    size = (height, width) if rotation in (90, 270) else (width, height)
    capture = cv2.VideoCapture(str(source))
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*'mp4v'), metadata.fps, size)
    count = 0
    try:
        if not writer.isOpened():
            raise RuntimeError('This runtime could not create an MPEG-4 video.')
        # Decode from zero: compressed-video seeking can land on a keyframe.
        for index in range(end_frame):
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f'Could not decode source frame {index}.')
            if index < start_frame:
                continue
            frame = frame[y:y + height, x:x + width]
            if rotation:
                frame = cv2.rotate(frame, {90: cv2.ROTATE_90_CLOCKWISE,
                    180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rotation])
            writer.write(frame)
            count += 1
    except Exception:
        writer.release()
        output.unlink(missing_ok=True)
        raise
    finally:
        capture.release()
        writer.release()
    try:
        derived = read_video_metadata(output)
        if derived.frame_count != count or (derived.width, derived.height) != size:
            raise ValueError('Encoded clip did not retain the requested frames and dimensions.')
        manifest = {
            'schema_version': 1, 'original': metadata.to_dict(), 'derived': derived.to_dict(),
            'start_frame_inclusive': start_frame, 'end_frame_exclusive': end_frame,
            'crop_source_pixels': [x, y, width, height], 'rotation_clockwise_degrees': rotation,
            'source_frame_mapping': 'source_frame = derived_frame + start_frame_inclusive',
            'audio': 'omitted', 'resized': False, 'timing': 'constant source nominal fps',
            'warning': 'Variable-frame-rate timing is not preserved. Use a constant-frame-rate camera recording for timing and derivatives.',
        }
        output.with_suffix('.preparation.json').write_text(json.dumps(manifest, indent=2))
        return manifest
    except Exception:
        output.unlink(missing_ok=True)
        raise
