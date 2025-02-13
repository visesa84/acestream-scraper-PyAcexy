import os
from app import create_app
from app.tasks.manager import TaskManager
import threading
import asyncio

def run_task_manager(app):
    """Run task manager in a separate thread"""
    task_manager = TaskManager()
    task_manager.init_app(app)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(task_manager.start())
    loop.run_forever()

def main():
    """Main entry point for development server"""
    app = create_app()
    
    # Get port from environment variable or use default
    port = int(os.getenv('FLASK_PORT', 8000))
    
    # Start task manager in a separate thread
    task_thread = threading.Thread(target=run_task_manager, args=(app,))
    task_thread.daemon = True
    task_thread.start()
    
    # Run Flask app in debug mode
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True,
        use_reloader=False  # Disable reloader when using threads
    )

if __name__ == '__main__':
    main()