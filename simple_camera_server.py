import atexit
from flask import Flask, send_file, request, jsonify
import picamera2
import io
import threading
import time
import sys
import os
import datetime

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
    time.sleep(2)
except Exception as e:
    print(f"Error initializing camera: {e}")
    print("Is the camera connected and enabled? (Check with rpicam-still --list-cameras)")
    # Exit if camera fails to initialize, as we can't do much without it
    sys.exit(1)


# --- Flask App Setup ---
app = Flask(__name__)

# --- Timelapse State ---
timelapse_lock = threading.Lock()
timelapse_state = {
    "running": False,
    "images_per_hour": 0,
    "duration_hours": 0,
    "images_captured": 0,
    "total_images": 0,
    "output_dir": "",
    "start_time": None,
}
_timelapse_stop_event = threading.Event()

# --- Timelapse Background Thread ---
def _timelapse_worker(images_per_hour, duration_hours, output_dir, stop_event):
    """Captures images at the specified rate for the given duration."""
    total_images = int(round(images_per_hour * duration_hours))
    interval_seconds = 3600.0 / images_per_hour
    captured = 0
    while captured < total_images and not stop_event.is_set():
        if camera is None:
            break
        try:
            filename = os.path.join(output_dir, f"frame_{captured:06d}.jpg")
            camera.capture_file(filename)
            captured += 1
            with timelapse_lock:
                timelapse_state["images_captured"] = captured
            print(f"Timelapse: captured {captured}/{total_images}")
        except Exception as e:
            print(f"Timelapse capture error: {e}")
        stop_event.wait(timeout=interval_seconds)
    with timelapse_lock:
        timelapse_state["running"] = False
    print("Timelapse finished.")

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
    """Simple HTML page to display the image and timelapse controls."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pi Camera Static View</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial, sans-serif; display: flex; flex-direction: column; align-items: center; padding: 1em; }
            img { max-width: 100%; height: auto; border: 2px solid #333; }
            .timelapse-box { margin-top: 2em; border: 1px solid #aaa; border-radius: 6px; padding: 1.2em; max-width: 400px; width: 100%; }
            .timelapse-box h2 { margin-top: 0; }
            .form-row { display: flex; align-items: center; gap: 0.5em; margin-bottom: 0.6em; }
            .form-row label { flex: 1; }
            .form-row input { width: 80px; padding: 3px 6px; }
            .hint { font-size: 0.85em; color: #555; margin: 0.5em 0 0.8em; }
            .status { font-size: 0.9em; margin-top: 0.8em; padding: 0.5em; background: #f0f0f0; border-radius: 4px; }
            button { padding: 6px 18px; cursor: pointer; }
            #stopBtn { display: none; margin-left: 0.5em; }
        </style>
    </head>
    <body>
        <h1>Pi Camera View (Refresh to update)</h1>
        <img id="cameraImage" src="/static_image.jpg?" alt="Camera Image">
        <p>Refresh your browser to get a new image.</p>

        <div class="timelapse-box">
            <h2>Timelapse Capture</h2>
            <div class="form-row">
                <label for="iph">Images per hour:</label>
                <input type="number" id="iph" value="16" min="1" max="3600">
            </div>
            <div class="form-row">
                <label for="days">Duration (days):</label>
                <input type="number" id="days" value="1" min="0.1" max="365" step="0.1">
            </div>
            <div class="hint" id="calcHint"></div>
            <div>
                <button id="startBtn" onclick="startTimelapse()">Start</button>
                <button id="stopBtn" onclick="stopTimelapse()">Stop</button>
            </div>
            <div class="status" id="tlStatus">Status: idle</div>
        </div>

        <script>
            function updateHint() {
                var iph = parseFloat(document.getElementById('iph').value) || 0;
                var days = parseFloat(document.getElementById('days').value) || 0;
                var perDay = iph * 24;
                var total = Math.round(perDay * days);
                var videoSec = (total / 20).toFixed(1);
                document.getElementById('calcHint').textContent =
                    iph + ' img/h \u2192 ' + perDay + ' img/day, ' +
                    total + ' total images. At 20 fps \u2248 ' + videoSec + 's of video.';
            }
            document.getElementById('iph').addEventListener('input', updateHint);
            document.getElementById('days').addEventListener('input', updateHint);
            updateHint();

            function startTimelapse() {
                var iph = parseInt(document.getElementById('iph').value);
                var days = parseFloat(document.getElementById('days').value);
                fetch('/timelapse/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({images_per_hour: iph, duration_days: days})
                }).then(r => r.json()).then(pollStatus);
            }

            function stopTimelapse() {
                fetch('/timelapse/stop', {method: 'POST'}).then(r => r.json()).then(pollStatus);
            }

            function pollStatus() {
                fetch('/timelapse/status').then(r => r.json()).then(function(s) {
                    var txt = s.running
                        ? 'Running \u2014 ' + s.images_captured + '/' + s.total_images + ' images captured (folder: ' + s.output_dir + ')'
                        : (s.images_captured > 0
                            ? 'Done \u2014 ' + s.images_captured + ' images saved to ' + s.output_dir
                            : 'Status: idle');
                    document.getElementById('tlStatus').textContent = txt;
                    document.getElementById('startBtn').disabled = s.running;
                    document.getElementById('stopBtn').style.display = s.running ? 'inline' : 'none';
                    if (s.running) setTimeout(pollStatus, 5000);
                });
            }
            pollStatus();
        </script>
    </body>
    </html>
    """

