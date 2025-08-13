import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

app = FastAPI()

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://localhost:8000/ws");
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""


class ChatService:
    def __init__(self, model="gemini-2.5-flash") -> None:
        self.model = model
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.chat = self.client.aio.chats.create(model=self.model)
        self.server_params = StdioServerParameters(
            command="python",  # Executable
            args=["server.py"],  # MCP Server
            env=None,  # Optional environment variables
        )

    async def sendMessage(self, message: str) -> str:
        result = ""
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                try:
                    response = await self.chat.send_message_stream(
                        message,
                        config=genai.types.GenerateContentConfig(
                            temperature=0,
                            tools=[session],
                        ),
                    )

                    async for chunk in response:
                        for candidate in chunk.candidates:
                            for part in candidate.content.parts:
                                if part.text:
                                    result += part.text
                except Exception as e:
                    logging.error(f"Error during chat: {str(e)}")
        return result


@app.get("/")
async def get():
    return HTMLResponse(html)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    chat = ChatService()
    try:
        while True:
            data = await websocket.receive_text()

            try:
                # Try to parse as JSON
                message_data = json.loads(data)

                # Handle different message types
                if message_data.get("type") == "message":
                    # Prepare message for broadcasting
                    broadcast_message = {
                        "type": "message",
                        "message": message_data.get("message", ""),
                        "sender": "Agent",
                        "timestamp": message_data.get(
                            "timestamp", datetime.now().isoformat()
                        ),
                        "isOwn": False,  # Recipients see it as not their own
                    }

                    if len(broadcast_message["message"]) != 0:
                        result = await chat.sendMessage(broadcast_message["message"])
                        broadcast_message["message"] = result

                    await websocket.send_text(json.dumps(broadcast_message))

                elif message_data.get("type") == "ping":
                    # Handle ping/keepalive
                    pong_message = {
                        "type": "pong",
                        "timestamp": datetime.now().isoformat(),
                    }
                    await websocket.send_text(json.dumps(pong_message))

            except json.JSONDecodeError:
                # Handle plain text messages
                broadcast_message = {
                    "type": "message",
                    "message": data,
                    "sender": "Unknown",
                    "timestamp": datetime.now().isoformat(),
                    "isOwn": False,
                }

                await websocket.send_text(json.dumps(broadcast_message))

    except WebSocketDisconnect:
        logging.info("Client disconnect")
