import cv2

cap = cv2.VideoCapture(0)  # 0 = /dev/video0

if not cap.isOpened():
    print("Cannot open camera")
    exit(1)

ret, frame = cap.read()
cap.release()

if not ret:
    print("Failed to grab frame")
    exit(1)

cv2.imwrite("test_frame.jpg", frame)
print("Saved test_frame.jpg")
