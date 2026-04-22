#!/usr/bin/env python3

import cv2
import numpy as np
import json
import time
import socket
import threading
import queue
import os
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, List, Dict, Any
from collections import deque
from datetime import datetime, timedelta
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class RFIDEvent:
    tag_id: str
    timestamp: float
    processed: bool = False

@dataclass
class ContainerEvent:
    entry_time: float
    exit_time: Optional[float]
    frame_ids: List[int]
    best_frames: List[Tuple[float, np.ndarray, int]]
    box_coordinates: List[Tuple[int, int, int, int]]
    
@dataclass
class MatchResult:
    tag_id: str
    container: ContainerEvent
    confidence: float
    entry_offset: float
    exit_offset: float

class Config:
    def __init__(self, config_path="config/config.json"):
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        
        self.socket_path = cfg.get("socket_path", "/tmp/rfid_vision.sock")
        self.output_dir = cfg.get("output_dir", "output")
        
        cam = cfg.get("camera", {})
        self.camera_index = cam.get("index", 0)
        self.camera_width = cam.get("width", 640)
        self.camera_height = cam.get("height", 480)
        self.camera_fps = cam.get("fps", 30)
        
        det = cfg.get("detection", {})
        self.motion_threshold = det.get("motion_threshold", 25.0)
        self.blur_kernel = tuple(det.get("blur_kernel", [5, 5]))
        self.min_area = det.get("min_area", 2000)
        self.max_area = det.get("max_area", 200000)
        self.aspect_ratio_min = det.get("aspect_ratio_min", 0.6)
        self.aspect_ratio_max = det.get("aspect_ratio_max", 3.5)
        self.presence_min_frames = det.get("presence_min_frames", 3)
        self.absence_min_frames = det.get("absence_min_frames", 10)
        
        assoc = cfg.get("association", {})
        self.rfid_buffer_seconds = assoc.get("rfid_buffer_seconds", 30)
        self.entry_buffer_seconds = assoc.get("entry_buffer_seconds", 2.0)
        self.exit_buffer_seconds = assoc.get("exit_buffer_seconds", 2.0)
        self.min_confidence = assoc.get("min_confidence", 0.6)
        
        cap = cfg.get("capture", {})
        self.capture_top_n = cap.get("top_n_frames", 5)
        self.save_visualization = cap.get("save_visualization", True)

