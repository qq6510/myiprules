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
    # 移除注释
    if '#' in line: line = line.split('#')[0].strip()
    if ';' in line: line = line.split(';')[0].strip()
    if not line: return None
    try:
        # strict=False 自动处理非网段首地址的输入，例如 1.1.1.1/24 -> 1.1.1.0/24
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
            print(f"  - 警告: 处理 {url} 时出错: {e}")

    if not combined_ips:
        print("错误：未提取到任何有效 IP 地址，脚本终止。")
        sys.exit(1)

    # 写入临时文件供 mihomo 读取
    print(f">>> 正在合并去重，共 {len(combined_ips)} 条规则...")
    with open(TEMP_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(combined_ips))))
    
    # 准备输出目录
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", OUTPUT_FILENAME)

    # 路径探测
    cwd = os.getcwd()
    executable = "mihomo.exe" if sys.platform == "win32" else "mihomo"
    mihomo_path = os.path.join(cwd, executable)

    if not os.path.exists(mihomo_path):
        print(f"错误：找不到可执行文件 {mihomo_path}")
        sys.exit(1)

    # 确保执行权限
    if sys.platform != "win32":
        os.chmod(mihomo_path, 0o755)

    print(f">>> 开始转换至 MRS: {output_path}")
    try:
        # 【核心修正】：针对 Alpha 版本的 4 参数要求
        # 参数顺序: convert-ruleset <behavior> <format> <input> <output>
        result = subprocess.run(
            [mihomo_path, "convert-ruleset", "ipcidr", "ipcidr", TEMP_TXT, output_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            size = os.path.getsize(output_path) / 1024
            print(f">>> 成功！生成的 MRS 文件大小: {size:.2f} KB")
        else:
            print(f"!!! 转换失败 (Exit Code {result.returncode}) !!!")
            print(f"错误详情: {result.stderr}")
            sys.exit(result.returncode)
            
    except Exception as e:
        print(f"发生异常: {e}")
        sys.exit(1)
    finally:
        # 清理临时文件
        if os.path.exists(TEMP_TXT):
            os.remove(TEMP_TXT)

if __name__ == "__main__":
    download_and_merge()
