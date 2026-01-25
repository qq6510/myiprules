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

OUTPUT_FILENAME = "merged_cloud_ips.mrs"
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
            print(f"  - 原始行数: {len(lines)} | 有效 IP 数: {valid_count}")
        except Exception as e:
            print(f"  - 警告: 处理 {url} 时出错, 错误: {e}")

    if not combined_ips:
        print("错误：没有提取到任何有效的 IP 地址。")
        sys.exit(1)

    with open(TEMP_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(combined_ips))))
    
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", OUTPUT_FILENAME)

    # 兼容性处理：在系统路径或当前目录寻找 mihomo
    exe_name = "mihomo.exe" if sys.platform == "win32" else "mihomo"
    mihomo_path = shutil.which(exe_name) or os.path.join(os.getcwd(), exe_name)

    if not os.path.exists(mihomo_path):
        print(f"错误：找不到 {exe_name} 可执行文件。")
        sys.exit(1)

    if sys.platform != "win32":
        os.chmod(mihomo_path, 0o755)

    print(f">>> 开始转换至: {output_path}")
    try:
        result = subprocess.run(
            [mihomo_path, "convert-ruleset", "ipcidr", TEMP_TXT, output_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f">>> 转换成功！文件大小: {os.path.getsize(output_path)/1024:.2f} KB")
        else:
            print(f"转换失败: {result.stderr}")
            sys.exit(result.returncode)
    finally:
        if os.path.exists(TEMP_TXT): os.remove(TEMP_TXT)

if __name__ == "__main__":
    download_and_merge()
