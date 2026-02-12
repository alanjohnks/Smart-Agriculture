import serial
import numpy as np
import cv2
import threading

PORT = "COM3"
BAUD = 921600

WIDTH = 96
HEIGHT = 96
BYTES_PER_PIXEL = 2
EXPECTED_RAW = WIDTH * HEIGHT * BYTES_PER_PIXEL

START = b"RAW_RGB565_START"
END   = b"RAW_RGB565_END"

# Only the two needed flags
flags = {
    "byte_swap": True,
    "channel_swap": True
}

latest_frame = None
lock = threading.Lock()
running = True


# ---------------------------------------------------------
# RGB565 → RGB888 with only two toggles
# ---------------------------------------------------------
def rgb565_to_rgb888(px, byte_swap=False, channel_swap=False):
    if byte_swap:
        px = ((px & 0xFF) << 8) | (px >> 8)

    r = ((px >> 11) & 0x1F) << 3
    g = ((px >> 5) & 0x3F) << 2
    b = (px & 0x1F) << 3

    if channel_swap:
        return np.stack([b, g, r], axis=-1).astype(np.uint8)
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


# ---------------------------------------------------------
# Very simple frame converter (no padding/offset logic)
# ---------------------------------------------------------
def convert_frame(raw):
    if len(raw) != EXPECTED_RAW:
        return None

    arr = np.frombuffer(raw, dtype=np.uint8).reshape((-1, 2))
    lo = arr[:, 0].astype(np.uint16)
    hi = arr[:, 1].astype(np.uint16)
    px = (hi << 8) | lo

    rgb = rgb565_to_rgb888(px,
                           byte_swap=flags["byte_swap"],
                           channel_swap=flags["channel_swap"])
    return rgb.reshape((HEIGHT, WIDTH, 3))


# ---------------------------------------------------------
# Thread for reading serial
# ---------------------------------------------------------
def serial_reader():
    global latest_frame, running
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.01)
    except Exception as e:
        print("Failed to open serial:", e)
        running = False
        return

    buffer = b""

    while running:
        data = ser.read(4096)
        if data:
            buffer += data

        start = buffer.find(START)
        end   = buffer.find(END)

        if start != -1 and end != -1 and end > start:
            raw = buffer[start + len(START): end]
            buffer = buffer[end + len(END):]

            frame = convert_frame(raw)
            if frame is not None:
                with lock:
                    latest_frame = frame


# ---------------------------------------------------------
# Main loop
# ---------------------------------------------------------
def main():
    global running
    threading.Thread(target=serial_reader, daemon=True).start()

    cv2.namedWindow("ESP32 Stream", cv2.WINDOW_NORMAL)

    print("\n=== Controls ===")
    print("b = toggle byte swap")
    print("c = toggle channel (RGB/BGR) swap")
    print("q = quit")
    print("================\n")

    while running:
        with lock:
            frame = latest_frame.copy() if latest_frame is not None else None

        if frame is not None:
            up = cv2.resize(frame, (320, 320), interpolation=cv2.INTER_NEAREST)
            cv2.imshow("ESP32 Stream", up)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('b'):
            flags["byte_swap"] = not flags["byte_swap"]
            print("byte_swap =", flags["byte_swap"])

        elif key == ord('c'):
            flags["channel_swap"] = not flags["channel_swap"]
            print("channel_swap =", flags["channel_swap"])

        elif key == ord('q'):
            running = False

    cv2.destroyAllWindows()

    print("\n======== DEBUG SUMMARY ========")
    for k, v in flags.items():
        print(f"{k}: {v}")
    print("================================")


if __name__ == "__main__":
    main()
