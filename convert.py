import requests
import subprocess
import os
import ipaddress
import sys
import shutil

# 配置需要合并的 IP 段网址
URLS = [
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/amazon/ipv4_merged.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/microsoft/ipv4_merged.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/github/ipv4_merged.txt"
]

# 输出文件名配置
OUTPUT_MRS = "merged_cloud_ips.mrs"
OUTPUT_TXT = "merged_cloud_ips.txt"  # 新增文本输出文件名
TEMP_TXT = "combined_temp.txt"

def clean_and_validate_ip(line):
    line = line.strip()
    if '#' in line: line = line.split('#')[0].strip()
    if ';' in line: line = line.split(';')[0].strip()
    if not line: return None
    try:
        net = ipaddress.ip_network(line, strict=False)
        return str(net)
    except ValueError:
        return None

def download_and_merge():
    combined_ips = set()
    print(">>> 开始下载并清洗数据...")
    
    for url in URLS:
        print(f"正在处理: {url}")
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            lines = resp.text.splitlines()
            valid_count = 0
            for line in lines:
                clean_ip = clean_and_validate_ip(line)
                if clean_ip:
                    combined_ips.add(clean_ip)
                    valid_count += 1
            print(f"  - 有效 IP 数: {valid_count}")
        except Exception as e:
            print(f"  - 警告: 处理 {url} 出错: {e}")

    if not combined_ips:
        print("错误：未提取到有效 IP")
        sys.exit(1)

    # 排序数据
    sorted_ips = sorted(list(combined_ips))
    
    # 准备输出目录
    os.makedirs("output", exist_ok=True)
    mrs_path = os.path.join("output", OUTPUT_MRS)
    txt_path = os.path.join("output", OUTPUT_TXT)

    # --- 1. 保存为 TXT 文件 ---
    print(f">>> 正在保存文本文件: {txt_path}")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_ips))

    # --- 2. 准备转换 MRS 的临时文件 ---
    with open(TEMP_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_ips))
    
    # 路径探测
    cwd = os.getcwd()
    executable = "mihomo.exe" if sys.platform == "win32" else "mihomo"
    mihomo_path = os.path.join(cwd, executable)

    if not os.path.exists(mihomo_path):
        print(f"错误：找不到 {mihomo_path}")
        sys.exit(1)

    if sys.platform != "win32":
        os.chmod(mihomo_path, 0o755)

    # --- 3. 调用转换 MRS ---
    print(f">>> 正在转换二进制 MRS: {mrs_path}")
    try:
        result = subprocess.run(
            [mihomo_path, "convert-ruleset", "ipcidr", "text", TEMP_TXT, mrs_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            mrs_size = os.path.getsize(mrs_path) / 1024
            txt_size = os.path.getsize(txt_path) / 1024
            print(f">>> 成功！")
            print(f"    - MRS 文件: {mrs_size:.2f} KB")
            print(f"    - TXT 文件: {txt_size:.2f} KB")
        else:
            print(f"!!! 转换失败 !!!\n{result.stderr}")
            sys.exit(result.returncode)
            
    except Exception as e:
        print(f"发生异常: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(TEMP_TXT):
            os.remove(TEMP_TXT)

if __name__ == "__main__":
    download_and_merge()
