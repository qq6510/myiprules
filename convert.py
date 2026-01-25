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
        # 自动处理 1.1.1.1/24 -> 1.1.1.0/24
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

    with open(TEMP_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(combined_ips))))
    
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", OUTPUT_FILENAME)

    cwd = os.getcwd()
    executable = "mihomo.exe" if sys.platform == "win32" else "mihomo"
    mihomo_path = os.path.join(cwd, executable)

    if not os.path.exists(mihomo_path):
        print(f"错误：找不到 {mihomo_path}")
        sys.exit(1)

    if sys.platform != "win32":
        os.chmod(mihomo_path, 0o755)

    print(f">>> 开始转换至 MRS: {output_path}")
    try:
        # 【修正后的命令】
        # 参数1: ipcidr (规则行为)
        # 参数2: text (源文件格式，因为临时文件是纯文本列表)
        result = subprocess.run(
            [mihomo_path, "convert-ruleset", "ipcidr", "text", TEMP_TXT, output_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            size = os.path.getsize(output_path) / 1024
            print(f">>> 成功！生成的 MRS 大小: {size:.2f} KB")
        else:
            print(f"!!! 转换失败 !!!\n错误详情: {result.stderr}")
            sys.exit(result.returncode)
            
    except Exception as e:
        print(f"发生异常: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(TEMP_TXT):
            os.remove(TEMP_TXT)

if __name__ == "__main__":
    download_and_merge()
