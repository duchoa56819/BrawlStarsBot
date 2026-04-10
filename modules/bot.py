# ============================================================================
# Module: bot.py
# Mô tả: Module chính điều khiển bot tự động chơi Brawl Stars.
#         Bot hoạt động theo máy trạng thái (state machine) với 5 trạng thái:
#         INITIALIZING -> SEARCHING -> MOVING -> HIDING -> ATTACKING
#         Bot sẽ tìm bụi cỏ, di chuyển đến đó, ẩn nấp, và tấn công kẻ địch
#         khi chúng đến gần.
# ============================================================================

from time import time,sleep
from threading import Thread, Lock
from math import *
import pyautogui as py
import numpy as np
import random
from constants import Constants

"""
Mô tả các trạng thái của bot:
INITIALIZING: Khởi tạo bot, chờ một khoảng thời gian trước khi bắt đầu
SEARCHING: Tìm bụi cỏ gần nhất với người chơi trên bản đồ
MOVING: Di chuyển đến bụi cỏ đã chọn
HIDING: Dừng di chuyển và ẩn nấp trong bụi cỏ, chờ kẻ địch đến gần
ATTACKING: Tấn công kẻ địch khi chúng ở trong tầm đánh
"""
class BotState:
    INITIALIZING = 0  # Trạng thái khởi tạo
    SEARCHING = 1     # Trạng thái tìm kiếm bụi cỏ
    MOVING = 2        # Trạng thái di chuyển đến bụi cỏ
    HIDING = 3        # Trạng thái ẩn nấp trong bụi cỏ
    ATTACKING = 4     # Trạng thái tấn công kẻ địch

