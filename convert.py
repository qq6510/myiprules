import ipaddress
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Set, Tuple, List
import requests
from requests.adapters import HTTPAdapter

# 1. 基础配置
PREVIOUS_URL = "https://raw.githubusercontent.com/QuixoticHeart/rule-set/ruleset/meta/ipcidr/gfw.list"
PREVIOUS_PROXY_URL = "https://raw.githubusercontent.com/QuixoticHeart/rule-set/refs/heads/ruleset/meta/ipcidr/proxy.list"
SERVICES = ["facebook", "github", "twitter", "telegram", "openai", "perplexity"]
BASE_URL = "https://raw.githubusercontent.com/lord-alfred/ipranges/main/{}/{}.txt"

OUTPUT_DIR = "output"
OUTPUT_IPV4_TXT = "merged_ipv4.txt"
OUTPUT_IPV4_MRS = "merged_ipv4.mrs"
OUTPUT_IPV6_TXT = "merged_ipv6.txt"
OUTPUT_IPV6_MRS = "merged_ipv6.mrs"

# 2. 线程局部变量：为每个线程创建安全的专属 Session
thread_local = threading.local()

def get_thread_session() -> requests.Session:
    """获取线程独立的 Session，配置连接池与重试策略"""
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=2)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        thread_local.session = session
    return thread_local.session

def check_mihomo() -> str:
    """检查并配置 mihomo 内核"""
    mihomo_path = os.path.join(os.getcwd(), "mihomo")
    if not os.path.exists(mihomo_path):
        print("致命错误：当前目录下未找到可执行文件 mihomo")
        sys.exit(1)
    os.chmod(mihomo_path, 0o755)
    return mihomo_path

def clean_and_validate_ip(line: str):
    """极致裁切注释并转换为 ip_network 对象"""
    # 利用 partition 替代 split，不产生多余列表，速度更快
    clean_line = line.partition('#')[0].partition(';')[0].strip()
    if not clean_line:
        return None
    try:
        return ipaddress.ip_network(clean_line, strict=False)
    except ValueError:
        return None

def fetch_and_categorize(urls: Set[str]) -> Tuple[Set[ipaddress.IPv4Network], Set[ipaddress.IPv6Network]]:
    """
    并发下载所有 URL，并在解析时利用 Set 进行 $O(1)$ 级别即时去重
    """
    ipv4_networks: Set[ipaddress.IPv4Network] = set()
    ipv6_networks: Set[ipaddress.IPv6Network] = set()

    print(f">>> 开始并发拉取 {len(urls)} 个规则源 (请求已去重)...")

    def _fetch(url: str):
        session = get_thread_session()
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            return url, resp.text
        except Exception as e:
            return url, e

    max_workers = min(len(urls), 10)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(_fetch, urls)

    for url, output in results:
        url_parts = url.rstrip('/').split('/')
        label = f"{url_parts[-2]}/{url_parts[-1]}" if len(url_parts) >= 2 else url_parts[-1]

        if isinstance(output, Exception):
            print(f"    - 警告: [{label}] 下载失败: {output}")
            continue

        v4_add, v6_add = 0, 0
        for line in output.splitlines():
            net = clean_and_validate_ip(line)
            if net:
                if net.version == 4:
                    if net not in ipv4_networks:
                        ipv4_networks.add(net)
                        v4_add += 1
                elif net.version == 6:
                    if net not in ipv6_networks:
                        ipv6_networks.add(net)
                        v6_add += 1

        print(f"    - [{label}] 新增有效唯一网段: IPv4={v4_add} 个, IPv6={v6_add} 个")

    return ipv4_networks, ipv6_networks

def process_and_convert(networks: Set[ipaddress._BaseNetwork], txt_file: str, mrs_file: str, mihomo_bin: str):
    """CIDR 聚合与 MRS 转换"""
    if not networks:
        print(f"警告：[{txt_file}] 无有效数据，跳过生成。")
        return

    raw_count = len(networks)
    print(f"\n>>> 正在对 [{txt_file}] 进行 CIDR 聚合合并 (去重后待处理数: {raw_count})...")

    # 预先去重后，collapse_addresses 的计算负担大幅减轻
    collapsed_networks = list(ipaddress.collapse_addresses(networks))
    final_count = len(collapsed_networks)

    print(f"  - 原始输入总数 (去重后): {raw_count}")
    print(f"  - 聚合精简后总数: {final_count} (进一步规约合并了 {raw_count - final_count} 个重叠网段)")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    txt_path = os.path.join(OUTPUT_DIR, txt_file)
    mrs_path = os.path.join(OUTPUT_DIR, mrs_file)

    # 写入文件
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(str(net) for net in collapsed_networks))

    print(f">>> 调用 Mihomo 生成 MRS: {mrs_path}")
    try:
        result = subprocess.run(
            [mihomo_bin, "convert-ruleset", "ipcidr", "text", txt_path, mrs_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print(f"    - [TXT] {txt_file}: {os.path.getsize(txt_path)/1024:.2f} KB")
            print(f"    - [MRS] {mrs_file}: {os.path.getsize(mrs_path)/1024:.2f} KB")
        else:
            print(f"!!! 转换失败 (Exit Code {result.returncode}) !!!\n{result.stderr}")
    except Exception as e:
        print(f"运行异常: {e}")

if __name__ == "__main__":
    mihomo_bin = check_mihomo()

    # 构建并去重 URL 集合
    target_urls: Set[str] = {PREVIOUS_URL, PREVIOUS_PROXY_URL}
    for svc in SERVICES:
        target_urls.add(BASE_URL.format(svc, "ipv4"))
        target_urls.add(BASE_URL.format(svc, "ipv6"))

    # 下载并分类去重
    ipv4_nets, ipv6_nets = fetch_and_categorize(target_urls)

    # 聚合转换
    process_and_convert(ipv4_nets, OUTPUT_IPV4_TXT, OUTPUT_IPV4_MRS, mihomo_bin)
    process_and_convert(ipv6_nets, OUTPUT_IPV6_TXT, OUTPUT_IPV6_MRS, mihomo_bin)

    print("\n>>> 全部作业处理完成！")
