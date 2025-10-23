import io
import json
import logging
import os
import re
import uuid
from datetime import datetime

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from google import genai
from google.genai.types import ContentEmbedding, EmbedContentConfig
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pdf2image import convert_from_bytes
from qdrant_client import QdrantClient, models

load_dotenv()

app = FastAPI()

origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

files_uploaded = []


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
                        [message],
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


class VectorDatabaseService:
    def __init__(self, model="gemini-2.5-flash", chunking_prompt: str | None = None) -> None:
        # Setup Qdrant
        self.qdrant_client = QdrantClient(url="http://localhost:6333")

        # Create Qdrant collection
        self.collection_name = "test"
        if not self.qdrant_client.collection_exists(collection_name=self.collection_name):
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=768,
                    distance=models.Distance.DOT,
                    on_disk=True,
                ),
                optimizers_config=models.OptimizersConfigDiff(
                    default_segment_number=5,
                ),
                hnsw_config=models.HnswConfigDiff(
                    m=0,
                ),
                quantization_config=models.BinaryQuantization(
                    binary=models.BinaryQuantizationConfig(always_ram=True),
                ),
            )

        # Setup Google GenAI
        self.genai_client = genai.Client(api_key=os.getenv("GENAI_API_KEY"))
        self.model = model
        self.chunking_prompt = """\
OCR the following page into Markdown. Tables should be formatted as HTML.
Do not surround your output with triple backticks.
Chunk the document into sections of roughly 250 - 1000 words.
Surround each chunk with <chunk> and </chunk> tags.
Preserve as much content as possible, including headings, tables, etc.
""" if chunking_prompt is None else chunking_prompt

    # Embedding with Google GenAI
    def embedding(self, texts: list[str]) -> tuple[list[ContentEmbedding], list[str]]:
        result = self.genai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=texts,
            config=EmbedContentConfig(output_dimensionality=768)
        ).embeddings

        if result is None:
            return [], []

        return result, texts

    # Create Qdrant points
    @staticmethod
    def create_qdrant_points(embeddings: tuple[list[ContentEmbedding], list[str]],
                             payload: dict[str, object] | None = None) -> list[models.PointStruct]:
        if len(embeddings[0]) == 0:
            return []

        return [
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedded.values,
                payload={"text": text} if payload is None else {"text": text, **payload},
            )
            for idx, (embedded, text) in enumerate(zip(*embeddings))
        ]

    # Convert PDF to Image
    @staticmethod
    def convert_local_pdf_to_image(pdf_bytes: bytes) -> dict[int, bytes]:
        try:
            # Use convert_from_path to directly read the file from the provided path
            pages = convert_from_bytes(pdf_bytes)
            print(f"Successfully converted {len(pages)} PDF pages to images.")

            # This part remains the same: encode the images as base64
            images_b64 = {}
            for i, page in enumerate(pages, start=1):
                buffer = io.BytesIO()
                page.save(buffer, format="PNG")
                image_data = buffer.getvalue()
                # b64_str = base64.b64encode(image_data).decode("utf-8")
                # images_b64[i] = b64_str
                images_b64[i] = image_data

            return images_b64

        except Exception as e:
            print(f"An error occurred: {e}")
            print("Please ensure the file path is correct and that you have Poppler installed.")
            return {}

    def process_page(self, page_num, image_b64):
        try:
            resp = self.genai_client.models.generate_content(model=self.model, contents=[
                genai.types.Part.from_bytes(data=image_b64, mime_type='image/png'),
                self.chunking_prompt,
            ])
            text_out = resp.text
        except Exception as e:
            print(f"Error processing page {page_num}: {e}")
            return []
        # parse <chunk> blocks
        chunks = re.findall(r"<chunk>(.*?)</chunk>", text_out, re.DOTALL)
        if not chunks:
            # fallback if model doesn't produce chunk tags
            chunks = text_out.split("\n\n")
        results = []
        for idx, chunk_txt in enumerate(chunks):
            # store ID, chunk text
            results.append({
                "id": f"page_{page_num}_chunk_{idx}",
                "text": chunk_txt.strip()
            })
        return results

    def upload_to_vector_db(self, pdf_bytes: bytes):
        all_images = self.convert_local_pdf_to_image(pdf_bytes)
        all_chunks = []
        for i, b64_str in all_images.items():
            page_chunks = self.process_page(i, b64_str)
            all_chunks.extend(page_chunks)

        chunks_data = [e["text"] for e in all_chunks]
        embed = self.embedding(chunks_data)

        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=self.create_qdrant_points(
                embeddings=embed,
            )
        )

    def query(self, user_query: str):
        query_vector = self.embedding([user_query])[0][0].values

        search_limit = 3
        search_results = self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            with_payload=True,
            with_vectors=False,
            limit=search_limit
        ).points

        retrieved_chunks = [chunk.payload["text"] for chunk in search_results]
        context_for_llm = "\n\n".join(retrieved_chunks)

        final_prompt = f"""Use the following context to answer the question:
        Context:
        {context_for_llm}
        Question: {user_query}
        Answer:
        """

        return final_prompt


@app.get("/")
async def get():
    return HTMLResponse(html)


VecDBService = VectorDatabaseService()


@app.post("/upload-files/")
async def upload_file(files: list[UploadFile]):
    for file in files:
        data = await file.read()
        VecDBService.upload_to_vector_db(pdf_bytes=data)

    return {"filename": [file.filename for file in files]}


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
                        result = await chat.sendMessage(VecDBService.query(broadcast_message["message"]))
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


@app.websocket("/n8n")
async def websocket_endpoint_n8n(websocket: WebSocket):
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
                        response = requests.post(
                            'https://uat-n8n.tevassur.com/webhook/51822a46-d90d-4aed-b62b-e06c466ec0f5',
                            json={
                                "sessionId": "6af3f8c2b5da4c9a8c1df016b0fc0800",
                                "action": "sendMessage",
                                "chatInput": broadcast_message["message"],
                            },
                            headers={
                                'Content-Type': 'application/json',
                                'Authorization': 'Basic Y2xpZW50OkBjbGllbnQ=',
                            }
                        )
                        result = response.json()
                        broadcast_message["message"] = result[0]["output"]

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