class Brawlbot:
    # === Thuộc tính kích thước trong game ===
    # Số ô (tile) theo chiều ngang và dọc tương ứng với tỉ lệ khung hình
    tile_w = 24  # Số tile theo chiều rộng
    tile_h = 17  # Số tile theo chiều cao
    # Độ lệch điểm giữa (offset) để căn chỉnh vị trí nhân vật trên màn hình
    midpoint_offset = Constants.midpoint_offset

    # === Cấu hình bản đồ ===
    # Bản đồ có góc cạnh nhọn (nhiều tường) hay không - ảnh hưởng đến thời gian di chuyển
    sharpCorner = Constants.sharpCorner
    # Chế độ ưu tiên: True = đi về trung tâm bản đồ, False = đi đến bụi gần nhất
    centerOrder = Constants.centerOrder

    # === Thuộc tính trạng thái của bot ===
    IGNORE_RADIUS = 0.5           # Bán kính bỏ qua (đơn vị tile) - không xử lý kẻ địch quá gần
    movement_screenshot = None    # Ảnh chụp trong lúc di chuyển
    screenshot = None             # Ảnh chụp màn hình hiện tại
    INITIALIZING_SECONDS = 2      # Thời gian chờ khởi tạo (giây)
    results = []                  # Kết quả nhận diện từ YOLO [player, bush, enemy]
    bushResult = []               # Danh sách bụi cỏ đã sắp xếp theo khoảng cách
    counter = 0                   # Bộ đếm để kiểm tra nhân vật có bị kẹt không
    direction = ["top","bottom","right","left"]  # Các hướng di chuyển
    current_bush = None           # Bụi cỏ hiện tại đang hướng đến
    last_player_pos = None        # Vị trí cuối cùng của người chơi (phát hiện kẹt)
    last_closest_enemy = None     # Kẻ địch gần nhất lần trước
    border_size = 1               # Kích thước đường viền (tile) để phát hiện vùng bão
    stopped = True                # Bot đang dừng hay không
    topleft = None                # Góc trên-trái bounding box của nhân vật
    avg_fps = 0                   # FPS trung bình của bot
    enemy_move_key = None         # Phím di chuyển tránh kẻ địch đã lưu
    timeFactor = 1                # Hệ số thời gian di chuyển (tăng nếu bản đồ có góc nhọn)
    
    # Tăng thời gian di chuyển thêm 5% nếu bản đồ có nhiều góc nhọn/tường
    # để tránh bị kẹt khi đi vòng quanh tường
    if sharpCorner: timeFactor = 1.05

    def __init__(self,windowSize,offsets,speed,attack_range) -> None:
        """
        Hàm khởi tạo bot Brawl Stars.
        
        :param windowSize (tuple): Kích thước cửa sổ game (width, height)
        :param offsets (tuple): Độ lệch tọa độ cửa sổ so với màn hình (offset_x, offset_y)
        :param speed (float): Tốc độ di chuyển của brawler (tile/giây)
        :param attack_range (float): Tầm đánh của brawler (đơn vị tile)
        """
        # Lock để đồng bộ thread, tránh xung đột khi đọc/ghi dữ liệu
        self.lock = Lock()
        
        # === Thiết lập thông số brawler dựa trên tầm đánh ===
        self.speed = speed
        
        # Phân loại brawler theo tầm đánh và điều chỉnh hệ số phù hợp
        # Brawler tầm ngắn (0-4 tile): giữ nguyên tầm đánh, ẩn nấp lâu hơn
        if attack_range >0 and attack_range <=4:
            range_multiplier = 1        # Không thay đổi tầm đánh
            hide_multiplier = 1.3       # Ẩn nấp lâu hơn 30% vì cần chờ địch đến gần
        # Brawler tầm trung (4-7 tile): giảm nhẹ tầm đánh
        elif attack_range > 4 and attack_range <=7:
            range_multiplier = 0.85     # Giảm tầm đánh 15% để đảm bảo đánh trúng
            hide_multiplier = 1         # Thời gian ẩn nấp bình thường
        # Brawler tầm xa (>7 tile): giảm mạnh tầm đánh và thời gian ẩn
        elif attack_range > 7:
            range_multiplier = 0.8      # Giảm tầm đánh 20%
            hide_multiplier = 0.8       # Giảm thời gian ẩn 20% vì đánh được từ xa
        
        # === Thiết lập các khoảng cách chiến đấu (đơn vị tile) ===
        # Tầm cảnh giác: nếu địch trong khoảng này, chuẩn bị di chuyển tránh
        self.alert_range = attack_range + 2
        # Tầm tấn công thực tế (đã nhân hệ số)
        self.attack_range = range_multiplier*attack_range
        # Tầm kích hoạt gadget (90% tầm tấn công - gần hơn mới dùng gadget)
        self.gadget_range = 0.9*self.attack_range
        # Tầm mà kẻ địch có thể nhìn thấy ta trong bụi cỏ
        self.hide_attack_range = 3.5
        # Thời gian ẩn nấp tối đa (giây) trước khi tìm bụi cỏ mới
        self.HIDINGTIME = hide_multiplier * 23
        
        # === Thiết lập kích thước cửa sổ và tọa độ ===
        self.timestamp = time()  # Thời điểm bắt đầu (dùng cho timer trạng thái)
        self.window_w = windowSize[0]  # Chiều rộng cửa sổ game
        self.window_h = windowSize[1]  # Chiều cao cửa sổ game
        # Tọa độ tâm cửa sổ (có offset dọc vì giao diện game không hoàn toàn đối xứng)
        self.center_window = (self.window_w / 2, int((self.window_h / 2)+ self.midpoint_offset))

        # Kích thước 1 tile trong pixel - tính trung bình chiều ngang và dọc
        # để đảm bảo chính xác trên các tỉ lệ màn hình khác nhau
        self.tileSize = round((round(self.window_w/self.tile_w)+round(self.window_h/self.tile_h))/2)
        # Bắt đầu ở trạng thái khởi tạo
        self.state = BotState.INITIALIZING
        
        # === Offset tọa độ cửa sổ BlueStacks ===
        # Dùng để chuyển đổi tọa độ từ ảnh chụp sang tọa độ thực trên màn hình
        self.offset_x = offsets[0]
        self.offset_y = offsets[1]

        # === Chỉ số (index) trong mảng kết quả nhận diện YOLO ===
        # results[0] = danh sách vị trí Player
        # results[1] = danh sách vị trí Bush (bụi cỏ)
        # results[2] = danh sách vị trí Enemy (kẻ địch)
        self.player_index = 0
        self.bush_index = 1
        self.enemy_index = 2
        

    def get_screen_position(self, cordinate):
        """
        Chuyển đổi tọa độ pixel trong ảnh chụp màn hình thành tọa độ thực trên màn hình.
        Cộng thêm offset của cửa sổ BlueStacks để click đúng vị trí.
        
        LƯU Ý: Nếu di chuyển cửa sổ BlueStacks sau khi chạy bot, 
        tọa độ sẽ bị sai vì offset chỉ tính một lần trong __init__.
        
        :param cordinate (tuple): Tọa độ (x, y) trong ảnh chụp
        :return: Tọa độ (x, y) thực trên màn hình đã cộng offset
        """
        return (cordinate[0] + self.offset_x, cordinate[1] + self.offset_y)
    
    # ============================================================================
    # PHẦN XỬ LÝ BÃO (STORM) - Phát hiện và di chuyển tránh vùng bão
    # Trong Brawl Stars, vùng bão sẽ thu hẹp dần, đẩy người chơi về trung tâm
    # ============================================================================
    
    def guess_storm_direction(self):
        """
        Dự đoán hướng bão dựa trên vị trí hiện tại của nhân vật.
        
        Logic: Nếu nhân vật lệch về bên phải so với tâm màn hình thì bão
        đang đến từ bên phải (nhân vật đang ở gần rìa phải bản đồ).
        
        Ví dụ: Nếu nhân vật ở bên phải tâm -> bão từ phải -> cần đi sang trái.

        :return: (List) danh sách [hướng_x, hướng_y] hoặc ["", ""] nếu không xác định
        """
        # Khởi tạo hướng x và y rỗng
        x_direction = ""
        y_direction =  ""
        # Kiểm tra có kết quả nhận diện không
        if self.results:
            # Kiểm tra có phát hiện nhân vật không
            if self.results[self.player_index]:
                # Tính kích thước vùng biên (border) - nếu nhân vật nằm trong vùng này
                # thì không cần lo bão
                x_border = (self.window_w/self.tile_w)*self.border_size
                y_border = (self.window_h/self.tile_h)*self.border_size
                # Tọa độ tâm màn hình
                p0 = self.center_window
                # Tọa độ nhân vật hiện tại
                p1 = self.results[self.player_index][0]
                # Tính độ lệch giữa nhân vật và tâm màn hình
                xDiff , yDiff = tuple(np.subtract(p1, p0))
                # Nhân vật lệch sang phải -> bão từ phải
                if xDiff>x_border:
                    x_direction = self.direction[2]  # "right"
                # Nhân vật lệch sang trái -> bão từ trái
                elif xDiff<-x_border:
                    x_direction = self.direction[3]  # "left"
                # Nhân vật lệch xuống dưới -> bão từ dưới
                if yDiff>y_border:
                    y_direction = self.direction[1]  # "bottom"
                # Nhân vật lệch lên trên -> bão từ trên
                elif yDiff<-y_border:
                    y_direction = self.direction[0]  # "top"
                return [x_direction,y_direction]
            else:
                return 2*[""]  # Không phát hiện nhân vật
        else:
            return 2*[""]  # Không có kết quả nhận diện
    
    def storm_movement_key(self):
        """
        Xác định phím di chuyển để tránh bão.
        Dựa trên hướng bão đã dự đoán, trả về phím ngược lại để chạy khỏi bão.
        
        Ví dụ: Bão từ phải ("right") -> nhấn "a" để đi sang trái.

        :return: (List) danh sách phím di chuyển [x_key, y_key] hoặc [] nếu không cần tránh
        """
        x = ""
        y = ""
        # Kiểm tra có kết quả nhận diện không
        if self.results:
            # Kiểm tra có phát hiện nhân vật không
            if self.results[self.player_index]:
                # Dự đoán hướng bão
                direction = self.guess_storm_direction()
                # Bão từ phải -> nhấn "a" (đi trái) để tránh
                if direction[0] == self.direction[2]:
                    x = "a"
                # Bão từ trái -> nhấn "d" (đi phải) để tránh
                elif direction[0] == self.direction[3]:
                    x = "d"
                # Bão từ dưới -> nhấn "w" (đi lên) để tránh
                if direction[1] == self.direction[1]:
                    y = "w"
                # Bão từ trên -> nhấn "s" (đi xuống) để tránh
                elif direction[1] == self.direction[0]:
                    y = "s"
        # Nếu không có phím nào -> không cần tránh bão
        if [x,y] == ["",""]:
            return []
        else:
            return [x,y]

    def get_quadrant_bush(self):
        """
        Xác định vùng (quadrant) trên màn hình để tìm bụi cỏ phù hợp.
        
        Màn hình được chia thành lưới 3x3. Dựa trên hướng bão, ta chỉ tìm
        bụi cỏ ở vùng an toàn (ngược hướng bão) để tránh chạy vào bão.
        
        Trả về 2 mảng [[x_min, x_max], [y_min, y_max]] xác định vùng tìm kiếm.

        :return: False nếu không xác định được hướng
                 (List) danh sách giới hạn vùng tìm kiếm [[x_range], [y_range]]
        """
        length = 0
        direction = self.guess_storm_direction()
        # Đếm số hướng bão đã xác định (0, 1 hoặc 2 hướng)
        for i in range(len(direction)):
            if len(direction[i]) > 0:
                length += 1
                index = i
        # Không xác định được hướng bão -> trả về False
        if length == 0:
            return False
        # Chỉ xác định được 1 hướng (ngang hoặc dọc)
        elif length == 1:
            single_direction = direction[index]
            # Bão từ trên -> tìm bụi ở nửa dưới
            if single_direction == self.direction[0]:
                return [[0,3],[2,3]]
            # Bão từ dưới -> tìm bụi ở nửa trên
            elif single_direction == self.direction[1]:
                return [[0,3],[0,1]]
            # Bão từ phải -> tìm bụi ở nửa trái
            elif single_direction == self.direction[2]:
                return [[0,1],[0,3]]
            # Bão từ trái -> tìm bụi ở nửa phải
            elif single_direction == self.direction[3]:
                return [[2,3],[0,3]]
        # Xác định được 2 hướng (chéo)
        elif length == 2:
            # Bão từ góc trên-phải -> tìm bụi ở góc dưới-trái
            if direction == [self.direction[0],self.direction[2]]:
                return [[0,2],[1,3]]
            # Bão từ góc trên-trái -> tìm bụi ở góc dưới-phải
            elif direction == [self.direction[0],self.direction[3]]:
                return [[1,3],[1,3]]
            # Bão từ góc dưới-phải -> tìm bụi ở góc trên-trái
            elif direction == [self.direction[1],self.direction[2]]:
                return [[0,2],[0,2]]
            # Bão từ góc dưới-trái -> tìm bụi ở góc trên-phải
            elif direction == [self.direction[1],self.direction[3]]:
                return [[1,3],[0,2]]
        
    # ============================================================================
    # PHẦN XỬ LÝ BỤI CỎ (BUSH) - Tìm và sắp xếp bụi cỏ
    # ============================================================================
    
    def ordered_bush_by_distance(self, index):
        """
        Sắp xếp danh sách bụi cỏ theo khoảng cách từ gần đến xa so với nhân vật.
        Lọc bụi cỏ theo vùng an toàn (tránh bão) nếu có thể.
        
        :param index (int): Chỉ số loại đối tượng trong results (1 = bush)
        :return: Danh sách bụi cỏ đã sắp xếp theo khoảng cách
        """
        # Nhân vật luôn ở gần tâm màn hình (camera theo nhân vật)
        # Nếu không phát hiện nhân vật hoặc chế độ centerOrder bật -> dùng tâm màn hình
        if not(self.results[self.player_index]) or self.centerOrder:
            player_position = self.center_window
        else:
            player_position = self.results[self.player_index][0]
        
        def tile_distance(position):
            """Tính khoảng cách tile giữa nhân vật và một vị trí bất kỳ"""
            return sqrt(((position[0] - player_position[0])/(self.window_w/self.tile_w))**2 
                        + ((position[1] - player_position[1])/(self.window_h/self.tile_h))**2)
        
        # Lấy danh sách tất cả bụi cỏ từ kết quả nhận diện
        unfilteredResults = self.results[index]
        filteredResult = []
        # Lấy vùng an toàn dựa trên hướng bão
        quadrant = self.get_quadrant_bush()
        if quadrant:
            # Chia màn hình thành lưới 3x3 để lọc bụi cỏ
            x_scale = self.window_w/3
            y_scale = self.window_h/3
            for x,y in unfilteredResults:
                # Chỉ giữ lại bụi cỏ nằm trong vùng an toàn (tránh bão)
                if ((x > quadrant[0][0]*x_scale and x <= quadrant[0][1]*x_scale)
                    and (y > quadrant[1][0]*y_scale and y <= quadrant[1][1]*y_scale)):
                    filteredResult.append((x,y))
            # Sắp xếp bụi cỏ đã lọc theo khoảng cách (gần nhất trước)
            filteredResult.sort(key=tile_distance)
            if filteredResult:
                return filteredResult
        # Nếu không xác định được vùng bão hoặc không có bụi trong vùng an toàn
        # -> sắp xếp tất cả bụi cỏ theo khoảng cách
        if not(quadrant) or not(filteredResult):
            unfilteredResults.sort(key=tile_distance)
            return unfilteredResults
    
    def ordered_enemy_by_distance(self,index):
        """
        Sắp xếp danh sách kẻ địch theo khoảng cách từ gần đến xa so với nhân vật.
        
        :param index (int): Chỉ số loại đối tượng trong results (2 = enemy)
        :return: Danh sách kẻ địch đã sắp xếp theo khoảng cách
        """
        # Xác định vị trí nhân vật
        if not(self.results[self.player_index]):
            player_position = self.center_window  # Mặc định dùng tâm màn hình
        else:
            player_position = self.results[self.player_index][0]
        
        def tile_distance(position):
            """Tính khoảng cách tile giữa nhân vật và kẻ địch"""
            return sqrt(((position[0] - player_position[0])/(self.window_w/self.tile_w))**2 
                        + ((position[1] - player_position[1])/(self.window_h/self.tile_h))**2)
        
        # Sắp xếp kẻ địch theo khoảng cách
        sortedResults = self.results[index]
        sortedResults.sort(key=tile_distance)
        return sortedResults
        
    def tile_distance(self,player_position,position):
        """
        Tính khoảng cách giữa 2 điểm theo đơn vị tile trong game.
        
        Công thức: sqrt((Δx / tile_width_px)² + (Δy / tile_height_px)²)
        - Chia cho kích thước tile pixel để chuyển từ pixel sang tile
        - Dùng định lý Pythagoras để tính khoảng cách Euclid

        :param player_position (tuple): Tọa độ pixel của nhân vật (x, y)
        :param position (tuple): Tọa độ pixel của mục tiêu (x, y)
        :return (float): Khoảng cách tính bằng tile
        """
        return sqrt(((position[0] - player_position[0])/(self.window_w/self.tile_w))**2 + ((position[1] - player_position[1])/(self.window_h/self.tile_h))**2)
    
    def find_bush(self):
        """
        Tìm và sắp xếp bụi cỏ theo khoảng cách.
        Cập nhật self.bushResult với danh sách bụi cỏ đã sắp xếp.
        
        :return (bool): True nếu tìm thấy bụi cỏ, False nếu không
        """
        if self.results:
            self.bushResult = self.ordered_bush_by_distance(self.bush_index)
        if self.bushResult:
            return True
        else:
            return False
        

    def move_to_bush(self):
        """
        Di chuyển nhân vật đến bụi cỏ gần nhất.
        
        Cách hoạt động:
        1. Lấy tọa độ bụi cỏ gần nhất từ bushResult[0]
        2. Tính khoảng cách tile đến bụi cỏ
        3. Nhấn giữ chuột giữa (movement_key) vào vị trí bụi cỏ trên màn hình
        4. Tính thời gian di chuyển = khoảng cách / tốc độ
        
        :return moveTime (float): Thời gian cần di chuyển (giây)
        """
        if self.bushResult:
            # Lấy tọa độ bụi cỏ gần nhất (index 0 sau khi đã sắp xếp)
            x,y = self.bushResult[0]
            # Xác định vị trí nhân vật
            if not(self.results[self.player_index]):
                player_pos = self.center_window
            else:
                player_pos = self.results[self.player_index][0]
            # Tính khoảng cách tile đến bụi cỏ
            tileDistance = self.tile_distance(player_pos,(x,y))
            # Chuyển tọa độ ảnh sang tọa độ màn hình thực (cộng offset)
            x,y = self.get_screen_position((x,y))
            # Nhấn giữ chuột giữa vào vị trí bụi cỏ để nhân vật di chuyển
            py.mouseDown(button=Constants.movement_key,x=x, y=y)
            # Tính thời gian di chuyển (giây) = khoảng cách / tốc độ
            moveTime = tileDistance/self.speed
            # Nhân hệ số thời gian (tăng nếu bản đồ có góc nhọn)
            moveTime = moveTime * self.timeFactor
            print(f"Distance: {round(tileDistance,2)} tiles")
            return moveTime
    
    # ============================================================================
    # PHẦN XỬ LÝ CHIẾN ĐẤU - Tấn công, gadget, và di chuyển chiến đấu
    # ============================================================================
    
    def attack(self):
        """
        Thực hiện đòn tấn công thường bằng cách nhấn phím 'e'.
        Trong BlueStacks, phím 'e' được map với nút tấn công trong game.
        """
        print("attacking enemy")
        attack_key = "e"
        py.press(attack_key)

    def gadget(self):
        """
        Kích hoạt gadget (kỹ năng phụ) bằng cách nhấn phím 'f'.
        Gadget chỉ dùng khi kẻ địch ở rất gần (trong gadget_range).
        """
        print("activate gadget")
        gadget_key = "f"
        py.press(gadget_key)

    def hold_movement_key(self,key,time):
        """
        Giữ phím di chuyển trong một khoảng thời gian nhất định.
        Dùng để di chuyển nhân vật theo hướng cụ thể.

        :param key (string): Phím cần giữ (w/a/s/d)
        :param time (float): Thời gian giữ phím (giây)
        """
        with py.hold(key):
            sleep(time)

    def storm_random_movement(self):
        """
        Di chuyển ngẫu nhiên để tránh bão.
        
        Nếu xác định được hướng bão -> di chuyển ngẫu nhiên theo các phím tránh bão.
        Nếu không -> di chuyển hoàn toàn ngẫu nhiên (w/a/s/d).
        Giữ phím 1 giây mỗi lần.
        """
        if self.storm_movement_key():
            move_keys = self.storm_movement_key()
        else:
            move_keys = ["w", "a", "s", "d"]
        random_move = random.choice(move_keys)
        hold_time = 1
        self.hold_movement_key(random_move,hold_time)
    
    def stuck_random_movement(self):
        """
        Di chuyển ngẫu nhiên khi nhân vật bị kẹt (stuck).
        
        Ưu tiên di chuyển về hướng bụi cỏ gần nhất.
        Nếu không xác định được hướng -> di chuyển ngẫu nhiên.
        Giữ phím 1 giây để thoát khỏi vị trí kẹt.
        """
        # Lấy phím di chuyển hướng về bụi cỏ
        move_keys = self.get_movement_key(self.bush_index)
        if not(move_keys):
            # Nếu không có hướng cụ thể -> chọn ngẫu nhiên 1 trong 4 hướng
            move_keys = ["w", "a", "s", "d"]
            move_keys = random.choice(move_keys)
        # Giữ phím 1 giây
        with py.hold(move_keys):
            sleep(1)

    def get_movement_key(self,index):
        """
        Xác định phím di chuyển dựa trên vị trí tương đối giữa nhân vật và mục tiêu.
        
        Tính chênh lệch tọa độ giữa nhân vật và mục tiêu (kẻ địch hoặc bụi cỏ),
        sau đó trả về phím di chuyển tương ứng.
        
        VD: Kẻ địch ở bên phải -> nhấn "d" để chạy về phía đó (hoặc trốn ngược lại)
        
        :param index (int): Chỉ số mục tiêu (1=bush, 2=enemy)
        :return: (List) danh sách phím [x_key, y_key] hoặc [] nếu không xác định
        """
        x_key = ""
        y_key = ""
        if self.results:
            # Xác định vị trí nhân vật
            if self.results[self.player_index]:
                player_pos = self.results[self.player_index][0]
            else:
                # Mặc định dùng tâm màn hình nếu không phát hiện nhân vật
                player_pos = self.center_window
            if self.results[index]:
                # Lấy vị trí mục tiêu đầu tiên (gần nhất sau khi sắp xếp)
                if index == self.enemy_index:
                    p0 = self.enemyResults[0]
                elif index == self.bush_index:
                    p0 = self.bushResult[0]
                p1 = player_pos
                # Tính chênh lệch tọa độ: dương = nhân vật ở bên phải/dưới mục tiêu
                xDiff , yDiff = tuple(np.subtract(p1, p0))
                # Mục tiêu ở bên trái nhân vật -> nhấn "d" (đi phải, tức hướng từ mục tiêu)
                if xDiff>0:
                    x_key = "d"
                # Mục tiêu ở bên phải nhân vật -> nhấn "a" (đi trái)
                elif xDiff<0:
                    x_key = "a"
                # Mục tiêu ở phía trên nhân vật -> nhấn "s" (đi xuống)
                if yDiff>0:
                    y_key = "s"
                # Mục tiêu ở phía dưới nhân vật -> nhấn "w" (đi lên)
                elif yDiff<0:
                    y_key = "w"
                return [x_key,y_key]
        return []
    
    def enemy_random_movement(self):
        """
        Di chuyển tránh kẻ địch và tấn công đồng thời.
        
        Vừa giữ phím di chuyển ra xa kẻ địch, vừa nhấn "e" 2 lần (tấn công)
        để tạo khoảng cách an toàn trong khi vẫn gây sát thương.
        """
        if not(self.enemy_move_key):
            # Tính phím di chuyển tránh kẻ địch
            move_keys = self.get_movement_key(self.enemy_index)
            if not(move_keys):
                # Nếu không có hướng -> di chuyển ngẫu nhiên
                move_keys = ["w", "a", "s", "d"]
                move_keys = random.choice(move_keys)
        else:
            # Dùng phím di chuyển đã lưu từ trước (từ alert_range)
            move_keys = self.enemy_move_key
        # Vừa di chuyển vừa tấn công 2 phát (interval 0.4 giây giữa 2 đòn)
        with py.hold(move_keys):
            py.press("e",presses=2,interval=0.4)

    def enemy_distance(self):
        """
        Tính khoảng cách từ nhân vật đến kẻ địch gần nhất.
        
        Sắp xếp tất cả kẻ địch theo khoảng cách và trả về khoảng cách
        đến kẻ địch gần nhất. Cũng lưu lại danh sách kẻ địch đã sắp xếp.
        
        :return (float|None): Khoảng cách tile đến kẻ địch gần nhất, None nếu không có
        """
        if self.results:
            # Xác định vị trí nhân vật
            if self.results[self.player_index]:
                player_pos = self.results[self.player_index][0]
            else:
                player_pos = self.center_window
            # Kiểm tra có kẻ địch nào trong kết quả nhận diện không
            if self.results[self.enemy_index]:
                # Sắp xếp kẻ địch theo khoảng cách
                self.enemyResults = self.ordered_enemy_by_distance(self.enemy_index)
                if self.enemyResults:
                    # Tính khoảng cách đến kẻ địch gần nhất
                    enemyDistance = self.tile_distance(player_pos,self.enemyResults[0])
                    return enemyDistance
        return None
    
    def is_enemy_in_range(self):
        """
        Kiểm tra kẻ địch có nằm trong tầm tấn công không và thực hiện hành động phù hợp.
        
        3 vùng khoảng cách:
        1. alert_range > distance > attack_range: Chuẩn bị (lưu phím di chuyển)
        2. attack_range >= distance > gadget_range: Tấn công thường
        3. gadget_range >= distance: Dùng gadget + tấn công
        
        :return (bool): True nếu đã tấn công, False nếu không
        """
        enemyDistance = self.enemy_distance()
        if enemyDistance:
            # Kẻ địch trong vùng cảnh giác nhưng chưa đến tầm đánh
            # -> chỉ lưu hướng di chuyển để chuẩn bị
            if (enemyDistance > self.attack_range
                and enemyDistance <= self.alert_range):
                self.enemy_move_key = self.get_movement_key(self.enemy_index)
            # Kẻ địch trong tầm đánh -> tấn công thường
            elif (enemyDistance > self.gadget_range 
                  and enemyDistance <= self.attack_range):
                self.attack()
                return True
            # Kẻ địch rất gần (trong tầm gadget) -> dùng gadget + tấn công
            elif enemyDistance <= self.gadget_range:
                self.gadget()
                self.attack()
                return True
        return False

    def is_enemy_close(self):
        """
        Kiểm tra kẻ địch có ở gần đến mức nhìn thấy ta trong bụi cỏ không.
        
        Khi ẩn trong bụi cỏ, nếu kẻ địch đến quá gần (hide_attack_range = 3.5 tile),
        chúng sẽ thấy nhân vật. Lúc này cần tấn công ngay (dùng gadget + attack).
        
        :return (bool): True nếu kẻ địch quá gần, False nếu an toàn
        """
        enemyDistance = self.enemy_distance()
        if enemyDistance:
            if enemyDistance <= self.hide_attack_range:
                # Kẻ địch sắp nhìn thấy ta -> phản công ngay
                self.gadget()
                self.attack()
                return True
        return False

    def is_player_damaged(self):
        """
        Kiểm tra nhân vật có đang bị trúng đòn không.
        
        Phương pháp: Kiểm tra màu pixel phía trên bounding box nhân vật.
        Khi bị đánh, thanh HP sẽ hiện ra với màu đỏ (204, 34, 34).
        Kiểm tra 2 điểm (1/3 và 2/3 chiều rộng) để tăng độ chính xác.
        
        :return (bool): True nếu đang bị đánh, False nếu không
        """
        if self.topleft:
            # Tính kích thước bounding box nhân vật
            width = abs(self.topleft[0] - self.bottomright[0])
            height = abs(self.topleft[1] - self.bottomright[1])
            # 2 điểm kiểm tra: 1/3 và 2/3 chiều rộng, phía trên bounding box
            w1 = int(self.topleft[0] + width/3)
            w2 = int(self.topleft[0] + 2*(width/3))
            h = int(self.topleft[1] - height/2)  # Phía trên bounding box (thanh HP)
            try:
                # Kiểm tra pixel có khớp màu đỏ (thanh HP bị mất) không
                if (py.pixelMatchesColor(w1,h,(204, 34, 34),tolerance=20)
                    or py.pixelMatchesColor(w2,h,(204, 34, 34),tolerance=20)):
                    print(f"player is damaged")
                    return True
            except OSError:
                pass  # Bỏ qua lỗi khi pixel nằm ngoài màn hình
        return False
    
    def have_stopped_moving(self):
        """
        Kiểm tra nhân vật có đang đứng im (bị kẹt) không.
        
        So sánh vị trí hiện tại với vị trí trước đó. Nếu vị trí không đổi
        trong 2 lần liên tiếp -> nhân vật đang bị kẹt (va vào tường/vật cản).
        
        :return (bool): True nếu bị kẹt, False nếu đang di chuyển bình thường
        """
        if self.results:
            if self.results[self.player_index]:
                player_pos = self.results[self.player_index][0]
                if self.last_player_pos is None:
                    # Lần đầu -> lưu vị trí
                    self.last_player_pos = player_pos
                else:
                    # So sánh vị trí hiện tại với vị trí trước
                    if self.last_player_pos == player_pos:
                        self.counter += 1
                        # Nếu đứng im 2 lần liên tiếp -> bị kẹt
                        if self.counter == 2:
                            print("have stopped moving or stuck")
                            return True
                    else:
                        # Vẫn đang di chuyển -> reset bộ đếm
                        self.counter = 0
                    self.last_player_pos = player_pos
        return False

    # ============================================================================
    # PHẦN CẬP NHẬT DỮ LIỆU - Nhận dữ liệu từ thread nhận diện
    # Các hàm này được gọi từ thread chính (main loop) để cập nhật dữ liệu
    # cho thread bot xử lý. Sử dụng Lock để đảm bảo thread-safe.
    # ============================================================================
    
    def update_results(self,results):
        """
        Cập nhật kết quả nhận diện YOLO (vị trí player, bush, enemy).
        Gọi từ main loop mỗi frame.
        
        :param results (list): Kết quả nhận diện [[player_coords], [bush_coords], [enemy_coords]]
        """
        self.lock.acquire()
        self.results = results
        self.lock.release()
    
    def update_player(self,topleft,bottomright):
        """
        Cập nhật bounding box của nhân vật cho hàm is_player_damaged().
        Chỉ cần thiết trong trạng thái HIDING.
        
        :param topleft (tuple): Góc trên-trái bounding box (x, y) trên màn hình
        :param bottomright (tuple): Góc dưới-phải bounding box (x, y) trên màn hình
        """
        self.lock.acquire()
        self.topleft = topleft
        self.bottomright =bottomright
        self.lock.release()

    def update_screenshot(self, screenshot):
        """
        Cập nhật ảnh chụp màn hình hiện tại.
        
        :param screenshot: Ảnh chụp màn hình (numpy array BGR)
        """
        self.lock.acquire()
        self.screenshot = screenshot
        self.lock.release()

    # ============================================================================
    # PHẦN ĐIỀU KHIỂN THREAD - Khởi động, dừng và vòng lặp chính của bot
    # ============================================================================
    
    def start(self):
        """
        Khởi động bot trong một thread riêng biệt.
        Thread chạy ở chế độ daemon (tự dừng khi chương trình chính kết thúc).
        """
        self.stopped = False
        self.loop_time = time()
        self.count = 0
        t = Thread(target=self.run)
        t.setDaemon(True)  # Thread daemon tự kết thúc khi main thread dừng
        t.start()

    def stop(self):
        """
        Dừng bot và reset vị trí cuối cùng của nhân vật.
        """
        self.stopped = True
        self.last_player_pos = None

    def run(self):
        """
        Vòng lặp chính của bot - Máy trạng thái (State Machine).
        
        Luồng hoạt động:
        INITIALIZING -> chờ 2 giây -> SEARCHING
        SEARCHING -> tìm được bụi -> MOVING -> đến nơi -> HIDING
        SEARCHING -> không tìm thấy -> di chuyển ngẫu nhiên tránh bão
        HIDING -> hết thời gian hoặc bị đánh -> SEARCHING
        Bất kỳ trạng thái nào -> phát hiện địch trong tầm -> ATTACKING
        ATTACKING -> hết địch -> SEARCHING
        """
        while not self.stopped:
            sleep(0.01)  # Tránh chiếm hết CPU, nghỉ 10ms mỗi vòng lặp
            
            # === TRẠNG THÁI 1: KHỞI TẠO ===
            # Chờ một khoảng thời gian (2 giây) trước khi bắt đầu hoạt động
            # Để đảm bảo game đã load xong
            if self.state == BotState.INITIALIZING:
                if time() > self.timestamp + self.INITIALIZING_SECONDS:
                    # Hết thời gian chờ -> chuyển sang tìm kiếm
                    self.lock.acquire()
                    self.state = BotState.SEARCHING
                    self.lock.release()

            # === TRẠNG THÁI 2: TÌM KIẾM BỤI CỎ ===
            elif self.state == BotState.SEARCHING:
                success = self.find_bush()
                if success:
                    # Tìm thấy bụi cỏ -> bắt đầu di chuyển đến đó
                    print("found bush")
                    self.moveTime = self.move_to_bush()
                    self.lock.acquire()
                    self.timestamp = time()
                    self.state = BotState.MOVING
                    self.lock.release()
                else:
                    # Không tìm thấy bụi -> di chuyển ngẫu nhiên tránh bão
                    print("Cannot find bush")
                    self.storm_random_movement()
                
                # Kiểm tra kẻ địch trong tầm đánh (ưu tiên chiến đấu)
                if self.is_enemy_in_range():
                        self.lock.acquire()
                        self.state = BotState.ATTACKING
                        self.lock.release()

            # === TRẠNG THÁI 3: DI CHUYỂN ĐẾN BỤI CỎ ===
            elif self.state == BotState.MOVING:
                # Kiểm tra nhân vật có bị kẹt (va vào tường) không
                if self.have_stopped_moving():
                    # Bị kẹt -> thả chuột, di chuyển ngẫu nhiên, rồi tìm bụi mới
                    py.mouseUp(button = Constants.movement_key)
                    self.stuck_random_movement()
                    self.lock.acquire()
                    self.state = BotState.SEARCHING
                    self.lock.release()
                else:
                    # Vẫn đang di chuyển -> chờ 150ms rồi kiểm tra lại
                    sleep(0.15)

                # Kiểm tra kẻ địch ngay cả khi đang di chuyển
                if self.is_enemy_in_range():
                    self.lock.acquire()
                    self.state = BotState.ATTACKING
                    self.lock.release()
                # Kiểm tra đã đến bụi cỏ chưa (hết thời gian di chuyển)
                if time() > self.timestamp + self.moveTime:
                    # Đã đến nơi -> thả chuột và chuyển sang ẩn nấp
                    py.mouseUp(button = Constants.movement_key)
                    print("Hiding")
                    self.lock.acquire()
                    self.timestamp = time()
                    self.state = BotState.HIDING
                    self.lock.release()
                    
            # === TRẠNG THÁI 4: ẨN NẤP TRONG BỤI CỎ ===
            elif self.state == BotState.HIDING:
                # Kiểm tra hết thời gian ẩn nấp hoặc bị kẻ địch tấn công
                if time() > self.timestamp + self.HIDINGTIME or self.is_player_damaged():
                    # Hết giờ hoặc bị đánh -> tìm bụi cỏ mới
                    print("Changing state to search")
                    self.lock.acquire()
                    self.stuck_random_movement()  # Di chuyển ngẫu nhiên trước khi tìm
                    self.state = BotState.SEARCHING
                    self.lock.release()

                # Kiểm tra kẻ địch tùy theo chế độ
                if self.centerOrder:
                    # Chế độ trung tâm: chỉ tấn công khi địch rất gần (nhìn thấy trong bụi)
                    if self.is_enemy_close():
                        print("Enemy is nearby")
                        self.lock.acquire()
                        self.state = BotState.ATTACKING
                        self.lock.release()
                else:
                    # Chế độ bụi gần: tấn công khi địch trong tầm đánh thường
                    if self.is_enemy_in_range():
                        print("Enemy in range")
                        self.lock.acquire()
                        self.state = BotState.ATTACKING
                        self.lock.release()
            
            # === TRẠNG THÁI 5: TẤN CÔNG KẺ ĐỊCH ===
            elif self.state == BotState.ATTACKING:
                if self.is_enemy_in_range():
                    # Kẻ địch vẫn trong tầm -> vừa tránh vừa đánh
                    self.enemy_random_movement()
                else:
                    # Hết kẻ địch trong tầm -> quay lại tìm bụi cỏ
                    self.lock.acquire()
                    self.state = BotState.SEARCHING
                    self.lock.release()
                    
            # === Tính FPS trung bình của bot ===
            self.fps = (1 / (time() - self.loop_time))
            self.loop_time = time()
            self.count += 1
            if self.count == 1:
                self.avg_fps = self.fps
            else:
                # Tính FPS trung bình cộng dồn (running average)
                self.avg_fps = (self.avg_fps*self.count+self.fps)/(self.count + 1)