#!/bin/bash
# Start the server and login

echo "Starting local server in background..."
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > /tmp/chattercheetah_server.log 2>&1 &
SERVER_PID=$!

echo "Waiting for server to start..."
sleep 3

# Check if server is running
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✓ Server is running (PID: $SERVER_PID)"
    echo ""
    echo "Login command:"
    echo 'curl -X POST "http://localhost:8000/api/v1/auth/login" \'
    echo '  -H "Content-Type: application/json" \'
    echo '  -d '"'"'{"email":"dustin.yates@gmail.com","password":"Hudlink2168"}'"' | python3 -m json.tool"
    echo ""
    echo "To stop the server, run: kill $SERVER_PID"
    echo "Or find it with: ps aux | grep uvicorn"
else
    echo "❌ Server failed to start. Check /tmp/chattercheetah_server.log"
    kill $SERVER_PID 2>/dev/null
fi

