# ============================================================================
# Module: detection.py
# Mô tả: Module nhận diện đối tượng trong game Brawl Stars sử dụng YOLO (You Only Look Once).
#         Module này chạy trong thread riêng, liên tục nhận diện 3 loại đối tượng:
#         - Player: Nhân vật người chơi (dựa trên bảng tên)
#         - Bush: Bụi cỏ (nơi ẩn nấp)
#         - Enemy: Kẻ địch
#         Ngoài ra còn có chức năng vẽ annotation debug (dấu chữ thập, viền, FPS).
# ============================================================================

from threading import Thread, Lock
from time import time
import cv2 as cv
from constants import Constants
from ultralytics import YOLO

class Detection:
    # === Thuộc tính điều khiển thread ===
    stopped = True       # Thread đã dừng hay chưa
    lock = None          # Lock để đồng bộ hóa (thread-safe)

    # === Thuộc tính dữ liệu ===
    screenshot = None            # Ảnh chụp màn hình hiện tại để nhận diện
    results = None               # Kết quả nhận diện: [[player_coords], [bush_coords], [enemy_coords]]
    fps = 0                      # FPS hiện tại của thread nhận diện
    avg_fps = 0                  # FPS trung bình
    player_topleft = None        # Góc trên-trái bounding box nhân vật (dùng kiểm tra HP)
    player_bottomright = None    # Góc dưới-phải bounding box nhân vật
    # Offset dọc để căn chỉnh vị trí nhân vật (game có hơi lệch so với tâm thực)
    midpoint_offset = Constants.midpoint_offset

    def __init__(self, windowSize, model_file_path, classes, heightScaleFactor):
        """
        Hàm khởi tạo Detection.
        
        :param windowSize (tuple): Kích thước cửa sổ game (width, height)
        :param model_file_path (str): Đường dẫn đến file model YOLO đã huấn luyện
        :param classes (list): Danh sách tên lớp ["Player", "Bush", "Enemy", "Cubebox"]
        :param heightScaleFactor (float): Hệ số dịch chuyển dọc cho vị trí nhân vật
                                           (mỗi brawler có chiều cao khác nhau)
        """
        # Tạo khóa thread để đảm bảo an toàn khi truy cập dữ liệu từ nhiều thread
        self.lock = Lock()
        # Tải model YOLO đã huấn luyện (hỗ trợ PyTorch, OpenVINO, TensorRT)
        self.model = YOLO(model_file_path,task="detect")
        # Danh sách tên các lớp đối tượng cần nhận diện
        self.classes = classes
        self.windowSize = windowSize
        self.w = windowSize[0]  # Chiều rộng cửa sổ
        self.h = windowSize[1]  # Chiều cao cửa sổ
        # Khoảng dịch chuyển theo chiều cao - dùng để điều chỉnh vị trí midpoint
        # của nhân vật (từ bảng tên xuống vị trí thực của nhân vật trên bản đồ)
        self.height = heightScaleFactor * self.h

    def find_midpoint(self,x1,y1,x2,y2):
        """
        Tìm điểm giữa (midpoint) của bounding box.
        
        Bounding box có tọa độ (x1,y1) là góc trên-trái và (x2,y2) là góc dưới-phải.
        Điểm giữa được dùng làm tọa độ đại diện cho đối tượng.
        
        :param x1 (int): Tọa độ x góc trên-trái
        :param y1 (int): Tọa độ y góc trên-trái
        :param x2 (int): Tọa độ x góc dưới-phải (x2 > x1)
        :param y2 (int): Tọa độ y góc dưới-phải (y2 > y1)
        :return (list): Danh sách chứa 1 tuple (mid_x, mid_y)
        """
        return [(x1+int((x2-x1)/2),y1+int((y2-y1)/2))]

    def annotate_detection_midpoint(self):
        """
        Vẽ dấu chữ thập (marker) tại điểm giữa của mỗi đối tượng được nhận diện.
        Dùng cho mục đích debug - hiển thị vị trí các đối tượng trên ảnh.
        
        - Mỗi đối tượng được đánh dấu bằng dấu + màu đỏ
        - Kèm nhãn tên lớp (Player/Bush/Enemy)
        """
        thickness = 1
        red = (0, 0, 255)  # Màu đỏ (BGR format trong OpenCV)
        if self.results:
            for i in range(len(self.results)):
                    # Kiểm tra danh sách không rỗng
                    if self.results[i]:
                        for cord in self.results[i]:
                            # Vẽ dấu chữ thập tại điểm giữa đối tượng
                            cv.drawMarker(self.screenshot, cord,
                                           red ,thickness=thickness,
                                           markerType= cv.MARKER_CROSS,
                                           line_type=cv.LINE_AA, markerSize=50)
                            # Hiển thị tên lớp bên cạnh marker
                            cv.putText(self.screenshot, self.classes[i],
                                       cord, cv.FONT_HERSHEY_SIMPLEX, 0.7, red, 2)

    def annotate_border(self,border_size,tile_w,tile_h):
        """
        Vẽ viền border và lưới quadrant lên ảnh cho mục đích debug.
        
        - Hình chữ nhật xanh: Vùng an toàn ở trung tâm (ngoài vùng này là gần bão)
        - Dấu chữ thập xanh: Tâm màn hình
        - Lưới 3x3: Chia màn hình thành 9 vùng để chọn bụi cỏ tránh bão
        
        :param border_size (int): Kích thước vùng biên (tile)
        :param tile_w (int): Số tile theo chiều ngang
        :param tile_h (int): Số tile theo chiều dọc
        """
        thickness = 2
        green = (0, 255, 0)  # Màu xanh lá (BGR)
        # Tính kích thước 1/3 màn hình cho lưới quadrant
        x_scale = int(self.w/3)
        y_scale = int(self.h/3)
        # Tính kích thước 1 tile theo pixel
        xBorder = (self.w/tile_w)
        yBorder = (self.h/tile_h)
        size = 2*border_size
        # Tính tọa độ hình chữ nhật vùng an toàn (trung tâm)
        xTop = int(xBorder*((tile_w-size)/2))
        yTop = int(yBorder*((tile_h-size)/2))+self.midpoint_offset
        xBottom = int(xBorder*((tile_w+size)/2))
        yBottom = int(yBorder*((tile_h+size)/2))+self.midpoint_offset
        
        # Vẽ hình chữ nhật vùng an toàn
        cv.rectangle(self.screenshot, (xTop, yTop), (xBottom, yBottom), (0,255,0), 2)
        # Vẽ dấu chữ thập tại tâm màn hình
        cv.drawMarker(self.screenshot, (int(self.w/2),int((self.h/2)+self.midpoint_offset)),
                    green ,thickness=thickness,markerType= cv.MARKER_CROSS,
                    line_type=cv.LINE_AA, markerSize=50)
        # Vẽ lưới chia 3x3 (quadrant lines)
        cv.line(self.screenshot,(x_scale,0),(x_scale,3*y_scale),green,thickness)       # Đường dọc trái
        cv.line(self.screenshot,(2*x_scale,0),(2*x_scale,3*y_scale),green,thickness)   # Đường dọc phải
        cv.line(self.screenshot,(0,y_scale),(3*x_scale,y_scale),green,thickness)       # Đường ngang trên
        cv.line(self.screenshot,(0,2*y_scale),(3*x_scale,2*y_scale),green,thickness)   # Đường ngang dưới
     
    def annotate_fps(self,wincap_avg_fps):
        """
        Hiển thị thông tin FPS lên ảnh chụp.
        
        Vẽ hộp đen ở góc dưới-trái và hiển thị:
        - Detection FPS: Tốc độ nhận diện YOLO (bao nhiêu frame/giây)
        - WindowCapture FPS: Tốc độ chụp màn hình
        
        :param wincap_avg_fps (float): FPS trung bình của WindowCapture
        """
        # Tính hệ số tỉ lệ dựa trên kích thước cửa sổ (để FPS text co giãn phù hợp)
        scale = (self.windowSize[0]+self.windowSize[1])/(1145+644)
        # Vẽ hình chữ nhật đen ở góc dưới-trái làm nền cho text FPS
        rect_w = int(180*scale)
        rect_h = int(60*scale)
        cv.rectangle(self.screenshot,(0,self.windowSize[1]),
                        (rect_w, self.windowSize[1] - rect_h), (0, 0, 0), -1)
        # Thiết lập font chữ
        fontScale = 0.7*scale
        spacing = int(10*scale)
        thickness = 1
        # Hiển thị FPS của Detection (nhận diện YOLO)
        cv.putText(self.screenshot,text=f"Detect: {int(self.avg_fps)}",
                    org=(0+spacing,self.windowSize[1]-spacing-int(30*scale)),fontFace=cv.FONT_HERSHEY_SIMPLEX,fontScale=fontScale,
                    color=(255,255,255),thickness=thickness)
        cv.putText(self.screenshot,text=f"FPS",
                    org=(0+spacing+int(scale*140),self.windowSize[1]-spacing-int(30*scale)),fontFace=cv.FONT_HERSHEY_SIMPLEX,fontScale=0.5*fontScale,
                    color=(255,255,255),thickness=thickness)
        # Hiển thị FPS của WindowCapture (chụp màn hình)
        cv.putText(self.screenshot,text=f"Wincap: {int(wincap_avg_fps)}",
                    org=(0+spacing,self.windowSize[1]-spacing),fontFace=cv.FONT_HERSHEY_SIMPLEX,fontScale=fontScale,
                    color=(255,255,255),thickness=thickness)
        cv.putText(self.screenshot,text=f"FPS",
                    org=(0+spacing+int(scale*140),self.windowSize[1]-spacing),fontFace=cv.FONT_HERSHEY_SIMPLEX,fontScale=0.5*fontScale,
                    color=(255,255,255),thickness=thickness)
    
    def update(self, screenshot):
        """
        Cập nhật ảnh chụp màn hình mới cho thread nhận diện.
        Gọi từ main loop mỗi frame.
        
        :param screenshot: Ảnh chụp màn hình (numpy array BGR)
        """
        self.lock.acquire()
        self.screenshot = screenshot
        self.lock.release()

    def start(self):
        """
        Khởi động thread nhận diện YOLO.
        Thread chạy ở chế độ daemon.
        """
        self.stopped = False
        self.loop_time = time()
        self.count = 0
        t = Thread(target=self.run)
        t.setDaemon(True)
        t.start()

    def stop(self):
        """
        Dừng thread nhận diện.
        """
        self.stopped = True

    def run(self):
        """
        Vòng lặp chính của thread nhận diện.
        
        Mỗi vòng lặp:
        1. Chạy YOLO predict trên ảnh chụp hiện tại
        2. Với mỗi bounding box kết quả:
           - Lọc theo ngưỡng confidence (threshold)
           - Tính điểm giữa (midpoint) của bounding box
           - Điều chỉnh vị trí midpoint cho Player và Enemy
        3. Cập nhật kết quả vào self.results (thread-safe)
        4. Tính FPS
        """
        while not self.stopped:
            if not self.screenshot is None:
                # Tạo danh sách rỗng cho mỗi lớp đối tượng
                # tempList = [[], [], [], []] tương ứng Player, Bush, Enemy, Cubebox
                tempList = len(self.classes)*[[]]
                
                # Chạy YOLO inference trên ảnh chụp
                # imgsz: kích thước ảnh input cho model
                # half: dùng FP16 hay không (nhanh hơn với GPU)
                # verbose: tắt log chi tiết
                results = self.model.predict(self.screenshot, imgsz=Constants.imgsz,
                                             half=Constants.half, verbose=False)
                result = results[0]  # Lấy kết quả frame đầu tiên
                
                # Duyệt qua từng bounding box được phát hiện
                for box in result.boxes:
                    # Lấy tọa độ 4 góc: (x1,y1) trên-trái, (x2,y2) dưới-phải
                    x1, y1, x2, y2 = [round(x) for x in box.xyxy[0].tolist()]
                    # ID lớp đối tượng (0=Player, 1=Bush, 2=Enemy, 3=Cubebox)
                    class_id = int(box.cls[0].item())
                    # Độ tin cậy của dự đoán (0-1)
                    prob = round(box.conf[0].item(), 2)
                    # Ngưỡng tin cậy tối thiểu cho lớp này
                    threshold = Constants.threshold[class_id]
                    
                    # Chỉ xử lý nếu vượt ngưỡng tin cậy
                    if prob >= threshold:
                        # Tính điểm giữa bounding box
                        midpoint = self.find_midpoint(x1,y1,x2,y2)
                        
                        if self.classes[class_id] == "Player":
                            # === Xử lý đặc biệt cho Player ===
                            # YOLO nhận diện bảng tên nhân vật (ở trên đầu)
                            # Cần dịch midpoint xuống dưới (vào thân nhân vật) 
                            # để có vị trí chính xác trên bản đồ
                            self.player_topleft = (x1,y1)         # Lưu bounding box cho kiểm tra HP
                            self.player_bottomright = (x2,y2)
                            # Dịch midpoint xuống theo heightScaleFactor
                            midpoint =  [( midpoint[0][0], int(midpoint[0][1] + self.height))]
                        
                        if self.classes[class_id] == "Enemy":
                            # === Xử lý đặc biệt cho Enemy ===
                            # Tương tự Player, cần điều chỉnh vị trí midpoint
                            # từ bảng tên xuống vị trí thực của kẻ địch
                            enemy_height = y2 - y1
                            y1 = y1 + (enemy_height+0.2*self.h)
                            midpoint = [( midpoint[0][0], int(midpoint[0][1] + 0.05*self.h))]
                        
                        # Thêm midpoint vào danh sách tương ứng với lớp
                        tempList[class_id] = tempList[class_id] + midpoint
                
                # Cập nhật kết quả an toàn (thread-safe) bằng Lock
                self.lock.acquire()
                self.results = tempList
                self.lock.release()
                
                # Tính FPS và FPS trung bình
                self.fps = (1 / (time() - self.loop_time))
                self.loop_time = time()
                self.count += 1
                if self.count == 1:
                    self.avg_fps = self.fps
                else:
                    # Tính trung bình cộng dồn (running average)
                    self.avg_fps = (self.avg_fps*self.count+self.fps)/(self.count + 1)