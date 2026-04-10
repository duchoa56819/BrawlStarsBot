# ============================================================================
# Module: main.py
# Mô tả: File chính để chạy bot Brawl Stars.
#         Chương trình này kết nối tất cả các module lại với nhau:
#         - WindowCapture: Chụp màn hình cửa sổ BlueStacks
#         - Detection: Nhận diện đối tượng bằng YOLO (Player, Bush, Enemy)
#         - Screendetect: Phát hiện trạng thái màn hình game (tải, thua, chơi lại)
#         - Brawlbot: Điều khiển bot tự động chơi game
#         
#         Ngoài ra còn có chức năng hẹn giờ tắt máy tính cho việc chạy bot qua đêm.
# ============================================================================

import cv2 as cv
from time import time,sleep
from modules.windowcapture import WindowCapture
from modules.bot import Brawlbot, BotState
from modules.screendetect import Screendetect, Detectstate
from modules.detection import Detection
from modules.print import bcolors
import pyautogui as py
import os
from constants import Constants

def stop_all_thread(wincap,screendetect,bot,detector):
    """
    Dừng tất cả các thread đang chạy và giải phóng tài nguyên.
    Được gọi khi người dùng thoát bot hoặc di chuyển chuột ra ngoài cửa sổ.
    
    Thứ tự dừng:
    1. Thả phím chuột di chuyển (tránh nhân vật tiếp tục di chuyển)
    2. Dừng thread chụp màn hình
    3. Dừng thread nhận diện YOLO
    4. Dừng thread phát hiện trạng thái màn hình
    5. Dừng thread bot
    6. Đóng tất cả cửa sổ OpenCV debug
    
    :param wincap: Đối tượng WindowCapture
    :param screendetect: Đối tượng Screendetect
    :param bot: Đối tượng Brawlbot
    :param detector: Đối tượng Detection
    """
    py.mouseUp(button = Constants.movement_key)  # Thả chuột giữa (dừng di chuyển)
    wincap.stop()         # Dừng chụp màn hình
    detector.stop()       # Dừng nhận diện YOLO
    screendetect.stop()   # Dừng phát hiện trạng thái
    bot.stop()            # Dừng bot
    cv.destroyAllWindows()  # Đóng cửa sổ debug OpenCV

def add_two_tuple(tup1,tup2):
    """
    Cộng 2 tuple theo từng phần tử.
    Dùng để cộng offset vào tọa độ bounding box khi chuyển từ tọa độ ảnh sang tọa độ màn hình.
    
    Ví dụ: (100, 200) + (50, 30) = (150, 230)
    
    :param tup1 (tuple): Tuple thứ nhất
    :param tup2 (tuple): Tuple thứ hai
    :return (tuple): Tuple kết quả đã cộng, None nếu đầu vào None
    """
    if not(tup1 is None or tup2 is None):
        return tuple(map(sum, zip(tup1, tup2)))

