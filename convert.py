import ipaddress
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Set, Tuple, List, Optional
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
OUTPUT_ALL_TXT = "merged_all.txt"
OUTPUT_ALL_MRS = "merged_all.mrs"

# 预编译 C-Regex 匹配合法 IP/CIDR 字符（比逐行创建 Python Set 实例快 5~10 倍）
RE_FAST_IP = re.compile(r'^[0-9a-fA-F.:/]+$')

# 2. 线程局部变量
thread_local = threading.local()

def get_thread_session() -> requests.Session:
    """获取线程独立的 Session 并配置 Header 与连接池"""
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=2)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        thread_local.session = session
    return thread_local.session

def check_mihomo() -> str:
    """检查并配置 mihomo 内核（支持当前目录与系统 PATH 自动降级）"""
    exec_name = "mihomo.exe" if sys.platform == "win32" else "mihomo"
    local_path = os.path.join(os.getcwd(), exec_name)
    
    if os.path.exists(local_path):
        if sys.platform != "win32":
            os.chmod(local_path, 0o755)
        return local_path

    path_bin = shutil.which(exec_name) or shutil.which("mihomo")
    if path_bin:
        return path_bin

    print(f"致命错误：未在当前目录或系统 PATH 中找到可执行文件 {exec_name}")
    sys.exit(1)

def clean_and_validate_ip(line: str) -> Optional[ipaddress._BaseNetwork]:
    """
    清洗并解析 IP/CIDR
    优化策略：
    1. 短路注释判断（99% 的纯 IP 行跳过 find 检索）
    2. C-Regex 快速拦截非 IP 行，零 Exception 抛出
    3. 区分 IPv4/IPv6 直接实例化，规避 ipaddress.ip_network 内部针对 IPv6 的 ValueError 抛出/捕获开销
    """
    # 只有在存在注释符号时才进行截断处理
    if '#' in line or ';' in line or '//' in line:
        for comment_symbol in ('#', ';', '//'):
            pos = line.find(comment_symbol)
            if pos != -1:
                line = line[:pos]

    clean_line = line.strip(" \t\r\n-+*\'\"")
    if not clean_line:
        return None

    # 处理 Clash 逗号分隔格式 (如 IP-CIDR,1.1.1.1/32,no-resolve)
    if ',' in clean_line:
        for part in clean_line.split(','):
            part = part.strip(" \t\r\n\'\"")
            if part and RE_FAST_IP.match(part):
                try:
                    if ':' in part:
                        return ipaddress.IPv6Network(part, strict=False)
                    return ipaddress.IPv4Network(part, strict=False)
                except ValueError:
                    continue
        return None

    # Fast-Path C-Regex 匹配：极速过滤非 IP 文本（域名/YAML 格式）
    if not RE_FAST_IP.match(clean_line):
        return None

    # 根据字符特征精准分流，避免 ip_network 内隐式抛出 ValueError 异常
    try:
        if ':' in clean_line:
            return ipaddress.IPv6Network(clean_line, strict=False)
        return ipaddress.IPv4Network(clean_line, strict=False)
    except ValueError:
        return None

def fetch_and_parse_worker(url: str) -> Tuple[str, Set[ipaddress.IPv4Network], Set[ipaddress.IPv6Network], Optional[Exception]]:
    """线程池 Task：在工作线程内部同时完成 HTTP 下载与 CPU 文本解析"""
    session = get_thread_session()
    v4_set: Set[ipaddress.IPv4Network] = set()
    v6_set: Set[ipaddress.IPv6Network] = set()
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()

        for line in resp.text.splitlines():
            net = clean_and_validate_ip(line)
            if net:
                if net.version == 4:
                    v4_set.add(net)
                else:
                    v6_set.add(net)

        return url, v4_set, v6_set, None
    except Exception as e:
        return url, v4_set, v6_set, e

