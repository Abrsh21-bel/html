import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog, messagebox
import firebase_admin
from firebase_admin import credentials, db
import threading
import queue
from datetime import datetime
import json
import os
from tkinter import font as tkfont
import webbrowser

class ModernChatApp:
    def __init__(self, root):
        self.root = root
        self.setup_window()
        self.message_queue = queue.Queue()
        self.running = True
        self.current_username = None
        self.message_count = 0
        self.theme = "light"  # light/dark mode
        
        # UI Setup
        self.create_menu()
        self.setup_ui()
        
        # Firebase Setup
        self.firebase_active = self.initialize_firebase()
        if not self.firebase_active:
            self.show_fallback_warning()
        
        # Start services
        self.root.after(100, self.process_messages)
        self.setup_auto_save()

    def setup_window(self):
        """Configure main window properties"""
        self.root.title("NeoChat - Secure Classroom Messenger")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        self.root.configure(bg="#f5f5f5")
        
        # Center window on screen
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        self.root.geometry(f'+{(ws-w)//2}+{(hs-h)//2}')

    def create_menu(self):
        """Create menu bar with options"""
        menubar = tk.Menu(self.root)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Change Username", command=self.change_username)
        file_menu.add_command(label="Clear Chat", command=self.clear_chat)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Light Mode", command=lambda: self.set_theme("light"))
        view_menu.add_command(label="Dark Mode", command=lambda: self.set_theme("dark"))
        menubar.add_cascade(label="View", menu=view_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Documentation", command=self.show_docs)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)

    def setup_ui(self):
        """Initialize all UI components"""
        # Custom fonts
        self.base_font = tkfont.Font(family="Segoe UI", size=12)
        self.bold_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Chat display
        self.chat_display = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            state="disabled",
            font=self.base_font,
            padx=10,
            pady=10,
            bg="white",
            fg="black",
            insertbackground="black"
        )
        self.chat_display.pack(expand=True, fill="both")
        
        # Bottom panel
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", pady=(5, 0))
        
        # Message entry
        self.msg_entry = ttk.Entry(
            bottom_frame,
            font=self.base_font
        )
        self.msg_entry.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.msg_entry.bind("<Return>", self.send_message)
        self.msg_entry.focus_set()
        
        # Send button with animation
        self.send_btn = ttk.Button(
            bottom_frame,
            text="Send",
            command=self.send_message,
            style="Accent.TButton"
        )
        self.send_btn.pack(side="right")
        
        # Status bar
        self.status_bar = ttk.Label(
            self.root,
            text="Connecting...",
            relief="sunken",
            anchor="center"
        )
        self.status_bar.pack(fill="x", pady=(5, 0))
        
        # Configure styles
        self.style = ttk.Style()
        self.style.configure("Accent.TButton", foreground="white", background="#4CAF50")
        self.style.map("Accent.TButton",
                      background=[("active", "#45a049"), ("disabled", "#cccccc")])
        
        # Initial username prompt
        self.change_username()

    def initialize_firebase(self):
        """Initialize Firebase with multiple fallback options"""
        try:
            # Try environment variables first (for deployment)
            if os.getenv("FIREBASE_CONFIG"):
                config = json.loads(os.getenv("FIREBASE_CONFIG"))
                cred = credentials.Certificate(config)
                db_url = os.getenv("DATABASE_URL")
            # Try local config file (for development)
            elif os.path.exists("firebase_config.json"):
                cred = credentials.Certificate("firebase_config.json")
                with open("firebase_config.json") as f:
                    config = json.load(f)
                    db_url = config.get("databaseURL")
            else:
                return False
                
            firebase_admin.initialize_app(cred, {"databaseURL": db_url})
            self.db_ref = db.reference("messages")
            self.setup_listener()
            self.update_status("Connected to Firebase", "green")
            return True
        except Exception as e:
            print(f"Firebase initialization failed: {str(e)}")
            self.update_status("Offline Mode - Messages not saved", "red")
            return False

    def setup_listener(self):
        """Set up real-time Firebase listener"""
        def listener():
            try:
                self.db_ref.limit_to_last(100).listen(self.message_handler)
            except Exception as e:
                self.queue_message("SYSTEM", f"Connection error: {str(e)}")
                self.update_status("Connection lost", "red")
        
        threading.Thread(target=listener, daemon=True).start()

    def message_handler(self, event):
        """Handle incoming Firebase messages"""
        if event.data and isinstance(event.data, dict):
            self.queue_message(
                event.data.get("sender", "Unknown"),
                event.data.get("message", ""),
                event.data.get("timestamp", "")
            )

    def queue_message(self, sender, message, timestamp=""):
        """Thread-safe message queuing"""
        self.message_queue.put({
            "sender": sender,
            "message": message,
            "timestamp": timestamp or datetime.now().isoformat()
        })

    def process_messages(self):
        """Process queued messages in main thread"""
        while not self.message_queue.empty():
            msg = self.message_queue.get()
            self.display_message(**msg)
        
        if self.running:
            self.root.after(100, self.process_messages)

    def display_message(self, sender, message, timestamp):
        """Display message in chat with formatting"""
        try:
            time_str = datetime.fromisoformat(timestamp).strftime("%H:%M")
            self.chat_display.config(state="normal")
            
            # Formatting tags
            self.chat_display.tag_config("time", foreground="gray")
            self.chat_display.tag_config("username", font=self.bold_font)
            self.chat_display.tag_config("self", foreground="blue")
            self.chat_display.tag_config("system", foreground="red")
            
            # Determine message type
            if sender == "SYSTEM":
                tag = "system"
            elif sender == self.current_username:
                tag = "self"
            else:
                tag = ""
            
            # Insert message
            self.chat_display.insert("end", f"[", "time")
            self.chat_display.insert("end", time_str, "time")
            self.chat_display.insert("end", "] ", "time")
            self.chat_display.insert("end", f"{sender}: ", "username")
            self.chat_display.insert("end", f"{message}\n", tag)
            
            self.chat_display.config(state="disabled")
            self.chat_display.see("end")
            self.message_count += 1
            
            # Auto-scroll if near bottom
            if self.chat_display.yview()[1] > 0.9:
                self.chat_display.see("end")
                
        except tk.TclError:
            pass  # Window destroyed

    def send_message(self, event=None):
        """Send message to Firebase"""
        message = self.msg_entry.get().strip()
        if message and self.current_username:
            try:
                if self.firebase_active:
                    self.db_ref.push({
                        "sender": self.current_username,
                        "message": message,
                        "timestamp": datetime.now().isoformat()
                    })
                else:
                    # Offline mode
                    self.queue_message(
                        self.current_username,
                        message,
                        datetime.now().isoformat()
                    )
                self.msg_entry.delete(0, "end")
            except Exception as e:
                self.queue_message("SYSTEM", f"Send failed: {str(e)}")

    def change_username(self):
        """Prompt for new username"""
        username = simpledialog.askstring(
            "Username",
            "Enter your display name (3-15 characters):",
            parent=self.root,
            initialvalue=self.current_username or ""
        )
        
        if username and 3 <= len(username) <= 15:
            self.current_username = username
            self.queue_message("SYSTEM", f"User set to: {username}")
            self.root.title(f"NeoChat - {username}")
            self.update_status(f"Logged in as: {username}", "blue")

    def clear_chat(self):
        """Clear the chat display"""
        self.chat_display.config(state="normal")
        self.chat_display.delete(1.0, "end")
        self.chat_display.config(state="disabled")
        self.message_count = 0

    def set_theme(self, theme):
        """Change between light/dark themes"""
        self.theme = theme
        if theme == "dark":
            bg = "#2d2d2d"
            fg = "#ffffff"
            entry_bg = "#3d3d3d"
        else:
            bg = "#f5f5f5"
            fg = "#000000"
            entry_bg = "#ffffff"
        
        # Apply colors
        self.root.configure(bg=bg)
        self.chat_display.configure(bg=entry_bg, fg=fg)
        self.msg_entry.configure(style=f"{theme}.TEntry")
        
        # Configure styles
        self.style.configure(".", background=bg, foreground=fg)
        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=fg)
        self.style.configure("TEntry", fieldbackground=entry_bg, foreground=fg)
        
        self.queue_message("SYSTEM", f"Switched to {theme} mode")

    def update_status(self, text, color="black"):
        """Update status bar message"""
        self.status_bar.config(text=text, foreground=color)

    def setup_auto_save(self):
        """Periodically save chat history"""
        if self.message_count % 10 == 0 and self.message_count > 0:
            self.save_chat_history()
        self.root.after(60000, self.setup_auto_save)  # Every minute

    def save_chat_history(self):
        """Save chat to local file"""
        try:
            with open("chat_history.txt", "w", encoding="utf-8") as f:
                f.write(self.chat_display.get(1.0, "end"))
        except Exception as e:
            print(f"Failed to save chat: {str(e)}")

    def show_fallback_warning(self):
        """Show offline mode warning"""
        self.queue_message(
            "SYSTEM",
            "Running in offline mode - messages won't be saved"
        )

    def show_docs(self):
        """Open documentation in browser"""
        webbrowser.open("https://github.com/Abrsh21-bel/Abrsh21-bel/wiki")

    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo(
            "About NeoChat",
            "Modern Classroom Chat Application\n"
            "Version 2.0\n\n"
            "Features:\n"
            "- Real-time messaging\n"
            "- Light/Dark themes\n"
            "- Message history\n"
            "- Cross-platform\n\n"
            "© 2023 Abrsh21-bel"
        )

    def on_close(self):
        """Clean shutdown procedure"""
        self.running = False
        if self.message_count > 0:
            self.save_chat_history()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ModernChatApp(root)
    root.mainloop()
