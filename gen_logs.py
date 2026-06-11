import random

def generate_mock_log(filename: str, total_lines: int):
    print(f" 正在生成 {total_lines:,} 行测试日志（预计仅占用约 90MB 空间）...")
    
    statuses = [b"200", b"200", b"304", b"404", b"500"]
    routes = [b"/index.html", b"/api/v1/user", b"/login", b"/static/js/main.js"]
    
    # 使用 'wb' 模式直接写入二进制字节流，速度最快
    with open(filename, "wb") as f:
        for _ in range(total_lines):
            #  强行注入小花样：有 30% 的概率将时间固定在 14 点，人工制造峰值
            if random.random() < 0.3:
                hour = b"14"
            else:
                hour = f"{random.randint(0, 23):02d}".encode()
            
            ip = f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}".encode()
            minute = f"{random.randint(0, 59):02d}".encode()
            second = f"{random.randint(0, 59):02d}".encode()
            status = random.choice(statuses)
            route = random.choice(routes)
            size = str(random.randint(100, 5000)).encode()
            
            # 严格按照 log_parser.py 要求的 Nginx combined 格式拼接
            # 确保 parts[3][13:15] 能完美切出 hour
            line = (
                ip + b' - - [11/Jun/2026:' + hour + b':' + minute + b':' + second + 
                b' +0800] "GET ' + route + b' HTTP/1.1" ' + status + b' ' + size + b'\n'
            )
            f.write(line)
            
    print(f" 生成完毕！请使用以下命令跑通分析器：\n👉 python log_parser.py {filename}")

if __name__ == "__main__":
    # 正好 100 万行，控住体积
    generate_mock_log("nginx_access.log", 1000000)