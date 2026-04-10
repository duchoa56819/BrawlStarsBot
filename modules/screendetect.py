# ============================================================================
# Module: screendetect.py
# Mô tả: Module phát hiện trạng thái màn hình game Brawl Stars.
#         Sử dụng pyautogui.pixelMatchesColor() để kiểm tra màu pixel tại
#         các vị trí cụ thể trên màn hình, từ đó xác định trạng thái game:
#         - Bị loại (defeated) -> thoát trận
#         - Nút chơi lại (play again) -> bấm chơi lại
#         - Đang tải trận (loading) -> khởi động bot
#         - Star Drop -> thu thập star drop
#         - Mất kết nối -> bấm tải lại
#         Module này chạy trong thread riêng, liên tục kiểm tra màn hình.
# ============================================================================

import pyautogui as py
from threading import Thread, Lock
from time import sleep
from constants import Constants

"""
Mô tả các trạng thái của Screendetect:

IDLE: Trạng thái nghỉ - sau khi xử lý xong một sự kiện, chờ 3 giây rồi quay lại DETECT
      (tránh spam terminal và cho game thời gian chuyển màn hình)

DETECT: Trạng thái chủ động kiểm tra - liên tục kiểm tra màu pixel tại các vị trí
        để phát hiện trạng thái game (thua, play again, loading, star drop...)

EXIT: Khi phát hiện nhân vật bị loại - chờ 5 giây rồi bấm nút thoát trận

PLAY_AGAIN: Khi phát hiện nút "Play Again" xuất hiện - bấm nút để tìm trận mới

LOAD: Khi phát hiện đang tải vào trận mới - thông báo cho main.py để khởi động bot

CONNECTION: Khi phát hiện mất kết nối - chờ 20 giây rồi bấm nút tải lại

PLAY: Khi phát hiện đang ở menu chính (nút Play) - bấm nút Play để tìm trận

PROCEED: Khi phát hiện nút Proceed (sau kết thúc trận) - bấm để tiếp tục

STARDROP: Khi phát hiện Star Drop ở menu chính - nhấn 'e' để mở và thu thập
"""
class Detectstate:
    IDLE = 0          # Nghỉ, chờ chuyển về DETECT
    DETECT = 1        # Đang kiểm tra màn hình
    EXIT = 2          # Phát hiện bị loại
    PLAY_AGAIN = 3    # Phát hiện nút Play Again
    LOAD = 4          # Phát hiện đang tải trận
    CONNECTION = 5    # Phát hiện mất kết nối
    PLAY = 6          # Phát hiện menu chính (nút Play)
    PROCEED = 7       # Phát hiện nút Proceed
    STARDROP = 8      # Phát hiện Star Drop
    
