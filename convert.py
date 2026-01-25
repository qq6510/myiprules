import requests
import subprocess
import os
import ipaddress
import sys

# IPv4 和 IPv6 源地址配置
URLS_IPV4 = [
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/facebook/ipv4.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/github/ipv4.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/twitter/ipv4.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/telegram/ipv4.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/openai/ipv4.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/perplexity/ipv4.txt"
]

URLS_IPV6 = [
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/facebook/ipv6.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/github/ipv6.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/twitter/ipv6.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/telegram/ipv6.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/openai/ipv6.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/perplexity/ipv6.txt"
]

# 输出文件名配置
OUTPUT_DIR = "output"
OUTPUT_IPV4_TXT = "merged_ipv4.txt"
OUTPUT_IPV4_MRS = "merged_ipv4.mrs"
OUTPUT_IPV6_TXT = "merged_ipv6.txt"
OUTPUT_IPV6_MRS = "merged_ipv6.mrs"
TEMP_IPV4 = "temp_ipv4.txt"
TEMP_IPV6 = "temp_ipv6.txt"

def clean_and_validate_ip(line):
    line = line.strip()
    if '#' in line: line = line.split('#')[0].strip()
    if ';' in line: line = line.split(';')[0].strip()
    if not line: return None
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
            lines = resp.text.splitlines()
            count = 0
            for line in lines:
                net = clean_and_validate_ip(line)
                if net:
                    raw_networks.append(net)
                    count += 1
            print(f"    - 成功提取 {count} 条记录")
        except Exception as e:
            print(f"    - 警告: 处理失败 {url}, 错误: {e}")
    return raw_networks

def save_and_convert(networks, txt_file, mrs_file, temp_file):
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

    # 保存 TXT 文件
    print(f">>> 写入文本文件: {txt_path}")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_ips))

    # 临时文件用于转换
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_ips))

    # 调用 Mihomo 转换
    cwd = os.getcwd()
    executable = "mihomo.exe" if sys.platform == "win32" else "mihomo"
    mihomo_path = os.path.join(cwd, executable)

    if not os.path.exists(mihomo_path):
        print(f"错误：在当前目录下未找到可执行文件 {executable}")
        return

    if sys.platform != "win32":
        os.chmod(mihomo_path, 0o755)

    print(f">>> 正在调用内核生成二进制 MRS: {mrs_path}")
    try:
        result = subprocess.run(
            [mihomo_path, "convert-ruleset", "ipcidr", "text", temp_file, mrs_path],
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
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

if __name__ == "__main__":
    print(">>> 正在下载并处理 IPv4...")
    ipv4_networks = download_and_merge(URLS_IPV4)
    save_and_convert(ipv4_networks, OUTPUT_IPV4_TXT, OUTPUT_IPV4_MRS, TEMP_IPV4)

    print("\n>>> 正在下载并处理 IPv6...")
    ipv6_networks = download_and_merge(URLS_IPV6)
    save_and_convert(ipv6_networks, OUTPUT_IPV6_TXT, OUTPUT_IPV6_MRS, TEMP_IPV6)

    print("\n>>> 所有处理完成！")
