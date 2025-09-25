# CHESS-in-Python

A simple networked chess game built in Python, using a client–server architecture.  
This project allows two players to play chess over a network connection using sockets.

---

## 🎯 Features

- Two-player chess over a network (client/server)
- Basic move validation
- Real-time updates between client and server
- Console-based interaction

---

## 📂 Repository Structure

.
├── chess_client.py # Client-side implementation
├── chess_server.py # Server-side implementation
└── README.md # Project documentation

yaml
Copy code

---

## ⚙️ Requirements

- Python **3.x**
- Networking enabled between client and server (sockets)

No external libraries are required — the project only uses Python’s standard library.

---

## 🚀 Usage

1. **Start the server** (on host machine):
   ```bash
   python chess_server.py
Start the client (on same or remote machine, ensure correct IP/port):

bash
Copy code
python chess_client.py
Connect the client to the server and start playing!
Players take turns to input moves in standard chess notation.
