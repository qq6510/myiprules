import requests
import subprocess
import os
import ipaddress
import sys
from concurrent.futures import ThreadPoolExecutor  # 引入线程池实现并发

# 提取公共变量，方便后续维护
# 新增：将 QuixoticHeart/rule-set 中的 gfw.list（包含多服务 IPv4/IPv6 列表）的 raw 链接
# 我使用了该文件的具体 commit OID 来确保引用固定版本（避免主分支变动导致内容不稳定）
PREVIOUS_URL = "https://raw.githubusercontent.com/QuixoticHeart/rule-set/f2917bd3eff4e2d8823f7d154bce885ca5c43b6e/meta/ipcidr/gfw.list"
# 新增 proxy.list（与 gfw.list 同一 commit OID，包含代理相关的 ip 段）
PREVIOUS_PROXY_URL = "https://raw.githubusercontent.com/QuixoticHeart/rule-set/f2917bd3eff4e2d8823f7d154bce885ca5c43b6e/files/meta/ipcidr/proxy.list"

SERVICES = ["facebook", "github", "twitter", "telegram", "openai", "perplexity"]
BASE_URL = "https://raw.githubusercontent.com/lord-alfred/ipranges/main/{}/{}.txt"

# 将 PREVIOUS_URL 和 PREVIOUS_PROXY_URL 放在每个 URL 列表的最前面（保证优先使用）
URLS_IPV4 = [PREVIOUS_URL, PREVIOUS_PROXY_URL] + [BASE_URL.format(svc, "ipv4") for svc in SERVICES]
URLS_IPV6 = [PREVIOUS_URL, PREVIOUS_PROXY_URL] + [BASE_URL.format(svc, "ipv6") for svc in SERVICES]

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

def _fetch_single_url(url):
    """单条 URL 下载线程函数"""
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return url, resp.text
    except Exception as e:
        return url, e

def download_and_merge(urls):
    raw_networks = []
    print(">>> 正在从远程源并发下载数据...")
    
    # 优化点：使用线程池并发请求所有 URL，最大线程数匹配 URL 数量
    max_workers = min(len(urls), 8)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # map 会按输入顺序返回结果
        results = executor.map(_fetch_single_url, urls)
            
    for url, output in results:
        # 从 URL 中提取服务名称（如 facebook），让日志更清爽
        svc_name = url.split('/')[-2]
        
        if isinstance(output, Exception):
            print(f"    - 警告: [{svc_name}] 下载失败, 错误: {output}")
            continue
            
        count = 0
        for line in output.splitlines():
            net = clean_and_validate_ip(line)
            if net:
                raw_networks.append(net)
                count += 1
        print(f"    - 成功提取 [{svc_name}]: {count} 条记录")
        
    return raw_networks

def save_and_convert(networks, txt_file, mrs_file, mihomo_path):
    if not networks:
        print(f"错误：未获取到任何有效 IP 数据，跳过 {txt_file}")
        return

    # 根据目标文件名判断要处理的 IP 版本（IPv4/IPv6），并过滤掉非目标版本的网段
    target_version = None
    if 'ipv4' in txt_file.lower():
        target_version = 4
    elif 'ipv6' in txt_file.lower():
        target_version = 6

    if target_version is not None:
        filtered_networks = [n for n in networks if getattr(n, 'version', None) == target_version]
        if not filtered_networks:
            print(f"错误：未获取到任何有效 IPv{target_version} 数据，跳过 {txt_file}")
            return
        networks = filtered_networks

    print(">>> 正在进行 CIDR 聚合与精简算法...")
    # collapse_addresses 核心：自动将连续的、重叠的网段合并（例如 192.168.1.0/24 和 192.168.0.0/24 合并为 /23）
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
        sys.exit(1)
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
