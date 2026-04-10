# ============================================================================
# Module: constants.py
# Mô tả: File cấu hình chính cho bot Brawl Stars.
#         Tập trung tất cả hằng số và cài đặt tại một nơi duy nhất.
#         Người dùng cần thay đổi file này trước khi chạy bot:
#         - Chọn brawler (tên hoặc chỉnh thủ công speed/attack_range)
#         - Cấu hình bản đồ (góc nhọn, vị trí spawn)
#         - Cấu hình BlueStacks (tên cửa sổ, GPU)
# ============================================================================

import json
from modules.print import bcolors

# Đọc dữ liệu brawler từ file JSON
# File này chứa speed, attack_range, heightScaleFactor cho từng brawler
brawler_stats_dict = json.load(open("brawler_stats.json"))

class Constants:
    # =========================================================================
    # PHẦN 1: THÔNG SỐ BRAWLER
    # Thay đổi tên brawler để tự động lấy thông số từ brawler_stats.json
    # Nếu brawler không có trong JSON, cần chỉnh thủ công speed/attack_range
    # =========================================================================
    
    """
    Thay đổi brawler_name thành tên brawler bạn đang sử dụng.
    Nếu không tìm thấy trong brawler_stats.json, hãy chỉnh thủ công
    speed, attack_range và heightScaleFactor bên dưới.
    """
    brawler_name = "frank"
    
    """
    Tra cứu thông số brawler tại: https://pixelcrux.com/Brawl_Stars/Brawlers/
    - speed: Tốc độ di chuyển (đơn vị tile/giây)
    - attack_range: Tầm đánh (đơn vị tile)
    - heightScaleFactor: Hệ số chiều cao - dùng hsf_finder.py để tìm
      (điều chỉnh vị trí midpoint từ bảng tên xuống vị trí thực nhân vật)
    
    Ví dụ: Eve có speed=2.4, attack_range=9.33, heightScaleFactor=0.158
    """
    speed = 2.4             # Tốc độ di chuyển (tile/giây)
    attack_range = 9.33     # Tầm đánh (tile)
    heightScaleFactor = 0.158  # Hệ số dịch chuyển dọc cho vị trí nhân vật
    
    # =========================================================================
    # PHẦN 2: ĐẶC TÍNH BẢN ĐỒ
    # Thay đổi để phù hợp với bản đồ đang chơi
    # =========================================================================
    
    """
    sharpCorner: Bản đồ có nhiều tường/góc nhọn không?
        True  -> Tăng thời gian di chuyển 5% (bù cho việc đi vòng qua tường)
        False -> Thời gian di chuyển bình thường
    
    centerOrder: Brawler spawn ở giữa hay ở rìa bản đồ?
        True  -> Ưu tiên di chuyển về trung tâm (spawn ở rìa)
        False -> Đi đến bụi cỏ gần nhất (spawn ở giữa)
    """
    sharpCorner = True     # Bản đồ có nhiều tường
    centerOrder = True     # Ưu tiên di chuyển về trung tâm
    
    # =========================================================================
    # PHẦN 3: CẤU HÌNH BLUESTACKS
    # =========================================================================
    
    """
    Tên cửa sổ BlueStacks. Nếu chạy multiple instance, tên sẽ khác nhau:
    "Bluestacks App Player 1", "Bluestacks App Player 2"...
    Kiểm tra tên ở góc trên-trái cửa sổ BlueStacks.
    
    Nếu gặp lỗi "Bluestacks App Player not found", thay đổi tên cho đúng.
    """
    window_name = "Bluestacks App Player"
    
    # True: Chụp cửa sổ bằng handle trực tiếp (nhanh hơn, cần focus)
    # False: Chụp toàn màn hình rồi crop (chậm hơn, không cần focus)
    # Nếu detection_test hiện màn hình đen -> đổi thành False
    focused_window = False

    # =========================================================================
    # PHẦN 4: CẤU HÌNH GPU
    # =========================================================================
    
    # True: Dùng CUDA (Nvidia GPU) - cần cài CUDA toolkit
    # False: Dùng OpenVINO (Intel/AMD CPU) - không cần GPU
    # None: Dùng TensorRT (Nvidia GPU) - hiệu suất cao nhất
    nvidia_gpu = False

    # =========================================================================
    # PHẦN 5: CHẾ ĐỘ DEBUG
    # =========================================================================
    
    """
    True: Mở cửa sổ OpenCV hiển thị ảnh chụp với annotation:
          - Dấu chữ thập tại các đối tượng được nhận diện
          - Viền vùng an toàn và lưới quadrant
          - Thông tin FPS
    False: Không hiện cửa sổ debug (tiết kiệm CPU)
    """
    DEBUG = False

    # =========================================================================
    # PHẦN 6: HẰNG SỐ CỐ ĐỊNH - KHÔNG NÊN THAY ĐỔI
    # =========================================================================
    
    # Danh sách tên lớp đối tượng YOLO nhận diện
    # Thứ tự phải khớp với model đã huấn luyện
    classes = ["Player","Bush","Enemy","Cubebox"]
    
    """
    Ngưỡng tin cậy (threshold) cho từng lớp nhận diện.
    Index tương ứng với classes:
      [0] Player:  0.37 (ngưỡng thấp vì quan trọng nhất)
      [1] Bush:    0.47
      [2] Enemy:   0.57
      [3] Cubebox:  0.65 (ngưỡng cao vì ít quan trọng)
    
    Nếu nhận diện sai nhiều (false positive), tăng threshold.
    Nếu bỏ sót nhiều (false negative), giảm threshold.
    """
    threshold = [0.37,0.47,0.57,0.65]

    # =========================================================================
    # PHẦN 7: TỰ ĐỘNG LẤY THÔNG SỐ BRAWLER TỪ JSON
    # =========================================================================
    
    try:
        # Tìm brawler trong file JSON (lowercase, bỏ khoảng trắng thừa)
        brawler_stats = brawler_stats_dict[brawler_name.lower().strip()]
        display_str = f"Using {brawler_name.upper()}'s stats if your selected brawler is not {brawler_name.upper()},\nplease manually modify at constants.py."
        standard_hsf = 0.15  # Hệ số chiều cao mặc định nếu không có trong JSON
        
        if len(brawler_stats) == 2:
            # JSON chỉ có speed và attack_range -> dùng HSF mặc định
            brawler_stats.append(standard_hsf)
        elif len(brawler_stats) > 3:
            # JSON có quá nhiều giá trị -> dùng thông số thủ công
            display_str = f"{brawler_name} in brawler_stats.json has more then 3 element, using stats at constants.py"
            brawler_stats = 3*[None]
    except KeyError:
        # Brawler không có trong JSON -> dùng thông số thủ công
        brawler_stats = 3*[None]
        display_str = f"{brawler_name.upper()}'s stats is not found in the JSON. \nUsing speed, attack_range and heightScaleFactor in constant.py.\nPlease manually modify at constants.py if you have not."
    
    # Hiển thị thông tin creator và thông số brawler
    print("")
    print(bcolors.BOLD + bcolors.OKGREEN + "Original Creator: https://github.com/Jooi025/BrawlStarsBot" + bcolors.ENDC)
    print("")
    print(bcolors.WARNING + display_str + bcolors.ENDC)
    
    # Gán thông số từ JSON (ưu tiên JSON, nếu None thì dùng giá trị thủ công)
    speed = brawler_stats[0] or speed               # Tốc độ (tile/giây)
    attack_range = brawler_stats[1] or attack_range  # Tầm đánh (tile)
    heightScaleFactor = brawler_stats[2] or heightScaleFactor  # Hệ số chiều cao
    
    print("")
    print(bcolors.OKBLUE + f"speed: {speed} tiles/second \nattack_range: {attack_range} tiles\nHeightScaleFactor: {heightScaleFactor}" + bcolors.ENDC)

    # =========================================================================
    # PHẦN 8: CẤU HÌNH MODEL YOLO
    # Chọn đường dẫn model và tham số inference dựa trên cấu hình GPU
    # =========================================================================
    
    if nvidia_gpu is None:
        # TensorRT: Hiệu suất cao nhất, cần Nvidia GPU + TensorRT
        model_file_path = "yolov8_model/yolov8.engine"
        half = False       # TensorRT đã tối ưu sẵn
        imgsz = 640        # Kích thước ảnh input
    elif nvidia_gpu:
        # PyTorch CUDA: Cần Nvidia GPU + CUDA toolkit
        model_file_path = "yolov8_model/yolov8.pt"
        half = False       # Dùng FP32 (chính xác hơn)
        imgsz = (384,640)  # Kích thước ảnh input (height, width)
    else:
        # OpenVINO: Chạy trên CPU Intel/AMD, không cần GPU
        model_file_path = "yolov8_model/yolov8_openvino_model"
        half = True        # Dùng FP16 (nhanh hơn trên CPU)
        imgsz = (384,640)  # Kích thước ảnh input
    
    # === Hằng số điều khiển bot ===
    movement_key = "middle"   # Phím chuột giữa để di chuyển nhân vật (drag trong BlueStacks)
    midpoint_offset = 12      # Offset dọc (pixel) để căn chỉnh vị trí nhân vật
    
    # =========================================================================
    # PHẦN 9: KIỂM TRA TÍNH HỢP LỆ CỦA CÁC THAM SỐ
    # Đảm bảo người dùng nhập đúng kiểu dữ liệu
    # =========================================================================
    
    # Nhóm tham số cần là số (int hoặc float)
    float_int_dict = {
        "speed":speed,
        "attack_range":attack_range,
        "heightScaleFactor": heightScaleFactor
    }

    # Nhóm tham số cần là boolean (True/False)
    bool_dict = {
        "sharpCorner": sharpCorner,
        "centerOrder": centerOrder,
    }

    # Kiểm tra kiểu dữ liệu - báo lỗi rõ ràng nếu sai
    for key in float_int_dict:
        assert type(float_int_dict[key]) == float or type(float_int_dict[key]) == int, f"{key.upper()} should be a integer or a float"

    for key in bool_dict:
        assert type(bool_dict[key]) == bool,f"{key.upper()} should be True or False"

if __name__ == "__main__":
    pass