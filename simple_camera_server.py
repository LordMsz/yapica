from flask import Flask, send_file
import picamera2
import io
import threading
import sys
import os # For checking if camera module exists

# --- Initialize Camera ---
camera = None
try:
    camera = picamera2.Picamera2()
    # Configure for a still image capture suitable for viewing
    camera_config = camera.create_still_configuration(main={"size": (640, 480)})
    camera.configure(camera_config)
    camera.start()
    print("Camera initialized.")
    # Give camera a moment to warm up and set exposure
    # This is important for the first image to be well-exposed
    print("Waiting for camera to warm up...")
    import time
    time.sleep(2)
except Exception as e:
    print(f"Error initializing camera: {e}")
    print("Is the camera connected and enabled? (Check with rpicam-still --list-cameras)")
    # Exit if camera fails to initialize, as we can't do much without it
    sys.exit(1)


# --- Flask App Setup ---
app = Flask(__name__)

# --- Capture Image Function ---
def capture_image_to_bytes():
    """Captures a single JPEG image to a BytesIO object."""
    if camera is None:
        print("Camera not initialized, cannot capture image.")
        return None

    try:
        stream = io.BytesIO()
        camera.capture_file(stream, format='jpeg')
        stream.seek(0) # Rewind the stream to the beginning
        return stream
    except Exception as e:
        print(f"Error capturing image: {e}")
        return None

# --- Flask Routes ---
@app.route('/static_image.jpg')
def static_image():
    """Serves a fresh JPEG image every time the URL is accessed."""
    image_bytes = capture_image_to_bytes()
    if image_bytes:
        return send_file(image_bytes, mimetype='image/jpeg')
    else:
        # Return a placeholder or error image if capture failed
        # For simplicity, we'll just return a 500 error for now
        return "Failed to capture image", 500

@app.route('/')
def index():
    """Simple HTML page to display the image. Requires manual refresh."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pi Camera Static View</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial, sans-serif; display: flex; flex-direction: column; align-items>            img { max-width: 100%; height: auto; border: 2px solid #333; }
        </style>                                                                                          </head>
    <body>
        <h1>Pi Camera View (Refresh to update)</h1>
        <img id="cameraImage" src="/static_image.jpg?" alt="Camera Image">
        <p>Refresh your browser to get a new image.</p>
    </body>
    </html>
    """

# --- Cleanup on exit ---
def cleanup():
    """Stops the camera safely when the application exits."""
    if camera:
        print("Stopping camera...")
        camera.stop()
        camera.close()
    print("Cleanup complete.")
    sys.exit(0)

import atexit
atexit.register(cleanup)


# --- Run Flask App ---
if __name__ == '__main__':
    # host='0.0.0.0' makes it accessible from any device on your network
    # port=5000 is the standard Flask development port
    # debug=True allows for auto-reloading on code changes and provides more detailed errors.
    #            Disable in production.
    app.run(host='0.0.0.0', port=5000, debug=False)