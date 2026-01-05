import requests
import subprocess
import os
import re

# 配置需要合并的 IP 段网址
URLS = [
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/amazon/ipv4_merged.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/microsoft/ipv4_merged.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/github/ipv4_merged.txt"
]

OUTPUT_FILENAME = "merged_cloud_ips.mrs"

def is_valid_ip_cidr(line):
    # 正则表达式：只允许 IPv4/IPv6 或 CIDR 格式
    pattern = r'^([0-9a-fA-F:\./]+)$'
    return re.match(pattern, line) is not None

def download_and_merge():
    combined_ips = set()
    print("开始获取并清洗 IP 数据...")
    
    for url in URLS:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            
            count = 0
            for line in resp.text.splitlines():
                line = line.strip()
                # 排除空行、注释，并且必须符合 IP 格式特征
                if line and not line.startswith(('#', ';', '//')) and is_valid_ip_cidr(line):
                    combined_ips.update(line.split()) # 防止一行多个 IP
                    count += 1
            print(f"成功获取并提取 {count} 条记录: {url}")
        except Exception as e:
            print(f"抓取失败 {url}: {e}")

    if not combined_ips:
        print("错误：未提取到任何有效 IP 段，终止转换。")
        exit(1)

    # 2. 写入临时文件
    temp_txt = "combined_temp.txt"
    with open(temp_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(combined_ips))))
    
    # 3. 确保输出目录存在
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", OUTPUT_FILENAME)

    # 4. 执行转换 (使用绝对路径增强稳定性)
    print(f"正在转换至: {output_path}...")
    try:
        current_dir = os.getcwd()
        mihomo_path = os.path.join(current_dir, "mihomo")
        result = subprocess.run(
            [mihomo_path, "convert-ruleset", "ipcidr", temp_txt, output_path],
            capture_output=True, text=True, check=True
        )
        print("--- 转换完成 ---")
    except subprocess.CalledProcessError as e:
        print(f"Mihomo 转换失败 (Exit Code {e.returncode}):")
        print(f"错误输出: {e.stderr}")
        exit(3)
    finally:
        if os.path.exists(temp_txt):
            os.remove(temp_txt)

if __name__ == "__main__":
    download_and_merge()