def main():
    """
    Hàm chính chạy bot Brawl Stars.
    
    Luồng hoạt động:
    1. Khởi tạo các module (WindowCapture, Detection, Screendetect, Brawlbot)
    2. Bắt đầu các thread xử lý song song
    3. Vào vòng lặp chính:
       - Chụp màn hình -> Cập nhật cho detector
       - Dựa trên trạng thái bot -> cập nhật dữ liệu phù hợp
       - Dựa trên trạng thái màn hình -> khởi động/dừng bot
       - Hiển thị debug nếu bật
       - Kiểm tra điều kiện thoát (nhấn 'q' hoặc chuột ra ngoài cửa sổ)
    """
    # === BƯỚC 1: KHỞI TẠO CÁC MODULE ===
    
    # Khởi tạo WindowCapture - chụp màn hình cửa sổ BlueStacks
    wincap = WindowCapture(Constants.window_name)
    # Lấy kích thước cửa sổ game (không bao gồm viền và thanh tiêu đề)
    windowSize = wincap.get_dimension()
    # Đưa cửa sổ BlueStacks lên foreground (nổi trên cùng)
    sleep(0.5)
    wincap.set_window()

    # Khởi tạo Detection - nhận diện đối tượng bằng YOLO
    # Truyền vào: kích thước cửa sổ, đường dẫn model, danh sách lớp, hệ số chiều cao
    detector = Detection(windowSize,Constants.model_file_path,Constants.classes,Constants.heightScaleFactor)
    # Khởi tạo Screendetect - phát hiện trạng thái màn hình game
    # (play again, loading, defeated, star drop...)
    screendetect = Screendetect(windowSize,wincap.offsets)
    # Khởi tạo Brawlbot - điều khiển bot tự động
    # Truyền vào: kích thước cửa sổ, offset, tốc độ brawler, tầm đánh
    bot = Brawlbot(windowSize, wincap.offsets, Constants.speed, Constants.attack_range)
    
    # Di chuyển con trỏ chuột đến chính giữa cửa sổ BlueStacks
    # để sẵn sàng cho việc di chuyển nhân vật
    middle_of_window = (int(wincap.w/2+wincap.offset_x),int(wincap.h/2+wincap.offset_y))
    py.moveTo(middle_of_window[0],middle_of_window[1])

    # === BƯỚC 2: KHỞI ĐỘNG CÁC THREAD ===
    # Mỗi module chạy trong thread riêng để xử lý song song
    wincap.start()       # Bắt đầu chụp màn hình liên tục
    detector.start()     # Bắt đầu nhận diện YOLO liên tục
    screendetect.start() # Bắt đầu kiểm tra trạng thái màn hình
    
    # Hiển thị thông tin cấu hình hệ thống
    print(f"Resolution: {wincap.screen_resolution}")      # Độ phân giải màn hình
    print(f"Window Size: {windowSize}")                     # Kích thước cửa sổ game
    print(f"Scaling: {wincap.scaling*100}%")                # Tỉ lệ DPI

    # Kiểm tra tỉ lệ khung hình - nếu > 16:9 thì có thể bị ảnh hưởng bởi quảng cáo
    aspect_ratio = windowSize[0]/windowSize[1]
    if aspect_ratio > 1.79:
        print(bcolors.WARNING + "Please make sure to disable ads on bluestack and close the right sidebar for the bot to work as intended." + bcolors.ENDC)

    # === BƯỚC 3: VÒNG LẶP CHÍNH ===
    while True:
        # Lấy ảnh chụp màn hình mới nhất từ thread WindowCapture
        screenshot = wincap.screenshot
        if screenshot is None:
            continue  # Bỏ qua nếu chưa có ảnh (thread chưa kịp chụp)
        
        # Cập nhật ảnh chụp cho thread Detection để nhận diện
        detector.update(screenshot)
        # Cập nhật trạng thái bot (dừng/chạy) cho Screendetect
        screendetect.update_bot_stop(bot.stopped)
        
        # === CẬP NHẬT DỮ LIỆU CHO BOT THEO TRẠNG THÁI ===
        if bot.state == BotState.INITIALIZING:
            # Đang khởi tạo -> chỉ cập nhật kết quả nhận diện
            bot.update_results(detector.results)
        elif bot.state == BotState.SEARCHING:
            # Đang tìm kiếm -> cập nhật kết quả nhận diện
            bot.update_results(detector.results)
        elif bot.state == BotState.MOVING:
            # Đang di chuyển -> cập nhật cả ảnh chụp và kết quả nhận diện
            bot.update_screenshot(screenshot)
            bot.update_results(detector.results)
        elif bot.state == BotState.HIDING:
            # Đang ẩn nấp -> cập nhật kết quả nhận diện + vị trí bounding box nhân vật
            # (cần bounding box để kiểm tra nhân vật có bị đánh không)
            bot.update_results(detector.results)
            bot.update_player(add_two_tuple(detector.player_topleft,wincap.offsets)
                              ,add_two_tuple(detector.player_bottomright,wincap.offsets))
        elif bot.state == BotState.ATTACKING:
            # Đang tấn công -> cập nhật kết quả nhận diện
            bot.update_results(detector.results)

        # === XỬ LÝ TRẠNG THÁI MÀN HÌNH GAME ===
        # Nếu phát hiện màn hình kết thúc trận (thua, play again, mất kết nối...)
        # -> dừng bot và thả phím di chuyển
        if (screendetect.state ==  Detectstate.EXIT
            or screendetect.state ==  Detectstate.PLAY_AGAIN
            or screendetect.state ==  Detectstate.CONNECTION
            or screendetect.state ==  Detectstate.PLAY
            or screendetect.state == Detectstate.PROCEED):
            py.mouseUp(button = Constants.movement_key)  # Thả chuột
            bot.stop()  # Dừng bot
        elif screendetect.state ==  Detectstate.LOAD:
            # Phát hiện đang tải vào trận mới
            if bot.stopped:
                # Chờ game tải xong (4 giây)
                sleep(4)
                print("starting bot")
                # Reset timestamp và trạng thái, rồi khởi động bot
                bot.timestamp = time()
                bot.state = BotState.INITIALIZING
                bot.start()

        # === HIỂN THỊ CỬA SỔ DEBUG ===
        # Nếu DEBUG = True trong constants.py, hiển thị ảnh có annotation
        if Constants.DEBUG:
            detector.annotate_detection_midpoint()  # Vẽ dấu chữ thập tại vị trí nhận diện
            detector.annotate_border(bot.border_size,bot.tile_w,bot.tile_h)  # Vẽ viền bão
            detector.annotate_fps(wincap.avg_fps)   # Hiển thị FPS
            cv.imshow("Brawl Stars Bot",detector.screenshot)  # Hiện cửa sổ debug

        # === KIỂM TRA ĐIỀU KIỆN THOÁT ===
        # Nhấn 'q' hoặc di chuyển chuột ra ngoài vùng an toàn để thoát
        key = cv.waitKey(1)
        x_mouse, y_mouse = py.position()
        
        # Xác định vùng thoát dựa trên cách bố trí cửa sổ
        if wincap.screen_resolution[1] == (windowSize[1]+wincap.titlebar_pixels+1):
            # Cửa sổ đúng bằng màn hình -> thoát khi chuột vượt quá bên phải
            stop_bool = x_mouse > (wincap.offset_x + wincap.w)
        else:
            # Cửa sổ nhỏ hơn màn hình -> thoát khi chuột ở góc trên-trái hoặc dưới-phải
            stop_bool = ((x_mouse > 0 and x_mouse < wincap.left and y_mouse > 0 and y_mouse < wincap.top)
            or ( x_mouse > wincap.right and x_mouse < wincap.screen_resolution[0]
                and y_mouse > wincap.bottom and y_mouse < wincap.screen_resolution[1]))
        
        # Thoát nếu nhấn 'q' hoặc chuột nằm ngoài vùng an toàn
        if (key == ord('q') or stop_bool):
            stop_all_thread(wincap,screendetect,bot,detector)
            break
    
    # Thông báo thoát và dọn dẹp
    print(bcolors.WARNING +'Cursor currently not on Bluestacks, exiting bot...' +bcolors.ENDC)
    stop_all_thread(wincap,screendetect,bot,detector)

