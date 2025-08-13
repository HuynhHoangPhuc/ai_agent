import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect, useRef } from "react";
import { Send, Users, Circle } from "lucide-react";

export const Route = createFileRoute("/chat")({
	component: ChatPage,
});

// Type definitions
interface Message {
	id: string;
	text: string;
	sender: string;
	timestamp: string;
	isOwn?: boolean;
	isSystem?: boolean;
}

interface WebSocketMessage {
	type: "message" | "user_count" | "system";
	message?: string;
	sender?: string;
	timestamp?: string;
	count?: number;
	isOwn?: boolean;
}

type ConnectionStatus = "Connected" | "Disconnected" | "Connecting" | "Error";

interface UseWebSocketReturn {
	socket: WebSocket | null;
	messages: Message[];
	connectionStatus: ConnectionStatus;
	onlineUsers: number;
	sendMessage: (message: string, sender?: string) => void;
}

// WebSocket hook for managing connection and messages
function useWebSocket(url: string): UseWebSocketReturn {
	const [socket, setSocket] = useState<WebSocket | null>(null);
	const [messages, setMessages] = useState<Message[]>([]);
	const [connectionStatus, setConnectionStatus] =
		useState<ConnectionStatus>("Disconnected");
	const [onlineUsers, setOnlineUsers] = useState<number>(0);

	useEffect(() => {
		setConnectionStatus("Connecting");
		const ws = new WebSocket(url);

		ws.onopen = () => {
			setSocket(ws);
			setConnectionStatus("Connected");
			console.log("WebSocket connected");
		};

		ws.onmessage = (event: MessageEvent) => {
			try {
				const data: WebSocketMessage = JSON.parse(event.data);

				// Handle different message types
				if (data.type === "message" && data.message) {
					setMessages((prev) => [
						...prev,
						{
							id: `${Date.now()}-${Math.random()}`,
							text: data.message as string,
							sender: data.sender || "Anonymous",
							timestamp: data.timestamp || new Date().toISOString(),
							isOwn: data.isOwn || false,
						},
					]);
				} else if (
					data.type === "user_count" &&
					typeof data.count === "number"
				) {
					setOnlineUsers(data.count);
				} else if (data.type === "system" && data.message) {
					setMessages((prev) => [
						...prev,
						{
							id: `${Date.now()}-${Math.random()}`,
							text: data.message as string,
							sender: "System",
							timestamp: new Date().toISOString(),
							isSystem: true,
						},
					]);
				}
			} catch (error) {
				// Handle plain text messages
				setMessages((prev) => [
					...prev,
					{
						id: `${Date.now()}-${Math.random()}`,
						text: event.data,
						sender: "Unknown",
						timestamp: new Date().toISOString(),
						isOwn: false,
					},
				]);
			}
		};

		ws.onclose = () => {
			setConnectionStatus("Disconnected");
			setSocket(null);
			console.log("WebSocket disconnected");
		};

		ws.onerror = (error: Event) => {
			setConnectionStatus("Error");
			console.error("WebSocket error:", error);
		};

		return () => {
			ws.close();
		};
	}, [url]);

	const sendMessage = (message: string, sender = "You"): void => {
		if (socket && socket.readyState === WebSocket.OPEN) {
			const messageData: WebSocketMessage = {
				type: "message",
				message,
				sender,
				timestamp: new Date().toISOString(),
			};
			socket.send(JSON.stringify(messageData));

			// Add to local messages immediately for better UX
			setMessages((prev) => [
				...prev,
				{
					id: `${Date.now()}-${Math.random()}`,
					text: message,
					sender,
					timestamp: new Date().toISOString(),
					isOwn: true,
				},
			]);
		}
	};

	return {
		socket,
		messages,
		connectionStatus,
		onlineUsers,
		sendMessage,
	};
}

