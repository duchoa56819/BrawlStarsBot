# ============================================================================
# Module: print.py
# Mô tả: Module hỗ trợ in text màu ra terminal.
#         Sử dụng mã ANSI escape để thay đổi màu/kiểu chữ trong terminal.
#         
#         Cách dùng: print(bcolors.WARNING + "Cảnh báo!" + bcolors.ENDC)
#         Luôn kết thúc bằng ENDC để reset về màu mặc định.
#         
# Tham khảo: https://stackoverflow.com/questions/287871/how-do-i-print-colored-text-to-the-terminal
# ============================================================================

class bcolors:
    HEADER = '\033[95m'     # Màu tím nhạt - dùng cho tiêu đề, header
    OKBLUE = '\033[94m'     # Màu xanh dương - dùng cho thông tin thành công
    OKCYAN = '\033[96m'     # Màu xanh lục lam (cyan) - dùng cho thông tin phụ
    OKGREEN = '\033[92m'    # Màu xanh lá - dùng cho trạng thái OK/thành công
    WARNING = '\033[93m'    # Màu vàng - dùng cho cảnh báo
    FAIL = '\033[91m'       # Màu đỏ - dùng cho lỗi/thất bại
    ENDC = '\033[0m'        # Reset về mặc định - LUÔN dùng sau khi đổi màu
    BOLD = '\033[1m'        # In đậm
    UNDERLINE = '\033[4m'   # Gạch chân