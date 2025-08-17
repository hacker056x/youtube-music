from flask import Flask, render_template, request, send_file, Response, jsonify
import os
import threading
from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
from io import BytesIO
import uuid
import logging

app = Flask(__name__)
app.config['DOWNLOAD_FOLDER'] = os.path.join(os.getcwd(), 'downloads')
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

ytmusic = YTMusic()
download_progress = {}
logging.basicConfig(level=logging.INFO)

@app.route('/')
def index():
    """Render the main page with the search interface."""
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    """Search for songs based on the query."""
    query = request.form.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Query is required'}), 400
    try:
        results = ytmusic.search(query, filter='songs')
        songs = [
            {
                'videoId': song['videoId'],
                'title': song['title'],
                'artist': ', '.join(a['name'] for a in song['artists'])
            }
            for song in results
        ]
        return jsonify({'results': songs})
    except Exception as e:
        logging.error(f"Search error: {e}")
        return jsonify({'error': 'Failed to search songs'}), 500

@app.route('/download', methods=['POST'])
def download():
    """Initiate song download and stream the file."""
    video_id = request.form.get('videoId')
    quality = request.form.get('quality', '128')
    if not video_id:
        return jsonify({'error': 'No song selected'}), 400

    download_id = str(uuid.uuid4())
    download_progress[download_id] = 0

    def progress_hook(d):
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0.0%').strip().replace('%', '')
            try:
                download_progress[download_id] = int(float(percent_str))
            except ValueError:
                pass
        elif d['status'] == 'finished':
            download_progress[download_id] = 100

    def download_thread():
        try:
            url = f"https://music.youtube.com/watch?v={video_id}"
            output_file = os.path.join(app.config['DOWNLOAD_FOLDER'], f"{download_id}.%(ext)s")
            options = {
                'format': 'bestaudio/best',
                'outtmpl': output_file,
                'quiet': True,
                'noplaylist': True,
                'progress_hooks': [progress_hook],
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality,
                }],
                'ffmpeg_location': '/usr/bin/ffmpeg'  # Render provides ffmpeg
            }
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
                download_progress[download_id] = {'filename': filename}
        except Exception as e:
            logging.error(f"Download error: {e}")
            download_progress[download_id] = {'error': str(e)}

    threading.Thread(target=download_thread, daemon=True).start()
    return jsonify({'download_id': download_id})

@app.route('/progress/<download_id>')
def progress(download_id):
    """Return the download progress for a given download ID."""
    progress = download_progress.get(download_id, 0)
    if isinstance(progress, dict):
        if 'error' in progress:
            return jsonify({'error': progress['error']}), 500
        return jsonify({'progress': 100, 'filename': progress['filename']})
    return jsonify({'progress': progress})

@app.route('/download_file/<download_id>')
def download_file(download_id):
    """Stream the downloaded file to the client."""
    if download_id not in download_progress or 'filename' not in download_progress[download_id]:
        return jsonify({'error': 'File not ready or does not exist'}), 400
    filename = download_progress[download_id]['filename']
    if not os.path.exists(filename):
        return jsonify({'error': 'File not found'}), 404

    def generate():
        with open(filename, 'rb') as f:
            while chunk := f.read(8192):
                yield chunk
        try:
            os.remove(filename)  # Clean up after streaming
            download_progress.pop(download_id, None)
        except Exception as e:
            logging.error(f"Error cleaning up file: {e}")

    return Response(
        generate(),
        mimetype='audio/mpeg',
        headers={'Content-Disposition': f'attachment; filename="{os.path.basename(filename)}"'}
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)