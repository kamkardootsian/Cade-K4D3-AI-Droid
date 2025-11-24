# vision_backend.py

import cv2
import base64
import tempfile
from pathlib import Path
from openai import OpenAI

client = OpenAI()  # uses OPENAI_API_KEY from env

# Adjust if your webcam is not /dev/video0
CAMERA_INDEX = 0


def capture_frame(device_index: int = CAMERA_INDEX) -> Path:
    """
    Grab a single frame from the webcam and save it as a JPEG.
    Returns the Path to the saved file.
    """
    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {device_index}")

    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise RuntimeError("Failed to grab frame from camera")

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    img_path = Path(tmp.name)
    tmp.close()

    cv2.imwrite(str(img_path), frame)
    return img_path


def describe_scene(device_index: int = CAMERA_INDEX) -> str:
    """
    Capture a frame from the camera and ask a vision-capable model
    to describe it in 12 sentences.
    """
    img_path = capture_frame(device_index)

    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",  # or any vision-capable model you like
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You are the vision module for a small droid named Cade. "
                            "In 1-2 short sentences, describe what you see in this image. "
                            "Focus on people, their rough position, and big obvious objects. "
                            "Do not mention that you are an AI or that you are describing an image."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}"
                        },
                    },
                ],
            }
        ],
    )

    # In the new OpenAI client, message content is a list of parts.
    content = resp.choices[0].message.content
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        description = " ".join(parts).strip()
    else:
        description = str(content).strip()

    return description
