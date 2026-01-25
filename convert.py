import requests
import subprocess
import os
import ipaddress
import sys

# 1. 配置需要合并的 IP 段网址
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
OUTPUT_IPV4_MRS = "merged_ipv4.mrs"
OUTPUT_IPV4_TXT = "merged_ipv4.txt"
OUTPUT_IPV6_MRS = "merged_ipv6.mrs"
OUTPUT_IPV6_TXT = "merged_ipv6.txt"

def clean_and_validate_ip(line):
    line = line.strip()
    if '#' in line: line = line.split('#')[0].strip()
    if ';' in line: line = line.split(';')[0].strip()
    if not line: return None
    try:
        # strict=False 极其重要：它会自动将 1.2.3.4/24 修正为网段首地址 1.2.3.0/24
        return ipaddress.ip_network(line, strict=False)
    except ValueError:
        return None

def download_and_merge():
    raw_networks = []
    print(">>> 正在从远程源下载数据...")
    
    for url in URLS:
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

    if not raw_networks:
        print("错误：未获取到任何有效 IP 数据，脚本终止。")
        sys.exit(1)

    # --- 核心逻辑：自动合并与精简 ---
    # 1. 自动去重
    # 2. 自动合并相邻网段 (例如两个连续的 /24 合并为 /23)
    # 3. 自动剔除包含关系 (例如有了 /16，自动删掉里面的 /24)
    print(">>> 正在进行 CIDR 聚合与精简算法...")
    collapsed_networks = list(ipaddress.collapse_addresses(raw_networks))
    
    # 转换为字符串并排序
    sorted_ips = [str(net) for net in collapsed_networks]
    
    # 统计信息
    print(f"  - 原始总数: {len(raw_networks)}")
    print(f"  - 精简后总数: {len(sorted_ips)} (减少了 {len(raw_networks) - len(sorted_ips)} 条冗余)")

    # 准备输出目录
    os.makedirs("output", exist_ok=True)
    mrs_path = os.path.join("output", OUTPUT_MRS)
    txt_path = os.path.join("output", OUTPUT_TXT)

    # --- 保存文本文件 ---
    print(f">>> 写入文本文件: {txt_path}")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_ips))

    # --- 准备转换二进制的临时文件 ---
    with open(TEMP_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_ips))
    
    # 环境探测
    cwd = os.getcwd()
    executable = "mihomo.exe" if sys.platform == "win32" else "mihomo"
    mihomo_path = os.path.join(cwd, executable)

    if not os.path.exists(mihomo_path):
        print(f"错误：在当前目录下未找到可执行文件 {executable}")
        sys.exit(1)

    if sys.platform != "win32":
        os.chmod(mihomo_path, 0o755)

    # --- 调用 Mihomo 转换为 MRS ---
    print(f">>> 正在调用内核生成二进制 MRS: {mrs_path}")
    try:
        # 针对 Alpha 版本的参数：behavior=ipcidr, format=text
        result = subprocess.run(
            [mihomo_path, "convert-ruleset", "ipcidr", "text", TEMP_TXT, mrs_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            mrs_size = os.path.getsize(mrs_path) / 1024
            print(f">>> 处理圆满完成！")
            print(f"    - [TXT] 纯文本文件: {os.path.getsize(txt_path)/1024:.2f} KB")
            print(f"    - [MRS] 二进制文件: {mrs_size:.2f} KB")
        else:
            print(f"!!! 转换失败 (Exit Code {result.returncode}) !!!")
            print(f"详细错误: {result.stderr}")
            sys.exit(result.returncode)
            
    except Exception as e:
        print(f"运行异常: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(TEMP_TXT):
            os.remove(TEMP_TXT)

if __name__ == "__main__":
    download_and_merge()
