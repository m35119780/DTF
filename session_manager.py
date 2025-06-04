"""
Session management module for DTF Design Packer
Handles session timeouts, cleanup of expired sessions, and resource management
"""
import os
import time
import shutil
import logging
from datetime import datetime, timedelta
import threading
import json

# Configure logging
logger = logging.getLogger(__name__)

class SessionManager:
    """Manages sessions and their associated resources"""
    
    def __init__(self, app):
        """Initialize the session manager with app configuration"""
        self.app = app
        self.upload_folder = app.config['UPLOAD_FOLDER']
        self.output_folder = app.config['OUTPUT_FOLDER']
        self.session_timeout = app.config.get('SESSION_TIMEOUT', 3600)  # Default 1 hour
        self.cleanup_interval = app.config.get('SESSION_CLEANUP_INTERVAL', 3600)  # Default 1 hour
        self.session_activity = {}  # Tracks last activity time for each session
        self.lock = threading.Lock()  # Thread safety for session activity tracking
        
        # Create session tracking file if not exists
        self.session_file = os.path.join(app.instance_path, 'sessions.json')
        os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
        if not os.path.exists(self.session_file):
            self._write_session_data({})
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_thread, daemon=True)
        self.cleanup_thread.start()
        
        logger.info(f"Session manager initialized with timeout: {self.session_timeout}s, "
                    f"cleanup interval: {self.cleanup_interval}s")
    
    def track_activity(self, session_id):
        """Track session activity to reset timeout"""
        if not session_id:
            return
            
        with self.lock:
            current_time = time.time()
            self.session_activity[session_id] = current_time
            
            # Also update persistent session data
            session_data = self._read_session_data()
            session_data[session_id] = {
                'last_activity': current_time,
                'created': session_data.get(session_id, {}).get('created', current_time)
            }
            self._write_session_data(session_data)
    
    def create_session(self, session_id):
        """Register a new session"""
        current_time = time.time()
        
        with self.lock:
            self.session_activity[session_id] = current_time
            
            # Update persistent session data
            session_data = self._read_session_data()
            session_data[session_id] = {
                'last_activity': current_time,
                'created': current_time
            }
            self._write_session_data(session_data)
            
        # Create folders for session if they don't exist
        upload_dir = os.path.join(self.upload_folder, session_id)
        output_dir = os.path.join(self.output_folder, session_id)
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Created new session: {session_id}")
        return session_id
    
    def end_session(self, session_id):
        """End a session and clean up its resources"""
        if not session_id:
            return
            
        # Remove from activity tracking
        with self.lock:
            if session_id in self.session_activity:
                del self.session_activity[session_id]
            
            # Remove from persistent storage
            session_data = self._read_session_data()
            if session_id in session_data:
                del session_data[session_id]
            self._write_session_data(session_data)
        
        # Clean up session files
        self._cleanup_session_files(session_id)
        logger.info(f"Ended session: {session_id}")
    
    def is_session_valid(self, session_id):
        """Check if a session is still valid (not expired)"""
        if not session_id:
            return False
            
        with self.lock:
            # Check in-memory activity data
            last_activity = self.session_activity.get(session_id)
            if last_activity is None:
                # Check persistent data as fallback
                session_data = self._read_session_data()
                session_info = session_data.get(session_id)
                if not session_info:
                    return False
                last_activity = session_info.get('last_activity')
                if last_activity is None:
                    return False
            
            # Check if expired
            current_time = time.time()
            return (current_time - last_activity) < self.session_timeout
    
    def cleanup_expired_sessions(self):
        """Clean up all expired sessions and their resources"""
        current_time = time.time()
        expired_sessions = []
        
        # Identify expired sessions
        with self.lock:
            # Check in-memory tracking
            for session_id, last_activity in list(self.session_activity.items()):
                if (current_time - last_activity) >= self.session_timeout:
                    expired_sessions.append(session_id)
                    del self.session_activity[session_id]
            
            # Also check persistent storage for missed sessions
            session_data = self._read_session_data()
            for session_id, info in list(session_data.items()):
                if session_id not in expired_sessions and (current_time - info['last_activity']) >= self.session_timeout:
                    expired_sessions.append(session_id)
                    if session_id in self.session_activity:
                        del self.session_activity[session_id]
                
            # Update persistent storage
            for session_id in expired_sessions:
                if session_id in session_data:
                    del session_data[session_id]
            self._write_session_data(session_data)
        
        # Clean up resources for each expired session
        for session_id in expired_sessions:
            self._cleanup_session_files(session_id)
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
        
        return len(expired_sessions)
    
    def _cleanup_session_files(self, session_id):
        """Remove all files associated with a session"""
        try:
            # Clean up upload directory
            upload_dir = os.path.join(self.upload_folder, session_id)
            if os.path.exists(upload_dir):
                shutil.rmtree(upload_dir, ignore_errors=True)
            
            # Clean up output directory  
            output_dir = os.path.join(self.output_folder, session_id)
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir, ignore_errors=True)
                
            # Clean up zip file
            zip_path = os.path.join(self.output_folder, f'{session_id}_results.zip')
            if os.path.exists(zip_path):
                os.remove(zip_path)
                
            logger.debug(f"Cleaned up files for session: {session_id}")
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")
    
    def _cleanup_thread(self):
        """Background thread that periodically cleans up expired sessions"""
        logger.info("Session cleanup thread started")
        while True:
            try:
                time.sleep(self.cleanup_interval)
                self.cleanup_expired_sessions()
            except Exception as e:
                logger.error(f"Error in session cleanup thread: {e}")
    
    def _read_session_data(self):
        """Read session data from persistent storage"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error reading session data: {e}")
        return {}
    
    def _write_session_data(self, session_data):
        """Write session data to persistent storage"""
        try:
            with open(self.session_file, 'w') as f:
                json.dump(session_data, f)
        except Exception as e:
            logger.error(f"Error writing session data: {e}")
    
    def get_session_stats(self):
        """Get statistics about active sessions"""
        with self.lock:
            session_data = self._read_session_data()
            current_time = time.time()
            
            active_count = 0
            expired_count = 0
            oldest_active = None
            
            for session_id, info in session_data.items():
                age = current_time - info['created']
                is_expired = (current_time - info['last_activity']) >= self.session_timeout
                
                if is_expired:
                    expired_count += 1
                else:
                    active_count += 1
                    if oldest_active is None or age > oldest_active:
                        oldest_active = age
            
            return {
                'active_sessions': active_count,
                'expired_sessions': expired_count,
                'oldest_active_session': oldest_active,
                'total_sessions': len(session_data)
            } 