# ============================================================================
# ĐIỂM VÀO CHƯƠNG TRÌNH (Entry Point)
# Hiển thị menu chính cho người dùng chọn:
# 1. Chạy bot
# 2. Hẹn giờ tắt máy (cho việc chạy bot qua đêm)
# 3. Hủy hẹn giờ tắt máy
# 4. Thoát
# ============================================================================
if __name__ == "__main__":
    print(" ")
    # Hiển thị hướng dẫn sử dụng
    print(bcolors.HEADER + bcolors.BOLD +
              "Before starting the bot, make sure you have Brawl Stars open \non Bluestacks and selected solo showdown gamemode.")
    print("")
    print("Also make sure to change the speed, attack_range and HeightScaleFactor"
            +"\nfor you selected brawler at constants.py (instruction there as well).")
    print("To exit bot hover cursor to the top left or bottom right corner.")
    print("")
    print(bcolors.UNDERLINE + "IMPORTANT - make sure to disable ads on bluestack and close the right sidebar" + bcolors.ENDC)
    
    # Vòng lặp menu chính - cho phép chạy bot nhiều lần
    while True:
        print("")
        print("1. Start Bot")               # Chạy bot
        print("2. Set shutdown timer")       # Hẹn giờ tắt máy tính
        print("3. Cancel shutdown timer")    # Hủy hẹn giờ tắt máy
        print("4. Exit")                     # Thoát chương trình
        user_input = input("Select: ").lower()
        print("")
        
        # === Lựa chọn 1: Chạy bot ===
        if user_input == "1" or user_input == "start bot":
            main()
        
        # === Lựa chọn 2: Hẹn giờ tắt máy ===
        # Sử dụng lệnh Windows "shutdown -s -t <giây>" để hẹn giờ
        # Hữu ích khi chạy bot qua đêm, muốn tắt máy sau vài giờ
        elif user_input == "2" or user_input == "set shutdown timer":
            print("Set Shutdown Timer")
            try:
                hour = int(input("How many hour before shutdown? "))
                second = 3600 * hour  # Chuyển giờ thành giây
                os.system(f'cmd /c "shutdown -s -t {second}"')
                print(f"Shuting down in {hour} hour")
            except ValueError:
                print("Please enter a valid input!")
        
        # === Lựa chọn 3: Hủy hẹn giờ tắt máy ===
        # Sử dụng lệnh "shutdown -a" (abort) để hủy
        elif user_input == "3" or user_input == "cancel shutdown timer":
            os.system('cmd /c "shutdown -a"')
            print("Shutdown timer cancelled")
        
        # === Lựa chọn 4: Thoát chương trình ===
        elif user_input =="4" or user_input == "exit":
            print("Exitting...")
            break