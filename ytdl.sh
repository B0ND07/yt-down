#!/bin/bash
# YouTube Downloader Backend Management Script

case "$1" in
    start)
        echo "Starting YouTube downloader backend..."
        cd /root/ytdl/backend
        source venv/bin/activate
        nohup python3 server.py > app.log 2>&1 &
        echo "Backend started. PID: $!"
        echo "View logs: tail -f /root/ytdl/backend/ytdl_backend.log"
        ;;
    stop)
        echo "Stopping YouTube downloader backend..."
        pkill -f "python3 server.py"
        echo "Backend stopped."
        ;;
    restart)
        echo "Restarting YouTube downloader backend..."
        pkill -f "python3 server.py"
        sleep 2
        cd /root/ytdl/backend
        source venv/bin/activate
        nohup python3 server.py > app.log 2>&1 &
        echo "Backend restarted. PID: $!"
        ;;
    status)
        echo "Backend status:"
        ps aux | grep "python3 server.py" | grep -v grep || echo "Not running"
        ;;
    logs)
        tail -f /root/ytdl/backend/app.log
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac