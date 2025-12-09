
import os
import sys
import subprocess
import time
import requests
from datetime import datetime
from threading import Thread
from flask import Flask, jsonify

# Flask App
app = Flask(__name__)

# Global status tracker
stream_status = {
    'is_streaming': False,
    'attempt': 0,
    'uptime_seconds': 0,
    'last_restart': None,
    'fps': 0,
    'download_status': 'Not started'
}

# Environment variables
YOUTUBE_STREAM_URL = os.getenv('YOUTUBE_STREAM_URL')
YOUTUBE_STREAM_KEY = os.getenv('YOUTUBE_STREAM_KEY')

# Internet Archive video URL
VIDEO_URL = 'https://archive.org/download/1128_20251128/1128.mp4'
VIDEO_FILE = 'downloaded_video.mp4'

def log(message):
    """Print timestamped log message"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def download_video():
    """Download video from Internet Archive"""
    if os.path.exists(VIDEO_FILE):
        file_size = os.path.getsize(VIDEO_FILE)
        log(f"Video already exists: {VIDEO_FILE} (Size: {file_size / (1024*1024):.2f} MB)")
        stream_status['download_status'] = 'Already downloaded'
        return True
    
    log(f"Downloading video from: {VIDEO_URL}")
    stream_status['download_status'] = 'Downloading...'
    
    try:
        response = requests.get(VIDEO_URL, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(VIDEO_FILE, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Log progress every 10 MB
                    if downloaded % (10 * 1024 * 1024) < 8192:
                        progress = (downloaded / total_size * 100) if total_size > 0 else 0
                        log(f"Download progress: {downloaded / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB ({progress:.1f}%)")
        
        file_size = os.path.getsize(VIDEO_FILE)
        log(f"Video downloaded successfully: {VIDEO_FILE} (Size: {file_size / (1024*1024):.2f} MB)")
        stream_status['download_status'] = 'Complete'
        return True
        
    except Exception as e:
        log(f"ERROR: Failed to download video: {str(e)}")
        stream_status['download_status'] = f'Failed: {str(e)}'
        if os.path.exists(VIDEO_FILE):
            os.remove(VIDEO_FILE)
        return False

def validate_video():
    """Check if video file exists and is valid"""
    if not os.path.exists(VIDEO_FILE):
        return False
    
    file_size = os.path.getsize(VIDEO_FILE)
    if file_size == 0:
        log(f"ERROR: {VIDEO_FILE} is empty!")
        return False
    
    log(f"Video file validated: {VIDEO_FILE} (Size: {file_size / (1024*1024):.2f} MB)")
    return True

def heartbeat():
    """Update uptime counter every second"""
    start_time = time.time()
    while True:
        if stream_status['is_streaming']:
            stream_status['uptime_seconds'] = int(time.time() - start_time)
        time.sleep(1)

def start_stream():
    """Start ffmpeg streaming process with optimized settings"""
    rtmp_url = f"{YOUTUBE_STREAM_URL}/{YOUTUBE_STREAM_KEY}"
    
    # Optimized FFmpeg settings for fast, stable streaming
    ffmpeg_command = [
        'ffmpeg',
        '-re',                          # Real-time streaming
        '-stream_loop', '-1',           # Infinite loop
        '-i', VIDEO_FILE,
        
        # Video encoding settings - optimized for speed
        '-vcodec', 'libx264',
        '-preset', 'ultrafast',         # Fastest encoding preset
        '-tune', 'zerolatency',         # Minimize latency
        '-maxrate', '4500k',            # Max bitrate
        '-bufsize', '5000k',            # Buffer size
        '-pix_fmt', 'yuv420p',
        '-g', '60',                     # Keyframe interval (2 seconds at 30fps)
        '-r', '30',                     # Force 30 FPS output
        '-vsync', '1',                  # Sync video frames
        
        # Audio encoding settings - optimized
        '-acodec', 'aac',
        '-b:a', '128k',
        '-ar', '44100',
        '-ac', '2',                     # Stereo audio
        
        # Threading for better performance
        '-threads', '4',
        
        # Output format
        '-f', 'flv',
        rtmp_url
    ]
    
    log("Starting optimized ffmpeg stream...")
    log(f"Settings: 30 FPS, ultrafast preset, zero latency")
    
    stream_status['is_streaming'] = True
    stream_status['last_restart'] = datetime.now().strftime('%H:%M:%S')
    
    try:
        process = subprocess.Popen(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        # Monitor ffmpeg output and extract FPS
        for line in process.stdout:
            if line.strip():
                # Extract FPS from ffmpeg output
                if 'fps=' in line:
                    try:
                        fps_part = line.split('fps=')[1].split()[0]
                        stream_status['fps'] = float(fps_part)
                    except:
                        pass
                
                # Log only important messages
                if any(x in line for x in ['error', 'Error', 'ERROR', 'frame=', 'Stream #']):
                    log(f"ffmpeg: {line.strip()}")
        
        return_code = process.wait()
        log(f"ffmpeg process exited with code: {return_code}")
        stream_status['is_streaming'] = False
        return return_code
        
    except Exception as e:
        log(f"ffmpeg error: {str(e)}")
        stream_status['is_streaming'] = False
        return -1

def validate_environment():
    """Validate all required environment variables are set"""
    log("Validating environment variables...")
    
    if not YOUTUBE_STREAM_URL:
        log("ERROR: YOUTUBE_STREAM_URL not set!")
        sys.exit(1)
    
    if not YOUTUBE_STREAM_KEY:
        log("ERROR: YOUTUBE_STREAM_KEY not set!")
        sys.exit(1)
    
    log("All environment variables validated successfully")

# Flask Routes
@app.route('/')
def index():
    """Web dashboard"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube Live Stream Bot</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #1a1a1a;
                color: #fff;
                padding: 20px;
                max-width: 800px;
                margin: 0 auto;
            }}
            .card {{
                background: #2d2d2d;
                border-radius: 10px;
                padding: 20px;
                margin: 20px 0;
            }}
            .status {{
                font-size: 24px;
                font-weight: bold;
                color: {'#00ff00' if stream_status['is_streaming'] else '#ff0000'};
            }}
            .stat {{
                margin: 10px 0;
                font-size: 18px;
            }}
            h1 {{
                color: #ff0000;
            }}
            .download-status {{
                color: #00aaff;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <h1>🔴 YouTube LIVE Stream Bot</h1>
        <div class="card">
            <div class="status">{'🟢 STREAMING' if stream_status['is_streaming'] else '🔴 OFFLINE'}</div>
            <div class="stat">📥 Download Status: <span class="download-status">{stream_status['download_status']}</span></div>
            <div class="stat">📊 Stream Attempt: #{stream_status['attempt']}</div>
            <div class="stat">⏱️ Uptime: {stream_status['uptime_seconds']} seconds</div>
            <div class="stat">🎬 Current FPS: {stream_status['fps']:.1f}</div>
            <div class="stat">🔄 Last Restart: {stream_status['last_restart'] or 'N/A'}</div>
        </div>
        <div class="card">
            <p>🎥 Streaming from Internet Archive</p>
            <p>Auto-refreshes every 5 seconds</p>
            <p>API Endpoint: <a href="/status" style="color: #00ff00;">/status</a></p>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/status')
def status():
    """JSON API for stream status"""
    return jsonify(stream_status)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'streaming': stream_status['is_streaming']})