// Main Chat component
function ChatPage(): JSX.Element {
	const [message, setMessage] = useState<string>("");
	const [username, setUsername] = useState<string>(() => {
		if (typeof window !== "undefined") {
			return window.localStorage?.getItem("chatUsername") || "Anonymous";
		}
		return "Anonymous";
	});
	const [isUsernameSet, setIsUsernameSet] = useState<boolean>(() => {
		if (typeof window !== "undefined") {
			return !!window.localStorage?.getItem("chatUsername");
		}
		return false;
	});
	const messagesEndRef = useRef<HTMLDivElement>(null);

	// Replace with your FastAPI WebSocket URL
	const { messages, connectionStatus, onlineUsers, sendMessage } = useWebSocket(
		"ws://localhost:8000/ws",
	);

	// Auto-scroll to bottom when new messages arrive
	useEffect(() => {
		messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [messages]);

	const handleSendMessage = (
		e:
			| React.MouseEvent<HTMLButtonElement>
			| React.KeyboardEvent<HTMLInputElement>,
	): void => {
		e.preventDefault();
		if (message.trim() && connectionStatus === "Connected") {
			sendMessage(message.trim(), username);
			setMessage("");
		}
	};

	const handleUsernameSubmit = (
		e:
			| React.MouseEvent<HTMLButtonElement>
			| React.KeyboardEvent<HTMLInputElement>,
	): void => {
		e.preventDefault();
		if (username.trim()) {
			if (typeof window !== "undefined") {
				window.localStorage?.setItem("chatUsername", username.trim());
			}
			setIsUsernameSet(true);
		}
	};

	const getConnectionStatusColor = (): string => {
		switch (connectionStatus) {
			case "Connected":
				return "text-green-500";
			case "Disconnected":
				return "text-red-500";
			case "Error":
				return "text-red-500";
			case "Connecting":
				return "text-yellow-500";
			default:
				return "text-gray-500";
		}
	};

	const formatTime = (timestamp: string): string => {
		return new Date(timestamp).toLocaleTimeString([], {
			hour: "2-digit",
			minute: "2-digit",
		});
	};

	const handleInputKeyPress = (
		e: React.KeyboardEvent<HTMLInputElement>,
		action: "send" | "username",
	): void => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			if (action === "send") {
				handleSendMessage(e);
			} else {
				handleUsernameSubmit(e);
			}
		}
	};

	const handleChangeUsername = (): void => {
		if (typeof window !== "undefined") {
			window.localStorage?.removeItem("chatUsername");
		}
		setIsUsernameSet(false);
	};

	if (!isUsernameSet) {
		return (
			<div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
				<div className="bg-white rounded-lg shadow-lg p-8 w-full max-w-md">
					<h1 className="text-2xl font-bold text-gray-900 mb-6 text-center">
						Join Chat
					</h1>
					<div className="space-y-4">
						<div>
							<div className="block text-sm font-medium text-gray-700 mb-2">
								Choose a username
							</div>
							<input
								type="text"
								value={username}
								onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
									setUsername(e.target.value)
								}
								placeholder="Enter your username"
								className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
								maxLength={20}
								onKeyPress={(e) => handleInputKeyPress(e, "username")}
							/>
						</div>
						<button
							onClick={handleUsernameSubmit}
							className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
						>
							Join Chat
						</button>
					</div>
				</div>
			</div>
		);
	}

	return (
		<div className="min-h-screen bg-gray-50">
			{/* Header */}
			<div className="bg-white shadow-sm border-b border-gray-200">
				<div className="max-w-4xl mx-auto px-4 py-4">
					<div className="flex items-center justify-between">
						<h1 className="text-2xl font-bold text-gray-900">
							Car Value AI Agent
						</h1>
						<div className="flex items-center space-x-4">
							{/* <div className="flex items-center space-x-2 text-sm text-gray-600"> */}
							{/* 	<Users size={16} /> */}
							{/* 	<span>{onlineUsers} online</span> */}
							{/* </div> */}
							<div className="flex items-center space-x-2 text-sm">
								<Circle
									size={8}
									className={`fill-current ${getConnectionStatusColor()}`}
								/>
								<span className={getConnectionStatusColor()}>
									{`${username} ${connectionStatus}`}
								</span>
							</div>
						</div>
					</div>
				</div>
			</div>

			{/* Chat Container */}
			<div className="max-w-4xl mx-auto p-4 h-[calc(100vh-80px)] flex flex-col">
				{/* Messages Area */}
				<div className="flex-1 bg-white rounded-lg shadow-sm border border-gray-200 mb-4 flex flex-col overflow-y-auto">
					<div className="flex-1 overflow-y-auto p-4 space-y-4">
						{messages.length === 0 ? (
							<div className="text-center text-gray-500 py-8">
								<p>No messages yet. Start the conversation!</p>
							</div>
						) : (
							messages.map((msg: Message) => (
								<div
									key={msg.id}
									className={`flex ${msg.isOwn ? "justify-end" : "justify-start"}`}
								>
									<div
										className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
											msg.isSystem
												? "bg-gray-100 text-gray-600 text-center text-sm italic"
												: msg.isOwn
													? "bg-blue-600 text-white"
													: "bg-gray-100 text-gray-900"
										}`}
									>
										{!msg.isSystem && !msg.isOwn && (
											<p className="text-xs font-semibold mb-1 opacity-75">
												{msg.sender}
											</p>
										)}
										<p className="text-sm">{msg.text}</p>
										<p
											className={`text-xs mt-1 ${
												msg.isOwn ? "text-blue-100" : "text-gray-500"
											}`}
										>
											{formatTime(msg.timestamp)}
										</p>
									</div>
								</div>
							))
						)}
						<div ref={messagesEndRef} />
					</div>
				</div>

				{/* Message Input */}
				<div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
					<div className="flex space-x-2">
						<input
							type="text"
							value={message}
							onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
								setMessage(e.target.value)
							}
							placeholder="Type your message..."
							className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
							disabled={connectionStatus !== "Connected"}
							maxLength={500}
							onKeyPress={(e) => handleInputKeyPress(e, "send")}
						/>
						<button
							onClick={handleSendMessage}
							disabled={!message.trim() || connectionStatus !== "Connected"}
							className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
						>
							<Send size={20} />
						</button>
					</div>
					<div className="flex items-center justify-between mt-2 text-xs text-gray-500">
						<span>Chatting as: {username}</span>
						<button
							onClick={handleChangeUsername}
							className="text-blue-600 hover:text-blue-700"
						>
							Change username
						</button>
					</div>
				</div>
			</div>
		</div>
	);
}
