"""多进程 mmap 日志解析器

从 Nginx access log 中提取每小时请求数，找到峰值时段。
使用 mmap 实现零拷贝文件读取，多进程分块并行处理。
"""

import os
import sys
import time
import mmap
from collections import Counter
from multiprocessing import Pool


# ---------------------------------------------------------------------------
#  1. 小时提取（无正则，纯索引切片）
# ---------------------------------------------------------------------------

def parse_hour(line: bytes) -> int | None:
    """从一行 Nginx 日志中提取小时。

    日志格式（combined）:
      192.168.1.1 - - [10/Jun/2026:14:30:25 +0800] "GET /api HTTP/1.1" ...

    按空格分割后 parts[3] = b'[10/Jun/2026:14:30:25'
    再取 bytes 切片 [13:15] = b'14' → int(14)
    """
    try:
        parts = line.split(b" ")
        if len(parts) < 5:
            return None
        return int(parts[3][13:15])
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------------------
#  2. 分块处理（mmap 零拷贝 + 行对齐）
# ---------------------------------------------------------------------------

def process_chunk(args: tuple) -> tuple:
    """处理文件的一个字节区间 [start, end)。

    如果 start 落在某行中间，向后回退到上一个 \n，保证以完整行开头。
    遇到超出 end 的 \n 就停，不处理跨边界的不完整行。
    """
    filepath, start, end = args
    counter: Counter = Counter()
    lines_processed = 0

    with open(filepath, "rb") as f:
        # 将整个文件映射到虚拟内存（多进程各自映射，OS 共享物理页）
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            # ── 对齐到行首 ──
            pos = start
            if pos > 0:
                while pos > 0 and m[pos - 1] != ord("\n"):
                    pos -= 1
            # pos 现在指向一个完整行的开头
            adjusted_start = pos

            # ── 逐行遍历（基于 mmap 切片，零拷贝） ──
            while pos < end:
                nl = m.find(b"\n", pos)
                if nl == -1 or nl >= end:
                    break

                line = m[pos:nl]
                if line:
                    hour = parse_hour(line)
                    if hour is not None:
                        counter[hour] += 1
                        lines_processed += 1

                pos = nl + 1

    return counter, lines_processed, adjusted_start


# ---------------------------------------------------------------------------
#  3. 主入口
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(f"用法: python {os.path.basename(__file__)} <nginx_log_file> [num_workers]")
        sys.exit(1)

    filepath = sys.argv[1]
    num_workers = int(sys.argv[2]) if len(sys.argv) > 2 else os.cpu_count() or 4

    if not os.path.exists(filepath):
        print(f"文件不存在: {filepath}")
        sys.exit(1)

    file_size = os.path.getsize(filepath)
    print(f"文件大小: {file_size / (1024*1024):.2f} MB")
    print(f"工作进程: {num_workers}")

    # ── 切分字节区间 ──
    chunk_size = file_size // num_workers
    chunks = []
    for i in range(num_workers):
        start = i * chunk_size
        end = file_size if i == num_workers - 1 else (i + 1) * chunk_size
        chunks.append((filepath, start, end))

    # ── 多进程并行 ──
    t0 = time.time()
    total_counter: Counter = Counter()
    total_lines = 0

    with Pool(num_workers) as pool:
        results = pool.map(process_chunk, chunks)

    for counter, lines_processed, _ in results:
        total_counter += counter
        total_lines += lines_processed

    elapsed = time.time() - t0

    # ── 输出统计 ──
    print(f"\n解析完成: {total_lines} 行")
    print(f"耗时: {elapsed:.2f} 秒  |  吞吐: {total_lines / elapsed:.0f} 行/秒")

    if total_counter:
        peak_hour, peak_count = total_counter.most_common(1)[0]
        max_bar = peak_count if peak_count >= 30 else 30

        print(f"\n每小时请求分布:")
        for hour in sorted(total_counter):
            count = total_counter[hour]
            bar_len = max(1, count * 30 // max_bar)
            tag = "  ← 峰值" if count == peak_count else ""
            print(f"  {hour:02d}:00  {'█' * bar_len}  {count}{tag}")

        print(f"\n峰值流量: {peak_hour:02d}:00 — {peak_count} 次请求")
    else:
        print("未解析到有效日志行（请确认文件是 Nginx combined 格式）")


if __name__ == "__main__":
    main()