def run_flask():
    """Run Flask server"""
    log("Starting Flask web server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def streaming_loop():
    """Main streaming loop with auto-reconnect"""
    validate_environment()
    
    # Download video first
    log("Step 1: Downloading video from Internet Archive...")
    if not download_video():
        log("ERROR: Failed to download video from Internet Archive")
        sys.exit(1)
    
    # Validate downloaded video
    if not validate_video():
        log("ERROR: Downloaded video validation failed")
        sys.exit(1)
    
    log("Video ready for streaming!")
    
    # Infinite streaming loop with auto-reconnect
    attempt = 0
    while True:
        attempt += 1
        stream_status['attempt'] = attempt
        log(f"Stream attempt #{attempt}")
        
        return_code = start_stream()
        
        log(f"Stream ended with return code: {return_code}")
        log("Reconnecting in 5 seconds...")
        time.sleep(5)

def main():
    """Main bot logic"""
    log("=" * 50)
    log("YouTube LIVE Streaming Bot Starting...")
    log("Source: Internet Archive (1127.mp4)")
    log("=" * 50)
    
    # Start heartbeat thread
    heartbeat_thread = Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    log("Heartbeat thread started")
    
    # Start Flask server in separate thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    log("Flask web server started on http://0.0.0.0:5000")
    
    # Start streaming in main thread
    streaming_loop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Bot stopped by user")
        stream_status['is_streaming'] = False
        sys.exit(0)
    except Exception as e:
        log(f"Fatal error: {str(e)}")
        stream_status['is_streaming'] = False
        sys.exit(1)