def fetch_and_categorize(urls: Set[str]) -> Tuple[Set[ipaddress.IPv4Network], Set[ipaddress.IPv6Network]]:
    """并发下载并并行解析所有规则源"""
    ipv4_networks: Set[ipaddress.IPv4Network] = set()
    ipv6_networks: Set[ipaddress.IPv6Network] = set()

    print(f">>> 开始并发拉取并并行解析 {len(urls)} 个规则源...")

    max_workers = min(len(urls), 10)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_and_parse_worker, url) for url in urls]

        for future in as_completed(futures):
            url, v4_set, v6_set, error = future.result()
            url_parts = url.rstrip('/').split('/')
            label = f"{url_parts[-2]}/{url_parts[-1]}" if len(url_parts) >= 2 else url_parts[-1]

            if error:
                print(f"    - 警告: [{label}] 下载/解析失败: {error}")
                continue

            v4_before = len(ipv4_networks)
            v6_before = len(ipv6_networks)

            # 在 C 语言层面快速做集合合并
            ipv4_networks.update(v4_set)
            ipv6_networks.update(v6_set)

            v4_added = len(ipv4_networks) - v4_before
            v6_added = len(ipv6_networks) - v6_before
            print(f"    - [{label}] 解析完成，新增有效唯一网段: IPv4={v4_added} 个, IPv6={v6_added} 个")

    return ipv4_networks, ipv6_networks

def save_and_convert_single_task(task_args: Tuple[List[str], str, str, str]):
    """保存 TXT 并并行调用 Mihomo 转换为 MRS"""
    lines, txt_file, mrs_file, mihomo_bin = task_args
    if not lines:
        print(f"警告：[{txt_file}] 无有效数据，跳过生成。")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    txt_path = os.path.join(OUTPUT_DIR, txt_file)
    mrs_path = os.path.join(OUTPUT_DIR, mrs_file)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        result = subprocess.run(
            [mihomo_bin, "convert-ruleset", "ipcidr", "text", txt_path, mrs_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print(f"    - [OK] {txt_file} ({os.path.getsize(txt_path)/1024:.1f} KB) -> {mrs_file} ({os.path.getsize(mrs_path)/1024:.1f} KB)")
        else:
            print(f"!!! [{mrs_file}] 转换失败 (Exit Code {result.returncode}) !!!\n{result.stderr}")
    except Exception as e:
        print(f"运行 [{mrs_file}] 异常: {e}")

if __name__ == "__main__":
    mihomo_bin = check_mihomo()

    # 1. 构建去重 URL 集合
    target_urls: Set[str] = {PREVIOUS_URL, PREVIOUS_PROXY_URL}
    for svc in SERVICES:
        target_urls.add(BASE_URL.format(svc, "ipv4"))
        target_urls.add(BASE_URL.format(svc, "ipv6"))

    # 2. 并发拉取 + 并行 CPU 文本解析
    ipv4_nets, ipv6_nets = fetch_and_categorize(target_urls)

    # 3. CIDR 聚合精简并转换为字符串列表
    print("\n>>> 正在对 IPv4 进行 CIDR 聚合精简...")
    lines_v4 = [str(net) for net in ipaddress.collapse_addresses(ipv4_nets)]
    print(f"    IPv4 原始: {len(ipv4_nets)} 条 -> 聚合后: {len(lines_v4)} 条")

    print("\n>>> 正在对 IPv6 进行 CIDR 聚合精简...")
    lines_v6 = [str(net) for net in ipaddress.collapse_addresses(ipv6_nets)]
    print(f"    IPv6 原始: {len(ipv6_nets)} 条 -> 聚合后: {len(lines_v6)} 条")

    lines_all = lines_v4 + lines_v6

    # 4. 多线程并行写盘与 Mihomo 转码
    print("\n>>> 并行生成 TXT 与二进制 MRS 产物...")
    tasks = [
        (lines_v4, OUTPUT_IPV4_TXT, OUTPUT_IPV4_MRS, mihomo_bin),
        (lines_v6, OUTPUT_IPV6_TXT, OUTPUT_IPV6_MRS, mihomo_bin),
        (lines_all, OUTPUT_ALL_TXT, OUTPUT_ALL_MRS, mihomo_bin),
    ]

    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(save_and_convert_single_task, tasks))

    print("\n>>> 全部作业处理完成！")
