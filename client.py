import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
    try:
        chat = ChatService()
        while True:
            data = await websocket.receive_text()
            if len(data.strip()) != 0:
                await websocket.send_text(f"Message text was: {data}")
                result = await chat.sendMessage(data)
                await websocket.send_text(f"Response was: {result}")
    except WebSocketDisconnect:
        logging.info("Client disconnect")