# --- Timelapse Routes ---
@app.route('/timelapse/start', methods=['POST'])
def timelapse_start():
    """Start a timelapse capture."""
    data = request.get_json(force=True)
    images_per_hour = int(data.get('images_per_hour', 16))
    duration_days = float(data.get('duration_days', 1))
    duration_hours = duration_days * 24

    if images_per_hour < 1 or duration_hours <= 0:
        return jsonify({"error": "Invalid parameters"}), 400

    with timelapse_lock:
        if timelapse_state["running"]:
            return jsonify({"error": "Already running"}), 400

    # Create output directory
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timelapse", ts)
    os.makedirs(output_dir, exist_ok=True)

    _timelapse_stop_event.clear()
    with timelapse_lock:
        timelapse_state.update({
            "running": True,
            "images_per_hour": images_per_hour,
            "duration_hours": duration_hours,
            "images_captured": 0,
            "total_images": round(images_per_hour * duration_hours),
            "output_dir": output_dir,
            "start_time": ts,
        })

    t = threading.Thread(
        target=_timelapse_worker,
        args=(images_per_hour, duration_hours, output_dir, _timelapse_stop_event),
        daemon=True,
    )
    t.start()
    return jsonify({"status": "started", "output_dir": output_dir})

@app.route('/timelapse/stop', methods=['POST'])
def timelapse_stop():
    """Stop a running timelapse."""
    _timelapse_stop_event.set()
    with timelapse_lock:
        timelapse_state["running"] = False
    return jsonify({"status": "stopped"})

@app.route('/timelapse/status')
def timelapse_status():
    """Return current timelapse state."""
    with timelapse_lock:
        return jsonify(dict(timelapse_state))

# --- Cleanup on exit ---
def cleanup():
    """Stops the camera safely when the application exits."""
    _timelapse_stop_event.set()
    if camera:
        print("Stopping camera...")
        camera.stop()
        camera.close()
    print("Cleanup complete.")

atexit.register(cleanup)


# --- Run Flask App ---
if __name__ == '__main__':
    # host='0.0.0.0' makes it accessible from any device on your network
    # port=5000 is the standard Flask development port
    # debug=True allows for auto-reloading on code changes and provides more detailed errors.
    #            Disable in production.
    app.run(host='0.0.0.0', port=5000, debug=False)