
import socket                          
import json
import threading
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog, messagebox
import re
import time
import io
import os

# Define piece unicode symbols
UNICODE_PIECES = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'
}

class ChessClientGUI:
    def __init__(self, root, host='localhost', port=5555, chat_port=None):
        self.root = root
        self.root.title("Chess Client")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # Network settings
        self.host = host
        self.port = port
        self.chat_port = chat_port or port + 1  # Use port+1 for chat by default
        self.game_socket = None
        self.chat_socket = None
        self.client_id = None
        self.username = None
        self.game_id = None
        self.color = None
        self.last_game_state = None
        self.receive_buffer = ""
        self.board_fen = None
        self.current_turn = None
        self.your_turn = False
        self.legal_moves = []
        self.is_connected = False
        self.selected_square = None
        self.valid_targets = []
        self.current_lobby_id = None
        self.lobby_ids = []  # Store lobby IDs for selection
        self.in_chat = False
        
        # Set up the main frame structure
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the main UI structure"""
        # Create main frames
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left section for game controls and lobby
        self.left_frame = ttk.Frame(self.main_frame)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        # Center section for chess board
        self.center_frame = ttk.Frame(self.main_frame)
        self.center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Right section for chat and game info
        self.right_frame = ttk.Frame(self.main_frame)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        # Set up each section
        self.setup_left_section()
        self.setup_center_section()
        self.setup_right_section()
        
        # Status bar at the bottom
        self.status_bar = ttk.Label(self.root, text="Not connected", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Ask for username
        self.root.after(100, self.prompt_for_username)
        
    def setup_left_section(self):
        """Set up the left side of the UI - connection and lobby controls"""
        # Connection frame
        connection_frame = ttk.LabelFrame(self.left_frame, text="Connection")
        connection_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Server settings
        ttk.Label(connection_frame, text="Server:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.server_entry = ttk.Entry(connection_frame, width=15)
        self.server_entry.insert(0, self.host)
        self.server_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        ttk.Label(connection_frame, text="Port:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.port_entry = ttk.Entry(connection_frame, width=15)
        self.port_entry.insert(0, str(self.port))
        self.port_entry.grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
        
        ttk.Label(connection_frame, text="Username:").grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
        self.username_entry = ttk.Entry(connection_frame, width=15)
        self.username_entry.grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
        
        self.connect_button = ttk.Button(connection_frame, text="Connect", command=self.handle_connect)
        self.connect_button.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        
        # Lobby frame
        lobby_frame = ttk.LabelFrame(self.left_frame, text="Lobby")
        lobby_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.create_lobby_button = ttk.Button(lobby_frame, text="Create Lobby", command=self.create_lobby, state=tk.DISABLED)
        self.create_lobby_button.pack(fill=tk.X, padx=5, pady=5)
        
        self.list_lobbies_button = ttk.Button(lobby_frame, text="List Lobbies", command=self.list_lobbies, state=tk.DISABLED)
        self.list_lobbies_button.pack(fill=tk.X, padx=5, pady=5)
        
        self.lobbies_frame = ttk.Frame(lobby_frame)
        self.lobbies_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.lobbies_listbox = tk.Listbox(self.lobbies_frame, selectmode=tk.SINGLE)
        self.lobbies_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        lobbies_scrollbar = ttk.Scrollbar(self.lobbies_frame, orient=tk.VERTICAL, command=self.lobbies_listbox.yview)
        lobbies_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.lobbies_listbox.config(yscrollcommand=lobbies_scrollbar.set)
        
        # Lobby action buttons
        lobby_actions_frame = ttk.Frame(lobby_frame)
        lobby_actions_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.join_lobby_button = ttk.Button(lobby_actions_frame, text="Join Selected", command=self.join_selected_lobby, state=tk.DISABLED)
        self.join_lobby_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=5)
        
        self.start_game_button = ttk.Button(lobby_actions_frame, text="Start Game", command=self.start_game, state=tk.DISABLED)
        self.start_game_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=5)
        
        # Spectate frame
        spectate_frame = ttk.LabelFrame(self.left_frame, text="Spectate")
        spectate_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(spectate_frame, text="Game ID:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.game_id_entry = ttk.Entry(spectate_frame, width=8)
        self.game_id_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        self.spectate_button = ttk.Button(spectate_frame, text="Spectate", command=self.spectate_game, state=tk.DISABLED)
        self.spectate_button.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
    
    def setup_center_section(self):
        """Set up the center section with the chess board"""
        # Game info frame
        self.game_info_frame = ttk.Frame(self.center_frame)
        self.game_info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Game ID display (selectable text)
        self.game_id_frame = ttk.Frame(self.game_info_frame)
        self.game_id_frame.pack(fill=tk.X, pady=2)
        
        self.game_id_label = ttk.Label(self.game_id_frame, text="Game ID:", font=("Arial", 10, "bold"))
        self.game_id_label.pack(side=tk.LEFT, padx=5)
        
        # Entry widget to make the game ID selectable and copyable
        self.game_id_display = tk.Entry(self.game_id_frame, width=40, font=("Arial", 10))
        self.game_id_display.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.game_id_display.config(state="readonly", readonlybackground="white")
        
        # Copy button
        self.copy_id_button = ttk.Button(self.game_id_frame, text="Copy", width=8, command=self.copy_game_id)
        self.copy_id_button.pack(side=tk.RIGHT, padx=5)
        
        # Player black info
        self.black_frame = ttk.Frame(self.game_info_frame)
        self.black_frame.pack(fill=tk.X, pady=2)
        
        self.black_name = ttk.Label(self.black_frame, text="Black: -", font=("Arial", 12))
        self.black_name.pack(side=tk.LEFT, padx=5)
        
        self.black_time = ttk.Label(self.black_frame, text="10:00", font=("Arial", 12))
        self.black_time.pack(side=tk.RIGHT, padx=5)
        
        # Chess board frame
        self.board_frame = ttk.Frame(self.center_frame, borderwidth=2, relief="solid")
        self.board_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create the chess board
        self.board_canvas = tk.Canvas(self.board_frame, bg="white")
        self.board_canvas.pack(fill=tk.BOTH, expand=True)
        self.board_canvas.bind("<Configure>", self.draw_board)
        self.board_canvas.bind("<Button-1>", self.board_click)
        
        # Player white info
        self.white_frame = ttk.Frame(self.game_info_frame)
        self.white_frame.pack(fill=tk.X, pady=2)
        
        self.white_name = ttk.Label(self.white_frame, text="White: -", font=("Arial", 12))
        self.white_name.pack(side=tk.LEFT, padx=5)
        
        self.white_time = ttk.Label(self.white_frame, text="10:00", font=("Arial", 12))
        self.white_time.pack(side=tk.RIGHT, padx=5)
        
        # Game controls
        self.game_controls_frame = ttk.Frame(self.center_frame)
        self.game_controls_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.resign_button = ttk.Button(self.game_controls_frame, text="Resign", command=self.resign, state=tk.DISABLED)
        self.resign_button.pack(side=tk.LEFT, padx=5)
        
        self.position_eval = ttk.Label(self.game_controls_frame, text="Position: Even", font=("Arial", 10))
        self.position_eval.pack(side=tk.RIGHT, padx=5)
        
        self.turn_label = ttk.Label(self.game_controls_frame, text="Turn: -", font=("Arial", 10))
        self.turn_label.pack(side=tk.RIGHT, padx=5)
        
    def setup_right_section(self):
        """Set up the right section with chat and game info"""
        # Game information frame
        game_info_frame = ttk.LabelFrame(self.right_frame, text="Game Information")
        game_info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.game_status = ttk.Label(game_info_frame, text="No active game", wraplength=250)
        self.game_status.pack(fill=tk.X, padx=5, pady=5)
        
        # Move history frame
        move_history_frame = ttk.LabelFrame(self.right_frame, text="Move History")
        move_history_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.move_history = scrolledtext.ScrolledText(move_history_frame, width=30, height=10, wrap=tk.WORD, state='disabled')
        self.move_history.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Chat frame
        chat_frame = ttk.LabelFrame(self.right_frame, text="Chat")
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.chat_display = scrolledtext.ScrolledText(chat_frame, width=30, height=15, wrap=tk.WORD, state='disabled')
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        chat_input_frame = ttk.Frame(chat_frame)
        chat_input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.chat_entry = ttk.Entry(chat_input_frame)
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.chat_entry.bind("<Return>", self.send_chat_message)
        
        self.send_button = ttk.Button(chat_input_frame, text="Send", command=self.send_chat_message, state=tk.DISABLED)
        self.send_button.pack(side=tk.RIGHT)
    
    def prompt_for_username(self):
        """Prompt user for username"""
        username = simpledialog.askstring("Username", "Enter your username:", parent=self.root)
        if username:
            self.username_entry.delete(0, tk.END)
            self.username_entry.insert(0, username)
    
    def handle_connect(self):
        """Handle connection to server"""
        # Get connection details
        host = self.server_entry.get()
        try:
            port = int(self.port_entry.get())
            chat_port = port + 1  # Chat port is game port + 1
        except ValueError:
            messagebox.showerror("Error", "Port must be a number")
            return
        
        username = self.username_entry.get()
        if not username:
            messagebox.showerror("Error", "Username cannot be empty")
            return
        
        # Update network settings
        self.host = host
        self.port = port
        self.chat_port = chat_port
        self.username = username
        
        # Try to connect
        if self.connect():
            self.status_bar.config(text=f"Connected to {host}:{port} as {username}")
            self.connect_button.config(text="Disconnect", command=self.disconnect)
            self.enable_lobby_buttons()
        else:
            messagebox.showerror("Connection Error", f"Failed to connect to {host}:{port}")
    
    def connect(self):
        """Connect to the chess server"""
        try:
            self.game_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.game_socket.connect((self.host, self.port))
            
            # Send initial data with username
            initial_data = {'username': self.username}
            self.send_game_message(initial_data)
            
            # Start listening for game messages
            listen_thread = threading.Thread(target=self.listen_for_game_messages)
            listen_thread.daemon = True
            listen_thread.start()
            
            self.is_connected = True
            return True
        except Exception as e:
            print(f"Failed to connect to game server: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the server"""
        try:
            if self.game_socket:
                self.game_socket.close()
            if self.chat_socket:
                self.chat_socket.close()
            
            self.status_bar.config(text="Disconnected")
            self.connect_button.config(text="Connect", command=self.handle_connect)
            self.disable_all_buttons()
            self.is_connected = False
            self.in_chat = False
            
            # Reset game and chat variables
            self.client_id = None
            self.game_id = None
            self.color = None
            self.last_game_state = None
            self.board_fen = None
            self.current_lobby_id = None
            self.chat_socket = None
            self.game_socket = None
            self.game_status.config(text="No active game")
            
            # Clear game ID display
            self.update_game_id_display("")
            
            # Clear move history and chat
            self.clear_move_history()
            self.clear_chat()
            
            # Redraw empty board
            self.draw_board()
        except Exception as e:
            print(f"Error disconnecting: {e}")
    
    def enable_lobby_buttons(self):
        """Enable lobby-related buttons after connecting"""
        self.create_lobby_button.config(state=tk.NORMAL)
        self.list_lobbies_button.config(state=tk.NORMAL)
        self.join_lobby_button.config(state=tk.NORMAL)
        self.spectate_button.config(state=tk.NORMAL)
    
    def disable_all_buttons(self):
        """Disable all action buttons"""
        self.create_lobby_button.config(state=tk.DISABLED)
        self.list_lobbies_button.config(state=tk.DISABLED)
        self.join_lobby_button.config(state=tk.DISABLED)
        self.start_game_button.config(state=tk.DISABLED)
        self.spectate_button.config(state=tk.DISABLED)
        self.resign_button.config(state=tk.DISABLED)
        self.send_button.config(state=tk.DISABLED)
    
    # Network related functions
    def connect_to_chat(self, is_lobby=False, is_game=False):
        """Connect to the chat server"""
        # Check if we have the necessary information
        if not self.client_id:
            self.add_to_chat("System", "Not connected to server")
            return False
            
        if is_game and not self.game_id:
            self.add_to_chat("System", "Not in a game")
            return False
            
        if is_lobby and not self.current_lobby_id:
            self.add_to_chat("System", "Not in a lobby")
            return False
            
        if not is_game and not is_lobby:
            if self.game_id:
                is_game = True
            elif self.current_lobby_id:
                is_lobby = True
            else:
                self.add_to_chat("System", "Must be in a game or lobby to chat")
                return False
        
        try:
            # Close any existing chat connection
            if self.chat_socket:
                try:
                    self.chat_socket.close()
                except:
                    pass
                    
            self.chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.chat_socket.connect((self.host, self.chat_port))  # Use the chat port
            
            # Send initial data
            initial_data = {
                'client_id': self.client_id
            }
            
            if is_game:
                initial_data['type'] = 'game_chat'
                initial_data['game_id'] = self.game_id
                self.add_to_chat("System", f"Connected to game chat for game {self.game_id}")
            elif is_lobby:
                initial_data['type'] = 'lobby_chat'
                initial_data['lobby_id'] = self.current_lobby_id
                self.add_to_chat("System", f"Connected to lobby chat for lobby {self.current_lobby_id}")
                
            self.send_chat_message_to_server(initial_data)
            
            # Start listening for chat messages
            chat_thread = threading.Thread(target=self.listen_for_chat_messages)
            chat_thread.daemon = True
            chat_thread.start()
            
            self.send_button.config(state=tk.NORMAL)
            self.in_chat = True
            
            return True
        except ConnectionRefusedError:
            error_msg = f"Failed to connect to chat server. Make sure the server is running on port {self.chat_port}."
            print(error_msg)
            self.add_to_chat("System", error_msg)
            return False
        except Exception as e:
            print(f"Failed to connect to chat server: {e}")
            self.add_to_chat("System", f"Failed to connect to chat: {e}")
            return False
    
    def send_game_message(self, message):
        """Send a message to the game server"""
        try:
            data = json.dumps(message)
            self.game_socket.sendall(data.encode())
        except Exception as e:
            print(f"Failed to send game message: {e}")
            self.status_bar.config(text=f"Error: {e}")
    
    def send_chat_message_to_server(self, message):
        """Send a message to the chat server"""
        if not self.chat_socket:
            print("Not connected to chat")
            return
        
        try:
            data = json.dumps(message)
            self.chat_socket.sendall(data.encode())
        except Exception as e:
            print(f"Failed to send chat message: {e}")
    
    def extract_json_objects(self, text):
        """Find and extract valid JSON objects from text"""
        json_objects = []
        decoder = json.JSONDecoder()
        pos = 0
        
        while pos < len(text):
            try:
                obj, pos = decoder.raw_decode(text, pos)
                json_objects.append(obj)
            except json.JSONDecodeError:
                pos += 1  # Skip a character and try again
                
        return json_objects
    
    def listen_for_game_messages(self):
        """Listen for messages from the game server"""
        try:
            self.receive_buffer = ""
            while True:
                data = self.game_socket.recv(8192).decode('utf-8', errors='replace')
                if not data:
                    print("Disconnected from game server")
                    self.root.after(0, lambda: self.status_bar.config(text="Disconnected from server"))
                    break
                
                # Add received data to buffer
                self.receive_buffer += data
                
                # Extract valid JSON objects
                json_objects = self.extract_json_objects(self.receive_buffer)
                
                # Process each complete JSON object
                for obj in json_objects:
                    try:
                        # Use after() to handle UI updates from the main thread
                        self.root.after(0, lambda m=obj: self.handle_game_message(m))
                    except Exception as e:
                        print(f"Error handling message: {e}")
                
                # Clean buffer - remove processed valid JSON
                last_brace = self.receive_buffer.rfind('}')
                if last_brace >= 0:
                    self.receive_buffer = self.receive_buffer[last_brace+1:]
                    
                # Prevent buffer from growing too large
                if len(self.receive_buffer) > 10000:
                    print("Warning: Clearing large buffer with invalid data")
                    self.receive_buffer = ""
                
        except Exception as e:
            print(f"Game connection closed: {e}")
            self.root.after(0, lambda: self.status_bar.config(text=f"Connection error: {e}"))
        finally:
            self.root.after(0, lambda: self.connect_button.config(text="Connect", command=self.handle_connect))
            self.root.after(0, self.disable_all_buttons)
    
    def listen_for_chat_messages(self):
        """Listen for messages from the chat server"""
        try:
            chat_buffer = ""
            while True:
                try:
                    data = self.chat_socket.recv(4096).decode('utf-8', errors='replace')
                    if not data:
                        print("Disconnected from chat server")
                        self.root.after(0, lambda: self.add_to_chat("System", "Disconnected from chat"))
                        self.root.after(0, lambda: self.try_reconnect_chat())
                        break
                    
                    # Add received data to buffer
                    chat_buffer += data
                    
                    # Extract valid JSON objects
                    json_objects = self.extract_json_objects(chat_buffer)
                    
                    # Process each complete JSON object
                    for obj in json_objects:
                        try:
                            self.root.after(0, lambda m=obj: self.handle_chat_message(m))
                        except Exception as e:
                            print(f"Error handling chat message: {e}")
                    
                    # Clean buffer - remove processed valid JSON
                    last_brace = chat_buffer.rfind('}')
                    if last_brace >= 0:
                        chat_buffer = chat_buffer[last_brace+1:]
                        
                    # Prevent buffer from growing too large
                    if len(chat_buffer) > 10000:
                        chat_buffer = ""
                    
                except socket.timeout:
                    pass
                except Exception as e:
                    print(f"Error receiving from chat server: {e}")
                    self.root.after(0, lambda: self.try_reconnect_chat())
                    break
                    
        except Exception as e:
            print(f"Chat connection closed: {e}")
            self.root.after(0, lambda: self.add_to_chat("System", f"Chat error: {e}"))
            self.root.after(0, lambda: self.try_reconnect_chat())
        finally:
            self.chat_socket = None

    def try_reconnect_chat(self):
        """Try to reconnect to chat if disconnected but still in a game or lobby"""
        if not self.in_chat:
            if self.game_id:
                self.connect_to_chat(is_game=True)
            elif self.current_lobby_id:
                self.connect_to_chat(is_lobby=True)
            else:
                self.send_button.config(state=tk.DISABLED)
    
    def handle_game_message(self, message):
        """Process a message from the game server"""
        message_type = message.get('type')
        
        if message_type == 'connection_ack':
            self.client_id = message.get('client_id')
            self.status_bar.config(text=message.get('message', 'Connected to server'))
            
            # Clear game ID display
            self.update_game_id_display("")
        
        elif message_type == 'lobby_created':
            lobby_id = message.get('lobby_id')
            self.status_bar.config(text=f"Lobby created with ID: {lobby_id}")
            self.start_game_button.config(state=tk.NORMAL)
            # Store the current lobby ID
            self.current_lobby_id = lobby_id
            
            # Enable chat in lobby
            if not self.in_chat:
                self.connect_to_chat(is_lobby=True)
                
            # Clear game ID display
            self.update_game_id_display("")
        
        elif message_type == 'lobby_joined':
            lobby_id = message.get('lobby_id')
            self.status_bar.config(text=f"Joined lobby: {lobby_id}")
            # Store the current lobby ID
            self.current_lobby_id = lobby_id
            
            # Enable chat in lobby
            if not self.in_chat:
                self.connect_to_chat(is_lobby=True)
                
            # Clear game ID display
            self.update_game_id_display("")
        
        elif message_type == 'player_joined_lobby':
            player = message.get('player')
            self.status_bar.config(text=f"{player} joined your lobby")
        
        elif message_type == 'lobbies_list':
            lobbies = message.get('lobbies', [])
            self.lobbies_listbox.delete(0, tk.END)
            
            # Store lobby IDs for selection
            self.lobby_ids = []
            
            if not lobbies:
                self.lobbies_listbox.insert(tk.END, "No active lobbies")
            else:
                for lobby in lobbies:
                    lobby_id = lobby.get('lobby_id')
                    players = ", ".join(lobby.get('players', []))
                    count = lobby.get('player_count')
                    self.lobbies_listbox.insert(tk.END, f"{lobby_id} - {players} ({count}/2)")
                    # Store lobby ID for selection
                    self.lobby_ids.append(lobby_id)
        
        elif message_type == 'game_started':
            self.game_id = message.get('game_id')
            self.color = message.get('color', "")  # Default to empty string
            opponent = message.get('opponent', "Unknown")  # Default value
            color_display = self.color.capitalize() if self.color else "Unknown"
            game_msg = f"Game started! You are playing as {color_display} against {opponent}"
            
            self.game_status.config(text=game_msg)
            self.status_bar.config(text=f"Playing as {color_display}")
            self.resign_button.config(state=tk.NORMAL)
            
            # Update game ID display
            self.update_game_id_display(self.game_id)
            
            # Connect to chat for this game if not already connected
            if not self.in_chat:
                self.connect_to_chat(is_game=True)
                
        elif message_type == 'game_announcement':
            # New game announcement for spectating
            game_id = message.get('game_id')
            white_player = message.get('white_player')
            black_player = message.get('black_player')
            
            # Add to chat with spectate instructions
            announcement = f"New game started: {white_player} (White) vs {black_player} (Black)"
            self.add_to_chat("System", announcement)
            self.add_to_chat("System", f"Game ID for spectating: {game_id}")
            self.add_to_chat("System", "To spectate, enter the Game ID in the Spectate section and click 'Spectate'")
            
            # Pre-fill the game ID entry if not in a game
            if not self.game_id and not self.current_lobby_id:
                self.game_id_entry.delete(0, tk.END)
                self.game_id_entry.insert(0, game_id)
        
        elif message_type == 'game_state':
            self._update_game_state(message)
        
        elif message_type == 'game_over':
            result = message.get('result', '')
            winner = message.get('winner')
            message_text = message.get('message', '')
            
            self.game_status.config(text=f"Game Over: {message_text}")
            self.status_bar.config(text=f"Game ended: {result}")
            self.resign_button.config(state=tk.DISABLED)
            
            # Show dialog with results
            messagebox.showinfo("Game Over", message_text)
            
            # Reset game info but keep connection
            self.game_id = None
            self.color = None
            self.last_game_state = None
            self.your_turn = False
            self.enable_lobby_buttons()
            
            # Clear game ID display
            self.update_game_id_display("")
            
            # Disable chat when game ends unless in a lobby
            if not self.current_lobby_id:
                self.send_button.config(state=tk.DISABLED)
                self.in_chat = False
                if self.chat_socket:
                    try:
                        self.chat_socket.close()
                        self.chat_socket = None
                    except:
                        pass
        
        elif message_type == 'error':
            error_msg = message.get('message', 'Unknown error')
            self.status_bar.config(text=f"Error: {error_msg}")
            messagebox.showerror("Error", error_msg)
        
        elif message_type == 'spectating':
            self.game_id = message.get('game_id')
            white_player = message.get('white_player')
            black_player = message.get('black_player')
            
            self.game_status.config(text=f"Spectating: {white_player} vs {black_player}")
            self.status_bar.config(text=f"Spectating game {self.game_id}")
            
            # Update game ID display
            self.update_game_id_display(self.game_id)
            
            # Connect to chat
            if not self.in_chat:
                self.connect_to_chat(is_game=True)
                
        elif message_type == 'lobby_closed' or message_type == 'player_left_lobby':
            # Disable chat if lobby is closed or left
            if self.current_lobby_id and not self.game_id:
                self.send_button.config(state=tk.DISABLED)
                self.current_lobby_id = None
                self.in_chat = False
                if self.chat_socket:
                    try:
                        self.chat_socket.close()
                        self.chat_socket = None
                    except:
                        pass
    
    def _update_game_state(self, message):
        """Update the game state display"""
        # Create a hash of key game state elements to detect duplicates
        state_hash = self._create_game_state_hash(message)
            
        # Only process if it's a new state or if it's specifically your turn
        if state_hash != self.last_game_state or message.get('your_turn', False):
            self.last_game_state = state_hash
            
            # Extract game state data
            self.board_fen = message.get('board_fen')
            self.current_turn = message.get('turn', '')
            self.your_turn = message.get('your_turn', False)
            white_player = message.get('white_player', '')
            black_player = message.get('black_player', '')
            white_time = int(message.get('white_time', 0))
            black_time = int(message.get('black_time', 0))
            in_check = message.get('in_check', False)
            self.legal_moves = message.get('legal_moves', [])
            move_history = message.get('move_history', [])
            
            # Update player names and times
            self.white_name.config(text=f"White: {white_player}")
            self.black_name.config(text=f"Black: {black_player}")
            self.white_time.config(text=f"{white_time//60}:{white_time%60:02d}")
            self.black_time.config(text=f"{black_time//60}:{black_time%60:02d}")
            
            # Update turn information
            self.turn_label.config(text=f"Turn: {self.current_turn.capitalize()}")
            
            if self.your_turn:
                self.status_bar.config(text="Your turn to move")
            else:
                self.status_bar.config(text=f"Waiting for {self.current_turn}")
            
            # Position evaluation
            if self.board_fen:
                eval_text = self.evaluate_position(self.board_fen)
                self.position_eval.config(text=f"Position: {eval_text}")
            
            # Update move history
            if move_history:
                self.update_move_history(move_history)
            
            # Ensure chat is enabled during the game
            if self.game_id and not self.in_chat:
                self.connect_to_chat(is_game=True)
            
            # Show check status if applicable
            if in_check:
                check_str = "You are in check!" if self.your_turn else f"{self.current_turn.capitalize()} is in check!"
                messagebox.showinfo("Check", check_str)
            
            # Redraw the board
            self.draw_board()
    
    def handle_chat_message(self, message):
        """Process a message from the chat server"""
        message_type = message.get('type')
        
        if message_type == 'chat':
            sender = message.get('sender', 'Unknown')
            text = message.get('text', '')
            self.add_to_chat(sender, text)
            
        elif message_type == 'chat_connected':
            # Chat connection confirmed by server
            self.in_chat = True
            self.send_button.config(state=tk.NORMAL)
            self.add_to_chat("System", message.get('message', 'Connected to chat'))
            
        elif message_type == 'error':
            # Chat error message
            error_msg = message.get('message', 'Unknown error')
            self.add_to_chat("System", f"Error: {error_msg}")
            self.in_chat = False
            self.send_button.config(state=tk.DISABLED)
    
    def _create_game_state_hash(self, state):
        """Create a hash of the game state to detect duplicates"""
        hash_elements = [
            state.get('board_fen', ''),
            state.get('turn', ''),
            state.get('white_time', 0),
            state.get('black_time', 0)
        ]
        return hash("-".join(str(item) for item in hash_elements))
    
    # Game action functions
    def create_lobby(self):
        """Create a new game lobby"""
        if not self.is_connected:
            messagebox.showerror("Error", "Not connected to server")
            return
        
        self.send_game_message({'type': 'create_lobby'})
        # Chat connection will be established when lobby is created confirmation is received
    
    def list_lobbies(self):
        """Request a list of available lobbies"""
        if not self.is_connected:
            messagebox.showerror("Error", "Not connected to server")
            return
        
        self.send_game_message({'type': 'list_lobbies'})
    
    def join_selected_lobby(self):
        """Join the currently selected lobby"""
        selection = self.lobbies_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No lobby selected")
            return
        
        # Get lobby ID from the selection
        lobby_index = selection[0]
        if lobby_index >= len(self.lobby_ids):
            messagebox.showerror("Error", "Invalid lobby selection")
            return
            
        lobby_id = self.lobby_ids[lobby_index]
        self.send_game_message({'type': 'join_lobby', 'lobby_id': lobby_id})
        # Chat connection will be established when lobby join confirmation is received
    
    def start_game(self):
        """Start a game in the current lobby"""
        if not self.current_lobby_id:
            messagebox.showerror("Error", "Not in a lobby")
            return
        
        self.send_game_message({'type': 'start_game', 'lobby_id': self.current_lobby_id})
    
    def spectate_game(self):
        """Spectate a game by ID"""
        game_id = self.game_id_entry.get()
        if not game_id:
            messagebox.showerror("Error", "Please enter a game ID")
            return
        
        self.send_game_message({'type': 'spectate', 'game_id': game_id})
    
    def resign(self):
        """Resign the current game"""
        if not self.game_id:
            messagebox.showerror("Error", "Not in a game")
            return
        
        confirm = messagebox.askyesno("Confirm Resignation", "Are you sure you want to resign?")
        if confirm:
            self.send_game_message({'type': 'resign', 'game_id': self.game_id})
    
    def send_chat_message(self, event=None):
        """Send a chat message"""
        message = self.chat_entry.get()
        if not message:
            return
        
        if not self.chat_socket:
            self.add_to_chat("System", "Not connected to chat")
            return
        
        chat_data = {
            'type': 'chat',
            'text': message
        }

        if self.game_id:
            chat_data['game_id'] = self.game_id
        elif self.current_lobby_id:
            chat_data['lobby_id'] = self.current_lobby_id
        
        self.send_chat_message_to_server(chat_data)
        self.chat_entry.delete(0, tk.END)
    
    # UI Helper Functions
    def add_to_chat(self, sender, text):
        """Add a message to the chat display"""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"{sender}: {text}\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
    
    def clear_chat(self):
        """Clear the chat display"""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete(1.0, tk.END)
        self.chat_display.config(state=tk.DISABLED)
    
    def update_move_history(self, moves):
        """Update the move history display"""
        self.move_history.config(state=tk.NORMAL)
        self.move_history.delete(1.0, tk.END)
        
        # Format moves nicely
        for i, move in enumerate(moves):
            move_num = i // 2 + 1
            if i % 2 == 0:  # White's move
                self.move_history.insert(tk.END, f"{move_num}. {move} ")
            else:  # Black's move
                self.move_history.insert(tk.END, f"{move}\n")
        
        self.move_history.see(tk.END)
        self.move_history.config(state=tk.DISABLED)
    
    def clear_move_history(self):
        """Clear the move history display"""
        self.move_history.config(state=tk.NORMAL)
        self.move_history.delete(1.0, tk.END)
        self.move_history.config(state=tk.DISABLED)
    
    def evaluate_position(self, fen):
        """Simple position evaluator - real eval would use an engine"""
        # Count material difference as a basic evaluation
        piece_values = {'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 0,
                        'p': -1, 'n': -3, 'b': -3, 'r': -5, 'q': -9, 'k': 0}
        
        board_part = fen.split(' ')[0]
        score = 0
        
        for char in board_part:
            if char in piece_values:
                score += piece_values[char]
        
        # Format the evaluation
        if score > 0:
            return f"+{score}"
        elif score < 0:
            return f"{score}"
        else:
            return "Even"
    
    # Chess Board Related Functions
    def draw_board(self, event=None):
        """Draw the chess board on the canvas"""
        self.board_canvas.delete("all")
        
        # Calculate board dimensions
        canvas_width = self.board_canvas.winfo_width()
        canvas_height = self.board_canvas.winfo_height()
        
        # Make board square by using the smaller dimension
        size = min(canvas_width, canvas_height)
        self.square_size = size // 8
        
        # Center the board
        offset_x = (canvas_width - (self.square_size * 8)) // 2
        offset_y = (canvas_height - (self.square_size * 8)) // 2
        
        # Draw squares
        for row in range(8):
            for col in range(8):
                x1 = offset_x + col * self.square_size
                y1 = offset_y + row * self.square_size
                x2 = x1 + self.square_size
                y2 = y1 + self.square_size
                
                # Choose color: light squares are even, dark are odd
                color = "#EEEED2" if (row + col) % 2 == 0 else "#769656"
                
                # Check if this square is selected
                if self.selected_square == self._get_square_name(row, col):
                    color = "#BBCC44"  # Highlight selected square
                
                # Check if this square is a valid target
                elif self._get_square_name(row, col) in self.valid_targets:
                    color = "#AABBFF"  # Highlight valid move targets
                
                # Draw the square
                self.board_canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")
                
                # Add coordinate labels
                if col == 0:  # Rank numbers
                    rank = 8 - row if self.color != 'black' else row + 1
                    self.board_canvas.create_text(x1 + 5, y1 + 5, text=str(rank),
                                                 anchor=tk.NW, fill="#333333", font=("Arial", 8))
                
                if row == 7:  # File letters
                    file = chr(97 + col) if self.color != 'black' else chr(104 - col)
                    self.board_canvas.create_text(x2 - 5, y2 - 5, text=file,
                                                anchor=tk.SE, fill="#333333", font=("Arial", 8))
        
        # Draw pieces if we have a board state
        if self.board_fen:
            self._draw_pieces(offset_x, offset_y)
    
    def _draw_pieces(self, offset_x, offset_y):
        """Draw chess pieces on the board"""
        # Parse FEN into a board representation
        rows = self.board_fen.split('/') if '/' in self.board_fen else self.board_fen.split(' ')[0].split('/')
        
        # Adjust the order based on player color
        board_rows = rows if self.color != 'black' else list(reversed(rows))
        
        # Draw each piece
        for row_idx, row_data in enumerate(board_rows):
            col_idx = 0
            for char in row_data:
                if char.isdigit():
                    # Skip empty squares
                    col_idx += int(char)
                else:
                    # Draw piece
                    x = offset_x + (col_idx * self.square_size) + (self.square_size // 2)
                    y = offset_y + (row_idx * self.square_size) + (self.square_size // 2)
                    
                    # Adjust position if board is flipped for black
                    if self.color == 'black':
                        x = offset_x + ((7 - col_idx) * self.square_size) + (self.square_size // 2)
                    
                    # Get Unicode symbol for piece
                    piece_symbol = UNICODE_PIECES.get(char, '')
                    
                    if piece_symbol:
                        font_size = int(self.square_size * 0.8)
                        self.board_canvas.create_text(x, y, text=piece_symbol,
                                                    font=("Arial", font_size),
                                                    fill="#000000" if char.isupper() else "#000000")
                    
                    col_idx += 1
    
    def board_click(self, event):
        """Handle clicks on the chess board"""
        if not self.game_id or not self.your_turn:
            return  # Not in a game or not your turn
        
        # Calculate board dimensions and offsets
        canvas_width = self.board_canvas.winfo_width()
        canvas_height = self.board_canvas.winfo_height()
        
        size = min(canvas_width, canvas_height)
        square_size = size // 8
        
        offset_x = (canvas_width - (square_size * 8)) // 2
        offset_y = (canvas_height - (square_size * 8)) // 2
        
        # Calculate row and column
        col = (event.x - offset_x) // square_size
        row = (event.y - offset_y) // square_size
        
        # Adjust for black's perspective
        if self.color == 'black':
            col = 7 - col
            row = 7 - row
        
        # Ensure within board boundaries
        if not (0 <= row < 8 and 0 <= col < 8):
            return
        
        # Convert to algebraic notation
        square = self._get_square_name(row, col)
        
        # Handle piece selection or move
        if not self.selected_square:
            # Check if the clicked square has a legal move
            has_moves = any(move.startswith(square) for move in self.legal_moves)
            if has_moves:
                self.selected_square = square
                # Find valid target squares
                self.valid_targets = []
                for move in self.legal_moves:
                    if move.startswith(square):
                        target = move[2:4]  # e.g., "e2e4" -> "e4"
                        self.valid_targets.append(target)
                
                self.draw_board()  # Redraw to highlight selection
        else:
            # Trying to make a move
            move = f"{self.selected_square}{square}"
            
            # Check if this is a standard move or needs promotion
            is_promotion = False
            for legal_move in self.legal_moves:
                # Check if base move matches
                if legal_move.startswith(move):
                    # Check if it's a promotion move (has extra character)
                    if len(legal_move) > 4:
                        is_promotion = True
                        break
            
            if is_promotion:
                # Ask user for promotion piece
                promotion_pieces = ['q', 'r', 'n', 'b']
                promotion = simpledialog.askstring(
                    "Promotion", 
                    "Choose promotion piece (q=Queen, r=Rook, n=Knight, b=Bishop):",
                    parent=self.root
                )
                
                if promotion and promotion.lower() in promotion_pieces:
                    move += promotion.lower()
                else:
                    # Default to queen if invalid or canceled
                    move += 'q'
            
            # Check if move is legal
            for legal_move in self.legal_moves:
                if legal_move.startswith(move):
                    # Send move to server
                    self.send_game_message({
                        'type': 'move',
                        'game_id': self.game_id,
                        'move': move
                    })
                    
                    # Clear selection
                    self.selected_square = None
                    self.valid_targets = []
                    self.draw_board()
                    return
            
            # If we got here, either:
            # 1. The move was not legal
            # 2. User clicked another of their pieces to select it instead
            
            # Check if new square is a valid starting square
            has_moves = any(move.startswith(square) for move in self.legal_moves)
            if has_moves:
                self.selected_square = square
                # Find valid target squares
                self.valid_targets = []
                for move in self.legal_moves:
                    if move.startswith(square):
                        target = move[2:4]  # e.g., "e2e4" -> "e4"
                        self.valid_targets.append(target)
            else:
                # Clear selection if clicking invalid target
                self.selected_square = None
                self.valid_targets = []
            
            self.draw_board()  # Redraw board
    
    def _get_square_name(self, row, col):
        """Convert row and column to algebraic notation (e.g., 'e4')"""
        file = chr(97 + col)  # 'a' through 'h'
        rank = 8 - row  # 1 through 8
        return f"{file}{rank}"

    def copy_game_id(self):
        """Copy the game ID to clipboard"""
        game_id = self.game_id_display.get()
        if game_id:
            self.root.clipboard_clear()
            self.root.clipboard_append(game_id)
            self.add_to_chat("System", "Game ID copied to clipboard")

    def update_game_id_display(self, game_id):
        """Update the game ID display with the provided ID"""
        # Enable the entry to update its contents
        self.game_id_display.config(state=tk.NORMAL)
        # Clear and set the new value
        self.game_id_display.delete(0, tk.END)
        self.game_id_display.insert(0, game_id)
        # Set back to readonly state
        self.game_id_display.config(state="readonly")
        
        # Update button state
        if game_id:
            self.copy_id_button.config(state=tk.NORMAL)
        else:
            self.copy_id_button.config(state=tk.DISABLED)

def main():
    root = tk.Tk()
    app = ChessClientGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
