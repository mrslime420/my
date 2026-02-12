from flask import Flask
import threading
import time

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK"

def run_webserver():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_webserver, daemon=True).start()

# Keep main thread alive
while True:
    time.sleep(60)
