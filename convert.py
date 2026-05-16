import requests
import subprocess
import os
import ipaddress
import sys

# 提取公共变量，方便后续维护
SERVICES = ["facebook", "github", "twitter", "telegram", "openai", "perplexity"]
BASE_URL = "https://raw.githubusercontent.com/lord-alfred/ipranges/main/{}/{}.txt"

URLS_IPV4 = [BASE_URL.format(svc, "ipv4") for svc in SERVICES]
URLS_IPV6 = [BASE_URL.format(svc, "ipv6") for svc in SERVICES]

OUTPUT_DIR = "output"
OUTPUT_IPV4_TXT = "merged_ipv4.txt"
OUTPUT_IPV4_MRS = "merged_ipv4.mrs"
OUTPUT_IPV6_TXT = "merged_ipv6.txt"
OUTPUT_IPV6_MRS = "merged_ipv6.mrs"

def clean_and_validate_ip(line):
    # 统一处理注释并去除前后空格
    for char in ('#', ';'):
        if char in line:
            line = line.split(char, 1)[0]
    
    line = line.strip()
    if not line: 
        return None
        
    try:
        return ipaddress.ip_network(line, strict=False)
    except ValueError:
        return None

def download_and_merge(urls):
    raw_networks = []
    print(">>> 正在从远程源下载数据...")
    for url in urls:
        print(f"  正在请求: {url}")
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            
            count = 0
            for line in resp.text.splitlines():
                net = clean_and_validate_ip(line)
                if net:
                    raw_networks.append(net)
                    count += 1
            print(f"    - 成功提取 {count} 条记录")
        except Exception as e:
            print(f"    - 警告: 处理失败 {url}, 错误: {e}")
    return raw_networks

def save_and_convert(networks, txt_file, mrs_file, mihomo_path):
    if not networks:
        print(f"错误：未获取到任何有效 IP 数据，跳过 {txt_file}")
        return

    print(">>> 正在进行 CIDR 聚合与精简算法...")
    collapsed_networks = list(ipaddress.collapse_addresses(networks))
    sorted_ips = [str(net) for net in collapsed_networks]

    print(f"  - 原始总数: {len(networks)}")
    print(f"  - 精简后总数: {len(sorted_ips)} (减少了 {len(networks) - len(sorted_ips)} 条冗余)")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    txt_path = os.path.join(OUTPUT_DIR, txt_file)
    mrs_path = os.path.join(OUTPUT_DIR, mrs_file)

    print(f">>> 写入文本文件: {txt_path}")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_ips))

    print(f">>> 正在调用内核生成二进制 MRS: {mrs_path}")
    try:
        # 直接使用 txt_path 作为输入，舍弃 temp_file
        result = subprocess.run(
            [mihomo_path, "convert-ruleset", "ipcidr", "text", txt_path, mrs_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print(f">>> 处理完成！")
            print(f"    - [TXT] {txt_file}: {os.path.getsize(txt_path)/1024:.2f} KB")
            print(f"    - [MRS] {mrs_file}: {os.path.getsize(mrs_path)/1024:.2f} KB")
        else:
            print(f"!!! 转换失败 (Exit Code {result.returncode}) !!!")
            print(f"详细错误: {result.stderr}")
    except Exception as e:
        print(f"运行异常: {e}")

def check_mihomo():
    """提前检查并设置 mihomo 可执行文件"""
    mihomo_path = os.path.join(os.getcwd(), "mihomo")
    if not os.path.exists(mihomo_path):
        print(f"致命错误：在当前目录下未找到可执行文件 mihomo")
        sys.exit(1) # 找不到工具直接退出，避免浪费网络请求
    os.chmod(mihomo_path, 0o755)
    return mihomo_path

if __name__ == "__main__":
    # 1. 初始化检查
    mihomo_path = check_mihomo()

    # 2. 处理 IPv4
    print(">>> 正在下载并处理 IPv4...")
    ipv4_networks = download_and_merge(URLS_IPV4)
    save_and_convert(ipv4_networks, OUTPUT_IPV4_TXT, OUTPUT_IPV4_MRS, mihomo_path)

    # 3. 处理 IPv6
    print("\n>>> 正在下载并处理 IPv6...")
    ipv6_networks = download_and_merge(URLS_IPV6)
    save_and_convert(ipv6_networks, OUTPUT_IPV6_TXT, OUTPUT_IPV6_MRS, mihomo_path)

    print("\n>>> 所有处理完成！")