class Screendetect:
    # === Màu RGB để so khớp pixel - dùng nhận diện các nút/trạng thái ===
    defeatedColor = (62,0,0)             # Màu đỏ đậm khi bị loại (viền đỏ trên màn hình)
    playColor = (224, 186, 8)            # Màu vàng của nút Play / Play Again
    loadColor = (0, 1, 0)               # Màu xanh đậm khi đang tải trận
    proceedColor = (35, 115, 255)        # Màu xanh dương nút Proceed
    connection_lost_color = (66, 66, 66) # Màu xám khi mất kết nối
    starDropColor = (222, 72, 227)       # Màu hồng/tím của Star Drop

    def __init__(self,windowSize,offset) -> None:
        """
        Hàm khởi tạo Screendetect.
        
        Tính toán tọa độ pixel cần kiểm tra dựa trên kích thước cửa sổ game.
        Các tọa độ được tính theo tỉ lệ phần trăm (%) để phù hợp mọi độ phân giải.
        
        :param windowSize (tuple): Kích thước cửa sổ game (width, height)
        :param offset (tuple): Offset cửa sổ so với màn hình (offset_x, offset_y)
        """
        self.state = Detectstate.DETECT  # Bắt đầu ở trạng thái kiểm tra
        self.lock = Lock()               # Lock cho thread-safe
        self.w = windowSize[0]           # Chiều rộng cửa sổ
        self.h = windowSize[1]           # Chiều cao cửa sổ
        self.offset_x = offset[0]        # Offset X cửa sổ
        self.offset_y = offset[1]        # Offset Y cửa sổ

        # === Tọa độ pixel cần kiểm tra (tính theo tỉ lệ % kích thước cửa sổ + offset) ===
        
        # 2 điểm kiểm tra trạng thái "bị loại" (viền đỏ ở góc phải trên)
        self.defeated1 = (round(self.w*0.9656)+self.offset_x, round(self.h*0.152)+self.offset_y)
        self.defeated2 = (round(self.w*0.993)+self.offset_x, round(self.h*0.2046)+self.offset_y)

        # 2 điểm kiểm tra Star Drop (ở giữa phía dưới màn hình)
        self.starDrop1 = (round(self.w*0.488)+ self.offset_x, round(self.h*0.9303) + self.offset_y)
        self.starDrop2 = (round(self.w*0.5228)+ self.offset_x, round(self.h*0.9296) + self.offset_y)

        # Tọa độ các nút bấm trên màn hình
        self.playAgainButton = (round(self.w*0.5903)+self.offset_x, round(self.h*0.9197)+self.offset_y)  # Nút Play Again
        self.playButton = (round(self.w*0.9419)+self.offset_x, round(self.h*0.8949)+self.offset_y)       # Nút Play (menu chính)
        self.exitButton = (round(self.w*0.493)+self.offset_x, round(self.h*0.9187)+self.offset_y)        # Nút Exit (sau khi thua)
        self.loadButton = (round(self.w*0.8057)+self.offset_x, round(self.h*0.9675)+self.offset_y)       # Điểm kiểm tra đang tải
        self.proceedButton = (round(self.w*0.8093)+self.offset_x, round(self.h*0.9165)+self.offset_y)    # Nút Proceed

        # Tọa độ cho xử lý mất kết nối
        self.connection_lost_cord = (round(self.w*0.4912)+self.offset_x,round(self.h*0.5525)+self.offset_y)  # Điểm kiểm tra popup mất kết nối
        self.reload_button = (round(self.w*0.2824)+self.offset_x,round(self.h*0.5812)+self.offset_y)         # Nút Reload

    def update_bot_stop(self,bot_stopped):
        """
        Cập nhật trạng thái bot (đang chạy hay đã dừng).
        Dùng để tránh xử lý thua trận khi bot đã dừng.
        
        :param bot_stopped (bool): True nếu bot đã dừng
        """
        self.bot_stopped = bot_stopped
    
    def start(self):
        """
        Khởi động thread phát hiện trạng thái màn hình.
        Thread chạy ở chế độ daemon.
        """
        self.stopped = False
        t = Thread(target=self.run)
        t.setDaemon(True)
        t.start()

    def stop(self):
        """
        Dừng thread phát hiện.
        """
        self.stopped = True

    def run(self):
        """
        Vòng lặp chính của thread phát hiện trạng thái màn hình.
        
        Hoạt động theo máy trạng thái:
        DETECT -> Kiểm tra pixel liên tục -> phát hiện sự kiện -> chuyển sang trạng thái tương ứng
        Mỗi trạng thái -> xử lý hành động -> quay về IDLE -> chờ 3 giây -> DETECT
        """
        while not self.stopped:
            sleep(0.01)  # Nghỉ 10ms mỗi vòng lặp
            
            # === TRẠNG THÁI IDLE: Chờ 3 giây rồi quay lại DETECT ===
            if self.state == Detectstate.IDLE:
                sleep(3)  # Chờ 3 giây để game chuyển màn hình
                self.state = Detectstate.DETECT
            
            # === TRẠNG THÁI DETECT: Kiểm tra pixel liên tục ===
            elif self.state == Detectstate.DETECT:
                try:
                    # Kiểm tra 1: Nút Play Again (sau khi thua/thắng)
                    if py.pixelMatchesColor(self.playAgainButton[0], self.playAgainButton[1],self.playColor,tolerance=15):
                        print("Playing again")
                        self.lock.acquire()
                        self.state = Detectstate.PLAY_AGAIN
                        self.lock.release()
                    
                    # Kiểm tra 2: Đang tải vào trận mới (màn hình loading)
                    elif py.pixelMatchesColor(self.loadButton[0], self.loadButton[1],self.loadColor,tolerance=30):
                        print("Loading in")
                        self.lock.acquire()
                        sleep(3)  # Chờ thêm 3 giây cho tải xong
                        self.state = Detectstate.LOAD
                        self.lock.release()
                    
                    # Kiểm tra 3: Bị loại (viền đỏ trên màn hình) - chỉ khi bot đang chạy
                    elif (py.pixelMatchesColor(self.defeated1[0], self.defeated1[1],
                                                     self.defeatedColor,tolerance=15)
                        or py.pixelMatchesColor(self.defeated2[0], self.defeated2[1],
                                                     self.defeatedColor,tolerance=15)) and not(self.bot_stopped):
                        print("Exiting match")
                        self.lock.acquire()
                        self.state = Detectstate.EXIT
                        self.lock.release()
                    
                    # Kiểm tra 4: Mất kết nối (đã tạm vô hiệu hóa - comment out)
                    # elif pyautogui.pixelMatchesColor(self.connection_lost_cord[0],self.connection_lost_cord[1],self.connection_lost_color,tolerance=1):
                    #     print("Connection Lost")
                    #     self.lock.acquire()
                    #     self.state = Detectstate.CONNECTION
                    #     self.lock.release()
                    
                    # Kiểm tra 5: Star Drop (phần thưởng ở menu chính)
                    elif (py.pixelMatchesColor(self.starDrop1[0], self.starDrop1[1], self.starDropColor,tolerance=15)
                    or py.pixelMatchesColor(self.starDrop2[0], self.starDrop2[1], self.starDropColor,tolerance=15)):
                        print("Collecting Star Drop")
                        self.lock.acquire()
                        self.state = Detectstate.STARDROP
                        self.lock.release()
                        
                    # Kiểm tra 6: Nút Play ở menu chính
                    elif py.pixelMatchesColor(self.playButton[0], self.playButton[1], self.playColor, tolerance=15):
                        print("Play")
                        self.lock.acquire()
                        self.state = Detectstate.PLAY
                        self.lock.release()

                    # Kiểm tra 7: Nút Proceed (sau kết thúc trận)
                    elif py.pixelMatchesColor(self.proceedButton[0], self.proceedButton[1], self.proceedColor, tolerance=25):
                        print("Proceed")
                        self.lock.acquire()
                        self.state = Detectstate.PROCEED
                        self.lock.release()
                
                except OSError:
                    pass  # Bỏ qua lỗi khi pixel nằm ngoài màn hình hoặc lỗi hệ thống
                        
            # === XỬ LÝ: Bấm nút Play Again ===
            elif self.state == Detectstate.PLAY_AGAIN:
                sleep(0.05)
                py.click(x=self.playAgainButton[0], y=self.playAgainButton[1], button="left")
                sleep(0.05)
                self.lock.acquire()
                self.state = Detectstate.IDLE  # Quay về IDLE chờ
                self.lock.release()
            
            # === XỬ LÝ: Đã phát hiện loading - thông báo cho main loop ===
            elif self.state == Detectstate.LOAD:
                sleep(0.1)
                self.lock.acquire()
                self.state = Detectstate.IDLE
                self.lock.release()
            
            # === XỬ LÝ: Bị loại - chờ animation rồi bấm Exit ===
            elif self.state == Detectstate.EXIT:
                # Thả phím chuột di chuyển (dừng nhân vật)
                py.mouseUp(button = Constants.movement_key)
                sleep(5)  # Chờ 5 giây cho animation kết thúc trận
                # Bấm nút Exit để thoát trận
                py.click(x=self.exitButton[0], y=self.exitButton[1], button="left")
                sleep(0.05)
                self.lock.acquire()
                self.state = Detectstate.IDLE
                self.lock.release()
            
            # === XỬ LÝ: Mất kết nối - chờ rồi bấm Reload ===
            elif self.state == Detectstate.CONNECTION:
                sleep(20)  # Chờ 20 giây cho kết nối ổn định
                py.click(x=self.reload_button[0], y=self.reload_button[1], button="left")
                sleep(0.05)
                self.lock.acquire()
                self.state = Detectstate.IDLE
                self.lock.release()
            
            # === XỬ LÝ: Bấm nút Play ở menu chính ===
            elif self.state == Detectstate.PLAY:
                sleep(0.05)
                py.click(x=self.playButton[0], y=self.playButton[1], button="left")
                sleep(0.05)
                self.lock.acquire()
                self.state = Detectstate.IDLE
                self.lock.release()
            
            # === XỬ LÝ: Bấm nút Proceed ===
            elif self.state == Detectstate.PROCEED:
                sleep(0.5)
                # Bấm 2 lần để đảm bảo bỏ qua animation
                py.click(x=self.proceedButton[0], y=self.proceedButton[1], button="left", clicks=2)
                sleep(0.5)
                self.lock.acquire()
                self.state = Detectstate.IDLE
                self.lock.release()
            
            # === XỬ LÝ: Thu thập Star Drop ===
            elif self.state == Detectstate.STARDROP:
                # Nhấn 'e' 5 lần để mở star drop
                py.press("e",presses=5)
                sleep(6)  # Chờ animation star drop
                py.press("e")  # Nhấn thêm 1 lần để đóng
                self.lock.acquire()
                self.state = Detectstate.IDLE
                self.lock.release()