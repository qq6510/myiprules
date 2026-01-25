import requests
import subprocess
import os
import ipaddress
import sys

# 配置需要合并的 IP 段网址
URLS = [
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/amazon/ipv4_merged.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/microsoft/ipv4_merged.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/github/ipv4_merged.txt"
]

OUTPUT_FILENAME = "merged_cloud_ips.mrs"
TEMP_TXT = "combined_temp.txt"

def clean_and_validate_ip(line):
    """
    使用 ipaddress 库严格验证 IP 或 CIDR。
    返回标准化的字符串，如果无效则返回 None。
    """
    line = line.strip()
    # 去除可能存在的行内注释
    if '#' in line:
        line = line.split('#')[0].strip()
    if ';' in line:
        line = line.split(';')[0].strip()
        
    if not line:
        return None

    try:
        # strict=False 允许像 10.0.0.1/24 这样主机位不为0的写法，自动修正为网段
        # 这一步是关键：它会过滤掉所有乱码、HTML、非 IP 字符
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
            
        except requests.exceptions.Timeout:
            print(f"  - 警告: 下载 {url} 超时")
        except requests.exceptions.RequestException as e:
            print(f"  - 警告: 无法下载 {url}, 错误: {e}")
        except Exception as e:
            print(f"  - 警告: 处理 {url} 时出错, 错误: {e}")

    if not combined_ips:
        print("错误：没有提取到任何有效的 IP 地址，脚本终止。")
        sys.exit(1)

    # 写入临时文件
    print(f">>> 正在合并并去重，共 {len(combined_ips)} 条规则...")
    with open(TEMP_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(combined_ips))))
    
    # 准备输出路径
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", OUTPUT_FILENAME)

    # 调用 Mihomo
    print(f">>> 开始转换至: {output_path}")
    cwd = os.getcwd()
    mihomo_path = os.path.join(cwd, "mihomo")

    if not os.path.exists(mihomo_path):
        print("错误：找不到 mihomo 可执行文件")
        print("请确保 mihomo 文件在当前目录中")
        sys.exit(1)

    # 确保有执行权限
    os.chmod(mihomo_path, 0o755)

    try:
        result = subprocess.run(
            [mihomo_path, "convert-ruleset", "ipcidr", TEMP_TXT, output_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print(">>> 转换成功！Success!")
            # 打印文件大小
            size = os.path.getsize(output_path) / 1024
            print(f"文件大小: {size:.2f} KB")
        else:
            print(f"!!! 转换失败 (Exit Code {result.returncode}) !!!")
            if result.stdout:
                print("标准输出:")
                print(result.stdout)
            if result.stderr:
                print("错误输出:")
                print(result.stderr)
            sys.exit(result.returncode)
            
    except subprocess.TimeoutExpired:
        print("错误：转换超时（超过 60 秒）")
        sys.exit(1)
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)
    finally:
        if os.path.exists(TEMP_TXT):
            os.remove(TEMP_TXT)

if __name__ == "__main__":
    download_and_merge()
