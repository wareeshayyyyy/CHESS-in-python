
import socket
import threading
import json
import uuid
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
import chess
import queue
import datetime
import os
import signal
import sys

class ChessGame:
    def __init__(self, game_id, white_player, black_player, time_control=600):
        self.game_id = game_id
        self.white_player = white_player
        self.black_player = black_player
        self.white_time = time_control
        self.black_time = time_control
        self.board = chess.Board()
        self.last_move_time = time.time()
        self.move_history = []
        self.is_active = True
        self.spectators = set()
        self.time_control = time_control
        
    def make_move(self, move_uci):
        # Check if move is legal
        try:
            move = chess.Move.from_uci(move_uci)
            if move not in self.board.legal_moves:
                return False, "Illegal move"
            
            # Update timers
            current_time = time.time()
            elapsed = current_time - self.last_move_time
            
            if self.board.turn == chess.WHITE:
                self.white_time -= int(elapsed)
                if self.white_time <= 0:
                    self.white_time = 0
                    return False, "White ran out of time"
            else:
                self.black_time -= int(elapsed)
                if self.black_time <= 0:
                    self.black_time = 0
                    return False, "Black ran out of time"
            
            # Make the move
            san_move = self.board.san(move)
            self.board.push(move)
            self.move_history.append(san_move)
            self.last_move_time = current_time
            
            return True, None
        except Exception as e:
            return False, str(e)
    
    def get_state(self, for_client=None):
        """Get the current game state"""
        turn = "white" if self.board.turn == chess.WHITE else "black"
        
        # Determine if the player is in check
        in_check = self.board.is_check()
        
        # Generate legal moves for the current player
        legal_moves = []
        for move in self.board.legal_moves:
            legal_moves.append(move.uci())
        
        # Determine if this is a specific player's turn
        your_turn = False
        if for_client:
            if turn == "white" and for_client == self.white_player:
                your_turn = True
            elif turn == "black" and for_client == self.black_player:
                your_turn = True
        
        # Check for game over conditions
        game_over = False
        result = None
        winner = None
        if self.board.is_checkmate():
            game_over = True
            result = "checkmate"
            winner = "black" if self.board.turn == chess.WHITE else "white"
        elif self.board.is_stalemate():
            game_over = True
            result = "stalemate"
        elif self.board.is_insufficient_material():
            game_over = True
            result = "insufficient material"
        elif self.board.is_fifty_moves():
            game_over = True
            result = "fifty-move rule"
        elif self.board.is_repetition():
            game_over = True
            result = "threefold repetition"
        
        # Create the state object
        state = {
            'type': 'game_state',
            'game_id': self.game_id,
            'board_fen': self.board.fen(),
            'turn': turn,
            'your_turn': your_turn,
            'in_check': in_check,
            'legal_moves': legal_moves,
            'white_player': self.white_player.username if self.white_player else "?",
            'black_player': self.black_player.username if self.black_player else "?",
            'white_time': self.white_time,
            'black_time': self.black_time,
            'move_history': self.move_history
        }
        
        # If game is over, add that information
        if game_over:
            state['game_over'] = True
            state['result'] = result
            state['winner'] = winner
        
        return state
    
    def is_player(self, client):
        """Check if client is a player in this game"""
        return client == self.white_player or client == self.black_player
    
    def get_opponent(self, client):
        """Get the opponent of the given client"""
        if client == self.white_player:
            return self.black_player
        elif client == self.black_player:
            return self.white_player
        return None
    
    def add_spectator(self, client):
        """Add a spectator to the game"""
        self.spectators.add(client)
    
    def remove_spectator(self, client):
        """Remove a spectator from the game"""
        if client in self.spectators:
            self.spectators.remove(client)
            
    def get_all_participants(self):
        """Get all participants (players and spectators)"""
        participants = set()
        if self.white_player:
            participants.add(self.white_player)
        if self.black_player:
            participants.add(self.black_player)
        participants.update(self.spectators)
        return participants

class GameLobby:
    def __init__(self, lobby_id, host):
        self.lobby_id = lobby_id
        self.players = [host]
        self.max_players = 2
        self.status = "waiting"  # waiting, full, playing
    
    def add_player(self, player):
        """Add a player to the lobby if there's space"""
        if len(self.players) < self.max_players:
            self.players.append(player)
            if len(self.players) == self.max_players:
                self.status = "full"
            return True
        return False
    
    def remove_player(self, player):
        """Remove a player from the lobby"""
        if player in self.players:
            self.players.remove(player)
            self.status = "waiting"
            return True
        return False
    
    def is_full(self):
        """Check if the lobby is full"""
        return len(self.players) == self.max_players
    
    def get_players(self):
        """Get the current players in the lobby"""
        return self.players
    
    def get_player_count(self):
        """Get the number of players in the lobby"""
        return len(self.players)

