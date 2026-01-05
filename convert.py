import requests
import subprocess
import os
import ipaddress

# 定义源文件
URLS = [
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/amazon/ipv4_merged.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/microsoft/ipv4_merged.txt",
    "https://raw.githubusercontent.com/lord-alfred/ipranges/main/github/ipv4_merged.txt"
]

OUTPUT_FILENAME = "merged_cloud_ips.mrs"
TEMP_TXT = "combined_temp.txt"

def validate_and_clean_ip(line):
    """
    尝试解析一行文本是否为合法的 IP 或 CIDR。
    如果是，返回标准化的字符串；否则返回 None。
    """
    line = line.strip()
    # 去除行内注释 (例如: 1.1.1.1 # comment)
    if '#' in line:
        line = line.split('#')[0].strip()
    
    if not line:
        return None

    try:
        # strict=False 允许像 192.168.1.1/24 这样主机位不为0的写法
        net = ipaddress.ip_network(line, strict=False)
        return str(net)
    except ValueError:
        return None

def download_and_merge():
    combined_ips = set()
    print(">>> 开始下载并清洗 IP 数据...")
    
    for url in URLS:
        print(f"正在处理: {url}")
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            
            valid_count = 0
            lines = resp.text.splitlines()
            for raw_line in lines:
                clean_ip = validate_and_clean_ip(raw_line)
                if clean_ip:
                    combined_ips.add(clean_ip)
                    valid_count += 1
            
            print(f"  - 原始行数: {len(lines)}, 有效 IP 数: {valid_count}")
            
        except Exception as e:
            print(f"  - 下载失败: {e}")
            # 如果是关键源失败，建议抛出异常停止，或者根据需求继续
            # exit(1) 

    if not combined_ips:
        print("错误：没有提取到任何有效的 IP 地址，脚本终止。")
        exit(1)

    # 排序并写入临时文件
    print(f">>> 正在写入临时文件，共 {len(combined_ips)} 条唯一规则...")
    with open(TEMP_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(combined_ips))))
    
    # 确保输出目录存在
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", OUTPUT_FILENAME)

    # 调用 mihomo 转换
    print(f">>> 开始调用 Mihomo 内核转换至: {output_path}")
    
    # 获取当前目录的绝对路径，防止路径问题
    cwd = os.getcwd()
    mihomo_exec = os.path.join(cwd, "mihomo")
    
    # 检查 mihomo 是否存在且可执行
    if not os.path.exists(mihomo_exec):
        print(f"错误：找不到 mihomo 可执行文件: {mihomo_exec}")
        exit(1)

    try:
        # 使用 capture_output=True 捕获详细报错
        result = subprocess.run(
            [mihomo_exec, "convert-ruleset", "ipcidr", TEMP_TXT, output_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(">>> 转换成功！Success!")
            print(result.stdout)
        else:
            print(f"!!! 转换失败 (Exit Code {result.returncode}) !!!")
            print("错误详情 (Stderr):")
            print(result.stderr)
            exit(result.returncode) # 传递错误码给 GitHub Actions
            
    except Exception as e:
        print(f"执行子进程时发生未知错误: {e}")
        exit(1)
    finally:
        # 清理临时文件
        if os.path.exists(TEMP_TXT):
            os.remove(TEMP_TXT)

if __name__ == "__main__":
    download_and_merge()
