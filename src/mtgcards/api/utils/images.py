import cv2
import numpy as np


def _variance_of_laplacian(image):
    return cv2.Laplacian(image, cv2.CV_64F).var()


def measure_blurriness(image_path):
    image = cv2.imread(str(image_path))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return _variance_of_laplacian(gray)


def measure_blurriness_from_bytes(data):
    arr = np.frombuffer(data, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return _variance_of_laplacian(gray)