class ChessClient:
    def __init__(self, client_socket, address, server):
        self.socket = client_socket
        self.address = address
        self.server = server
        self.username = None
        self.client_id = str(uuid.uuid4())
        self.current_game = None
        self.current_lobby = None
        self.is_authenticated = False
        self.last_activity = time.time()
        
    def authenticate(self, username):
        """Set the username and mark as authenticated"""
        self.username = username
        self.is_authenticated = True
        
    def send(self, message):
        """Send a message to the client"""
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
            self.socket.sendall(message.encode())
            self.last_activity = time.time()
            return True
        except Exception as e:
            self.server.log(f"Error sending to {self.username}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect the client from the server"""
        try:
            self.socket.close()
        except:
            pass
        
        # Remove from any game or lobby
        if self.current_game:
            self.server.handle_player_leave_game(self)
        if self.current_lobby:
            self.server.handle_player_leave_lobby(self)
    
    def __str__(self):
        return f"{self.username}({self.client_id})"

class ChatClient:
    def __init__(self, socket, address, server):
        self.socket = socket
        self.address = address
        self.server = server
        self.game_id = None
        self.lobby_id = None
        self.client_id = None
        self.game_client = None  # Reference to the associated game client
        
    def send(self, message):
        """Send a message to the client"""
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
            self.socket.sendall(message.encode())
            return True
        except Exception as e:
            self.server.log(f"Error sending chat to client: {e}")
            return False
    
    def disconnect(self):
        """Disconnect the client from the chat server"""
        try:
            self.socket.close()
        except:
            pass

class ChessServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Chess Server")
        self.root.geometry("1000x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Server configuration
        self.game_port = 5555
        self.chat_port = 5556
        
        # Server state
        self.clients = {}  # client_id -> ChessClient
        self.chat_clients = {}  # client_id -> ChatClient
        self.games = {}  # game_id -> ChessGame
        self.lobbies = {}  # lobby_id -> GameLobby
        
        # Server sockets
        self.game_socket = None
        self.chat_socket = None
        
        # Threading
        self.running = False
        self.threads = []
        self.log_queue = queue.Queue()
        
        # Setup UI
        self.setup_ui()
        
        # Start processing logs
        self.process_logs()
    
    def setup_ui(self):
        """Set up the user interface"""
        # Create main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel - server controls and status
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        # Server settings frame
        settings_frame = ttk.LabelFrame(left_frame, text="Server Settings")
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Game port
        ttk.Label(settings_frame, text="Game Port:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.game_port_entry = ttk.Entry(settings_frame, width=6)
        self.game_port_entry.insert(0, str(self.game_port))
        self.game_port_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Chat port
        ttk.Label(settings_frame, text="Chat Port:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.chat_port_entry = ttk.Entry(settings_frame, width=6)
        self.chat_port_entry.insert(0, str(self.chat_port))
        self.chat_port_entry.grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Server control buttons
        control_frame = ttk.Frame(left_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.start_button = ttk.Button(control_frame, text="Start Server", command=self.start_server)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.stop_button = ttk.Button(control_frame, text="Stop Server", command=self.stop_server, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Server statistics
        stats_frame = ttk.LabelFrame(left_frame, text="Server Statistics")
        stats_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(stats_frame, text="Status:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.status_label = ttk.Label(stats_frame, text="Offline")
        self.status_label.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        ttk.Label(stats_frame, text="Connected clients:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.clients_label = ttk.Label(stats_frame, text="0")
        self.clients_label.grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
        
        ttk.Label(stats_frame, text="Active games:").grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
        self.games_label = ttk.Label(stats_frame, text="0")
        self.games_label.grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
        
        ttk.Label(stats_frame, text="Open lobbies:").grid(row=3, column=0, padx=5, pady=2, sticky=tk.W)
        self.lobbies_label = ttk.Label(stats_frame, text="0")
        self.lobbies_label.grid(row=3, column=1, padx=5, pady=2, sticky=tk.W)
        
        # Connected clients
        clients_frame = ttk.LabelFrame(left_frame, text="Connected Clients")
        clients_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.clients_list = tk.Listbox(clients_frame)
        self.clients_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        clients_scrollbar = ttk.Scrollbar(clients_frame, orient=tk.VERTICAL, command=self.clients_list.yview)
        clients_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.clients_list.config(yscrollcommand=clients_scrollbar.set)
        
        # Right panel - logs and game status
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Server logs
        log_frame = ttk.LabelFrame(right_frame, text="Server Logs")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_display = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD)
        self.log_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Active games frame
        active_games_frame = ttk.LabelFrame(right_frame, text="Active Games")
        active_games_frame.pack(fill=tk.X, padx=5, pady=5)
        
        games_listbox_frame = ttk.Frame(active_games_frame)
        games_listbox_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.games_listbox = tk.Listbox(games_listbox_frame, height=5)
        self.games_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        games_scrollbar = ttk.Scrollbar(games_listbox_frame, orient=tk.VERTICAL, command=self.games_listbox.yview)
        games_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.games_listbox.config(yscrollcommand=games_scrollbar.set)
        
        # Status bar
        self.status_bar = ttk.Label(self.root, text="Server offline", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def start_server(self):
        """Start the chess server"""
        try:
            # Get port settings
            game_port = int(self.game_port_entry.get())
            chat_port = int(self.chat_port_entry.get())
            
            # Update server settings
            self.game_port = game_port
            self.chat_port = chat_port
            
            # Create server sockets
            self.game_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.game_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.game_socket.bind(('0.0.0.0', self.game_port))
            self.game_socket.listen(5)
            
            self.chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.chat_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.chat_socket.bind(('0.0.0.0', self.chat_port))
            self.chat_socket.listen(5)
            
            # Update UI
            self.status_label.config(text="Online")
            self.status_bar.config(text=f"Server running on ports {self.game_port} (game) and {self.chat_port} (chat)")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            # Start server threads
            self.running = True
            
            # Game connection thread
            game_thread = threading.Thread(target=self.handle_game_connections)
            game_thread.daemon = True
            game_thread.start()
            self.threads.append(game_thread)
            
            # Chat connection thread
            chat_thread = threading.Thread(target=self.handle_chat_connections)
            chat_thread.daemon = True
            chat_thread.start()
            self.threads.append(chat_thread)
            
            # Timer thread for game clocks, etc.
            timer_thread = threading.Thread(target=self.timer_loop)
            timer_thread.daemon = True
            timer_thread.start()
            self.threads.append(timer_thread)
            
            self.log("Server started successfully")
        except Exception as e:
            self.log(f"Failed to start server: {e}")
            self.status_label.config(text="Error")
            self.status_bar.config(text=f"Error starting server: {e}")
    
    def stop_server(self):
        """Stop the chess server"""
        self.running = False
        
        # Close all client connections
        for client_id, client in list(self.clients.items()):
            client.disconnect()
        
        for client_id, client in list(self.chat_clients.items()):
            client.disconnect()
        
        # Close server sockets
        if self.game_socket:
            self.game_socket.close()
            self.game_socket = None
            
        if self.chat_socket:
            self.chat_socket.close()
            self.chat_socket = None
        
        # Update UI
        self.status_label.config(text="Offline")
        self.status_bar.config(text="Server offline")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        # Clear lists
        self.clients_list.delete(0, tk.END)
        self.games_listbox.delete(0, tk.END)
        
        # Reset server state
        self.clients = {}
        self.chat_clients = {}
        self.games = {}
        self.lobbies = {}
        
        self.update_stats()
        self.log("Server stopped")
    
    def handle_game_connections(self):
        """Accept and handle game client connections"""
        self.log("Listening for game connections")
        self.game_socket.settimeout(1.0)  # Set a timeout to allow checking if we should stop
        
        while self.running:
            try:
                client_socket, address = self.game_socket.accept()
                self.log(f"New game connection from {address[0]}:{address[1]}")
                
                # Create client instance
                client = ChessClient(client_socket, address, self)
                
                # Add to clients dictionary
                self.clients[client.client_id] = client
                
                # Start a thread to handle this client
                client_thread = threading.Thread(target=self.handle_game_client, args=(client,))
                client_thread.daemon = True
                client_thread.start()
                self.threads.append(client_thread)
                
                # Update UI
                self.update_stats()
                
            except socket.timeout:
                pass  # This is expected due to the timeout
            except Exception as e:
                if self.running:  # Only log if we're still supposed to be running
                    self.log(f"Error accepting game connection: {e}")
    
    def handle_chat_connections(self):
        """Accept and handle chat client connections"""
        self.log("Listening for chat connections")
        self.chat_socket.settimeout(1.0)  # Set a timeout to allow checking if we should stop
        
        while self.running:
            try:
                client_socket, address = self.chat_socket.accept()
                self.log(f"New chat connection from {address[0]}:{address[1]}")
                
                # Create chat client instance
                chat_client = ChatClient(client_socket, address, self)
                
                # Start a thread to handle this chat client
                chat_thread = threading.Thread(target=self.handle_chat_client, args=(chat_client,))
                chat_thread.daemon = True
                chat_thread.start()
                self.threads.append(chat_thread)
                
            except socket.timeout:
                pass  # This is expected due to the timeout
            except Exception as e:
                if self.running:  # Only log if we're still supposed to be running
                    self.log(f"Error accepting chat connection: {e}")
    
    def handle_game_client(self, client):
        """Handle communication with a game client"""
        try:
            buffer = ""
            while self.running:
                try:
                    data = client.socket.recv(4096).decode('utf-8', errors='replace')
                    if not data:
                        self.log(f"Client {client.username or client.client_id[:8]} disconnected")
                        break
                    
                    buffer += data
                    
                    # Process complete JSON messages
                    while True:
                        # Find a complete JSON object
                        json_end = buffer.find('}')
                        if json_end == -1:
                            break
                        
                        # Extract JSON
                        try:
                            # Try to find the start of the JSON object
                            json_start = buffer.find('{')
                            if json_start == -1:
                                # No start brace found, clear buffer and break
                                buffer = ""
                                break
                                
                            # Extract and parse JSON
                            json_str = buffer[json_start:json_end+1]
                            message = json.loads(json_str)
                            
                            # Process the message
                            self.process_game_message(client, message)
                            
                            # Remove processed JSON from buffer
                            buffer = buffer[json_end+1:]
                            
                        except json.JSONDecodeError:
                            # Invalid JSON, try to find the next complete object
                            buffer = buffer[json_end+1:]
                        except Exception as e:
                            self.log(f"Error processing message from {client.username or client.client_id[:8]}: {e}")
                            buffer = buffer[json_end+1:]
                
                except socket.timeout:
                    # Check if client hasn't sent any messages in a while
                    if time.time() - client.last_activity > 300:  # 5 minutes
                        self.log(f"Client {client.username or client.client_id[:8]} timed out")
                        break
                except Exception as e:
                    self.log(f"Error receiving from {client.username or client.client_id[:8]}: {e}")
                    break
                    
        except Exception as e:
            self.log(f"Error handling client {client.client_id[:8]}: {e}")
        finally:
            # Clean up when client disconnects
            self.handle_client_disconnect(client)
    
    def handle_chat_client(self, chat_client):
        """Handle communication with a chat client"""
        try:
            buffer = ""
            while self.running:
                try:
                    data = chat_client.socket.recv(4096).decode('utf-8', errors='replace')
                    if not data:
                        self.log(f"Chat client disconnected")
                        break
                    
                    buffer += data
                    
                    # Process complete JSON messages
                    while True:
                        # Find a complete JSON object
                        json_end = buffer.find('}')
                        if json_end == -1:
                            break
                        
                        # Extract JSON
                        try:
                            # Try to find the start of the JSON object
                            json_start = buffer.find('{')
                            if json_start == -1:
                                # No start brace found, clear buffer and break
                                buffer = ""
                                break
                                
                            # Extract and parse JSON
                            json_str = buffer[json_start:json_end+1]
                            message = json.loads(json_str)
                            
                            # Process the message
                            self.process_chat_message(chat_client, message)
                            
                            # Remove processed JSON from buffer
                            buffer = buffer[json_end+1:]
                            
                        except json.JSONDecodeError:
                            # Invalid JSON, try to find the next complete object
                            buffer = buffer[json_end+1:]
                        except Exception as e:
                            self.log(f"Error processing chat message: {e}")
                            buffer = buffer[json_end+1:]
                
                except socket.timeout:
                    pass
                except Exception as e:
                    self.log(f"Error receiving from chat client: {e}")
                    break
                    
        except Exception as e:
            self.log(f"Error handling chat client: {e}")
        finally:
            # Clean up when chat client disconnects
            self.handle_chat_client_disconnect(chat_client)
    
    def process_game_message(self, client, message):
        """Process a message from a game client"""
        message_type = message.get('type', '')
        
        # First message should include username
        if not client.is_authenticated:
            username = message.get('username')
            if username:
                client.authenticate(username)
                
                # Send acknowledgement
                client.send({
                    'type': 'connection_ack',
                    'client_id': client.client_id,
                    'message': f"Connected as {username}"
                })
                
                self.log(f"Client authenticated as {username}")
                self.update_clients_list()
                return
            else:
                # Disconnect clients that don't provide a username
                client.send({'type': 'error', 'message': 'Username required'})
                client.disconnect()
                return
        
        # Handle messages from authenticated clients
        if message_type == 'create_lobby':
            self.handle_create_lobby(client)
            
        elif message_type == 'list_lobbies':
            self.handle_list_lobbies(client)
            
        elif message_type == 'join_lobby':
            lobby_id = message.get('lobby_id')
            self.handle_join_lobby(client, lobby_id)
            
        elif message_type == 'start_game':
            lobby_id = message.get('lobby_id')
            self.handle_start_game(client, lobby_id)
            
        elif message_type == 'move':
            game_id = message.get('game_id')
            move = message.get('move')
            self.handle_game_move(client, game_id, move)
            
        elif message_type == 'resign':
            game_id = message.get('game_id')
            self.handle_resignation(client, game_id)
            
        elif message_type == 'spectate':
            game_id = message.get('game_id')
            self.handle_spectate_request(client, game_id)
    
    def process_chat_message(self, chat_client, message):
        """Process a message from a chat client"""
        message_type = message.get('type', '')
        
        # First message should include client_id and either game_id or lobby_id
        if not chat_client.client_id:
            client_id = message.get('client_id')
            game_id = message.get('game_id')
            lobby_id = message.get('lobby_id')
            chat_type = message.get('type')
            
            if client_id:
                # Find the corresponding game client
                game_client = self.clients.get(client_id)
                
                if game_client:
                    chat_client.client_id = client_id
                    chat_client.game_client = game_client
                    
                    # Set up for game chat
                    if chat_type == 'game_chat' and game_id and game_id in self.games:
                        chat_client.game_id = game_id
                        chat_client.lobby_id = None
                        self.chat_clients[client_id] = chat_client
                        
                        # Send acknowledgment
                        chat_client.send({
                            'type': 'chat_connected',
                            'message': f"Connected to game chat for game {game_id}"
                        })
                        
                        self.log(f"Chat client connected for game {game_id}")
                        return
                    
                    # Set up for lobby chat
                    elif chat_type == 'lobby_chat' and lobby_id and lobby_id in self.lobbies:
                        chat_client.lobby_id = lobby_id
                        chat_client.game_id = None
                        self.chat_clients[client_id] = chat_client
                        
                        # Send acknowledgment
                        chat_client.send({
                            'type': 'chat_connected',
                            'message': f"Connected to lobby chat for lobby {lobby_id}"
                        })
                        
                        self.log(f"Chat client connected for lobby {lobby_id}")
                        return
            
            # If we get here, something was wrong with the initial message
            chat_client.send({'type': 'error', 'message': 'Invalid connection parameters'})
            chat_client.disconnect()
            return
        
        # Handle chat messages
        if message_type == 'chat':
            text = message.get('text', '')
            game_id = message.get('game_id')
            lobby_id = message.get('lobby_id')
            
            if game_id and game_id in self.games:
                # Game chat
                game = self.games[game_id]
                
                # Create chat message to broadcast
                chat_message = {
                    'type': 'chat',
                    'sender': chat_client.game_client.username,
                    'text': text,
                    'timestamp': time.time()
                }
                
                # Broadcast to all participants in the game
                self.broadcast_chat(game, chat_message)
                self.log(f"Chat in game {game_id}: {chat_client.game_client.username}: {text}")
                
            elif lobby_id and lobby_id in self.lobbies:
                # Lobby chat
                lobby = self.lobbies[lobby_id]
                
                # Create chat message to broadcast
                chat_message = {
                    'type': 'chat',
                    'sender': chat_client.game_client.username,
                    'text': text,
                    'timestamp': time.time()
                }
                
                # Broadcast to all players in the lobby
                self.broadcast_lobby_chat(lobby, chat_message)
                self.log(f"Chat in lobby {lobby_id}: {chat_client.game_client.username}: {text}")
    
    def handle_create_lobby(self, client):
        """Handle a client's request to create a lobby"""
        # First check if client is already in a lobby
        if client.current_lobby:
            client.send({'type': 'error', 'message': 'Already in a lobby'})
            return
            
        # Create a new lobby
        lobby_id = str(uuid.uuid4())
        new_lobby = GameLobby(lobby_id, client)
        
        # Add to lobbies dictionary
        self.lobbies[lobby_id] = new_lobby
        
        # Update client's current lobby
        client.current_lobby = new_lobby
        
        # Send confirmation to client
        client.send({
            'type': 'lobby_created',
            'lobby_id': lobby_id,
            'message': 'Lobby created successfully'
        })
        
        self.log(f"Player {client.username} created lobby {lobby_id[:8]}")
        self.update_stats()
    
    def handle_list_lobbies(self, client):
        """Handle a client's request to list available lobbies"""
        lobby_list = []
        
        for lobby_id, lobby in self.lobbies.items():
            # Only include lobbies that are still waiting for players
            if lobby.status == "waiting":
                lobby_list.append({
                    'lobby_id': lobby_id,
                    'host': lobby.players[0].username,
                    'players': [player.username for player in lobby.players],
                    'player_count': lobby.get_player_count(),
                    'max_players': lobby.max_players
                })
        
        # Send the list to the client
        client.send({
            'type': 'lobbies_list',
            'lobbies': lobby_list
        })
        
        self.log(f"Sent lobby list to {client.username}")
    
    def handle_join_lobby(self, client, lobby_id):
        """Handle a client's request to join a lobby"""
        # Check if client is already in a lobby
        if client.current_lobby:
            client.send({'type': 'error', 'message': 'Already in a lobby'})
            return
            
        # Check if lobby exists
        if lobby_id not in self.lobbies:
            client.send({'type': 'error', 'message': 'Lobby not found'})
            return
            
        lobby = self.lobbies[lobby_id]
        
        # Check if lobby is full
        if lobby.is_full():
            client.send({'type': 'error', 'message': 'Lobby is full'})
            return
            
        # Add player to lobby
        if lobby.add_player(client):
            # Update client's current lobby
            client.current_lobby = lobby
            
            # Notify client they joined successfully
            client.send({
                'type': 'lobby_joined',
                'lobby_id': lobby_id,
                'host': lobby.players[0].username,
                'players': [p.username for p in lobby.players]
            })
            
            # Notify other players in the lobby
            for player in lobby.players:
                if player != client:
                    player.send({
                        'type': 'player_joined_lobby',
                        'lobby_id': lobby_id,
                        'player': client.username,
                        'players': [p.username for p in lobby.players]
                    })
            
            self.log(f"Player {client.username} joined lobby {lobby_id[:8]}")
            
            # If lobby is now full, notify both players
            if lobby.is_full():
                for player in lobby.players:
                    player.send({
                        'type': 'lobby_full',
                        'lobby_id': lobby_id,
                        'message': 'Lobby is now full. Ready to start game.'
                    })
        else:
            client.send({'type': 'error', 'message': 'Failed to join lobby'})
    
    def handle_start_game(self, client, lobby_id):
        """Handle a client's request to start a game from a lobby"""
        # Check if lobby exists
        if lobby_id not in self.lobbies:
            client.send({'type': 'error', 'message': 'Lobby not found'})
            return
            
        lobby = self.lobbies[lobby_id]
        
        # Check if client is the host of the lobby
        if lobby.players[0] != client:
            client.send({'type': 'error', 'message': 'Only the host can start the game'})
            return
            
        # Check if lobby has enough players
        if len(lobby.players) < 2:
            client.send({'type': 'error', 'message': 'Need at least 2 players to start'})
            return
            
        # Create a new game
        game_id = str(uuid.uuid4())
        white_player = lobby.players[0]  # Host is white
        black_player = lobby.players[1]  # Joiner is black
        
        # Create the chess game
        new_game = ChessGame(game_id, white_player, black_player)
        self.games[game_id] = new_game
        
        # Update players' current game
        white_player.current_game = new_game
        black_player.current_game = new_game
        
        # Remove players from lobby
        white_player.current_lobby = None
        black_player.current_lobby = None
        
        # Remove the lobby
        del self.lobbies[lobby_id]
        
        # Notify players that game has started
        for player in [white_player, black_player]:
            player.send({
                'type': 'game_started',
                'game_id': game_id,
                'white_player': white_player.username,
                'black_player': black_player.username,
                'time_control': new_game.time_control
            })
            
            # Send initial game state
            player.send(new_game.get_state(player))
        
        # Log game start and create a message for all clients
        self.log(f"Game {game_id} started: {white_player.username} (White) vs {black_player.username} (Black)")
        
        # Announce game to all connected clients so they can spectate
        spectate_announcement = {
            'type': 'game_announcement',
            'message': f"Game started: {white_player.username} (White) vs {black_player.username} (Black)",
            'game_id': game_id,
            'white_player': white_player.username,
            'black_player': black_player.username
        }
        
        # Send announcement to all connected clients
        for client_id, other_client in self.clients.items():
            if other_client != white_player and other_client != black_player:
                other_client.send(spectate_announcement)
        
        self.update_stats()
        self.update_games_list()
    
    def handle_game_move(self, client, game_id, move_uci):
        """Handle a move in a chess game"""
        # Check if game exists
        if game_id not in self.games:
            client.send({'type': 'error', 'message': 'Game not found'})
            return
            
        game = self.games[game_id]
        
        # Check if client is a player in this game
        if not game.is_player(client):
            client.send({'type': 'error', 'message': 'Not a player in this game'})
            return
            
        # Check if it's this player's turn
        is_white_turn = game.board.turn == chess.WHITE
        if (is_white_turn and client != game.white_player) or \
           (not is_white_turn and client != game.black_player):
            client.send({'type': 'error', 'message': 'Not your turn'})
            return
            
        # Try to make the move
        success, error_msg = game.make_move(move_uci)
        
        if success:
            # Get updated game state
            game_state = game.get_state()
            
            # Send updated state to all participants
            for participant in game.get_all_participants():
                participant.send(game.get_state(participant))
            
            # Log the move
            turn_number = len(game.move_history)
            self.log(f"Game {game_id[:8]}: {client.username} played {move_uci} ({turn_number})")
            
            # Check if game is over
            if game_state.get('game_over', False):
                self.handle_game_over(game, game_state)
        else:
            # Send error message to client
            client.send({'type': 'error', 'message': f'Invalid move: {error_msg}'})
    
    def handle_resignation(self, client, game_id):
        """Handle a player resigning from a game"""
        # Check if game exists
        if game_id not in self.games:
            client.send({'type': 'error', 'message': 'Game not found'})
            return
            
        game = self.games[game_id]
        
        # Check if client is a player in this game
        if not game.is_player(client):
            client.send({'type': 'error', 'message': 'Not a player in this game'})
            return
            
        # Determine winner
        winner = None
        if client == game.white_player:
            winner = "black"
        else:
            winner = "white"
            
        # Update game state
        game_state = game.get_state()
        game_state['game_over'] = True
        game_state['result'] = 'resignation'
        game_state['winner'] = winner
        
        # Notify all participants
        for participant in game.get_all_participants():
            participant.send(game_state)
            
        self.log(f"Game {game_id[:8]}: {client.username} resigned, {winner} wins")
        
        # Handle game over
        self.handle_game_over(game, game_state)
    
    def handle_spectate_request(self, client, game_id):
        """Handle a client's request to spectate a game"""
        # Check if game exists
        if game_id not in self.games:
            client.send({'type': 'error', 'message': 'Game not found'})
            return
            
        game = self.games[game_id]
        
        # Check if client is already a player or spectator
        if game.is_player(client) or client in game.spectators:
            client.send({'type': 'error', 'message': 'Already in this game'})
            return
            
        # Add client as spectator
        game.add_spectator(client)
        client.current_game = game
        
        # Send game state to spectator
        client.send({
            'type': 'spectating',
            'game_id': game_id,
            'white_player': game.white_player.username,
            'black_player': game.black_player.username
        })
        
        client.send(game.get_state(client))
        
        # Notify players about new spectator
        for player in [game.white_player, game.black_player]:
            if player:
                player.send({
                    'type': 'new_spectator',
                    'game_id': game_id,
                    'spectator': client.username
                })
                
        self.log(f"Player {client.username} is now spectating game {game_id[:8]}")
    
    def handle_game_over(self, game, game_state):
        """Handle a game that has ended"""
        # Mark game as inactive
        game.is_active = False
        
        # Send game over notification to all participants
        for participant in game.get_all_participants():
            participant.send({
                'type': 'game_over',
                'game_id': game.game_id,
                'result': game_state.get('result'),
                'winner': game_state.get('winner')
            })
            
            # Update client state
            participant.current_game = None
            
        # Remove game after a delay
        threading.Timer(60, self.remove_game, args=(game.game_id,)).start()
        
        self.log(f"Game {game.game_id[:8]} ended: {game_state.get('result')}, winner: {game_state.get('winner')}")
        self.update_stats()
        self.update_games_list()
    
    def remove_game(self, game_id):
        """Remove a game from the server"""
        if game_id in self.games:
            del self.games[game_id]
            self.log(f"Game {game_id[:8]} removed from memory")
            self.update_stats()
            self.update_games_list()
    
    def handle_player_leave_game(self, client):
        """Handle a player leaving a game"""
        if not client.current_game:
            return
            
        game = client.current_game
        
        # Check if client is a player or spectator
        if game.is_player(client):
            # If game is still active, handle as resignation
            if game.is_active:
                # Determine winner
                winner = None
                if client == game.white_player:
                    winner = "black"
                else:
                    winner = "white"
                    
                # Update game state
                game_state = game.get_state()
                game_state['game_over'] = True
                game_state['result'] = 'disconnection'
                game_state['winner'] = winner
                
                self.log(f"Player {client.username} disconnected from active game {game.game_id[:8]}, {winner} wins")
                
                # Handle game over
                self.handle_game_over(game, game_state)
            else:
                # Game already over, just remove client
                if client == game.white_player:
                    game.white_player = None
                elif client == game.black_player:
                    game.black_player = None
        else:
            # Remove spectator
            game.remove_spectator(client)
            self.log(f"Spectator {client.username} left game {game.game_id[:8]}")
            
        client.current_game = None
    
    def handle_player_leave_lobby(self, client):
        """Handle a player leaving a lobby"""
        if not client.current_lobby:
            return
            
        lobby = client.current_lobby
        
        # Check if client is the host
        if lobby.players[0] == client:
            # Host left, notify other players and remove lobby
            for player in lobby.players:
                if player != client:
                    player.send({
                        'type': 'lobby_closed',
                        'message': 'Host left the lobby'
                    })
                    player.current_lobby = None
                    
            # Remove lobby
            if lobby.lobby_id in self.lobbies:
                del self.lobbies[lobby.lobby_id]
                self.log(f"Lobby {lobby.lobby_id[:8]} closed because host left")
        else:
            # Regular player left, notify host
            lobby.remove_player(client)
            
            if lobby.players:  # Make sure there are still players
                host = lobby.players[0]
                host.send({
                    'type': 'player_left_lobby',
                    'player': client.username,
                    'players': [p.username for p in lobby.players]
                })
                self.log(f"Player {client.username} left lobby {lobby.lobby_id[:8]}")
                
        client.current_lobby = None
        self.update_stats()
    
    def handle_client_disconnect(self, client):
        """Handle a client disconnecting from the server"""
        # Remove from any game
        if client.current_game:
            self.handle_player_leave_game(client)
            
        # Remove from any lobby
        if client.current_lobby:
            self.handle_player_leave_lobby(client)
            
        # Remove from clients list
        if client.client_id in self.clients:
            del self.clients[client.client_id]
            
        # Update UI
        self.update_stats()
        self.update_clients_list()
        self.log(f"Client {client.username or client.client_id[:8]} disconnected")
    
    def handle_chat_client_disconnect(self, chat_client):
        """Handle a chat client disconnecting"""
        # Remove from chat clients dictionary
        if chat_client.client_id and chat_client.client_id in self.chat_clients:
            del self.chat_clients[chat_client.client_id]
            self.log(f"Chat client for {chat_client.client_id[:8]} disconnected")
    
    def broadcast_chat(self, game, chat_message):
        """Broadcast a chat message to all participants in a game"""
        # Get all chat clients for participants in this game
        for participant in game.get_all_participants():
            # Find the participant's chat client
            if participant.client_id in self.chat_clients:
                chat_client = self.chat_clients[participant.client_id]
                chat_client.send(chat_message)
    
    def broadcast_lobby_chat(self, lobby, chat_message):
        """Broadcast a chat message to all players in a lobby"""
        # Get all chat clients for players in this lobby
        for player in lobby.players:
            # Find the player's chat client
            if player.client_id in self.chat_clients:
                chat_client = self.chat_clients[player.client_id]
                chat_client.send(chat_message)
    
    def timer_loop(self):
        """Main timer loop for handling game clocks and inactivity"""
        while self.running:
            try:
                # Update active games every second
                time.sleep(1)
                
                # Check for inactive clients
                current_time = time.time()
                for client_id, client in list(self.clients.items()):
                    # If client hasn't sent any message in 15 minutes, disconnect
                    if current_time - client.last_activity > 900:  # 15 minutes
                        self.log(f"Client {client.username or client.client_id[:8]} inactive, disconnecting")
                        client.disconnect()
                        
                # Update UI
                if self.games or self.clients:
                    self.update_ui()
                    
            except Exception as e:
                self.log(f"Error in timer loop: {e}")
    
    def update_ui(self):
        """Update UI elements"""
        try:
            # Only update UI elements once per second at most
            self.update_stats()
            self.root.update_idletasks()
        except Exception as e:
            pass  # Ignore UI update errors
    
    def update_stats(self):
        """Update the statistics display"""
        try:
            self.clients_label.config(text=str(len(self.clients)))
            self.games_label.config(text=str(len(self.games)))
            self.lobbies_label.config(text=str(len(self.lobbies)))
        except:
            pass  # Ignore UI update errors
    
    def update_clients_list(self):
        """Update the connected clients list"""
        try:
            self.clients_list.delete(0, tk.END)
            for client_id, client in self.clients.items():
                status = ""
                if client.current_game:
                    status = "(in game)"
                elif client.current_lobby:
                    status = "(in lobby)"
                    
                self.clients_list.insert(tk.END, f"{client.username} {status}")
        except:
            pass  # Ignore UI update errors
    
    def update_games_list(self):
        """Update the active games list"""
        try:
            self.games_listbox.delete(0, tk.END)
            for game_id, game in self.games.items():
                status = "Active" if game.is_active else "Ended"
                self.games_listbox.insert(tk.END, f"{game.white_player.username} vs {game.black_player.username} ({status})")
        except:
            pass  # Ignore UI update errors
    
    def log(self, message):
        """Add a message to the log queue"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")
    
    def process_logs(self):
        """Process log messages from the queue"""
        try:
            while not self.log_queue.empty():
                message = self.log_queue.get_nowait()
                self.log_display.insert(tk.END, message + "\n")
                self.log_display.see(tk.END)  # Scroll to bottom
        except:
            pass  # Ignore log processing errors
            
        # Schedule next log processing
        self.root.after(100, self.process_logs)
    
    def on_closing(self):
        """Handle window closing"""
        if self.running:
            self.stop_server()
        self.root.destroy()
        # Force exit if threads are hanging
        os._exit(0)

def main():
    """Main entry point"""
    # Set up signal handlers for clean shutdown
    def signal_handler(sig, frame):
        print("Shutting down server...")
        if hasattr(root, 'server'):
            root.server.stop_server()
        root.destroy()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create Tkinter root
    root = tk.Tk()
    
    # Create server GUI
    server_gui = ChessServerGUI(root)
    root.server = server_gui  # Store reference for signal handler
    
    # Run Tkinter main loop
    root.mainloop()

if __name__ == "__main__":
    main()
