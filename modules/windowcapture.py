# ============================================================================
# Module: windowcapture.py
# Mô tả: Module chụp ảnh màn hình cửa sổ BlueStacks sử dụng Win32 API.
#         Module này chạy trong thread riêng, liên tục chụp màn hình cửa sổ game
#         và cung cấp ảnh (numpy array) cho các module khác xử lý.
#         
#         Sử dụng Win32 API (win32gui, win32ui) thay vì screenshot thông thường
#         để đạt FPS cao hơn và hỗ trợ chụp cửa sổ bị che khuất (background capture).
# ============================================================================

import numpy as np
import win32gui, win32ui, win32con,win32com.client
from threading import Thread, Lock
from ctypes import windll
import tkinter
from time import time
from constants import Constants

class WindowCapture:

    # === Thuộc tính điều khiển thread ===
    stopped = True       # Thread đã dừng hay chưa
    lock = None          # Lock cho thread-safe
    screenshot = None    # Ảnh chụp màn hình mới nhất (numpy array BGR)
    
    # === Thuộc tính kích thước cửa sổ ===
    w = 0                # Chiều rộng cửa sổ (không bao gồm viền)
    h = 0                # Chiều cao cửa sổ (không bao gồm viền + thanh tiêu đề)
    hwnd = None          # Handle (số nhận dạng) của cửa sổ
    cropped_x = 0        # Pixel cần cắt theo chiều ngang (viền trái)
    cropped_y = 0        # Pixel cần cắt theo chiều dọc (thanh tiêu đề)
    offset_x = 0         # Offset X: vị trí thực bắt đầu nội dung game trên màn hình
    offset_y = 0         # Offset Y: vị trí thực bắt đầu nội dung game trên màn hình
    fps = 0              # FPS hiện tại
    avg_fps = 0          # FPS trung bình

    def __init__(self, window_name=None):
        """
        Hàm khởi tạo WindowCapture.
        
        Quy trình:
        1. Xử lý DPI scaling (Windows scale 125%, 150%...)
        2. Tìm handle của cửa sổ BlueStacks
        3. Tính kích thước thực của cửa sổ (trừ viền + thanh tiêu đề)
        4. Tính offset để chuyển đổi tọa độ ảnh -> tọa độ màn hình
        
        :param window_name (str|None): Tên cửa sổ cần chụp. None = chụp toàn màn hình.
        """
        # === XỬ LÝ DPI SCALING ===
        # Windows có thể scale giao diện (125%, 150%), làm sai tọa độ
        # SetProcessDPIAware() giúp lấy tọa độ pixel thực, không bị scale
        # Tham khảo: https://stackoverflow.com/a/45911849
        user32 = windll.user32
        user32.SetProcessDPIAware()
        
        # Lấy DPI hiện tại của màn hình bằng tkinter
        root = tkinter.Tk()
        dpi = root.winfo_fpixels('1i')  # Số pixel trên 1 inch
        deafault_dpi = 96               # DPI mặc định Windows (100% scale)
        self.scaling = int(dpi/deafault_dpi)  # Hệ số scale (1, 2, 3...)
        root.destroy()  # Đóng cửa sổ tkinter (chỉ dùng để lấy DPI)
        
        # Tạo khóa thread
        self.lock = Lock()
        
        # === TÌM HANDLE CỬA SỔ ===
        if window_name is None:
            # Không có tên cửa sổ -> chụp toàn bộ desktop
            self.hwnd = win32gui.GetDesktopWindow()
        else:
            # Tìm cửa sổ theo tên (ví dụ: "Bluestacks App Player")
            self.hwnd = win32gui.FindWindow(None, window_name)
            if not self.hwnd:
                raise Exception(f"{window_name} not found. \nPlease open {window_name} or change the window_name at constants.py")

        # === TÍNH KÍCH THƯỚC CỬA SỔ ===
        # GetWindowRect trả về (left, top, right, bottom) bao gồm cả viền
        window_rect = win32gui.GetWindowRect(self.hwnd)
        self.w = window_rect[2] - window_rect[0]  # Chiều rộng tổng
        self.h = window_rect[3] - window_rect[1]  # Chiều cao tổng
        
        # Lưu tọa độ 4 góc cửa sổ (dùng để xác định vùng thoát bot)
        self.left = window_rect[0]      # Viền trái
        self.top = window_rect[1]       # Viền trên
        self.right = window_rect[2]     # Viền phải
        self.bottom = window_rect[3]    # Viền dưới
        
        # Độ phân giải toàn bộ màn hình (dùng để xác định vùng thoát)
        self.screen_resolution = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

        # === CẮT VIỀN VÀ THANH TIÊU ĐỀ ===
        # Cửa sổ Windows có viền (border) và thanh tiêu đề (titlebar)
        # Cần loại bỏ chúng để chỉ lấy phần nội dung game
        self.border_pixels = int(1*self.scaling)      # Viền thường dày 1 pixel (nhân scaling)
        self.titlebar_pixels = int(33*self.scaling)    # Thanh tiêu đề thường cao 33 pixel
        self.w = self.w - (self.border_pixels * 2)     # Trừ viền trái + phải
        self.h = self.h - self.titlebar_pixels - self.border_pixels  # Trừ thanh tiêu đề + viền dưới
        self.cropped_x = self.border_pixels            # Vị trí bắt đầu cắt ngang
        self.cropped_y = self.titlebar_pixels           # Vị trí bắt đầu cắt dọc

        # === TÍNH OFFSET TỌA ĐỘ ===
        # Offset = vị trí góc trên-trái của nội dung game trên màn hình
        # Dùng để chuyển tọa độ pixel trong ảnh -> tọa độ click trên màn hình
        self.offset_x = window_rect[0] + self.cropped_x
        self.offset_y = window_rect[1] + self.cropped_y
        self.offsets = (self.offset_x,self.offset_y)

        # === CẤU HÌNH CHỤP FOREGROUND vs BACKGROUND ===
        if Constants.focused_window:
            # True: Chụp cửa sổ trực tiếp bằng handle (chỉ hoạt động khi cửa sổ ở foreground)
            self.window = self.hwnd
            self.cropped = (self.cropped_x,self.cropped_y)
        else:
            # False: Chụp toàn màn hình rồi crop (hoạt động cả khi cửa sổ bị che)
            self.window = None
            self.cropped = (self.offset_x,self.offset_y)
    
    def set_window(self):
        """
        Đưa cửa sổ BlueStacks lên foreground (nổi trên cùng).
        
        Trick: Dùng WScript.Shell.SendKeys('%') để gửi phím Alt trước
        rồi mới SetForegroundWindow - tránh lỗi Windows không cho phép
        ứng dụng tự ý chiếm foreground.
        Tham khảo: https://stackoverflow.com/a/15503675
        """
        if self.hwnd:
            shell = win32com.client.Dispatch("WScript.Shell")
            shell.SendKeys('%')  # Gửi Alt key
            win32gui.SetForegroundWindow(self.hwnd)

    def get_dimension(self):
        """
        Lấy kích thước nội dung cửa sổ game (đã trừ viền và thanh tiêu đề).
        
        :return (tuple): (width, height) tính bằng pixel
        """
        return self.w,self.h

    def get_screenshot(self):
        """
        Chụp ảnh màn hình cửa sổ game bằng Win32 API.
        
        Quy trình:
        1. Lấy Device Context (DC) của cửa sổ
        2. Tạo compatible DC và Bitmap trong bộ nhớ
        3. BitBlt: Copy pixel từ cửa sổ vào bitmap (rất nhanh, sử dụng GPU)
        4. Chuyển bitmap thành numpy array
        5. Loại bỏ kênh alpha (BGRA -> BGR) vì OpenCV không cần
        6. Giải phóng tài nguyên Win32
        
        :return (numpy.ndarray): Ảnh chụp dạng BGR, kích thước (h, w, 3)
        """
        # Lấy Device Context (DC) - đối tượng đại diện cho bề mặt vẽ của cửa sổ
        wDC = win32gui.GetWindowDC(self.window)
        dcObj = win32ui.CreateDCFromHandle(wDC)
        # Tạo compatible DC trong bộ nhớ (cho BitBlt)
        cDC = dcObj.CreateCompatibleDC()
        # Tạo bitmap để lưu ảnh chụp
        dataBitMap = win32ui.CreateBitmap()
        dataBitMap.CreateCompatibleBitmap(dcObj, self.w, self.h)
        cDC.SelectObject(dataBitMap)
        # BitBlt: Copy pixel từ cửa sổ vào bitmap
        # self.cropped: vị trí bắt đầu copy (bỏ viền + thanh tiêu đề)
        cDC.BitBlt((0, 0), (self.w, self.h), dcObj, self.cropped, win32con.SRCCOPY)

        # Chuyển bitmap thành numpy array
        signedIntsArray = dataBitMap.GetBitmapBits(True)
        img = np.fromstring(signedIntsArray, dtype='uint8')
        img.shape = (self.h, self.w, 4)  # BGRA format (4 kênh)

        # Giải phóng tài nguyên Win32 (rất quan trọng - tránh memory leak)
        dcObj.DeleteDC()
        cDC.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, wDC)
        win32gui.DeleteObject(dataBitMap.GetHandle())

        # Loại bỏ kênh alpha (kênh thứ 4)
        # OpenCV cv.matchTemplate() chỉ chấp nhận 3 kênh (BGR)
        img = img[...,:3]

        # Đảm bảo array là C_CONTIGUOUS (liên tục trong bộ nhớ)
        # Tránh lỗi TypeError khi vẽ bằng OpenCV
        # Tham khảo: https://github.com/opencv/opencv/issues/14866#issuecomment-580207109
        img = np.ascontiguousarray(img)

        return img

    @staticmethod
    def list_window_names():
        """
        Liệt kê tên tất cả cửa sổ đang mở trên Windows.
        Dùng để tìm tên chính xác của cửa sổ BlueStacks.
        
        Cách dùng: WindowCapture.list_window_names()
        
        Tham khảo: https://stackoverflow.com/questions/55547940/
        """
        def winEnumHandler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                print(hex(hwnd), f"\"{win32gui.GetWindowText(hwnd)}\"")
        win32gui.EnumWindows(winEnumHandler, None)

    # ============================================================================
    # PHẦN ĐIỀU KHIỂN THREAD - Khởi động, dừng, và vòng lặp chụp màn hình
    # ============================================================================
    
    def start(self):
        """
        Khởi động thread chụp màn hình liên tục.
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
        Dừng thread chụp màn hình.
        """
        self.stopped = True

    def run(self):
        """
        Vòng lặp chính - Chụp màn hình liên tục.
        
        Mỗi vòng lặp:
        1. Chụp ảnh mới từ cửa sổ game
        2. Cập nhật self.screenshot (thread-safe)
        3. Tính FPS và FPS trung bình
        """
        while not self.stopped:
            # Chụp ảnh màn hình mới
            screenshot = self.get_screenshot()
            # Cập nhật ảnh an toàn (dùng Lock tránh xung đột với thread khác)
            self.lock.acquire()
            self.screenshot = screenshot
            self.lock.release()
            
            # Tính FPS và FPS trung bình
            self.fps = (1 / (time() - self.loop_time))
            self.loop_time = time()
            self.count += 1
            if self.count == 1:
                self.avg_fps = self.fps
            else:
                # Trung bình cộng dồn (running average)
                self.avg_fps = (self.avg_fps*self.count+self.fps)/(self.count + 1)