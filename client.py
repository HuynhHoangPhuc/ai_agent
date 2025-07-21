import os
import asyncio
import sys
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai

# Load environment variables
load_dotenv("./.env")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
chat = client.aio.chats.create(model="gemini-2.5-flash")

# Create server parameters for stdio connection
server_params = StdioServerParameters(
    command="python",  # Executable
    args=["server_test.py"],  # MCP Server
    env=None,  # Optional environment variables
)


async def run():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection between client and server
            await session.initialize()

            while True:
                try:
                    prompt = input("\nYour query: ").strip()
                    if prompt.lower() == "quit":
                        print("Session ended. Goodbye!")
                        break
                    response = await chat.send_message_stream(
                        prompt,
                        config=genai.types.GenerateContentConfig(
                            temperature=0,
                            tools=[session],
                        ),
                    )
                    async for chunk in response:
                        for i in chunk.candidates:
                            for part in i.content.parts:
                                if part.text:
                                    print(part.text, end="", flush=True)
                except KeyboardInterrupt:
                    print("\nSession interrupted. Goodbye!")
                    break
                except Exception as e:
                    print(f"\nAn error occurred: {str(e)}")


# Start the asyncio event loop and run the main function
if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Session interrupted. Goodbye!")
    finally:
        sys.stderr = open(os.devnull, "w")