class IPCServer:
    def __init__(self, socket_path, message_queue):
        self.socket_path = socket_path
        self.message_queue = message_queue
        self.running = True
        self.server_socket = None
        
    def start(self):
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(1)
        self.server_socket.settimeout(1.0)
        
        logger.info(f"IPC server listening on {self.socket_path}")
        
        while self.running:
            try:
                conn, _ = self.server_socket.accept()
                threading.Thread(target=self.handle_client, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Server error: {e}")
    
    def handle_client(self, conn):
        logger.info("RFID reader connected")
        buffer = ""
        
        try:
            while self.running:
                data = conn.recv(1024).decode('utf-8')
                if not data:
                    break
                
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line:
                        try:
                            msg = json.loads(line)
                            self.message_queue.put(msg)
                            logger.debug(f"Received: {msg}")
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            conn.close()
            logger.info("RFID reader disconnected")
    
    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()

class VisionProcessor:
    def __init__(self, config: Config):
        self.config = config
        self.rfid_events = deque(maxlen=1000)
        self.containers = []
        self.active_container = None
        self.matches = []
        
        self.prev_gray = None
        self.present_streak = 0
        self.absent_streak = 0
        self.frame_id = 0
        
        self.kalman = self._create_kalman_filter()
        self.smoothed_box = None
        
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
        Path(f"{config.output_dir}/matched").mkdir(parents=True, exist_ok=True)
        Path(f"{config.output_dir}/unmatched").mkdir(parents=True, exist_ok=True)
    
    def _create_kalman_filter(self):
        kf = cv2.KalmanFilter(4, 2)
        kf.transitionMatrix = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ], dtype=np.float32)
        kf.measurementMatrix = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ], dtype=np.float32)
        kf.processNoiseCov = np.eye(4, dtype=np.float32) * 0.01
        kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 0.1
        return kf
    
    def add_rfid_event(self, tag_id: str, timestamp: float):
        self.rfid_events.append(RFIDEvent(tag_id, timestamp))
        self._cleanup_old_events()
    
    def _cleanup_old_events(self):
        cutoff = time.time() - self.config.rfid_buffer_seconds
        while self.rfid_events and self.rfid_events[0].timestamp < cutoff:
            self.rfid_events.popleft()
    
    def detect_container(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, self.config.blur_kernel, 0)
        
        if self.prev_gray is None:
            self.prev_gray = gray
            return None
        
        diff = cv2.absdiff(self.prev_gray, gray)
        _, thresh = cv2.threshold(diff, self.config.motion_threshold, 255, cv2.THRESH_BINARY)
        
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        thresh = cv2.dilate(thresh, kernel, iterations=1)
        
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        best_box = None
        max_area = 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.config.min_area or area > self.config.max_area:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            aspect = h / max(w, 1)
            
            if self.config.aspect_ratio_min <= aspect <= self.config.aspect_ratio_max:
                if area > max_area:
                    max_area = area
                    best_box = (x, y, w, h)
        
        self.prev_gray = gray
        
        if best_box:
            x, y, w, h = best_box
            cx, cy = x + w/2, y + h/2
            self.kalman.correct(np.array([[cx], [cy]], dtype=np.float32))
            
            if self.smoothed_box is None:
                self.smoothed_box = best_box
            else:
                alpha = 0.3
                sx, sy, sw, sh = self.smoothed_box
                self.smoothed_box = (
                    alpha * x + (1-alpha) * sx,
                    alpha * y + (1-alpha) * sy,
                    alpha * w + (1-alpha) * sw,
                    alpha * h + (1-alpha) * sh
                )
            
            return tuple(map(int, self.smoothed_box))
        
        return None
    
    def _score_focus(self, gray_roi: np.ndarray) -> float:
        lap = cv2.Laplacian(gray_roi, cv2.CV_64F)
        return float(lap.var())
    
    def process_frame(self, frame: np.ndarray):
        box = self.detect_container(frame)
        
        if box:
            self.present_streak += 1
            self.absent_streak = 0
            
            if self.present_streak >= self.config.presence_min_frames:
                if self.active_container is None:
                    self.active_container = ContainerEvent(
                        entry_time=time.time(),
                        exit_time=None,
                        frame_ids=[],
                        best_frames=[],
                        box_coordinates=[]
                    )
                    logger.info(f"Container entered at frame {self.frame_id}")
                
                self.active_container.frame_ids.append(self.frame_id)
                self.active_container.box_coordinates.append(box)
                
                x, y, w, h = box
                roi = frame[y:y+h, x:x+w]
                gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                score = self._score_focus(gray_roi)
                
                self.active_container.best_frames.append((score, frame.copy(), self.frame_id))
                self.active_container.best_frames.sort(key=lambda x: x[0], reverse=True)
                if len(self.active_container.best_frames) > self.config.capture_top_n:
                    self.active_container.best_frames = self.active_container.best_frames[:self.config.capture_top_n]
        else:
            self.absent_streak += 1
            self.present_streak = 0
            
            if self.absent_streak >= self.config.absence_min_frames:
                if self.active_container and self.active_container.exit_time is None:
                    self.active_container.exit_time = time.time()
                    self.containers.append(self.active_container)
                    logger.info(f"Container exited at frame {self.frame_id}")
                    
                    self._try_match_container(self.active_container)
                    self.active_container = None
                    self.smoothed_box = None
        
        self.frame_id += 1
    
    def _try_match_container(self, container: ContainerEvent):
        best_match = None
        best_confidence = 0
        
        for event in self.rfid_events:
            if event.processed:
                continue
            
            entry_offset = abs(event.timestamp - container.entry_time)
            exit_offset = abs(event.timestamp - container.exit_time) if container.exit_time else float('inf')
            
            confidence = 0
            if entry_offset <= self.config.entry_buffer_seconds:
                confidence += (1 - entry_offset / self.config.entry_buffer_seconds) * 0.5
            
            if exit_offset <= self.config.exit_buffer_seconds:
                confidence += (1 - exit_offset / self.config.exit_buffer_seconds) * 0.5
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = MatchResult(
                    tag_id=event.tag_id,
                    container=container,
                    confidence=confidence,
                    entry_offset=entry_offset,
                    exit_offset=exit_offset
                )
        
        if best_match:
            self._save_match(best_match)
            for event in self.rfid_events:
                if event.tag_id == best_match.tag_id:
                    event.processed = True
                    break
        else:
            self._save_unmatched(container)
    
    def _save_match(self, match: MatchResult):
        if match.confidence >= self.config.min_confidence:
            output_dir = f"{self.config.output_dir}/matched/{match.tag_id}"
        else:
            output_dir = f"{self.config.output_dir}/unmatched/{match.tag_id}_low_conf"
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        metadata = {
            "tag_id": match.tag_id,
            "confidence": round(match.confidence, 3),
            "entry_time": match.container.entry_time,
            "exit_time": match.container.exit_time,
            "transit_duration": round(match.container.exit_time - match.container.entry_time, 3) if match.container.exit_time else None,
            "entry_offset": round(match.entry_offset, 3),
            "exit_offset": round(match.exit_offset, 3),
            "frame_count": len(match.container.frame_ids),
            "best_frames": []
        }
        
        for i, (score, frame, frame_id) in enumerate(match.container.best_frames[:self.config.capture_top_n]):
            filename = f"frame_{i+1:02d}_id{frame_id}_score{int(score)}.jpg"
            filepath = f"{output_dir}/{filename}"
            
            if self.config.save_visualization and i < len(match.container.box_coordinates):
                vis = frame.copy()
                x, y, w, h = match.container.box_coordinates[i]
                cv2.rectangle(vis, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(vis, f"Tag: {match.tag_id[:8]}...", (x, y-10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                cv2.putText(vis, f"Conf: {match.confidence:.0%}", (x, y-25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                cv2.imwrite(filepath, vis)
            else:
                cv2.imwrite(filepath, frame)
            
            metadata["best_frames"].append({
                "filename": filename,
                "frame_id": frame_id,
                "focus_score": round(score, 2)
            })
        
        with open(f"{output_dir}/metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved match: {match.tag_id} (confidence: {match.confidence:.0%})")
    
    def _save_unmatched(self, container: ContainerEvent):
        timestamp = datetime.fromtimestamp(container.entry_time).strftime("%Y%m%d_%H%M%S")
        output_dir = f"{self.config.output_dir}/unmatched/no_tag_{timestamp}"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        metadata = {
            "tag_id": "UNMATCHED",
            "entry_time": container.entry_time,
            "exit_time": container.exit_time,
            "transit_duration": round(container.exit_time - container.entry_time, 3) if container.exit_time else None,
            "frame_count": len(container.frame_ids),
            "best_frames": []
        }
        
        for i, (score, frame, frame_id) in enumerate(container.best_frames[:self.config.capture_top_n]):
            filename = f"frame_{i+1:02d}_id{frame_id}.jpg"
            cv2.imwrite(f"{output_dir}/{filename}", frame)
            metadata["best_frames"].append({
                "filename": filename,
                "frame_id": frame_id,
                "focus_score": round(score, 2)
            })
        
        with open(f"{output_dir}/metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved unmatched container at {timestamp}")

class Application:
    def __init__(self):
        self.config = Config()
        self.processor = VisionProcessor(self.config)
        self.message_queue = queue.Queue()
        self.ipc_server = IPCServer(self.config.socket_path, self.message_queue)
        self.running = True
        
    def signal_handler(self, sig, frame):
        logger.info("Shutdown signal received")
        self.running = False
    
    def process_messages(self):
        while self.running:
            try:
                msg = self.message_queue.get(timeout=0.1)
                if msg.get("type") == "rfid":
                    self.processor.add_rfid_event(msg["tag_id"], msg["timestamp"])
                    logger.info(f"RFID event: {msg['tag_id']}")
            except queue.Empty:
                continue
    
    def run(self):
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        server_thread = threading.Thread(target=self.ipc_server.start, daemon=True)
        server_thread.start()
        
        msg_thread = threading.Thread(target=self.process_messages, daemon=True)
        msg_thread.start()
        
        try:
            from picamera2 import Picamera2
            picam = Picamera2()
            config = picam.create_preview_configuration(
                main={"size": (self.config.camera_width, self.config.camera_height), 
                      "format": "BGR888"},
                controls={"FrameRate": self.config.camera_fps}
            )
            picam.configure(config)
            picam.start()
            logger.info("Using Picamera2")
            use_picam = True
        except:
            cap = cv2.VideoCapture(self.config.camera_index)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.camera_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.camera_height)
            cap.set(cv2.CAP_PROP_FPS, self.config.camera_fps)
            logger.info("Using OpenCV VideoCapture")
            use_picam = False
        
        logger.info("Vision processor started")
        
        try:
            while self.running:
                if use_picam:
                    frame = picam.capture_array()
                else:
                    ret, frame = cap.read()
                    if not ret:
                        continue
                
                self.processor.process_frame(frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        
        finally:
            if use_picam:
                picam.stop()
            else:
                cap.release()
            
            cv2.destroyAllWindows()
            self.ipc_server.stop()
            logger.info("Application shutdown complete")

if __name__ == "__main__":
    app = Application()
    app.run()